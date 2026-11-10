# RFC 0002: Tooling and sources of truth

| | |
|---|---|
| Status | Draft |
| Spec version | 0.1.0 |
| Date | 2026-11-08 |
| Depends on | [RFC 0001](0001-object-model.md) |

This document is the proposal for how OpenGRC tools store and move the objects from RFC 0001. It is written so it can be edited in place. The open questions at the end are the spots most likely to move during review.

The language stays RFC 0001. This RFC decides which copy of those objects is authoritative, and which tools read or write each copy.

## 1. Summary

There are two sources of truth for a program, and a provider publication works the same way the library does.

This repository is the source of truth for the exchange library: frameworks, requirements, standard mappings, and, as they are written, the standard controls, baselines, and library tests. An organization database pulls a revision of that library forward.

A provider is the source of truth for the bundle it publishes: the service, and the controls that service inherits, shares, or leaves to the customer. An organization database imports a revision of that bundle. Microsoft 365 is the shape of one. The [Django component definition](https://github.com/CivicActions/oscal-component-definitions/tree/main/django) is the same kind of document in OSCAL.

Once those are loaded, that organization's database is the source of truth for the organization's program. Implementations, parameter values, evidence, results, policies, and risks are created there. A scheduled job exports a snapshot of that database to a git repository, and can write an OSCAL package beside it. The running tool does not read either export back, and it does not edit the provider's rows. The one reader of a snapshot is a restore into an empty database, in [section 8.1](#81-restore).

## 2. Copies

| Copy | Holds | Who writes it |
|---|---|---|
| This repository | The exchange library | OpenGRC, by change to this repo. `ogrc import` is one writer: it compiles NIST OSCAL catalogs into library files. |
| Provider publication | The provider party, its components, and the implementations a customer inherits | The provider. An organization imports a pinned revision. |
| Organization database | A pinned projection of the library, a pinned projection of each imported provider bundle, plus that organization's objects | The platform. A pull replaces the library projection. A provider import replaces that provider's projection. The application writes the organization's objects. |
| Organization git repository | A snapshot of the organization's objects, plus the library revision they were exported against | The export job, on a schedule. |

YAML in git and rows in the database are the same objects. Same id, same `modified`, same fields. RFC 0001's authoring form is YAML. The database stores the canonical JSON of the object. Extra columns the application needs for queries stay in the database. They become part of the language only when they appear on the object, which is the rule already in RFC 0001.

Evidence bytes live in object storage. The evidence object, with its hash and URI, is what the database and the git snapshot store.

## 3. Library

Library objects are the ones RFC 0001 calls the library side:

- `framework`
- `requirement`
- `mapping` published by OpenGRC
- `control` with `origin: standard`
- `baseline` published with the library
- `test` published with the library

A library revision is the `version` on `bundle--ogrc-library`, pinned to a commit of this repository. The files under `library/` are the revision. Git history is how that revision changes.

Organization databases do not edit these files, and they do not edit the rows that mirror them. A judgment about a library mapping is an organization object. The next pull replaces the library row and leaves the judgment in place.

## 4. Organization database

The database is the system of record for one organization. It holds:

- The library projection at one pinned revision.
- One pinned projection per imported provider bundle. See [section 7](#7-provider-bundles).
- That organization's objects: `party`, `component`, `system`, `program`, `implementation`, `result`, `finding`, `evidence`, `policy`, `procedure`, `risk`, `exception`, controls with `origin: custom`, baselines the organization authors, and tests the organization authors. An organization baseline that sets `extends_ref` follows the library baseline it names: a pull replaces the base, and the effective baseline changes with it. Provider objects in the projection are not in this list. The organization does not edit them.
- The organization's reviews of library mappings. See [section 6](#6-mapping-reviews).

The dashboard and the later automations read and write this database. They do not commit to git to save an implementation.

**Revisions.** The database keeps every revision of every object it holds, not only the current one. A revision is the object body at one `modified`, plus who wrote it and when the database stored it. That covers organization objects, each library projection, and each provider projection, together with the pins that were in force.

Status asked for at a past instant is computed from the revisions in force at that instant: the implementations, tests, mappings, reviews, baselines, and library pin as they were then. Today's objects are not evaluated against an old date. An implementation marked `implemented` this morning was not implemented last March, and a readiness view over an audit period depends on that.

The writer on a revision is how an edit is attributed. `created_by_ref` on the object names who first produced it. The revision log says who changed it afterwards, which is where a person's acceptance of an agent's draft is recorded. The log is a property of the store and not a field of the language. The git snapshot is not this history. It is taken on a schedule and it holds current objects only.

Parameter values are fields on the implementation, as in RFC 0001: `parameter_values` for the OpenGRC control, and `requirement_parameter_values` when one NIST parameter needs a different answer. The organization sets them there. The pull does not change them, because they are not library fields.

## 5. Pull

A pull loads one library revision into one organization database.

1. Read `bundle--ogrc-library` at a chosen commit. The revision's objects are the files under `library/` in that commit.
2. For each library object in the revision, replace the stored object with the same id. The replacement is the whole object. Fields are not merged.
3. Leave every organization object unchanged, and leave every provider projection unchanged. That includes implementations, parameter values, requirement parameter overrides, evidence, results, findings, and mapping reviews.
4. A library id that was in the previous projection and is absent from the new revision is stored as `revoked: true` on the old body, with `modified` set to the time of the pull. This is the one case where RFC 0001 lets a store that is not the producer advance `modified`. The row stays so existing references still resolve. The id is not deleted.
5. Record the new pin: the bundle `version` and the commit.

A pull that is interrupted leaves the previous pin in place. The projection moves only when every object in the revision has been replaced and the pin is then updated.

The organization chooses when to pull. A pull does not edit an organization object, and it can still change computed status, because status is computed against whatever library revision is pinned. A new required test, a new parameter on a control, a changed mapping, or a control dropped from a baseline moves a control or a requirement without anyone touching an implementation.

The pull job reports what moved. Before it updates the pin, it computes status for each program at the old revision and at the new one, on the same evaluation date, and records the controls and requirements whose state differs, together with the mapping reviews the pull made stale. See [section 6](#6-mapping-reviews). The same comparison can be run without pulling, so an organization can read the effect of a revision first.

## 6. Mapping reviews

Library mappings arrive with `review_status: draft`. An organization that accepts or rejects one records that decision beside the mapping, not on it.

```yaml
type: mapping_review
id: mapping_review--7c9e6679-7425-40de-944b-e07fc1f90ae7
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
mapping_ref: mapping--nist-sp-800-171-r3-03-01-01_to_nist-sp-800-53-r5-ac-2
library_version: 0.1.0
mapping_modified: 2026-10-22T11:30:00Z
review_status: reviewed          # reviewed | rejected
summary: >
  Accepted for the 2026 program. The requirement's account-management
  statements are covered by the access-control implementations.
```

`library_version` is the bundle version that was pinned when the review was made. `mapping_modified` is the `modified` of the mapping the reviewer read. The platform copies it from the mapping when the review is written.

A review is **current** while the mapping's `modified` equals `mapping_modified`. After a pull that changes the mapping, the review is stale: it is kept, it no longer applies, and the mapping goes back to unreviewed for this organization until someone reviews the new body. An acceptance of `subset-of` is not an acceptance of the `equal-to` that replaced it. A stale rejection stops applying the same way. A review whose mapping was revoked is kept and no longer applies.

A current review with `review_status: rejected` takes the mapping out of this organization's coverage, including a mapping the library publishes as `reviewed`. One non-revoked review per organization per `mapping_ref`.

RFC 0001 lists this type in its closed set and defers the definition to this section. It uses the same envelope as every other object, and `name` is optional on it.

Customer-facing coverage still uses reviewed mappings only. A library mapping counts as reviewed for an organization when that organization has a current `mapping_review` with `review_status: reviewed` for it. A combined set from RFC 0001 counts only when every mapping in it is reviewed this way or by the library. The `review_status` on the library object stays `draft` until OpenGRC itself publishes a reviewed mapping.

## 7. Provider bundles

A provider bundle is the YAML a cloud or software provider publishes so a customer can import the service and the controls that come with it. It uses the objects in RFC 0001. It is not a new type, and it is not an OSCAL document. The OSCAL component definition is a render of the same objects, and an OSCAL component definition can be imported back into these objects.

The provider's publication is the source of truth for the bundle. After import, the organization database holds a projection. The organization's own implementations, including a system-specific override of an inherited control, stay the organization's objects.

An illustration, not a vendor's published matrix:

```yaml
type: bundle
id: bundle--com.example.cloud-idp
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Example Cloud IdP
version: "2026.11"
library:
  id: bundle--ogrc-library
  version: 0.1.0
```

```yaml
type: party
id: party--com.example
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Example
kind: organization
```

```yaml
type: component
id: component--com.example.cloud-idp
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Example Cloud IdP
kind: service
description: >
  Workforce identity service. The customer's tenant lives here.
party_ref: party--com.example
```

```yaml
type: implementation
id: implementation--com.example.cloud-idp-ogrc-ac-01
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
origin: provider
component_ref: component--com.example.cloud-idp
control_ref: control--ogrc-ac-01
status: implemented
responsibility: shared
narrative: >
  The service assigns one identity per person in the tenant and
  refuses a second active identity with the same employee id.
customer_responsibility: >
  The customer disables shared mailboxes used as logins and
  reviews guest accounts.
```

Ids use the provider's domain, the same way RFC 0001 allows `control--com.acme.badge-access`. A provider does not mint an id in the standard-library slug space. `library.version` is the OpenGRC library revision the statements were written against. `control_ref` points at a library control. A provider that is speaking a NIST control id instead sets `requirement_ref` and omits `control_ref`. That is the shape an imported OSCAL component definition takes, because those documents address `ac-3` and not an OpenGRC id.

`responsibility` is the inheritance:

| Value | What the customer imports |
|---|---|
| `provider` | The provider implements the control. Unexpired evidence on the implementation, such as the provider's report, satisfies a library test the customer has not replaced. |
| `subservice` | Same as `provider`, and `subservice_ref` names the party. |
| `shared` | The provider's half is `narrative`. The customer's half is `customer_responsibility`. The control stays a gap until the customer writes a system implementation. |
| `customer` | The product can support the control. The customer implements it. The provider row does not satisfy the control. |

Evidence in the bundle is a link or an attestation, with a URI and a digest, and `valid_until` set to the report's expiry. The bytes stay at the provider. A test in the bundle describes a check and has no `run`. The customer's harness does not execute the provider's tenant.

**Import.** The organization chooses a bundle revision and a system does not have to be named yet. Import makes the component available. Attaching it is `component_refs` on a system, which the organization writes.

1. Read the bundle. Refuse it when `spec_version` is a version this reader does not accept under the version rule in RFC 0001 section 6.2, or when `library.version` is newer than the pinned library and a `control_ref` does not resolve.
2. For each object in the revision, replace the stored provider object with the same id. The replacement is the whole object. Fields are not merged.
3. Leave every organization object unchanged. A system implementation that overrides an inherited control is an organization object and stays.
4. A provider id that was in the previous projection of this bundle and is absent from the new revision is stored as `revoked: true` on the old body. The row stays so existing references still resolve.
5. Record the pin: bundle id, `version`, and the commit or content digest the organization fetched.

An interrupted import leaves the previous pin in place. A library pull does not touch a provider projection. A provider import does not touch the library projection or any other provider's projection.

**OSCAL component definition.** `ogrc import oscal-component` reads a document such as the Django component definition and writes this bundle's objects. The component `title` and `description` become the component. Each party becomes a `party`. Each implemented requirement becomes an implementation with `requirement_ref` resolved from the OSCAL `control-id` against the pinned catalog (`ac-3` is `requirement--nist-sp-800-53-r5-ac-3`). The description becomes `narrative`.

Responsibility is decided in this order. The first match wins.

| Source | `responsibility` |
|---|---|
| Prop `provider` is `No`, or `control-origination` is `customer-configured` or `customer-provided` | `customer` |
| `control-origination` is `inherited`, `service-provider-corporate`, or `service-provider-system` | `provider` |
| `control-origination` is `shared`, or `security_control_type` is `Hybrid` | `shared` |

Anything else is `shared`. The Django file marks its controls `Hybrid`, and marks AC-14 and AU-2 with `provider: No` as well. Those two import as `customer`. The rest import as `shared`. `customer_responsibility` is copied when the OSCAL description separates the customer's sentence. The Django JSON keeps that sentence in the README only, so those imports omit the field. The control still does not meet. Object ids are `component--{uuid}` and `implementation--{uuid}` from the OSCAL uuids, so a second import of the same document replaces the same rows.

Export of a component definition writes `control-origination` from `responsibility` in the other direction: `provider` and `subservice` become `inherited`, `shared` becomes `shared`, and `customer` becomes `customer-configured`. `narrative` and `customer_responsibility` are both copied into the implemented-requirement description.

## 8. Export

On a schedule, the platform writes the organization's objects to a git repository that organization controls.

The snapshot contains:

- The organization objects listed in [section 4](#4-organization-database), including mapping reviews.
- A pin file naming the library bundle version and commit, and each imported provider bundle. It does not contain the library bodies. Those remain in this repository.
- Each imported provider projection, copied under `provider/{bundle-remainder}/`. The job overwrites that tree from the pin. A hand edit there does not change the database.

```yaml
type: bundle
id: bundle--7c9e6679-7425-40de-944b-e07fc1f90ae7
spec_version: 0.1.0
created: 2026-11-08T00:00:00Z
modified: 2026-11-08T00:00:00Z
name: Example organization
version: 2026-11-08T00:00:00Z
library:
  id: bundle--ogrc-library
  version: 0.1.0
  commit: f0de6d8d8c059d374f15e0ae07508d82e370fc1d
providers:
  - id: bundle--com.example.cloud-idp
    version: "2026.11"
    digest: sha-256:0000000000000000000000000000000000000000000000000000000000000000
```

Layout follows RFC 0001. One object per file, path `{type}/{remainder}.yaml`, under a directory the organization owns. The writer uses canonical field order so a commit is the change in objects, not a reorder of keys.

The job commits only when the tree changed. It pushes to the remote the organization configured. It does not pull, merge, or rebase. If the remote has commits the job did not write, the job stops and reports that the export repository has diverged. Someone resolves that outside the tool. The database is not updated from the repository.

Files the job does not own are left as they are. A README in that repository can stay. A hand-edited copy of an implementation file is overwritten on the next successful export, and the database does not read the hand edit.

Evidence files are not committed. The evidence object in the snapshot carries `resource.uri` and `resource.digest`. A consumer that needs the bytes fetches them from object storage and checks the hash.

### 8.1 Restore

The snapshot is how a program leaves this tool, so something has to be able to take one in. Restore loads an organization snapshot into an empty organization database. It is the path for recovering a lost database, moving to a new deployment, and arriving from another tool that writes the same objects.

Restore is not a sync. It runs once, into a database that holds no organization objects, and it is refused otherwise. There is no merge, and a database that has started work does not read a snapshot. The rule in section 1 stands for a running program: its database is the source of truth, and the export is one-way.

The input is a snapshot in the layout of [section 8](#8-export), at one commit, or the same objects as one exchange-form bundle.

1. Read the manifest. Refuse a `spec_version` this reader does not accept.
2. Pull the library at the `version` and `commit` the manifest pins, as in [section 5](#5-pull).
3. Load each provider projection from the copy under `provider/` in the snapshot, and check it against the digest the manifest pins. A copy that does not match is refused. The provider is not contacted.
4. Check the whole graph as a self-contained bundle under RFC 0001: every organization object, against the library and the provider projections just loaded. A dangling reference or a broken graph constraint refuses the restore and names the object.
5. Store each organization object as it is. The id, `created`, `modified`, and `created_by_ref` do not change. Restore is not the producer and does not advance `modified`.
6. Record the pins.

A restore that stops at any step leaves the database empty. Nothing is stored until step 4 has passed for every object.

**What does not come back.** The snapshot holds current objects, so the revision history from [section 4](#4-organization-database) starts again at the restore. Each object gets one revision, written by whoever ran the restore, and status asked for at an instant before the restore is refused instead of being computed from objects that were not known to be in force then. An organization that needs its past status keeps the database backup as well as the snapshot.

**Bytes.** Evidence bytes are not in the snapshot. After the objects are stored, restore checks each `resource.uri`: a path relative to the bundle root is read from the snapshot, and an absolute URI is fetched. Bytes that are found and match the digest are copied into this deployment's object storage. Evidence whose bytes cannot be found, or do not match, is kept and reported, and it is treated as incomplete under RFC 0001 until the bytes are supplied, so it does not count toward status. Policy and procedure bodies follow the same rule. The export job writes those bodies into the snapshot beside their objects, because an adopted policy without its text is not a policy.

**Round trip.** A snapshot restored into an empty database and exported again produces the same objects, byte for byte in canonical form. A tool passes this before it claims that a program can move through it.

## 9. OSCAL export

Government users need the same program as OSCAL. The export is a render of the organization database and the pinned library, for one system and one target NIST framework. It is not a source of truth. Editing the OSCAL and importing it back is out of scope. The database is not updated from the OSCAL.

The caller names the target framework, for example `nist-sp-800-53-r5` or `nist-sp-800-171-r3`. A program that maps to both can be exported twice. The documents use OSCAL 1.2.3, the revision of the NIST catalogs this library was imported from. Each document is written as JSON and as XML. The content is the same.

| File | What it is |
|---|---|
| `oscal/profile.json` | Selects the target-framework requirements that the program's controls map to. The profile imports the upstream NIST catalog by the `source.uri`, `source.path`, and `source.commit` on that framework. It does not copy the catalog. Parameter settings in the profile come from the binding in RFC 0001. |
| `oscal/ssp.json` | System security plan for the system. `import-profile` points at the profile in this export. |
| `oscal/mapping-collection.json` | The library mappings from OpenGRC controls, and from other requirements, onto that target framework. |
| `oscal/component-definition.json` | The components the system includes, and the implementations those components carry with no `system_ref`. |
| `oscal/assessment-results.json` | Findings on the system whose objective is on the target framework. |
| `oscal/poam.json` | Open risks that have milestones and name an in-scope control, open exceptions on in-scope implementations, and findings in force with determination `not-satisfied`. |

The git export writes these files into the snapshot. A direct download uses the same writer and does not need the git remote.

**Profile.** A target requirement is in scope when it is in the requirements of the program's effective baseline, a control on that baseline has a mapping to it, and that control has an implementation the system uses, including an inherited component implementation. Withdrawn requirements stay out. `set-parameter` entries are the target parameters that resolve under RFC 0001. An unresolved parameter is omitted.

**SSP.** The system characteristics come from the `system` object. `function` is the description. `boundary` is the authorization boundary. `information_types` are the system information, with confidentiality, integrity, and availability impact. Each component the system includes is an OSCAL component. A party with role `subservice` is a leveraged authorization, and its `authorization` block supplies the identifier and the dates.

Implemented requirements come from the implementations RFC 0001 section 8 would evaluate, projected through mappings onto OSCAL control ids. An implementation with `system_ref` and no `component_ref` is the `this-system` statement. An implementation with `component_ref` is that component's statement. A system-specific component implementation replaces the inherited one for this system.

Each in-scope target requirement becomes one `implemented-requirement`. Its `control-id` is the OSCAL id of that requirement:

- SP 800-53: the `display_id`, lowercased, with an enhancement parenthesis turned into a dot. `AC-2` is `ac-2`. `AC-2(1)` is `ac-2.1`.
- SP 800-171 Rev 3: `SP_800_171_` prefixed to the `display_id`. `03.01.01` is `SP_800_171_03.01.01`.

The statement part, when the mapping names one, becomes the OSCAL `statement-id`.

Status is derived from the implementations that map to the requirement:

| Implementations and mappings | OSCAL `implementation-status` |
|---|---|
| Every implementation is `implemented`, and every mapping is `equal-to`, `equivalent-to`, or `superset-of` | `implemented` |
| Every implementation is `not-applicable` | `not-applicable` |
| Any implementation is `planned`, and none is `implemented` or `partial` | `planned` |
| Anything else, including `exception`, `subset-of`, and `intersects-with` | `partial` |

Each contributing implementation adds its resolved control statement and its narrative to the requirement remarks. The remarks also name the mapping relationship and whether the organization's `mapping_review` accepts it. An `exception` adds its justification and expiry. A finding against an objective of the requirement is cited in the remarks and does not by itself change `implementation-status`.

NIST organization-defined parameters are filled from the binding in RFC 0001: the implementation override, then the baseline literal, then the control parameter named by `parameter_map`. The export writes an OSCAL `set-parameter` for each value that resolves. A parameter with no binding is left unset. The exporter does not invent a value for `ac_02_odp_10`. The resolved OpenGRC statement is still copied into the remarks.

**Mapping collection.** One OSCAL mapping per library mapping whose target is in the chosen framework. `source` is the OpenGRC control id. `target` is the OSCAL control id, plus the statement id when the mapping has a part. `relationship` is copied. `rationale` is copied. `confidence` is copied. `review_status` is a prop. A `mapping_review` for that mapping is a prop on the same entry. `parameter_map` is copied as a prop so a consumer can see which control parameter answers which target parameter. The collection's provenance says it was generated from the pinned library revision.

**Component definition.** One document for the components in `system.component_refs`. Each component's control implementations are the implementations with that `component_ref` and no `system_ref`, including imported provider rows. System-specific overrides stay in the SSP and out of this document, so a provider can hand the component definition to another system. `responsibility` is written as the `control-origination` prop from [section 7](#7-provider-bundles).

**Assessment results.** One finding becomes one OSCAL finding. `determination: satisfied` is `satisfied`. `determination: not-satisfied` is `not-satisfied`. The objective fragment selects the OSCAL objective id on the target control. The narrative is the observation. Evidence refs become back-matter resources by hash and URI, the same way the git snapshot records evidence. A linked risk is the associated risk, using the same likelihood, impact, and treatment as the register.

**Plan of action and milestones.** One OSCAL item per open risk that has at least one milestone and names a control mapped into the target framework, per open exception on an in-scope implementation, and per finding in force with `determination: not-satisfied`. A finding that a later `satisfied` finding replaced is not an item. The risk's milestones are the remediation schedule. `done` closes that milestone. An exception item carries the justification and `expires`. A not-satisfied finding item points at that finding and at `risk_ref` when the finding has one.

## 10. Tools

| Tool | Direction | Status |
|---|---|---|
| `ogrc import` | OSCAL catalogs to library files in this repository | Built. Writes statements, parts, parameters, and draft mappings. Assessment objectives are specified in RFC 0001 and are not written yet. It is not the organization pull. |
| Library pull | A revision of this repository to an organization database | Not built. [Section 5](#5-pull) is the contract. |
| Application | Organization database to the screen, and back | Not built. [RFC 0003](0003-application.md) is the process shape. The API reads and writes organization objects only. |
| Export job | Organization database to the organization git repository | Not built. [Section 8](#8-export) is the contract. |
| Restore | An organization snapshot to an empty organization database | Not built. [Section 8.1](#81-restore) is the contract. |
| OSCAL export | Organization database and pinned library to a profile, an SSP, a mapping collection, a component definition, assessment results, and a POA&M | Not built. [Section 9](#9-oscal-export) is the contract. The git export writes the same files. |
| Provider import | A provider bundle, or an OSCAL component definition, into an organization database | Not built. [Section 7](#7-provider-bundles) is the contract. |

The harness from RFC 0001 executes a test's `run` block and writes `result` and `evidence` objects into the organization database, including the test's `objective_refs` on the result. It does not commit them. The export job picks them up on the next run.

## 11. Open questions

1. **Review type name.** The working name is `mapping_review`. A shorter `review` collides with the idea of an audit engagement, which this RFC still leaves out.
2. **Absent library ids.** The default is to keep the previous body and set `revoked: true` when a pull no longer contains an id. Deleting the row would break references from implementations and reviews.
3. **Export remote.** The default is one repository per organization. A repository per system is a possible split once an organization has more than one program, and it is not required to start.
