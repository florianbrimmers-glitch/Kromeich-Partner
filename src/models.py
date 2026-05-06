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
    PRODUZENT = "Produzent"
    HANDEL = "Handel"


GROUP_ID_MAP: dict[GroupCategory, int] = {
    GroupCategory.EIGENTUEMER: 507350,
    GroupCategory.INVESTOR: 507349,
    GroupCategory.LOGISTIKER: 636740,
    GroupCategory.MAKLER: 409483,
    GroupCategory.PRODUZENT: 641030,
    GroupCategory.HANDEL: 641031,
}


class ContactResult(BaseModel):
    email: str
    name: str = ""
    company: str | None = None
    status: ContactStatus
    group_ids: list[int] = Field(default_factory=list)
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


class WarehouseCandidate(BaseModel):
    osm_type: str
    osm_id: int
    name: str | None = None
    operator: str | None = None
    area_sqm: float
    lat: float
    lon: float
    street: str | None = None
    house_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    building: str | None = None
    landuse: str | None = None

    @property
    def display_name(self) -> str:
        return self.operator or self.name or f"OSM {self.osm_type}/{self.osm_id}"

    @property
    def address_line(self) -> str:
        parts: list[str] = []
        if self.street:
            street_part = self.street
            if self.house_number:
                street_part = f"{self.street} {self.house_number}"
            parts.append(street_part)
        if self.zip_code or self.city:
            parts.append(f"{self.zip_code or ''} {self.city or ''}".strip())
        return ", ".join(p for p in parts if p)

    @property
    def osm_url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"

    @property
    def maps_url(self) -> str:
        return f"https://www.google.com/maps?q={self.lat},{self.lon}"
