"""Fixture users by dataset. Code, not files: an installed package runs from memory."""

USERS = {
    "acme": [
        {"admin": True, "id": "u1", "mfa": True, "name": "alice@acme.test", "status": "ACTIVE"},
        {"admin": False, "id": "u2", "mfa": False, "name": "bob@acme.test", "status": "ACTIVE"},
        {"admin": True, "id": "u3", "mfa": False, "name": "carol@acme.test", "status": "SUSPENDED"},
    ],
    "secure": [
        {"admin": True, "id": "s1", "mfa": True, "name": "dana@secure.test", "status": "ACTIVE"}
    ],
}
