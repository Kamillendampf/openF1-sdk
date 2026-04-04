from __future__ import annotations

import httpx


class OpenF1Error(Exception):
    """Base class for all F1-SDK errors"""


class OpenF1NoDataError(OpenF1Error):
    """Raised when an endpoint returns no data."""


class OpenF1HTTPError(OpenF1Error):
    """Base class for all F1-SDK HTTP errors"""

    def __init__(self, message: str, status_code: int, request: httpx.Request, response: httpx.Response):
        super().__init__(message)
        self.status_code = status_code
        self.request = request
        self.response = response


class OpenF1AuthError(OpenF1Error):
    """Raised when OAuth token retrieval/refresh fails."""


class OpenF1LiveError(OpenF1Error):
    """Raised for MQTT/Websocket live-stream related failures."""
