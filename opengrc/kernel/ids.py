"""Object identifiers, RFC 0001 section 6.3."""

from uuid import UUID, uuid4


def split(object_id: str) -> tuple[str, str]:
    object_type, sep, remainder = object_id.partition("--")
    if not sep or not object_type or not remainder:
        raise ValueError(f"not an OpenGRC id: {object_id!r}")
    return object_type, remainder


def mint(object_type: str) -> str:
    return f"{object_type}--{uuid4()}"


def is_reserved(object_id: str) -> bool:
    """True when the id is in the standard-library slug space.

    Organizations use a UUID or a slug prefixed by a domain they control
    (`control--com.acme.badge-access`). A bare slug is the library's.
    """
    _, remainder = split(object_id)
    try:
        UUID(remainder)
        return False
    except ValueError:
        pass
    domain, _, _ = remainder.partition("-")
    return "." not in domain
