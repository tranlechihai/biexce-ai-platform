"""Errors raised by Plan/Build configuration services."""

from ..autopilot import ControlPlaneError


class BasicConfigError(ControlPlaneError, ValueError):
    """Raised when a Plan/Build configuration is invalid or unsafe."""
