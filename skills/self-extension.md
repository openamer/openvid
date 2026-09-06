# OPENVID Self-Extension v1

## Neue Makro-Fähigkeiten (durch Selbst-Erweiterung hinzugefügt)

### skill: app.start
Beschreibung: Startet beliebiges installiertes Programm robust.
Prozedur: shell.run mit `Start-Process <name>` (PowerShell), NICHT `start <name>` via cmd (Timeout-Risiko).
Beispiel: Start-Process calc | Start-Process brave | Start-Process notepad

### skill: sys.report
Beschreibung: Systemzustand melden.
Prozedur: 1) sys.info aufrufen. 2) Optional shell.run: `Get-Process | Sort-Object CPU -Descending | Select-Object -First 5`

### skill: web.digest
Beschreibung: Thema recherchieren und zusammenfassen.
Prozedur: 1) web.search mit Query. 2) Top-Ergebnis mit web.fetch laden. 3) Kernaussagen extrahieren und auf Deutsch zusammenfassen.

### skill: page.extract
Beschreibung: Daten aus aktiver Browser-Page extrahieren.
Prozedur: browser.eval mit `document.title + document.body.innerText.substring(0,2000)`

### skill: note.save / note.load
Beschreibung: Persistentes Gedächtnis.
Prozedur: memory.write zum Speichern, memory.read mit Suchbegriff zum Abrufen.

## Gelernte Lessons
- L1: `start calc` via cmd im shell.run läuft in Tool-Timeout → immer PowerShell `Start-Process` nutzen.
- L2: Bestätigungen kurz halten, Resultat + Exit-Code nennen.
- L3: Bei Tool-Timeout einmal alternatives Tool/parallelen Weg probieren, dann ehrlich melden.
