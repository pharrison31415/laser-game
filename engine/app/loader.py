from __future__ import annotations
import importlib.util
from pathlib import Path
import yaml
from typing import Tuple, Dict, Any


def load_game_manifest(game_root: Path) -> Dict[str, Any]:
    manifest = game_root / "manifest.yaml"
    if not manifest.exists():
        raise FileNotFoundError(f"Missing manifest.yaml in {game_root}")
    with open(manifest, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_game_module(game_root: Path):
    """
    Loads games/<id>/main.py module and returns the module object.
    The file must define a get_game() -> Game factory.
    """
    main_py = game_root / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(f"Missing main.py in {game_root}")
    spec = importlib.util.spec_from_file_location(f"games.{game_root.name}.main", main_py)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    if not hasattr(module, "get_game"):
        raise AttributeError("Game module must define get_game()")
    return module
