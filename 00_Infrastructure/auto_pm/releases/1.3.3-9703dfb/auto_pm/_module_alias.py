"""Make the short import paths (``auto_pm.core.x``) resolve to the same module object as the layered ones.

``auto_pm/__init__.py`` appends ``domain``, ``infrastructure``, ``application`` and ``ui`` to the package ``__path__``,
so ``auto_pm.core.project_service`` and ``auto_pm.application.core.project_service`` are both importable.  Python then
loads the file twice under two names: two module objects, two copies of every class and module-level variable, so a
``monkeypatch`` on one path never reaches code that imported through the other (TD-SW008-056).

This finder runs first, notices that a module imported by a short name lives under a layer directory, and hands back
the module already registered under its layered name.  The layered path stays the canonical one; the short path is a
compatibility alias only.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import os
import sys
from collections.abc import Sequence
from types import ModuleType

ROOT = "auto_pm"


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, canonical: str) -> None:
        self._canonical = canonical
        self._real_spec: importlib.machinery.ModuleSpec | None = None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        module = importlib.import_module(self._canonical)
        self._real_spec = module.__spec__
        return module

    def exec_module(self, module: ModuleType) -> None:
        """The canonical module is already executed; only undo what the import machinery just did to it.

        ``module_from_spec`` assigns the alias spec to ``__spec__`` unconditionally; left alone, the module would claim
        the short name, and relative imports inside it would warn ``__package__ != __spec__.parent``.
        """
        if self._real_spec is not None:
            module.__spec__ = self._real_spec


class LayerAliasFinder(importlib.abc.MetaPathFinder):
    def __init__(self, package_dir: str) -> None:
        self._package_dir = os.path.realpath(package_dir)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith(ROOT + ".") or path is None:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, list(path))
        if spec is None:
            return None
        canonical = self._canonical_name(spec)
        if canonical is None or canonical == fullname:
            return None
        return importlib.machinery.ModuleSpec(fullname, _AliasLoader(canonical))

    def _canonical_name(self, spec: importlib.machinery.ModuleSpec) -> str | None:
        """The dotted name the file location implies, or None for a namespace part or a file outside the package."""
        if spec.origin and spec.origin not in ("namespace", "built-in", "frozen"):
            location = os.path.realpath(spec.origin)
            if os.path.basename(location) == "__init__.py":
                location = os.path.dirname(location)
            else:
                location, _ext = os.path.splitext(location)
        else:
            return None
        relative = os.path.relpath(location, self._package_dir)
        if relative.startswith(os.pardir):
            return None
        return ".".join([ROOT, *relative.split(os.sep)])


def install(package_dir: str) -> None:
    """Idempotent: one finder per package directory, ahead of the default path finder."""
    real = os.path.realpath(package_dir)
    if not any(isinstance(f, LayerAliasFinder) and f._package_dir == real for f in sys.meta_path):
        sys.meta_path.insert(0, LayerAliasFinder(real))
