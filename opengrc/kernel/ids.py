"""Object identifiers and references, RFC 0001 sections 6.3 and 6.4."""

import re
from uuid import UUID, uuid4

TYPE_RE = re.compile(r"^[a-z_]+$")
REMAINDER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")


def split(object_id: str) -> tuple[str, str]:
    """`type--remainder`, split on the first `--`. Raises ValueError when malformed."""
    object_type, sep, remainder = object_id.partition("--")
    if not sep or not object_type or not remainder:
        raise ValueError(f"not an OpenGRC id: {object_id!r}")
    if not TYPE_RE.match(object_type):
        raise ValueError("the type part is lowercase ASCII letters and underscores")
    if "--" in remainder or not REMAINDER_RE.match(remainder):
        raise ValueError(
            "the remainder is lowercase letters, digits, hyphen, dot, and underscore, "
            "starts and ends with a letter or a digit, and contains no --"
        )
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
    if "_" in remainder:  # `_to_` and `_part_` are library mapping joins
        return True
    domain, _, _ = remainder.partition("-")
    return "." not in domain


def base(ref: str) -> str:
    """The object id of a reference, without any `#fragment`."""
    return ref.partition("#")[0]


def fragment(ref: str) -> str | None:
    _, sep, frag = ref.partition("#")
    return frag if sep else None


def type_of(ref: str) -> str | None:
    try:
        return split(base(ref))[0]
    except ValueError:
        return None


def objective_of(ref: str) -> str | None:
    """`requirement--x#obj.a` is objective `a`. None for any other reference."""
    frag = fragment(ref)
    return frag[4:] if frag and frag.startswith("obj.") and len(frag) > 4 else None
