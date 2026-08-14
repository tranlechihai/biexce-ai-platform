"""Public API for deterministic BIEXCE OpenCode + Slim config generation."""

from .builder import build_config, build_prototype, validate_output_path
from .catalog import ROLE_ORDER, SLIM_IDS
from .config import load_routing
from .errors import PrototypeError, SlimConfigError

__all__ = [
    "PrototypeError",
    "SlimConfigError",
    "ROLE_ORDER",
    "SLIM_IDS",
    "build_config",
    "build_prototype",
    "load_routing",
    "validate_output_path",
]
