"""Utility functions for Haier API client."""

import logging
import random
import string
import time
import uuid
from typing import Any

_LOGGER = logging.getLogger(__name__)


def generate_instant_id() -> str:
    """Generate a 12-character instance ID with letters and digits."""
    return "HA" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))


def generate_ag_client_id(area: str) -> str:
    """Generate the client instance identifier.

    Format: {instant_id}.{area}.{ha_uuid}

    Args:
        area: User selected region (e.g., "cn", "sea")

    Returns:
        The formatted client instance identifier
    """
    ha_uuid = str(uuid.uuid4()).replace("-", "")[:16]
    return f"{generate_instant_id()}.{area}.{ha_uuid}"


def mask_token(token: str | None, prefix: int = 4) -> str:
    """Return a masked preview of a token for logging.

    Only the first ``prefix`` characters are shown, so a token can be told
    apart (e.g. whether it changed after a refresh) without exposing it.
    """
    if not token:
        return "<none>"
    return f"{token[:prefix]}***"


def validate_construct_token(token_data: dict[str, Any]) -> dict[str, Any]:
    """把接口返回的 token 字段整理成 HA 惯用的形态。"""
    if not token_data:
        raise ValueError("Token data is empty")
    if not (
        "accessToken" in token_data and "refreshToken" in token_data and "expiresIn" in token_data
    ):
        raise ValueError("Token data is invalid, missing required fields")
    expires_in = int(token_data["expiresIn"])
    expires_at = time.time() + expires_in
    token = {
        "access_token": token_data["accessToken"],
        "refresh_token": token_data["refreshToken"],
        "expires_in": expires_in,
        "expires_at": expires_at,
    }
    # Masked preview: the prefix identifies the token across produce/refresh.
    _LOGGER.debug(
        "OAuth token prepared: %s (expires_in=%ss)",
        mask_token(token["access_token"]),
        expires_in,
    )
    return token
