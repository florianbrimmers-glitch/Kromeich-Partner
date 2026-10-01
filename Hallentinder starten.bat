@echo off
rem Startet Hallentinder fuer eine Vorfuehrung im Team (Windows).
rem Doppelklick genuegt. Bewusst ohne Umlaute - die Windows-Konsole
rem stellt sie je nach Codepage falsch dar.
setlocal
cd /d "%~dp0"
title Hallentinder

echo ====================================================
echo  Hallentinder wird gestartet
echo ====================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo FEHLER: Python wurde nicht gefunden.
    echo.
    echo Python von python.org installieren und dabei
    echo "Add Python to PATH" anhaken. Danach dieses
    echo Fenster schliessen und neu starten.
    echo.
    pause
    exit /b 1
)

echo Abhaengigkeiten pruefen und bei Bedarf installieren...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo FEHLER: Die Installation ist fehlgeschlagen. Bitte die
    echo Meldung oben an Claude weitergeben.
    echo.
    pause
    exit /b 1
)
echo Fertig.
echo.

if "%PROPSTACK_API_KEY%"=="" (
    echo Propstack-API-Key einfuegen ^(rechte Maustaste = einfuegen^)
    echo und mit Enter bestaetigen. Der Key wird nicht gespeichert.
    echo.
    set /p PROPSTACK_API_KEY=Key: 
    echo.
)

if "%PROPSTACK_API_KEY%"=="" (
    echo FEHLER: Kein Key eingegeben.
    echo Zu finden in Propstack unter Verwaltung - API-Schluessel.
    echo.
    pause
    exit /b 1
)

echo ====================================================
echo  Der Bestand wird jetzt geladen. Das dauert rund
echo  zwei Minuten. Bereit ist die App, sobald die Zeile
echo  "Bestand im Cache: ... vermietbare Hallen" erscheint.
echo.
echo  Die Adresse fuer die Kollegen steht gleich unten -
echo  die Zeile "Fuer Kollegen im gleichen WLAN".
echo.
echo  Beenden mit Strg+C oder Fenster schliessen.
echo ====================================================
echo.

python -m hallentinder.main

echo.
echo Hallentinder wurde beendet.
pause
