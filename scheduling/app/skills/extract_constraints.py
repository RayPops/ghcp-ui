"""Skill A: Extract scheduling constraints from unstructured notes."""

from __future__ import annotations

import re
import logging
from datetime import date
from typing import Optional

from app.models import SchedulingConstraints

logger = logging.getLogger(__name__)

# Date patterns: "before 15th March", "after 10th April", "until 10 April"
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

_DATE_PATTERN = re.compile(
    r"(?:before|after|until|from)\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)

_NOT_BEFORE_PATTERN = re.compile(
    r"(?:do\s+not\s+attend\s+before|not\s+before|don'?t\s+(?:come|attend)\s+before"
    r"|only\s+available\s+(?:after|from))\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)

_HOLIDAY_UNTIL_PATTERN = re.compile(
    r"(?:holiday|away|abroad|unavailable)\s+(?:until|till|to)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)

_AVAILABILITY_PATTERNS = [
    (re.compile(r"(?:only\s+)?(?:available\s+)?mornings?\s+(?:before|until)\s+(\d{1,2})", re.IGNORECASE), "mornings only"),
    (re.compile(r"(?:only\s+)?(?:available\s+)?afternoons?\s+(?:after|from)\s+(\d{1,2})", re.IGNORECASE), "afternoons only"),
    (re.compile(r"(?:prefers?|only)\s+afternoon", re.IGNORECASE), "afternoons only"),
    (re.compile(r"(?:prefers?|only)\s+morning", re.IGNORECASE), "mornings only"),
    (re.compile(r"after\s+(\d{1,2})\s*(?:pm|PM)", re.IGNORECASE), "afternoons only"),
    (re.compile(r"before\s+(\d{1,2})\s*(?:pm|PM|noon)", re.IGNORECASE), "mornings only"),
    (re.compile(r"available\s+(?:any\s+day|anytime|any\s+time)", re.IGNORECASE), "any time"),
    (re.compile(r"weekdays?\s+only", re.IGNORECASE), "weekdays only"),
    (re.compile(r"available\s+weekdays?\s+(?:only\s+)?(\d{1,2})\s*[-to]+\s*(\d{1,2})", re.IGNORECASE), "weekdays only"),
    (re.compile(r"night\s+shift\s+only\s+available\s+between\s+(\d{1,2})(?:pm|PM)?\s+and\s+(\d{1,2})(?:am|AM)?", re.IGNORECASE), "night shift only"),
    (re.compile(r"Mon(?:day)?\s+to\s+Fri(?:day)?\s+(\d{1,2})(?:am|AM)?\s+to\s+(\d{1,2})(?:pm|PM)?", re.IGNORECASE), "weekdays business hours only"),
    (re.compile(r"only\s+accessible\s+Mon(?:day)?\s+to\s+Fri(?:day)?", re.IGNORECASE), "weekdays only"),
]

_INSTRUCTION_PATTERNS = [
    re.compile(r"(use\s+(?:rear|side|back|front)\s+(?:access|gate|door|entrance)[^.]*)", re.IGNORECASE),
    re.compile(r"(gate\s+code\s+\d+)", re.IGNORECASE),
    re.compile(r"((?:contact|call|ring|phone)\s+(?:site\s+manager|customer|daughter|building\s+manager)[^.]*)", re.IGNORECASE),
    re.compile(r"(knock\s+loudly[^.]*)", re.IGNORECASE),
    re.compile(r"((?:dog|dogs)\s+(?:must\s+be|should\s+be|need\s+to\s+be)\s+secured[^.]*)", re.IGNORECASE),
    re.compile(r"((?:call|contact|ring)\s+(?:her|him|them)\s+(?:when|before)[^.]*)", re.IGNORECASE),
    re.compile(r"((?:security\s+clearance|photo\s+ID|confirmation\s+email)[^.]*)", re.IGNORECASE),
    re.compile(r"((?:building\s+manager|site\s+manager)\s+must\s+grant[^.]*)", re.IGNORECASE),
    re.compile(r"((?:do\s+not\s+book|DO\s+NOT\s+book)[^.]*)", re.IGNORECASE),
    re.compile(r"((?:customer\s+(?:says|aware|will)\s+)[^.]*)", re.IGNORECASE),
    re.compile(r"(48\s*hrs?\s+in\s+advance[^.]*)", re.IGNORECASE),
]


def _extract_date(day_str: str, month_str: str, reference_year: int) -> date:
    """Build a date from extracted day and month strings."""
    month = _MONTH_MAP[month_str.lower()]
    day = int(day_str)
    return date(reference_year, month, day)


def extract_scheduling_constraints(
    customer_notes: str,
    requested_start_date: date,
    requested_end_date: date,
    committed_delivery_date: date,
) -> SchedulingConstraints:
    """Extract scheduling constraints from unstructured customer notes.

    Args:
        customer_notes: Free text notes from customer or agent.
        requested_start_date: Start of customer requested window.
        requested_end_date: End of customer requested window.
        committed_delivery_date: Contractual delivery date.

    Returns:
        SchedulingConstraints with extracted fields.
    """
    result = SchedulingConstraints()
    if not customer_notes:
        return result

    reference_year = committed_delivery_date.year
    notes_lower = customer_notes.lower()

    # Extract earliest allowed date from "do not attend before" or "holiday until"
    for pattern in [_NOT_BEFORE_PATTERN, _HOLIDAY_UNTIL_PATTERN]:
        match = pattern.search(customer_notes)
        if match:
            try:
                extracted = _extract_date(match.group(1), match.group(2), reference_year)
                if result.earliest_allowed_date is None or extracted > result.earliest_allowed_date:
                    result.earliest_allowed_date = extracted
                    logger.info("Extracted earliest allowed date: %s", extracted)
            except ValueError:
                logger.warning("Could not parse date from notes: %s", match.group(0))

    # Extract customer availability window
    for pattern, window_label in _AVAILABILITY_PATTERNS:
        if pattern.search(customer_notes):
            result.customer_availability_window = window_label
            logger.info("Extracted availability window: %s", window_label)
            break

    # Extract special instructions
    for pattern in _INSTRUCTION_PATTERNS:
        for match in pattern.finditer(customer_notes):
            instruction = match.group(1).strip().rstrip(".")
            if instruction and instruction not in result.special_instructions:
                result.special_instructions.append(instruction)

    # Check for "do not book" type constraints
    if re.search(r"do\s+not\s+book", notes_lower):
        if result.earliest_allowed_date is None:
            # Set a far future date to force human review
            result.earliest_allowed_date = date(reference_year, 12, 31)

    logger.info(
        "Extracted constraints for notes (%d chars): earliest=%s, window=%s, instructions=%d",
        len(customer_notes),
        result.earliest_allowed_date,
        result.customer_availability_window,
        len(result.special_instructions),
    )

    return result
