# openF1 SDK Facade Documentation

This document describes the public Python facade exposed by the `f1_sdk` package.

The facade is the recommended entry point for applications using the SDK. Instead of creating resource classes manually, import the package and access resources directly:

```python
import f1_sdk as f1

session = f1.session.latest()
drivers = f1.driver.all(session_key=session.session_key)
```

## Facade Overview

The package-level facade is implemented in:

```text
f1_sdk/__init__.py
```

Resources are created lazily. Importing `f1_sdk` does not immediately construct the underlying SDK client. The client is initialized when a resource or client-backed attribute is accessed for the first time.

The facade exposes:

- SDK configuration and lifecycle helpers
- OpenF1 resource proxies
- synchronous and asynchronous SDK client classes
- OAuth and live-data client classes
- SDK-specific exception types

---

## Configuration and Lifecycle

### `f1.configure(config=None)`

Replaces the currently active SDK instance with a new instance using the supplied configuration.

```python
import f1_sdk as f1

config = f1.F1Config(...)
f1.configure(config)
```

If an SDK instance already exists, it is closed before the new instance is created.

**Parameters**

- `config`: optional SDK configuration object. If omitted, the SDK uses its default configuration behavior.

**Returns**

`None`

---

### `f1.close()`

Closes the active SDK client and resets the facade.

```python
import f1_sdk as f1

try:
    session = f1.session.latest()
finally:
    f1.close()
```

After calling `close()`, the facade will create a fresh SDK instance automatically on the next resource access.

---

## Resource Access

The following resource proxies are exposed directly on the `f1_sdk` package.

| Facade attribute | OpenF1 resource | Aliases |
|---|---|---|
| `f1.car_data` | Car data | — |
| `f1.driver` | Drivers | `f1.drivers` |
| `f1.interval` | Intervals | `f1.intervals` |
| `f1.lap` | Laps | `f1.laps` |
| `f1.location` | Location | — |
| `f1.meeting` | Meetings | `f1.meetings` |
| `f1.overtake` | Overtakes | `f1.overtakes` |
| `f1.pit` | Pit stops | — |
| `f1.position` | Positions | — |
| `f1.race_control` | Race control messages | — |
| `f1.session` | Sessions | `f1.sessions` |
| `f1.session_result` | Session results | — |
| `f1.starting_grid` | Starting grid | — |
| `f1.stint` | Stints | `f1.stints` |
| `f1.team_radio` | Team radio | — |
| `f1.weather` | Weather | — |

The singular and plural aliases point to the same logical SDK resources.

---

## Common Resource Methods

All facade resources are based on the SDK's generic resource abstraction and expose the following methods.

### `resource.all(...)`

Returns all matching objects.

```python
drivers = f1.driver.all(session_key=9158)
```

`all()` is the convenience equivalent of `list()`.

**Returns**

A list of typed SDK model objects.

---

### `resource.list(params=None, **filters)`

Queries an OpenF1 resource.

```python
laps = f1.lap.list(
    session_key=9158,
    driver_number=1,
)
```

**Parameters**

- `params`: optional mapping of raw query parameters
- `**filters`: additional OpenF1 API filters

`None` values are omitted from the outgoing query.

**Returns**

A list of typed SDK model objects.

---

### `resource.latest(params=None, **filters)`

Returns one matching object representing the latest result according to the resource's configured ordering.

```python
session = f1.session.latest()
```

Resources that support OpenF1's `latest` syntax automatically send the corresponding parameter using the value `"latest"` when appropriate.

If no data is returned, the SDK raises:

```python
f1.OpenF1NoDataError
```

---

## Session Resource

Accessible as:

```python
f1.session
f1.sessions
```

### `f1.session.all(...)`

```python
sessions = f1.session.all(
    session_key=None,
    meeting_key=None,
    session_name=None,
    session_type=None,
    year=None,
    country_name=None,
    location=None,
)
```

Supported convenience filters:

| Parameter | Type | Description |
|---|---|---|
| `session_key` | `int \| str \| None` | Session identifier or OpenF1 special value |
| `meeting_key` | `int \| str \| None` | Meeting identifier |
| `session_name` | `str \| None` | Session name |
| `session_type` | `str \| None` | Session type |
| `year` | `int \| None` | Championship year |
| `country_name` | `str \| None` | Country name |
| `location` | `str \| None` | Event location |
| `params` | mapping or `None` | Raw query parameters |
| `**filters` | arbitrary | Additional OpenF1 filters |

Example:

```python
race_sessions = f1.session.all(
    year=2025,
    session_name="Race",
)
```

### `f1.session.latest(...)`

```python
session = f1.session.latest(
    meeting_key=None,
    session_name=None,
    session_type=None,
)
```

Explicit convenience filters include:

- `session_key`
- `meeting_key`
- `session_name`
- `session_type`
- `params`
- arbitrary additional filters

Example:

```python
latest_race = f1.session.latest(session_name="Race")
```

The session resource determines the latest result using `date_start`.

---

## Meeting Resource

Accessible as:

```python
f1.meeting
f1.meetings
```

### `f1.meeting.all(...)`

Supported convenience filters:

- `meeting_key`
- `year`
- `country_name`
- `country_code`
- `location`
- `meeting_name`
- `circuit_key`
- `params`
- arbitrary additional OpenF1 filters

Example:

```python
meetings = f1.meeting.all(
    year=2025,
    country_name="Italy",
)
```

### `f1.meeting.latest(...)`

Explicit convenience filters include:

- `meeting_key`
- `year`
- `country_name`
- `params`
- arbitrary additional filters

Example:

```python
meeting = f1.meeting.latest()
print(meeting.meeting_key)
```

The meeting resource determines the latest result using `date_start`.

---

## Driver Resource

Accessible as:

```python
f1.driver
f1.drivers
```

### `f1.driver.all(...)`

Supported convenience filters:

- `session_key`
- `meeting_key`
- `driver_number`
- `name_acronym`
- `first_name`
- `last_name`
- `full_name`
- `team_name`
- `params`
- arbitrary additional OpenF1 filters

Example:

```python
drivers = f1.driver.all(
    session_key=9158,
    team_name="McLaren",
)
```

### `f1.driver.latest(...)`

Explicit convenience filters include:

- `session_key`
- `meeting_key`
- `driver_number`
- `params`
- arbitrary additional filters

Example:

```python
driver = f1.driver.latest(
    session_key="latest",
    driver_number=1,
)
```

---

## Other Resources

The remaining facade resources use the same resource interface:

```python
results = resource.all(...)
result = resource.latest(...)
results = resource.list(...)
```

Examples:

### Laps

```python
laps = f1.lap.all(
    session_key=session.session_key,
    driver_number=1,
)
```

### Car Data

```python
telemetry = f1.car_data.all(
    session_key=session.session_key,
    driver_number=1,
)
```

### Intervals

```python
intervals = f1.interval.all(
    session_key=session.session_key,
)
```

### Location

```python
locations = f1.location.all(
    session_key=session.session_key,
    driver_number=1,
)
```

### Overtakes

```python
overtakes = f1.overtake.all(
    session_key=session.session_key,
)
```

### Pit Stops

```python
pit_stops = f1.pit.all(
    session_key=session.session_key,
)
```

### Position

```python
positions = f1.position.all(
    session_key=session.session_key,
    driver_number=1,
)
```

### Race Control

```python
messages = f1.race_control.all(
    session_key=session.session_key,
)
```

### Session Results

```python
results = f1.session_result.all(
    session_key=session.session_key,
)
```

### Starting Grid

```python
grid = f1.starting_grid.all(
    session_key=session.session_key,
)
```

### Stints

```python
stints = f1.stint.all(
    session_key=session.session_key,
    driver_number=1,
)
```

### Team Radio

```python
radio = f1.team_radio.all(
    session_key=session.session_key,
    driver_number=1,
)
```

### Weather

```python
weather = f1.weather.all(
    session_key=session.session_key,
)
```

Additional OpenF1 filters may be passed as keyword arguments even when they are not listed explicitly in a convenience method signature.

For the authoritative list of query parameters supported by each OpenF1 endpoint, refer to the OpenF1 API documentation:

https://openf1.org/

---

## Raw Query Parameters

Every resource accepts a `params` mapping as well as keyword filters.

```python
laps = f1.lap.all(
    params={
        "session_key": 9158,
        "driver_number": 1,
    }
)
```

You can also use keyword arguments:

```python
laps = f1.lap.all(
    session_key=9158,
    driver_number=1,
)
```

This makes it possible to use OpenF1 filters that are supported by the upstream API even if the SDK has not added a dedicated named parameter for them.

---

## Return Values

Resource calls return SDK model objects rather than untyped dictionaries.

```python
session = f1.session.latest()

print(session.session_key)
print(session.meeting_key)
print(session.session_name)
```

List-style calls return lists of model objects:

```python
drivers = f1.driver.all(session_key=session.session_key)

for driver in drivers:
    print(driver.driver_number, driver.full_name)
```

---

## Error Handling

### `OpenF1NoDataError`

Raised when `latest()` cannot find a matching result.

```python
import f1_sdk as f1

try:
    session = f1.session.latest(year=1900)
except f1.OpenF1NoDataError:
    print("No matching session found.")
```

### `OpenF1AuthError`

Represents authentication-related errors.

```python
except f1.OpenF1AuthError as exc:
    print(f"Authentication failed: {exc}")
```

### `OpenF1LiveError`

Represents failures related to the live-data client.

```python
except f1.OpenF1LiveError as exc:
    print(f"Live data error: {exc}")
```

---

## Advanced SDK Classes

The facade also exports lower-level SDK classes for applications that do not want to use the package-level singleton facade:

```python
f1.OpenF1SDK
f1.AsyncOpenF1SDK
```

The package-level facade is generally simpler:

```python
import f1_sdk as f1

session = f1.session.latest()
```

A manually managed client can be useful when an application needs multiple independently configured SDK instances.

---

## OAuth and Live Data

The public package also exposes:

```python
f1.OpenF1OAuthConfig
f1.OpenF1OAuthClient
f1.OpenF1LiveClient
```

as well as:

```python
f1.OpenF1AuthError
f1.OpenF1LiveError
```

OAuth configuration used by the project can be stored in:

```text
config/openf1.auth.ini
```

Registration, API access and paid plans for the upstream OpenF1 service are managed by OpenF1:

https://openf1.org/

The availability and pricing of OpenF1 live-data access are controlled by OpenF1. This SDK does not control and assumes no responsibility for OpenF1 pricing, subscription fees, plan changes, subscription conditions, or service availability.

---

## Typical Usage

```python
import f1_sdk as f1

# Get the latest session
session = f1.session.latest()

# Get all drivers in that session
drivers = f1.driver.all(
    session_key=session.session_key,
)

# Query one driver's laps
if drivers:
    driver = drivers[0]

    laps = f1.lap.all(
        session_key=session.session_key,
        driver_number=driver.driver_number,
    )

    print(
        session.session_name,
        driver.full_name,
        len(laps),
    )
```

---

## Facade API Summary

```text
f1_sdk
├── configure(config=None)
├── close()
│
├── car_data
├── driver / drivers
├── interval / intervals
├── lap / laps
├── location
├── meeting / meetings
├── overtake / overtakes
├── pit
├── position
├── race_control
├── session / sessions
├── session_result
├── starting_grid
├── stint / stints
├── team_radio
└── weather
```

Each resource proxy exposes the underlying resource methods, including the common:

```text
all(...)
list(...)
latest(...)
```

interface.

---

## Upstream API Documentation

This document describes the **Python SDK facade**.

The authoritative documentation for the underlying OpenF1 API endpoints, fields and supported API query parameters is maintained by OpenF1:

https://openf1.org/
