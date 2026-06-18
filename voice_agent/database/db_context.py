import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(here, "..", "section_1_agent", ".env"))

def _connect():
    """Open a fresh Cloud SQL connection."""
    return psycopg2.connect(
        host=os.environ["CLOUD_SQL_HOST"],
        port=5432,
        dbname="claimpilot",
        user="postgres",
        password=os.environ["CLOUD_SQL_PASSWORD"],
        sslmode="require",
    )


def load_context(medicaid_id: str) -> dict:
    """Fetch one recipient's goals, meds, and today's shift, shaped for the agent."""
    conn = _connect()
    # RealDictCursor makes each row a dict (like Supabase), so we use row["col"] not row[0].
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Recipient — look up by medicaid_id, get the real primary key.
    cur.execute("""
        select care_recipient_id, full_name, medicaid_id, waiver_program,
               date_of_birth, primary_diagnosis_code
        from care_recipients
        where medicaid_id = %s;
    """, (medicaid_id,))
    recipient = cur.fetchone()
    care_recipient_id = recipient["care_recipient_id"]

    # 2. Active goals.
    cur.execute("""
        select goal_id, goal_category, goal_description
        from support_plan_goals
        where care_recipient_id = %s and is_currently_active = true
        order by goal_category;
    """, (care_recipient_id,))
    goals = cur.fetchall()

    # 3. Active meds.
    cur.execute("""
        select medication_id, medication_name, dosage_amount,
               administration_route, scheduled_time_of_day
        from prescribed_medications
        where care_recipient_id = %s and is_currently_active = true
        order by scheduled_time_of_day;
    """, (care_recipient_id,))
    meds = cur.fetchall()

    # 4. Today's shift.
    cur.execute("""
        select shift_assignment_id, direct_support_professional_name,
               service_location_name, scheduled_start_time, scheduled_end_time,
               service_billing_code
        from staff_shift_assignments
        where care_recipient_id = %s and shift_date = current_date;
    """, (care_recipient_id,))
    shift_row = cur.fetchone()

    cur.close()
    conn.close()

    # --- Reshape into the SAME structures the agent + gaps already expect ---
    goals_text = "\n".join(
        f'- goal_id={g["goal_id"]} | category={g["goal_category"]} | "{g["goal_description"]}"'
        for g in goals
    )
    medications = [
        {"name": m["medication_name"], "time": str(m["scheduled_time_of_day"])}
        for m in meds
    ]
    shift = {
        "start": str(shift_row["scheduled_start_time"]),
        "end": str(shift_row["scheduled_end_time"]),
    }

    # Auto-fields: what the progress form pre-fills but the DSP never speaks.
    # /extract returns these straight to the frontend to populate form Sections 1-2.
    auto_fields = {
        "recipient_name": recipient["full_name"],
        "medicaid_id": recipient["medicaid_id"],
        "date_of_birth": str(recipient["date_of_birth"]),
        "primary_diagnosis_code": recipient["primary_diagnosis_code"],
        "waiver_program": recipient["waiver_program"],
        "service_location_name": shift_row["service_location_name"],
        "dsp_name": shift_row["direct_support_professional_name"],
        "scheduled_start_time": str(shift_row["scheduled_start_time"]),
        "scheduled_end_time": str(shift_row["scheduled_end_time"]),
        "service_billing_code": shift_row["service_billing_code"],
    }

    return {
        "goals_text": goals_text,
        "goals_raw": goals,
        "medications": medications,   # simple list — gap detection consumes this
        "meds_raw": meds,             # full rows incl. medication_id — MAR writer consumes this
        "shift": shift,
        "care_recipient_id": care_recipient_id,
        "shift_assignment_id": shift_row["shift_assignment_id"],
        "auto_fields": auto_fields,
    }
    
    
    
def insert_care_session(row: dict) -> str:
    """Insert one documented_care_sessions row. Returns the new care_session_id."""
    conn = _connect()
    cur = conn.cursor()

    columns = list(row.keys())
    placeholders = ", ".join(
        "%s::uuid[]" if col == "goals_addressed_in_session" else "%s"
        for col in columns
    )
    col_names = ", ".join(columns)

    sql = f"""
        insert into documented_care_sessions ({col_names})
        values ({placeholders})
        returning care_session_id;
    """
    cur.execute(sql, list(row.values()))
    new_id = cur.fetchone()[0]

    conn.commit()          # <-- writes are NOT saved until you commit
    cur.close()
    conn.close()
    return str(new_id)


def delete_care_session(care_session_id: str) -> None:
    """Delete one care session by id (used for test cleanup)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "delete from documented_care_sessions where care_session_id = %s;",
        (care_session_id,),
    )
    conn.commit()          # deletes, like inserts, aren't permanent until commit
    cur.close()
    conn.close()



def insert_mar_rows(cur, care_session_id: str, mar_entries: list[dict]) -> int:
    """
    Insert one medication_administration_records row per dose.

    Works on a CALLER-PROVIDED cursor (does NOT open its own connection or commit)
    so the MAR can share one transaction with the progress-note write — the note
    and its MAR rows must commit together or not at all. The caller owns the
    connection lifecycle and the commit.

    Each entry in mar_entries:
      - medication_id   (real UUID, resolved from the DB by the caller)
      - was_given       (bool — True if administered)
      - admin_time      (timestamp the dose was given, or None)
      - reason_not_given (required string when was_given is False, else None)

    Enforces the schema's reason_required_when_not_given rule BEFORE inserting,
    so we fail fast with a clear error instead of a raw DB constraint violation.

    Returns the number of rows inserted.
    """
    for e in mar_entries:
        if not e["was_given"] and not e.get("reason_not_given"):
            raise ValueError(
                f"Medication {e['medication_id']} marked not given but no reason supplied; "
                "a reason is required when a dose is not administered."
            )

    sql = """
        insert into medication_administration_records
            (care_session_id, medication_id, was_medication_given,
             actual_administration_time, reason_if_not_given)
        values (%s, %s, %s, %s, %s);
    """
    for e in mar_entries:
        cur.execute(sql, (
            care_session_id,
            e["medication_id"],
            e["was_given"],
            e.get("admin_time"),
            e.get("reason_not_given"),
        ))
    return len(mar_entries)
    
# if __name__ == "__main__":
#     import json
#     print(json.dumps(load_context("482910053"), indent=2))   # Marcus