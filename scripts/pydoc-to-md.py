#!/usr/bin/env python3
"""Generate a Markdown API reference for a Python package via runtime introspection.

Imports the package, walks all public modules/classes/functions, extracts
signatures and docstrings, and writes a structured markdown file.

Usage:
    # Full pipeline (auto-detect version)
    python3 scripts/pydoc-to-md.py jax
    python3 scripts/pydoc-to-md.py optax 0.2.4

    # Options
    --output PATH    Override output file path
    --only-index     Compact index (just names, no docstrings)
    --stdout         Write to stdout instead of file
    --depth N        Max sub-module recursion depth (default: 2)
    --include MOD    Only include these sub-modules (repeatable)

If the output file already exists with a curated section above a "# Full API
Reference" separator, that section is preserved and only the API reference
below it is replaced.

Run with the project venv: .venv/bin/python scripts/pydoc-to-md.py jax
"""

import argparse
import importlib
import inspect
import pkgutil
import sys
import warnings
from pathlib import Path
from types import ModuleType


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def get_version(package_name: str, mod: ModuleType) -> str:
    """Get package version from module or importlib.metadata."""
    if hasattr(mod, "__version__"):
        return mod.__version__

    try:
        from importlib.metadata import version
        return version(package_name)
    except Exception:
        return "unknown"


def is_public(name: str) -> bool:
    """Check if a name is public (not starting with _)."""
    return not name.startswith("_")


def get_public_names(mod: ModuleType) -> list[str]:
    """Get public names from a module, respecting __all__."""
    if hasattr(mod, "__all__"):
        return list(mod.__all__)
    return [name for name in dir(mod) if is_public(name)]


def safe_signature(obj) -> str | None:
    """Extract function/method signature, returning None on failure."""
    try:
        sig = inspect.signature(obj)
        return str(sig)
    except (ValueError, TypeError):
        # C extensions, builtins, some descriptors
        pass

    # Fallback: try to extract from docstring (numpy-style)
    doc = inspect.getdoc(obj)
    if doc:
        first_line = doc.split("\n")[0]
        name = getattr(obj, "__name__", "")
        if name and first_line.startswith(f"{name}("):
            # Extract signature from first line: "func(a, b, c=3)"
            return first_line[len(name):]
    return None


def safe_getdoc(obj) -> str:
    """Get docstring safely."""
    try:
        return inspect.getdoc(obj) or ""
    except Exception:
        return ""


def classify_object(obj):
    """Classify an object as class, function, module, or data."""
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj) or inspect.isbuiltin(obj) or callable(obj):
        # callable catches things like jax.jit which are wrapper objects
        if inspect.ismodule(obj):
            return "module"
        return "function"
    if inspect.ismodule(obj):
        return "module"
    return "data"


def is_from_package(obj, package_name: str) -> bool:
    """Check if an object originates from the given package (not re-exported from stdlib/etc)."""
    mod = getattr(obj, "__module__", None)
    if mod is None:
        return True  # Benefit of the doubt
    return mod.startswith(package_name)


# ---------------------------------------------------------------------------
# Module walker
# ---------------------------------------------------------------------------

class PackageWalker:
    """Walk a Python package and collect all public API items."""

    def __init__(self, package_name: str, max_depth: int = 2, include_modules: list[str] | None = None):
        self.package_name = package_name
        self.max_depth = max_depth
        self.include_modules = include_modules
        self.visited: set[int] = set()  # Track by id to avoid cycles
        self.modules: dict[str, ModuleInfo] = {}

    def walk(self, mod: ModuleType):
        """Walk the package tree."""
        self._walk_module(mod, self.package_name, depth=0)

    def _walk_module(self, mod: ModuleType, full_name: str, depth: int):
        if depth > self.max_depth:
            return
        if id(mod) in self.visited:
            return
        self.visited.add(id(mod))

        # Filter by include list if specified
        if self.include_modules:
            parts = full_name.split(".")
            if len(parts) > 1:
                sub = ".".join(parts[1:])
                top_sub = parts[1]
                if top_sub not in self.include_modules and sub not in self.include_modules:
                    return

        info = ModuleInfo(full_name)
        public_names = get_public_names(mod)

        for name in sorted(public_names):
            try:
                obj = getattr(mod, name)
            except Exception:
                continue

            # Skip objects not from this package (re-exports from stdlib, etc.)
            if not is_from_package(obj, self.package_name):
                continue

            kind = classify_object(obj)

            if kind == "class":
                cls_info = self._inspect_class(obj, f"{full_name}.{name}")
                if cls_info:
                    info.classes.append(cls_info)
            elif kind == "function":
                fn_info = self._inspect_function(obj, name)
                if fn_info:
                    info.functions.append(fn_info)
            elif kind == "module":
                # Recurse into submodules
                self._walk_module(obj, f"{full_name}.{name}", depth + 1)
            elif kind == "data":
                info.data.append(DataInfo(name, type(obj).__name__, repr_short(obj)))

        # Also walk subpackages via pkgutil
        if hasattr(mod, "__path__"):
            try:
                for importer, modname, ispkg in pkgutil.iter_modules(mod.__path__, prefix=f"{full_name}."):
                    if not is_public(modname.split(".")[-1]):
                        continue
                    try:
                        submod = importlib.import_module(modname)
                        self._walk_module(submod, modname, depth + 1)
                    except Exception:
                        continue
            except Exception:
                pass

        if info.classes or info.functions or info.data:
            self.modules[full_name] = info

    def _inspect_class(self, cls, full_name: str) -> "ClassInfo | None":
        if id(cls) in self.visited:
            return None
        self.visited.add(id(cls))

        doc = safe_getdoc(cls)
        sig = safe_signature(cls)

        # Collect methods
        methods = []
        for name in sorted(dir(cls)):
            if name.startswith("_") and name != "__init__" and name != "__call__":
                continue

            try:
                obj = getattr(cls, name)
            except Exception:
                continue

            if not (inspect.isfunction(obj) or inspect.ismethod(obj)
                    or isinstance(obj, (classmethod, staticmethod, property))
                    or callable(obj)):
                continue

            # Skip inherited from object/builtins
            if name in ("__init_subclass__", "__subclasshook__", "__class__",
                        "__delattr__", "__dir__", "__format__", "__getattribute__",
                        "__hash__", "__new__", "__reduce__", "__reduce_ex__",
                        "__repr__", "__setattr__", "__sizeof__", "__str__",
                        "__init__"):
                # Include __init__ only if it has a non-trivial signature
                if name == "__init__":
                    init_sig = safe_signature(obj)
                    if init_sig and init_sig != "(self)":
                        methods.append(FunctionInfo(name, init_sig, safe_getdoc(obj), is_method=True))
                continue

            fn_sig = safe_signature(obj)
            fn_doc = safe_getdoc(obj)
            if fn_sig or fn_doc:
                is_prop = isinstance(inspect.getattr_static(cls, name, None), property)
                methods.append(FunctionInfo(
                    name, fn_sig, fn_doc,
                    is_method=True,
                    is_property=is_prop,
                    is_classmethod=isinstance(inspect.getattr_static(cls, name, None), classmethod),
                    is_staticmethod=isinstance(inspect.getattr_static(cls, name, None), staticmethod),
                ))

        # Base classes (skip object)
        bases = [b.__module__ + "." + b.__qualname__ for b in cls.__mro__[1:]
                 if b is not object]

        return ClassInfo(
            name=cls.__name__,
            full_name=full_name,
            doc=doc,
            signature=sig,
            methods=methods,
            bases=bases,
        )

    def _inspect_function(self, func, name: str) -> "FunctionInfo | None":
        sig = safe_signature(func)
        doc = safe_getdoc(func)
        if not sig and not doc:
            return None
        return FunctionInfo(name, sig, doc)


def repr_short(obj, max_len: int = 80) -> str:
    """Short repr of a data object."""
    try:
        r = repr(obj)
        if len(r) > max_len:
            return r[:max_len - 3] + "..."
        return r
    except Exception:
        return f"<{type(obj).__name__}>"


# ---------------------------------------------------------------------------
# Data classes for collected info
# ---------------------------------------------------------------------------

class FunctionInfo:
    def __init__(self, name: str, signature: str | None, doc: str,
                 is_method: bool = False, is_property: bool = False,
                 is_classmethod: bool = False, is_staticmethod: bool = False):
        self.name = name
        self.signature = signature
        self.doc = doc
        self.is_method = is_method
        self.is_property = is_property
        self.is_classmethod = is_classmethod
        self.is_staticmethod = is_staticmethod


class ClassInfo:
    def __init__(self, name: str, full_name: str, doc: str,
                 signature: str | None, methods: list[FunctionInfo],
                 bases: list[str]):
        self.name = name
        self.full_name = full_name
        self.doc = doc
        self.signature = signature
        self.methods = methods
        self.bases = bases


class DataInfo:
    def __init__(self, name: str, type_name: str, value: str):
        self.name = name
        self.type_name = type_name
        self.value = value


class ModuleInfo:
    def __init__(self, name: str):
        self.name = name
        self.classes: list[ClassInfo] = []
        self.functions: list[FunctionInfo] = []
        self.data: list[DataInfo] = []


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def generate_markdown(walker: PackageWalker, package_name: str, version: str,
                      only_index: bool = False) -> str:
    """Generate markdown from collected API info."""
    lines = []
    w = lines.append

    w(f"# {package_name} {version} — Full API Reference\n")
    w(f"> Generated via runtime introspection (`inspect` module)\n")

    if only_index:
        _generate_index(walker, w)
    else:
        _generate_full(walker, w)

    return "\n".join(lines) + "\n"


def _generate_index(walker: PackageWalker, w):
    """Compact index mode."""
    for mod_name in sorted(walker.modules):
        mod_info = walker.modules[mod_name]
        w(f"## `{mod_name}`\n")

        if mod_info.classes:
            w("**Classes:**\n")
            for cls in mod_info.classes:
                brief = first_paragraph(cls.doc)
                w(f"- `{cls.name}` — {brief}")
            w("")

        if mod_info.functions:
            w("**Functions:**\n")
            for fn in mod_info.functions:
                brief = first_paragraph(fn.doc)
                w(f"- `{fn.name}` — {brief}")
            w("")


def _generate_full(walker: PackageWalker, w):
    """Full mode with signatures and docs."""
    for mod_name in sorted(walker.modules):
        mod_info = walker.modules[mod_name]
        w(f"## `{mod_name}`\n")

        # Classes
        for cls in mod_info.classes:
            bases_str = ""
            if cls.bases:
                # Show only first 3 bases, skip internal ones
                visible_bases = [b for b in cls.bases if not b.startswith("builtins.")][:3]
                if visible_bases:
                    bases_str = f"({', '.join(visible_bases)})"

            sig_str = cls.signature or ""
            w(f"### `{cls.name}{sig_str}`\n")
            if bases_str:
                w(f"*Bases: {bases_str}*\n")

            if cls.doc:
                w(cls.doc.strip() + "\n")

            # Methods
            if cls.methods:
                for method in cls.methods:
                    prefix = ""
                    if method.is_property:
                        prefix = "*property* "
                    elif method.is_classmethod:
                        prefix = "*classmethod* "
                    elif method.is_staticmethod:
                        prefix = "*staticmethod* "

                    sig = method.signature or "(…)"
                    if method.is_property:
                        w(f"#### {prefix}`{method.name}`\n")
                    else:
                        w(f"#### {prefix}`{method.name}{sig}`\n")

                    if method.doc:
                        w(method.doc.strip() + "\n")

            w("---\n")

        # Functions
        if mod_info.functions:
            for fn in mod_info.functions:
                sig = fn.signature or "(…)"
                w(f"### `{fn.name}{sig}`\n")
                if fn.doc:
                    w(fn.doc.strip() + "\n")

            w("---\n")

        # Module-level data/constants
        if mod_info.data:
            w("**Constants / Data:**\n")
            for d in mod_info.data:
                w(f"- `{d.name}`: `{d.type_name}` = `{d.value}`")
            w("\n---\n")


def first_paragraph(doc: str) -> str:
    """Extract first paragraph from a docstring."""
    if not doc:
        return ""
    lines = []
    for line in doc.strip().split("\n"):
        if line.strip() == "" and lines:
            break
        lines.append(line.strip())
    text = " ".join(lines)
    if len(text) > 200:
        text = text[:197] + "..."
    return text


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_output(api_markdown: str, output_path: Path):
    """Write the API reference, preserving any existing curated section."""
    SEPARATOR = "# Full API Reference"

    if output_path.exists():
        existing = output_path.read_text()
        sep_idx = existing.find(f"\n{SEPARATOR}")
        if sep_idx == -1:
            sep_idx = existing.find(SEPARATOR)

        if sep_idx != -1:
            curated = existing[:sep_idx].rstrip() + "\n\n"
            api_body = api_markdown.lstrip()
            if api_body.startswith("# "):
                api_body = api_body.split("\n", 1)[1] if "\n" in api_body else ""
            final = curated + SEPARATOR + "\n\n" + api_body
            output_path.write_text(final)
            print(f"  Updated API reference in {output_path} (curated section preserved)", file=sys.stderr)
            return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(api_markdown)
    print(f"  Wrote {output_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_project_root() -> Path:
    """Walk up from cwd to find pyproject.toml or Cargo.lock."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "Cargo.lock").exists() or (parent / "pyproject.toml").exists():
            return parent
    return cwd


def main():
    parser = argparse.ArgumentParser(
        description="Generate Markdown API reference for a Python package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("package", help="Python package name (e.g., jax, optax)")
    parser.add_argument("version", nargs="?", help="Package version (auto-detected if omitted)")
    parser.add_argument("--output", "-o", metavar="PATH", help="Output file path")
    parser.add_argument("--only-index", action="store_true", help="Compact index mode")
    parser.add_argument("--stdout", action="store_true", help="Write to stdout instead of file")
    parser.add_argument("--depth", type=int, default=2, help="Max sub-module recursion depth (default: 2)")
    parser.add_argument("--include", action="append", metavar="MOD",
                        help="Only include these top-level sub-modules (repeatable)")

    args = parser.parse_args()

    # Import the package
    print(f"  Importing {args.package}...", file=sys.stderr)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            mod = importlib.import_module(args.package)
        except ImportError as e:
            sys.exit(f"Error: could not import '{args.package}': {e}\n"
                     f"Make sure you're using the right Python: {sys.executable}")

    version = args.version or get_version(args.package, mod)
    print(f"  {args.package} {version} from {getattr(mod, '__file__', '?')}", file=sys.stderr)

    # Walk the package
    print(f"  Walking public API (depth={args.depth})...", file=sys.stderr)
    walker = PackageWalker(args.package, max_depth=args.depth, include_modules=args.include)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        walker.walk(mod)

    # Stats
    n_modules = len(walker.modules)
    n_classes = sum(len(m.classes) for m in walker.modules.values())
    n_functions = sum(len(m.functions) for m in walker.modules.values())
    print(f"  {n_modules} modules, {n_classes} classes, {n_functions} functions", file=sys.stderr)

    # Generate markdown
    md = generate_markdown(walker, args.package, version, only_index=args.only_index)
    n_lines = md.count("\n")
    print(f"  {n_lines} lines of markdown", file=sys.stderr)

    if args.stdout:
        sys.stdout.write(md)
        return

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        project_root = find_project_root()
        output_path = project_root / "docs" / "vendored" / "python" / f"{args.package}-{version}.md"

    write_output(md, output_path)


if __name__ == "__main__":
    main()
