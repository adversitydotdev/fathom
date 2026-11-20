"""Renderer port implementations (RFC 0003 section 5). Renders are disposable views."""

from ogrl.renderer.oscal import OscalRenderer
from ogrl.renderer.ssp import SspRenderer

__all__ = ["OscalRenderer", "SspRenderer"]
