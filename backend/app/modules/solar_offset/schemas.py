from pydantic import BaseModel, Field, field_validator


class SolarOffsetIn(BaseModel):
    account_id: int
    billing_period: str = Field(min_length=1)
    offset_kwh: float = Field(ge=0)
    source_note: str | None = None
    entered_by: str | None = None
    # 更正已有有效记录时必须显式携带当前版本号；首录不传。
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("billing_period")
    @classmethod
    def _strip_period(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("billing_period must not be empty")
        return v


class SolarPreviewIn(BaseModel):
    account_id: int
    billing_period: str = Field(min_length=1)
    gross_kwh: float = Field(ge=0)
    peak: bool = False

    @field_validator("billing_period")
    @classmethod
    def _strip_period(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("billing_period must not be empty")
        return v
