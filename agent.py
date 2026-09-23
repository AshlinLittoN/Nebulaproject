"""
Agent loop using Groq (qwen/qwen3.8-27b) with tool calling.
Observe → Reason → Act (tool call) → Feed result back → Continue.
"""
import json
import os
import time
from groq import Groq, RateLimitError
from agent_tools import TOOLS, dispatch_tool
from tools.memory import get_all_preferences

MODEL = "qwen/qwen3.8-27b"

SYSTEM_PROMPT = """You are a kirana store assistant. You ONLY answer by calling tools. Never make up data.

CRITICAL RULES:
- NEVER invent numbers, stock levels, prices, bill numbers, or sales data.
- NEVER answer a data question without calling a tool first.
- NEVER show a list of products without calling list_products first.
- NEVER show sales figures without calling daily_close or sales_summary first.
- NEVER show a bill without calling view_bill or get_bill_by_number first.
- NEVER show stock without calling query_stock or list_products first.
- If you have not called a tool, you do not have the data. Do not guess.
- For bills: call create_bill ONCE, then add_item_to_bill for EACH item one by one, then finalize_bill.
- Make ONE tool call at a time. Wait for the result before the next call.
- Payment mode: use default_payment preference if set, else ask the owner.
- Khata: add_credit = customer owes store. record_payment = customer pays back.
- Amounts always in Rs. with 2 decimal places.
- LANGUAGE: Reply in the same language the owner used (Hindi or English).
- For barcodes: always use set_barcode and lookup_by_barcode tools.
- Be concise.
"""


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


def run_agent(chat_id: str, user_message: str, history: list) -> tuple[str, list, list]:
    prefs = get_all_preferences()
    pref_context = ""
    if prefs["preferences"]:
        pref_context = f"\n[Owner preferences: {json.dumps(prefs['preferences'])}]"

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
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
                    max_tokens=800,
                    reasoning_effort="none",
                )
                break
            except RateLimitError:
                if attempt == 2:
                    raise
                time.sleep(15)

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
            return msg.content or "", saved, files_to_send

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
