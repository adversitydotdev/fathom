"""Plugin registry. In-tree plugins register here at startup in the composition root.

Out-of-tree runners and connectors are subprocesses (RFC 0003 section 6);
their adapter is an ordinary `Runner` or `Connector` registered here.
"""

from dataclasses import dataclass, field

from ogrl.plugins.ports import Connector, Importer, Renderer, Runner


class Registry[T]:
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str, plugin: T) -> None:
        if name in self._items:
            raise ValueError(f"{self._kind} {name!r} is already registered")
        self._items[name] = plugin

    def get(self, name: str) -> T | None:
        return self._items.get(name)

    def names(self) -> list[str]:
        return sorted(self._items)


@dataclass
class Plugins:
    importers: Registry[Importer] = field(default_factory=lambda: Registry("importer"))
    renderers: Registry[Renderer] = field(default_factory=lambda: Registry("renderer"))
    runners: Registry[Runner] = field(default_factory=lambda: Registry("runner"))
    connectors: Registry[Connector] = field(default_factory=lambda: Registry("connector"))
