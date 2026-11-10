"""Renderer port implementations (RFC 0003 section 5). Renders are disposable views."""

from opengrc.renderer.oscal import OscalRenderer
from opengrc.renderer.ssp import SspRenderer

__all__ = ["OscalRenderer", "SspRenderer"]
