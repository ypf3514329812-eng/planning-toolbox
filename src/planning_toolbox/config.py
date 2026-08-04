from pathlib import Path
import yaml
from typing import Any, Dict

def _find_config_dir() -> Path:
    """
    Locate the config directory. Searches upward from the package location
    to find a 'config' directory containing 'default.yaml'.
    Falls back to a path relative to the source tree.
    """
    # Start from the package directory and walk up looking for config/
    current = Path(__file__).resolve().parent
    for _ in range(5):  # Walk up at most 5 levels
        candidate = current / "config" / "default.yaml"
        if candidate.exists():
            return current / "config"
        current = current.parent
    # Final fallback: relative to CWD
    return Path("config")

DEFAULT_CONFIG_DIR = _find_config_dir()

def load_config(config_path: Path | str | None = None) -> Dict[str, Any]:
    """Load YAML configuration from the given path or the default config file."""
    if config_path:
        path = Path(config_path)
    else:
        path = DEFAULT_CONFIG_DIR / "default.yaml"
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
