"""The permission catalog. Ids are the authorization contract; names may change."""

from enum import StrEnum


class Permission(StrEnum):
    # value, human-readable name for role-assignment screens
    def __new__(cls, value: str, label: str) -> "Permission":
        member = str.__new__(cls, value)
        member._value_ = value
        member.label = label
        return member

    label: str

    LIBRARY_READ = "library:read", "Read the shared library"
    LIBRARY_PULL = "library:pull", "Load a library revision"

    CONTROLS_READ = "controls:read", "Read controls"
    CONTROLS_WRITE = "controls:write", "Create and edit custom controls"
    CONTROLS_REVOKE = "controls:revoke", "Revoke custom controls"

    MAPPINGS_WRITE = "mappings:write", "Draft organization mappings"
    MAPPINGS_REVIEW = "mappings:review", "Accept or reject library mappings"

    PROGRAMS_READ = "programs:read", "Read programs, status, and summaries"
    PROGRAMS_WRITE = "programs:write", "Create and edit programs and baselines"
    PROGRAMS_RENDER = "programs:render", "Render a program package (OSCAL)"

    IMPLEMENTATIONS_WRITE = "implementations:write", "Draft implementation narratives"
    # Moving an implementation to `implemented` is an attestation by a person
    # (RFC 0003 section 4). Agents draft; they do not hold this.
    IMPLEMENTATIONS_ATTEST = "implementations:attest", "Mark implementations implemented"

    TESTS_WRITE = "tests:write", "Author tests"
    TESTS_RUN = "tests:run", "Run tests through the harness"
    EVIDENCE_WRITE = "evidence:write", "Record results and upload evidence"

    FINDINGS_WRITE = "findings:write", "Record assessor findings"
    EXCEPTIONS_APPROVE = "exceptions:approve", "Waive an implementation"
    RISKS_WRITE = "risks:write", "Edit risks and milestones"

    EXPORTS_RUN = "exports:run", "Write the git snapshot"
    CONNECTORS_RUN = "connectors:run", "Start connector jobs"
    MEMBERS_MANAGE = "members:manage", "Manage people, agents, and their roles"
