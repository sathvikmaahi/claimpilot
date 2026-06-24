# Narrative Extractor

An ADK agent that reads a DSP's single spoken shift narration and returns structured activity documentation.

## Input

One voice recording (or text) describing the shift: what activities happened, roughly when, the level of support given, and how the recipient responded.

## What it extracts

- `transcript` — faithful transcription of the narration
- `activities_performed` — the distinct activities described
- `activity_timestamps` — times for activities that have a stated or implied time
- `support_level` — one of `independent`, `verbal`, `physical`, `full`, or `unknown`
- `individual_response` — how the recipient engaged or responded
- `isp_goals_addressed` — active goals the activities map to (mapped only on clear evidence)
- `confidence` — per-field High / Medium / Low

## Notes

- Goals are supplied at build time from the database, via `build_narrative_extractor(goals_text)` — the agent is not hardcoded to any recipient.
- Gap detection (e.g. an unmentioned scheduled medication) is **not** done here. It runs in deterministic Python (`detect_gaps.py`) after extraction, because the shift-window logic must be exact.

## Files

| File | Role |
|------|------|
| `agent.py` | The agent definition, schema, and instruction. |
| `detect_gaps.py` | Deterministic, shift-window-aware gap detection. |
| `__init__.py` | Marks this folder as a discoverable ADK agent package. |
