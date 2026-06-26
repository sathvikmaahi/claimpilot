"""
Step 5: 837P EDI generator.

Takes the structured ClaimFields produced by the Claim Builder agent and assembles
the actual 837P EDI text. Pure Python — no LLM, no external calls.

The output is a valid 837P transaction set (005010X222A1) that can be submitted
to MO HealthNet. Delimiter conventions:
  Element separator : *
  Sub-element separator : :
  Segment terminator : ~
"""
import uuid
from datetime import datetime, timezone

from agents.claim_builder.agent import ClaimFields
from agents.claim_builder.billing_rules import (
    BILLING_PROVIDER_TAXONOMY,
    CLAIM_FREQUENCY_CODE,
    FACILITY_CODE_QUALIFIER,
    ISA_AUTHORIZATION_INFO_QUALIFIER,
    ISA_INTERCHANGE_ID_QUALIFIER,
    ISA_SECURITY_INFO_QUALIFIER,
    ISA_VERSION,
    PLACE_OF_SERVICE_CODE,
    SUBSCRIBER_RELATIONSHIP,
)

# EDI delimiters
_EL = "*"   # element separator
_SE = ":"   # sub-element separator
_ST = "~"   # segment terminator


def _seg(*elements: str) -> str:
    """Join elements with * and append ~ segment terminator."""
    return _EL.join(str(e) for e in elements) + _ST


def generate_837p(
    fields: ClaimFields,
    billing_npi: str,
    tax_id: str,
    payer_id: str,
    claim_id: uuid.UUID,
) -> str:
    """
    Assemble a 837P EDI transaction set from ClaimFields.

    Returns the full EDI string with one segment per line for readability.
    Each segment ends with ~.
    """
    now = datetime.now(tz=timezone.utc)
    date_str = now.strftime("%y%m%d")       # YYMMDD for ISA09
    time_str = now.strftime("%H%M")         # HHMM for ISA10
    date_long = now.strftime("%Y%m%d")      # YYYYMMDD for GS04 / DTP
    control_number = "000000001"
    sender_id = billing_npi.ljust(15)       # ISA06 — padded to 15 chars
    receiver_id = payer_id.ljust(15)        # ISA08 — padded to 15 chars
    tax_id_digits = tax_id.replace("-", "") # EIN without hyphen for REF*EI

    segments: list[str] = []

    # -----------------------------------------------------------------------
    # ISA / GS envelope
    # -----------------------------------------------------------------------
    segments.append(_seg(
        "ISA",
        ISA_AUTHORIZATION_INFO_QUALIFIER, "          ",  # ISA02 — 10 spaces
        ISA_SECURITY_INFO_QUALIFIER,      "          ",  # ISA04 — 10 spaces
        ISA_INTERCHANGE_ID_QUALIFIER, sender_id,
        ISA_INTERCHANGE_ID_QUALIFIER, receiver_id,
        date_str, time_str,
        "^",                   # ISA11 repetition separator
        ISA_VERSION,
        control_number,
        "0",                   # ISA14 ack requested: No
        "P",                   # ISA15 usage: Production
        _SE,                   # ISA16 sub-element separator
    ))
    segments.append(_seg("GS", "HC", billing_npi, payer_id, date_long, time_str, "1", "X", "005010X222A1"))
    segments.append(_seg("ST", "837", "0001", "005010X222A1"))

    # -----------------------------------------------------------------------
    # Loop 1000A — Submitter (Life Unlimited)
    # -----------------------------------------------------------------------
    segments.append(_seg("NM1", "41", "2", "LIFE UNLIMITED INC", "", "", "", "", "46", billing_npi))
    segments.append(_seg("PER", "IC", "BILLING DEPT", "TE", "0000000000"))  # TODO: real phone

    # Loop 1000B — Receiver (MO HealthNet)
    segments.append(_seg("NM1", "40", "2", "MO HEALTHNET", "", "", "", "", "46", payer_id))

    # -----------------------------------------------------------------------
    # Loop 2000A — Billing Provider Hierarchical Level
    # -----------------------------------------------------------------------
    segments.append(_seg("HL", "1", "", "20", "1"))
    segments.append(_seg("PRV", "BI", "PXC", BILLING_PROVIDER_TAXONOMY))
    segments.append(_seg("NM1", "85", "2", "LIFE UNLIMITED INC", "", "", "", "", "XX", billing_npi))
    segments.append(_seg("REF", "EI", tax_id_digits))

    # -----------------------------------------------------------------------
    # Loop 2000B — Subscriber (patient is the Medicaid subscriber)
    # -----------------------------------------------------------------------
    segments.append(_seg("HL", "2", "1", "22", "0"))
    segments.append(_seg("SBR", "P", SUBSCRIBER_RELATIONSHIP, fields.subscriber_medicaid_id, "", "", "", "", "", "MC"))

    # Loop 2010BA — Subscriber Name
    last = fields.subscriber_last_name
    first = fields.subscriber_first_name or ""
    segments.append(_seg("NM1", "IL", "1", last, first, "", "", "", "MI", fields.subscriber_medicaid_id))
    segments.append(_seg("DMG", "D8", fields.subscriber_dob, fields.subscriber_sex))

    # Loop 2010BB — Payer (MO HealthNet)
    segments.append(_seg("NM1", "PR", "2", "MO HEALTHNET", "", "", "", "", "PI", payer_id))

    # -----------------------------------------------------------------------
    # Loop 2300 — Claim Information
    # -----------------------------------------------------------------------
    claim_ref = str(claim_id).replace("-", "")[:20]  # claim control number (max 20 chars)
    clm05 = f"{PLACE_OF_SERVICE_CODE}{_SE}{FACILITY_CODE_QUALIFIER}{_SE}{CLAIM_FREQUENCY_CODE}"
    segments.append(_seg("CLM", claim_ref, fields.billed_amount, "", "", clm05, "Y", "A", "Y", "I"))
    segments.append(_seg("DTP", "472", "D8", fields.service_date))
    segments.append(_seg("HI", f"{fields.diagnosis_qualifier}{_SE}{fields.diagnosis_code}"))

    # Loop 2310B — Rendering Provider
    segments.append(_seg("NM1", "82", "1", last, first, "", "", "", "XX", fields.rendering_npi))
    segments.append(_seg("PRV", "PE", "PXC", BILLING_PROVIDER_TAXONOMY))

    # -----------------------------------------------------------------------
    # Loop 2400 — Service Line
    # -----------------------------------------------------------------------
    segments.append(_seg("LX", "1"))

    # SV101: procedure composite — HC:code:mod1:mod2:mod3
    sv101_parts = [fields.procedure_qualifier, fields.procedure_code, fields.modifier_1]
    if fields.modifier_2:
        sv101_parts.append(fields.modifier_2)
    if fields.modifier_3:
        sv101_parts.append(fields.modifier_3)
    sv101 = _SE.join(sv101_parts)
    segments.append(_seg("SV1", sv101, fields.billed_amount, "UN", str(fields.service_units), "", "", "1"))

    # Service date on line level
    if fields.service_begin_time and fields.service_end_time:
        segments.append(_seg("DTP", "472", "RD8", f"{fields.service_date}-{fields.service_date}"))
        segments.append(_seg("DTP", "473", "TM", fields.service_begin_time))
        segments.append(_seg("DTP", "474", "TM", fields.service_end_time))
    else:
        segments.append(_seg("DTP", "472", "D8", fields.service_date))

    # -----------------------------------------------------------------------
    # ST/SE segment count + GS/IEA trailers
    # -----------------------------------------------------------------------
    # Count: all segments between ST and SE inclusive
    seg_count = len(segments) - 2 + 1  # subtract ISA+GS, add SE itself
    segments.append(_seg("SE", str(seg_count), "0001"))
    segments.append(_seg("GE", "1", "1"))
    segments.append(_seg("IEA", "1", control_number))

    return "\n".join(segments)
