"""The object collections: list, create, get, update, and revoke per type.

Each collection's permissions come from its `TypeSpec`, so the route guard
and the operation check the same permission. Sub-collections (a control's
mappings, an implementation's results) are listed with their parent.
"""

from dataclasses import dataclass, field
from http import HTTPMethod, HTTPStatus

from opengrc.api.paths.endpoint import Endpoint
from opengrc.kernel.models import Envelope
from opengrc.operations import types as t
from opengrc.operations.objects import TypeSpec
from opengrc.operations.pagination import Page, PageRequest


@dataclass(frozen=True)
class SubList:
    endpoint: Endpoint
    spec: TypeSpec
    parent: TypeSpec
    query: type[PageRequest]
    field: str  # how a child row names its parent: a ref field, or a callable key below


@dataclass(frozen=True)
class Collection:
    spec: TypeSpec
    tag: str
    path: str
    index: Endpoint | None = None
    create: Endpoint | None = None
    get: Endpoint | None = None
    update: Endpoint | None = None
    revoke: Endpoint | None = None
    subs: list[SubList] = field(default_factory=list)

    def endpoints(self) -> tuple[Endpoint, ...]:
        own = (self.index, self.create, self.get, self.update, self.revoke)
        return (*(e for e in own if e is not None), *(s.endpoint for s in self.subs))


def collection(
    spec: TypeSpec,
    tag: str,
    path: str,
    *,
    plural: str,
    singular: str,
    list_id: str | None = None,
    create_id: str | None = None,
    get_id: str | None = None,
    update_id: str | None = None,
    revoke_id: str | None = None,
) -> Collection:
    model: type[Envelope] = spec.model
    item = f"{path}/{{id}}"

    def ep(op_id: str | None, **kw) -> Endpoint | None:
        return Endpoint(id=op_id, tag=tag, **kw) if op_id else None

    return Collection(
        spec=spec,
        tag=tag,
        path=path,
        index=ep(
            list_id,
            summary=f"List {plural}.",
            method=HTTPMethod.GET,
            path=path,
            permission=spec.read_permission,
            response=Page[model],
        ),
        create=ep(
            create_id,
            summary=f"Create {singular}.",
            method=HTTPMethod.POST,
            path=path,
            permission=spec.write_permission,
            response=model,
            success_status=HTTPStatus.CREATED,
        ),
        get=ep(
            get_id,
            summary=f"Get one {singular}.",
            method=HTTPMethod.GET,
            path=item,
            permission=spec.read_permission,
            response=model,
        ),
        update=ep(
            update_id,
            summary=f"Update {singular}.",
            method=HTTPMethod.PATCH,
            path=item,
            permission=spec.write_permission,
            response=model,
            description="JSON Merge Patch. Arrays replace. `If-Match` is `modified`.",
        ),
        revoke=ep(
            revoke_id,
            summary=f"Revoke {singular}.",
            method=HTTPMethod.POST,
            path=f"{item}/revoke",
            permission=spec.revoke_permission,
            response=model,
        ),
    )


def sub(
    op_id: str,
    tag: str,
    path: str,
    spec: TypeSpec,
    parent: TypeSpec,
    query: type[PageRequest],
    ref: str,
    summary: str,
) -> SubList:
    return SubList(
        Endpoint(
            id=op_id,
            summary=summary,
            method=HTTPMethod.GET,
            path=path,
            tag=tag,
            permission=spec.read_permission,
            response=Page[spec.model],
        ),
        spec,
        parent,
        query,
        ref,
    )


FRAMEWORKS = collection(
    t.FRAMEWORK,
    "Frameworks",
    "/frameworks",
    plural="frameworks",
    singular="a framework",
    list_id="listFrameworks",
    get_id="getFramework",
)

REQUIREMENTS = collection(
    t.REQUIREMENT,
    "Requirements",
    "/requirements",
    plural="requirements",
    singular="a requirement",
    list_id="listRequirements",
    get_id="getRequirement",
)
REQUIREMENTS.subs.append(
    sub(
        "listRequirementMappings",
        "Requirements",
        "/requirements/{id}/mappings",
        t.MAPPING,
        t.REQUIREMENT,
        PageRequest,
        "target_ref",
        "Mappings whose target is this requirement.",
    )
)

CONTROLS = collection(
    t.CONTROL,
    "Controls",
    "/controls",
    plural="library and custom controls",
    singular="a custom control",
    list_id="listControls",
    create_id="createControl",
    get_id="getControl",
    update_id="updateControl",
    revoke_id="revokeControl",
)
CONTROLS.subs.extend(
    [
        sub(
            "listControlMappings",
            "Controls",
            "/controls/{id}/mappings",
            t.MAPPING,
            t.CONTROL,
            PageRequest,
            "source_ref",
            "Mappings whose source is this control.",
        ),
        sub(
            "listControlTests",
            "Controls",
            "/controls/{id}/tests",
            t.TEST,
            t.CONTROL,
            PageRequest,
            "control_ref",
            "Tests of this control.",
        ),
        sub(
            "listControlImplementations",
            "Controls",
            "/controls/{id}/implementations",
            t.IMPLEMENTATION,
            t.CONTROL,
            t.ScopedImplementationQuery,
            "control_ref",
            "Implementations of this control.",
        ),
    ]
)

MAPPINGS = collection(
    t.MAPPING,
    "Mappings",
    "/mappings",
    plural="mappings",
    singular="an organization mapping",
    list_id="listMappings",
    create_id="createMapping",
    get_id="getMapping",
    update_id="updateMapping",
    revoke_id="revokeMapping",
)

BASELINES = collection(
    t.BASELINE,
    "Baselines",
    "/baselines",
    plural="library and organization baselines",
    singular="an organization baseline",
    list_id="listBaselines",
    create_id="createBaseline",
    get_id="getBaseline",
    update_id="updateBaseline",
    revoke_id="revokeBaseline",
)

TESTS = collection(
    t.TEST,
    "Tests",
    "/tests",
    plural="tests",
    singular="an organization test",
    list_id="listTests",
    create_id="createTest",
    get_id="getTest",
    update_id="updateTest",
    revoke_id="revokeTest",
)

PARTIES = collection(
    t.PARTY,
    "Parties",
    "/parties",
    plural="parties",
    singular="a party",
    list_id="listParties",
    create_id="createParty",
    get_id="getParty",
    update_id="updateParty",
    revoke_id="revokeParty",
)

COMPONENTS = collection(
    t.COMPONENT,
    "Components",
    "/components",
    plural="components",
    singular="a component",
    list_id="listComponents",
    create_id="createComponent",
    get_id="getComponent",
    update_id="updateComponent",
    revoke_id="revokeComponent",
)
COMPONENTS.subs.append(
    sub(
        "listComponentImplementations",
        "Components",
        "/components/{id}/implementations",
        t.IMPLEMENTATION,
        t.COMPONENT,
        PageRequest,
        "component_ref",
        "Implementations on this component.",
    )
)

SYSTEMS = collection(
    t.SYSTEM,
    "Systems",
    "/systems",
    plural="systems",
    singular="a system",
    list_id="listSystems",
    create_id="createSystem",
    get_id="getSystem",
    update_id="updateSystem",
    revoke_id="revokeSystem",
)

PROGRAMS = collection(
    t.PROGRAM,
    "Programs",
    "/programs",
    plural="programs",
    singular="a program",
    list_id="listPrograms",
    create_id="createProgram",
    get_id="getProgram",
    update_id="updateProgram",
    revoke_id="revokeProgram",
)

IMPLEMENTATIONS = collection(
    t.IMPLEMENTATION,
    "Implementations",
    "/implementations",
    plural="implementations",
    singular="an implementation",
    list_id="listImplementations",
    create_id="createImplementation",
    get_id="getImplementation",
    update_id="updateImplementation",
    revoke_id="revokeImplementation",
)
IMPLEMENTATIONS.subs.extend(
    [
        sub(
            "listImplementationResults",
            "Implementations",
            "/implementations/{id}/results",
            t.RESULT,
            t.IMPLEMENTATION,
            t.OutcomeQuery,
            "implementation_ref",
            "Results recorded against this implementation.",
        ),
        sub(
            "listImplementationEvidence",
            "Implementations",
            "/implementations/{id}/evidence",
            t.EVIDENCE,
            t.IMPLEMENTATION,
            t.ValidOnQuery,
            "implementation_ref",
            "Evidence attached to this implementation.",
        ),
    ]
)

RESULTS = collection(
    t.RESULT,
    "Results",
    "/results",
    plural="results",
    singular="a manual test result",
    list_id="listResults",
    create_id="createResult",
    get_id="getResult",
)

EVIDENCE = collection(
    t.EVIDENCE,
    "Evidence",
    "/evidence",
    plural="evidence",
    singular="evidence",
    list_id="listEvidence",
    create_id="createEvidence",
    get_id="getEvidence",
    update_id="updateEvidence",
    revoke_id="revokeEvidence",
)

FINDINGS = collection(
    t.FINDING,
    "Findings",
    "/findings",
    plural="findings",
    singular="a finding",
    list_id="listFindings",
    create_id="createFinding",
    get_id="getFinding",
    update_id="updateFinding",
    revoke_id="revokeFinding",
)

POLICIES = collection(
    t.POLICY,
    "Policies",
    "/policies",
    plural="policies",
    singular="a policy",
    list_id="listPolicies",
    create_id="createPolicy",
    get_id="getPolicy",
    update_id="updatePolicy",
    revoke_id="revokePolicy",
)

PROCEDURES = collection(
    t.PROCEDURE,
    "Procedures",
    "/procedures",
    plural="procedures",
    singular="a procedure",
    list_id="listProcedures",
    create_id="createProcedure",
    get_id="getProcedure",
    update_id="updateProcedure",
    revoke_id="revokeProcedure",
)

RISKS = collection(
    t.RISK,
    "Risks",
    "/risks",
    plural="risks",
    singular="a risk",
    list_id="listRisks",
    create_id="createRisk",
    get_id="getRisk",
    update_id="updateRisk",
    revoke_id="revokeRisk",
)

EXCEPTIONS = collection(
    t.EXCEPTION,
    "Exceptions",
    "/exceptions",
    plural="exceptions",
    singular="an exception",
    list_id="listExceptions",
    create_id="createException",
    get_id="getException",
    update_id="updateException",
    revoke_id="revokeException",
)

MAPPING_REVIEWS = collection(
    t.MAPPING_REVIEW,
    "Mapping reviews",
    "/mapping-reviews",
    plural="mapping reviews",
    singular="a mapping review",
    list_id="listMappingReviews",
    create_id="createMappingReview",
    get_id="getMappingReview",
    update_id="updateMappingReview",
    revoke_id="revokeMappingReview",
)

ALL_COLLECTIONS = (
    FRAMEWORKS,
    REQUIREMENTS,
    CONTROLS,
    MAPPINGS,
    BASELINES,
    TESTS,
    PARTIES,
    COMPONENTS,
    SYSTEMS,
    PROGRAMS,
    IMPLEMENTATIONS,
    RESULTS,
    EVIDENCE,
    FINDINGS,
    POLICIES,
    PROCEDURES,
    RISKS,
    EXCEPTIONS,
    MAPPING_REVIEWS,
)

ALL = tuple(e for c in ALL_COLLECTIONS for e in c.endpoints())
