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
    authorization: Optional[str] = None,
) -> bool:
    """
    Verify the local access key for authentication.
    Accepts authorization header value (Bearer <key> format).

    Args:
        authorization: authorization header value (with or without Bearer prefix)

    Returns:
        True if authentication is successful

    Raises:
        HTTPException: If authentication fails
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="authorization header missing")

    api_key = authorization.removeprefix("Bearer ").strip()
    if api_key != config["server"]["access_key"]:
        raise HTTPException(status_code=401, detail="Invalid access key")

    return True


async def check_rate_limit(data: str or bytes) -> Tuple[bool, Optional[int]]:
    """
    Check for rate limit error in Anthropic OR OpenAI API response.

    Anthropic format: {"type": "error", "error": {"type": "rate_limit_error"}}
    OpenAI format:    {"error": {"code": "rate_limit_exceeded", "message": "..."}}
    """
    has_rate_limit_error = False
    reset_time_ms = None
    try:
        err = json.loads(data)
    except Exception as e:
        logger.warning('Json.loads error %s', e)
        return False, None

    if not isinstance(err, dict):
        return False, None

    # Anthropic format
    if err.get("type") == "error":
        error_info = err.get("error", {})
        if error_info.get("type") == "rate_limit_error":
            has_rate_limit_error = True
            logger.warning("Anthropic rate limit error: %s", error_info.get("message", ""))

    # OpenAI format
    elif "error" in err:
        error_info = err.get("error", {})
        code = str(error_info.get("code", ""))
        msg = str(error_info.get("message", ""))
        if "rate_limit" in code.lower() or "rate limit" in msg.lower():
            has_rate_limit_error = True
            logger.warning("OpenAI rate limit error: %s", msg)

    return has_rate_limit_error, reset_time_ms
