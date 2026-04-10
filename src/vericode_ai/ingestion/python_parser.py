import importlib
import inspect
import sys
import pkgutil
import warnings
from typing import List, Optional
from types import ModuleType

from vericode_ai.schema.doc_chunk import DocChunk


class PythonIngestor:
    """
    Ingests a Python package via runtime introspection and returns a structured
    list of DocChunk objects ready for vector embedding and retrieval.
    """
    
    def __init__(self, package_name: str, max_depth: int = 2):
        self.package_name = package_name
        self.max_depth = max_depth
        self.visited = set()
        self.chunks: List[DocChunk] = []

    def ingest(self) -> List[DocChunk]:
        """Loads the package and extracts all public API surface as DocChunks."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                mod = importlib.import_module(self.package_name)
            except ImportError as e:
                # Fallback to empty if not installed
                print(f"Failed to import {self.package_name}: {e}")
                return []

        self._walk_module(mod, self.package_name, depth=0)
        return self.chunks

    def _walk_module(self, mod: ModuleType, full_name: str, depth: int):
        if depth > self.max_depth:
            return
        if id(mod) in self.visited:
            return
        self.visited.add(id(mod))

        # Register the module chunk itself
        mod_doc = self._safe_getdoc(mod)
        if mod_doc:
            self.chunks.append(DocChunk(
                id=f"{full_name}_module",
                content=mod_doc,
                source=self.package_name,
                symbol=full_name,
                symbol_type="module",
                signature=None
            ))

        public_names = self._get_public_names(mod)
        
        for name in public_names:
            try:
                obj = getattr(mod, name)
            except Exception:
                continue

            if not self._is_from_package(obj, self.package_name):
                continue
                
            kind = self._classify_object(obj)
            symbol_name = f"{full_name}.{name}"

            if kind == "class":
                self._inspect_class(obj, symbol_name)
            elif kind == "function":
                self._inspect_function(obj, symbol_name)
            elif kind == "module":
                self._walk_module(obj, symbol_name, depth + 1)

        # Walk subpackages
        if hasattr(mod, "__path__"):
            try:
                for importer, modname, ispkg in pkgutil.iter_modules(mod.__path__, prefix=f"{full_name}."):
                    if not modname.split(".")[-1].startswith("_"):
                        try:
                            submod = importlib.import_module(modname)
                            self._walk_module(submod, modname, depth + 1)
                        except Exception:
                            continue
            except Exception:
                pass

    def _inspect_class(self, cls, full_name: str):
        if id(cls) in self.visited:
            return
        self.visited.add(id(cls))

        doc = self._safe_getdoc(cls)
        sig = self._safe_signature(cls)

        if doc or sig:
            self.chunks.append(DocChunk(
                id=f"{full_name}_class",
                content=doc,
                source=self.package_name,
                symbol=full_name,
                symbol_type="class",
                signature=sig
            ))

        # Collect methods
        for name in sorted(dir(cls)):
            if name.startswith("_") and name not in ("__init__",):
                continue
            try:
                obj = getattr(cls, name)
            except Exception:
                continue
                
            if not callable(obj) and not isinstance(obj, property):
                continue

            method_sig = self._safe_signature(obj)
            method_doc = self._safe_getdoc(obj)
            
            if method_doc or method_sig:
                symbol_type = "property" if isinstance(obj, property) else "method"
                self.chunks.append(DocChunk(
                    id=f"{full_name}.{name}_{symbol_type}",
                    content=method_doc,
                    source=self.package_name,
                    symbol=f"{full_name}.{name}",
                    symbol_type=symbol_type,
                    signature=method_sig
                ))

    def _inspect_function(self, func, full_name: str):
        sig = self._safe_signature(func)
        doc = self._safe_getdoc(func)
        if sig or doc:
            self.chunks.append(DocChunk(
                id=f"{full_name}_function",
                content=doc,
                source=self.package_name,
                symbol=full_name,
                symbol_type="function",
                signature=sig
            ))

    # Helper methods
    def _get_public_names(self, mod: ModuleType) -> list:
        if hasattr(mod, "__all__"):
            return list(mod.__all__)
        return [n for n in dir(mod) if not n.startswith("_")]

    def _classify_object(self, obj) -> str:
        if inspect.isclass(obj): return "class"
        if inspect.isfunction(obj) or inspect.isbuiltin(obj) or callable(obj):
            if inspect.ismodule(obj): return "module"
            return "function"
        if inspect.ismodule(obj): return "module"
        return "data"

    def _is_from_package(self, obj, package_name: str) -> bool:
        mod = getattr(obj, "__module__", None)
        if not mod: return True
        return mod.startswith(package_name)

    def _safe_signature(self, obj) -> Optional[str]:
        try:
            return str(inspect.signature(obj))
        except Exception:
            return None

    def _safe_getdoc(self, obj) -> str:
        try:
            return inspect.getdoc(obj) or ""
        except Exception:
            return ""
