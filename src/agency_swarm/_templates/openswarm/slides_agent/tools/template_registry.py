"""Per-project template registry utilities for slides_agent_v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE_DIRNAME = "_templates"
TEMPLATE_INDEX_FILENAME = "index.json"


def _templates_dir(project_dir: Path) -> Path:
    return project_dir / TEMPLATE_DIRNAME


def _template_index_path(project_dir: Path) -> Path:
    return _templates_dir(project_dir) / TEMPLATE_INDEX_FILENAME


def ensure_template_dir(project_dir: Path) -> Path:
    path = _templates_dir(project_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_template_index(project_dir: Path) -> dict[str, dict[str, Any]]:
    path = _template_index_path(project_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    clean: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            clean[key] = value
    return clean


def save_template_index(project_dir: Path, index_data: dict[str, dict[str, Any]]) -> None:
    ensure_template_dir(project_dir)
    _template_index_path(project_dir).write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def template_path(project_dir: Path, template_key: str) -> Path:
    ensure_template_dir(project_dir)
    return _templates_dir(project_dir) / f"{template_key}.html"

