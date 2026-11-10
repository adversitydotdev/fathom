# RFC 0004: HTTP API

| | |
|---|---|
| Status | Draft |
| Spec version | 0.1.0 |
| Date | 2026-11-08 |
| Depends on | [RFC 0001](0001-object-model.md), [RFC 0002](0002-tooling.md), [RFC 0003](0003-application.md) |

This document is the proposal for the HTTP API the `opengrc` process serves. The contract is [api/openapi.yaml](../../api/openapi.yaml). This RFC records why the resources have the shape they do. It is written so it can be edited in place.

## 1. Summary

The API exchanges the objects from RFC 0001. A response body is that object, or a page of them, or a computed view the kernel already knows how to derive. Vanta, Drata, Secureframe, and Paramify expose the same operational work under product names. Those names are mapped onto our objects below. Where a product has a workflow the language does not have, this API does not invent a resource for it.

The API is the only writer of an organization's database, as in RFC 0003. The library commands of `ogrc` do not call it. Organization commands on the CLI, once they exist, do, as in RFC 0003. The web application does not recompute status.

## 2. What the other products actually expose

The public APIs, read in November 2026, group the same way.

| Work | Vanta | Drata | Secureframe | Paramify | OpenGRC resource |
|---|---|---|---|---|---|
| Practice the org implements | Control, with owner and implementation notes | Control, with owners, requirements, tests, evidence | Control (read) | Requirement on an element | `control` plus `implementation` |
| Publication the practice is judged against | Framework and its controls | Requirements and reports | Framework | Target framework on a project | `framework`, `requirement`, `baseline`, `program` |
| Crosswalk | Control-to-document and control-to-test links | Control linked to requirement ids | Implicit in the product | Control mappings on an issue | `mapping`, `mapping_review` |
| Check | Test, with status, owner, failing items | Monitor and test | Test, create and update | Validator, pass fail or partial | `test`, `result` |
| Proof | Document upload, then submit | Evidence library, file on a control or a person | Evidence on a test | Evidence set, then artifact upload | `evidence` and its content |
| Mandate | Policy document | Policy linked from a control | Knowledge base, separate from policy | Policies as a generated deliverable | `policy`, `procedure` |
| What might go wrong | Risk scenario and its controls | Risk | Vendor risk, separate from issues | Issue, with risk and milestones | `risk` |
| Waiver | Deactivated test | Archived or disabled control | Archived vendor or connection | Deviation | `exception`, or `revoked` on the object |
| Assessor's call | Not a public resource | Not a public resource | Not a public resource | Assessment and assessment cycle | `finding`, and `GET` status at a date |
| Inherited service | Vendor and its documents | Vendor, review, sub-processor | Vendor and integration connection | Element | `party`, `component`, provider bundle |
| Who owns it | User | Personnel and user | User | Person on an issue | `party` |
| Package out | Not the public control API | Report | Test export | `GET /issues/oscal`, SSP, POA&M | Render job |

Paramify is the closest on the federal side. An issue is their POA&M line, a deviation is a waiver, an element is a component, and an evidence set is the container an artifact is uploaded to. Vanta and Drata are the closest on the commercial side. A control there is what we split into a library `control` and an `implementation`, because the practice is shared and the narrative belongs to one system.

## 3. Rules

**The body is the object.** Field names are the language. The API does not rename `control_ref` to `controlId`. Clients that want a joined view use the computed routes.

**Pages are cursors.** A list takes `limit` (default 50, maximum 200) and `cursor`. The response is `{ "data": [], "page": { "next_cursor": } }`. `next_cursor` is omitted on the last page. Filters are query parameters and match the way those products slice a program: by system, control, framework, status, owner, and a date.

**Writes send `If-Match`.** The value is the object's current `modified` timestamp. A stale writer receives 412. Create does not send it. The server sets `created`, `modified`, and `spec_version`. The client may supply `id` when it is a UUID or a domain slug it controls. The server mints a UUID when `id` is omitted. An id in the standard-library slug space is rejected.

**A write body takes the whole envelope.** Besides the fields of its type, every create and update accepts `tags`, `external_references`, `extensions`, and `lang`. A field the server does not know is stored and returned, which is the round-trip rule in RFC 0001. The server models keep unknown fields. They do not drop them.

**`If-Match` is exact.** `modified` changes on every write, carries fractional seconds, and is strictly later than the value before it. Two writes in the same second have different values.

**Results and complete evidence do not change.** There is no `PATCH` on a result. `PATCH` on evidence changes `name` and `tags`, and, until the content is uploaded, the rest. After that the fields RFC 0001 freezes return 409. A correction is a revoke and a new object.

**Past status uses past objects.** `at` in the past is computed from the revisions in force at `at`, as in RFC 0002 section 4. It is not today's objects against an old date.

**Revoke, do not delete.** RFC 0001 says a revoked id is never reused. `POST /{collection}/{id}/revoke` sets `revoked: true` and returns the object. Lists hide revoked objects unless `revoked=true`. There is no `DELETE`. Drata's archive and Vanta's deactivate are this operation when the thing being archived is one of our objects.

**Library rows and provider rows are read-only.** `PATCH` on one returns 409. A judgment about a library mapping is a `mapping_review`. A customer's half of a shared control is a new `implementation` with `system_ref`, which RFC 0001 already prefers over the inherited row.

**Long work is a job.** A test run, a library pull, a provider import, a render, a git export, and a restore return 202 and a `job`. The client polls `GET /jobs/{id}`. The job's product is an object id or a file, not a second copy of the rules.

**Nested lists stay on the parent.** Milestones live on the risk. Parameters live on the control. Parts and objectives live on the requirement. Paramify exposes milestones as their own routes. We patch the risk. A new exception, finding, result, or evidence is its own object because it has its own id and lifecycle.

**Status is a view.** `GET /programs/{id}/status` is the kernel's section 8 computation for that program at `at`. The words `met`, `gap`, `waived`, and `out_of_scope` are not stored. Requirement coverage uses the same call. The screen and any other client render this payload. They do not recompute it.

**Bytes are a side route.** `POST /evidence/{id}/content`, and the same for a policy or a procedure, stores the file, sets `resource.uri` and `resource.digest`, and returns the object. `GET` of that content returns the bytes. The object never contains them. This is Paramify's artifact upload and Vanta's document upload, without a separate evidence-set type. The recurring request is the test, the policy, or the procedure. Each collection is a new `evidence` object, and `GET /evidence?implementation_id=` is the history.

## 4. How a program is operated

These are the calls behind the screens those products have, in our resources.

1. `POST /library/pull` loads a revision of this repository.
2. `POST /providers` imports a provider bundle or an OSCAL component definition. `PATCH /systems/{id}` adds the component to `component_refs`.
3. `POST /programs` binds a system to a baseline. That is a library baseline, or one the organization wrote with `POST /baselines` to add custom controls or to choose its own requirements. `GET /baselines/{id}/effective` is the baseline after `extends_ref` is applied, which is what status is computed against.
4. `PUT` is not used. `POST /implementations` records how the system carries out a control. `PATCH` updates the narrative, the status, and parameter values.
5. `POST /tests` is an organization's methodology. `POST /tests/{id}/runs` asks the harness to execute it.
6. `POST /evidence` and `POST /evidence/{id}/content` attach a file a person uploaded. A run creates evidence itself.
7. `POST /exceptions` waives an implementation. `POST /findings` records an assessor's determination.
8. `PATCH /risks/{id}` keeps the treatment and the milestones.
9. `GET /programs/{id}/summary` and `GET /programs/{id}/status` are the readiness view.
10. `POST /programs/{id}/renders` with `view: oscal` produces the profile, SSP, mapping collection, component definition, assessment results, and POA&M from RFC 0002. `POST /exports/git` writes the snapshot.

`POST /restore` is the other direction, once: it loads a snapshot into a database that has no organization objects, as in RFC 0002 section 8.1. It returns 409 on a database that has any. It is not a way to edit a program from git.

`POST /mappings` is for a crosswalk the organization authors. It does not edit the library. When it names a source and target the library also maps, the organization's mapping replaces the library's in this organization's status, which is how a different relationship is recorded. `POST /mapping-reviews` accepts or rejects a library mapping for this organization.

## 5. Workflows this API does not grow a resource for

RFC 0001 leaves these out of the language. The products have them. Adding a route without an object would create a second model.

| Their feature | Why it waits |
|---|---|
| Personnel, HRIS match, background checks, training completion per person | A `party` can own an implementation. A training record is evidence on the control that requires training. A personnel directory with compliance checks is a different product. |
| Devices, cloud resources, repositories, asset scope per framework | Inventory is a CMDB. A result may name a subject. The subject is not an asset record. |
| Vendor questionnaires, security reviews, renewal calendars, sub-processor registers | A subservice party, a component, and a provider bundle are the inherited-control case. A vendor register is the non-goal RFC 0001 already names. |
| Trust center and security questionnaires | A public marketing site and a questionnaire workflow. The program data they would publish is already `GET /programs/{id}/status`. |
| Tickets in Jira or ServiceNow | A connector can create evidence or read a ticket later. The ticket is not an object. |
| Per-product integration catalogs | Connectors are the port in RFC 0003. `GET /connectors` lists what this deployment installed. There is no `/integrations/aws`. |

## 6. Errors

Errors are `application/problem+json`. `type` is a URN.

| Status | When |
|---|---|
| 400 | The body or a query parameter violates the schema or a graph constraint. |
| 401 | No bearer token. |
| 403 | The token is not allowed this action. The permission model is not in this revision. See open questions. |
| 404 | The id is unknown. |
| 409 | The object is a library or provider row, or the id is already in use. |
| 412 | `If-Match` does not equal `modified`. |
| 415 | A content upload is not the media type the route accepts. |

## 7. Open questions

1. **Authentication.** The spec requires a bearer token and does not say how it is issued. Accounts were deferred in RFC 0001. The next revision of this API names the token exchange and the organization it selects.
2. **Authorization.** Vanta and Drata scope tokens to actions such as "list controls." We have not named roles. Until we do, a token may call every route on this server, and the server is one organization.
3. **Webhooks.** Those products notify a failing test to Slack or a ticket. A subscription resource is easy to add and hard to deliver reliably. It waits until a caller asks for it.
4. **Partial update shape.** `PATCH` is a merge of the fields sent. Arrays replace. Sending `milestones` replaces the whole list. JSON Merge Patch (RFC 7386) is the default. JSON Patch is more precise and worse to author.
