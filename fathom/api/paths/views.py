"""Computed views, content routes, providers, and jobs."""

from http import HTTPMethod, HTTPStatus

from fathom.access import Permission as P
from fathom.api.paths.endpoint import Endpoint
from fathom.features import Feature
from fathom.kernel.models import Evidence, Policy, Procedure
from fathom.operations import views
from fathom.operations.pagination import Page
from fathom.operations.records import Job, LibraryPin, ProviderPin

GET, POST = HTTPMethod.GET, HTTPMethod.POST
ACCEPTED = HTTPStatus.ACCEPTED

GET_LIBRARY = Endpoint(
    id="getLibrary",
    summary="The pinned library revision.",
    method=GET,
    path="/library",
    tag="Library",
    permission=P.LIBRARY_READ,
    response=LibraryPin | dict,
)
PULL_LIBRARY = Endpoint(
    id="pullLibrary",
    summary="Replace the library projection with one revision.",
    method=POST,
    path="/library/pull",
    tag="Library",
    permission=P.LIBRARY_PULL,
    response=Job,
    success_status=ACCEPTED,
)
GET_EFFECTIVE_BASELINE = Endpoint(
    id="getEffectiveBaseline",
    summary="The baseline after `extends_ref` is applied.",
    method=GET,
    path="/baselines/{id}/effective",
    tag="Baselines",
    permission=P.CONTROLS_READ,
    response=views.EffectiveBaseline,
)
RUN_TEST = Endpoint(
    id="runTest",
    summary="Ask the harness to execute this test.",
    method=POST,
    path="/tests/{id}/runs",
    tag="Tests",
    permission=P.TESTS_RUN,
    response=Job,
    success_status=ACCEPTED,
)
LIST_SYSTEM_GAPS = Endpoint(
    id="listSystemGaps",
    summary="Controls in gap for every program on this system.",
    method=GET,
    path="/systems/{id}/gaps",
    tag="Systems",
    permission=P.PROGRAMS_READ,
    response=views.SystemGaps,
)
GET_PROGRAM_SUMMARY = Endpoint(
    id="getProgramSummary",
    summary="Counts for the readiness view.",
    method=GET,
    path="/programs/{id}/summary",
    tag="Programs",
    permission=P.PROGRAMS_READ,
    response=views.ProgramSummary,
)
GET_PROGRAM_SPRS = Endpoint(
    id="getProgramSprs",
    summary="SPRS score, POA&M eligibility, and CMMC reminders.",
    method=GET,
    path="/programs/{id}/sprs",
    tag="Programs",
    permission=P.PROGRAMS_READ,
    response=views.SprsReport,
    description=(
        "32 CFR 170.24 score and 170.21 POA&M rules for a program on a CMMC Level 2 baseline."
    ),
)
GET_PROGRAM_STATUS = Endpoint(
    id="getProgramStatus",
    summary="Computed status for the program at an instant.",
    method=GET,
    path="/programs/{id}/status",
    tag="Programs",
    permission=P.PROGRAMS_READ,
    response=views.ProgramStatus,
)
CREATE_PROGRAM_RENDER = Endpoint(
    id="createProgramRender",
    summary="Render the program as OSCAL or an SSP.",
    method=POST,
    path="/programs/{id}/renders",
    tag="Programs",
    permission=P.PROGRAMS_RENDER,
    response=Job,
    success_status=ACCEPTED,
)

GET_EVIDENCE_CONTENT = Endpoint(
    id="getEvidenceContent",
    summary="The evidence bytes.",
    method=GET,
    path="/evidence/{id}/content",
    tag="Evidence",
    permission=P.PROGRAMS_READ,
)
UPLOAD_EVIDENCE_CONTENT = Endpoint(
    id="uploadEvidenceContent",
    summary="Store evidence bytes and set the digest.",
    method=POST,
    path="/evidence/{id}/content",
    tag="Evidence",
    permission=P.EVIDENCE_WRITE,
    response=Evidence,
)
GET_POLICY_CONTENT = Endpoint(
    id="getPolicyContent",
    summary="The policy body.",
    method=GET,
    path="/policies/{id}/content",
    tag="Policies",
    permission=P.PROGRAMS_READ,
)
UPLOAD_POLICY_CONTENT = Endpoint(
    id="uploadPolicyContent",
    summary="Store the policy body and set the digest.",
    method=POST,
    path="/policies/{id}/content",
    tag="Policies",
    permission=P.POLICIES_WRITE,
    response=Policy,
)
GET_PROCEDURE_CONTENT = Endpoint(
    id="getProcedureContent",
    summary="The procedure body.",
    method=GET,
    path="/procedures/{id}/content",
    tag="Procedures",
    permission=P.PROGRAMS_READ,
)
UPLOAD_PROCEDURE_CONTENT = Endpoint(
    id="uploadProcedureContent",
    summary="Store the procedure body and set the digest.",
    method=POST,
    path="/procedures/{id}/content",
    tag="Procedures",
    permission=P.POLICIES_WRITE,
    response=Procedure,
)

LIST_PROVIDERS = Endpoint(
    id="listProviders",
    summary="List imported provider bundles.",
    method=GET,
    path="/providers",
    tag="Providers",
    permission=P.PROGRAMS_READ,
    response=views.DataList[ProviderPin],
)
IMPORT_PROVIDER = Endpoint(
    id="importProvider",
    summary="Import a provider bundle or an OSCAL component definition.",
    method=POST,
    path="/providers",
    tag="Providers",
    permission=P.PROVIDERS_IMPORT,
    response=Job,
    success_status=ACCEPTED,
)
GET_PROVIDER = Endpoint(
    id="getProvider",
    summary="Get one provider pin.",
    method=GET,
    path="/providers/{id}",
    tag="Providers",
    permission=P.PROGRAMS_READ,
    response=ProviderPin,
)

EXPORT_GIT = Endpoint(
    id="exportGit",
    summary="Write the organization snapshot to the git remote.",
    method=POST,
    path="/exports/git",
    tag="Jobs",
    permission=P.EXPORTS_RUN,
    response=Job,
    success_status=ACCEPTED,
    feature=Feature.GIT_EXPORT,
)
RESTORE = Endpoint(
    id="restoreOrganization",
    summary="Load an organization snapshot into an empty database.",
    method=POST,
    path="/restore",
    tag="Jobs",
    permission=P.RESTORE_RUN,
    response=Job,
    success_status=ACCEPTED,
)
LIST_JOBS = Endpoint(
    id="listJobs",
    summary="List jobs.",
    method=GET,
    path="/jobs",
    tag="Jobs",
    permission=P.PROGRAMS_READ,
    response=Page[Job],
)
GET_JOB = Endpoint(
    id="getJob",
    summary="Get one job.",
    method=GET,
    path="/jobs/{id}",
    tag="Jobs",
    permission=P.PROGRAMS_READ,
    response=Job,
)
GET_JOB_FILE = Endpoint(
    id="getJobFile",
    summary="Download one file a render produced.",
    method=GET,
    path="/jobs/{id}/files/{filename}",
    tag="Jobs",
    permission=P.PROGRAMS_READ,
)
ALL = (
    GET_LIBRARY,
    PULL_LIBRARY,
    GET_EFFECTIVE_BASELINE,
    RUN_TEST,
    LIST_SYSTEM_GAPS,
    GET_PROGRAM_SUMMARY,
    GET_PROGRAM_STATUS,
    GET_PROGRAM_SPRS,
    CREATE_PROGRAM_RENDER,
    GET_EVIDENCE_CONTENT,
    UPLOAD_EVIDENCE_CONTENT,
    GET_POLICY_CONTENT,
    UPLOAD_POLICY_CONTENT,
    GET_PROCEDURE_CONTENT,
    UPLOAD_PROCEDURE_CONTENT,
    LIST_PROVIDERS,
    IMPORT_PROVIDER,
    GET_PROVIDER,
    EXPORT_GIT,
    RESTORE,
    LIST_JOBS,
    GET_JOB,
    GET_JOB_FILE,
)
