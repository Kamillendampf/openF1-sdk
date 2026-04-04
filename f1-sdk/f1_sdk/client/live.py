from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import ssl
from threading import Event, Lock
from time import sleep
from typing import Any, Callable, Optional, TYPE_CHECKING

from .errors import OpenF1LiveError

if TYPE_CHECKING:
    from .sdk import OpenF1SDK
    from ..Models import Session

TokenProvider = Callable[[bool], Optional[str]]
LOGGER = logging.getLogger("openf1.live")


class OpenF1LiveClient:
    """
    MQTT-based live stream client for OpenF1.
    """

    def __init__(
        self,
        sdk: OpenF1SDK,
        *,
        token_provider: TokenProvider,
        username: str,
        topics: tuple[str, ...] = ("v1/position", "v1/laps", "v1/location"),
        broker: str = "mqtt.openf1.org",
        mqtt_port: int = 8883,
        ws_port: int = 8084,
        use_websocket: bool = False,
        websocket_path: str = "/mqtt",
        keepalive_seconds: int = 60,
        connect_timeout_seconds: float = 10.0,
        track_cache_ttl_seconds: float = 900.0,
    ):
        self._sdk = sdk
        self._token_provider = token_provider
        self._username = username
        self._topics = topics
        self._broker = broker
        self._mqtt_port = mqtt_port
        self._ws_port = ws_port
        self._use_websocket = use_websocket
        self._websocket_path = websocket_path
        self._keepalive_seconds = keepalive_seconds
        self._connect_timeout_seconds = connect_timeout_seconds
        self._track_cache_ttl_seconds = track_cache_ttl_seconds

        self._state_lock = Lock()
        self._connected_event = Event()
        self._connect_rc: int | None = None
        self._mqtt_client: Any | None = None
        self._last_auth_username_masked: str | None = None
        self._last_auth_token_length: int | None = None
        self._last_auth_token_fingerprint: str | None = None
        self._running = False
        self._latest_msg_id_by_topic: dict[str, int] = {}
        self._state: dict[str, Any] = {
            "session_key": None,
            "session_name": None,
            "session_type": None,
            "circuit_name": None,
            "session_started_at": None,
            "track": [],
            "drivers": {},
            "lap_current": None,
            "lap_max": None,
            "position_timestamp": None,
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _session_track_cache_key(session: Session) -> str:
        return (
            f"track:{session.circuit_key}:"
            f"{session.session_type}:{session.session_name}:{session.year}"
        )

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return None
        return None

    @staticmethod
    def _as_str(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _mask_identity(value: str | None) -> str:
        if not value:
            return "<empty>"
        if "@" in value:
            local, domain = value.split("@", 1)
            if not local:
                return f"***@{domain}"
            return f"{local[0]}***@{domain}"
        if len(value) <= 2:
            return "***"
        return f"{value[0]}***{value[-1]}"

    @staticmethod
    def _token_fingerprint(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _connect_reason(rc: int) -> str:
        reasons = {
            0: "connection accepted",
            1: "unacceptable protocol version",
            2: "identifier rejected",
            3: "broker unavailable",
            4: "bad username or password",
            5: "not authorized",
            128: "unspecified error",
            129: "malformed packet",
            130: "protocol error",
            131: "implementation specific error",
            132: "unsupported protocol version",
            133: "client identifier not valid",
            134: "bad username or password",
            135: "not authorized",
            136: "server unavailable",
        }
        return reasons.get(rc, "unknown reason")

    @staticmethod
    def _normalize_reason_code(reason_code: Any, default: int = -1) -> int:
        if reason_code is None:
            return default
        try:
            return int(reason_code)
        except Exception:  # noqa: BLE001
            pass

        raw_value = getattr(reason_code, "value", None)
        if isinstance(raw_value, (int, float)):
            return int(raw_value)

        raw_name = str(reason_code).strip().lower()
        if raw_name == "success":
            return 0
        return default

    @staticmethod
    def _is_protocol_mismatch_rc(rc: int | None) -> bool:
        return rc in {1, 132}

    @staticmethod
    def _resolve_protocol_candidates(mqtt) -> list[tuple[str, int]]:
        raw = os.getenv("OPENF1_LIVE_MQTT_PROTOCOL", "auto").strip().lower()
        protocol_v5 = getattr(mqtt, "MQTTv5", None)
        protocol_v311 = getattr(mqtt, "MQTTv311", None)
        protocol_v31 = getattr(mqtt, "MQTTv31", None)

        if raw == "v5":
            return [("v5", protocol_v5)] if protocol_v5 is not None else []
        if raw in {"v311", "3.1.1"}:
            return [("v311", protocol_v311)] if protocol_v311 is not None else []
        if raw in {"v31", "3.1"}:
            return [("v31", protocol_v31)] if protocol_v31 is not None else []

        candidates: list[tuple[str, int]] = []
        if protocol_v5 is not None:
            candidates.append(("v5", protocol_v5))
        if protocol_v311 is not None:
            candidates.append(("v311", protocol_v311))
        if protocol_v31 is not None:
            candidates.append(("v31", protocol_v31))
        return candidates

    def _resolve_transport_candidates(self) -> list[str]:
        # Keep explicit websocket mode, otherwise try mqtt first and fallback to websocket.
        if self._use_websocket:
            return ["websocket"]
        return ["mqtt", "websocket"]

    def _ensure_mqtt_module(self):
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except ModuleNotFoundError as exc:
            raise OpenF1LiveError(
                "Missing dependency 'paho-mqtt'. Install with: pip install paho-mqtt"
            ) from exc
        return mqtt

    def _require_access_token(self, force_refresh: bool = False) -> str:
        token = self._token_provider(force_refresh)
        if not token:
            raise OpenF1LiveError("No OAuth access token available for MQTT authentication.")
        return token

    def _bootstrap_state(self) -> None:
        session = self._sdk.latest_session()
        track_key = self._session_track_cache_key(session)
        track_points = self._sdk.get_or_load_cached(
            key=track_key,
            loader=lambda: self._sdk.get_track(session),
            ttl_seconds=self._track_cache_ttl_seconds,
        )

        drivers_by_number: dict[int, dict[str, Any]] = {}
        for driver in self._sdk.driver.list(session_key=session.session_key):
            payload = driver.model_dump()
            payload["current_position"] = None
            payload["position_date"] = None
            payload["current_lap"] = None
            payload["lap_date"] = None
            payload["track_point"] = None
            drivers_by_number[driver.driver_number] = payload

        seeded_positions = 0
        seeded_track_points = 0
        latest_position_by_driver: dict[int, Any] = {}
        try:
            position_rows = self._sdk.position.list(session_key=session.session_key)
            for row in position_rows:
                previous = latest_position_by_driver.get(row.driver_number)
                if previous is None or row.date > previous.date:
                    latest_position_by_driver[row.driver_number] = row
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Could not seed initial positions from /position: %s", exc)

        bootstrap_locations_enabled = os.getenv("OPENF1_LIVE_BOOTSTRAP_LOCATIONS", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        for driver_number, payload in drivers_by_number.items():
            latest_position = latest_position_by_driver.get(driver_number)
            if latest_position is not None:
                payload["current_position"] = self._as_int(getattr(latest_position, "position", None))
                payload["position_date"] = self._as_str(getattr(latest_position, "date", None))
                if payload["current_position"] is not None:
                    seeded_positions += 1

            if not bootstrap_locations_enabled:
                continue
            try:
                location_rows = self._sdk.location.list(session_key=session.session_key, driver_number=driver_number)
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug(
                    "Could not seed initial location for driver_number=%s: %s",
                    driver_number,
                    exc,
                )
                continue
            if not location_rows:
                continue
            latest_location = max(location_rows, key=lambda row: row.date)
            payload["track_point"] = {
                "x": latest_location.x,
                "y": latest_location.y,
                "z": latest_location.z,
                "date": latest_location.date,
            }
            seeded_track_points += 1

        max_lap: int | None = None
        try:
            session_result = self._sdk.session_result.list(session_key=session.session_key, position=1)
            if session_result:
                max_lap = self._as_int(session_result[0].number_of_laps)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Could not read max laps from session_result: %s", exc)

        with self._state_lock:
            self._state["session_key"] = session.session_key
            self._state["session_name"] = session.session_name
            self._state["session_type"] = session.session_type
            self._state["circuit_name"] = session.circuit_short_name
            self._state["session_started_at"] = self._as_str(getattr(session, "date_start", None))
            self._state["track"] = track_points
            self._state["drivers"] = drivers_by_number
            self._state["lap_current"] = None
            self._state["lap_max"] = max_lap
            self._state["position_timestamp"] = None

        LOGGER.info(
            "Live client bootstrapped (session_key=%s, drivers=%d, track_points=%d, seeded_positions=%d, seeded_track_points=%d, max_lap=%s).",
            session.session_key,
            len(drivers_by_number),
            len(track_points),
            seeded_positions,
            seeded_track_points,
            max_lap,
        )

    def _ensure_driver_state(self, driver_number: int) -> dict[str, Any]:
        drivers = self._state["drivers"]
        if driver_number not in drivers:
            drivers[driver_number] = {
                "driver_number": driver_number,
                "full_name": None,
                "name_acronym": None,
                "team_name": None,
                "headshot_url": None,
                "team_colour": None,
                "current_position": None,
                "position_date": None,
                "current_lap": None,
                "lap_date": None,
                "track_point": None,
            }
        return drivers[driver_number]

    def _handle_position_message(self, payload: dict[str, Any]) -> None:
        driver_number = self._as_int(payload.get("driver_number"))
        position = self._as_int(payload.get("position"))
        date = self._as_str(payload.get("date"))
        if driver_number is None or position is None:
            return

        with self._state_lock:
            driver = self._ensure_driver_state(driver_number)
            driver["current_position"] = position
            if date:
                driver["position_date"] = date
                if self._state["position_timestamp"] is None or date > self._state["position_timestamp"]:
                    self._state["position_timestamp"] = date

    def _handle_lap_message(self, payload: dict[str, Any]) -> None:
        driver_number = self._as_int(payload.get("driver_number"))
        lap_number = self._as_int(payload.get("lap_number"))
        lap_date = self._as_str(payload.get("date_start")) or self._as_str(payload.get("date"))
        if driver_number is None or lap_number is None:
            return

        with self._state_lock:
            driver = self._ensure_driver_state(driver_number)
            driver["current_lap"] = lap_number
            if lap_date:
                driver["lap_date"] = lap_date

            max_observed_lap = lap_number
            for candidate in self._state["drivers"].values():
                candidate_lap = candidate.get("current_lap")
                if isinstance(candidate_lap, int) and candidate_lap > max_observed_lap:
                    max_observed_lap = candidate_lap
            self._state["lap_current"] = max_observed_lap

            number_of_laps = self._as_int(payload.get("number_of_laps")) or self._as_int(payload.get("max_lap"))
            if number_of_laps is not None:
                self._state["lap_max"] = number_of_laps
            elif self._state["lap_max"] is None:
                self._state["lap_max"] = max_observed_lap

    def _handle_location_message(self, payload: dict[str, Any]) -> None:
        driver_number = self._as_int(payload.get("driver_number"))
        if driver_number is None:
            return
        x = self._as_int(payload.get("x"))
        y = self._as_int(payload.get("y"))
        z = self._as_int(payload.get("z"))
        date = self._as_str(payload.get("date"))
        if x is None or y is None or z is None:
            return

        with self._state_lock:
            driver = self._ensure_driver_state(driver_number)
            driver["track_point"] = {"x": x, "y": y, "z": z, "date": date}

    def _topic_session_key(self, payload: dict[str, Any]) -> int | None:
        return self._as_int(payload.get("session_key"))

    def _accept_message(self, payload: dict[str, Any]) -> bool:
        incoming_session_key = self._topic_session_key(payload)
        with self._state_lock:
            state_session_key = self._state.get("session_key")
        if incoming_session_key is None or state_session_key is None:
            return True
        return incoming_session_key == state_session_key

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
        rc = self._normalize_reason_code(reason_code, default=1)
        self._connect_rc = rc
        reason_text = self._connect_reason(rc)

        if rc == 0:
            LOGGER.info(
                "Connected to OpenF1 MQTT broker (rc=%s, reason=%s, auth_username=%s, token_fingerprint=%s).",
                rc,
                reason_text,
                self._last_auth_username_masked or "<unknown>",
                self._last_auth_token_fingerprint or "<unknown>",
            )
            for topic in self._topics:
                client.subscribe(topic)
                LOGGER.info("Subscribed to topic '%s'.", topic)
        else:
            LOGGER.error(
                "MQTT connect failed with rc=%s (%s). Client sent auth payload (username=%s, token_len=%s, token_fingerprint=%s).",
                rc,
                reason_text,
                self._last_auth_username_masked or "<unknown>",
                self._last_auth_token_length if self._last_auth_token_length is not None else "<unknown>",
                self._last_auth_token_fingerprint or "<unknown>",
            )
        self._connected_event.set()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):  # noqa: ANN001
        rc = self._normalize_reason_code(reason_code, default=-1)
        LOGGER.warning("Disconnected from OpenF1 MQTT broker (rc=%s).", rc)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Invalid MQTT JSON payload on topic %s: %s", topic, exc)
            return
        if not isinstance(payload, dict):
            return

        msg_id = self._as_int(payload.get("_id"))
        if msg_id is not None:
            previous_id = self._latest_msg_id_by_topic.get(topic)
            if previous_id is not None and msg_id <= previous_id:
                return
            self._latest_msg_id_by_topic[topic] = msg_id

        if not self._accept_message(payload):
            return

        if topic == "v1/position":
            self._handle_position_message(payload)
        elif topic == "v1/laps":
            self._handle_lap_message(payload)
        elif topic == "v1/location":
            self._handle_location_message(payload)

    def start(self) -> None:
        if self._running:
            return

        self._bootstrap_state()
        mqtt = self._ensure_mqtt_module()
        token = self._require_access_token(force_refresh=True)
        protocol_candidates = self._resolve_protocol_candidates(mqtt)
        if not protocol_candidates:
            raise OpenF1LiveError("No supported MQTT protocol constants found in paho-mqtt.")
        transport_candidates = self._resolve_transport_candidates()
        self._last_auth_username_masked = self._mask_identity(self._username)
        self._last_auth_token_length = len(token)
        self._last_auth_token_fingerprint = self._token_fingerprint(token)
        LOGGER.info(
            "Prepared MQTT auth payload (username=%s, token_len=%d, token_fingerprint=%s).",
            self._last_auth_username_masked,
            self._last_auth_token_length,
            self._last_auth_token_fingerprint,
        )
        LOGGER.info(
            "MQTT protocol negotiation candidates: %s (env OPENF1_LIVE_MQTT_PROTOCOL=%s).",
            ", ".join(name for name, _ in protocol_candidates),
            os.getenv("OPENF1_LIVE_MQTT_PROTOCOL", "auto"),
        )
        LOGGER.info("MQTT transport candidates: %s.", ", ".join(transport_candidates))

        last_error: OpenF1LiveError | None = None
        total_protocols = len(protocol_candidates)
        total_transports = len(transport_candidates)
        for transport_idx, transport_name in enumerate(transport_candidates, start=1):
            is_websocket_transport = transport_name == "websocket"
            LOGGER.info(
                "Starting MQTT transport attempt %d/%d (%s).",
                transport_idx,
                total_transports,
                transport_name,
            )
            for protocol_idx, (protocol_name, protocol_value) in enumerate(protocol_candidates, start=1):
                if is_websocket_transport:
                    client = mqtt.Client(
                        mqtt.CallbackAPIVersion.VERSION2,
                        protocol=protocol_value,
                        transport="websockets",
                    )
                    client.ws_set_options(path=self._websocket_path)
                    connect_port = self._ws_port
                else:
                    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=protocol_value)
                    connect_port = self._mqtt_port

                client.username_pw_set(username=self._username, password=token)
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
                client.on_connect = self._on_connect
                client.on_message = self._on_message
                client.on_disconnect = self._on_disconnect
                client.reconnect_delay_set(min_delay=1, max_delay=30)
                try:
                    client.enable_logger(LOGGER)
                except Exception:  # noqa: BLE001
                    LOGGER.debug("Could not enable paho MQTT debug logger.")

                self._connected_event.clear()
                self._connect_rc = None
                self._mqtt_client = client
                self._running = True

                LOGGER.info(
                    "Connecting live client (transport_attempt=%d/%d, protocol_attempt=%d/%d, protocol=%s, transport=%s, broker=%s:%s, auth_username=%s, token_len=%s, token_fingerprint=%s).",
                    transport_idx,
                    total_transports,
                    protocol_idx,
                    total_protocols,
                    protocol_name,
                    transport_name,
                    self._broker,
                    connect_port,
                    self._last_auth_username_masked or "<unknown>",
                    self._last_auth_token_length if self._last_auth_token_length is not None else "<unknown>",
                    self._last_auth_token_fingerprint or "<unknown>",
                )
                client.connect(self._broker, connect_port, self._keepalive_seconds)
                client.loop_start()

                if not self._connected_event.wait(timeout=self._connect_timeout_seconds):
                    self.stop()
                    last_error = OpenF1LiveError("MQTT connection timed out.")
                elif self._connect_rc != 0:
                    self.stop()
                    last_error = OpenF1LiveError(f"MQTT connection failed with rc={self._connect_rc}.")
                else:
                    LOGGER.info(
                        "MQTT connection established using transport=%s, protocol=%s.",
                        transport_name,
                        protocol_name,
                    )
                    return

                if (
                    protocol_idx < total_protocols
                    and last_error is not None
                    and self._is_protocol_mismatch_rc(self._connect_rc)
                ):
                    LOGGER.warning(
                        "MQTT broker rejected protocol=%s (rc=%s) on transport=%s. Retrying with next protocol candidate.",
                        protocol_name,
                        self._connect_rc,
                        transport_name,
                    )
                    continue

                if last_error is not None:
                    LOGGER.warning(
                        "MQTT attempt failed on transport=%s protocol=%s: %s",
                        transport_name,
                        protocol_name,
                        last_error,
                    )
                    break

            if transport_idx < total_transports:
                LOGGER.warning("Switching MQTT transport to next candidate after failed attempt (%s).", transport_name)

        raise last_error or OpenF1LiveError("MQTT connection failed with all transport/protocol candidates.")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._mqtt_client = None
        LOGGER.info("Live client stopped.")

    def get_snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            state_copy = deepcopy(self._state)

        drivers_payload = list(state_copy["drivers"].values())
        drivers_payload.sort(
            key=lambda row: (
                row.get("current_position") is None,
                row.get("current_position") if row.get("current_position") is not None else 999,
                row.get("driver_number", 999),
            )
        )

        lap_current = state_copy.get("lap_current")
        lap_max = state_copy.get("lap_max")
        lap_display = None
        if lap_current is not None and lap_max is not None:
            lap_display = f"{lap_current}/{lap_max}"

        return {
            "mode": "live_mqtt",
            "session_key": state_copy["session_key"],
            "session_name": state_copy["session_name"],
            "session_type": state_copy["session_type"],
            "circuit_name": state_copy["circuit_name"],
            "session_started_at": state_copy["session_started_at"],
            "track": state_copy["track"],
            "drivers": drivers_payload,
            "lap": {
                "current": lap_current,
                "max": lap_max,
                "display": lap_display,
            },
            "position_timestamp": state_copy["position_timestamp"],
            "generated_at": self._now_iso(),
        }

    def iter_snapshots(self, interval_seconds: float = 1.0):
        while self._running:
            yield self.get_snapshot()
            sleep(max(0.1, float(interval_seconds)))
