# docvault

Vendor library documentation locally for AI-assisted development. Converts Rust crates (via rustdoc JSON) and Python packages (via runtime introspection) into structured Markdown API references. Zero external dependencies.

## Why

LLMs hallucinate API signatures. Vendored docs don't. By keeping accurate, machine-generated API references in your repo, your AI assistant reads real signatures and real docstrings instead of guessing.

Each guide has two tiers:
- **Top**: Curated patterns, gotchas, and project-specific usage (written by you or your AI)
- **Bottom**: Full API reference, machine-generated from the source of truth

## Quick Start

### Rust crates

```bash
# Copy scripts to your project
cp scripts/rustdoc-json-to-md.py /path/to/your/project/scripts/

# Generate docs (resolves version from Cargo.lock, runs cargo rustdoc, converts)
python3 scripts/rustdoc-json-to-md.py datafusion
python3 scripts/rustdoc-json-to-md.py iceberg-datafusion 0.9.0
```

Requires `rustup toolchain install nightly` (stable stays your default).

### Python packages

```bash
# Copy scripts to your project
cp scripts/pydoc-to-md.py /path/to/your/project/scripts/

# Generate docs (imports package, walks API via inspect)
python3 scripts/pydoc-to-md.py jax
python3 scripts/pydoc-to-md.py optax --depth 1
python3 scripts/pydoc-to-md.py jax --include numpy --include random
```

Must run with a Python environment where the package is installed.

## Output

Guides are written to `docs/vendored/{lang}/{name}-{version}.md` — Rust crates go to `docs/vendored/rust/` and Python packages to `docs/vendored/python/`. This avoids name collisions between packages in different languages. Re-running the script updates the API reference while preserving any curated content you've added above the `# Full API Reference` separator.

### Example output structure

```
docs/vendored/
  rust/
    datafusion-52.4.0.md      # 6,000+ lines — full Rust API + curated patterns
    iceberg-datafusion-0.9.0.md
  python/
    jax-0.9.2.md              # 48,000+ lines — full Python API
    optax-0.2.7.md
```

## CLI Reference

### `rustdoc-json-to-md.py`

```
python3 scripts/rustdoc-json-to-md.py CRATE [VERSION]   Full pipeline
python3 scripts/rustdoc-json-to-md.py CRATE --skip-build Reuse existing JSON
python3 scripts/rustdoc-json-to-md.py --json FILE        Convert existing JSON
python3 scripts/rustdoc-json-to-md.py CRATE --only-index Compact index
python3 scripts/rustdoc-json-to-md.py CRATE --stdout     Write to stdout
python3 scripts/rustdoc-json-to-md.py CRATE -o PATH      Custom output path
```

### `pydoc-to-md.py`

```
python3 scripts/pydoc-to-md.py PKG [VERSION]        Full pipeline
python3 scripts/pydoc-to-md.py PKG --depth N         Sub-module depth (default: 2)
python3 scripts/pydoc-to-md.py PKG --include MOD     Only specific sub-modules
python3 scripts/pydoc-to-md.py PKG --only-index      Compact index
python3 scripts/pydoc-to-md.py PKG --stdout          Write to stdout
python3 scripts/pydoc-to-md.py PKG -o PATH           Custom output path
```

## Claude Code Skill

Copy `.claude/skills/vendored-docs.md` to your project's `.claude/skills/` directory. This teaches Claude to:
1. **Check vendored docs before the internet** when looking up any API
2. **Generate new guides** when asked ("vendor docs for X")
3. **Add curated content** (patterns, gotchas) on top of the machine-generated reference

## How It Works

### Rust

1. Runs `cargo +nightly rustdoc` to generate **rustdoc JSON** — a structured representation of every public type, method, trait, and doc comment
2. A Python script converts the JSON to clean Markdown, rendering type signatures back to Rust syntax
3. Output includes full method docs with inline examples (from `///` doc comments)

### Python

1. **Imports** the package and walks it via `inspect.getmembers()`
2. Extracts signatures via `inspect.signature()` (falls back to docstring parsing for C extensions)
3. Collects complete docstrings including Args/Returns/Examples sections

Both scripts use only Python stdlib — zero external dependencies.

## License

MIT
