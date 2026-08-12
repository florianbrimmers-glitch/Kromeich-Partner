from __future__ import annotations

import io
import logging
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from . import config
from .models import DriveDoc

logger = logging.getLogger(__name__)

_FILE_FIELDS = (
    "id, name, mimeType, size, md5Checksum, modifiedTime, createdTime, "
    "webViewLink, owners(emailAddress), shortcutDetails(targetId, targetMimeType)"
)
_FIELDS = f"nextPageToken, files({_FILE_FIELDS})"

# Kopie-Marker im Dateinamen: "(1)", "Kopie von", "copy of"
_COPY_RE = re.compile(r"\(\d+\)|kopie von|copy of", re.IGNORECASE)

_service = None


def _build_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=config.drive_refresh_token(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.google_client_id(),
        client_secret=config.google_client_secret(),
        scopes=list(config.DRIVE_SCOPES),
    )
    creds.refresh(Request())
    return creds


def get_service():
    """Drive-v3-Service (gecacht). Nutzt dasselbe OAuth-Muster wie src/gmail_client."""
    global _service
    if _service is None:
        _service = build("drive", "v3", credentials=_build_credentials())
    return _service


def _to_doc(raw: dict, gefunden_via: str, pfad_hinweis: str | None = None) -> DriveDoc:
    owners = raw.get("owners") or []
    size = raw.get("size")
    return DriveDoc(
        file_id=raw["id"],
        name=(raw.get("name") or "").strip(),
        mime_type=raw.get("mimeType", ""),
        size=int(size) if size else None,
        md5=raw.get("md5Checksum"),
        modified_time=raw.get("modifiedTime"),
        created_time=raw.get("createdTime"),
        web_link=raw.get("webViewLink"),
        owner=owners[0].get("emailAddress") if owners else None,
        gefunden_via=gefunden_via,
        pfad_hinweis=pfad_hinweis,
    )


def _list(query: str) -> list[dict]:
    """Alle Seiten einer Drive-Suche; Shared Drives eingeschlossen."""
    service = get_service()
    files: list[dict] = []
    page_token = None
    while True:
        try:
            response = (
                service.files()
                .list(
                    q=query,
                    fields=_FIELDS,
                    pageSize=200,
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    corpora="allDrives",
                )
                .execute()
            )
        except HttpError as e:
            logger.error("Drive-Suche fehlgeschlagen (%s): %s", query, e)
            break
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def _resolve_shortcut(raw: dict) -> dict | None:
    """Verknüpfung auflösen – im Drive liegen Angebote teils als Shortcut."""
    target_id = (raw.get("shortcutDetails") or {}).get("targetId")
    if not target_id:
        return None
    try:
        return (
            get_service()
            .files()
            .get(fileId=target_id, fields=_FILE_FIELDS, supportsAllDrives=True)
            .execute()
        )
    except HttpError as e:
        logger.warning("Shortcut %s nicht auflösbar: %s", raw.get("name"), e)
        return None


def _walk_folder(folder_id: str, depth: int = 0, folder_name: str | None = None) -> list[DriveDoc]:
    """Rekursiv alle Dateien unter einem Ordner (inkl. Unterordner)."""
    if depth > config.MAX_FOLDER_DEPTH:
        logger.warning("Ordner-Tiefe %d überschritten bei %s", config.MAX_FOLDER_DEPTH, folder_id)
        return []

    docs: list[DriveDoc] = []
    for raw in _list(f"'{folder_id}' in parents and trashed = false"):
        mime = raw.get("mimeType", "")
        if mime == config.MIME_FOLDER:
            docs.extend(_walk_folder(raw["id"], depth + 1, raw.get("name")))
            continue
        if mime == config.MIME_SHORTCUT:
            target = _resolve_shortcut(raw)
            if not target:
                continue
            raw = target
            mime = raw.get("mimeType", "")
        if mime == config.MIME_FOLDER:      # Shortcut auf einen Ordner
            docs.extend(_walk_folder(raw["id"], depth + 1, raw.get("name")))
            continue
        docs.append(_to_doc(raw, f"ordner:{folder_id}", folder_name))
    return docs


def _title_search() -> list[DriveDoc]:
    docs: list[DriveDoc] = []
    for term in config.TITLE_TERMS:
        raws = _list(f"name contains '{term}' and trashed = false")
        logger.info("Titel-Suche %r: %d Treffer", term, len(raws))
        for raw in raws:
            mime = raw.get("mimeType", "")
            if mime == config.MIME_FOLDER:
                continue
            if mime == config.MIME_SHORTCUT:
                target = _resolve_shortcut(raw)
                if not target or target.get("mimeType") == config.MIME_FOLDER:
                    continue
                raw = target
            docs.append(_to_doc(raw, "titel"))
    return docs


def _copy_score(doc: DriveDoc) -> tuple[int, str]:
    """Sortierschlüssel: welche Kopie einer Datei wir behalten.

    Kleiner ist besser – bevorzugt einen Namen ohne "(1)"/"Kopie von" und den
    zuerst angelegten Eintrag (das Original)."""
    return (1 if _COPY_RE.search(doc.name) else 0, doc.created_time or "9999")


def discover_documents() -> tuple[list[DriveDoc], int, int]:
    """Findet alle Angebots-Dokumente und dedupliziert auf Datei-Ebene.

    Rückgabe: (eindeutige Dokumente, Rohtreffer der Drive-Suche,
    zusammengefasste Mehrfachablagen).
    """
    roh: list[DriveDoc] = _title_search()
    for folder_id in config.SEED_FOLDER_IDS:
        gefunden = _walk_folder(folder_id)
        logger.info("Ordner %s: %d Dateien", folder_id, len(gefunden))
        roh.extend(gefunden)

    # Erst nach file_id zusammenfassen (Titel-Suche + Ordner-Scan finden
    # dieselbe Datei doppelt), dann nach Datei-Inhalt (md5/Größe).
    nach_id: dict[str, DriveDoc] = {}
    for doc in roh:
        vorhanden = nach_id.get(doc.file_id)
        if vorhanden is None:
            nach_id[doc.file_id] = doc
        elif not vorhanden.pfad_hinweis and doc.pfad_hinweis:
            doc.gefunden_via = vorhanden.gefunden_via
            nach_id[doc.file_id] = doc

    nach_inhalt: dict[str, DriveDoc] = {}
    for doc in nach_id.values():
        key = doc.dedup_key()
        vorhanden = nach_inhalt.get(key)
        if vorhanden is None:
            nach_inhalt[key] = doc
            continue
        # gleiche Datei an anderer Stelle: Fundstellen zählen, bessere Kopie behalten
        fundstellen = vorhanden.fundstellen + 1
        behalten = min(vorhanden, doc, key=_copy_score)
        behalten.fundstellen = fundstellen
        nach_inhalt[key] = behalten

    eindeutig = sorted(nach_inhalt.values(), key=lambda d: d.modified_time or "", reverse=True)
    kopien = len(nach_id) - len(eindeutig)
    logger.info(
        "Drive-Discovery: %d Rohtreffer -> %d Dateien -> %d eindeutige Dokumente "
        "(%d Mehrfachablagen übersprungen)",
        len(roh), len(nach_id), len(eindeutig), kopien,
    )
    return eindeutig, len(roh), kopien


def download_bytes(doc: DriveDoc) -> bytes | None:
    """Binärinhalt einer Datei (PDF/Office)."""
    try:
        request = get_service().files().get_media(fileId=doc.file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request, chunksize=5 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        data = buffer.getvalue()
        logger.info("Geladen: %s (%d bytes)", doc.name, len(data))
        return data
    except HttpError as e:
        logger.error("Download fehlgeschlagen %s: %s", doc.name, e)
        return None


def export_text(doc: DriveDoc) -> str | None:
    """Google-eigene Formate (Docs/Slides/Sheets) als Text exportieren."""
    mime_map = {
        config.MIME_GDOC: "text/plain",
        config.MIME_GSLIDES: "text/plain",
        config.MIME_GSHEET: "text/csv",
    }
    export_mime = mime_map.get(doc.mime_type)
    if not export_mime:
        return None
    try:
        data = (
            get_service()
            .files()
            .export(fileId=doc.file_id, mimeType=export_mime)
            .execute()
        )
        return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
    except HttpError as e:
        logger.error("Export fehlgeschlagen %s: %s", doc.name, e)
        return None
