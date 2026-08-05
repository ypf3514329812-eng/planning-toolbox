from pathlib import Path
import yaml
from typing import Any, Dict

def _find_config_dir() -> Path:
    """
    Locate the config directory. Searches upward from the current directory,
    falling back to package-internal config directory.
    """
    # 1. Search upward from package location
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "config" / "default.yaml"
        if candidate.exists():
            return current / "config"
        current = current.parent

    # 2. Package embedded fallback (installed mode)
    package_config = Path(__file__).resolve().parent / "config"
    if (package_config / "default.yaml").exists():
        return package_config

    # 3. Final fallback: relative to CWD
    return Path("config")

DEFAULT_CONFIG_DIR = _find_config_dir()

def load_config(config_path: Path | str | None = None) -> Dict[str, Any]:
    """Load YAML configuration from the given path or the default config file."""
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
    else:
        path = DEFAULT_CONFIG_DIR / "default.yaml"
        if not path.exists():
            package_fallback = Path(__file__).resolve().parent / "config" / "default.yaml"
            if package_fallback.exists():
                path = package_fallback
            else:
                raise FileNotFoundError(f"Configuration file not found: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
