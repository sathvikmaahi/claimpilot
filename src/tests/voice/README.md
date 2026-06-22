# Tests

Development and verification scripts for the voice pipeline. These are run by hand during the build to confirm pieces work — they are not part of the running pipeline, and nothing in the app imports them.

## Files

| File | What it checks |
|------|----------------|
| `test_cloudsql.py` | Confirms the Cloud SQL connection works — driver, SSL, credentials, and that the recipient tables return rows. Run this first if the database seems unreachable. |

## Running

Run from inside `voice_agent/`, with the virtual environment active and the `.env` credentials in place:

    python tests/test_cloudsql.py

A successful run prints recipient rows from the database. Connection failures usually mean the machine's IP isn't authorized on the Cloud SQL instance, or the credentials in `.env` are wrong.

## Adding tests

This folder holds all test scripts, not only database ones. As the pipeline grows, add checks here (extraction, gap detection, the write path) and list them in the table above so anyone can see what's covered at a glance.
