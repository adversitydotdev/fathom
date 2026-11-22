"""Query sources over a vendor's API model: OpenAPI (RFC 0006) or Smithy (RFC 0007).

The service sees one interface whichever model an integration bundles: search
the queryable operations, describe one, and validate a definition into its
item schema. Both implementations wrap the SDK, which the integration process
also uses, so OGRL and the integration agree on what a query means.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ogrl_integration import openapi, smithy

Problem = openapi.Problem


@dataclass(frozen=True)
class QuerySpec:
    operation: str
    params: dict[str, str] = field(default_factory=dict)
    items: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    regions: list[str] | Literal["*"] | None = None
    for_each: dict[str, Any] | None = None  # RFC 0006 section 3


class ApiModel(Protocol):
    kind: Literal["openapi", "smithy"]

    def search(self, text: str, limit: int = 100) -> list[dict[str, Any]]:
        """Queryable operations matching every word, as `OperationView` fields."""
        ...

    def describe(self, operation: str) -> dict[str, Any] | None:
        """One operation with its parameters and item fields; None if absent."""
        ...

    def validate(
        self, spec: QuerySpec, name: str | None = None
    ) -> tuple[list[Problem], dict[str, Any] | None]:
        """Static validation and the derived item schema."""
        ...


class OpenApiModel:
    kind: Literal["openapi"] = "openapi"

    def __init__(self, settings: openapi.Settings, description: openapi.Description) -> None:
        self.settings = settings
        self.description = description

    def _view(self, op: openapi.Operation) -> dict[str, Any]:
        return {
            "id": op.id,
            "method": op.method,
            "path": op.path,
            "summary": op.summary,
            "parameters": [
                {
                    "name": name,
                    "in": p["in"],
                    "required": p["required"],
                    "type": p["schema"].get("type", "string"),
                    **({"description": p["description"][:200]} if p.get("description") else {}),
                }
                for name, p in op.parameters.items()
            ],
        }

    def search(self, text: str, limit: int = 100) -> list[dict[str, Any]]:
        words = text.lower().split()
        out = []
        for op in self.description.operations.values():
            if op.method != "GET" and op.id not in self.settings.read_operations:
                continue
            if all(w in f"{op.id} {op.path} {op.summary}".lower() for w in words):
                out.append(self._view(op))
        return out[:limit]

    def describe(self, operation: str) -> dict[str, Any] | None:
        op = self.description.operations.get(operation)
        if op is None:
            return None
        view = self._view(op)
        if op.response is not None:
            schema = self.description.schema(op.response)
            # A list body, or the first list property (such as `value` or `data`), holds the items.
            items, prefix = None, ""
            if schema.get("type") == "array":
                items = schema.get("items")
            else:
                for name, child in (schema.get("properties") or {}).items():
                    child = self.description.schema(child)
                    if child.get("type") == "array":
                        items, prefix = child.get("items"), name
                        break
            if items is not None:
                view["items"] = prefix
                view["fields"] = [{**f, "items": prefix} for f in self.description.fields_of(items)]
        return view

    def validate(
        self, spec: QuerySpec, name: str | None = None
    ) -> tuple[list[Problem], dict[str, Any] | None]:
        query = openapi.Query(
            spec.operation,
            spec.params,
            spec.items,
            spec.fields,
            for_each=openapi.ForEach.from_json(spec.for_each) if spec.for_each else None,
        )
        problems, schema = openapi.validate(self.description, self.settings, query, name=name)
        if spec.regions:
            problems.append(Problem("/regions", "regions apply to AWS (Smithy) query sources only"))
        return problems, schema


class SmithyModel:
    kind: Literal["smithy"] = "smithy"

    def __init__(self, api: smithy.Api) -> None:
        self.api = api

    def _view(self, op: smithy.Operation) -> dict[str, Any]:
        service = self.api.settings.services.get(op.service)
        return {
            "id": op.name,
            "method": op.method,
            "path": op.uri,
            "summary": op.summary,
            "protocol": op.protocol,
            "regional": bool(service and service.regional),
            "queryable": op.readable,
            **({"reason": op.reason} if op.reason else {}),
            "parameters": [],
        }

    def search(self, text: str, limit: int = 100) -> list[dict[str, Any]]:
        return [self._view(op) for op in self.api.search(text, limit)]

    def describe(self, operation: str) -> dict[str, Any] | None:
        op = self.api.operations.get(operation)
        if op is None:
            return None
        described = self.api.describe(operation)
        items = described["items"]
        return {
            **self._view(op),
            "parameters": [
                {
                    "name": p["name"],
                    "in": "json" if p["json"] else "value",
                    "required": p["required"],
                    "type": p["type"],
                }
                for p in described["params"]
            ],
            "items": items,
            "fields": [{**f, "items": items} for f in described["fields"]],
        }

    def validate(
        self, spec: QuerySpec, name: str | None = None
    ) -> tuple[list[Problem], dict[str, Any] | None]:
        query = smithy.Query(
            spec.operation,
            spec.params,
            spec.items,
            spec.fields,
            regions=spec.regions or [],
            for_each=smithy.ForEach.from_json(spec.for_each) if spec.for_each else None,
        )
        return smithy.validate(self.api, query, name=name)
