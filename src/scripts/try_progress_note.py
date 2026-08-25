"""
Throwaway verification script for the progress_note_extractor vision agent.

Reads a photographed, hand-filled Progress Note (one or more ordered page
images) and prints the agent's parsed JSON so we can eyeball it against the
paper BEFORE wiring anything. No DB writes.

The form is multi-page: pass the page images in order. They are fed to ONE
agent call as ordered image parts and produce a SINGLE combined extraction.

Usage (run from src/):
    uv run python -m scripts.try_progress_note <page1> [page2 ...] [medicaid_id]

Any all-digit argument is treated as the medicaid_id; the rest are page-image
paths in order. medicaid_id defaults to Linda Martinez (517402981) — the
recipient on the form template. Her shift must be dated today, or load_context
raises NoShiftToday (the DB filters shift_date = current_date).
"""

import sys
import json
import mimetypes
import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from db.db_context import load_context
from agents.progress_note_extractor.agent import build_progress_note_extractor

APP_NAME = "claimpilot_image_try"
USER_ID = "dsp_maria"


async def main(image_paths: list[str], medicaid_id: str) -> None:
    # 1. The recipient's real active goals -> the agent's Section 12 match list.
    ctx = load_context(medicaid_id)
    print(f"loaded goals for {medicaid_id}:\n{ctx['goals_text']}\n")

    # 2. Read each page's bytes + guess its mime, preserving the given order.
    parts = []
    for i, image_path in enumerate(image_paths, start=1):
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        print(f"page {i}: {image_path} ({len(image_bytes)} bytes, {mime})")
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    print()

    # 3. Build the agent with goals injected, run it over ALL page parts at once.
    agent = build_progress_note_extractor(ctx["goals_text"])
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    message = types.Content(role="user", parts=parts)

    text = None
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content:
            text = event.content.parts[0].text

    # 4. Print the parsed extraction for inspection.
    print("=== extraction ===")
    print(json.dumps(json.loads(text), indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    # Any all-digit arg is the medicaid_id; everything else is a page-image path.
    mids = [a for a in args if a.isdigit()]
    pages = [a for a in args if not a.isdigit()]
    if not pages:
        sys.exit("usage: uv run python -m scripts.try_progress_note <page1> [page2 ...] [medicaid_id]")
    mid = mids[0] if mids else "517402981"
    asyncio.run(main(pages, mid))
