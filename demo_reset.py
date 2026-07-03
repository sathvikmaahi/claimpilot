"""
Demo DB reset script.

Final state after running:
  NEEDS ATTENTION:  2 (Marcus Reyes, pre-existing failed)
  READY TO REVIEW:  0
  SUBMITTED:        1 (Robert Kim confirmed)
  PAYER REJECTED:   5 (Fizah, Denise, Priya, Tyrone, Marcus — all clean)
  UNPROCESSED:      3 sessions (Linda w/ GPS, James Carter no GPS, Maria Santos no GPS)

When Process Claims is clicked:
  → Linda Martinez passes all checks → Ready to Review
  → James Carter fails Check 4 (no GPS) → Needs Attention
  → Maria Santos fails Check 4 (no GPS) → Needs Attention
"""
import asyncio
import uuid
import asyncpg

DB = dict(
    host="34.27.194.50", port=5432,
    user="postgres", password="v3bYlE`ziqMmhVF(",
    database="claimpilot", ssl="require"
)

LOCATION_ID = uuid.UUID("7356ac26-b1e6-4259-9de1-ab7929a2f43e")

# 2 Marcus Reyes failed claims to KEEP
KEEP_FAILED = {
    uuid.UUID("af12b9ca-6e0d-4592-bac3-25731328d579"),
    uuid.UUID("79d20813-1153-4099-9d7e-036bb576cc7c"),
}

# 1 Robert Kim confirmed claim to KEEP
KEEP_CONFIRMED = uuid.UUID("174d614b-7cd7-48cf-9958-ac374a2d70b0")

# 5 rejected claims to RESET (not delete)
RESET_REJECTED = [
    uuid.UUID("b1c2d3e4-0001-4a1a-9c1a-ee0000000001"),  # Fizah Johnson
    uuid.UUID("b1c2d3e4-0002-4a1a-9c1a-ee0000000002"),  # Marcus Reyes
    uuid.UUID("b1c2d3e4-0003-4a1a-9c1a-ee0000000003"),  # Denise Coleman
    uuid.UUID("b1c2d3e4-0004-4a1a-9c1a-ee0000000004"),  # Tyrone Banks
    uuid.UUID("b1c2d3e4-0005-4a1a-9c1a-ee0000000005"),  # Priya Patel
]

# Linda session to add GPS to (exists, no claim yet)
LINDA_SESSION = uuid.UUID("f815490e-61b8-41b7-90e3-6087d7626214")

# Linda shift assignment to use for her session (2026-07-03 already linked to LINDA_SESSION)
# We'll update the existing session instead of creating a new one


async def main():
    conn = await asyncpg.connect(**DB)

    print("=" * 60)
    print("DEMO DB RESET")
    print("=" * 60)

    async with conn.transaction():

        # ── Step 1: Identify claims to DELETE ───────────────────────
        print("\n[1/9] Identifying claims to delete...")

        # All failed claims except the 2 kept Marcus Reyes
        failed_to_delete = await conn.fetch("""
            SELECT c.claim_id, c.service_event_id AS session_id
            FROM claims c
            WHERE c.claim_status = 'failed'
            AND c.claim_id != ALL($1)
        """, list(KEEP_FAILED))
        print(f"     Failed claims to delete: {len(failed_to_delete)}")

        # Confirmed/resubmitted claims that are NOT the 5 resets and NOT the kept Robert Kim
        extra_confirmed = await conn.fetch("""
            SELECT c.claim_id, c.service_event_id AS session_id
            FROM claims c
            WHERE c.claim_status IN ('confirmed', 'submitted', 'resubmitted')
            AND c.claim_id != $1
            AND c.claim_id != ALL($2)
        """, KEEP_CONFIRMED, RESET_REJECTED)
        print(f"     Extra confirmed/resubmitted claims to delete: {len(extra_confirmed)}")

        all_delete_ids = [r["claim_id"] for r in failed_to_delete] + [r["claim_id"] for r in extra_confirmed]
        # For session cleanup: only delete sessions from failed claims (not from confirmed, which may be shared)
        failed_session_ids = [r["session_id"] for r in failed_to_delete]
        # For confirmed, only delete the Robert Kim extra session (e3998e14) — it's unique
        robert_extra_sessions = [r["session_id"] for r in extra_confirmed
                                  if r["claim_id"] != uuid.UUID("b1c2d3e4-0001-4a1a-9c1a-ee0000000001")
                                  and r["claim_id"] != uuid.UUID("b1c2d3e4-0002-4a1a-9c1a-ee0000000002")]
        sessions_to_delete = failed_session_ids + robert_extra_sessions

        # ── Step 2: NULL out resubmitted_claim_id references ────────
        print("\n[2/9] Clearing resubmitted_claim_id pointers to claims being deleted...")
        n = await conn.execute("""
            UPDATE claim_rejections
            SET resubmitted_claim_id = NULL
            WHERE resubmitted_claim_id = ANY($1)
        """, all_delete_ids)
        print(f"     Updated: {n}")

        # ── Step 3: Delete claim_fields for claims being deleted ─────
        print("\n[3/9] Deleting claim_fields records...")
        n = await conn.execute("""
            DELETE FROM claim_fields WHERE claim_id = ANY($1)
        """, all_delete_ids)
        print(f"     Deleted: {n}")

        # ── Step 4: Delete claim_rejections for claims being deleted ─
        print("\n[4/9] Deleting claim_rejection rows for deleted claims...")
        n = await conn.execute("""
            DELETE FROM claim_rejections WHERE claim_id = ANY($1)
        """, all_delete_ids)
        print(f"     Deleted: {n}")

        # ── Step 5: Delete the claims themselves ─────────────────────
        print("\n[5/9] Deleting claims...")
        n = await conn.execute("""
            DELETE FROM claims WHERE claim_id = ANY($1)
        """, all_delete_ids)
        print(f"     Deleted: {n}")

        # ── Step 6: Delete orphaned care sessions ────────────────────
        print("\n[6/9] Deleting care sessions (no remaining claim references)...")
        n = await conn.execute("""
            DELETE FROM documented_care_sessions
            WHERE care_session_id = ANY($1)
            AND care_session_id NOT IN (SELECT service_event_id FROM claims)
        """, sessions_to_delete)
        print(f"     Deleted: {n}")

        # ── Step 7: Reset 5 rejected claims ─────────────────────────
        print("\n[7/9] Resetting 5 rejected claims to clean state...")
        n = await conn.execute("""
            UPDATE claims
            SET claim_status = 'rejected'
            WHERE claim_id = ANY($1)
        """, RESET_REJECTED)
        print(f"     Claims reset: {n}")

        n = await conn.execute("""
            UPDATE claim_rejections
            SET resolution_status = 'pending',
                resolution_action = NULL,
                triage_agent_output = NULL,
                resubmitted_claim_id = NULL,
                appeal_packet_text = NULL,
                resolved_by = NULL,
                resolved_at = NULL
            WHERE claim_id = ANY($1)
        """, RESET_REJECTED)
        print(f"     Rejection rows reset: {n}")

        # ── Step 8: Update Linda's session to add GPS ────────────────
        print("\n[8/9] Adding GPS to Linda Martinez's unprocessed session...")
        n = await conn.execute("""
            UPDATE documented_care_sessions
            SET checkin_location_latitude  = 39.099728,
                checkin_location_longitude = -94.578568,
                checkout_location_latitude  = 39.099728,
                checkout_location_longitude = -94.578568
            WHERE care_session_id = $1
        """, LINDA_SESSION)
        print(f"     Updated: {n}")

        # ── Step 9: Create James Carter + Maria Santos sessions ───────
        print("\n[9/9] Creating James Carter and Maria Santos care records...")

        # James Carter
        james_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO care_recipients
              (care_recipient_id, full_name, medicaid_id, date_of_birth,
               waiver_program, primary_diagnosis_code, sex)
            VALUES ($1, 'James Carter', 'JC100007', '1985-03-22',
                    'Comprehensive', 'F70', 'M')
        """, james_id)

        james_sa_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO staff_shift_assignments
              (shift_assignment_id, care_recipient_id, direct_support_professional_name,
               shift_date, scheduled_start_time, scheduled_end_time,
               service_billing_code, location_id)
            VALUES ($1, $2, 'Jordan Williams', '2026-07-03',
                    '08:00', '16:00', 'T2016', $3)
        """, james_sa_id, james_id, LOCATION_ID)

        james_sess_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO documented_care_sessions
              (care_session_id, shift_assignment_id, care_recipient_id,
               actual_clock_in_time, actual_clock_out_time,
               total_duration_minutes, billable_units_calculated,
               care_session_narrative, level_of_support_provided,
               recipient_engagement_notes, dsp_has_signed, session_status,
               record_created_at, record_updated_at)
            VALUES ($1, $2, $3,
                    '2026-07-03 08:00:00+00', '2026-07-03 16:00:00+00',
                    480, 32,
                    'Supported James with daily living activities including morning routine, meal preparation, and community integration. James was cooperative and engaged throughout the shift.',
                    'full_support',
                    'James participated actively in all activities. He showed enthusiasm during community outing and completed morning tasks with minimal prompting.',
                    true, 'submitted_by_dsp', now(), now())
        """, james_sess_id, james_sa_id, james_id)
        print(f"     James Carter: care_recipient={james_id}, session={james_sess_id}")

        # Maria Santos
        maria_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO care_recipients
              (care_recipient_id, full_name, medicaid_id, date_of_birth,
               waiver_program, primary_diagnosis_code, sex)
            VALUES ($1, 'Maria Santos', 'MS100008', '1978-09-15',
                    'Comprehensive', 'F71', 'F')
        """, maria_id)

        maria_sa_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO staff_shift_assignments
              (shift_assignment_id, care_recipient_id, direct_support_professional_name,
               shift_date, scheduled_start_time, scheduled_end_time,
               service_billing_code, location_id)
            VALUES ($1, $2, 'Jordan Williams', '2026-07-03',
                    '09:00', '17:00', 'T2016', $3)
        """, maria_sa_id, maria_id, LOCATION_ID)

        maria_sess_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO documented_care_sessions
              (care_session_id, shift_assignment_id, care_recipient_id,
               actual_clock_in_time, actual_clock_out_time,
               total_duration_minutes, billable_units_calculated,
               care_session_narrative, level_of_support_provided,
               recipient_engagement_notes, dsp_has_signed, session_status,
               record_created_at, record_updated_at)
            VALUES ($1, $2, $3,
                    '2026-07-03 09:00:00+00', '2026-07-03 17:00:00+00',
                    480, 32,
                    'Maria had a productive shift. Staff assisted with personal care, medication management, and skill-building activities. Maria enjoyed the afternoon art activity and completed her morning hygiene routine independently.',
                    'full_support',
                    'Maria was engaged and positive throughout the shift. She communicated her needs effectively and smiled frequently during activities.',
                    true, 'submitted_by_dsp', now(), now())
        """, maria_sess_id, maria_sa_id, maria_id)
        print(f"     Maria Santos: care_recipient={maria_id}, session={maria_sess_id}")

    # ── Verify final state ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    counts = await conn.fetchrow("""
        SELECT
          (SELECT count(*) FROM claims WHERE claim_status = 'failed') AS failed,
          (SELECT count(*) FROM claims WHERE claim_status IN ('confirmed', 'submitted')) AS submitted,
          (SELECT count(*) FROM claims WHERE claim_status IN ('rejected', 'appeal_submitted', 'written_off')) AS rejected,
          (SELECT count(*) FROM documented_care_sessions
           WHERE care_session_id NOT IN (SELECT service_event_id FROM claims)) AS unprocessed
    """)
    print(f"  NEEDS ATTENTION (failed):   {counts['failed']}  (expect 2)")
    print(f"  SUBMITTED (confirmed):      {counts['submitted']}  (expect 1)")
    print(f"  PAYER REJECTED:             {counts['rejected']}  (expect 5)")
    print(f"  UNPROCESSED sessions:       {counts['unprocessed']}  (expect 3)")

    # Show names
    failed_names = await conn.fetch("""
        SELECT r.full_name, c.claim_id, c.created_at
        FROM claims c
        JOIN documented_care_sessions cs ON cs.care_session_id = c.service_event_id
        JOIN care_recipients r ON r.care_recipient_id = cs.care_recipient_id
        WHERE c.claim_status = 'failed'
        ORDER BY r.full_name
    """)
    print("\n  Failed claims:")
    for row in failed_names:
        print(f"    - {row['full_name']} ({str(row['claim_id'])[:8]})")

    submitted_names = await conn.fetch("""
        SELECT r.full_name, c.claim_id, c.claim_status
        FROM claims c
        JOIN documented_care_sessions cs ON cs.care_session_id = c.service_event_id
        JOIN care_recipients r ON r.care_recipient_id = cs.care_recipient_id
        WHERE c.claim_status IN ('confirmed', 'submitted')
        ORDER BY r.full_name
    """)
    print("\n  Submitted claims:")
    for row in submitted_names:
        print(f"    - {row['full_name']} ({row['claim_status']})")

    rejected_names = await conn.fetch("""
        SELECT r.full_name, c.claim_id, c.claim_status
        FROM claims c
        JOIN documented_care_sessions cs ON cs.care_session_id = c.service_event_id
        JOIN care_recipients r ON r.care_recipient_id = cs.care_recipient_id
        WHERE c.claim_status IN ('rejected', 'appeal_submitted', 'written_off')
        ORDER BY r.full_name
    """)
    print("\n  Rejected claims:")
    for row in rejected_names:
        print(f"    - {row['full_name']} ({row['claim_status']})")

    unprocessed_names = await conn.fetch("""
        SELECT r.full_name, cs.care_session_id,
               cs.checkin_location_latitude IS NOT NULL AS has_gps
        FROM documented_care_sessions cs
        JOIN care_recipients r ON r.care_recipient_id = cs.care_recipient_id
        WHERE cs.care_session_id NOT IN (SELECT service_event_id FROM claims)
        ORDER BY r.full_name
    """)
    print("\n  Unprocessed sessions (will be picked up by Process Claims):")
    for row in unprocessed_names:
        gps_str = "WITH GPS → Ready to Review" if row["has_gps"] else "NO GPS → Needs Attention"
        print(f"    - {row['full_name']} ({gps_str})")

    await conn.close()
    print("\nDone!\n")


asyncio.run(main())
