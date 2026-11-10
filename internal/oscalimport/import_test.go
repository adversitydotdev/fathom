package oscalimport

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const fixture = `{
  "catalog": {
    "metadata": {
      "title": "Fixture",
      "last-modified": "2026-10-22T11:30:00.00000-00:00",
      "version": "5.2.0",
      "oscal-version": "1.2.3"
    },
    "groups": [{
      "id": "ac",
      "controls": [{
        "id": "ac-2",
        "class": "SP800-53",
        "title": "Account Management",
        "params": [{
          "id": "ac-02_odp.01",
          "label": "frequency",
          "props": [{"name": "alt-identifier", "value": "ac-2_prm_1"}]
        }],
        "props": [
          {"name": "label", "value": "AC-02", "class": "zero-padded"},
          {"name": "label", "value": "AC-2"},
          {"name": "sort-id", "value": "ac-02"}
        ],
        "links": [
          {"href": "#pub", "rel": "reference"},
          {"href": "#ac-1", "rel": "related"}
        ],
        "parts": [{
          "id": "ac-2_smt",
          "name": "statement",
          "parts": [{
            "id": "ac-2_smt.a",
            "name": "item",
            "props": [{"name": "label", "value": "a."}],
            "prose": "Review accounts {{ insert: param, ac-2_prm_1 }}.",
            "parts": [{
              "id": "ac-2_smt.a.1",
              "name": "item",
              "props": [{"name": "label", "value": "1."}],
              "prose": "Include emergency accounts."
            }]
          }]
        }],
        "controls": [{
          "id": "ac-2.1",
          "class": "SP800-53-enhancement",
          "title": "Automated System Account Management",
          "props": [
            {"name": "label", "value": "AC-02(01)", "class": "zero-padded"},
            {"name": "label", "value": "AC-2(1)"},
            {"name": "status", "value": "withdrawn"}
          ],
          "links": [{"href": "#ac-2_smt.a", "rel": "incorporated-into"}],
          "parts": [{
            "id": "ac-2.1_smt",
            "name": "statement",
            "prose": "Support the management of system accounts using {{ insert: param, ac-02_odp.01 }}."
          }]
        }]
      }]
    }],
    "back-matter": {
      "resources": [{
        "uuid": "pub",
        "title": "SP 800-162",
        "rlinks": [{"href": "https://csrc.nist.gov/publications/detail/sp/800-162"}]
      }]
    }
  }
}`

const fixture171 = `{
  "catalog": {
    "metadata": {
      "title": "Fixture 171",
      "last-modified": "2026-10-22T11:30:00Z",
      "version": "1.1.0"
    },
    "groups": [{
      "id": "03.01",
      "controls": [{
        "id": "SP_800_171_03.01.01",
        "class": "requirement",
        "title": "Account Management",
        "props": [
          {"name": "sort-id", "value": "03.01.01"},
          {"name": "label", "value": "Account Management (03.01.01)"}
        ],
        "links": [
          {"href": "#ac02", "rel": "reference"},
          {"href": "#guide", "rel": "reference"}
        ],
        "parts": [{
          "id": "stmt",
          "name": "statement",
          "parts": [{
            "name": "item",
            "props": [{"name": "label", "value": "SR-03.01.01.a"}],
            "prose": "Define the types of system accounts allowed and prohibited."
          }]
        }]
      }, {
        "id": "SP_800_171_03.01.14",
        "class": "requirement",
        "title": "03.01.14",
        "props": [
          {"name": "sort-id", "value": "03.01.14"},
          {"name": "status", "value": "withdrawn"}
        ],
        "links": [{"href": "03.01.01", "rel": "incorporated_into"}]
      }]
    }],
    "back-matter": {
      "resources": [
        {"uuid": "ac02", "title": "AC-02", "rlinks": [{"href": "https://csrc.nist.gov/projects/cprt/catalog"}]},
        {"uuid": "guide", "title": "SP 800-162", "rlinks": [{"href": "https://csrc.nist.gov/publications/detail/sp/800-162"}]}
      ]
    }
  }
}`

func TestImportFixture(t *testing.T) {
	dir := t.TempDir()
	result, err := Import([]byte(fixture), Options{
		FrameworkID: "nist-sp-800-53-r5",
		Name:        "NIST SP 800-53 Revision 5",
		OutDir:      dir,
		SourcePath:  "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
		Commit:      "abc",
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Requirements != 2 || result.Withdrawn != 1 || result.Mappings != 1 {
		t.Fatalf("counts = %+v", result)
	}

	body, err := os.ReadFile(filepath.Join(dir, "requirement", "nist-sp-800-53-r5", "ac-2.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	text := string(body)
	for _, want := range []string{
		"id: requirement--nist-sp-800-53-r5-ac-2",
		"display_id: AC-2",
		"class: control",
		"{{ ac_02_odp_01 }}",
		"id: a",
		"id: a.1",
		"description: SP 800-162",
		"source: NIST",
	} {
		if !strings.Contains(text, want) {
			t.Errorf("ac-2.yaml missing %q\n%s", want, text)
		}
	}
	if strings.Contains(text, "insert: param") {
		t.Errorf("oscal insert left in prose:\n%s", text)
	}

	enh, err := os.ReadFile(filepath.Join(dir, "requirement", "nist-sp-800-53-r5", "ac-2-1.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	enhText := string(enh)
	for _, want := range []string{
		"display_id: \"AC-2(1)\"",
		"class: enhancement",
		"withdrawn: true",
		"label: frequency",
		"{{ ac_02_odp_01 }}",
	} {
		if !strings.Contains(enhText, want) {
			t.Errorf("enhancement missing %q\n%s", want, enhText)
		}
	}

	mapping, err := os.ReadFile(filepath.Join(dir, "mapping", "nist-sp-800-53-r5-ac-2-1_to_nist-sp-800-53-r5-ac-2_part_a.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	mapText := string(mapping)
	for _, want := range []string{
		"source_ref: requirement--nist-sp-800-53-r5-ac-2-1",
		"target_ref: \"requirement--nist-sp-800-53-r5-ac-2#a\"",
		"relationship: subset-of",
		"review_status: draft",
		"rationale: semantic",
	} {
		if !strings.Contains(mapText, want) {
			t.Errorf("mapping missing %q\n%s", want, mapText)
		}
	}

	idx := result.Index
	got, err := Import([]byte(fixture171), Options{
		FrameworkID: "nist-sp-800-171-r3",
		Name:        "NIST SP 800-171 Revision 3",
		OutDir:      dir,
		Resolve:     idx,
	})
	if err != nil {
		t.Fatal(err)
	}
	if got.Requirements != 2 || got.Withdrawn != 1 || got.Mappings != 2 {
		t.Fatalf("171 counts = %+v", got)
	}
	req, err := os.ReadFile(filepath.Join(dir, "requirement", "nist-sp-800-171-r3", "03-01-01.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	reqText := string(req)
	for _, want := range []string{
		"id: requirement--nist-sp-800-171-r3-03-01-01",
		"display_id: \"03.01.01\"",
		"id: a",
		"description: SP 800-162",
	} {
		if !strings.Contains(reqText, want) {
			t.Errorf("171 requirement missing %q\n%s", want, reqText)
		}
	}
	if strings.Contains(reqText, "AC-02") {
		t.Errorf("control reference was copied onto the requirement instead of a mapping:\n%s", reqText)
	}
	cross, err := os.ReadFile(filepath.Join(dir, "mapping", "nist-sp-800-171-r3-03-01-01_to_nist-sp-800-53-r5-ac-2.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(cross), "relationship: intersects-with") || !strings.Contains(string(cross), "review_status: draft") {
		t.Fatalf("crosswalk:\n%s", cross)
	}
}

func TestWrapKeepsParametersIntact(t *testing.T) {
	lines := wrap("Create accounts in accordance with {{ ac_02_odp_04 }}; and stop.", 40)
	joined := strings.Join(lines, " ")
	if !strings.Contains(joined, "{{ ac_02_odp_04 }};") {
		t.Fatalf("placeholder split across words: %#v", lines)
	}
	for _, line := range lines {
		if strings.Contains(line, "{{") && !strings.Contains(line, "}}") {
			t.Fatalf("placeholder split across lines: %#v", lines)
		}
	}
}

func TestNISTCatalogs(t *testing.T) {
	path53 := os.Getenv("OGRC_OSCAL_53")
	path171 := os.Getenv("OGRC_OSCAL_171")
	if path53 == "" || path171 == "" {
		t.Skip("set OGRC_OSCAL_53 and OGRC_OSCAL_171 to run")
	}
	raw53, err := os.ReadFile(path53)
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	got53, err := Import(raw53, Options{FrameworkID: "nist-sp-800-53-r5", Name: "NIST SP 800-53 Revision 5", OutDir: dir})
	if err != nil {
		t.Fatal(err)
	}
	if got53.Requirements != 1196 || got53.Withdrawn != 182 || got53.Mappings != 199 {
		t.Fatalf("53 counts = %+v", got53)
	}
	ac2, err := os.ReadFile(filepath.Join(dir, "requirement", "nist-sp-800-53-r5", "ac-2.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(ac2), "display_id: AC-2") || strings.Contains(string(ac2), "insert: param") {
		t.Fatalf("ac-2 was not rewritten:\n%s", ac2[:800])
	}

	raw171, err := os.ReadFile(path171)
	if err != nil {
		t.Fatal(err)
	}
	got171, err := Import(raw171, Options{
		FrameworkID: "nist-sp-800-171-r3",
		Name:        "NIST SP 800-171 Revision 3",
		OutDir:      dir,
		Resolve:     got53.Index,
	})
	if err != nil {
		t.Fatal(err)
	}
	if got171.Requirements != 130 || got171.Withdrawn != 33 || got171.Mappings != 198 {
		t.Fatalf("171 counts = %+v", got171)
	}
}
