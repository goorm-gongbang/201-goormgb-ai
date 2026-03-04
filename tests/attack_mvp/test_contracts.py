from __future__ import annotations

from traffic_master_ai.attack.a1_mvp.contracts.api import (
    API_PATH_HOLDS,
    API_PATH_RECOMMENDATIONS,
    API_PATH_SEATS_SUFFIX,
    API_PATH_ZONES_PREFIX,
    URL_GLOB_PAYMENT,
    URL_GLOB_PAYMENT_DONE,
    URL_GLOB_QUEUE_PAGE,
    URL_GLOB_SEATS_MAP,
    URL_GLOB_SEATS_RECOMMEND,
)
from traffic_master_ai.attack.a1_mvp.contracts.defense import (
    HTTP_BLOCKED,
    HTTP_CHALLENGE_REQUIRED,
    REASON_BLOCKED,
    REASON_CHALLENGE_REQUIRED,
    is_blocked_response,
    is_challenge_required_response,
)
from traffic_master_ai.attack.a1_mvp.contracts.selectors import (
    SELECTOR_CONTRACT,
    SEL_AGREE_CANCEL,
    SEL_AGREE_TERMS,
    SEL_BOOKING_BTN,
    SEL_HOLD_FAIL_CLOSE,
    SEL_MAP_BOOK_BTN,
    SEL_PARTY_SIZE_SELECT_MAP,
    SEL_PARTY_SIZE_SELECT_RECOMMEND,
    SEL_PAY_BTN,
    SEL_REC_AUTO,
    SEL_SEAT_AVAILABLE,
    SEL_SEAT_GRID,
    SEL_SEAT_MODE_TOGGLE,
    SEL_SECURITY_ERROR,
    SEL_SECURITY_INPUT,
    SEL_SECURITY_OVERLAY,
    SEL_SECURITY_SUBMIT,
    SEL_ZONE_ITEM,
)
from traffic_master_ai.attack.a1_mvp.contracts.storage import (
    TM_PREFERENCES_KEY,
    TM_SESSION_ID_KEY,
    build_default_tm_preferences,
)


def test_selector_contract_has_expected_values() -> None:
    assert SELECTOR_CONTRACT["preEntry"]["bookingButton"] == "#booking-button:not([disabled])"
    assert SELECTOR_CONTRACT["security"]["overlay"] == '[data-testid="security-overlay"]'
    assert SELECTOR_CONTRACT["security"]["input"] == '[data-testid="security-input"]'
    assert SELECTOR_CONTRACT["security"]["submit"] == '[data-testid="security-submit"]'
    assert SELECTOR_CONTRACT["security"]["error"] == '[data-testid="security-error"]'
    assert (
        SELECTOR_CONTRACT["map"]["zoneItem"]
        == 'button[data-testid^="zone-"][data-remaining]:not([disabled])'
    )
    assert SELECTOR_CONTRACT["map"]["seatGrid"] == '[data-testid="seat-grid"]'
    assert SELECTOR_CONTRACT["map"]["seatAvailable"] == 'button[data-seat-status="AVAILABLE"]'
    assert SELECTOR_CONTRACT["map"]["bookingButtonMap"] == "#booking-button-map:not([disabled])"
    assert SELECTOR_CONTRACT["map"]["holdFailClose"] == '[data-testid="hold-fail-close"]'
    assert SELECTOR_CONTRACT["map"]["partySizeSelect"] == '[data-testid="party-size-select"]'
    assert (
        SELECTOR_CONTRACT["recommend"]["recAuto"]
        == '[data-testid="rec-auto-select"]:not([disabled])'
    )
    assert SELECTOR_CONTRACT["recommend"]["seatModeToggle"] == '[data-testid="seat-mode-toggle"]'
    assert SELECTOR_CONTRACT["recommend"]["partySizeSelect"] == '[data-testid="party-size-select"]'
    assert SELECTOR_CONTRACT["payment"]["agreeTerms"] == '[data-testid="agree-terms"]'
    assert SELECTOR_CONTRACT["payment"]["agreeCancelFee"] == '[data-testid="agree-cancel-fee"]'
    assert SELECTOR_CONTRACT["payment"]["payButton"] == "#pay-button:not([disabled])"


def test_flattened_selector_aliases_match_contract() -> None:
    assert SEL_BOOKING_BTN == SELECTOR_CONTRACT["preEntry"]["bookingButton"]
    assert SEL_SECURITY_OVERLAY == SELECTOR_CONTRACT["security"]["overlay"]
    assert SEL_SECURITY_INPUT == SELECTOR_CONTRACT["security"]["input"]
    assert SEL_SECURITY_SUBMIT == SELECTOR_CONTRACT["security"]["submit"]
    assert SEL_SECURITY_ERROR == SELECTOR_CONTRACT["security"]["error"]
    assert SEL_ZONE_ITEM == SELECTOR_CONTRACT["map"]["zoneItem"]
    assert SEL_SEAT_GRID == SELECTOR_CONTRACT["map"]["seatGrid"]
    assert SEL_SEAT_AVAILABLE == SELECTOR_CONTRACT["map"]["seatAvailable"]
    assert SEL_MAP_BOOK_BTN == SELECTOR_CONTRACT["map"]["bookingButtonMap"]
    assert SEL_HOLD_FAIL_CLOSE == SELECTOR_CONTRACT["map"]["holdFailClose"]
    assert SEL_PARTY_SIZE_SELECT_MAP == SELECTOR_CONTRACT["map"]["partySizeSelect"]
    assert SEL_REC_AUTO == SELECTOR_CONTRACT["recommend"]["recAuto"]
    assert SEL_SEAT_MODE_TOGGLE == SELECTOR_CONTRACT["recommend"]["seatModeToggle"]
    assert SEL_PARTY_SIZE_SELECT_RECOMMEND == SELECTOR_CONTRACT["recommend"]["partySizeSelect"]
    assert SEL_AGREE_TERMS == SELECTOR_CONTRACT["payment"]["agreeTerms"]
    assert SEL_AGREE_CANCEL == SELECTOR_CONTRACT["payment"]["agreeCancelFee"]
    assert SEL_PAY_BTN == SELECTOR_CONTRACT["payment"]["payButton"]


def test_storage_contract_defaults() -> None:
    assert TM_SESSION_ID_KEY == "TM_SESSION_ID"
    assert TM_PREFERENCES_KEY == "TM_PREFERENCES"

    map_prefs = build_default_tm_preferences("MAP")
    assert map_prefs["recommendEnabled"] is False
    assert map_prefs["partySize"] == 2
    assert map_prefs["priceFilterEnabled"] is False
    assert map_prefs["priceRange"] == {"min": 20000, "max": 100000}

    recommend_prefs = build_default_tm_preferences("RECOMMEND")
    assert recommend_prefs["recommendEnabled"] is True


def test_defense_contract_helpers() -> None:
    assert HTTP_BLOCKED == 403
    assert HTTP_CHALLENGE_REQUIRED == 428
    assert REASON_BLOCKED == "BLOCKED"
    assert REASON_CHALLENGE_REQUIRED == "CHALLENGE_REQUIRED"

    assert is_blocked_response(403, None) is True
    assert is_blocked_response(200, "BLOCKED") is True
    assert is_blocked_response(428, None) is False

    assert is_challenge_required_response(428, None) is True
    assert is_challenge_required_response(200, "CHALLENGE_REQUIRED") is True
    assert is_challenge_required_response(403, None) is False


def test_api_contract_constants() -> None:
    assert URL_GLOB_QUEUE_PAGE == "**/queue/**"
    assert URL_GLOB_SEATS_MAP == "**/seats?mode=MAP"
    assert URL_GLOB_SEATS_RECOMMEND == "**/seats?mode=RECOMMEND"
    assert URL_GLOB_PAYMENT == "**/payment?orderId=*"
    assert URL_GLOB_PAYMENT_DONE == "**/payment/done*"
    assert API_PATH_RECOMMENDATIONS == "/api/recommendations"
    assert API_PATH_HOLDS == "/api/holds"
    assert API_PATH_ZONES_PREFIX == "/api/zones/"
    assert API_PATH_SEATS_SUFFIX == "/seats"

