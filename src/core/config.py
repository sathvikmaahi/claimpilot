from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    mock_auth_api_url: str
    auth_api_timeout: float = 10.0

    # Life Unlimited billing config — used by Step 3 Claim Builder to populate 837P billing fields.
    # Placeholder values for POC; replace with real values before production.
    billing_npi: str = "1234567890"        # Life Unlimited org NPI (Loop 2010AA NM109)
    tax_id: str = "12-3456789"             # Life Unlimited EIN (Loop 2010AA REF EI)
    payer_id: str = "MOHLTH"              # MO HealthNet payer ID (ISA08 / GS03)
    t2016_fee_schedule_rate: Decimal = Decimal("487.68")  # Billed amount per T2016 unit (SV102)


settings = Settings()
