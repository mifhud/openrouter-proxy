import json
import time
import uuid
from typing import Any, AsyncIterator

from config import logger


def _sse_event(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


def _anthropic_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


def _anthropic_tool_choice_to_openai(tool_choice: Any) -> Any:
    if not tool_choice:
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    tc_type = tool_choice.get("type")
    if tc_type == "auto":
        return "auto"
    if tc_type == "any":
        return "required"
    if tc_type == "tool":
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return None


def _anthropic_content_to_openai_user(content: Any) -> Any:
    """Convert Anthropic user message content to OpenAI format.
    Returns (openai_content, tool_result_messages) where tool_result_messages
    are extra messages to insert for tool_result blocks."""
    if isinstance(content, str):
        return content, []

    if not isinstance(content, list):
        return content, []

    tool_results = []
    other_parts = []

    for block in content:
        if not isinstance(block, dict):
            other_parts.append(block)
            continue
        btype = block.get("type")
        if btype == "tool_result":
            tool_use_id = block.get("tool_use_id", "")
            result_content = block.get("content", "")
            if isinstance(result_content, list):
                # flatten text blocks
                texts = []
                for rb in result_content:
                    if isinstance(rb, dict) and rb.get("type") == "text":
                        texts.append(rb.get("text", ""))
                    else:
                        texts.append(json.dumps(rb))
                result_content = "\n".join(texts)
            elif not isinstance(result_content, str):
                result_content = json.dumps(result_content)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_use_id,
                "content": result_content,
            })
        elif btype == "text":
            other_parts.append({"type": "text", "text": block.get("text", "")})
        elif btype == "image":
            source = block.get("source", {})
            src_type = source.get("type")
            if src_type == "base64":
                media_type = source.get("media_type", "image/png")
                data = source.get("data", "")
                url = f"data:{media_type};base64,{data}"
            else:
                url = source.get("url", "")
            other_parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            other_parts.append(block)

    # Build final user content
    if not other_parts:
        user_content = None
    elif len(other_parts) == 1 and other_parts[0].get("type") == "text":
        user_content = other_parts[0]["text"]
    else:
        user_content = other_parts

    return user_content, tool_results


def _anthropic_content_to_openai_assistant(content: Any) -> tuple[Any, list]:
    """Returns (content_str_or_none, tool_calls_list)"""
    if isinstance(content, str):
        return content, []

    if not isinstance(content, list):
        return None, []

    text_parts = []
    tool_calls = []

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", ""),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })

    text_content = "".join(text_parts) if text_parts else None
    return text_content, tool_calls


def _anthropic_messages_to_openai(messages: list, system: str | None = None) -> list:
    result = []

    if system:
        # Anthropic allows system as a list of content blocks; flatten to string for OpenAI
        if isinstance(system, list):
            system = " ".join(
                b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"
            )
        if system:
            result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if role == "user":
            user_content, tool_result_msgs = _anthropic_content_to_openai_user(content)
            if tool_result_msgs:
                # If there's also user content, add it before tool results
                if user_content is not None:
                    result.append({"role": "user", "content": user_content})
                result.extend(tool_result_msgs)
            else:
                result.append({"role": "user", "content": user_content})
        elif role == "assistant":
            text_content, tool_calls = _anthropic_content_to_openai_assistant(content)
            oai_msg: dict = {"role": "assistant"}
            if text_content:
                oai_msg["content"] = text_content
            else:
                oai_msg["content"] = None
            if tool_calls:
                oai_msg["tool_calls"] = tool_calls
            result.append(oai_msg)
        else:
            result.append(msg)

    return result


def translate_messages_request(body: dict) -> dict:
    system = body.get("system")
    messages = body.get("messages", [])

    oai_messages = _anthropic_messages_to_openai(messages, system=system)

    result: dict = {
        "model": body.get("model", ""),
        "messages": oai_messages,
    }

    # Copy simple fields
    for field in ("max_tokens", "temperature", "top_p", "stream"):
        if field in body:
            result[field] = body[field]

    if "stop_sequences" in body:
        result["stop"] = body["stop_sequences"]

    if "tools" in body:
        result["tools"] = [_anthropic_tool_to_openai(t) for t in body["tools"]]

    if "tool_choice" in body:
        tc = _anthropic_tool_choice_to_openai(body["tool_choice"])
        if tc is not None:
            result["tool_choice"] = tc

    if body.get("stream"):
        result["stream_options"] = {"include_usage": True}

    return result


def _finish_reason_to_stop_reason(finish_reason: str) -> str:
    mapping = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "content_filter": "end_turn",
    }
    result = mapping.get(finish_reason)
    if result is None:
        logger.warning("Unknown finish_reason '%s', defaulting to end_turn", finish_reason)
        result = "end_turn"
    return result


def _openai_message_to_anthropic_content(message: dict) -> list:
    content = []

    text = message.get("content")
    if text:
        content.append({"type": "text", "text": text})

    tool_calls = message.get("tool_calls") or []
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            input_data = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            input_data = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": input_data,
        })

    return content


def translate_chat_completion_response(response: dict) -> dict:
    msg_id = response.get("id", "")
    anthropic_id = f"msg_{msg_id[:24]}"

    choices = response.get("choices", [])
    choice = choices[0] if choices else {}
    message = choice.get("message", {})

    content = _openai_message_to_anthropic_content(message)

    finish_reason = choice.get("finish_reason") or "stop"
    stop_reason = _finish_reason_to_stop_reason(finish_reason)

    usage = response.get("usage", {})

    return {
        "id": anthropic_id,
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": response.get("model", ""),
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


async def translate_openai_stream_to_anthropic(
    lines_iter: AsyncIterator[str], model: str
) -> AsyncIterator[bytes]:
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    emitted_message_start = False
    emitted_text_block_start = False
    text_block_index = 0
    current_block_index = -1
    tool_state: dict[int, dict] = {}  # oai_index -> {block_index, id, name}
    input_tokens = 0
    output_tokens = 0
    finish_reason = None

    async for line in lines_iter:
        line = line.strip()
        if not line:
            continue
        if not line.startswith("data:"):
            continue

        raw = line[len("data:"):].strip()

        if raw == "[DONE]":
            break

        try:
            chunk = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse SSE chunk: %s", raw)
            continue

        # Emit message_start on first real chunk
        if not emitted_message_start:
            emitted_message_start = True
            yield _sse_event("message_start", {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": model,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            })
            yield _sse_event("ping", {"type": "ping"})

        # Extract usage if present
        usage = chunk.get("usage")
        if usage:
            input_tokens = usage.get("prompt_tokens", input_tokens)
            output_tokens = usage.get("completion_tokens", output_tokens)

        choices = chunk.get("choices", [])
        if not choices:
            continue

        choice = choices[0]
        delta = choice.get("delta", {})
        fr = choice.get("finish_reason")
        if fr:
            finish_reason = fr

        # Handle text delta
        text_delta = delta.get("content")
        if text_delta:
            if not emitted_text_block_start:
                emitted_text_block_start = True
                text_block_index = current_block_index + 1
                current_block_index = text_block_index
                yield _sse_event("content_block_start", {
                    "type": "content_block_start",
                    "index": text_block_index,
                    "content_block": {"type": "text", "text": ""},
                })
            yield _sse_event("content_block_delta", {
                "type": "content_block_delta",
                "index": text_block_index,
                "delta": {"type": "text_delta", "text": text_delta},
            })

        # Handle tool call deltas
        tool_calls_delta = delta.get("tool_calls", [])
        for tc_delta in tool_calls_delta:
            oai_idx = tc_delta.get("index", 0)

            if oai_idx not in tool_state:
                # New tool call — close text block if open
                if emitted_text_block_start:
                    yield _sse_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": text_block_index,
                    })
                    emitted_text_block_start = False

                # Note: previous tool blocks are closed in the finalization loop
                # to avoid double-close events when multiple tools are streamed.

                block_index = current_block_index + 1
                current_block_index = block_index
                tc_id = tc_delta.get("id", "")
                fn = tc_delta.get("function", {})
                tc_name = fn.get("name", "")
                tool_state[oai_idx] = {
                    "block_index": block_index,
                    "id": tc_id,
                    "name": tc_name,
                }
                yield _sse_event("content_block_start", {
                    "type": "content_block_start",
                    "index": block_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tc_id,
                        "name": tc_name,
                        "input": {},
                    },
                })
            else:
                # May have updated name/id in subsequent chunks (rare)
                fn = tc_delta.get("function", {})
                if fn.get("name"):
                    tool_state[oai_idx]["name"] = fn["name"]

            # Emit argument delta
            fn = tc_delta.get("function", {})
            args_delta = fn.get("arguments", "")
            if args_delta:
                block_index = tool_state[oai_idx]["block_index"]
                yield _sse_event("content_block_delta", {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": "input_json_delta", "partial_json": args_delta},
                })

    # Finalization
    if not emitted_message_start:
        # Edge case: no chunks received
        yield _sse_event("message_start", {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        })
        yield _sse_event("ping", {"type": "ping"})

    # Close open text block
    if emitted_text_block_start:
        yield _sse_event("content_block_stop", {
            "type": "content_block_stop",
            "index": text_block_index,
        })

    # Close open tool blocks
    for oai_idx in sorted(tool_state.keys()):
        ts = tool_state[oai_idx]
        yield _sse_event("content_block_stop", {
            "type": "content_block_stop",
            "index": ts["block_index"],
        })

    stop_reason = _finish_reason_to_stop_reason(finish_reason) if finish_reason else "end_turn"

    yield _sse_event("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": output_tokens},
    })

    yield _sse_event("message_stop", {"type": "message_stop"})


def translate_models_response(openai_models: dict) -> dict:
    data = []
    for m in openai_models.get("data", []):
        ts = m.get("created", 0)
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
        data.append({
            "id": m.get("id", ""),
            "display_name": m.get("name") or m.get("id", ""),
            "created_at": created_at,
            "type": "model",
        })
    return {"data": data}
