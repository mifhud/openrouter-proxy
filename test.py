#!/usr/bin/env python3
"""
Test script for Anthropic-compatible API Proxy with streaming responses.
Tests the proxy using configuration from config.yml.
"""

import asyncio
import json
import os

import httpx
import yaml

MODEL = "claude-sonnet-4-5"
STREAM = True
MAX_TOKENS = 600


def load_config():
    """Load configuration from config.yml"""
    with open("config.yml", encoding="utf-8") as file:
        return yaml.safe_load(file)


# Get configuration
config = load_config()
server_config = config["server"]

# Configure proxy settings from config
host = server_config["host"]
# Replace 0.0.0.0 with 127.0.0.1 for client connections
if host == "0.0.0.0":
    host = "127.0.0.1"
port = server_config["port"]
PROXY_URL = f"http://{host}:{port}"
ACCESS_KEY = server_config["access_key"]

# Override with environment variable if set
if os.environ.get("ACCESS_KEY"):
    ACCESS_KEY = os.environ.get("ACCESS_KEY")


async def test_anthropic_messages():
    """
    Test the Anthropic proxy with messages endpoint.
    """
    print(f"Testing Anthropic Proxy at {PROXY_URL} with model {MODEL}")

    url = f"{PROXY_URL}/v1/messages"
    headers = {
        "x-api-key": ACCESS_KEY or "dummy",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if not ACCESS_KEY:
        print("No valid access key found. Request may fail if server requires authentication.")
    else:
        print(f"Using access key: {ACCESS_KEY[:5]}...{ACCESS_KEY[-5:]}")

    # Request body following Anthropic API format
    request_data = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "user", "content": "Write a short poem about AI and humanity working together"}
        ],
        "stream": STREAM,
    }

    client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, read=600.0))
    req = client.build_request("POST", url, headers=headers, json=request_data)

    print(f"\nStarting to receive data streaming: {STREAM}...\n")
    print("-" * 50)

    resp = await client.send(req, stream=STREAM)
    try:
        resp.raise_for_status()
        if STREAM:
            current_event = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    current_event = line[7:].strip()
                elif line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if data.get("type") == "error":
                        raise ValueError(str(data))

                    if current_event == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            print(delta.get("text", ""), end='', flush=True)
        else:
            data = resp.json()
            if data.get("type") == "error":
                raise ValueError(str(data))
            content_blocks = data.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    print(block.get("text", ""), end='')
    except Exception as e:
        print(f"Error occurred during test: {str(e)}")
    finally:
        if STREAM:
            await resp.aclose()
    print("\n" + "-" * 50)
    if STREAM:
        print("\nStream completed!")
    else:
        print("\nNon-streaming response completed!")


if __name__ == "__main__":
    asyncio.run(test_anthropic_messages())
