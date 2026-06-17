import os
import sys
import asyncio


# Make voice_agent/ importable no matter where we run from
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, ".."))

from run_pipeline import main
from database.db_context import _connect, delete_care_session
from psycopg2.extras import RealDictCursor




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


def test_full_pipeline_write():
    new_id = None
    try:
        # 1. Run the full pipeline (this calls Gemini — slow, uses quota)
        new_id = asyncio.run(main())
        assert new_id, "Pipeline did not return a care_session_id"
        print(f"  inserted care_session_id = {new_id}")

        # 2. Read the row back and check it landed correctly
        row = read_back(new_id)
        assert row is not None, "Row was not found in the database after insert"
        assert row["session_status"] == "submitted_by_dsp", \
            f"unexpected status: {row['session_status']}"
        assert row["dsp_has_signed"] is True, "dsp_has_signed should be True"
        assert row["level_of_support_provided"] == "verbal_prompts", \
            f"support not translated: {row['level_of_support_provided']}"
        assert len(row["goals_addressed_in_session"]) >= 1, \
            "no goals were written"
        print("  read-back checks passed ✓")

    finally:
        # 3. Clean up — runs even if an assertion above failed
        if new_id:
            delete_care_session(new_id)
            print(f"  cleaned up test row {new_id}")


if __name__ == "__main__":
    test_full_pipeline_write()
    print("\n write-path test passed")