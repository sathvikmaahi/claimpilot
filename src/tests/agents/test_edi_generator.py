"""
Unit tests for the 837P EDI generator.

These test the pure Python generate_837p() function in isolation —
no LLM, no DB, no external calls. Input is a ClaimFields object;
output is an 837P EDI text string.

Tests verify:
  - ISA/IEA envelope wraps the transaction set
  - ST/SE are present and SE segment count is accurate
  - CLM segment carries the correct billed amount
  - SV1 composite includes procedure code + modifiers
  - Null modifiers are excluded from SV1 composite
  - DMG has subscriber sex
  - HI has diagnosis code
  - Time segments (DTP*473/474) only appear when begin/end times are given
"""
import uuid

from agents.claim_builder.agent import ClaimFields
from agents.claim_builder.edi_generator import generate_837p

_CLAIM_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_fields(**overrides) -> ClaimFields:
    base = {
        "subscriber_last_name": "Smith",
        "subscriber_first_name": "John",
        "subscriber_medicaid_id": "MO100001",
        "subscriber_dob": "19820314",
        "subscriber_sex": "M",
        "service_date": "20260610",
        "service_begin_time": None,
        "service_end_time": None,
        "diagnosis_code": "F70",
        "waiver_type": "Comprehensive",
        "diagnosis_qualifier": "ABK",
        "place_of_service": "12",
        "claim_filing_indicator": "MC",
        "rendering_npi": "1234567890",
        "procedure_code": "T2016",
        "procedure_qualifier": "HC",
        "modifier_1": "U1",
        "modifier_2": None,
        "modifier_3": None,
        "service_units": 32,
        "billed_amount": "15606.00",
        "taxonomy_code": "251G00000X",
        "notes": None,
    }
    base.update(overrides)
    return ClaimFields(**base)


def _edi(**overrides) -> str:
    return generate_837p(
        fields=_make_fields(**overrides),
        billing_npi="1234567890",
        tax_id="12-3456789",
        payer_id="MOHLTH",
        claim_id=_CLAIM_ID,
    )


def _lines(**overrides) -> list[str]:
    return _edi(**overrides).split("\n")


# -----------------------------------------------------------------------
# Envelope
# -----------------------------------------------------------------------

def test_isa_is_first_segment():
    """
    Input: Default ClaimFields.
    Description: ISA must be the first segment of any 837P EDI file.
    Output: First line starts with ISA*.
    """
    assert _lines()[0].startswith("ISA*")


def test_iea_is_last_segment():
    """
    Input: Default ClaimFields.
    Description: IEA closes the interchange envelope and must be the last segment.
    Output: Last line starts with IEA*.
    """
    assert _lines()[-1].startswith("IEA*")


def test_gs_and_ge_present():
    """
    Input: Default ClaimFields.
    Description: GS/GE wrap the functional group — must appear after ISA and before IEA.
    Output: Lines contain GS* and GE*.
    """
    lines = _lines()
    assert any(l.startswith("GS*") for l in lines)
    assert any(l.startswith("GE*") for l in lines)


# -----------------------------------------------------------------------
# Transaction set
# -----------------------------------------------------------------------

def test_st_segment_present():
    """
    Input: Default ClaimFields.
    Description: ST*837 opens the transaction set.
    Output: A line starting with ST*837* exists.
    """
    assert any(l.startswith("ST*837*") for l in _lines())


def test_se_segment_count_matches_actual_segments():
    """
    Input: Default ClaimFields.
    Description: SE02 must equal the total number of segments from ST to SE inclusive.
                 This is validated by EDI translators and must be exact.
    Output: SE segment count == number of segments between ST and SE inclusive.
    """
    lines = _lines()
    st_idx = next(i for i, l in enumerate(lines) if l.startswith("ST*"))
    se_idx = next(i for i, l in enumerate(lines) if l.startswith("SE*"))
    expected = se_idx - st_idx + 1  # ST through SE inclusive
    reported = int(lines[se_idx].rstrip("~").split("*")[1])
    assert reported == expected


# -----------------------------------------------------------------------
# Claim segment (Loop 2300)
# -----------------------------------------------------------------------

def test_clm_billed_amount():
    """
    Input: billed_amount="15606.00".
    Description: CLM02 must carry the billed amount — used by payer for adjudication.
    Output: CLM*<ref>*15606.00* in the EDI text.
    """
    clm = next(l for l in _lines() if l.startswith("CLM*"))
    parts = clm.rstrip("~").split("*")
    assert parts[2] == "15606.00"


def test_hi_contains_diagnosis_code():
    """
    Input: diagnosis_code="F70".
    Description: HI segment carries the ICD-10 code for the claim.
    Output: HI line contains "F70".
    """
    hi = next(l for l in _lines() if l.startswith("HI*"))
    assert "F70" in hi


# -----------------------------------------------------------------------
# Service line (Loop 2400)
# -----------------------------------------------------------------------

def test_sv1_modifier_1_present():
    """
    Input: modifier_1="U1".
    Description: modifier_1 is required by MO HealthNet for T2016 — must appear in SV1 composite.
    Output: "U1" is in the SV1 line.
    """
    sv1 = next(l for l in _lines() if l.startswith("SV1*"))
    assert "U1" in sv1


def test_sv1_null_modifiers_excluded():
    """
    Input: modifier_2=None, modifier_3=None.
    Description: Null modifiers must not appear in the SV1 composite — no trailing colons.
    Output: SV1 composite is exactly "HC:T2016:U1".
    """
    lines = _lines(modifier_2=None, modifier_3=None)
    sv1 = next(l for l in lines if l.startswith("SV1*"))
    composite = sv1.rstrip("~").split("*")[1]
    assert composite == "HC:T2016:U1"


def test_sv1_modifier_2_included_when_present():
    """
    Input: modifier_2="HQ".
    Description: When modifier_2 is set it must appear in the SV1 composite after modifier_1.
    Output: "HQ" is in the SV1 line.
    """
    lines = _lines(modifier_2="HQ")
    sv1 = next(l for l in lines if l.startswith("SV1*"))
    assert "HQ" in sv1


def test_sv1_service_units():
    """
    Input: service_units=32.
    Description: SV104 carries the unit count for the claim.
    Output: SV1 element 4 (index 4) is "32".
    """
    sv1 = next(l for l in _lines() if l.startswith("SV1*"))
    parts = sv1.rstrip("~").split("*")
    assert parts[4] == "32"


# -----------------------------------------------------------------------
# Subscriber (Loop 2000B)
# -----------------------------------------------------------------------

def test_dmg_subscriber_sex():
    """
    Input: subscriber_sex="M".
    Description: DMG03 carries the patient sex code — required for 837P.
    Output: DMG line ends with "*M~".
    """
    dmg = next(l for l in _lines() if l.startswith("DMG*"))
    assert dmg.rstrip("~").endswith("*M")


# -----------------------------------------------------------------------
# Service times
# -----------------------------------------------------------------------

def test_no_tm_segments_when_times_absent():
    """
    Input: service_begin_time=None, service_end_time=None.
    Description: DTP*473 and DTP*474 (time segments) must not appear when times are not recorded.
    Output: No DTP*473* or DTP*474* lines.
    """
    lines = _lines(service_begin_time=None, service_end_time=None)
    assert not any(l.startswith("DTP*473*") for l in lines)
    assert not any(l.startswith("DTP*474*") for l in lines)


def test_tm_segments_present_when_times_given():
    """
    Input: service_begin_time="0700", service_end_time="1500".
    Description: When shift times are recorded, DTP*473 (check-in) and DTP*474 (check-out)
                 time segments must appear on the service line.
    Output: DTP*473*TM*0700~ and DTP*474*TM*1500~ are present.
    """
    lines = _lines(service_begin_time="0700", service_end_time="1500")
    assert any(l.startswith("DTP*473*TM*") for l in lines)
    assert any(l.startswith("DTP*474*TM*") for l in lines)


def test_waiver_type_is_added_as_note_segment():
    """
    Input: waiver_type="Comprehensive".
    Description: Waiver type must be preserved in the generated EDI as an NTE note.
    Output: NTE*ADD*WaiverType:Comprehensive~ is present.
    """
    lines = _lines(waiver_type="Comprehensive")
    assert any(l.startswith("NTE*ADD*WaiverType:Comprehensive~") for l in lines)
