# SDK Migration Prompt (History/Replay)

Stand: 2026-03-22
Repo: `E:\dev\Nexora\openF1`

## Ziel
Die History/Replay-Domainlogik aus `main.py` in das SDK (`f1-sdk/f1_sdk`) verschieben, ohne API-Vertrag zu brechen.

## Copy/Paste Prompt (fuer spaeter)
```text
Arbeite im Repo E:\dev\Nexora\openF1.

Bitte migriere die History/Replay-Domainlogik aus main.py in das SDK unter f1-sdk/f1_sdk und stelle sicher, dass die bestehende FastAPI-API kompatibel bleibt.

Wichtig:
1) Keine Breaking Changes an den Endpunkt-Responses:
   - /api/history
   - /api/history/playback
   - /api/history/replay/init
   - /api/history/replay/lap
2) 404 von /position muss robust behandelt werden (Fallback auf leere Positionsdaten, kein 500).
3) Positions-Sync zwischen Leaderboard und Track muss konsistent bleiben.
4) Fehlende Location/Position-Daten duerfen nicht zum kompletten Ausfall fuehren (seed/fallback verwenden).
5) sample_step Defaults fuer Replay/Playback sollen auf fluessige Darstellung optimiert bleiben (aktuell 1).

Scope fuer die Migration:
- Domain-Helfer aus main.py ins SDK verschieben:
  _load_position_rows
  _load_driver_position_rows
  _latest_position_before
  _latest_location_for_driver
  _snap_to_track_point
  _build_driver_metadata_payload
  _build_drivers_payload
  _session_lap_payload
  _build_history_playback_events
  _build_lap_window_map
  _build_lap_events_for_window
- API-spezifische Verantwortung in main.py lassen:
  FastAPI Routing, Query/HTTPException, Response-Envelope, Logging am Endpoint-Rand.

Architekturziel:
- Neue SDK-Service-Schicht z. B. f1-sdk/f1_sdk/services/history_replay.py
- Main ruft nur noch SDK-Servicefunktionen auf.
- Caching-Konzept klar halten (track/history context), kein versteckter globaler Zustand im SDK ohne Grund.

Lieferergebnis:
1) Code umgesetzt
2) main.py auf neue SDK-Funktionen umgestellt
3) Kurzer Migrationshinweis in einer Doku-Datei
4) Verifikation ausgefuehrt und dokumentiert:
   - python -m py_compile main.py
   - python -m py_compile f1-sdk/f1_sdk/client/live.py
   - falls vorhanden: relevante SDK-Tests

Bitte direkt umsetzen (nicht nur planen), sauber commit-bereite Aenderungen liefern und am Ende kurz:
- was verschoben wurde
- welche API-Vertraege unveraendert blieben
- welche Rest-Risiken bestehen
```

## Kurzprompt (Alternative)
```text
Bitte fuehre jetzt die SDK-Migration der History/Replay-Logik aus main.py durch, ohne API-Breaking-Changes, inklusive 404-/position-Fallback, konsistentem Position-Sync und Verifikation.
```
