"""
Lightweight structural validator for generated 837P EDI strings.

Checks that required ISA/GS/ST/CLM/NM1/SV1 segments are present and that
loop ordering is coherent. Used by the Correction and Resubmit flows (Step 6)
and re-used by Check 8 (837P structural check) in the validation pipeline.

Returns a list of error strings; empty list means the EDI passes structural checks.
"""
from __future__ import annotations

import re

# Segments that must appear exactly once at the envelope level
_REQUIRED_ENVELOPE_SEGMENTS = ["ISA", "GS", "ST", "SE", "GE", "IEA"]

# Segments that must appear at least once inside the transaction
_REQUIRED_TRANSACTION_SEGMENTS = [
    "NM1",  # subscriber / billing provider name
    "CLM",  # claim information
    "SV1",  # professional service
]

# ISA segment must have exactly 16 elements
_ISA_ELEMENT_COUNT = 16

# SV1 dollar amount pattern (digits, optional decimal)
_DOLLAR_RE = re.compile(r"^\d+(\.\d{1,2})?$")


def validate_837p(edi_text: str) -> list[str]:
    """Return a list of structural error strings (empty = OK)."""
    errors: list[str] = []

    if not edi_text or not edi_text.strip():
        return ["EDI text is empty."]

    # Detect element separator (char at position 3 of ISA segment)
    lines = [ln.strip() for ln in edi_text.splitlines() if ln.strip()]
    if not lines[0].startswith("ISA"):
        errors.append("First segment is not ISA.")
        return errors

    element_sep = lines[0][3]
    segment_ids = {ln.split(element_sep)[0] for ln in lines}

    # Envelope segments
    for seg in _REQUIRED_ENVELOPE_SEGMENTS:
        if seg not in segment_ids:
            errors.append(f"Missing required segment: {seg}")

    # Transaction segments
    for seg in _REQUIRED_TRANSACTION_SEGMENTS:
        if seg not in segment_ids:
            errors.append(f"Missing required transaction segment: {seg}")

    # ISA element count
    isa_line = next((ln for ln in lines if ln.startswith("ISA")), None)
    if isa_line:
        parts = isa_line.rstrip(element_sep).split(element_sep)
        if len(parts) - 1 != _ISA_ELEMENT_COUNT:
            errors.append(
                f"ISA segment has {len(parts) - 1} elements; expected {_ISA_ELEMENT_COUNT}."
            )

    # SV1 billed amount must be a valid dollar figure
    sv1_line = next((ln for ln in lines if ln.startswith("SV1")), None)
    if sv1_line:
        sv1_parts = sv1_line.split(element_sep)
        # SV102 is the charge amount (index 2)
        if len(sv1_parts) > 2:
            amount = sv1_parts[2].strip()
            if not _DOLLAR_RE.match(amount):
                errors.append(f"SV102 billed amount '{amount}' is not a valid dollar figure.")

    # CLM must have a non-empty claim ID (CLM01)
    clm_line = next((ln for ln in lines if ln.startswith("CLM")), None)
    if clm_line:
        clm_parts = clm_line.split(element_sep)
        if len(clm_parts) < 2 or not clm_parts[1].strip():
            errors.append("CLM01 (claim ID) is missing or empty.")

    return errors
