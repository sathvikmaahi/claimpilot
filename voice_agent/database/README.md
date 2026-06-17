## 3. THE SEVEN-TABLE SCHEMA

The schema is intentionally minimal — seven tables is the smallest set that covers the end-to-end flow from "DSP arrives at the home" to "claim submitted to Medicaid." Every table earned its place.

### Three layers

**Reference layer (pre-populated, queried often, updated rarely):**
- `care_recipients` — the people receiving services
- `support_plan_goals` — their authorized goals
- `prescribed_medications` — their standing medications
- `staff_shift_assignments` — planned shifts (who supports whom, when, where)

**Capture layer (written during/after a shift):**
- `documented_care_sessions` — the documented shift = the progress note
- `medication_administration_records` — the MAR rows (one per dose)

**Output layer (derived for billing):**
- `medicaid_billing_claims` — the billable claim derived from each session

### The connecting key: `care_recipient_id`

The schema is anchored on `care_recipient_id`. Every other table either holds this column directly or reaches it through one foreign-key hop. The product itself is "ClaimPilot's view of a single care recipient" — the schema mirrors that focus.

### Full schema

```sql
-- ============================================================
-- ClaimPilot AI — Pipeline A Database Schema
-- ============================================================

create extension if not exists "uuid-ossp";


-- TABLE 1: care_recipients
create table care_recipients (
  care_recipient_id        uuid         primary key default uuid_generate_v4(),
  full_name                text         not null,
  medicaid_id              text         not null unique,
  date_of_birth            date         not null,
  waiver_program           text         not null default 'Comprehensive',
  primary_diagnosis_code   text         not null,
  record_created_at        timestamptz  not null default now()
);
create index idx_care_recipients_medicaid_id on care_recipients(medicaid_id);


-- TABLE 2: support_plan_goals
create table support_plan_goals (
  goal_id                  uuid         primary key default uuid_generate_v4(),
  care_recipient_id        uuid         not null references care_recipients(care_recipient_id) on delete cascade,
  goal_category            text         not null check (goal_category in
                             ('daily_living', 'community_integration', 'health_and_safety',
                              'employment', 'social_skills')),
  goal_description         text         not null,
  is_currently_active      boolean      not null default true,
  record_created_at        timestamptz  not null default now()
);
create index idx_support_plan_goals_recipient on support_plan_goals(care_recipient_id);
create index idx_support_plan_goals_active on support_plan_goals(care_recipient_id, is_currently_active);


-- TABLE 3: prescribed_medications
create table prescribed_medications (
  medication_id            uuid         primary key default uuid_generate_v4(),
  care_recipient_id        uuid         not null references care_recipients(care_recipient_id) on delete cascade,
  medication_name          text         not null,
  dosage_amount            text         not null,
  administration_route     text         not null,
  scheduled_time_of_day    time         not null,
  is_currently_active      boolean      not null default true,
  record_created_at        timestamptz  not null default now()
);
create index idx_prescribed_medications_recipient on prescribed_medications(care_recipient_id);
create index idx_prescribed_medications_active on prescribed_medications(care_recipient_id, is_currently_active);


-- TABLE 4: staff_shift_assignments
create table staff_shift_assignments (
  shift_assignment_id              uuid         primary key default uuid_generate_v4(),
  care_recipient_id                uuid         not null references care_recipients(care_recipient_id) on delete cascade,
  direct_support_professional_name text         not null,
  service_location_name            text         not null,
  shift_date                       date         not null,
  scheduled_start_time             time         not null,
  scheduled_end_time               time         not null,
  service_billing_code             text         not null default 'T2016',
  record_created_at                timestamptz  not null default now()
);
create index idx_shift_assignments_recipient on staff_shift_assignments(care_recipient_id);
create index idx_shift_assignments_date on staff_shift_assignments(shift_date);
create index idx_shift_assignments_dsp on staff_shift_assignments(direct_support_professional_name);


-- TABLE 5: documented_care_sessions (the progress note)
create table documented_care_sessions (
  care_session_id                      uuid         primary key default uuid_generate_v4(),
  shift_assignment_id                  uuid         not null references staff_shift_assignments(shift_assignment_id) on delete restrict,
  care_recipient_id                    uuid         not null references care_recipients(care_recipient_id) on delete restrict,
  actual_clock_in_time                 timestamptz,
  actual_clock_out_time                timestamptz,
  total_duration_minutes               integer,
  billable_units_calculated            integer,
  care_session_narrative               text,
  activities_performed                 text[],
  level_of_support_provided            text         check (level_of_support_provided in
                                         ('independent', 'verbal_prompts', 'physical_assistance', 'full_support')),
  recipient_engagement_notes           text,
  health_observations_notes            text,
  behavioral_observations_notes        text,
  community_outing_notes               text,
  meals_provided                       text[],
  personal_care_activities             text[],
  goals_addressed_in_session           uuid[],
  checkin_location_latitude            numeric(9, 6),
  checkin_location_longitude           numeric(9, 6),
  checkout_location_latitude           numeric(9, 6),
  checkout_location_longitude          numeric(9, 6),
  ai_confidence_rating                 text         check (ai_confidence_rating in ('High', 'Medium', 'Low')),
  documentation_gap_flags              text[],
  dsp_has_signed                       boolean      not null default false,
  session_status                       text         not null default 'in_progress'
                                         check (session_status in
                                           ('in_progress', 'submitted_by_dsp', 'ready_for_billing')),
  record_created_at                    timestamptz  not null default now(),
  record_updated_at                    timestamptz  not null default now()
);
create index idx_care_sessions_recipient on documented_care_sessions(care_recipient_id);
create index idx_care_sessions_assignment on documented_care_sessions(shift_assignment_id);
create index idx_care_sessions_status on documented_care_sessions(session_status);
create index idx_care_sessions_clockin on documented_care_sessions(actual_clock_in_time);


-- TABLE 6: medication_administration_records
create table medication_administration_records (
  administration_record_id     uuid         primary key default uuid_generate_v4(),
  care_session_id              uuid         not null references documented_care_sessions(care_session_id) on delete cascade,
  medication_id                uuid         not null references prescribed_medications(medication_id) on delete restrict,
  was_medication_given         boolean      not null,
  actual_administration_time   timestamptz,
  reason_if_not_given          text,
  record_created_at            timestamptz  not null default now(),
  constraint reason_required_when_not_given
    check ((was_medication_given = true)
        or (was_medication_given = false and reason_if_not_given is not null))
);
create index idx_med_records_session on medication_administration_records(care_session_id);
create index idx_med_records_medication on medication_administration_records(medication_id);


-- TABLE 7: medicaid_billing_claims
create table medicaid_billing_claims (
  billing_claim_id              uuid         primary key default uuid_generate_v4(),
  care_session_id               uuid         not null unique references documented_care_sessions(care_session_id) on delete restrict,
  service_procedure_code        text         not null default 'T2016',
  service_modifier_code         text,
  total_units_billed            integer      not null,
  total_billed_amount_usd       numeric(10, 2) not null,
  claim_status                  text         not null default 'built'
                                  check (claim_status in
                                    ('built', 'submitted_to_medicaid', 'accepted', 'denied', 'paid')),
  date_submitted_to_medicaid    date,
  record_created_at             timestamptz  not null default now(),
  record_updated_at             timestamptz  not null default now()
);
create index idx_billing_claims_session on medicaid_billing_claims(care_session_id);
create index idx_billing_claims_status on medicaid_billing_claims(claim_status);
