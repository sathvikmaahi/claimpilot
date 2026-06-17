# Section 2 Agent — Observation Extractor

An ADK agent that extracts ONE observation field from a short, focused DSP recording. It is deliberately single-purpose: each call handles exactly one topic.

## Input

A short voice note about ONE topic the DSP toggled on. The orchestrator calls this agent once per toggled topic — never combined.

## The three topics

- `health` → `health_observations` (symptoms, skin, appetite, sleep, injury, pain)
- `behavioral` → `behavioral_observations` (mood, agitation, engagement, an incident)
- `outing` → `community_outing` (where they went, how long, what happened)

## What it returns

- `value` — a concise clinical note for the one target topic only
- `confidence` — High / Medium / Low

## Notes

- The target topic is supplied per call via `build_section2_agent(field)`, which stamps the right instruction and field into a fresh agent. This is what keeps each call disciplined to a single topic, rather than the model grabbing everything it hears.
- Topics the DSP did not toggle are never sent here — they simply stay null. No toggle, no agent call.
- No goal mapping or gap detection happens here; that is Section 1's job.

## Files

| File | Role |
|------|------|
| `agent.py` | The agent factory (`build_section2_agent`), schema, and instruction. |
| `__init__.py` | Marks this folder as a discoverable ADK agent package. |
