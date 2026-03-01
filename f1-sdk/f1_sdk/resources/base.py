from __future__ import annotations

from typing import Any, Generic, Mapping, TypeVar

from ..Models import F1BaseModel
from ..client.errors import OpenF1NoDataError
from ..client.http import HttpClient

ModelT = TypeVar("ModelT", bound=F1BaseModel)


class ModelResource(Generic[ModelT]):
    """
    Generic resource for list-style OpenF1 endpoints.
    """

    def __init__(
        self,
        http: HttpClient,
        path: str,
        model_type: type[ModelT],
        latest_by: str | None = None,
        latest_param: str | None = None,
    ):
        self._http = http
        self._path = path
        self._model_type = model_type
        self._latest_by = latest_by
        self._latest_param = latest_param

    @property
    def path(self) -> str:
        return self._path

    @property
    def model_type(self) -> type[ModelT]:
        return self._model_type

    @staticmethod
    def _compact(filters: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in filters.items() if value is not None}

    def list(self, params: Mapping[str, Any] | None = None, **filters: Any) -> list[ModelT]:
        query: dict[str, Any] = dict(params or {})
        query.update(self._compact(filters))
        raw_items = self._http.get_list(self._path, params=query if query else None)
        return [self._model_type.model_validate(item) for item in raw_items]

    def all(self, params: Mapping[str, Any] | None = None, **filters: Any) -> list[ModelT]:
        return self.list(params=params, **filters)

    def latest(self, params: Mapping[str, Any] | None = None, **filters: Any) -> ModelT:
        query: dict[str, Any] = dict(params or {})
        query.update(self._compact(filters))

        if self._latest_param:
            query[self._latest_param] = "latest"

        items = self.list(params=query if query else None)
        if not items:
            raise OpenF1NoDataError(f"No data returned for endpoint '{self._path}'")

        if self._latest_param and self._latest_by:
            return max(items, key=lambda item: getattr(item, self._latest_by))
        if self._latest_param:
            return items[0]

        if not self._latest_by:
            return items[-1]
        return max(items, key=lambda item: getattr(item, self._latest_by))
