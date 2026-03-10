"""Backend API path and URL-glob contract for attack browser nodes."""

from __future__ import annotations

from typing import Final


# URL globs used for navigation waits.
URL_GLOB_QUEUE_PAGE: Final[str] = "**/queue/**"
URL_GLOB_SEATS_MAP: Final[str] = "**/seats?mode=MAP"
URL_GLOB_SEATS_RECOMMEND: Final[str] = "**/seats?mode=RECOMMEND"
URL_GLOB_PAYMENT: Final[str] = "**/payment?orderId=*"
URL_GLOB_PAYMENT_DONE: Final[str] = "**/payment/done*"

# API path fragments used for response waits.
API_PATH_RECOMMENDATIONS: Final[str] = "/api/recommendations"
API_PATH_HOLDS: Final[str] = "/api/holds"
API_PATH_PAYMENTS: Final[str] = "/api/payments"
API_PATH_ZONES_PREFIX: Final[str] = "/api/zones/"
API_PATH_SEATS_SUFFIX: Final[str] = "/seats"
