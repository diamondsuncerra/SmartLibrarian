from __future__ import annotations
import json
from typing import List, Tuple
from openai import OpenAI
from .summary import get_summary_by_title

SYSTEM_PROMPT = (
    "You are Smart Librarian. You will be given a user query and a small list of candidate titles "
    "with similarity scores from a vector search.\n"
    "1) Pick EXACTLY ONE title that best matches the user's themes.\n"
    "2) Call the tool `get_summary_by_title` with that exact title.\n"
    "3) Compose a helpful final answer that includes: a one-sentence recommendation, why it matches, "
    "and the full summary returned by the tool.\n"
    "Be concise but friendly. If candidates are empty, ask the user to rephrase."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_summary_by_title",
            "description": "Return the full summary of an exact book title.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string", "description": "Exact book title"}},
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    }
]

def recommend_with_toolcall(user_query: str, candidates: List[Tuple[str, float]], *, model: str, client: OpenAI | None = None) -> tuple[str, str, str]:
    """
    Returns (final_answer_text, chosen_title, full_summary).
    """
    client = client or OpenAI()
    cand = [{"title": t, "distance": float(d)} for (t, d) in candidates]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"user_query": user_query, "candidates": cand})},
    ]

    chosen_title = ""
    chosen_full = ""

    for _ in range(6):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.4,
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append(
                {"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump() for tc in msg.tool_calls]}
            )
            for tc in msg.tool_calls:
                if tc.function.name == "get_summary_by_title":
                    args = json.loads(tc.function.arguments or "{}")
                    title = (args.get("title") or "").strip()
                    full_summary = get_summary_by_title(title)
                    if title:
                        chosen_title = title
                    if full_summary:
                        chosen_full = full_summary
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": "get_summary_by_title",
                            "content": full_summary,
                        }
                    )
            continue

        return (msg.content or "Sorry, I couldn't generate a response.", chosen_title, chosen_full)

    return ("Sorry, I couldn't complete the tool interaction.", chosen_title, chosen_full)
