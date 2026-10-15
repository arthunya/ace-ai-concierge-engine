"""A.C.E. Layer 1 — Automated Invoice Ingestion (Working Paper §3.2).

WHAT THIS MODULE ACTUALLY DOES
    It parses the *text layer* of a supplier invoice into structured line
    items, fuzzy-matches each line to an inventory SKU, and routes each line
    to one of three outcomes defined in Working Paper §3.2:

        auto_sync             match >= 80% AND price change <= 5%
        manager_confirmation  match >= 80% AND price change  > 5%   (§3.2, §5.2)
        manual_review         match  < 80%                          (§3.2)

WHAT THIS MODULE DOES NOT DO
    It does not perform optical character recognition. Working Paper §3.2
    specifies "a fine-tuned transformer model for restaurant invoice format
    recognition"; no such model is trained or invoked here, and none is
    claimed. Phase 1 consumes a text rendering of the invoice and records
    how that text was obtained in `extraction_method`, so a reader can never
    mistake a fixture for a live OCR result.

    Consequently this repository reports NO OCR accuracy figure. Character-
    and field-level accuracy are measurable only against a labelled corpus of
    real supplier invoices, which does not exist in this project.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process, utils as fuzz_utils

from ace import db

logger = logging.getLogger(__name__)

# Units seen on U.S. foodservice distributor invoices.
UNITS = ("CS", "EA", "LB", "KG", "OZ", "GAL", "QT", "PK", "BAG", "BOX", "DZ")

# Line-item forms this parser accepts. Both are anchored and require a
# trailing unit price + extended price, which is what distinguishes a line
# item from a header, footer, or address line.
_UNIT_ALT = "|".join(UNITS)
_QTY = r"(?P<qty>[\d,]+(?:\.\d+)?)"


def _money(name: str) -> str:
    return rf"\$?\s*(?P<{name}>[\d,]+\.\d{{2}})"


# The shared tail of both line forms: UNIT  QTY  UNIT_PRICE  EXTENDED
_TAIL = (
    rf"(?P<unit>{_UNIT_ALT})\s+{_QTY}\s+"
    rf"{_money('unit_price')}\s+{_money('extended')}\s*$"
)

# ITEMCODE  DESCRIPTION  UNIT  QTY  UNIT_PRICE  EXTENDED
LINE_WITH_CODE = re.compile(
    rf"^\s*(?P<code>[A-Z0-9][A-Z0-9\-_/]{{2,}})\s{{2,}}"
    rf"(?P<desc>\S.*?)\s{{2,}}" + _TAIL,
    re.IGNORECASE,
)

# DESCRIPTION  UNIT  QTY  UNIT_PRICE  EXTENDED   (no supplier item code column)
LINE_NO_CODE = re.compile(
    rf"^\s*(?P<desc>\S.*?)\s{{2,}}" + _TAIL,
    re.IGNORECASE,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def portable_source_path(path: Path) -> str:
    """Repo-relative POSIX path for storage and display.

    Absolute paths leak the operating user's name and local directory layout
    into the database, the API responses, and the built dashboard — which is
    published. Files inside the repository are recorded relative to its root;
    anything outside is reduced to its bare filename.
    """
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


SUPPLIER_RE = re.compile(r"^\s*(?:supplier|vendor|from)\s*:\s*(.+?)\s*$", re.IGNORECASE)
INVOICE_NO_RE = re.compile(r"^\s*invoice\s*(?:#|no\.?|number)\s*:?\s*(\S+)", re.IGNORECASE)
DATE_RE = re.compile(r"^\s*(?:invoice\s*)?date\s*:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "").replace("$", "").strip())


@dataclass
class ParsedLineItem:
    """One line item as read off the invoice, before SKU matching."""
    raw_text: str
    ingredient_name: str
    quantity: float
    unit: str
    unit_price: float
    total_price: float
    supplier_code: Optional[str] = None


@dataclass
class MatchedLineItem:
    """A parsed line item after SKU matching and routing."""
    parsed: ParsedLineItem
    matched_sku: Optional[str]
    match_confidence: float
    routing: str
    routing_reason: str
    previous_unit_price: Optional[float] = None
    price_change_pct: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "raw_text": self.parsed.raw_text,
            "ingredient_name": self.parsed.ingredient_name,
            "quantity": self.parsed.quantity,
            "unit": self.parsed.unit,
            "unit_price": round(self.parsed.unit_price, 2),
            "total_price": round(self.parsed.total_price, 2),
            "supplier_code": self.parsed.supplier_code,
            "matched_sku": self.matched_sku,
            "match_confidence": round(self.match_confidence, 4),
            "routing": self.routing,
            "routing_reason": self.routing_reason,
            "previous_unit_price": (
                round(self.previous_unit_price, 2)
                if self.previous_unit_price is not None else None
            ),
            "price_change_pct": (
                round(self.price_change_pct * 100, 1)
                if self.price_change_pct is not None else None
            ),
        }


@dataclass
class InvoiceResult:
    invoice_id: str
    source_path: str
    supplier_name: str
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    extraction_method: str
    is_demo: bool
    line_items: List[MatchedLineItem] = field(default_factory=list)

    @property
    def total_extracted(self) -> float:
        return sum(li.parsed.total_price for li in self.line_items)

    def counts(self) -> Dict[str, int]:
        c = {"auto_sync": 0, "manager_confirmation": 0, "manual_review": 0}
        for li in self.line_items:
            c[li.routing] += 1
        return c

    def to_dict(self) -> Dict:
        counts = self.counts()
        return {
            "invoice_id": self.invoice_id,
            "source_path": self.source_path,
            "supplier_name": self.supplier_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "extraction_method": self.extraction_method,
            "is_demo": self.is_demo,
            "items_extracted": len(self.line_items),
            "items_matched": sum(1 for li in self.line_items if li.matched_sku),
            "routing_counts": counts,
            "requires_manager_action": counts["manager_confirmation"]
                                       + counts["manual_review"] > 0,
            "total_extracted": round(self.total_extracted, 2),
            "line_items": [li.to_dict() for li in self.line_items],
        }


def parse_invoice_text(text: str) -> Tuple[Dict[str, Optional[str]], List[ParsedLineItem]]:
    """Parse invoice text into a header dict and a list of line items.

    Pure function — no I/O, no database. This is the unit under test.
    Lines that do not match a line-item form are ignored, which is how
    headers, totals, and address blocks are excluded.
    """
    header: Dict[str, Optional[str]] = {
        "supplier_name": None, "invoice_number": None, "invoice_date": None,
    }
    items: List[ParsedLineItem] = []

    for raw in text.splitlines():
        if not raw.strip():
            continue

        if header["supplier_name"] is None:
            m = SUPPLIER_RE.match(raw)
            if m:
                header["supplier_name"] = m.group(1).strip()
                continue
        if header["invoice_number"] is None:
            m = INVOICE_NO_RE.match(raw)
            if m:
                header["invoice_number"] = m.group(1).strip()
                continue
        if header["invoice_date"] is None:
            m = DATE_RE.match(raw)
            if m:
                header["invoice_date"] = m.group(1).strip()
                continue

        m = LINE_WITH_CODE.match(raw) or LINE_NO_CODE.match(raw)
        if not m:
            continue

        g = m.groupdict()
        items.append(ParsedLineItem(
            raw_text=raw.strip(),
            ingredient_name=g["desc"].strip(),
            quantity=float(g["qty"].replace(",", "")),
            unit=g["unit"].upper(),
            unit_price=_to_float(g["unit_price"]),
            total_price=_to_float(g["extended"]),
            supplier_code=(g.get("code") or None),
        ))

    return header, items


class InvoiceLoader:
    """Layer 1 pipeline: parse -> match -> route -> persist."""

    def __init__(self, config, conn=None):
        self.config = config
        self.conn = conn or db.connect()

    # ── SKU matching ────────────────────────────────────────────────────
    def _sku_catalogue(self, restaurant_id: str) -> Dict[str, Dict]:
        rows = self.conn.execute(
            "SELECT sku, name, unit, last_unit_price FROM inventory_skus "
            "WHERE restaurant_id = ?", (restaurant_id,)
        ).fetchall()
        return {r["sku"]: dict(r) for r in rows}

    def match_sku(self, ingredient_name: str, catalogue: Dict[str, Dict],
                  supplier_code: Optional[str] = None) -> Tuple[Optional[str], float]:
        """Fuzzy-match a description to a SKU.

        A supplier item code that exactly equals a known SKU is an unambiguous
        identifier and short-circuits at confidence 1.0. Otherwise this falls
        back to token-set similarity on the human-readable name, which
        tolerates word order and the size/pack noise typical of distributor
        descriptions ("CHICKEN BREAST BNLS SKNLS 5LB" vs "Chicken Breast
        Boneless Skinless 5lb").

        `default_process` case-folds and strips punctuation before comparison.
        Without it, invoices printed in upper case — which is most of them —
        score near zero against mixed-case SKU names.
        """
        if supplier_code and supplier_code.upper() in catalogue:
            return supplier_code.upper(), 1.0
        if not catalogue:
            return None, 0.0

        names = {data["name"]: sku for sku, data in catalogue.items()}
        best = process.extractOne(
            ingredient_name, list(names.keys()), scorer=fuzz.token_set_ratio,
            processor=fuzz_utils.default_process,
        )
        if best is None:
            return None, 0.0
        matched_name, score, _ = best
        return names[matched_name], score / 100.0

    # ── Routing (Working Paper §3.2) ──────────────────────────────────────
    def route(self, confidence: float, unit_price: float,
              previous_price: Optional[float]) -> Tuple[str, str, Optional[float]]:
        """Decide the outcome for one line item. Returns (routing, reason, change_pct)."""
        conf_pct = confidence * 100
        conf_gate = self.config.sku_match_confidence_threshold

        if confidence < conf_gate:
            return ("manual_review",
                    f"SKU match confidence {conf_pct:.1f}% is below the "
                    f"{conf_gate * 100:.0f}% threshold (Working Paper §3.2).",
                    None)

        if previous_price is None or previous_price <= 0:
            return ("manager_confirmation",
                    "No previously recorded unit price for this SKU, so the "
                    "change cannot be verified; first-time costs are confirmed "
                    "by a manager before sync.",
                    None)

        change = (unit_price - previous_price) / previous_price
        gate = self.config.price_change_confirmation_threshold
        if abs(change) > gate:
            direction = "increase" if change > 0 else "decrease"
            return ("manager_confirmation",
                    f"Unit price {direction} of {abs(change) * 100:.1f}% "
                    f"(${previous_price:.2f} -> ${unit_price:.2f}) exceeds the "
                    f"{gate * 100:.0f}% variance gate (Working Paper §3.2, §5.2).",
                    change)

        return ("auto_sync",
                f"Match {conf_pct:.1f}% and price change {change * 100:+.1f}% is "
                f"within the {gate * 100:.0f}% gate; safe to sync automatically.",
                change)

    # ── Orchestration ───────────────────────────────────────────────────
    def process(self, invoice_path: str | Path, restaurant_id: str, *,
                extraction_method: str = "text_layer",
                is_demo: bool = False, actor: str = "system") -> InvoiceResult:
        """Parse one invoice file and persist the results.

        `extraction_method` records the provenance of the text. Phase 1 uses
        'text_layer'; a future OCR integration would record the engine and
        model version here instead.
        """
        path = Path(invoice_path)
        text = path.read_text(encoding="utf-8")
        header, parsed_items = parse_invoice_text(text)

        catalogue = self._sku_catalogue(restaurant_id)
        invoice_id = db.new_id()
        matched: List[MatchedLineItem] = []

        for item in parsed_items:
            sku, confidence = self.match_sku(
                item.ingredient_name, catalogue, item.supplier_code
            )
            previous = catalogue.get(sku, {}).get("last_unit_price") if sku else None
            routing, reason, change = self.route(confidence, item.unit_price, previous)
            matched.append(MatchedLineItem(
                parsed=item,
                matched_sku=sku if confidence >= self.config.sku_match_confidence_threshold else None,
                match_confidence=confidence,
                routing=routing,
                routing_reason=reason,
                previous_unit_price=previous,
                price_change_pct=change,
            ))

        result = InvoiceResult(
            invoice_id=invoice_id,
            source_path=portable_source_path(path),
            supplier_name=header["supplier_name"] or "Unknown Supplier",
            invoice_number=header["invoice_number"],
            invoice_date=header["invoice_date"],
            extraction_method=extraction_method,
            is_demo=is_demo,
            line_items=matched,
        )
        self._persist(result, restaurant_id, actor)
        self._sync_auto_approved(result, actor)
        logger.info(
            "Invoice %s parsed: %d items, routing=%s",
            result.invoice_number, len(matched), result.counts(),
        )
        return result

    def _sync_auto_approved(self, result: InvoiceResult, actor: str) -> None:
        """Write costs for lines that cleared both gates.

        Working Paper §3.2 makes this the whole point of Layer 1: a confidently
        matched line whose price moved within tolerance updates inventory
        without human keying. Lines routed to manager_confirmation or
        manual_review are deliberately NOT written here — they wait for an
        explicit approval via `apply_confirmed_price`.
        """
        synced = []
        for li in result.line_items:
            if li.routing == "auto_sync" and li.matched_sku:
                self.conn.execute(
                    "UPDATE inventory_skus SET last_unit_price = ?, updated_at = ? "
                    "WHERE sku = ?",
                    (li.parsed.unit_price, db.now_iso(), li.matched_sku),
                )
                synced.append({"sku": li.matched_sku,
                               "unit_price": li.parsed.unit_price})
        if synced:
            self.conn.commit()
            db.audit(self.conn, actor=actor, action="SKU_PRICES_AUTO_SYNCED",
                     payload={"invoice_id": result.invoice_id, "items": synced})

    def _persist(self, result: InvoiceResult, restaurant_id: str, actor: str) -> None:
        self.conn.execute(
            "INSERT INTO invoices (invoice_id, restaurant_id, supplier_name, "
            "invoice_number, invoice_date, source_path, extraction_method, "
            "total_extracted, is_demo, processed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (result.invoice_id, restaurant_id, result.supplier_name,
             result.invoice_number, result.invoice_date, result.source_path,
             result.extraction_method, round(result.total_extracted, 2),
             int(result.is_demo), db.now_iso()),
        )
        for li in result.line_items:
            self.conn.execute(
                "INSERT INTO invoice_line_items (line_item_id, invoice_id, raw_text, "
                "ingredient_name, quantity, unit, unit_price, total_price, "
                "supplier_code, matched_sku, match_confidence, routing, routing_reason) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), result.invoice_id, li.parsed.raw_text,
                 li.parsed.ingredient_name, li.parsed.quantity, li.parsed.unit,
                 li.parsed.unit_price, li.parsed.total_price, li.parsed.supplier_code,
                 li.matched_sku, li.match_confidence, li.routing, li.routing_reason),
            )
        self.conn.commit()
        db.audit(self.conn, actor=actor, action="INVOICE_PROCESSED",
                 payload={"invoice_id": result.invoice_id,
                          "supplier": result.supplier_name,
                          "routing_counts": result.counts(),
                          "extraction_method": result.extraction_method})

    def apply_confirmed_price(self, sku: str, new_unit_price: float,
                              decided_by: str) -> None:
        """Write a manager-confirmed price to the SKU record.

        Only ever called after a recorded approval — this is the write side of
        the Human-in-the-Loop gate (Working Paper §3.1).
        """
        self.conn.execute(
            "UPDATE inventory_skus SET last_unit_price = ?, updated_at = ? WHERE sku = ?",
            (new_unit_price, db.now_iso(), sku),
        )
        self.conn.commit()
        db.audit(self.conn, actor=decided_by, action="SKU_PRICE_UPDATED",
                 payload={"sku": sku, "new_unit_price": new_unit_price})
