"""Verify ogrl_rs integration: XML OSCAL component import, 12-file OSCAL render, and defaults."""

from datetime import UTC, datetime

from fathom import container
from fathom.adapters.library import DirectoryLibrary, GitLibrary
from fathom.importer.oscal_component import OscalComponentImporter
from fathom.kernel.graph import Graph
from fathom.kernel.models import parse
from fathom.plugins.ports import RenderRequest
from fathom.renderer.oscal import OscalRenderer
from tests.conftest import C1, LIB_BASELINE, library_objects

SAMPLE_OSCAL_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<component-definition
    xmlns="http://csrc.nist.gov/ns/oscal/1.0"
    uuid="11111111-1111-4111-8111-111111111111">
  <metadata>
    <title>Example XML Provider</title>
    <last-modified>2026-11-20T00:00:00Z</last-modified>
    <version>1.0.0</version>
    <oscal-version>1.2.3</oscal-version>
  </metadata>
  <component uuid="22222222-2222-4222-8222-222222222222" type="service">
    <title>Managed Vault</title>
    <description>Secrets management service.</description>
    <control-implementation
        uuid="33333333-3333-4333-8333-333333333333"
        source="https://example.com/nist_sp-800-53_rev5_catalog.json">
      <description>800-53 controls</description>
      <implemented-requirement
          uuid="44444444-4444-4444-8444-444444444444"
          control-id="ac-2">
        <prop name="control-origination" value="inherited"/>
        <description>Provider manages tenant accounts.</description>
      </implemented-requirement>
    </control-implementation>
  </component>
</component-definition>
"""


def test_oscal_component_importer_accepts_xml():
    lib = [parse(o) for o in library_objects()]
    graph = Graph(lib, library_ids=[o.id for o in lib])
    imported = OscalComponentImporter().import_bytes(SAMPLE_OSCAL_XML, graph)
    assert imported.id == "bundle--11111111-1111-4111-8111-111111111111"
    assert imported.name == "Example XML Provider"
    assert imported.version == "1.0.0"
    assert not imported.warnings
    impls = [o for o in imported.objects if o.type == "implementation"]
    assert len(impls) == 1
    assert impls[0].requirement_ref == "requirement--nist-sp-800-53-r5-ac-2"
    assert impls[0].responsibility == "provider"


def test_oscal_renderer_opt_in_xml_emits_twelve_documents():
    lib = [parse(o) for o in library_objects()]
    stamp = "2026-11-20T00:00:00Z"
    org = [
        parse(
            {
                "type": "system",
                "id": "system--com.acme.prod",
                "created": stamp,
                "modified": stamp,
                "name": "Prod",
            }
        ),
        parse(
            {
                "type": "program",
                "id": "program--com.acme.fed",
                "created": stamp,
                "modified": stamp,
                "name": "Fed",
                "system_ref": "system--com.acme.prod",
                "baseline_ref": LIB_BASELINE,
            }
        ),
        parse(
            {
                "type": "implementation",
                "id": "implementation--com.acme.ac1",
                "created": stamp,
                "modified": stamp,
                "system_ref": "system--com.acme.prod",
                "control_ref": C1,
                "status": "implemented",
                "responsibility": "provider",
                "narrative": "SSO enforced.",
            }
        ),
    ]
    graph = Graph([*lib, *org], library_ids=[o.id for o in lib])
    req = RenderRequest(
        graph=graph,
        program=graph.program("program--com.acme.fed"),
        at=datetime(2026, 11, 20, tzinfo=UTC),
        framework_id="framework--nist-sp-800-53-r5",
    )
    files = OscalRenderer(include_xml=True).render(req)
    names = {f.name for f in files}
    assert len(files) == 12
    assert "ssp.json" in names and "ssp.xml" in names
    assert "profile.json" in names and "profile.xml" in names
    assert b"<system-security-plan" in next(f.content for f in files if f.name == "ssp.xml")


def test_default_library_source_resolves_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(container, "REPOSITORY_LIBRARY", tmp_path / "missing-repo-lib")
    monkeypatch.setattr(container, "SIBLING_LIBRARY", tmp_path / "missing-sibling-lib")
    src = container.default_library_source()
    assert isinstance(src, GitLibrary)
    assert src._repository == container.DEFAULT_LIBRARY_REPO

    sibling = tmp_path / "sibling-lib"
    sibling.mkdir()
    (sibling / "bundle.yaml").write_text("type: bundle\n", encoding="utf-8")
    monkeypatch.setattr(container, "SIBLING_LIBRARY", sibling)
    assert isinstance(container.default_library_source(), DirectoryLibrary)
