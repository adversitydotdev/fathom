# RFC 0001: OpenGRC Object Model

| | |
|---|---|
| Status | Draft |
| Spec version | 0.1.0 |
| Date | 2026-11-08 |

This document is the proposal for the OpenGRC language: the objects tools exchange when they talk about controls, implementations, evidence, policies, and risk. It is written so it can be edited in place. The open questions at the end are the spots most likely to move during review.

OpenGRC the application is a later project. This RFC is only the language that application, and any other tool, will read and write.

## 1. Summary

OpenGRC defines a graph of typed objects. Each object is one YAML file. A set of objects travels between tools as a JSON bundle. Catalogs, SSPs, and dashboards are views produced by walking the graph. They are not document types in the model.

The language plays the role for GRC that STIX plays for threat intelligence. A control, a mapping, or a piece of evidence can be exchanged on its own. A tool can implement part of the model and still interoperate, provided it preserves fields it does not understand.

OSCAL remains the import and export bridge for NIST catalogs and for federal tooling. People author OpenGRC YAML. Compilers turn OSCAL catalogs into `requirement` objects, including the assessor's questions on each requirement. Renderers turn a system, its components, and its implementations into an SSP, and turn findings and risks into an assessment package.

## 2. Motivation

Companies run one security program and account for it under several frameworks. SOC 2, ISO/IEC 27001, HIPAA, NIST SP 800-53, NIST SP 800-171, and CMMC ask overlapping questions in different identifiers. Products such as Vanta, Drata, and Secureframe hide that overlap behind a private control library. OpenGRC publishes the library and the mapping rules so a program can move between tools.

The language has to come before the dashboard, the automations, and the self-hosted app. Those products will only be as good as the objects they share. A control written by hand, a control created through an API, and a control emitted by a future connector need the same shape.

OSCAL already models catalogs, profiles, mappings, and SSPs, and NIST publishes SP 800-53 Rev 5 and SP 800-171 Rev 3 in it. OSCAL's unit is a large document: groups contain controls, controls contain parts, an SSP contains every narrative. Reading one control means opening a file the size of the catalog. Links often point at UUIDs. The authoring surface is a stack of `props` pairs carried over from XML. Tools end up inventing their own object layer above OSCAL, and that private layer is where interoperability goes to die.

STIX shows the other shape. The unit is an object with a type, a stable id, and a `modified` time. Relationships that carry meaning are objects. A bundle is a bag of objects. Documents are something a tool renders.

## 3. Goals

- One object model for the standard library and for a company's live program.
- Authoring that a person can review in git: one object, one file, prose in YAML.
- A JSON exchange form that is the same model, so a tool without a repository can still speak it.
- Honest mappings. A control contributes to a framework requirement, and the relationship says whether the contribution covers the requirement or only part of it.
- A defined way to compute whether a control is met, so two dashboards agree on the same bundle.
- An executable testing methodology on a test, so an organization can define how a control is checked. A later harness runs that methodology and writes the `result` and `evidence` objects.
- Room for company-authored controls, policies, risks, and evidence without a spec change.
- Import of public NIST catalogs from OSCAL, including assessment objectives, and a path to render an SSP, a component definition, an assessment result, and a plan of action and milestones, without making OSCAL the authoring format.

## 4. Non-goals

- The application, the UI, connectors, and account system. The harness that executes a test is in this set. The contract it will implement is in [Tests](#76-test).
- Replacing OSCAL inside federal authorization tooling. OpenGRC compiles to and from it where that helps.
- A CMDB, a vendor register beyond a party, ticketing, training records, or audit-engagement workflow.
- Publishing AICPA Trust Services Criteria text or ISO/IEC 27001 text. See [External catalogs and copyright](#10-external-catalogs-and-copyright).
- Transitive closure over mappings. If A maps to B and B maps to C, nothing is asserted about A and C until someone reviews a direct mapping.

## 5. Principles

**The object is the unit.** A catalog is a query over `control` and `requirement` objects. An SSP is a render of a `system`, a `program`, and its `implementation` objects. The source of truth is the graph.

**The id is the address.** References use ids. They never use file paths, and they never embed the target object.

**Edges follow one of three rules.**

| Kind of fact | Where it lives | Examples |
|---|---|---|
| Intrinsic to the author of the object | A field on that object | A test names its control. A policy names the controls it governs. |
| A crosswalk with a relationship and a rationale | A `mapping` object | OGRC-AC-01 intersects CC6.1. |
| Operational state with a lifecycle | Its own object | How production carries out OGRC-AC-01. |

A control file does not list framework ids. Mappings change when frameworks are revised. The control changes when the practice changes.

**Our controls read as practices. Imported requirements keep their legal structure.** An OpenGRC control has a summary, a statement, an objective, and guidance. That objective is the practice's success condition, in one sentence. Lettered parts exist on external requirements, because NIST AC-2(a) and AC-2(g) are different obligations. Assessment objectives on a requirement are the assessor's questions, and they are separate from the control's objective.

**Status is computed.** Objects store observations, narratives, and expiry. They do not store a rolled-up "compliant" flag.

**Unknown fields survive a round trip.** A tool that does not implement an extension still has to write it back out. The producer of an object is the only one who advances `modified`. There is one exception. A store that holds a projection of someone else's publication sets `revoked: true` on an id that publication no longer contains, and sets `modified` to the time it did so, because the producer is no longer speaking for that id.

## 6. Serialization and identity

### 6.1 YAML and JSON

YAML 1.2 is the authoring form. Canonical JSON is the wire form and the form tools hash and compare. Canonical JSON is the JSON Canonicalization Scheme, RFC 8785. Timestamps and calendar dates are JSON strings. YAML 1.2 is a superset of JSON, so a JSON bundle is valid YAML.

Authoring rules:

- One object per file.
- Two-space indentation.
- Folded scalars (`>`) for prose.
- No anchors, aliases, or merge keys.
- Omit a field when it has no value. Null is invalid.
- Comments are non-normative and are dropped in the canonical form.
- Timestamps are RFC 3339 in UTC (`2026-11-08T00:00:00Z`). Calendar dates (`2026-11-08`) are used for expiry, adoption, and review dates.

### 6.2 Envelope

Every object has these fields.

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | One of the types in [section 7](#7-types). |
| `id` | yes | See below. |
| `spec_version` | yes | Language version. This RFC is `0.1.0`. |
| `created` | yes | When this id was first minted. Never changes. |
| `modified` | yes | When the producer last changed any field of the object. A new revision is the same id and a strictly later `modified`. A producer that writes more than once a second uses fractional seconds. |
| `name` | yes, except `mapping`, `mapping_review`, `implementation`, `result`, and `exception` | Human title. The excepted types are identified by what they point at, and may still carry a name. |
| `revoked` | no | Defaults to `false`. A revoked id is never reused. |
| `created_by_ref` | no | `party` id of the producer. |
| `tags` | no | List of strings. |
| `external_references` | no | Citations. Each entry may include `source`, `url`, and `description`. |
| `extensions` | no | Map of extension objects, keyed by the extension owner's domain. |
| `lang` | no | BCP 47 language tag. Defaults to `en`. |

`spec_version` is the language. A bundle's `version` is the content release of a library. Those move independently.

A bundle's objects share one `spec_version`. Mixing language versions in one bundle is out of scope for 0.1.0.

`spec_version` is `major.minor.patch`. A patch release clarifies text and changes no object. A minor release may add an optional field, an enum value, or a type. A major release may remove or redefine one. While the major version is 0, a minor release may also break, and it says so. A reader accepts an object whose major and minor it implements, at any patch. It refuses any other version and does not guess. A type added in a minor release is part of the closed set from that release on.

### 6.3 Identifiers

An id is `type--remainder`, split on the first `--`. The type is lowercase ASCII letters and underscores. The remainder is lowercase ASCII letters, digits, and three separators: hyphen, dot, and underscore. It starts and ends with a letter or a digit, and it contains no `--`. A dot appears where a publisher's identifier or a domain has one (`cc6.1`, `com.acme`). An underscore appears only in the `_to_` and `_part_` joins of a derived mapping id. Every one of those characters is safe in a filename and in a URL path segment.

Two issuers:

- **Standard library.** Readable slugs the project mints and never reuses. `control--ogrc-ac-01`, `requirement--soc2-tsc-2017-cc6.1`.
- **Everyone else.** A UUID, or a slug prefixed by a domain they control: `control--com.acme.badge-access`. Bare slugs such as `control--ac-01` are reserved for the standard library.

`display_id` is the label a person sees in a UI: `OGRC-AC-01`, `CC6.1`, `AC-2`, `AC-2(1)`, `3.1.1`, `A.5.15`. The display id may contain parentheses, spaces, and uppercase. The object id does not.

Official punctuation stays in `display_id` and, where useful, in `citation` on a requirement. The slug form of an enhancement is `ac-2-1` for NIST AC-2(1).

Standard-library mapping ids are derived from their ends so there is one file per pair. A dot in a part id becomes a hyphen after `_part_`. A mapping an organization authors uses a UUID or a domain slug like any other organization object, and the one-per-pair rule in [Graph constraints](#720-graph-constraints) holds without the id.

```text
mapping--ogrc-ac-01_to_soc2-tsc-2017-cc6.1
mapping--ogrc-ac-01_to_nist-sp-800-53-r5-ac-2_part_a
```

A reference to a statement part uses a fragment on the requirement id: `requirement--nist-sp-800-53-r5-ac-2#a`. A reference to an assessment objective uses `#obj.` plus the objective id: `requirement--nist-sp-800-53-r5-ac-2#obj.a`. The fragment is part of the reference, not part of the requirement's own id.

### 6.4 References

A field ending in `_ref` is one id. A field ending in `_refs` is a list of ids. Lists of refs are unordered. Dangling refs are errors in a self-contained bundle and warnings when a tool has loaded only part of a graph.

### 6.5 Bundles

Repository form. A manifest describes the set, and each object is a sibling file discovered by scanning. `objects` is omitted.

```yaml
type: bundle
id: bundle--ogrc-library
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: OpenGRC Control Library
version: 0.1.0
```

Exchange form. The same manifest inlines every object in `objects`. This is the document a tool can POST or sign.

```yaml
type: bundle
id: bundle--ogrc-library
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: OpenGRC Control Library
version: 0.1.0
objects:
  - type: control
    id: control--ogrc-ac-01
    spec_version: 0.1.0
    # remaining fields of each object
```

Filename convention, when a tool is storing one object per file: the path is `{type}/{remainder}.yaml`. `control--ogrc-ac-01` lives at `control/ogrc-ac-01.yaml`. The path is a convention. The id is normative, and an object stays valid if it is lifted out of the file.

## 7. Types

The set is closed. New controls, risks, and policies are new objects. A new type is a new spec version.

| Type | Question it answers | Side |
|---|---|---|
| `framework` | Which publication, which revision? | Library |
| `requirement` | What does that publication demand? | Library |
| `control` | What practice do we implement and test? | Library or organization |
| `mapping` | How does a control or requirement relate to a requirement? | Library or organization |
| `baseline` | Which controls and which requirements make up a program? | Library or organization |
| `test` | How is the control checked, repeatedly? | Library or organization |
| `party` | Who owns it? | Organization |
| `component` | What reusable piece of the boundary carries a practice? | Organization |
| `system` | What is in scope? | Organization |
| `program` | Which baseline is this system pursuing? | Organization |
| `implementation` | How does this system, or this component, carry out this control? | Organization |
| `result` | What happened the last time we checked? | Organization |
| `finding` | What did an assessor determine about one objective? | Organization |
| `evidence` | What artifact supports that, and until when? | Organization |
| `policy` | What has the organization mandated? | Organization |
| `procedure` | What steps do people follow? | Organization |
| `risk` | What might go wrong, and what is being done? | Organization |
| `exception` | Where is a control formally waived, and until when? | Organization |
| `mapping_review` | Does this organization accept a mapping it did not write? | Organization |

`mapping_review` is defined in [RFC 0002](0002-tooling.md), with the pull it exists for.

A tool may implement only the library types and still be a conforming reader of the standard. A GRC application implements the operational types as well. See [Conformance](#11-conformance).

Digest values in the examples below are placeholders.

### 7.1 `framework`

```yaml
type: framework
id: framework--nist-sp-800-53-r5
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: NIST SP 800-53 Revision 5
publisher: NIST
version: "5.2.0"
reproduction: permitted            # permitted | citation-only
source:
  format: oscal-catalog
  uri: https://github.com/usnistgov/oscal-content
  path: nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
```

`reproduction: citation-only` means requirement objects for that framework carry identifiers and titles we write, and they do not carry the publisher's text. SOC 2 and ISO/IEC 27001 use `citation-only`. NIST publications and the Code of Federal Regulations use `permitted`.

### 7.2 `requirement`

A requirement is an external obligation. Enhancements are their own requirements, because they are withdrawn and revised on their own. Letters inside a requirement are `parts`.

```yaml
type: requirement
id: requirement--soc2-tsc-2017-cc6.1
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
display_id: CC6.1
name: Logical access security software, infrastructure, and architectures
framework_ref: framework--soc2-tsc-2017
class: criterion                   # criterion | control | enhancement | clause | specification
external_references:
  - source: AICPA
    description: 2017 Trust Services Criteria, CC6.1
```

```yaml
type: requirement
id: requirement--nist-sp-800-53-r5-ac-2
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
display_id: AC-2
name: Account Management
framework_ref: framework--nist-sp-800-53-r5
class: control
parameters:
  ac_02_odp_10:
    label: frequency
parts:
  - id: a
    statement: >
      Define and document the types of accounts allowed and
      specifically prohibited for use within the system;
  - id: j
    statement: >
      Review accounts for compliance with account management
      requirements {{ ac_02_odp_10 }};
```

This example is abridged. The imported AC-2 has ten parameters and parts `a` through `l`.

`withdrawn: true` means the publisher retired the obligation. NIST withdrew AC-13 and incorporated it into AC-2 and AU-6. Omitted means `false`. A withdrawn requirement is still a valid object, and its id still resolves, because old crosswalks and old findings point at it. It carries no obligation: it is never in a baseline's requirements, it is not reported by requirement coverage, and it usually has no statement. A mapping whose source is a withdrawn requirement records where the publisher sent it, and stays.

Withdrawn is not revoked. `withdrawn` is the publisher's statement about the obligation. `revoked` on the envelope is the producer's statement about the object: the id was published in error, or the library no longer carries it. A pull that finds a library id missing sets `revoked`. It never sets `withdrawn`.

`class` records the publisher's kind of obligation: a SOC 2 criterion, a NIST control, a NIST enhancement, an ISO clause, a HIPAA implementation specification. It does not change how mappings work.

`objectives` are the assessor's questions for this requirement. They are how SP 800-53A and SP 800-171A score a control. The id is local to the requirement, the same way a part id is. A reference uses the `#obj.` fragment from [section 6.3](#63-identifiers).

```yaml
objectives:
  - id: a
    statement: >
      Determine if the types of accounts allowed for use within
      the system are defined and documented.
    methods:
      - method: examine          # examine | interview | test
        statement: Account management policy.
      - method: interview
        statement: Personnel with account management responsibilities.
```

`methods` is optional. The method token is the assessor's kind of procedure. The statement under it is prose. Nothing in `methods` is executed by the harness. A test that answers the question points at the objective. See [Tests](#76-test).

### 7.3 `control`

A control is one auditable practice. A team can implement it, and an auditor can test it with one evidence pattern.

`statement` and `objective` are normative. `guidance` is informative, and a conforming tool may ignore it. `{{ parameter }}` interpolates a parameter name. The braces contain a name and nothing else.

`origin: standard` marks the OpenGRC library. Company controls use `origin: custom`.

```yaml
type: control
id: control--ogrc-ac-01
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
display_id: OGRC-AC-01
name: Unique identities
origin: standard                   # standard | custom
family: ac
control_type: preventive           # preventive | detective | corrective
frequency: continuous              # continuous | daily | weekly | monthly | quarterly | annual | event-driven
summary: >
  Every person and every service account has its own identity.
statement: >
  The organization assigns a unique identity to each workforce
  user and each service account. Shared credentials are prohibited
  unless inventoried, owned, and approved, and the inventory is
  reviewed {{ shared_account_review }}.
objective: >
  Every active account can be traced to one owner, and every
  approved shared account appears on the inventory.
guidance: >
  Workforce users live in the IdP. Service accounts are owned by
  a team. Break-glass credentials count as shared accounts.
parameters:
  shared_account_review:
    label: how often shared accounts are reviewed
    value: quarterly
```

Parameter values resolve in this order, highest first:

1. `implementation.parameter_values`
2. `baseline.parameter_bindings` for the program in force
3. `control.parameters[].value`

A control is not met for a program while any parameter named in the resolved statement is unset for that program. That is a status rule in [section 8](#8-computed-status) and not a constraint on the implementation, because the baseline that may supply the value belongs to the program, and one implementation can serve two programs.

`frequency` on a control says how often the practice operates. It is descriptive and does not enter section 8. How often the practice is checked is `interval` on each test. A NIST organization-defined parameter takes its value through the binding in [Mappings](#74-mapping). Until that binding resolves, the SSP export leaves the NIST parameter unset.

Standard families for `origin: standard` controls:

| `family` | Covers |
|---|---|
| `gv` | Policies, roles, oversight, the compliance calendar |
| `rm` | Risk assessment and risk treatment |
| `am` | Systems, data, and owners |
| `hr` | Hiring, termination, responsibility |
| `ac` | Identities, least privilege, reviews, removal |
| `cm` | Change and configuration management |
| `sd` | Secure development and release |
| `lm` | Logging, alerting, time sync |
| `ir` | Response, evidence, notification |
| `vm` | Scanning, patching, endpoint hardening |
| `cr` | Cryptography, retention, disposal |
| `tp` | Vendors and subservice organizations |
| `bc` | Backup, recovery, capacity |
| `ps` | Facilities and media |

Custom controls may use these families or a token of their own. The first library targets 80 to 120 controls covering SOC 2 Security, Availability, Confidentiality, and Processing Integrity. Privacy criteria are a later family.

Display ids for standard controls are `OGRC-{FAMILY}-{NN}`, zero-padded, with the family in uppercase. `OGRC-AC-01` corresponds to id `control--ogrc-ac-01`. The number is never reused inside a family.

### 7.4 `mapping`

Mappings are the only crosswalk. `source_ref` is a control or a requirement. `target_ref` is a requirement, optionally with a `#part` fragment.

```yaml
type: mapping
id: mapping--ogrc-ac-01_to_soc2-tsc-2017-cc6.1
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
source_ref: control--ogrc-ac-01
target_ref: requirement--soc2-tsc-2017-cc6.1
relationship: intersects-with
rationale: functional
review_status: reviewed
confidence: high
summary: >
  Unique identities are necessary for CC6.1. Removal, reviews,
  and authentication are other controls.
```

```yaml
type: mapping
id: mapping--ogrc-ac-01_to_nist-sp-800-53-r5-ac-2_part_a
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
source_ref: control--ogrc-ac-01
target_ref: requirement--nist-sp-800-53-r5-ac-2#a
relationship: subset-of
rationale: functional
review_status: reviewed
summary: >
  Covers identification of account types and owners.
  Review of accounts is a different control.
```

`relationship` is the OSCAL mapping vocabulary:

| Value | Meaning |
|---|---|
| `equal-to` | Same requirement. Wording differences do not change the meaning. |
| `equivalent-to` | Same effective requirement. The words differ. |
| `subset-of` | The source is narrower than the target. The target still has unmet content. |
| `superset-of` | The source covers the target and more. |
| `intersects-with` | Real overlap, with content left over on both sides. |
| `no-relationship` | Reviewed and deliberately empty. Recorded so a later import does not "fix" it. |

Direction is source relative to target. `subset-of` on a mapping from `control--ogrc-ac-01` to AC-2(a) means the OpenGRC control covers part of that part.

`rationale` records how the relationship was judged.

| Value | Meaning |
|---|---|
| `functional` | What implementing the source accomplishes. Default for OpenGRC library mappings. |
| `semantic` | Whether the texts mean the same thing. Typical of imported NIST crosswalks. |
| `syntactic` | Whether the wording matches. |

`review_status` is `draft` or `reviewed`. A customer-facing coverage claim uses `reviewed` mappings only. `confidence` is `low`, `medium`, or `high`, and it is optional.

Tools derive coverage from `relationship`. `equal-to`, `equivalent-to`, and `superset-of` count as full coverage of the cited target (the whole requirement, or the named part). `subset-of` and `intersects-with` count as contribution. There is no separate coverage field, so the two cannot contradict each other.

Practice-sized controls are usually narrower than the requirement they answer, so most honest mappings are `subset-of` or `intersects-with`. `combined_with_refs` is how a reviewer records that several of them together leave nothing over.

```yaml
type: mapping
id: mapping--ogrc-ac-01_to_nist-sp-800-53-r5-ac-2_part_a
source_ref: control--ogrc-ac-01
target_ref: requirement--nist-sp-800-53-r5-ac-2#a
relationship: subset-of
review_status: reviewed
combined_with_refs:
  - mapping--ogrc-ac-02_to_nist-sp-800-53-r5-ac-2_part_a
```

The mapping that carries the field, plus every mapping it lists, is a combined set. The claim is that the sources of the set, taken together, are `equal-to` or `superset-of` the target. Every mapping in the set has the same `target_ref`, has a control as its source, and is `subset-of` or `intersects-with`. The field is written on one mapping of the set. Each member keeps its own `relationship`, so a member alone is still shown as contribution. The set is a claim only when every member is reviewed. [Section 8](#8-computed-status) says how a set covers a target.

Requirement-to-requirement mappings are how an official crosswalk is stored, for example SP 800-171 Rev 2 to SP 800-53. They use the same object, with a requirement as `source_ref`. They are input for authors. They are not composed automatically into control-to-framework claims.

`parameter_map` binds a parameter on the target requirement to a parameter on the source control. The key is the target parameter key, such as `ac_02_odp_10`. The value is the source control's parameter name. The map belongs on the mapping whose target uses the parameter. AC-2 asks for a review frequency in part `j`, so the control that reviews accounts carries it:

```yaml
# on mapping--ogrc-ac-04_to_nist-sp-800-53-r5-ac-2_part_j
parameter_map:
  ac_02_odp_10: access_review_frequency
```
 An implementation can override one target parameter without changing the control parameter. See [Implementations](#711-implementation). A baseline can set a literal for a target parameter. See [Baselines](#75-baseline).

Resolution for one target parameter, highest first:

1. `implementation.requirement_parameter_values` on the implementation under evaluation for the source control
2. `baseline.parameter_bindings` for that requirement
3. The resolved value of the control parameter named in `parameter_map`

If two non-revoked mappings from controls in the same program name different control parameters for the same target parameter, the binding is an error and the target parameter stays unset. A target parameter with no implementation override, no baseline literal, and no `parameter_map` entry stays unset. The exporter does not invent a value.

### 7.5 `baseline`

A baseline is a selection for a stated purpose: the controls a program implements, the requirements that program is judged against, and the parameter values the selection assumes. The library publishes baselines. An organization writes its own when it adds custom controls or pursues a different set of requirements.

```yaml
type: baseline
id: baseline--soc2-s-a-c-pi
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: SOC 2 Security, Availability, Confidentiality, and Processing Integrity
framework_refs:
  - framework--soc2-tsc-2017
control_refs:
  - control--ogrc-ac-01
parameter_bindings:
  control--ogrc-ac-01:
    shared_account_review: quarterly
  requirement--nist-sp-800-53-r5-ac-2:
    ac_02_odp_01: manager approval and a documented business need
```

`parameter_bindings` keyed by a control id sets control parameters, as in the resolution order on the control. Keyed by a requirement id, it sets a literal for a target-framework parameter. The baseline literal wins over a `parameter_map` on a mapping, and loses to `requirement_parameter_values` on the implementation.

`requirement_refs` is the requirements in scope. Each entry is a whole requirement id with no fragment, and its framework is one of the baseline's `framework_refs`. When a baseline has no `requirement_refs`, its requirements are every requirement of its `framework_refs` that is neither revoked nor withdrawn. A withdrawn requirement listed in `requirement_refs` is an error. A baseline that selects part of a catalog lists them: the SP 800-53B moderate baseline, or CMMC Level 2 as the 110 requirements of SP 800-171 Rev 2. Requirement coverage in [section 8](#8-computed-status) is computed over this set and nothing else, so a requirement outside the baseline is never reported as unmapped.

A baseline may list requirements and no controls. That is a catalog selection nobody has written practices for yet. Every requirement in it reports as unmapped until controls and reviewed mappings exist.

An organization baseline usually starts from a library one. `extends_ref` names it.

```yaml
type: baseline
id: baseline--com.acme.soc2-2026
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Acme SOC 2, with badge access
extends_ref: baseline--soc2-s-a-c-pi
control_refs:
  - control--com.acme.badge-access
parameter_bindings:
  control--ogrc-ac-01:
    shared_account_review: monthly
```

The baseline in `extends_ref` has no `extends_ref` of its own. One level deep. The **effective** baseline is what a program evaluates:

- Controls are the base's `control_refs` plus this baseline's.
- Frameworks are the base's `framework_refs` plus this baseline's.
- Requirements are the base's requirements plus this baseline's, each worked out by the rule above. A baseline that extends another and names no frameworks and no requirements adds none.
- `parameter_bindings` are merged key by key. This baseline's value wins.

A baseline with no `extends_ref` is its own effective baseline. A library pull that changes the base changes every baseline that extends it, without an edit to the organization's object.

Extending only adds. A control the organization does not carry out stays on the baseline with an implementation whose status is `not-applicable` and a reason in `narrative`, so the omission is visible in the program. An organization that needs fewer requirements than a library baseline writes a baseline without `extends_ref` and lists them.

Library baselines list `origin: standard` controls only. An organization baseline may list standard and custom controls, and it uses a UUID or a domain slug for its id.

### 7.6 `test`

A test is a check definition for a control. The control states the practice. The tests that reference it state how that practice is checked. One control may have several tests. Running a test produces a `result`, and the files the run declares become `evidence`.

Library tests describe the check in `description` and usually stop there, because the command depends on the organization's identity provider, cloud, and tools. An organization authors its own test, with a `run` block, for the methodology its harness executes. `fulfills_ref` points that test at the library test it carries out, so the library check stays required and the command belongs to the organization.

`required: true` means the check gates the met-computation in [section 8](#8-computed-status). `required: false` means the check is visible and does not, on its own, keep the control from being met. Omitted means `false`. A test that sets `fulfills_ref` takes the place of the test it fulfills, so its own `required` is not read.

`interval: continuous` and `interval: daily` have the same one-day window in section 8. `continuous` tells the harness to run the check as often as it can.

```yaml
type: test
id: test--ogrc-ac-01-unique-idp-users
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Active IdP users are unique
control_ref: control--ogrc-ac-01
objective_refs:
  - requirement--nist-sp-800-53-r5-ac-2#obj.a
method: automated                  # automated | manual
interval: monthly
required: true
description: >
  Fail if two active users share an employee identifier, or if an
  active user has no identifier.
```

An organization test that fulfills the library check:

```yaml
type: test
id: test--9f1c2d3e-4a5b-4c6d-8e7f-001122334455
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Active IdP users are unique
control_ref: control--ogrc-ac-01
fulfills_ref: test--ogrc-ac-01-unique-idp-users
method: automated
interval: monthly
description: >
  Export workforce users from the IdP and fail when two active
  users share an employee identifier.
run:
  runner: shell
  timeout: 5m
  env:
    - IDP_TENANT
  command: |
    set -eu
    ./checks/unique-idp-users.sh
  evidence:
    - path: idp-users.json
      name: IdP user export
      media_type: application/json
```

`method: manual` never has a `run` block. A manual test may set `procedure_ref` to the procedure operators follow. Library tests do not point at an organization's procedures. `method: automated` may omit `run` when the test only describes the check. A harness executes a test only when `run` is present.

`fulfills_ref` points at a test with the same `control_ref`. The target has no `fulfills_ref` of its own. One level deep. When any non-revoked test fulfills a library test, those organization tests are the methodology for it, and the library test's own results no longer count toward status.

`system_refs` is optional on an organization test. It lists the systems whose implementations the test checks. A test without it applies to every system. An organization that checks one control two ways, one identity provider for one system and a second for another, writes two fulfilling tests and names the system on each. Only the tests that apply to a program's system replace the library test for that program. Library tests and provider tests do not set `system_refs`.

`objective_refs` names the assessment objectives this check is designed to answer. Each entry is a requirement id plus an `#obj.` fragment. The harness copies the list onto the result. A result may carry a shorter list when a run covered only some of the test's objectives. The list does not change the pass or fail outcome.

**`run` for `runner: shell`.** This is the one runner defined in this revision. `runner` is an open token so a later revision can add others (`http`, a query, a policy engine) without moving the block. A harness that does not recognize `runner` does not execute the test. It records a `result` with `outcome: error` and preserves the object.

| Field | Required | Meaning |
|---|---|---|
| `runner` | yes | `shell` in this revision. |
| `command` | yes | Script body the harness writes to a file and executes with `sh`. |
| `timeout` | no | Positive integer plus `s` or `m`. Defaults to `5m`. Upper bound `60m`. |
| `env` | no | Environment variable names the script reads. Values are not in the object. |
| `evidence` | no | Files the script writes, which the harness turns into `evidence` objects. |
| `evidence[].path` | yes, per entry | Relative to the scratch directory. No absolute path, and no `..`. |
| `evidence[].name` | yes, per entry | Name copied onto the evidence object. |
| `evidence[].media_type` | yes, per entry | Media type copied onto the evidence resource. |

The command is trusted by the organization that authored it. The harness runs it with the credentials that organization configured. Secret values stay in the harness's secret store. Naming `IDP_TENANT` under `env` is the contract. Putting the tenant id or a token in `command` is a mistake the spec cannot usefully detect, and reviewers should treat a secret in a test file as a defect.

**Harness contract.** A harness, given a test with `run.runner: shell`, an implementation of that test's control, and an evaluation date:

1. Creates a scratch directory for the run and discards it after the run.
2. Exports each name in `env`. A name with no configured value ends the run as `error`. It also exports the resolved control parameters as `OGRC_PARAM_<NAME>` (name uppercased), plus `OGRC_CONTROL_ID`, `OGRC_TEST_ID`, `OGRC_IMPLEMENTATION_ID`, and, when the implementation has a `system_ref`, `OGRC_SYSTEM_ID`. A run against a component implementation has no system. Its result speaks for the component in every system that inherits it.
3. Writes `command` to a file in the scratch directory and executes it with `sh`. The working directory is the scratch directory.
4. Stops the process at `timeout`. A timeout is `error`.
5. Maps the exit code to `outcome`: `0` is `pass`, `1` is `fail`, anything else is `error`.
6. Sets `result.summary` from the last non-empty line of stdout, truncated to 2 KB. Stdout is not evidence. A script that wants a log kept as evidence writes a file and lists it under `evidence`.
7. For a `pass`, every declared evidence path exists. A missing file turns the outcome into `error`. For a `fail` or `error`, the harness collects whichever declared files exist.
8. Writes one `evidence` object per collected file, with `method: automated`, sha-256 of the bytes, `valid_from` of the evaluation date, and `valid_until` of the evaluation date plus the test's freshness window from [section 8](#8-computed-status). The URI is wherever the harness stored the bytes.
9. Writes one `result` for this test and implementation with `observed` set to the run time, the outcome, the summary, `evidence_refs` for the files it collected, and `objective_refs` copied from the test.

The harness does not edit the test. A second run is a new result. Previous results stay in the graph.

### 7.7 `party`

```yaml
type: party
id: party--0d4e1c2b-3a49-4e6d-8c8b-9a0f1e2d3c4b
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Security lead
kind: role                         # person | team | role | organization
```

The standard library does not contain people. Guidance lives in control text. An implementation points at a real party.

### 7.8 `component`

A component is a reusable piece of a boundary: an identity provider, a cloud partition, a dataset, a team. Systems include components. Implementations on a component say how that piece carries out a control, and every system that includes the component inherits those implementations until it writes its own.

A provider publishes that set as a bundle an organization imports: the provider party, the component, and one implementation per control the provider inherits, shares, or leaves to the customer. [RFC 0002](0002-tooling.md) is the package and the import. The same objects render as an OSCAL component definition. The [Django component definition](https://github.com/CivicActions/oscal-component-definitions/tree/main/django) is that document written against SP 800-53 control ids.

A component is not an asset. It has no serial number and no instance count. An inventory of hosts and accounts stays out of this language.

```yaml
type: component
id: component--a1b2c3d4-e5f6-4781-92a3-b4c5d6e7f809
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Corporate IdP
kind: software                     # infrastructure | software | people | data | procedure | service
description: >
  Workforce identity provider. Employees and their groups live here.
party_ref: party--a3bb189e-8bf9-4388-9912-ace4e6543002
```

`party_ref` is optional. It names the organization that operates the component when that is someone other than the system owner.

### 7.9 `system`

A system is the front half of an SSP: the boundary, the information it holds, and the other parties involved. The pieces of the boundary are `component` objects the system includes.

```yaml
type: system
id: system--3fa85f64-5717-4562-b3fc-2c963f66afa6
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Customer production environment
function: >
  Multi-tenant application customers use to manage their work.
boundary: >
  Production AWS organization, the GitHub organization,
  and the corporate IdP.
component_refs:
  - component--a1b2c3d4-e5f6-4781-92a3-b4c5d6e7f809
information_types:
  - name: Customer content
    description: Documents and messages customers store in the product.
    confidentiality: moderate      # low | moderate | high
    integrity: moderate
    availability: low
    component_refs:
      - component--a1b2c3d4-e5f6-4781-92a3-b4c5d6e7f809
parties:
  - party_ref: party--a3bb189e-8bf9-4388-9912-ace4e6543002
    role: subservice               # subservice | customer | operator
    function: Cloud infrastructure
    authorization:
      identifier: FedRAMP-Moderate-123456
      authorized: 2024-06-01
      expires: 2027-06-01
```

`information_types` is the categorization a federal SSP expects. Each entry names the information, the component that holds it, and a low, moderate, or high impact for confidentiality, integrity, and availability. `component_refs` on an information type is a subset of the system's `component_refs`.

`authorization` belongs on a party whose `role` is `subservice`. `identifier` is the provider's authorization number, not an object id. `authorized` and `expires` are calendar dates. The block is how a leveraged authorization is recorded. A customer or operator party does not carry one.

### 7.10 `program`

A program binds one system to one baseline.

```yaml
type: program
id: program--7c9e6679-7425-40de-944b-e07fc1f90ae7
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: 2026 SOC 2
system_ref: system--3fa85f64-5717-4562-b3fc-2c963f66afa6
baseline_ref: baseline--soc2-s-a-c-pi
```

### 7.11 `implementation`

An implementation is one cell of the SSP: how this system, or a component the system includes, carries out this control. There is no SSP object. A renderer walks the system, the program, the components, and these records. A status change is a later `modified` on the same id.

An implementation has `system_ref`, `component_ref`, or both.

| Refs set | Applies to |
|---|---|
| `system_ref` only | This system's own statement for the control. |
| `component_ref` only | The component. Every system that includes the component inherits it. |
| Both | This system's statement for that component. It replaces the inherited component implementation for this system only. |

```yaml
type: implementation
id: implementation--2f1e0c3a-7b4d-4e5f-9a6b-1c2d3e4f5a6b
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
system_ref: system--3fa85f64-5717-4562-b3fc-2c963f66afa6
control_ref: control--ogrc-ac-01
status: implemented
# planned | implemented | partial | not-applicable | exception
responsibility: provider            # provider | customer | shared | subservice
parameter_values:
  shared_account_review: quarterly
requirement_parameter_values:
  requirement--nist-sp-800-53-r5-ac-2:
    ac_02_odp_10: monthly
owner_ref: party--0d4e1c2b-3a49-4e6d-8c8b-9a0f1e2d3c4b
narrative: >
  Every employee has one IdP account. Service accounts are created
  in AWS IAM and owned by the platform team. Shared accounts are
  listed in the security register and reviewed quarterly.
```

`responsibility` records who implements the practice, from the author's side. `origin` says who the author is, so the same word reads differently on the two kinds of row.

| Value | On an organization row | On a provider row (`origin: provider`) |
|---|---|---|
| `provider` | The organization does it, as the provider of this system. | The publishing provider does it. |
| `shared` | The organization does its part, and says whose the rest is in `narrative`. | The provider does part. The importing organization does `customer_responsibility`. |
| `customer` | The organization's own customers do it. | The importing organization does it. |
| `subservice` | A party the organization relies on does it. | A party the provider relies on does it. |
 `customer` and `subservice` are how SOC 2 complementary controls and a CMMC shared-responsibility matrix are expressed. When `responsibility` is `subservice`, `subservice_ref` names the party.

`origin` is `organization` or `provider`. Omitted means `organization`. A provider bundle sets `provider`. An organization writes a new implementation for its own half, and that object stays `organization`. It does not edit the provider's row.

`requirement_ref` names a framework requirement when the author is speaking that catalog directly, which is how an OSCAL component definition is imported. An implementation has `control_ref`, `requirement_ref`, or both. `control_ref` is how a provider speaks an OpenGRC control. `requirement_ref` alone is how a provider speaks `ac-2` without choosing an OpenGRC control. Status for that shape is in [section 8](#8-computed-status).

`customer_responsibility` is the customer's remaining work. A provider implementation with `responsibility` `shared` or `customer` includes it. The provider's own work stays in `narrative`.

`requirement_parameter_values` overrides one target-framework parameter for this implementation. The key is the requirement id. The inner key is the requirement's parameter key. It does not change `parameter_values` for the OpenGRC control. The resolution order is in [Mappings](#74-mapping).

`status: not-applicable` puts the reason in `narrative`. `status: exception` requires an `exception` object. See [Graph constraints](#720-graph-constraints).

### 7.12 `result`

A result is a judgment about one run of a test. A failure is a result. A failure often has nothing an auditor would call evidence, which is why the artifact is a separate type.

```yaml
type: result
id: result--6ba7b810-9dad-11d1-80b4-00c04fd430c8
spec_version: 0.1.0
created: 2026-11-08T17:00:00Z
modified: 2026-11-08T17:00:00Z
test_ref: test--ogrc-ac-01-unique-idp-users
implementation_ref: implementation--2f1e0c3a-7b4d-4e5f-9a6b-1c2d3e4f5a6b
observed: 2026-11-08T17:00:00Z
outcome: pass                      # pass | fail | error | skip
summary: 418 active users, each with a distinct employee id.
subjects:
  - kind: account
    name: alice@company.com
    external_id: "100231"
objective_refs:
  - requirement--nist-sp-800-53-r5-ac-2#obj.a
evidence_refs:
  - evidence--6ba7b811-9dad-11d1-80b4-00c04fd430c8
```

`subjects` are inline identifiers (an account, a hostname, an ARN). A later asset type can match them on `external_id`. Event-driven tests set `valid_until` on the result, as a timestamp. A result is not edited after it is written. A wrong one is revoked and a new one recorded. `objective_refs` records which assessment objectives this run spoke to. A pass is the check's outcome. It is not an assessor's determination. That determination is a `finding`.

### 7.13 `finding`

A finding is a person's determination against one assessment objective. A `result` stays the record of a test run. An assessor can cite those results as evidence and still reach a different determination.

```yaml
type: finding
id: finding--c0ffee00-9dad-11d1-80b4-00c04fd430c8
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Account types are defined
system_ref: system--3fa85f64-5717-4562-b3fc-2c963f66afa6
objective_ref: requirement--nist-sp-800-53-r5-ac-2#obj.a
determination: satisfied           # satisfied | not-satisfied
observed: 2026-11-08
narrative: >
  The account inventory lists individual, service, and shared
  accounts, and it names the prohibited types.
implementation_ref: implementation--2f1e0c3a-7b4d-4e5f-9a6b-1c2d3e4f5a6b
evidence_refs:
  - evidence--6ba7b811-9dad-11d1-80b4-00c04fd430c8
risk_ref: risk--b7e23ec2-8b7b-4c3a-9f4e-1d5a6c7e8f90
```

`objective_ref` is one requirement objective. A second objective is a second finding. `implementation_ref`, `evidence_refs`, and `risk_ref` are optional. `risk_ref` points at the organization's risk register. There is not a second risk type for the assessor. `observed` is the calendar date of the determination.

The finding **in force** for a system and an objective is the non-revoked one with the latest `observed`. Earlier findings on the same objective are history. A `not-satisfied` finding is closed by a later `satisfied` finding on that objective, not by editing it. Reports, the plan of action and milestones among them, use findings in force.

Findings do not change the met, waived, out-of-scope, or gap words in [section 8](#8-computed-status). They are reported beside that status.

### 7.14 `evidence`

Evidence is an artifact with a validity window and a hash. The bytes are not in the object. `resource.uri` is an absolute URI or a path relative to the bundle root.

```yaml
type: evidence
id: evidence--6ba7b811-9dad-11d1-80b4-00c04fd430c8
spec_version: 0.1.0
created: 2026-11-08T17:05:00Z
modified: 2026-11-08T17:05:00Z
name: IdP user export, 2026-11-08
collected: 2026-11-08T17:04:00Z
valid_from: 2026-11-08
valid_until: 2026-12-08
method: automated                  # automated | upload | attestation | link
implementation_ref: implementation--2f1e0c3a-7b4d-4e5f-9a6b-1c2d3e4f5a6b
result_ref: result--6ba7b810-9dad-11d1-80b4-00c04fd430c8
resource:
  uri: evidence/2026-11-08-idp-users.csv
  media_type: text/csv
  digest:
    algorithm: sha-256
    value: 0000000000000000000000000000000000000000000000000000000000000000
```

`result_ref` is optional. A person can attach evidence directly to an implementation. When both are set, the result's `evidence_refs` includes this evidence id.

What `resource` holds depends on `method`.

| `method` | `resource.uri` | `resource.digest` |
|---|---|---|
| `automated`, `upload` | Where the bytes are stored. | Required. sha-256 of the bytes. |
| `attestation` | The signed statement, stored as a document. | Required. |
| `link` | The page or record a person pointed at. | Optional. When present, it is the sha-256 of what was retrieved at `collected`. |

An evidence object that lacks the digest its method requires is **incomplete**. A store may hold it, which is how an upload in two steps works. It never counts in [section 8](#8-computed-status).

Once evidence is complete, `resource`, `method`, `collected`, `valid_from`, `valid_until`, `implementation_ref`, and `result_ref` do not change. A correction is a revoke and a new object. Extending `valid_until` on an old artifact is collecting it again.

### 7.15 `policy`

A policy is adopted prose plus the controls it governs. The body is Markdown (or another document type) addressed by hash. The taxonomy does not model sections as objects.

```yaml
type: policy
id: policy--1a2b3c4d-5e6f-4781-92a3-b4c5d6e7f809
spec_version: 0.1.0
created: 2026-01-15T00:00:00Z
modified: 2026-01-15T00:00:00Z
name: Access Control Policy
status: adopted                    # draft | adopted | retired
version: "1.4"
adopted: 2026-01-15
review_interval: annual
owner_ref: party--0d4e1c2b-3a49-4e6d-8c8b-9a0f1e2d3c4b
control_refs:
  - control--ogrc-ac-01
resource:
  uri: policy/access-control.md
  media_type: text/markdown
  digest:
    algorithm: sha-256
    value: 0000000000000000000000000000000000000000000000000000000000000000
```

Employee acknowledgment is a `result` against the control that requires acknowledgment. It is not a list of names on the policy.

A policy with `status: adopted` requires `resource.digest`, `adopted`, and `owner_ref`.

`reviewed` is the calendar date of the last review, and it is optional. The next review is due one `review_interval` after `reviewed`, or after `adopted` when the policy has not been reviewed since.

### 7.16 `procedure`

A procedure is how people carry a policy out. The same content rule applies: steps live in the Markdown body.

```yaml
type: procedure
id: procedure--9c858901-8a57-4791-81fe-4c455b099bc9
spec_version: 0.1.0
created: 2026-01-15T00:00:00Z
modified: 2026-01-15T00:00:00Z
name: Quarterly access review
status: adopted
policy_ref: policy--1a2b3c4d-5e6f-4781-92a3-b4c5d6e7f809
control_refs:
  - control--ogrc-ac-04
interval: quarterly
owner_ref: party--0d4e1c2b-3a49-4e6d-8c8b-9a0f1e2d3c4b
resource:
  uri: procedure/quarterly-access-review.md
  media_type: text/markdown
  digest:
    algorithm: sha-256
    value: 0000000000000000000000000000000000000000000000000000000000000000
```

### 7.17 `risk`

Likelihood and impact are integers from 1 to 5.

| Score | Likelihood | Impact |
|---|---|---|
| 1 | Rare within a year | Negligible. No customer or regulatory effect. |
| 2 | Unlikely | Low. Limited internal effect. |
| 3 | Possible | Moderate. Noticeable customer effect, contained. |
| 4 | Likely | High. Material customer, contractual, or regulatory effect. |
| 5 | Expected more than once a year | Severe. Existential or reportable breach-scale. |

Tools derive the rating from this matrix. Objects store the scores, not the word.

| Likelihood \ Impact | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | low | low | low | medium | medium |
| 2 | low | low | medium | medium | high |
| 3 | low | medium | medium | high | high |
| 4 | medium | medium | high | high | critical |
| 5 | medium | high | high | critical | critical |

```yaml
type: risk
id: risk--b7e23ec2-8b7b-4c3a-9f4e-1d5a6c7e8f90
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Shared production admin credential
system_ref: system--3fa85f64-5717-4562-b3fc-2c963f66afa6
statement: >
  A shared admin credential would let a departed engineer keep
  production access.
likelihood: 2
impact: 5
residual_likelihood: 1
residual_impact: 5
treatment: mitigate               # mitigate | accept | transfer | avoid
status: treating                  # open | treating | accepted | closed
owner_ref: party--0d4e1c2b-3a49-4e6d-8c8b-9a0f1e2d3c4b
control_refs:
  - control--ogrc-ac-01
review_on: 2027-01-15
milestones:
  - name: Move break-glass to individual vault identities
    due: 2027-02-01
  - name: Remove the shared credential
    due: 2027-03-01
    done: 2027-02-20
```

`treatment: accept` requires `approver_ref` and `review_on` before `status` can be `accepted`. Residual scores are optional and use the same scales.

`milestones` is the remediation schedule. Each entry has a `name` and a `due` date. `done` is the calendar date the step was finished, and it is omitted while the step is open. A plan of action and milestones is a render of open risks that have milestones, open exceptions, and findings whose determination is `not-satisfied`. There is no `poam` type.

### 7.18 `exception`

An exception is a waived control with an owner and an end date. It is distinct from a risk. A risk can exist while every control is still in place.

```yaml
type: exception
id: exception--c5d24601-86f7-4e1a-9b2c-3d4e5f607182
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
implementation_ref: implementation--2f1e0c3a-7b4d-4e5f-9a6b-1c2d3e4f5a6b
justification: >
  Production admin currently uses a shared break-glass credential
  stored in the vault. Replacement is the SSO cutover.
expires: 2027-03-01
approver_ref: party--0d4e1c2b-3a49-4e6d-8c8b-9a0f1e2d3c4b
risk_ref: risk--b7e23ec2-8b7b-4c3a-9f4e-1d5a6c7e8f90
```

`risk_ref` is optional.

`implementation_ref` points at an implementation the organization wrote. A provider's row is not the organization's to waive. An organization that waives an inherited control writes its own implementation for the system, with status `exception`, and points the exception at that.

### 7.19 Extensions

Extension data lives under `extensions`, keyed by a domain the extension owner controls. Producers preserve keys they do not implement.

```yaml
extensions:
  com.example.connector:
    product: google-workspace
    query: users.list
```

### 7.20 Graph constraints

- `mapping.target_ref` resolves to a requirement. `mapping.source_ref` resolves to a control or a requirement.
- At most one non-revoked `mapping` exists for a given source, target, and part within one publication: one in the standard library, and one authored by the organization. When both exist, the organization's mapping is the one section 8 uses for that organization, and the library's is shown as replaced. This is how an organization records a different relationship than the library published.
- An `exception` points at an organization-authored implementation.
- `parameter_map` values name parameters on the source control. Keys name parameters on the target requirement. The source is a control.
- An implementation has `system_ref`, `component_ref`, or both.
- An implementation has `control_ref`, `requirement_ref`, or both.
- `origin` is `organization` or `provider`. Omitted means `organization`.
- A provider bundle authored as OpenGRC YAML includes `customer_responsibility` when `origin` is `provider` and `responsibility` is `shared` or `customer`. An OSCAL component definition that does not separate that sentence may omit it. The control still does not meet.
- At most one non-revoked implementation exists for a given system and control with no `component_ref`.
- At most one non-revoked implementation exists for a given component and control with no `system_ref`.
- At most one non-revoked implementation exists for a given system, component, and control.
- A system's `information_types[].component_refs` are a subset of that system's `component_refs`.
- `authorization` appears only on a system party whose `role` is `subservice`, and it includes `identifier`, `authorized`, and `expires`.
- `implementation.status: exception` requires at least one `exception` whose `implementation_ref` points at it and whose `expires` is on or after the evaluation date.
- `exception` requires `justification`, `expires`, `approver_ref`, and `implementation_ref`.
- `result.test_ref` and `result.implementation_ref` are required. The test's control and the implementation's control are the same control.
- `objective_refs` and `finding.objective_ref` use a `#obj.` fragment that matches an `objectives[].id` on that requirement.
- `finding` requires `system_ref`, `objective_ref`, `determination`, `observed`, and `narrative`.
- `method: manual` has no `run`. `run.runner: shell` requires `command`.
- `run.env` lists names only. Values are not fields on the test.
- `run.evidence[].path` is relative to the scratch directory, is not absolute, and does not contain `..`.
- `fulfills_ref` points at a test with the same `control_ref`. That target has no `fulfills_ref`.
- `test.system_refs` resolve to systems. A library test has none.
- `combined_with_refs` lists mappings with the same `target_ref` as the mapping that carries it. Every mapping in the set has a control as `source_ref` and a `relationship` of `subset-of` or `intersects-with`. A mapping belongs to at most one combined set.
- `evidence` includes `implementation_ref` or `result_ref` or both. A digest, where present, uses `sha-256`. Which methods require one is in [Evidence](#714-evidence).
- `policy.status: adopted` and `procedure.status: adopted` require a digest, an owner, and, for a policy, an `adopted` date.
- `risk.status: accepted` requires `treatment: accept`, `approver_ref`, and `review_on`.
- A milestone has `name` and `due`. `done`, when set, is on or after the risk's `created` date.
- `program` references one system and one baseline.
- `baseline.extends_ref` points at a baseline that has no `extends_ref`.
- `baseline.requirement_refs` are requirement ids without a fragment, and none of them is withdrawn. Each one's `framework_ref` is in that baseline's `framework_refs`.
- A baseline in the standard library lists only `origin: standard` controls and has no `extends_ref`.

## 8. Computed status

Evaluated at an instant, for one program. The instant is an RFC 3339 timestamp, and "the evaluation date" below is its UTC calendar date. A calendar-date field such as `valid_until` or `expires` includes the whole of that UTC day. A freshness window is counted in 24-hour days from `observed`. "The baseline" in this section is the program's effective baseline from [Baselines](#75-baseline): the controls, requirements, and parameter bindings after `extends_ref` is applied.

**Freshness windows** for `test.interval`:

| Interval | Window |
|---|---|
| `continuous` | 1 day |
| `daily` | 1 day |
| `weekly` | 7 days |
| `monthly` | 30 days |
| `quarterly` | 90 days |
| `annual` | 365 days |
| `event-driven` | Until the latest result's `valid_until`, which that result must set |

A test's **current result** for an implementation is the non-revoked result for that test and implementation with the latest `observed`. A test is **passing** for an implementation when its current result has `outcome: pass` and the evaluation date falls inside the window starting at that result's `observed`. An earlier pass does not count once a later result exists. `fail`, `error`, and `skip` are not passing.

A test **applies** to a program when the test has no `system_refs`, or when the program's system is listed in them.

The implementation section 8 evaluates is the one with `system_ref` for the program's system and no `component_ref`, when that implementation exists. It replaces the inherited component implementations, with one exception. A provider-authored implementation (`origin: provider`) with `responsibility: shared`, on a component the system includes, stays under evaluation beside it as the **provider's half**. The organization's statement is its own half of a shared control and does not stand in for the provider's. When no system implementation exists, section 8 evaluates the implementations of that control on components the system includes. A component implementation that also sets `system_ref` for this system replaces the inherited one for this system. A provider implementation with `requirement_ref` and no `control_ref` joins that set only when a reviewed mapping from the control to that requirement, or to a part of it, is `equal-to`, `equivalent-to`, or `subset-of`. The direction matters. The provider is speaking for the whole requirement, so its statement reaches a control that is the same as the requirement or narrower than it. A control that is `superset-of` the requirement, or that `intersects-with` it, asks for something the provider's statement does not address, and the statement does not join. The control is **met** only when at least one such implementation remains and each of them meets the rules below. Findings do not enter this computation.

A control in a program is **met** when every implementation under evaluation meets all of the following:

- `implementation.status` is `implemented`.
- `responsibility` allows the implementation to satisfy the control. On an organization-authored implementation, `provider` and `shared` mean the organization does the work, and the implementation can satisfy the control. `customer` and `subservice` mean someone else does the work. Such an implementation never makes the control met. It makes the control out of scope, as defined below. On a provider-authored implementation (`origin: provider`), `provider` and `subservice` can satisfy it. `shared` and `customer` cannot: `shared` is the provider's half, and the control stays a gap until the organization writes its own implementation for the half named in `customer_responsibility`.
- Every parameter in the resolved statement has a value.
- Every `required: true` test for that control is satisfied for that implementation. Only tests that apply to the program are considered. A test that nothing fulfills is satisfied when it is passing. When one or more non-revoked tests that apply to the program `fulfills_ref` it, those tests replace it: each of them is passing, and the required test's own results do not count. A fulfilling test that does not apply to the program is ignored. A required `method: automated` test with no `run` and no applicable fulfillment is a gap, and the gap says that no methodology has been defined. A `method: manual` test needs no `run`. A person records its result, and it is satisfied when it is passing. A provider implementation with `responsibility` `provider` or `subservice` is the exception: unexpired evidence on that implementation satisfies a library test that no organization test fulfills. The evidence is the provider's report. An organization test that fulfills the library test still has to pass.
- Every evidence record cited by those results, or used in place of them, has `valid_until` on or after the evaluation date.
- When no `required: true` test applies to the control, at least one evidence record whose `implementation_ref` is this implementation has `valid_until` on or after the evaluation date. A status flag alone does not meet a control.

The provider's half is held to a shorter list, because the provider's row was already ruled unable to satisfy the control alone. It holds when its `status` is `implemented` and every evidence record on it has `valid_until` on or after the evaluation date. The control is met only when the system implementation meets the rules above and every provider's half holds. A gap names the half that failed. A system that does not rely on the provider for the control writes an implementation with both `system_ref` and that `component_ref`, which replaces the provider's row for this system.

A control is **waived** when every implementation under evaluation has status `exception` and an exception pointing at each has not reached `expires`. It is **out of scope** when every one has status `not-applicable`, or is organization-authored with `responsibility` `customer` or `subservice`. The provider's half is not counted in either test. Every other case is **gap**. A gap records which condition failed.

**Requirement coverage** is computed for each requirement in the baseline's requirements that is neither revoked nor withdrawn. A requirement the publisher withdraws after a baseline listed it drops out of the computation at the pull that brings the withdrawal in, and the pull report names it.

The **units** of a requirement are its leaf parts: the parts whose id is not the dotted prefix of another part's id. `d.1` is a unit, and `d` is not when `d.1` exists. A requirement with no parts is one unit. A mapping whose `target_ref` has no fragment reaches every unit. A mapping to `#d` reaches `d`, or every unit under `d` when `d` has nested parts.

A mapping counts here when its source is a control on the program's baseline, it is not revoked, its `relationship` is not `no-relationship`, and it is reviewed. Reviewed means `review_status: reviewed` on the mapping, or an accepting `mapping_review` from [RFC 0002](0002-tooling.md) that is still current. A `mapping_review` with `review_status: rejected` removes the mapping from this computation, whatever the mapping itself says.

A **path** to a unit is one of:

- A counted mapping that reaches the unit with `equal-to`, `equivalent-to`, or `superset-of`.
- A combined set from [Mappings](#74-mapping) whose target reaches the unit: the mapping that carries `combined_with_refs` and every mapping it lists, all of them counted.

A path **holds** when every source control on it is met. A unit is covered when at least one path to it holds.

The states, first match wins:

| State | When |
|---|---|
| **unmapped** | No counted mapping reaches any unit. |
| **contribution** | At least one unit has no path. The counted mappings are shown as contribution. |
| **gap** | Every unit has a path, and at least one unit has no path that holds. The gap names the controls that are not met. |
| **covered** | Every unit has a path that holds. |

A unit no mapping reaches keeps the requirement at contribution. Parts without mappings are not skipped. Unmapped is a different state from a gap in implementation: it means nobody has reviewed a crosswalk, and gap means the crosswalk is complete and the practice is not in place. A waived or out-of-scope control is not met for this purpose, and the report says which it is.

Nothing in the bundle stores these words. Tools derive them.

### 8.1 What an SSP render contains

A renderer producing an SSP, or the system-description-plus-control-matrix packet a SOC 2 or CMMC auditor asks for, walks:

1. The `system`: function, boundary, components, information types, parties, and any leveraged authorization.
2. The `program` and its `baseline`.
3. For each control on the baseline: the control statement with parameters resolved, the system implementation and any component implementations, the latest result of each required test, unexpired evidence, and any exception.
4. Findings on that system, beside the computed status.
5. Adopted policies and procedures that name those controls.
6. Open risks that name those controls, including milestones.

The render is disposable. Edits happen on the objects.

[RFC 0002](0002-tooling.md) defines the OSCAL form of this render: a profile, a system security plan, a mapping collection, a component definition, assessment results, and a plan of action and milestones, for one system and one target NIST framework. The database remains the source of those objects. The OSCAL is not imported back.

## 9. Authoring layout

This layout is conventional. A conforming tool may store objects somewhere else if ids and references still resolve.

```text
library/
  bundle.yaml
  framework/
  requirement/soc2-tsc-2017/
  requirement/nist-sp-800-53-r5/     # generated from OSCAL
  control/
  mapping/
  baseline/
  test/
org/
  bundle.yaml
  party/
  component/
  system/
  baseline/                          # organization baselines, when the library one is not enough
  program/
  implementation/
  policy/
  procedure/
  evidence/                          # objects; blobs live beside them or in object storage
  result/
  finding/
  risk/
  exception/
```

People write `library/control`, `library/mapping`, `library/baseline`, and `library/test`. NIST requirement trees are generated and are not hand-edited. SOC 2, ISO, and HIPAA indexes are small enough to write by hand because they hold identifiers and titles, not the copyrighted or regulatory prose in bulk. HIPAA is the exception on prose: the CFR text may be stored. See the next section.

The first content slice that validates this RFC is the access-control family, on the order of eight controls, mapped to SP 800-53 (including statement parts), to SP 800-171 Rev 2 `3.1.x` and `3.5.3`, and to SOC 2 CC6.1 through CC6.3, plus one baseline, one library test, one manual test, and a sample `org/` graph. The org graph includes a system, implementations, a test with a `shell` run that fulfills the library test, a result, a piece of evidence, a policy, and a risk. The slice is acceptable when that bundle is readable in review and a tool can render control status and a one-page SSP from it without extra data.

## 10. External catalogs and copyright

| Framework | How it enters the graph | Text in the repo |
|---|---|---|
| NIST SP 800-53 Rev 5.2.0, and the 800-53B low, moderate, high, and privacy baselines | Compiled from the pinned `oscal-content` catalog and profiles | Permitted. Public domain. |
| NIST SP 800-171 Rev 3 and SP 800-172 Rev 3 | Compiled from `oscal-content` | Permitted. |
| NIST SP 800-171 Rev 2 | Authored into `requirement` objects from the NIST publication. `oscal-content` publishes Rev 3, and CMMC Level 2 still assesses Rev 2. | Permitted. |
| CMMC Level 1 | 17 practices aligned to FAR 52.204-21, as requirements | Permitted as citations of the FAR. |
| CMMC Level 2 | A baseline whose requirements are the 110 SP 800-171 Rev 2 requirements | Same objects as Rev 2. |
| CMMC Level 3 | A later baseline over Rev 2 plus a selected SP 800-172 subset | Deferred past the first slice. |
| SOC 2 Trust Services Criteria (2017) | Hand-authored index. Security is CC1.1–CC9.2 (33 criteria). Availability, Confidentiality, and Processing Integrity add A1.1–A1.3, C1.1–C1.2, and PI1.1–PI1.5. | Identifier, title we write, citation. The criteria text and points of focus stay in the AICPA document. |
| ISO/IEC 27001:2022 | Annex A (93 controls, A.5–A.8) and clauses 4–10, as an index | Identifier and title we write. Annex A wording stays with ISO. |
| HIPAA Security Rule | 45 CFR 164.308, 164.310, 164.312, 164.314, 164.316, including required and addressable specifications | Permitted. The CFR is public domain. |
| NIST CSF 2.0 | Later. Already published as OSCAL. | Permitted when we add it. |

SP 800-53 is the hub catalog: the superset the other NIST publications were written against, and the index authors use while mapping. The OpenGRC control library stays a smaller operational set. SP 800-53 statements are the target of mappings, not the controls a company marks done.

CMMC Level 2 and DFARS 252.204-7012 still name SP 800-171 Revision 2 (110 requirements, numbered `3.1.1` through `3.14.7`, assessed against 800-171A's 320 objectives). Revision 3 renumbers those requirements (`03.01.01`) and is a separate catalog. DoD rulemaking RIN 0790-AM01 is the transition to Revision 3 and is not the assessment baseline as of this writing. Both revisions exist in the model so a later baseline can move without rewriting controls.

NIST SP 800-66 Rev 2 is the draft crosswalk from the HIPAA Security Rule to SP 800-53 Rev 5. It is ingested as requirement-to-requirement mappings for authors. The mapping a customer relies on is a reviewed mapping from OpenGRC controls to the HIPAA requirements.

### 10.1 OSCAL import

`ogrc import nist` reads a pinned revision of `oscal-content` and writes SP 800-53 Rev 5.2.0 and SP 800-171 Rev 3 into this model.

Each catalog becomes one `framework` file and one `requirement` file per control. SP 800-53 enhancements are their own requirements, with `class: enhancement`. Withdrawn items are written with `withdrawn: true` so the id remains. They are not revoked. The statement and its lettered items are kept. OSCAL parameter inserts (`{{ insert: param, ... }}`) are rewritten to `{{ param_key }}`, and the parameter's label is kept. Discussion is not copied. A lettered item is a `part`. Nested items use dotted ids (`a`, `a.1`, `a.1.a`).

Assessment objectives are copied onto `objectives`, and assessment methods onto `objectives[].methods`. The objective id is the local label (`a`, `a.1`), and a reference uses the `#obj.` fragment. Method prose is stored and is not a test. The current `ogrc import` writes statements, parts, parameters, and draft mappings. It does not write `objectives` yet. The next import pass does, without changing requirement ids.

Draft mappings are written for links that name another requirement. `review_status` is `draft`, `rationale` is `semantic`, and `confidence` is `low`. Nothing imported this way is a reviewed coverage claim.

| OSCAL link | Mapping |
|---|---|
| SP 800-171 `reference` whose target title is an SP 800-53 control id, such as `AC-02(03)` | `intersects-with` that SP 800-53 requirement |
| `incorporated-into` | `subset-of` |
| `moved-to` | `equivalent-to` |
| `addressed_by` | `intersects-with` |

`related` and `required` links are not mappings. A link that points at a control family rather than a requirement is an `external_references` entry on the source. Other reference targets (SP 800-162, FIPS, the CFR) are `external_references` too.

SP 800-171 Rev 2 is not part of this import. `oscal-content` publishes Rev 3, and Rev 2 is still the CMMC Level 2 catalog. `ogrc import oscal` reads any OSCAL catalog file, so a Rev 2 catalog can be imported when one is in hand.

## 11. Conformance

**A library reader** loads `framework`, `requirement`, `control`, `mapping`, `baseline`, and `test`, resolves refs among them, including `#obj.` fragments, and preserves every other field on round trip.

**An application** also loads the operational types and computes status as in [section 8](#8-computed-status).

Both of these are required of anything that writes objects:

- Emit the envelope and the required fields for each type it produces.
- Refuse to mint an id in the standard-library slug space.
- Advance `modified` only as the producer, to a strictly later timestamp, whenever the object changes.
- Preserve unknown fields and `extensions`.
- Write canonical JSON that another 0.1.0 reader accepts. YAML authoring is optional for a pure API.

A tool may store extra internal columns in its database. Those columns become part of the language only when they appear in an object defined here or under `extensions`.

## 12. Alternatives considered

**Author OSCAL directly.** OSCAL mapping collections already have the relationship vocabulary this RFC adopts, and the NIST catalogs are OSCAL. Authoring and company operational data stay in the object graph because that is the unit tools and reviewers can share. OSCAL is the compiler input and a renderer output.

**Use SP 800-53 identifiers as the OpenGRC control ids.** The catalog is the right hub and the wrong working set. A SOC 2 program is on the order of a hundred practices. SP 800-53 Rev 5, with enhancements, is an order of magnitude larger, and its statements are written as organizational duties with parameters. Sharing the AC-2 identifier with a different sentence would make every mapping ambiguous. Standard controls use the `ogrc-` slug and the `OGRC-AC-01` display id.

**Put framework ids inside the control file.** Convenient for a single author, and brittle the moment a second person revises mappings or a framework publishes a new revision. Mappings are their own objects so the practice and the crosswalk version independently. This is also how OSCAL separates catalogs from mapping collections, with a smaller authoring surface.

**Make every link a relationship object.** STIX does this. It fits machine-written graphs. A policy that governs three controls would become three extra files a person has to keep in sync. Intrinsic refs stay inline. Crosswalks and operational state become objects because they carry their own fields and lifecycle.

**Add an SSP type, a catalog type, and a POA&M type.** Those are views. An SSP type would drift from the implementations. A plan of action and milestones is a render of open risks and their milestones, open exceptions, and findings with determination `not-satisfied`. A finding is its own type because an assessor's determination has a lifecycle a failing result does not.

**Make combined coverage its own object, or leave it out.** Practice-sized controls are narrower than most requirements, so without a way to add partial mappings up, a requirement is almost never reported as covered. A separate object for the claim would have its own review lifecycle and one more file per requirement part. `combined_with_refs` keeps the claim on a mapping, where the reviewer of that mapping already is, and each member keeps its own `relationship`.

**Store evidence bytes or policy prose in the YAML.** Diffs and bundles stop being reviewable, and the same bytes would be copied into every tool's database. The object carries a URI and a sha-256 digest.

**Put the shell command on the control.** The control is the practice, and it is shared. The command is one organization's tools and one organization's tenant. A control can be checked more than one way. The command lives on the `test` that references the control, and `fulfills_ref` keeps that command tied to the library check it carries out.

**Treat stdout as the evidence.** Scripts mix logs and artifacts. The test names the files that count as evidence. The harness hashes those files. Stdout is truncated into `result.summary` so a reviewer can see why a run failed.

## 13. Open questions

These are the choices most worth challenging in review. The body of the RFC states a default so the rest of the model is concrete.

1. **Mapping ids.** The default is a readable derived id (`mapping--ogrc-ac-01_to_soc2-tsc-2017-cc6.1`). The alternative is a UUID, with the pair expressed only in `source_ref` and `target_ref`. Derived ids make the file name predictable and make duplicates obvious. They get long, and a renamed scheme is a breaking change.
2. **Risk matrix.** The 5-by-5 table in [section 7.17](#717-risk) is a proposal so two registers mean the same thing. The anchors and the band names (`low` through `critical`) need a sanity check from people who run risk committees.
3. **In-scope responsibilities.** For an organization-authored implementation, `provider` and `shared` can satisfy a control, and `customer` and `subservice` put the control out of scope. Provider bundles flip that, and [section 8](#8-computed-status) already says how. Out of scope is the default because the work is not the organization's to test. The alternative is a fifth state for a carved-out control, so it is not counted with `not-applicable`. What is still open is a program that wants organization-authored `shared` to stay unmet until both halves have a passing result. That may belong on the program (`in_scope_responsibilities`) rather than in the global rule.
4. **Part address syntax.** Fragments (`requirement--…-ac-2#a`) keep part ids short and local to the parent. They also mean a reference is not always a bare object id. A separate id for every part would make every ref the same shape and would multiply objects.
5. **Where generated NIST YAML lives.** Vendoring thousands of generated requirement files into this repository keeps the graph self-contained. A submodule or a release tarball of `oscal-content`, compiled on demand, keeps the git history readable. The object schema is the same either way.
6. **`program` as a type.** It exists so one system can pursue more than one baseline over time and so the binding itself has a lifecycle. Folding `baseline_ref` onto `system` is smaller and gets awkward as soon as a system has two concurrent programs.
7. **A control with no required test.** The default asks for one unexpired evidence record on the implementation. The alternative is to let `status: implemented` meet the control and mark it untested in the report.
8. **The provider's half.** A provider `shared` row stays under evaluation beside the system implementation, and holds on its status and its evidence. A provider bundle with no evidence on that row holds on status alone. Requiring evidence there would put every imported OSCAL component definition in gap.

## 14. What this RFC does not freeze

Assets and inventory items, vendors as more than `party.kind: organization`, locations, tickets, training records, and audit engagements. An assessment plan, the schedule of an engagement, stays out with those engagements. Connector configuration stays in `extensions` until a connector protocol is actually designed. Runners other than `shell` are named in `run.runner` and defined when a harness actually supports them. CSF 2.0, CMMC Level 3, and the SOC 2 privacy criteria can be added as frameworks, requirements, and baselines without a new type.
