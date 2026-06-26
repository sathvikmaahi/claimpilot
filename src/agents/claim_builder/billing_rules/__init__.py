"""
Billing rules for the Claim Builder.

This package exposes billing constants loaded from `config.yaml`.
The actual config is stored in YAML, while Python only provides the importable
module interface used by the rest of the codebase.
"""
from __future__ import annotations

from pathlib import Path
import yaml


_CONFIG_PATH = Path(__file__).with_name("config.yaml")


def _load_config() -> dict:
    with _CONFIG_PATH.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


_config = _load_config()

PROCEDURE_CODE = _config["PROCEDURE_CODE"]
PROCEDURE_CODE_QUALIFIER = _config["PROCEDURE_CODE_QUALIFIER"]
CLAIM_FILING_INDICATOR = _config["CLAIM_FILING_INDICATOR"]
PLACE_OF_SERVICE_CODE = _config["PLACE_OF_SERVICE_CODE"]
FACILITY_CODE_QUALIFIER = _config["FACILITY_CODE_QUALIFIER"]
CLAIM_FREQUENCY_CODE = _config["CLAIM_FREQUENCY_CODE"]
BILLING_PROVIDER_TAXONOMY = _config["BILLING_PROVIDER_TAXONOMY"]
SUBSCRIBER_RELATIONSHIP = _config["SUBSCRIBER_RELATIONSHIP"]
VALID_MODIFIERS = _config["VALID_MODIFIERS"]
FIELD_MAP = _config["FIELD_MAP"]
DIAGNOSIS_CODE_QUALIFIER = _config["DIAGNOSIS_CODE_QUALIFIER"]
ISA_AUTHORIZATION_INFO_QUALIFIER = _config["ISA_AUTHORIZATION_INFO_QUALIFIER"]
ISA_SECURITY_INFO_QUALIFIER = _config["ISA_SECURITY_INFO_QUALIFIER"]
ISA_INTERCHANGE_ID_QUALIFIER = _config["ISA_INTERCHANGE_ID_QUALIFIER"]
ISA_VERSION = _config["ISA_VERSION"]
