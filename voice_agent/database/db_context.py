import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv("/Users/shubhangvangari/Documents/AI_fellowship/care-claim-repo/care-claim-ai/section_1_agent/.env")


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
        select care_recipient_id, full_name, medicaid_id, waiver_program
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
        select medication_name, dosage_amount, scheduled_time_of_day
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

    return {
        "goals_text": goals_text,
        "medications": medications,
        "shift": shift,
        "care_recipient_id": care_recipient_id,            # FK for the write
        "shift_assignment_id": shift_row["shift_assignment_id"],  # FK for the write
    }
    
    
if __name__ == "__main__":
    import json
    print(json.dumps(load_context("482910053"), indent=2))   # Marcus