#!/usr/bin/env python3
"""
API routes for Anthropic-compatible API Proxy.
"""

import json
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Header, HTTPException, FastAPI
from fastapi.responses import StreamingResponse, Response

from config import config, logger
from key_manager import KeyManager, mask_key
from utils import verify_access_key, check_rate_limit

# Create router
router = APIRouter()

# Initialize key manager
key_manager = KeyManager(
    keys=config["anthropic"]["keys"],
    cooldown_seconds=config["anthropic"]["rate_limit_cooldown"],
    strategy=config["anthropic"]["key_selection_strategy"],
    opts=config["anthropic"]["key_selection_opts"],
)


@asynccontextmanager
async def lifespan(app_: FastAPI):
    client_kwargs = {"timeout": 600.0}  # Increase default timeout
    # Add proxy configuration if enabled
    if config["requestProxy"]["enabled"]:
        proxy_url = config["requestProxy"]["url"]
        client_kwargs["proxy"] = proxy_url
        logger.info("Using proxy for httpx client: %s", proxy_url)
    app_.state.http_client = httpx.AsyncClient(**client_kwargs)
    yield
    await app_.state.http_client.aclose()


async def get_async_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


async def check_httpx_err(body: str | bytes, api_key: Optional[str]):
    # too big or small for error
    if 10 > len(body) > 4000 or not api_key:
        return
    has_rate_limit_error, reset_time_ms = await check_rate_limit(body)
    if has_rate_limit_error:
        await key_manager.disable_key(api_key, reset_time_ms)


def prepare_forward_headers(request: Request) -> dict:
    return {
        k: v
        for k, v in request.headers.items()
        if k.lower()
           not in ["host", "content-length", "connection", "authorization", "x-api-key"]
    }


@router.api_route("/v1{path:path}", methods=["GET", "POST"])
async def proxy_endpoint(
    request: Request, path: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Main proxy endpoint for handling all requests to Anthropic-compatible API."""
    is_public = any(f"/v1{path}".startswith(ep) for ep in config["anthropic"]["public_endpoints"])

    # Extract key from authorization header if x-api-key not provided
    if not x_api_key and authorization:
        x_api_key = authorization.removeprefix("Bearer ").strip()

    # Verify authorization for non-public endpoints
    if not is_public:
        await verify_access_key(x_api_key=x_api_key)

    # Log the full request URL including query parameters
    full_url = str(request.url).replace(str(request.base_url), "/")

    # Get API key to use
    api_key = "" if is_public else await key_manager.get_next_key()

    logger.info("Proxying request to %s (Public: %s, key: %s)", full_url, is_public, mask_key(api_key))

    is_stream = False
    if request.method == "POST":
        try:
            if body_bytes := await request.body():
                request_body = json.loads(body_bytes)
                if is_stream := request_body.get("stream", False):
                    logger.info("Detected streaming request")
                if model := request_body.get("model"):
                    logger.info("Using model: %s", model)
        except Exception as e:
            logger.debug("Could not parse request body: %s", str(e))

    return await proxy_with_httpx(request, path, api_key, is_stream)


async def proxy_with_httpx(
    request: Request,
    path: str,
    api_key: str,
    is_stream: bool,
) -> Response:
    """Core logic to proxy requests to Anthropic-compatible API."""
    req_kwargs = {
        "method": request.method,
        "url": f"{config['anthropic']['base_url']}{path}",
        "headers": prepare_forward_headers(request),
        "content": await request.body(),
        "params": request.query_params,
    }
    if api_key:
        req_kwargs["headers"]["authorization"] = api_key

    client = await get_async_client(request)
    try:
        anthropic_req = client.build_request(**req_kwargs)
        anthropic_resp = await client.send(anthropic_req, stream=is_stream)

        if anthropic_resp.status_code >= 400:
            if is_stream:
                try:
                    await anthropic_resp.aread()
                except Exception as e:
                    await anthropic_resp.aclose()
                    raise e
            anthropic_resp.raise_for_status()

        headers = dict(anthropic_resp.headers)
        # Content has already been decoded
        headers.pop("content-encoding", None)
        headers.pop("Content-Encoding", None)

        if not is_stream:
            body = anthropic_resp.content
            await check_httpx_err(body, api_key)
            return Response(
                content=body,
                status_code=anthropic_resp.status_code,
                media_type="application/json",
                headers=headers,
            )

        async def sse_stream():
            error_json = ""
            try:
                async for line in anthropic_resp.aiter_lines():
                    # Capture data lines that contain Anthropic errors for rate limit detection
                    if line.startswith("data: {"):
                        data_str = line[6:]
                        if '"type":"error"' in data_str or '"type": "error"' in data_str:
                            error_json = data_str
                    yield f"{line}\n\n".encode("utf-8")
            except Exception as err:
                logger.error("sse_stream error: %s", err)
            finally:
                await anthropic_resp.aclose()
            await check_httpx_err(error_json, api_key)

        return StreamingResponse(
            sse_stream(),
            status_code=anthropic_resp.status_code,
            media_type="text/event-stream",
            headers=headers,
        )
    except httpx.HTTPStatusError as e:
        await check_httpx_err(e.response.content, api_key)
        logger.error("Request error: %s", str(e))
        raise HTTPException(e.response.status_code, str(e.response.content)) from e
    except httpx.ConnectError as e:
        logger.error("Connection error to Anthropic API: %s", str(e))
        raise HTTPException(503, "Unable to connect to Anthropic API") from e
    except httpx.TimeoutException as e:
        logger.error("Timeout connecting to Anthropic API: %s", str(e))
        raise HTTPException(504, "Anthropic API request timed out") from e
    except Exception as e:
        logger.error("Internal error: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal Proxy Error") from e


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
