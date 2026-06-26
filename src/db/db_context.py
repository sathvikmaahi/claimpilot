import os
from dotenv import load_dotenv
import psycopg2

from sqlalchemy import select, func, delete

# ORM (Pipeline A migration). The read path (load_roster, load_context) and the
# write path (create_care_session, insert_mar_rows, delete_care_session) are on
# SQLAlchemy; only _connect() / raw psycopg2 remains for any not-yet-migrated use.
from db.voice_session import get_session
from db.models.voice import (
    CareRecipient, ServiceLocation, StaffShiftAssignment,
    SupportPlanGoal, PrescribedMedication,
    DocumentedCareSession, MedicationAdministrationRecord,
)

here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(here, "..", "agents", "narrative_extractor", ".env"))

class NoShiftToday(Exception):
    """Raised when a recipient has no shift scheduled for today.
    A real, expected condition (not a bug) — callers can catch this and
    return a clean response instead of a raw crash."""


class RecipientNotFound(Exception):
    """Raised when no care recipient matches the given medicaid_id.
    An expected condition (unknown/bad id) — callers map it to a 404."""

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
    """Fetch one recipient's goals, meds, and today's shift, shaped for the agent.

    ORM VERSION (Pipeline A migration). Same four reads as the original psycopg2
    version (recipient -> goals -> meds -> today's shift) and the SAME return
    shape. UUIDs are stringified at the boundary so consumers — and the (still
    psycopg2) write path — keep seeing the same string ids RealDictCursor returned.
    """
    with get_session() as session:
        # 1. Recipient — look up by medicaid_id, get the real primary key.
        recipient = session.execute(
            select(
                CareRecipient.care_recipient_id, CareRecipient.full_name,
                CareRecipient.medicaid_id, CareRecipient.waiver_program,
                CareRecipient.date_of_birth, CareRecipient.primary_diagnosis_code,
            ).where(CareRecipient.medicaid_id == medicaid_id)
        ).first()
        if recipient is None:
            raise RecipientNotFound(f"No care recipient found for medicaid_id {medicaid_id}.")
        care_recipient_id = recipient.care_recipient_id

        # 2. Active goals.
        goals = session.execute(
            select(
                SupportPlanGoal.goal_id, SupportPlanGoal.goal_category,
                SupportPlanGoal.goal_description,
            )
            .where(
                SupportPlanGoal.care_recipient_id == care_recipient_id,
                SupportPlanGoal.is_currently_active.is_(True),
            )
            .order_by(SupportPlanGoal.goal_category)
        ).all()

        # 3. Active meds.
        meds = session.execute(
            select(
                PrescribedMedication.medication_id, PrescribedMedication.medication_name,
                PrescribedMedication.dosage_amount, PrescribedMedication.administration_route,
                PrescribedMedication.scheduled_time_of_day,
            )
            .where(
                PrescribedMedication.care_recipient_id == care_recipient_id,
                PrescribedMedication.is_currently_active.is_(True),
            )
            .order_by(PrescribedMedication.scheduled_time_of_day)
        ).all()

        # 4. Today's shift (joined to its location for the display name).
        shift_row = session.execute(
            select(
                StaffShiftAssignment.shift_assignment_id,
                StaffShiftAssignment.direct_support_professional_name,
                ServiceLocation.service_location_name,
                StaffShiftAssignment.scheduled_start_time,
                StaffShiftAssignment.scheduled_end_time,
                StaffShiftAssignment.service_billing_code,
            )
            .select_from(StaffShiftAssignment)
            .join(ServiceLocation, ServiceLocation.location_id == StaffShiftAssignment.location_id)
            .where(
                StaffShiftAssignment.care_recipient_id == care_recipient_id,
                StaffShiftAssignment.shift_date == func.current_date(),
            )
        ).first()

    # No shift dated today for this recipient — fail clearly, not with a raw
    # NoneType crash. This is an expected condition a live app must handle.
    if shift_row is None:
        raise NoShiftToday(
            f"No shift scheduled today for recipient with medicaid_id {medicaid_id}."
        )

    # --- Reshape into the SAME dict structures the agent + write path expect ---
    # str() the UUIDs so the contract matches the old RealDictCursor output.
    goals_raw = [
        {"goal_id": str(g.goal_id), "goal_category": g.goal_category,
         "goal_description": g.goal_description}
        for g in goals
    ]
    meds_raw = [
        {"medication_id": str(m.medication_id), "medication_name": m.medication_name,
         "dosage_amount": m.dosage_amount, "administration_route": m.administration_route,
         "scheduled_time_of_day": m.scheduled_time_of_day}
        for m in meds
    ]

    goals_text = "\n".join(
        f'- goal_id={g["goal_id"]} | category={g["goal_category"]} | "{g["goal_description"]}"'
        for g in goals_raw
    )
    medications = [
        {"name": m["medication_name"], "time": str(m["scheduled_time_of_day"])}
        for m in meds_raw
    ]
    shift = {
        "start": str(shift_row.scheduled_start_time),
        "end": str(shift_row.scheduled_end_time),
    }

    # Auto-fields: what the progress form pre-fills but the DSP never speaks.
    # /extract returns these straight to the frontend to populate form Sections 1-2.
    auto_fields = {
        "recipient_name": recipient.full_name,
        "medicaid_id": recipient.medicaid_id,
        "date_of_birth": str(recipient.date_of_birth),
        "primary_diagnosis_code": recipient.primary_diagnosis_code,
        "waiver_program": recipient.waiver_program,
        "service_location_name": shift_row.service_location_name,
        "dsp_name": shift_row.direct_support_professional_name,
        "scheduled_start_time": str(shift_row.scheduled_start_time),
        "scheduled_end_time": str(shift_row.scheduled_end_time),
        "service_billing_code": shift_row.service_billing_code,
    }

    return {
        "goals_text": goals_text,
        "goals_raw": goals_raw,
        "medications": medications,   # simple list — gap detection consumes this
        "meds_raw": meds_raw,         # full rows incl. medication_id — MAR writer consumes this
        "shift": shift,
        "care_recipient_id": str(care_recipient_id),
        "shift_assignment_id": str(shift_row.shift_assignment_id),
        "auto_fields": auto_fields,
    }
    
    
    
def create_care_session(session, row: dict) -> str:
    """Insert one documented_care_sessions row on the GIVEN ORM session (no commit).

    Shares the caller's session/transaction so the note and its MAR rows commit
    together. The model's column types handle the array/jsonb columns, so `row`
    carries plain Python lists/dicts — no ::uuid[] cast or Json() wrapper needed.
    session.flush() emits INSERT ... RETURNING, which populates the DB-generated
    care_session_id. Returns it as a str.
    """
    cs = DocumentedCareSession(**row)
    session.add(cs)
    session.flush()
    return str(cs.care_session_id)


def insert_mar_rows(session, care_session_id: str, mar_entries: list[dict]) -> int:
    """Insert one medication_administration_records row per dose on the GIVEN ORM
    session (no commit) — shares the note's transaction so both persist together.

    Each entry: medication_id, was_given (bool), admin_time (or None),
    reason_not_given (required when was_given is False). Enforces the
    reason-required-when-not-given rule first, so we fail with a clear error
    instead of a raw DB constraint violation. Returns the number of rows inserted.
    """
    for e in mar_entries:
        if not e["was_given"] and not e.get("reason_not_given"):
            raise ValueError(
                f"Medication {e['medication_id']} marked not given but no reason supplied; "
                "a reason is required when a dose is not administered."
            )

    session.add_all([
        MedicationAdministrationRecord(
            care_session_id=care_session_id,
            medication_id=e["medication_id"],
            was_medication_given=e["was_given"],
            actual_administration_time=e.get("admin_time"),
            reason_if_not_given=e.get("reason_not_given"),
        )
        for e in mar_entries
    ])
    return len(mar_entries)


def delete_care_session(care_session_id: str) -> None:
    """Delete one care session by id (used for test cleanup)."""
    with get_session() as session:
        session.execute(
            delete(DocumentedCareSession).where(
                DocumentedCareSession.care_session_id == care_session_id
            )
        )
        session.commit()
    
# if __name__ == "__main__":
#     import json
#     print(json.dumps(load_context("482910053"), indent=2))   # Marcus

def load_roster(dsp_name: str) -> list[dict]:
    """Return today's scheduled recipients for one DSP — the roster screen.

    Queries staff_shift_assignments (the DSP->recipient assignment for today)
    joined to care_recipients for display details. Returns ONLY the fields the
    roster screen needs: who, where, when. Goals/meds/narrative come later via
    /extract. Empty list if the DSP has no shifts today.

    ORM VERSION (Pipeline A migration POC). This is the SQLAlchemy ORM
    equivalent of the original raw-SQL query — same joins, same filters, same
    result shape. Things to notice vs the psycopg2 version:
      - No SQL string: select()/join()/where() build the query from the model
        classes, and SQLAlchemy generates the SQL (with bound params, so it's
        still injection-safe).
      - `func.current_date()` renders Postgres CURRENT_DATE.
      - `with get_session()` opens and (on exit) closes the session for us — no
        manual cursor.close()/conn.close().
      - Selecting individual columns gives Row objects we read by attribute
        (row.full_name), the ORM analog of RealDictCursor's row["..."].
    """
    stmt = (
        select(
            CareRecipient.full_name,
            CareRecipient.medicaid_id,
            ServiceLocation.service_location_name,
            StaffShiftAssignment.scheduled_start_time,
            StaffShiftAssignment.scheduled_end_time,
        )
        .select_from(StaffShiftAssignment)
        .join(
            CareRecipient,
            CareRecipient.care_recipient_id == StaffShiftAssignment.care_recipient_id,
        )
        .join(
            ServiceLocation,
            ServiceLocation.location_id == StaffShiftAssignment.location_id,
        )
        .where(
            StaffShiftAssignment.direct_support_professional_name == dsp_name,
            StaffShiftAssignment.shift_date == func.current_date(),
        )
        .order_by(StaffShiftAssignment.scheduled_start_time)
    )

    with get_session() as session:
        rows = session.execute(stmt).all()

    # JSON-safe: times come back as time objects.
    return [
        {
            "recipient_name": row.full_name,
            "medicaid_id": row.medicaid_id,
            "service_location_name": row.service_location_name,
            "scheduled_start_time": str(row.scheduled_start_time),
            "scheduled_end_time": str(row.scheduled_end_time),
        }
        for row in rows
    ]
