"""The route catalog and api/openapi.yaml must agree on every operationId we serve."""

from pathlib import Path

import pytest
import yaml

from fathom.api.paths import all_endpoints

SPEC = yaml.safe_load((Path(__file__).parents[1] / "api" / "openapi.yaml").read_text())

OPERATIONS = {
    op["operationId"]: (method.upper(), path, op)
    for path, item in SPEC["paths"].items()
    for method, op in item.items()
    if isinstance(op, dict) and "operationId" in op
}


@pytest.mark.parametrize("endpoint", all_endpoints(), ids=lambda e: e.id)
def test_endpoint_matches_spec(endpoint):
    assert endpoint.id in OPERATIONS, f"{endpoint.id} is not in api/openapi.yaml"
    method, path, op = OPERATIONS[endpoint.id]
    assert (endpoint.method.value, endpoint.path) == (method, path)
    assert str(int(endpoint.success_status)) in op["responses"]
    public = op.get("security") == []
    assert endpoint.authenticated != public


def test_catalog_ids_are_unique():
    ids = [e.id for e in all_endpoints()]
    assert len(ids) == len(set(ids))
