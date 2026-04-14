"""
A.C.E. Layer 1: Automated Invoice Ingestion — AI-OCR Pipeline

The most operationally impactful A.C.E. capability: eliminates manual invoice
data entry by automatically parsing PDF supplier invoices, extracting line-item
data, and syncing cost updates to the restaurant's inventory records.

Design principle: Human-in-the-Loop validation gate.
Any price change exceeding the configured threshold (default 5%) triggers a
mandatory manager confirmation step before the data is accepted into the system.
This satisfies the legal standard of "reasonable skill and care" and limits
autonomous authority to low-stakes routine updates.

Background: The manual invoice data entry problem was observed firsthand during
14 years of financial analysis work at YLG Bullion Group and ASUSTeK Computer,
where the same fragmented data integration challenge — structured system data
vs. unstructured supplier documents — was managed manually at scale. A.C.E.
encodes the resolution logic that experienced financial analysts apply intuitively.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class InvoiceLineItem:
    """A single extracted line item from a supplier invoice."""
    raw_text: str
    ingredient_name: str
    quantity: float
    unit: str
    unit_price: float
    total_price: float
    supplier_code: Optional[str] = None
    matched_sku: Optional[str] = None
    match_confidence: float = 0.0
    requires_review: bool = False


@dataclass
class InvoiceResult:
    """Complete result of processing a single supplier invoice."""
    invoice_path: str
    supplier_name: str
    invoice_date: Optional[str]
    items_extracted: int
    items_mapped: int
    items_requiring_review: int
    total_invoice_cost: float
    cost_changes_flagged: List[Dict] = field(default_factory=list)
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    processed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    requires_manager_review: bool = False

    def to_dict(self) -> Dict:
        return {
            "invoice_path": self.invoice_path,
            "supplier_name": self.supplier_name,
            "invoice_date": self.invoice_date,
            "items_extracted": self.items_extracted,
            "items_mapped": self.items_mapped,
            "items_requiring_review": self.items_requiring_review,
            "total_invoice_cost": round(self.total_invoice_cost, 2),
            "cost_changes_flagged": self.cost_changes_flagged,
            "requires_manager_review": self.requires_manager_review,
            "processed_at": self.processed_at,
        }


class InvoiceLoader:
    """
    A.C.E. Layer 1 — Invoice ingestion and OCR extraction.

    Phase 1 (proof-of-concept): Simulates OCR extraction using structured
    sample data. Phase 2 will integrate a fine-tuned transformer OCR model
    trained on restaurant invoice formats.

    Usage:
        loader = InvoiceLoader(config)
        loader.initialize()
        result = loader.process("path/to/invoice.pdf")
        print(result.to_dict())
    """

    # Common restaurant supplier invoice patterns
    # These regex patterns encode the structural knowledge of how
    # U.S. food distributor invoices (Sysco, US Foods, etc.) are formatted
    PRICE_PATTERN = re.compile(r'\$?\s*(\d{1,6}(?:\.\d{2})?)')
    QTY_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(cs|ea|lb|kg|oz|gal|qt|pk|bag|box|case)', re.IGNORECASE)

    def __init__(self, config):
        self.config = config
        self._inventory_db: Dict[str, Dict] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Load inventory database for SKU matching."""
        self._load_sample_inventory()
        self._initialized = True
        logger.info(f"InvoiceLoader initialized with {len(self._inventory_db)} inventory SKUs")

    def process(self, invoice_path: str) -> InvoiceResult:
        """
        Process a supplier invoice and return extracted line items.

        In Phase 1, this demonstrates the pipeline logic using sample data.
        In Phase 2, this connects to a live OCR model and POS inventory API.
        """
        if not self._initialized:
            self.initialize()

        logger.info(f"Processing invoice: {invoice_path}")

        # Phase 1: simulate OCR extraction with sample invoice data
        extracted_items = self._simulate_ocr_extraction(invoice_path)
        mapped_items, cost_changes = self._map_to_inventory(extracted_items)

        requires_review = any(
            item.requires_review for item in mapped_items
        ) or len(cost_changes) > 0

        result = InvoiceResult(
            invoice_path=invoice_path,
            supplier_name=self._detect_supplier(invoice_path),
            invoice_date=datetime.now().strftime("%Y-%m-%d"),
            items_extracted=len(extracted_items),
            items_mapped=sum(1 for i in mapped_items if i.matched_sku),
            items_requiring_review=sum(1 for i in mapped_items if i.requires_review),
            total_invoice_cost=sum(i.total_price for i in mapped_items),
            cost_changes_flagged=cost_changes,
            line_items=mapped_items,
            requires_manager_review=requires_review,
        )

        logger.info(
            f"Invoice processed: {result.items_extracted} items extracted, "
            f"{result.items_mapped} mapped, "
            f"{len(cost_changes)} cost changes flagged"
        )
        return result

    def _simulate_ocr_extraction(self, invoice_path: str) -> List[InvoiceLineItem]:
        """
        Phase 1 simulation of OCR extraction.
        Returns representative sample data demonstrating the pipeline.
        """
        # Sample invoice data representative of U.S. food distributor format
        # (Sysco / US Foods style line items)
        sample_items = [
            InvoiceLineItem(
                raw_text="CHICKEN BREAST BNLS SKNLS 5LB   CS  4   $22.50  $90.00",
                ingredient_name="Chicken Breast Boneless Skinless 5lb",
                quantity=4.0, unit="CS",
                unit_price=22.50, total_price=90.00,
                supplier_code="CHK-BREAST-5LB"
            ),
            InvoiceLineItem(
                raw_text="ROMA TOMATOES 25LB CASE   CS  2   $18.99  $37.98",
                ingredient_name="Roma Tomatoes 25lb",
                quantity=2.0, unit="CS",
                unit_price=18.99, total_price=37.98,
                supplier_code="VEG-TOMATO-ROMA"
            ),
            InvoiceLineItem(
                raw_text="OLIVE OIL EVOO 1GAL   EA  6   $24.99  $149.94",
                ingredient_name="Extra Virgin Olive Oil 1 Gallon",
                quantity=6.0, unit="EA",
                unit_price=24.99, total_price=149.94,
                supplier_code="OIL-EVOO-1GAL"
            ),
            InvoiceLineItem(
                raw_text="ALL PURPOSE FLOUR 50LB BAG   EA  3   $19.50  $58.50",
                ingredient_name="All Purpose Flour 50lb",
                quantity=3.0, unit="EA",
                unit_price=19.50, total_price=58.50,
                supplier_code="DRY-FLOUR-AP-50"
            ),
        ]
        return sample_items

    def _map_to_inventory(
        self, items: List[InvoiceLineItem]
    ) -> Tuple[List[InvoiceLineItem], List[Dict]]:
        """
        Match extracted invoice items to inventory SKUs and flag cost changes.
        """
        cost_changes = []

        for item in items:
            # Fuzzy match to inventory
            best_match, confidence = self._fuzzy_match_sku(item.ingredient_name)

            if confidence >= self.config.ocr_confidence_threshold:
                item.matched_sku = best_match
                item.match_confidence = confidence

                # Check for price change vs. last recorded cost
                if best_match in self._inventory_db:
                    last_price = self._inventory_db[best_match].get("last_unit_price", 0)
                    if last_price > 0:
                        change_pct = abs(item.unit_price - last_price) / last_price
                        if change_pct > self.config.price_change_confirmation_threshold:
                            item.requires_review = True
                            cost_changes.append({
                                "sku": best_match,
                                "ingredient": item.ingredient_name,
                                "old_price": round(last_price, 2),
                                "new_price": round(item.unit_price, 2),
                                "change_pct": round(change_pct * 100, 1),
                                "direction": "increase" if item.unit_price > last_price else "decrease",
                                "action_required": "Manager confirmation required before syncing",
                            })
            else:
                # Low confidence match → manual review queue
                item.requires_review = True
                logger.debug(f"Low confidence match for '{item.ingredient_name}': {confidence:.2f}")

        return items, cost_changes

    def _fuzzy_match_sku(self, ingredient_name: str) -> Tuple[Optional[str], float]:
        """
        Match ingredient name to inventory SKU using fuzzy string matching.
        Phase 2 will use a trained embedding model for semantic matching.
        """
        from difflib import SequenceMatcher

        name_lower = ingredient_name.lower()
        best_sku = None
        best_score = 0.0

        for sku, data in self._inventory_db.items():
            sku_name = data.get("name", "").lower()
            score = SequenceMatcher(None, name_lower, sku_name).ratio()
            if score > best_score:
                best_score = score
                best_sku = sku

        return best_sku, best_score

    def _detect_supplier(self, invoice_path: str) -> str:
        """Extract supplier name from invoice path or content."""
        path_lower = invoice_path.lower()
        if "sysco" in path_lower:
            return "Sysco Corporation"
        elif "usfoods" in path_lower or "us_foods" in path_lower:
            return "US Foods"
        elif "gordon" in path_lower:
            return "Gordon Food Service"
        return "Unknown Supplier"

    def _load_sample_inventory(self) -> None:
        """
        Load sample inventory database for Phase 1 demonstration.
        In Phase 2, this connects to the live POS inventory API.
        """
        self._inventory_db = {
            "CHK-BREAST-5LB": {
                "name": "Chicken Breast Boneless Skinless 5lb",
                "unit": "CS",
                "last_unit_price": 18.99,  # Previous price — change will be flagged
                "category": "protein",
            },
            "VEG-TOMATO-ROMA": {
                "name": "Roma Tomatoes 25lb Case",
                "unit": "CS",
                "last_unit_price": 18.50,
                "category": "produce",
            },
            "OIL-EVOO-1GAL": {
                "name": "Extra Virgin Olive Oil 1 Gallon",
                "unit": "EA",
                "last_unit_price": 24.99,
                "category": "dry_goods",
            },
            "DRY-FLOUR-AP-50": {
                "name": "All Purpose Flour 50lb Bag",
                "unit": "EA",
                "last_unit_price": 17.25,
                "category": "dry_goods",
            },
        }
