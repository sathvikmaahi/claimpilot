--
-- PostgreSQL database dump
--

\restrict CTh2IMRrrh3iq5QSMUQzBo8r8wbej3ZEMmhLxY2KQGtbsRA9dsxOH9u1HVfs1B1

-- Dumped from database version 16.14
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: update_record_updated_at_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_record_updated_at_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
  new.record_updated_at = now();
  return new;
end;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: care_recipients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.care_recipients (
    care_recipient_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    full_name text NOT NULL,
    medicaid_id text NOT NULL,
    date_of_birth date NOT NULL,
    waiver_program text DEFAULT 'Comprehensive'::text NOT NULL,
    primary_diagnosis_code text NOT NULL,
    sex character(1) NOT NULL,  -- 'M', 'F', or 'U'; required by Pipeline B for the claim
    record_created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT care_recipients_sex_check CHECK (sex IN ('M', 'F', 'U'))
);


--
-- Name: service_locations; Type: TABLE; Schema: public; Owner: -
-- Billing attributes per service location. Source of rendering_npi + modifiers
-- that Pipeline B uses for the claim. Not shown to the DSP.
--

CREATE TABLE public.service_locations (
    location_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    service_location_name text NOT NULL,
    rendering_npi character varying(10) NOT NULL,
    modifier_1 character varying(10) NOT NULL,
    modifier_2 character varying(10),
    modifier_3 character varying(10),
    record_created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: documented_care_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documented_care_sessions (
    care_session_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    shift_assignment_id uuid NOT NULL,
    care_recipient_id uuid NOT NULL,
    actual_clock_in_time timestamp with time zone,
    actual_clock_out_time timestamp with time zone,
    total_duration_minutes integer,
    billable_units_calculated integer,
    care_session_narrative text,
    activities_performed text[],
    level_of_support_provided text,
    recipient_engagement_notes text,
    health_observations_notes text,
    behavioral_observations_notes text,
    community_outing_notes text,
    meals_provided text[],
    personal_care_activities text[],
    goals_addressed_in_session uuid[],
    checkin_location_latitude numeric(9,6),
    checkin_location_longitude numeric(9,6),
    checkout_location_latitude numeric(9,6),
    checkout_location_longitude numeric(9,6),
    ai_confidence_rating text,  -- agent confidence as a 0.0-1.0 score, stored as text (was High/Medium/Low)
    documentation_gap_flags text[],
    dsp_has_signed boolean DEFAULT false NOT NULL,
    session_status text DEFAULT 'in_progress'::text NOT NULL,
    record_created_at timestamp with time zone DEFAULT now() NOT NULL,
    record_updated_at timestamp with time zone DEFAULT now() NOT NULL,
    goals_resolution jsonb,
    CONSTRAINT documented_care_sessions_level_of_support_provided_check CHECK ((level_of_support_provided = ANY (ARRAY['independent'::text, 'verbal_prompts'::text, 'physical_assistance'::text, 'full_support'::text]))),
    CONSTRAINT documented_care_sessions_session_status_check CHECK ((session_status = ANY (ARRAY['in_progress'::text, 'submitted_by_dsp'::text, 'ready_for_billing'::text])))
);


--
-- Name: medicaid_billing_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medicaid_billing_claims (
    billing_claim_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    care_session_id uuid NOT NULL,
    service_procedure_code text DEFAULT 'T2016'::text NOT NULL,
    service_modifier_code text,
    total_units_billed integer NOT NULL,
    total_billed_amount_usd numeric(10,2) NOT NULL,
    claim_status text DEFAULT 'built'::text NOT NULL,
    date_submitted_to_medicaid date,
    record_created_at timestamp with time zone DEFAULT now() NOT NULL,
    record_updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT medicaid_billing_claims_claim_status_check CHECK ((claim_status = ANY (ARRAY['built'::text, 'submitted_to_medicaid'::text, 'accepted'::text, 'denied'::text, 'paid'::text])))
);


--
-- Name: medication_administration_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medication_administration_records (
    administration_record_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    care_session_id uuid NOT NULL,
    medication_id uuid NOT NULL,
    was_medication_given boolean NOT NULL,
    actual_administration_time timestamp with time zone,
    reason_if_not_given text,
    record_created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reason_required_when_not_given CHECK (((was_medication_given = true) OR ((was_medication_given = false) AND (reason_if_not_given IS NOT NULL))))
);


--
-- Name: prescribed_medications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prescribed_medications (
    medication_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    care_recipient_id uuid NOT NULL,
    medication_name text NOT NULL,
    dosage_amount text NOT NULL,
    administration_route text NOT NULL,
    scheduled_time_of_day time without time zone NOT NULL,
    is_currently_active boolean DEFAULT true NOT NULL,
    record_created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: staff_shift_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_shift_assignments (
    shift_assignment_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    care_recipient_id uuid NOT NULL,
    direct_support_professional_name text NOT NULL,
    location_id uuid NOT NULL,
    shift_date date NOT NULL,
    scheduled_start_time time without time zone NOT NULL,
    scheduled_end_time time without time zone NOT NULL,
    service_billing_code text DEFAULT 'T2016'::text NOT NULL,
    record_created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: support_plan_goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_plan_goals (
    goal_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    care_recipient_id uuid NOT NULL,
    goal_category text NOT NULL,
    goal_description text NOT NULL,
    is_currently_active boolean DEFAULT true NOT NULL,
    record_created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT support_plan_goals_goal_category_check CHECK ((goal_category = ANY (ARRAY['daily_living'::text, 'community_integration'::text, 'health_and_safety'::text, 'employment'::text, 'social_skills'::text])))
);


--
-- Name: care_recipients care_recipients_medicaid_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_recipients
    ADD CONSTRAINT care_recipients_medicaid_id_key UNIQUE (medicaid_id);


--
-- Name: care_recipients care_recipients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_recipients
    ADD CONSTRAINT care_recipients_pkey PRIMARY KEY (care_recipient_id);


--
-- Name: documented_care_sessions documented_care_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documented_care_sessions
    ADD CONSTRAINT documented_care_sessions_pkey PRIMARY KEY (care_session_id);


--
-- Name: medicaid_billing_claims medicaid_billing_claims_care_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medicaid_billing_claims
    ADD CONSTRAINT medicaid_billing_claims_care_session_id_key UNIQUE (care_session_id);


--
-- Name: medicaid_billing_claims medicaid_billing_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medicaid_billing_claims
    ADD CONSTRAINT medicaid_billing_claims_pkey PRIMARY KEY (billing_claim_id);


--
-- Name: medication_administration_records medication_administration_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medication_administration_records
    ADD CONSTRAINT medication_administration_records_pkey PRIMARY KEY (administration_record_id);


--
-- Name: prescribed_medications prescribed_medications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescribed_medications
    ADD CONSTRAINT prescribed_medications_pkey PRIMARY KEY (medication_id);


--
-- Name: staff_shift_assignments staff_shift_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_shift_assignments
    ADD CONSTRAINT staff_shift_assignments_pkey PRIMARY KEY (shift_assignment_id);


--
-- Name: service_locations service_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_locations
    ADD CONSTRAINT service_locations_pkey PRIMARY KEY (location_id);


--
-- Name: service_locations service_locations_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_locations
    ADD CONSTRAINT service_locations_name_key UNIQUE (service_location_name);


--
-- Name: support_plan_goals support_plan_goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_plan_goals
    ADD CONSTRAINT support_plan_goals_pkey PRIMARY KEY (goal_id);


--
-- Name: idx_billing_claims_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_billing_claims_session ON public.medicaid_billing_claims USING btree (care_session_id);


--
-- Name: idx_billing_claims_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_billing_claims_status ON public.medicaid_billing_claims USING btree (claim_status);


--
-- Name: idx_care_recipients_medicaid_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_care_recipients_medicaid_id ON public.care_recipients USING btree (medicaid_id);


--
-- Name: idx_care_sessions_assignment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_care_sessions_assignment ON public.documented_care_sessions USING btree (shift_assignment_id);


--
-- Name: idx_care_sessions_clockin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_care_sessions_clockin ON public.documented_care_sessions USING btree (actual_clock_in_time);


--
-- Name: idx_care_sessions_recipient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_care_sessions_recipient ON public.documented_care_sessions USING btree (care_recipient_id);


--
-- Name: idx_care_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_care_sessions_status ON public.documented_care_sessions USING btree (session_status);


--
-- Name: idx_med_records_medication; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_med_records_medication ON public.medication_administration_records USING btree (medication_id);


--
-- Name: idx_med_records_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_med_records_session ON public.medication_administration_records USING btree (care_session_id);


--
-- Name: idx_prescribed_medications_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prescribed_medications_active ON public.prescribed_medications USING btree (care_recipient_id, is_currently_active);


--
-- Name: idx_prescribed_medications_recipient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prescribed_medications_recipient ON public.prescribed_medications USING btree (care_recipient_id);


--
-- Name: idx_shift_assignments_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_shift_assignments_date ON public.staff_shift_assignments USING btree (shift_date);


--
-- Name: idx_shift_assignments_dsp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_shift_assignments_dsp ON public.staff_shift_assignments USING btree (direct_support_professional_name);


--
-- Name: idx_shift_assignments_recipient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_shift_assignments_recipient ON public.staff_shift_assignments USING btree (care_recipient_id);


--
-- Name: idx_support_plan_goals_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_support_plan_goals_active ON public.support_plan_goals USING btree (care_recipient_id, is_currently_active);


--
-- Name: idx_support_plan_goals_recipient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_support_plan_goals_recipient ON public.support_plan_goals USING btree (care_recipient_id);


--
-- Name: medicaid_billing_claims trg_billing_claims_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_billing_claims_updated_at BEFORE UPDATE ON public.medicaid_billing_claims FOR EACH ROW EXECUTE FUNCTION public.update_record_updated_at_timestamp();


--
-- Name: documented_care_sessions trg_care_sessions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_care_sessions_updated_at BEFORE UPDATE ON public.documented_care_sessions FOR EACH ROW EXECUTE FUNCTION public.update_record_updated_at_timestamp();


--
-- Name: documented_care_sessions documented_care_sessions_care_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documented_care_sessions
    ADD CONSTRAINT documented_care_sessions_care_recipient_id_fkey FOREIGN KEY (care_recipient_id) REFERENCES public.care_recipients(care_recipient_id) ON DELETE RESTRICT;


--
-- Name: documented_care_sessions documented_care_sessions_shift_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documented_care_sessions
    ADD CONSTRAINT documented_care_sessions_shift_assignment_id_fkey FOREIGN KEY (shift_assignment_id) REFERENCES public.staff_shift_assignments(shift_assignment_id) ON DELETE RESTRICT;


--
-- Name: medicaid_billing_claims medicaid_billing_claims_care_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medicaid_billing_claims
    ADD CONSTRAINT medicaid_billing_claims_care_session_id_fkey FOREIGN KEY (care_session_id) REFERENCES public.documented_care_sessions(care_session_id) ON DELETE RESTRICT;


--
-- Name: medication_administration_records medication_administration_records_care_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medication_administration_records
    ADD CONSTRAINT medication_administration_records_care_session_id_fkey FOREIGN KEY (care_session_id) REFERENCES public.documented_care_sessions(care_session_id) ON DELETE CASCADE;


--
-- Name: medication_administration_records medication_administration_records_medication_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medication_administration_records
    ADD CONSTRAINT medication_administration_records_medication_id_fkey FOREIGN KEY (medication_id) REFERENCES public.prescribed_medications(medication_id) ON DELETE RESTRICT;


--
-- Name: prescribed_medications prescribed_medications_care_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescribed_medications
    ADD CONSTRAINT prescribed_medications_care_recipient_id_fkey FOREIGN KEY (care_recipient_id) REFERENCES public.care_recipients(care_recipient_id) ON DELETE CASCADE;


--
-- Name: staff_shift_assignments staff_shift_assignments_care_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_shift_assignments
    ADD CONSTRAINT staff_shift_assignments_care_recipient_id_fkey FOREIGN KEY (care_recipient_id) REFERENCES public.care_recipients(care_recipient_id) ON DELETE CASCADE;


--
-- Name: staff_shift_assignments staff_shift_assignments_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_shift_assignments
    ADD CONSTRAINT staff_shift_assignments_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.service_locations(location_id) ON DELETE RESTRICT;


--
-- Name: support_plan_goals support_plan_goals_care_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_plan_goals
    ADD CONSTRAINT support_plan_goals_care_recipient_id_fkey FOREIGN KEY (care_recipient_id) REFERENCES public.care_recipients(care_recipient_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict CTh2IMRrrh3iq5QSMUQzBo8r8wbej3ZEMmhLxY2KQGtbsRA9dsxOH9u1HVfs1B1

