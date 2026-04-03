# docvault

Vendor library documentation locally for AI-assisted development. Converts Rust crates (via rustdoc JSON) and Python packages (via runtime introspection) into structured Markdown API references. Zero external dependencies.

## Why

LLMs hallucinate API signatures. Vendored docs don't. By keeping accurate, machine-generated API references in your repo, your AI assistant reads real signatures and real docstrings instead of guessing.

Each guide has two tiers:
- **Top**: Curated patterns, gotchas, and project-specific usage (written by you or your AI)
- **Bottom**: Full API reference, machine-generated from the source of truth

## Install

Add the marketplace and install the plugin from within Claude Code:

```
/plugin marketplace add zeapo/docvault
/plugin install vendored-docs@docvault
```

This gives Claude the skill to generate, find, and use vendored docs automatically. You can install at user scope (default, works across all your projects) or project scope (`--scope project`, shared with collaborators).

After installing, run `/reload-plugins` if you're in an active session.

### Prompting tips

The plugin triggers automatically on phrases like "vendor docs for", "how do I use", or "what's the API for". But you can also be direct:

```
vendor docs for tokio
document the jax package
look up crate serde
```

Once docs exist in your repo, Claude checks them before reaching for the internet. You don't need to tell it to — the skill handles that. If you want to add curated patterns on top of a generated reference, just ask:

```
add common patterns to the tokio docs
add gotchas to the jax guide
```

## Quick Start (manual)

If you prefer to run the scripts directly without the plugin, they live in `plugin/skills/vendored-docs/scripts/`:

### Rust crates

```bash
python3 path/to/rustdoc-json-to-md.py datafusion
python3 path/to/rustdoc-json-to-md.py iceberg-datafusion 0.9.0
```

Requires `rustup toolchain install nightly` (stable stays your default).

### Python packages

```bash
python3 path/to/pydoc-to-md.py jax
python3 path/to/pydoc-to-md.py optax --depth 1
python3 path/to/pydoc-to-md.py jax --include numpy --include random
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
rustdoc-json-to-md.py CRATE [VERSION]   Full pipeline
rustdoc-json-to-md.py CRATE --skip-build Reuse existing JSON
rustdoc-json-to-md.py --json FILE        Convert existing JSON
rustdoc-json-to-md.py CRATE --only-index Compact index
rustdoc-json-to-md.py CRATE --stdout     Write to stdout
rustdoc-json-to-md.py CRATE -o PATH      Custom output path
```

### `pydoc-to-md.py`

```
pydoc-to-md.py PKG [VERSION]        Full pipeline
pydoc-to-md.py PKG --depth N         Sub-module depth (default: 2)
pydoc-to-md.py PKG --include MOD     Only specific sub-modules
pydoc-to-md.py PKG --only-index      Compact index
pydoc-to-md.py PKG --stdout          Write to stdout
pydoc-to-md.py PKG -o PATH           Custom output path
```

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
