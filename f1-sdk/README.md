# OpenF1 SDK (Facade + Resources)

## Ziel
Dieses SDK stellt eine einfache Facade bereit, damit du direkt so arbeiten kannst:

```python
import f1_sdk as f1

session = f1.session.latest()
print(session.meeting_key)

drivers = f1.driver.all(session_key=session.session_key)
```

## Installation

```bash
pip install -e ./f1-sdk
```

Danach:

```python
import f1_sdk as f1
```

## Facade-Struktur

Die Facade exportiert explizite Ressourcen-Objekte:

- `f1.session`, `f1.driver`, `f1.lap`, `f1.meeting`, ...
- Zusätzlich auch Plural-Aliase: `f1.sessions`, `f1.drivers`, `f1.laps`, ...

Jede Resource hat standardisiert:

- `all(...)` -> Liste von Model-Objekten
- `list(...)` -> Alias zu `all(...)`
- `latest(...)` -> genau ein Model-Objekt (oder Exception bei keinen Daten)

## Verhalten von `latest()`

`latest()` ist API-orientiert:

- Bei session-basierten Endpoints wird `session_key=latest` erzwungen.
- Bei meeting-basierten Endpoints wird `meeting_key=latest` erzwungen.

Beispiel:

```python
f1.session.latest()      # nutzt session_key=latest
f1.meeting.latest()      # nutzt meeting_key=latest
f1.weather.latest()      # nutzt meeting_key=latest
```

Falls die API keine Daten zurückgibt, wird `OpenF1NoDataError` geworfen.

## Rückgabewerte und Typen

Alle Resource-Methoden geben Pydantic-Modelle aus `Models/` zurück.
Beispiele:

- `f1.session.latest()` -> `Session`
- `f1.driver.all(...)` -> `list[Driver]`
- `f1.lap.latest(...)` -> `Laps`
- `f1.weather.all(...)` -> `list[Weather]`

Damit ist nachgelagertes Filtern direkt möglich:

```python
session = f1.session.latest()
drivers = f1.driver.all(session_key=session.session_key)
ferrari = [d for d in drivers if d.team_name == "Ferrari"]
```

## Resource-Übersicht (pro Datei unter `resources/`)

### `CarDataResource` (`f1.car_data`, `f1.car`)
- Datei: `resources/car_data.py`
- Optionen in `all(...)`:
  - `session_key`, `meeting_key`, `driver_number`, `date`, `n_gear`, `speed`, `params`, `**filters`
- Optionen in `latest(...)`:
  - `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`

### `DriverResource` (`f1.driver`, `f1.drivers`)
- Datei: `resources/driver.py`
- `all(...)`:
  - `session_key`, `meeting_key`, `driver_number`, `name_acronym`, `first_name`, `last_name`, `full_name`, `team_name`, `params`, `**filters`
- `latest(...)`:
  - `session_key`, `meeting_key`, `driver_number`, `params`, `**filters`

### `IntervalResource` (`f1.interval`, `f1.intervals`)
- Datei: `resources/interval.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`

### `LapResource` (`f1.lap`, `f1.laps`)
- Datei: `resources/lap.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `lap_number`, `date_start`, `is_pit_out_lap`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `lap_number`, `params`, `**filters`

### `LocationResource` (`f1.location`)
- Datei: `resources/location.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`

### `MeetingResource` (`f1.meeting`, `f1.meetings`)
- Datei: `resources/meeting.py`
- `all(...)`: `meeting_key`, `year`, `country_name`, `country_code`, `location`, `meeting_name`, `circuit_key`, `params`, `**filters`
- `latest(...)`: `meeting_key`, `year`, `country_name`, `params`, `**filters`

### `OvertakeResource` (`f1.overtake`, `f1.overtakes`)
- Datei: `resources/overtake.py`
- `all(...)`: `session_key`, `meeting_key`, `overtaking_driver_number`, `overtaken_driver_number`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `overtaking_driver_number`, `overtaken_driver_number`, `params`, `**filters`

### `PitResource` (`f1.pit`)
- Datei: `resources/pit.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `lap_number`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `lap_number`, `params`, `**filters`

### `PositionResource` (`f1.position`)
- Datei: `resources/position.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `position`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `params`, `**filters`

### `RaceControlResource` (`f1.race_control`)
- Datei: `resources/race_control.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `category`, `flag`, `lap_number`, `scope`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `category`, `params`, `**filters`

### `SessionResource` (`f1.session`, `f1.sessions`)
- Datei: `resources/session.py`
- `all(...)`: `session_key`, `meeting_key`, `session_name`, `session_type`, `year`, `country_name`, `location`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `session_name`, `session_type`, `params`, `**filters`

### `SessionResultResource` (`f1.session_result`)
- Datei: `resources/session_result.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `position`, `dnf`, `dns`, `dsq`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `params`, `**filters`

### `StartingGridResource` (`f1.starting_grid`)
- Datei: `resources/starting_grid.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `position`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `params`, `**filters`

### `StintResource` (`f1.stint`, `f1.stints`)
- Datei: `resources/stint.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `stint_number`, `compound`, `lap_start`, `lap_end`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `stint_number`, `params`, `**filters`

### `TeamRadioResource` (`f1.team_radio`)
- Datei: `resources/team_radio.py`
- `all(...)`: `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`
- `latest(...)`: `session_key`, `meeting_key`, `driver_number`, `date`, `params`, `**filters`

### `WeatherResource` (`f1.weather`)
- Datei: `resources/weather.py`
- `all(...)`: `meeting_key`, `session_key`, `date`, `humidity`, `rainfall`, `params`, `**filters`
- `latest(...)`: `meeting_key`, `session_key`, `date`, `params`, `**filters`

## SDK-Helper in der Facade

Neben den Resources gibt es in `OpenF1SDK` (über `f1` erreichbar):

- `f1.resource_names()`
- `f1.list_resource(resource_name, ...)`
- `f1.latest_resource(resource_name, ...)`
- `f1.latest_meeting(...)`
- `f1.latest_session(...)`
- `f1.latest_race_session(...)`
- `f1.drivers_for_session(...)`
- `f1.weather_for_session(...)`
- `f1.race_control_for_session(...)`
- `f1.laps_for_driver(...)`
- `f1.car_data_for_driver(...)`
- `f1.positions_for_driver(...)`
- `f1.team_radio_for_driver(...)`
- `f1.session_scope(...)`

## SessionScope

`SessionScope` kapselt wiederkehrende Filter:

```python
scope = f1.session_scope(session_key="latest")
session = scope.session()
drivers = scope.drivers()
laps_1 = scope.laps(driver_number=1)
```

## Fehlerbehandlung

- `OpenF1HTTPError`: HTTP-Fehler/Statusfehler
- `OpenF1NoDataError`: `latest()` hat keine Daten erhalten

Beispiel:

```python
import f1_sdk as f1

try:
    session = f1.session.latest()
except f1.OpenF1NoDataError:
    session = None
```

## IntelliJ / PyCharm Hinweise

Wenn Autocomplete nicht sofort stimmt:

1. Projekt neu laden
2. Python-Interpreter prüfen
3. Caches/Index neu aufbauen

Die Facade ist mit expliziten Resource-Attributen typisiert (`f1.session`, `f1.driver`, ...), damit Vorschläge für Methoden und Felder angezeigt werden.
