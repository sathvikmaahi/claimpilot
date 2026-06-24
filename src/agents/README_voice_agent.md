cat > README.md << 'EOF'
# Voice Agent (Pipeline A · Agent A2)

Turns a Direct Support Professional's spoken account of their shift into structured progress-note fields, ready to be written as a billable care session.

## What it does

A DSP narrates their shift by voice. The pipeline runs two extraction agents and assembles one structured result (the "Voice Extraction Object"):

- **Section 1 — activity narrative:** one recording covering what was done, roughly when, the level of support given, and how the recipient responded. From it the agent extracts the activities, timestamps, support level, and engagement notes; maps the activities to the recipient's active ISP goals; and flags documentation gaps (e.g. a scheduled medication within the shift that wasn't mentioned).
- **Section 2 — observations:** short per-topic recordings for health, behavioral, and community-outing notes. Only the topics the DSP toggled on are captured.

Recipient context (active goals, medications, shift) is read from the database; the completed session is written back.

## Folder layout

| Path | Role |
|------|------|
| `narrative_extractor/` | The activity-narrative extractor (ADK agent). |
| `observation_extractor/` | The single-observation extractor (ADK agent), called once per toggled topic. |
| `database/` | Cloud SQL access (`db_context.py`) and the schema reference (`schema.sql`). |
| `run_pipeline.py` | The orchestrator — loads context, runs the agents, assembles the result. |
| `tests/` | Development and connection test scripts. |

## Running it

Run everything from **inside this `voice_agent/` folder**, with your virtual environment active.

**Full pipeline:**

    python run_pipeline.py

Produces the complete Voice Extraction Object for the test recipient.

**A single agent on its own** (useful while developing one section):

    adk run narrative_extractor

Then type or speak input when prompted; Ctrl+C to exit.

## Configuration

Each agent folder has a `.env` (git-ignored) holding the Gemini/Vertex settings and the Cloud SQL credentials (`CLOUD_SQL_HOST`, `CLOUD_SQL_PASSWORD`). These are never committed — see `.gitignore`.

## Tech

Google ADK (agent framework) · Gemini 2.5 Flash (native-audio extraction) · Google Cloud SQL / PostgreSQL (recipient data).
