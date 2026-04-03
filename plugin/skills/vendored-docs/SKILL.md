---
name: vendored-docs
description: Vendor library documentation locally for AI-assisted development. Generates two-tier API references (curated patterns + full API) for Rust crates and Python packages. Always check vendored docs before searching the internet.
triggers:
  - vendor docs
  - vendor docs for
  - document crate
  - document package
  - generate docs for
  - how do I use
  - what's the API for
  - look up crate
  - look up package
  - python docs for
---

# Vendored Docs

## Rule: vendored docs first

**Before searching the internet for any Rust crate or Python package API, always check vendored docs first:**

```bash
ls docs/vendored/rust/{NAME}-*.md docs/vendored/python/{NAME}-*.md 2>/dev/null
```

If a guide exists, read it — it contains curated patterns, project-specific gotchas, and a full API reference with complete signatures and docs.

Only reach for the internet if no vendored guide exists or it doesn't cover the specific API you need.

---

## Generating docs

The scripts are bundled with this plugin — no need to copy them into your project.

### Rust crates

```bash
# Full pipeline: resolve version from Cargo.lock, generate rustdoc JSON, convert
python3 ${CLAUDE_SKILL_DIR}/scripts/rustdoc-json-to-md.py {CRATE_NAME}

# Explicit version
python3 ${CLAUDE_SKILL_DIR}/scripts/rustdoc-json-to-md.py {CRATE_NAME} {VERSION}

# Reuse existing JSON (faster re-runs)
python3 ${CLAUDE_SKILL_DIR}/scripts/rustdoc-json-to-md.py {CRATE_NAME} --skip-build

# Convert existing JSON file directly
python3 ${CLAUDE_SKILL_DIR}/scripts/rustdoc-json-to-md.py --json target/doc/{CRATE}.json

# Compact index or stdout
python3 ${CLAUDE_SKILL_DIR}/scripts/rustdoc-json-to-md.py {CRATE} --only-index --stdout
```

Requires nightly toolchain: `rustup toolchain install nightly` (won't change your default).

### Python packages

```bash
# Must use a Python env where the package is installed
python3 ${CLAUDE_SKILL_DIR}/scripts/pydoc-to-md.py {PACKAGE}

# Explicit version
python3 ${CLAUDE_SKILL_DIR}/scripts/pydoc-to-md.py {PACKAGE} {VERSION}

# Control depth and scope
python3 ${CLAUDE_SKILL_DIR}/scripts/pydoc-to-md.py {PACKAGE} --depth 1
python3 ${CLAUDE_SKILL_DIR}/scripts/pydoc-to-md.py {PACKAGE} --include numpy --include random

# Compact index or stdout
python3 ${CLAUDE_SKILL_DIR}/scripts/pydoc-to-md.py {PACKAGE} --only-index --stdout
```

Both scripts use `-o PATH` to override the output path. Defaults: `docs/vendored/rust/{name}-{version}.md` (Rust) and `docs/vendored/python/{name}-{version}.md` (Python).

---

## Adding curated content

The scripts generate the full API reference. To add curated content (patterns, gotchas), edit the file and add sections **above** the `# Full API Reference` separator. Re-running the script preserves the curated section.

### Curated section structure

```markdown
## Common Patterns
[5-10 working code snippets from tests/codebase, 5-15 lines each]

## Gotchas
- **Problem:** ...
- **Why:** ...
- **Fix:** ...

## Config Options
| Option | Type | Default | Description |

## Compatibility Notes
[versions, known incompatibilities]

---

# Full API Reference
{machine-generated — do not edit below this line}
```

### Where to find patterns and gotchas

**Rust:**
- Your codebase: `use {CRATE_NAME}` in `crates/` or `src/`
- Crate source: `~/.cargo/registry/src/*/{CRATE}-{VERSION}/tests/`
- Comments: `NOTE`, `HACK`, `WARNING`, `FIXME`, `TODO`, `#[deprecated]`

**Python:**
- Your codebase: `import {PACKAGE}` or `from {PACKAGE} import`
- Package tests: `{site-packages}/{PACKAGE}/tests/`
- Docstring warnings and deprecation notices

### Quality rules

1. Code snippets must come from working code — never guessed
2. The API reference section is machine-generated — re-run the script to update it
3. If unsure about a signature, read the source — do not guess