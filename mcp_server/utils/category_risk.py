"""
Structural port of Albugent's pii_detector.py, revised per the Alexa+ MCP Toolkit
Functional Requirements (section 13, MCP Tool Validation): "Include common synonyms,
abbreviations, and alternate spellings in your tool parameter descriptions and enums
so variants resolve correctly."

`category` used to be a free-text string matched by substring ("gift_card" in
category.lower()) -- which silently missed anything the model phrased differently
from our internal keyword ("gift card", "giftcard", "Gift Card"), quietly downgrading
a High-severity purchase to Low. Fixed by making `category` a closed enum
(CATEGORY_VALUES) declared directly in the tool's JSON Schema (see server.py's
Literal[...] type) instead of guessed free text, and switching severity lookup to an
exact match against that closed set -- there is no longer a "spelling" for the model
to get wrong.
"""
from typing import List

# The full set of category values the tool schema accepts (mirrored as a Literal type
# in server.py). "other" is the deliberate catch-all for anything not in this list.
CATEGORY_VALUES = [
    "electronics", "groceries", "dining", "entertainment", "travel",
    "subscription", "luxury", "healthcare", "prescription",
    "financial", "loan", "wire_transfer", "gift_card", "gambling", "crypto",
    "other",
]

# High: hard-to-reverse / regulatory exposure
# Medium: sensitive but recoverable
# Low: everyday recurring spend
CATEGORY_SEVERITY = {
    "wire_transfer": "High",
    "gift_card": "High",
    "gambling": "High",
    "crypto": "High",
    "loan": "High",
    "financial": "Medium",
    "healthcare": "Medium",
    "prescription": "Medium",
    "luxury": "Medium",
    "subscription": "Low",
    "electronics": "Low",
    "groceries": "Low",
    "dining": "Low",
    "entertainment": "Low",
    "travel": "Low",
    "other": "Low",
}

CATEGORY_KEYWORDS = list(CATEGORY_SEVERITY.keys())


def detect_risky_category(category: str) -> List[str]:
    """Exact-match against the closed category set (no longer substring matching --
    `category` is now a schema-level enum, so there is nothing to fuzzy-match)."""
    if category in ("wire_transfer", "gift_card", "gambling", "crypto", "loan"):
        return [category]
    return []


def classify_category_severity(category: str) -> str:
    """Exact dict lookup against the closed category set."""
    return CATEGORY_SEVERITY.get(category, "Low")
