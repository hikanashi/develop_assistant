from __future__ import annotations

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
ENVIRONMENT_SPEC = REPOSITORY_DIR / "design" / "requiments" / "enviroment.md"
SEED_DIR = BACKEND_DIR / "seed"


def configured_path(key: str) -> Path:
    if not ENVIRONMENT_SPEC.is_file():
        raise FileNotFoundError(
            f"Cannot read {key}: environment specification not found at {ENVIRONMENT_SPEC}"
        )
    pattern = rf"^\| `{re.escape(key)}` \| `([^`]+)` \|"
    content = ENVIRONMENT_SPEC.read_text(encoding="utf-8")
    match = re.search(pattern, content, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"Setting {key} is missing from {ENVIRONMENT_SPEC}")
    configured = Path(match.group(1))
    if key == "LOCALDATA_DIR":
        return BACKEND_DIR / configured.relative_to("backend")
    return REPOSITORY_DIR / configured


LOCALDATA_DIR = configured_path("LOCALDATA_DIR")
