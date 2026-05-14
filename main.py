#!/usr/bin/env python3
"""
Anthropic-Compatible API Proxy
Proxies requests to Kilo.ai Anthropic-compatible API and rotates API keys to bypass rate limits.
"""

import shlex

import uvicorn
from fastapi import FastAPI, Request

from config import config, logger
from routes import router, lifespan
from utils import get_local_ip

# Create FastAPI app
app = FastAPI(
    title="Anthropic API Proxy",
    description="Proxies requests to Kilo.ai Anthropic-compatible API and rotates API keys to bypass rate limits",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def log_request_as_curl(request: Request, call_next):
    """Log every incoming request as a curl command when request_detail_log is enabled."""
    if config["server"].get("request_detail_log", False):
        body = await request.body()  # Starlette caches body; safe to read again in route handlers

        curl_parts = [f"curl -X {request.method} {shlex.quote(str(request.url))}"]

        for key, value in request.headers.items():
            curl_parts.append(f"  -H {shlex.quote(f'{key}: {value}')}")

        if body:
            try:
                body_str = body.decode("utf-8")
            except Exception:
                body_str = f"<binary {len(body)} bytes>"
            curl_parts.append(f"  -d {shlex.quote(body_str)}")

        logger.info("Incoming request:\n%s", " \\\n".join(curl_parts))

    return await call_next(request)


# Include routes
app.include_router(router)

# Entry point
if __name__ == "__main__":
    host = config["server"]["host"]
    port = config["server"]["port"]

    # If host is 0.0.0.0, use actual local IP for display
    display_host = get_local_ip() if host == "0.0.0.0" else host

    logger.warning("Starting Anthropic Proxy on %s:%s", host, port)
    logger.warning("API URL: http://%s:%s/v1", display_host, port)
    logger.info("Health check: http://%s:%s/health", display_host, port)

    # Configure log level for HTTP access logs
    log_config = uvicorn.config.LOGGING_CONFIG
    http_log_level = config["server"].get("http_log_level", "INFO").upper()
    log_config["loggers"]["uvicorn.access"]["level"] = http_log_level
    logger.info("HTTP access log level set to %s", http_log_level)

    uvicorn.run(app, host=host, port=port, log_config=log_config, timeout_graceful_shutdown=30)
