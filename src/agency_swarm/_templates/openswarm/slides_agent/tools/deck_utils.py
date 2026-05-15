"""Utilities for slides_agent test deck."""

from pathlib import Path
import shutil

from .slide_file_utils import get_project_dir


def test_deck_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "test_deck"


def test_project_dir(project_name: str) -> Path:
    return get_project_dir(project_name)


def load_theme_css() -> str:
    return (test_deck_dir() / "_theme.css").read_text(encoding="utf-8")


def load_slide_body(slide_name: str) -> str:
    return (test_deck_dir() / f"{slide_name}.html").read_text(encoding="utf-8")


def ensure_assets(project_name: str) -> None:
    assets_src = test_deck_dir() / "assets"
    assets_dst = test_project_dir(project_name) / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)
    for asset in assets_src.iterdir():
        if asset.is_file():
            shutil.copy2(asset, assets_dst / asset.name)
