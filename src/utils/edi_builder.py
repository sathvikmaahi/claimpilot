"""
Stub — 837P EDI file builder.

Input: Mapped and transformed 837P field dict from the Claim Builder agent.
Description: Wraps python-x12 (or pyx12) to assemble a valid 837P EDI transaction
             from a dictionary of pre-transformed segment values.
             Handles ISA/GS envelope construction, loop ordering (2000A, 2000B, 2300, 2400),
             segment delimiter configuration, and SE01 segment count calculation.
             The Claim Builder agent calls this after completing all field transformations.
Output: Valid 837P EDI string that can be submitted to MO HealthNet via eMOMED.
        Raises ValueError if any mandatory segment is missing from the input dict.
"""


def build_837p(segment_map: dict) -> str:
    """
    Input: segment_map (dict) — pre-transformed 837P field values keyed by segment name.
    Description: Assembles a complete 837P EDI transaction from the segment map.
    Output: 837P EDI string.
    """
    raise NotImplementedError("EDI builder not yet implemented — requires python-x12 setup.")
