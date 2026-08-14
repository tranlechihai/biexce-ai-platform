"""Slim configuration errors."""

from ..autopilot import ControlPlaneError


class SlimConfigError(ControlPlaneError, ValueError):
    """Raised when generated Slim input or output is unsafe or invalid."""


# Compatibility name for the isolated Step 1 facade and tests.
PrototypeError = SlimConfigError
