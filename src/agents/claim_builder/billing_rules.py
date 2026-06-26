"""
837P billing rules for Life Unlimited, Inc. — ISL Residential (T2016) claims.

All constants here are read by the Claim Builder agent at runtime.
The LLM never invents these values — it reads them from this file.

Values marked TODO must be confirmed against the MO HealthNet companion guide
before submitting live claims.
"""

# ---------------------------------------------------------------------------
# Procedure code
# ---------------------------------------------------------------------------
PROCEDURE_CODE = "T2016"                  # ISL Residential Habilitation
PROCEDURE_CODE_QUALIFIER = "HC"           # Health Care Financing Administration Common Procedure Coding System

# ---------------------------------------------------------------------------
# 837P Claim Filing Indicator (Loop 2000B SBR09)
# ---------------------------------------------------------------------------
CLAIM_FILING_INDICATOR = "MC"             # Medicaid

# ---------------------------------------------------------------------------
# Place of Service (Loop 2300 CLM05-1)
# ---------------------------------------------------------------------------
PLACE_OF_SERVICE_CODE = "12"             # Home — ISL residential setting
# TODO: confirm with MO HealthNet companion guide (may require 99 for ISL)

# ---------------------------------------------------------------------------
# Facility Code Qualifier (Loop 2300 CLM05-2) and Claim Frequency (CLM05-3)
# ---------------------------------------------------------------------------
FACILITY_CODE_QUALIFIER = "B"            # Off Campus-Outpatient Hospital (standard for community-based)
CLAIM_FREQUENCY_CODE = "1"               # Original claim

# ---------------------------------------------------------------------------
# Taxonomy code (Loop 2000A PRV03 and Loop 2310B PRV03)
# ---------------------------------------------------------------------------
BILLING_PROVIDER_TAXONOMY = "251G00000X"  # Residential Treatment — DD waiver
# TODO: confirm exact taxonomy with Life Unlimited's credentialing team

# ---------------------------------------------------------------------------
# Subscriber relationship to patient (Loop 2000B SBR02)
# ---------------------------------------------------------------------------
SUBSCRIBER_RELATIONSHIP = "18"            # Self (Medicaid recipient is the subscriber)

# ---------------------------------------------------------------------------
# Valid modifiers for T2016 ISL claims
# Modifier U1 is Missouri-specific for DD waiver residential habilitation.
# ---------------------------------------------------------------------------
VALID_MODIFIERS = {
    "U1": "Missouri DD waiver — required on all T2016 ISL claims",
    "U5": "Individual waiver",
    "HQ": "Group setting",
    "TT": "Multi-therapy",
}

# ---------------------------------------------------------------------------
# 837P loop → EnrichedServiceEvent field mapping
# Used by the agent as a reference when building each segment.
# ---------------------------------------------------------------------------
FIELD_MAP = {
    # Loop 2000A — Billing Provider (values come from config.py Settings)
    "billing_provider_npi":    "settings.billing_npi",       # NM109 (XX qualifier)
    "billing_provider_ein":    "settings.tax_id",            # REF*EI

    # Loop 2000B — Subscriber
    "subscriber_medicaid_id":  "event.participant_dcn",       # NM109
    "subscriber_name":         "event.participant_name",      # NM103 (last) / NM104 (first)
    "subscriber_dob":          "event.participant_dob",       # DMG02
    "subscriber_sex":          "event.sex",                   # DMG03

    # Loop 2300 — Claim
    "claim_service_date":      "event.service_date",          # DTP*472
    "claim_diagnosis_code":    "event.diagnosis_code",        # HI*ABK (ICD-10)
    "claim_billed_amount":     "computed: service_units × settings.t2016_fee_schedule_rate",
    "claim_service_units":     "event.service_units",         # SV103

    # Loop 2310B — Rendering Provider
    "rendering_provider_npi":  "event.rendering_npi",         # NM109 (XX qualifier)

    # Loop 2400 — Service Line
    "procedure_code":          "event.procedure_code",        # SV101 HC qualifier
    "modifier_1":              "event.modifier_1",            # SV101-3
    "modifier_2":              "event.modifier_2",            # SV101-4
    "modifier_3":              "event.modifier_3",            # SV101-5
    "service_begin_time":      "event.begin_time",            # DTP*472 begin
    "service_end_time":        "event.end_time",              # DTP*472 end
}

# ---------------------------------------------------------------------------
# Diagnosis code qualifier (Loop 2300 HI01-1)
# ---------------------------------------------------------------------------
DIAGNOSIS_CODE_QUALIFIER = "ABK"          # ICD-10-CM principal diagnosis

# ---------------------------------------------------------------------------
# ISA envelope defaults (outer envelope — not claim-specific)
# ---------------------------------------------------------------------------
ISA_AUTHORIZATION_INFO_QUALIFIER = "00"   # No authorization info
ISA_SECURITY_INFO_QUALIFIER = "00"        # No security info
ISA_INTERCHANGE_ID_QUALIFIER = "ZZ"       # Mutually defined
ISA_VERSION = "00501"                     # 837P version
