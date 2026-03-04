"""UI selector contract for Attack MVP.

This module keeps selector strings in one place so FE/Attack contract changes
are easy to review and update.
"""

from __future__ import annotations

from typing import Final, TypedDict


class PreEntrySelectors(TypedDict):
    bookingButton: str


class SecuritySelectors(TypedDict):
    overlay: str
    input: str
    submit: str
    error: str


class MapSelectors(TypedDict):
    zoneItem: str
    seatGrid: str
    seatAvailable: str
    bookingButtonMap: str
    holdFailClose: str
    partySizeSelect: str


class RecommendSelectors(TypedDict):
    recAuto: str
    seatModeToggle: str
    partySizeSelect: str


class PaymentSelectors(TypedDict):
    agreeTerms: str
    agreeCancelFee: str
    payButton: str


class SelectorContract(TypedDict):
    preEntry: PreEntrySelectors
    security: SecuritySelectors
    map: MapSelectors
    recommend: RecommendSelectors
    payment: PaymentSelectors


SELECTOR_CONTRACT: Final[SelectorContract] = {
    "preEntry": {
        "bookingButton": "#booking-button:not([disabled])",
    },
    "security": {
        "overlay": '[data-testid="security-overlay"]',
        "input": '[data-testid="security-input"]',
        "submit": '[data-testid="security-submit"]',
        "error": '[data-testid="security-error"]',
    },
    "map": {
        "zoneItem": 'button[data-testid^="zone-"][data-remaining]:not([disabled])',
        "seatGrid": '[data-testid="seat-grid"]',
        "seatAvailable": 'button[data-seat-status="AVAILABLE"]',
        "bookingButtonMap": "#booking-button-map:not([disabled])",
        "holdFailClose": '[data-testid="hold-fail-close"]',
        "partySizeSelect": '[data-testid="party-size-select"]',
    },
    "recommend": {
        "recAuto": '[data-testid="rec-auto-select"]:not([disabled])',
        "seatModeToggle": '[data-testid="seat-mode-toggle"]',
        "partySizeSelect": '[data-testid="party-size-select"]',
    },
    "payment": {
        "agreeTerms": '[data-testid="agree-terms"]',
        "agreeCancelFee": '[data-testid="agree-cancel-fee"]',
        "payButton": "#pay-button:not([disabled])",
    },
}

# Flattened aliases for concise use in node code.
SEL_BOOKING_BTN: Final[str] = SELECTOR_CONTRACT["preEntry"]["bookingButton"]

SEL_SECURITY_OVERLAY: Final[str] = SELECTOR_CONTRACT["security"]["overlay"]
SEL_SECURITY_INPUT: Final[str] = SELECTOR_CONTRACT["security"]["input"]
SEL_SECURITY_SUBMIT: Final[str] = SELECTOR_CONTRACT["security"]["submit"]
SEL_SECURITY_ERROR: Final[str] = SELECTOR_CONTRACT["security"]["error"]

SEL_ZONE_ITEM: Final[str] = SELECTOR_CONTRACT["map"]["zoneItem"]
SEL_SEAT_GRID: Final[str] = SELECTOR_CONTRACT["map"]["seatGrid"]
SEL_SEAT_AVAILABLE: Final[str] = SELECTOR_CONTRACT["map"]["seatAvailable"]
SEL_MAP_BOOK_BTN: Final[str] = SELECTOR_CONTRACT["map"]["bookingButtonMap"]
SEL_HOLD_FAIL_CLOSE: Final[str] = SELECTOR_CONTRACT["map"]["holdFailClose"]
SEL_PARTY_SIZE_SELECT_MAP: Final[str] = SELECTOR_CONTRACT["map"]["partySizeSelect"]

SEL_REC_AUTO: Final[str] = SELECTOR_CONTRACT["recommend"]["recAuto"]
SEL_SEAT_MODE_TOGGLE: Final[str] = SELECTOR_CONTRACT["recommend"]["seatModeToggle"]
SEL_PARTY_SIZE_SELECT_RECOMMEND: Final[str] = SELECTOR_CONTRACT["recommend"]["partySizeSelect"]

SEL_AGREE_TERMS: Final[str] = SELECTOR_CONTRACT["payment"]["agreeTerms"]
SEL_AGREE_CANCEL: Final[str] = SELECTOR_CONTRACT["payment"]["agreeCancelFee"]
SEL_PAY_BTN: Final[str] = SELECTOR_CONTRACT["payment"]["payButton"]

