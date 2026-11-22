"""Feature switches for optional modules (agents, git export).

A deployment with no model configured runs without agents (RFC 0003 section 4).
An endpoint that names a feature returns 404-like `feature-disabled` when off.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol

from ogrl.access import Principal


class Feature(StrEnum):
    AGENTS = "agents"
    GIT_EXPORT = "git_export"


class FeatureEvaluator(Protocol):
    def enabled(self, feature: Feature, principal: Principal | None) -> bool: ...


class StaticFeatures:
    def __init__(self, enabled: Iterable[Feature] = ()) -> None:
        self._enabled = frozenset(enabled)

    def enabled(self, feature: Feature, principal: Principal | None) -> bool:
        return feature in self._enabled
