from __future__ import annotations

import configparser
from dataclasses import dataclass
import logging
import os
from pathlib import Path
from time import time
from typing import Any

import httpx

from .errors import OpenF1AuthError

LOGGER = logging.getLogger("openf1.auth")


def _is_truthy_env(var_name: str) -> bool:
    return os.getenv(var_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _mask_email(value: str | None) -> str:
    if not value:
        return "<empty>"
    if "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _email_for_logs(value: str | None) -> str:
    if LOGGER.isEnabledFor(logging.DEBUG) and _is_truthy_env("OPENF1_LOG_PII"):
        return value or "<empty>"
    return _mask_email(value)


@dataclass(frozen=True)
class OpenF1OAuthConfig:
    auth_required: bool = False
    user_email: str = ""
    user_password: str = ""
    token_url: str = "https://api.openf1.org/token"
    timeout: float = 15.0

    @classmethod
    def from_ini(cls, config_path: str | Path, section: str = "openf1_auth") -> OpenF1OAuthConfig:
        path = Path(config_path)
        LOGGER.debug("Loading OAuth INI from %s (section=%s).", path, section)
        if not path.exists():
            LOGGER.warning("Missing auth config: %s. OAuth disabled.", path)
            return cls(auth_required=False)

        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")

        if section not in parser:
            LOGGER.warning("Missing section [%s] in %s. OAuth disabled.", section, path)
            return cls(auth_required=False)

        cfg = parser[section]
        auth_required = cfg.getboolean("auth_required", fallback=False)
        if not auth_required:
            LOGGER.info("OAuth is configured as disabled in %s.", path)
            return cls(auth_required=False)

        user_email = cfg.get("user_email", "").strip()
        user_password = cfg.get("user_password", "").strip()
        token_url = cfg.get("token_url", "https://api.openf1.org/token").strip()

        timeout_raw = cfg.get("timeout", "15").strip()
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise OpenF1AuthError(f"Invalid timeout value '{timeout_raw}' in auth config.") from exc

        if not user_email or not user_password:
            raise OpenF1AuthError("Missing 'user_email' or 'user_password' in auth config.")

        LOGGER.info(
            "OAuth config enabled (token_url=%s, timeout=%ss, user_email=%s).",
            token_url,
            timeout,
            _email_for_logs(user_email),
        )
        LOGGER.debug("OAuth PII debug mode is %s.", _is_truthy_env("OPENF1_LOG_PII"))

        return cls(
            auth_required=True,
            user_email=user_email,
            user_password=user_password,
            token_url=token_url,
            timeout=timeout,
        )


@dataclass(frozen=True)
class OpenF1Token:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    obtained_at: float = 0.0

    def is_expired(self, skew_seconds: int = 30) -> bool:
        if self.expires_in is None:
            return False
        return time() >= (self.obtained_at + self.expires_in - skew_seconds)


class OpenF1OAuthClient:
    def __init__(self, config: OpenF1OAuthConfig):
        self.config = config
        self._http = httpx.Client(timeout=config.timeout)
        self._cached: OpenF1Token | None = None
        LOGGER.debug("OpenF1OAuthClient initialized (token_url=%s).", config.token_url)

    def close(self) -> None:
        LOGGER.debug("Closing OpenF1OAuthClient HTTP client.")
        self._http.close()

    def fetch_access_token(self) -> OpenF1Token:
        LOGGER.info("Fetching OAuth access token from %s.", self.config.token_url)
        LOGGER.debug(
            "OAuth token request metadata (user_email=%s, timeout=%ss).",
            _email_for_logs(self.config.user_email),
            self.config.timeout,
        )
        payload = {
            "username": self.config.user_email,
            "password": self.config.user_password,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            response = self._http.post(self.config.token_url, data=payload, headers=headers)
            LOGGER.debug("OAuth token HTTP response status=%s.", response.status_code)
            response.raise_for_status()
            data: Any = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            body_preview = exc.response.text[:500] if exc.response is not None else ""
            raise OpenF1AuthError(f"Token request failed with HTTP {status_code}: {body_preview}") from exc
        except Exception as exc:  # noqa: BLE001
            raise OpenF1AuthError(f"Token request failed: {exc}") from exc

        if not isinstance(data, dict):
            raise OpenF1AuthError(f"OAuth response is not a JSON object: {type(data)}")

        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OpenF1AuthError("OAuth response does not contain a valid access_token.")

        raw_token_type = data.get("token_type")
        token_type = raw_token_type if isinstance(raw_token_type, str) and raw_token_type else "Bearer"

        raw_expires_in = data.get("expires_in")
        expires_in: int | None = None
        if isinstance(raw_expires_in, (int, float)):
            expires_in = max(0, int(raw_expires_in))
        elif isinstance(raw_expires_in, str):
            try:
                expires_in = max(0, int(float(raw_expires_in)))
            except ValueError:
                expires_in = None

        parsed = OpenF1Token(
            access_token=access_token,
            token_type=token_type,
            expires_in=expires_in,
            obtained_at=time(),
        )
        self._cached = parsed
        LOGGER.debug("OAuth token parsed (token_type=%s, expires_in=%s).", token_type, expires_in)
        LOGGER.info("OAuth token fetched successfully (expires_in=%s).", expires_in)
        return parsed

    def get_token(self, force_refresh: bool = False, min_ttl_seconds: int = 60) -> OpenF1Token:
        LOGGER.debug("get_token called (force_refresh=%s, min_ttl_seconds=%s).", force_refresh, min_ttl_seconds)
        if force_refresh or self._cached is None or self._cached.is_expired(skew_seconds=min_ttl_seconds):
            if force_refresh:
                LOGGER.info("Refreshing OAuth token (force_refresh=True).")
            return self.fetch_access_token()
        LOGGER.debug("Using cached OAuth token.")
        return self._cached
