from __future__ import annotations

from importlib.machinery import SourceFileLoader
import types

from tests.paths import REPO_ROOT


def load_script_module(name: str) -> types.ModuleType:
    path = REPO_ROOT / "scripts" / f"{name}.py"
    loader = SourceFileLoader(name, str(path))
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__loader__ = loader
    loader.exec_module(module)
    return module
