"""
Agent loop using Groq (qwen/qwen3.8-27b) with tool calling.
Observe → Reason → Act (tool call) → Feed result back → Continue.
"""
import json
import os
import re
import time
from groq import Groq, RateLimitError, BadRequestError
from agent_tools import TOOLS, dispatch_tool
from tools.memory import get_all_preferences

MODEL = "qwen/qwen3.8-27b"

SYSTEM_PROMPT = """Kirana store assistant. Call tools only, never invent data.
Rules: NEVER show stock/prices/bills/sales without calling the relevant tool first. For bills: create_bill once, add_item_to_bill per item, finalize_bill last. One tool call at a time. Khata: add_credit=owes store, record_payment=pays back. Amounts in Rs. 2 decimals. Reply in owner's language (Hindi/English). Be concise."""


def _groq_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOLS
    ]


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _trim_tool_results(messages, max_chars=300):
    """Truncate tool result content in history to reduce token count."""
    trimmed = []
    for m in messages:
        if m.get("role") == "tool" and len(m.get("content", "")) > max_chars:
            m = {**m, "content": m["content"][:max_chars] + "…"}
        trimmed.append(m)
    return trimmed


def run_agent(chat_id: str, user_message: str, history: list) -> tuple[str, list, list]:
    prefs = get_all_preferences()
    pref_context = ""
    if prefs["preferences"]:
        pref_context = f"\n[Owner preferences: {json.dumps(prefs['preferences'])}]"

    # Keep only last 10 messages and truncate large tool results
    trimmed_history = _trim_tool_results(history[-10:])

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + trimmed_history
        + [{"role": "user", "content": user_message + pref_context}]
    )

    files_to_send = []
    groq_tools = _groq_tools()

    while True:
        for attempt in range(3):
            try:
                response = _get_client().chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=groq_tools,
                    tool_choice="auto",
                    max_tokens=400,
                    reasoning_effort="none",
                )
                break
            except RateLimitError as e:
                msg_text = str(e)
                # TPD (daily) limit — extract wait time and raise with friendly message
                if "tokens per day" in msg_text or "TPD" in msg_text:
                    m = re.search(r'try again in (\d+m[\d.]+s|[\d.]+s)', msg_text)
                    wait_str = m.group(1) if m else "some time"
                    raise RuntimeError(f"\u23f3 Daily token limit reached. Please try again in {wait_str}.")
                # OTPM (per-minute) limit — wait and retry
                if attempt == 2:
                    raise
                time.sleep(15)
            except BadRequestError as e:
                # 413: input too large — drop half the history and retry
                if "413" in str(e) or "Request too large" in str(e):
                    if attempt == 2:
                        raise
                    keep = max(2, len(trimmed_history) // 2)
                    trimmed_history = _trim_tool_results(trimmed_history[-keep:], max_chars=150)
                    messages = (
                        [{"role": "system", "content": SYSTEM_PROMPT}]
                        + trimmed_history
                        + [{"role": "user", "content": user_message + pref_context}]
                    )
                else:
                    raise

        msg = response.choices[0].message

        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if not msg.tool_calls:
            saved = [m for m in messages if m.get("role") != "system"]
            return msg.content or "", saved[-10:], files_to_send

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            result = dispatch_tool(tc.function.name, args)

            if result.get("ok") and result.get("path"):
                files_to_send.append(result["path"])

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })
