"""The kernel: RFC 0001 objects, graph checks, parameters, and status.

Pure. No network, database, shell, or model client (RFC 0003 section 3).
Everything else imports the kernel; the kernel imports nothing of ours.

    models       the objects, one Pydantic model per type
    ids          identifiers, fragments, the library slug space
    graph        an indexed, read-only view over a set of objects
    constraints  the graph constraints in section 7.20
    baselines    the effective baseline (7.5)
    parameters   parameter resolution (7.3, 7.4)
    status       computed status and requirement coverage (8)
    bundles      objects as YAML files, exchange bundles, and canonical JSON
"""
