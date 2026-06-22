import os
import sys
import asyncio
import pytest

# Make voice_agent/ importable no matter where we run from
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))

from services.pipeline import extract, write_session
from db.db_context import _connect, delete_care_session
from psycopg2.extras import RealDictCursor

MARCUS_MEDICAID_ID = "482910053"


def _read(path):
    with open(os.path.join(here, "..", "..", "agents", path), "rb") as f:
        return f.read()


def read_back(care_session_id):
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        select care_recipient_id, level_of_support_provided,
               goals_addressed_in_session, session_status, dsp_has_signed
        from documented_care_sessions
        where care_session_id = %s;
    """, (care_session_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def count_mar(care_session_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "select count(*) from medication_administration_records where care_session_id = %s;",
        (care_session_id,),
    )
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n




@pytest.mark.integration
def test_full_pipeline_write():
    """End-to-end: extract -> write_session (note + MAR atomically) -> read back -> clean up."""
    new_id = None
    try:
        # 1. Extract (calls Gemini — slow, uses quota), then submit.
        result = asyncio.run(extract(
            medicaid_id=MARCUS_MEDICAID_ID,
            narration_activities=_read("narrative_extractor/section1.m4a"),
            narration_engagement=None,
            toggled={},
        ))
        approved = dict(result["progress_note"])
        approved["medicaid_id"] = MARCUS_MEDICAID_ID
        mar_grid = [
            {"medication_name": m["medication_name"], "was_given": True}
            for m in result["mar_scaffold"]
        ]
        # Resolve every active goal — required by goal-enforcement validation,
        # mirroring what a real DSP submission sends.
        goals_resolution = [
            {"goal_id": g["goal_id"], "addressed": True, "note": "covered in shift"}
            for g in result["active_goals"]
        ]
        out = write_session(
            approved, mar_grid=mar_grid, meals=["Lunch"], personal_care=[],
            goals_resolution=goals_resolution,
        )
        new_id = out["care_session_id"]
        assert new_id, "Pipeline did not return a care_session_id"
        print(f"  inserted care_session_id = {new_id}")

        # 2. Read the note back and check it landed correctly.
        row = read_back(new_id)
        assert row is not None, "Row was not found in the database after insert"
        assert row["session_status"] == "submitted_by_dsp", \
            f"unexpected status: {row['session_status']}"
        assert row["dsp_has_signed"] is True, "dsp_has_signed should be True"
        assert row["level_of_support_provided"] == "verbal_prompts", \
            f"support not translated: {row['level_of_support_provided']}"
        assert len(row["goals_addressed_in_session"]) >= 1, "no goals were written"

        # 3. Check the MAR rows landed in the same write.
        assert out["mar_rows_written"] == count_mar(new_id) == len(mar_grid), \
            "MAR rows not written as expected"
        print("  read-back checks passed (note + MAR) ")

    finally:
        # 4. Clean up — runs even if an assertion above failed (MAR cascades on delete).
        if new_id:
            delete_care_session(new_id)
            print(f"  cleaned up test row {new_id}")


if __name__ == "__main__":
    test_full_pipeline_write()
    print("\n write-path test passed")
