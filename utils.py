#!/usr/bin/env python3
"""
Utility functions for Anthropic API Proxy.
"""

import json
import socket
from typing import Optional, Tuple

from fastapi import HTTPException

from config import config, logger


def get_local_ip() -> str:
    """Get local IP address for displaying in logs."""
    try:
        # Create a socket that connects to a public address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No actual connection is made
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "localhost"


async def verify_access_key(
    x_api_key: Optional[str] = None,
) -> bool:
    """
    Verify the local access key for authentication.
    Accepts x-api-key header (Anthropic SDK style).

    Args:
        x_api_key: x-api-key header value

    Returns:
        True if authentication is successful

    Raises:
        HTTPException: If authentication fails
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key header missing")

    if x_api_key != config["server"]["access_key"]:
        raise HTTPException(status_code=401, detail="Invalid access key")

    return True


async def check_rate_limit(data: str or bytes) -> Tuple[bool, Optional[int]]:
    """
    Check for rate limit error in Anthropic API response.

    Anthropic rate limit error format:
    {"type": "error", "error": {"type": "rate_limit_error", "message": "..."}}

    Args:
        data: response body

    Returns:
        Tuple (has_rate_limit_error, reset_time_ms)
        reset_time_ms is always None for Anthropic (use default cooldown)
    """
    has_rate_limit_error = False
    reset_time_ms = None
    try:
        err = json.loads(data)
    except Exception as e:
        logger.warning('Json.loads error %s', e)
        return False, None

    if isinstance(err, dict) and err.get("type") == "error":
        error_info = err.get("error", {})
        if error_info.get("type") == "rate_limit_error":
            has_rate_limit_error = True
            logger.warning("Anthropic rate limit error: %s", error_info.get("message", ""))

    return has_rate_limit_error, reset_time_ms
