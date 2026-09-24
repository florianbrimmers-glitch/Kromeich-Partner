from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NewUnit(BaseModel):
    """Eine im Berichtsfenster angelegte Einheit (Propstack "unit" == Rails Property)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str | None = None
    name: str | None = None
    address: str | None = None
    city: str | None = None
    property_space_value: float | None = None
    marketing_type: str | None = None
    project_id: int | None = None
    created_at: str | None = None

    def label(self) -> str:
        return self.title or self.name or self.address or f"Einheit {self.id}"


class ProjectInfo(BaseModel):
    """Projekt-Stammdaten aus GET /v1/projects – bewusst ohne Zeitstempel, den gibt es dort nicht."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str | None = None
    name: str | None = None
    address: str | None = None

    def label(self) -> str:
        return self.title or self.name or self.address or f"Projekt {self.id}"


class ProjectActivity(BaseModel):
    """Ein Projekt, das im Fenster Einheiten bekommen hat – neu oder bereits bestehend."""

    project: ProjectInfo
    neue_einheiten: int
    gesamtflaeche: float | None = None
    ist_neu: bool
    # Einheiten können auf ein Projekt zeigen, das es nicht mehr gibt: GET /v1/projects
    # listet es nicht und GET /v1/projects/:id antwortet 404 (verifiziert an 570742).
    # Dann gibt es keinen Titel und der Deep-Link würde ins Leere führen.
    gefunden: bool = True


class PruefTask(BaseModel):
    """Eine Prüfaufgabe aus GET /v1/activities?item_type=reminder."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str | None = None
    done: bool | None = None
    broker_id: int | None = None
    original_created_at: str | None = None
    updated_at: str | None = None
    property_names: list[str] = Field(default_factory=list)
    project_names: list[str] = Field(default_factory=list)

    def label(self) -> str:
        return (self.title or "").strip() or f"Aufgabe {self.id}"


class ReportData(BaseModel):
    """Alles, was report.build() für die Slack-Nachricht braucht."""

    since: str
    until: str
    neue_projekte: list[ProjectActivity] = Field(default_factory=list)
    bestehende_projekte: list[ProjectActivity] = Field(default_factory=list)
    neue_einheiten: list[NewUnit] = Field(default_factory=list)
    einheiten_ohne_projekt: list[NewUnit] = Field(default_factory=list)
    abgeschlossene_aufgaben: list[PruefTask] = Field(default_factory=list)
    bearbeitete_aufgaben: list[PruefTask] = Field(default_factory=list)
