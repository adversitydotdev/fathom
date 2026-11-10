"""Composition root. The one place concrete implementations are chosen.

Everything below this file depends on protocols. Swapping Postgres for
memory, Casbin for the static policy, or adding a runner happens here.
"""

from dataclasses import dataclass, field

from opengrc.access import Authorizer, StaticPolicy
from opengrc.auth import Authenticator
from opengrc.features import FeatureEvaluator, StaticFeatures
from opengrc.operations.controls import ControlRepository, ControlService
from opengrc.persistence.memory import MemoryControls
from opengrc.plugins import Plugins


@dataclass(frozen=True)
class Container:
    version: str
    authenticator: Authenticator
    authorizer: Authorizer
    features: FeatureEvaluator
    controls: ControlService
    plugins: Plugins = field(default_factory=Plugins)


def build(
    *,
    authenticator: Authenticator,
    controls: ControlRepository | None = None,
    authorizer: Authorizer | None = None,
    features: FeatureEvaluator | None = None,
    version: str = "0.1.0",
) -> Container:
    authorizer = authorizer or StaticPolicy()
    plugins = Plugins()
    # plugins.runners.register("shell", ShellRunner())        # once it exists
    # plugins.importers.register("nist", NistImporter())
    return Container(
        version=version,
        authenticator=authenticator,
        authorizer=authorizer,
        features=features or StaticFeatures(),
        controls=ControlService(controls or MemoryControls(), authorizer),
        plugins=plugins,
    )
