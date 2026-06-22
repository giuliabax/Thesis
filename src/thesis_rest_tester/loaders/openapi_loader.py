"""Load and normalize OpenAPI 3 or Swagger 2 specifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from thesis_rest_tester.domain.models import OpenAPIOperation
from thesis_rest_tester.domain.schemas import LoadedOpenAPI

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


class OpenAPILoader:
    def load(self, path: str | Path) -> LoadedOpenAPI:
        spec_path = Path(path)
        if not spec_path.is_file():
            raise FileNotFoundError(f"OpenAPI/Swagger file not found: {spec_path}")

        try:
            text = spec_path.read_text(encoding="utf-8")
            raw = json.loads(text) if spec_path.suffix.lower() == ".json" else yaml.safe_load(text)
        except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ValueError(f"Could not parse OpenAPI/Swagger file {spec_path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"OpenAPI/Swagger root must be a mapping: {spec_path}")
        paths = raw.get("paths")
        if not isinstance(paths, dict):
            raise ValueError(f"OpenAPI/Swagger document has no valid 'paths' mapping: {spec_path}")

        operations: list[OpenAPIOperation] = []
        for endpoint, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            path_parameters = self._parameter_list(path_item.get("parameters"))
            for method, operation in path_item.items():
                if (
                    not isinstance(method, str)
                    or method.lower() not in _HTTP_METHODS
                    or not isinstance(operation, dict)
                ):
                    continue
                operation_parameters = self._parameter_list(operation.get("parameters"))
                parameters = self._merge_parameters(path_parameters, operation_parameters)
                responses = operation.get("responses")
                response_codes = list(responses) if isinstance(responses, dict) else []
                operations.append(
                    OpenAPIOperation(
                        operation_id=operation.get("operationId"),
                        method=method,
                        path=str(endpoint),
                        summary=operation.get("summary"),
                        description=operation.get("description"),
                        tags=[str(tag) for tag in operation.get("tags", [])],
                        parameters=parameters,
                        request_body_schema=self._request_schema(operation, parameters),
                        response_codes=[str(code) for code in response_codes],
                        auth_required=self._auth_required(operation, raw),
                    )
                )
        return LoadedOpenAPI(raw_document=raw, operations=operations)

    @staticmethod
    def _parameter_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [parameter for parameter in value if isinstance(parameter, dict)]

    @staticmethod
    def _merge_parameters(
        path_parameters: list[dict[str, Any]],
        operation_parameters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[Any, Any], dict[str, Any]] = {}
        anonymous_index = 0
        for parameter in [*path_parameters, *operation_parameters]:
            if "$ref" in parameter:
                key = ("$ref", parameter["$ref"])
            elif parameter.get("name") is not None:
                key = (parameter.get("in"), parameter.get("name"))
            else:
                anonymous_index += 1
                key = ("anonymous", anonymous_index)
            merged[key] = parameter
        return list(merged.values())

    @staticmethod
    def _request_schema(
        operation: dict[str, Any],
        parameters: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        request_body = operation.get("requestBody")
        if isinstance(request_body, dict):
            if "$ref" in request_body:
                return {"$ref": request_body["$ref"]}
            content = request_body.get("content")
            if isinstance(content, dict) and content:
                media = content.get("application/json") or next(iter(content.values()))
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    return media["schema"]

        for parameter in parameters:
            if parameter.get("in") == "body" and isinstance(parameter.get("schema"), dict):
                return parameter["schema"]
        return None

    @staticmethod
    def _auth_required(operation: dict[str, Any], raw: dict[str, Any]) -> bool | None:
        if "security" in operation:
            security = operation["security"]
        elif "security" in raw:
            security = raw["security"]
        else:
            return None
        return bool(security)
