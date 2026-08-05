from __future__ import annotations

from datetime import date
from enum import Enum
from pydantic import BaseModel, Field


class EmailData(BaseModel):
    message_id: str
    sender: str
    sender_email: str
    subject: str
    body: str
    date: str


class ContactData(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str
    phone: str | None = None
    company: str | None = None
    position: str | None = None
    street: str | None = None
    house_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str = "Deutschland"
    salutation: str | None = None  # "mr" (Herr) / "ms" (Frau), sonst None

    def has_missing_fields(self) -> bool:
        return any(
            v is None
            for v in [self.phone, self.company, self.position, self.street, self.city]
        )


class EnrichmentResult(BaseModel):
    phone: str | None = None
    company: str | None = None
    position: str | None = None
    street: str | None = None
    house_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    enriched_fields: list[str] = Field(default_factory=list)


class ContactStatus(str, Enum):
    CREATED = "created"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_INTERNAL = "skipped_internal"
    SKIPPED_AUTO = "skipped_auto"
    SKIPPED_NO_EMAIL = "skipped_no_email"
    SKIPPED_SESSION_DUPLICATE = "skipped_session_duplicate"
    ERROR = "error"


class GroupCategory(str, Enum):
    EIGENTUEMER = "Eigentümer"
    INVESTOR = "Investor"
    LOGISTIKER = "Logistiker"
    MAKLER = "Makler"
    ENTWICKLER = "Entwickler"
    SONSTIGES = "Sonstiges"


GROUP_ID_MAP: dict[GroupCategory, str] = {
    GroupCategory.EIGENTUEMER: "0a0b21607f",
    GroupCategory.INVESTOR: "825c6dd31e",
    GroupCategory.LOGISTIKER: "c09cc4c2f4",
    GroupCategory.MAKLER: "c0b62f43fa",
    GroupCategory.ENTWICKLER: "4b88636ddc",
    GroupCategory.SONSTIGES: "193c2a15bf",
}


class ContactResult(BaseModel):
    email: str
    name: str = ""
    company: str | None = None
    status: ContactStatus
    group_ids: list[str] = Field(default_factory=list)
    group_labels: list[str] = Field(default_factory=list)
    apollo_enriched: bool = False
    enriched_fields: list[str] = Field(default_factory=list)
    error: str | None = None


class PipelineReport(BaseModel):
    run_date: str = Field(default_factory=lambda: date.today().isoformat())
    emails_searched: int = 0
    emails_skipped_internal: int = 0
    emails_skipped_auto: int = 0
    contacts_created: list[ContactResult] = Field(default_factory=list)
    contacts_skipped_duplicate: list[ContactResult] = Field(default_factory=list)
    contacts_skipped_no_email: int = 0
    contacts_skipped_session_duplicate: int = 0
    errors: list[ContactResult] = Field(default_factory=list)
