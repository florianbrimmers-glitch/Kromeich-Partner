# Hinweise für Claude

## E-Mail-Anhänge
- Alle Gmail-Anhänge werden per Gmail-Automatisierung in Google Drive im Ordner
  **„Email Anhänge“** (Meine Ablage, Ordner-ID `1xXNw6v7Tn70m0QHJOFoz7BQGZy26wNAK`) gespeichert.
- Anhänge daher nicht über Gmail laden, sondern dort suchen
  (`search_files` mit `parentId = '1xXNw6v7Tn70m0QHJOFoz7BQGZy26wNAK'`).
- Text lesen: `read_file_content` (funktioniert auch bei großen PDFs; frisch abgelegte
  Dateien sind evtl. erst nach ein paar Minuten indexiert).
- Komplett herunterladen (`download_file_content`) klappt nur bis ca. 3 MB; größere
  Dateien (Bilder/Anhänge für Propstack) muss der Nutzer im Chat hochladen.
