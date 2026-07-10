from __future__ import annotations

import json
import logging

from . import config
from .models import Event

logger = logging.getLogger(__name__)


def build_row(event: Event, notiz_link: str) -> list[str]:
    """Baut eine Tabellenzeile in exakter Spaltenreihenfolge.

    'Funktion KP' und 'Spannend für' bleiben leer (füllt ein Mensch)."""
    return [
        event.datum or "",
        event.event_name or "",
        event.branche or "",
        event.ort or "",
        event.kosten or "",
        "",  # Funktion KP – bewusst leer
        "",  # Spannend für – bewusst leer
        notiz_link or "",
    ]


def _build_service():
    """Sheets-Service: Service-Account bevorzugt, sonst OAuth-Refresh-Token.

    Import der Google-Bibliotheken bewusst lazy, damit NO_WRITE-Läufe ohne
    Google-Credentials laufen."""
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    sa_json = config.google_service_account_json()
    if sa_json:
        from google.oauth2 import service_account
        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[config.GOOGLE_SHEETS_SCOPE]
        )
        return build("sheets", "v4", credentials=creds)

    refresh_token = config.google_sheets_refresh_token()
    if refresh_token:
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=config.google_client_id(),
            client_secret=config.google_client_secret(),
            scopes=[config.GOOGLE_SHEETS_SCOPE],
        )
        creds.refresh(Request())
        return build("sheets", "v4", credentials=creds)

    raise RuntimeError(
        "Keine Google-Sheets-Credentials: GOOGLE_SERVICE_ACCOUNT_JSON oder "
        "GOOGLE_SHEETS_REFRESH_TOKEN (+ GOOGLE_CLIENT_ID/SECRET) setzen."
    )


def append_rows(rows: list[list[str]]) -> int:
    """Hängt Zeilen an die Zieltabelle an. Gibt die Anzahl geschriebener Zeilen zurück.

    NO_WRITE -> nur loggen, 0."""
    if not rows:
        return 0
    if config.no_write():
        logger.info("[NO_WRITE] Würde %d Zeile(n) an Sheet %s anhängen: %s",
                    len(rows), config.sheet_id(), rows)
        return 0

    service = _build_service()
    service.spreadsheets().values().append(
        spreadsheetId=config.sheet_id(),
        range=config.SHEET_TAB,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    logger.info("%d Zeile(n) an Sheet %s angehängt", len(rows), config.sheet_id())
    return len(rows)
