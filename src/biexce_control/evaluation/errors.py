"""Errors raised by the BIEXCE evaluation services."""

from ..autopilot import ControlPlaneError


class EvaluationError(ControlPlaneError, ValueError):
    """Raised when evaluation evidence is missing or malformed."""
