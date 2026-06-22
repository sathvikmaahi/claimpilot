"""
Stub — 837P field transformation helpers.

Input: Raw field values from EnrichedServiceEvent or Life Unlimited config.
Description: Pure functions that transform service event data into the strict formats
             required by the 837P EDI specification. Used by the Claim Builder agent.
             Transformations include:
             — split_name(full_name) → (last_name, first_name) for NM1 segments
             — format_date_edi(iso_date) → "D8YYYYMMDD" string for DTP segments
             — qualify_diagnosis(icd10_code) → "ABK:F70" string for HI segments
             — build_sv1_procedure(code, *modifiers) → "HC:T2016:UP" string for SV1 segments
             — location_to_pos_code(service_location) → place-of-service code string for CLM05
             — generate_claim_id() → unique UUID-based control number for CLM01
Output: Formatted string values ready for insertion into 837P EDI segments.
"""


def split_name(full_name: str) -> tuple[str, str]:
    raise NotImplementedError


def format_date_edi(iso_date: str) -> str:
    raise NotImplementedError


def qualify_diagnosis(icd10_code: str) -> str:
    raise NotImplementedError


def build_sv1_procedure(code: str, *modifiers: str) -> str:
    raise NotImplementedError


def location_to_pos_code(service_location: str) -> str:
    raise NotImplementedError


def generate_claim_id() -> str:
    raise NotImplementedError
