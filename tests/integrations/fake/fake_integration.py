"""A protocol-1 integration with no vendor: users come from fake_data.USERS[<dataset>].

`mode` in the connection config makes it misbehave on purpose: auth_failed,
rate_limited, crash, hang, garbage, incomplete, extra_fields, bad_item.
"""

import json
import os
import sys
import time

from fake_data import USERS

MANIFEST_ID, VERSION = "dev.ogrl.fake", "0.1.0"


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def fail(request_id, kind, message, **data):
    send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": message, "data": {"kind": kind, **data}},
        }
    )


def users(config):
    return USERS[config["dataset"]]


def handle(request):
    rid, method, params = request["id"], request["method"], request.get("params") or {}
    if method == "initialize":
        return send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"protocol": 1, "id": MANIFEST_ID, "version": VERSION},
            }
        )
    if method == "check":
        (snapshot,) = params["snapshots"].values()  # users@1, whatever the package id
        weak = [u for u in snapshot["items"] if u.get("admin") and not u.get("mfa")]
        result = {
            "outcome": "fail" if weak else "pass",
            "summary": f"{len(weak)} admins without MFA",
            "subjects": [
                {"kind": "account", "name": u["name"], "external_id": u["id"]} for u in weak
            ],
        }
        assert "FAKE_TOKEN" not in os.environ, "checks never see credentials"
        return send({"jsonrpc": "2.0", "id": rid, "result": result})

    config = params.get("config") or {}
    mode = config.get("mode", "")
    authorized = (
        os.environ.get("FAKE_TOKEN") == "s3cret"
        or os.environ.get("OGRL_ACCESS_TOKEN", "").startswith("access-")
        or os.environ.get("AWS_SESSION_TOKEN") == "fake-session"
    )
    if not authorized or mode == "auth_failed":
        return fail(rid, "auth_failed", "the token was rejected")
    if mode == "rate_limited":
        return fail(rid, "rate_limited", "slow down", retry_after=1)
    if mode == "crash":
        print("boom: fake crash", file=sys.stderr)
        sys.exit(3)
    if mode == "hang":
        time.sleep(3600)
    if mode == "garbage":
        sys.stdout.write("this is not json\n")
        sys.stdout.flush()
        return None
    send({"jsonrpc": "2.0", "method": "log", "params": {"message": f"{method} starting"}})
    if method == "connection.validate":
        return send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "identity": f"{config['dataset']} as svc-fathom",
                    "granted_scopes": ["users.read"],
                },
            }
        )
    if method == "collect":
        rows = users(config)
        if mode == "extra_fields":
            rows = [{**u, "password_hash": "x"} for u in rows]
        if mode == "bad_item":
            rows = [{"id": 1}]
        if mode == "incomplete":
            rows = rows[:1]
        for start in range(0, len(rows), 2):  # two per batch, to exercise batching
            send(
                {"jsonrpc": "2.0", "method": "items", "params": {"items": rows[start : start + 2]}}
            )
        return send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "count": len(rows),
                    "complete": mode != "incomplete",
                    **({"reason": "rate limited after page 1"} if mode == "incomplete" else {}),
                },
            }
        )
    return fail(rid, "invalid_config", f"unknown method {method}")


def main():
    for line in sys.stdin:
        if line.strip():
            handle(json.loads(line))


if __name__ == "__main__":
    main()
