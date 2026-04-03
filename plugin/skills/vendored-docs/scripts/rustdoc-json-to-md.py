#!/usr/bin/env python3
"""Generate a Markdown API reference for a Rust crate from rustdoc JSON.

Handles the full pipeline: resolve version, run cargo rustdoc, convert JSON to
markdown, and write to docs/vendored/rust/.

Usage:
    # Full pipeline (resolve version from Cargo.lock, generate JSON, convert)
    python3 scripts/rustdoc-json-to-md.py datafusion
    python3 scripts/rustdoc-json-to-md.py datafusion 52.4.0

    # Just convert an existing JSON file
    python3 scripts/rustdoc-json-to-md.py --json target/doc/datafusion.json

    # Options
    --output PATH    Override output file path
    --only-index     Compact index (just type names, no method docs)
    --skip-build     Reuse existing JSON, skip cargo rustdoc
    --stdout         Write to stdout instead of file

If the output file already exists with a curated section above a "# Full API
Reference" separator, that section is preserved and only the API reference
below it is replaced.

Requires: nightly toolchain (rustup toolchain install nightly)
"""

import json
import os
import re
import subprocess
import sys
import argparse
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Type rendering
# ---------------------------------------------------------------------------

def render_type(ty, index, paths):
    """Render a rustdoc JSON type to Rust syntax."""
    if ty is None:
        return "()"
    if isinstance(ty, str):
        return ty

    if "resolved_path" in ty:
        rp = ty["resolved_path"]
        name = rp["path"]
        args = render_generic_args(rp.get("args"), index, paths)
        return f"{name}{args}"

    if "generic" in ty:
        return ty["generic"]

    if "primitive" in ty:
        return ty["primitive"]

    if "borrowed_ref" in ty:
        br = ty["borrowed_ref"]
        lt = f"'{br['lifetime']} " if br.get("lifetime") else ""
        mut = "mut " if br.get("is_mutable") else ""
        inner = render_type(br["type"], index, paths)
        return f"&{lt}{mut}{inner}"

    if "tuple" in ty:
        items = [render_type(t, index, paths) for t in ty["tuple"]]
        return f"({', '.join(items)})"

    if "slice" in ty:
        inner = render_type(ty["slice"], index, paths)
        return f"[{inner}]"

    if "array" in ty:
        inner = render_type(ty["array"]["type"], index, paths)
        length = ty["array"]["len"]
        return f"[{inner}; {length}]"

    if "dyn_trait" in ty:
        dt = ty["dyn_trait"]
        traits = [render_trait_bound(tb, index, paths) for tb in dt["traits"]]
        lt = f" + '{dt['lifetime']}" if dt.get("lifetime") else ""
        return f"dyn {' + '.join(traits)}{lt}"

    if "impl_trait" in ty:
        bounds = [render_generic_bound(b, index, paths) for b in ty["impl_trait"]]
        return f"impl {' + '.join(bounds)}"

    if "qualified_path" in ty:
        qp = ty["qualified_path"]
        self_ty = render_type(qp["self_type"], index, paths)
        trait_path = render_type(qp["trait"], index, paths) if qp.get("trait") else ""
        name = qp["name"]
        args = render_generic_args(qp.get("args"), index, paths)
        if trait_path:
            return f"<{self_ty} as {trait_path}>::{name}{args}"
        return f"{self_ty}::{name}{args}"

    if "raw_pointer" in ty:
        rp = ty["raw_pointer"]
        mut = "mut" if rp.get("is_mutable") else "const"
        inner = render_type(rp["type"], index, paths)
        return f"*{mut} {inner}"

    if "function_pointer" in ty:
        fp = ty["function_pointer"]
        sig = fp.get("sig", fp) if "sig" in fp else fp
        inputs = ", ".join(render_type(inp, index, paths) for inp in sig.get("inputs", []))
        output = render_type(sig.get("output"), index, paths)
        ret = f" -> {output}" if output and output != "()" else ""
        return f"fn({inputs}){ret}"

    if "infer" in ty:
        return "_"

    if "pat" in ty:
        p = ty["pat"]
        inner = render_type(p.get("type"), index, paths)
        return f"{inner}"

    # Fallback
    return f"/* unknown type: {list(ty.keys())} */"


def render_generic_args(args, index, paths):
    """Render generic arguments like <T, U>."""
    if args is None:
        return ""

    if "angle_bracketed" in args:
        ab = args["angle_bracketed"]
        parts = []
        for arg in ab.get("args", []):
            if "type" in arg:
                parts.append(render_type(arg["type"], index, paths))
            elif "lifetime" in arg:
                parts.append(f"'{arg['lifetime']}")
            elif "const" in arg:
                parts.append(str(arg["const"]))
        for constraint in ab.get("constraints", []):
            name = constraint.get("name", "")
            bounds = [render_generic_bound(b, index, paths) for b in constraint.get("bounds", [])]
            if bounds:
                parts.append(f"{name}: {' + '.join(bounds)}")
        if parts:
            return f"<{', '.join(parts)}>"
        return ""

    if "parenthesized" in args:
        pa = args["parenthesized"]
        inputs = [render_type(t, index, paths) for t in pa.get("inputs", [])]
        output = render_type(pa.get("output"), index, paths)
        ret = f" -> {output}" if output and output != "()" else ""
        return f"({', '.join(inputs)}){ret}"

    return ""


def render_trait_bound(tb, index, paths):
    """Render a trait bound from dyn_trait."""
    trait_ty = tb.get("trait", {})
    path = trait_ty.get("path", "")
    args = render_generic_args(trait_ty.get("args"), index, paths)
    return f"{path}{args}"


def render_generic_bound(bound, index, paths):
    """Render a generic bound (trait bound or lifetime)."""
    if "trait_bound" in bound:
        tb = bound["trait_bound"]
        trait_info = tb.get("trait", {})
        path = trait_info.get("path", "")
        args = render_generic_args(trait_info.get("args"), index, paths)
        return f"{path}{args}"
    if "lifetime" in bound:
        return f"'{bound['lifetime']}"
    if "use" in bound:
        return "use<..>"
    return str(bound)


def render_generics(generics, index, paths):
    """Render generic parameters like <T: Clone, U>."""
    params = generics.get("params", [])
    if not params:
        return ""

    parts = []
    for p in params:
        name = p.get("name", "")
        kind = p.get("kind", {})
        if "type" in kind:
            bounds = kind["type"].get("bounds", [])
            bound_strs = [render_generic_bound(b, index, paths) for b in bounds]
            if bound_strs:
                parts.append(f"{name}: {' + '.join(bound_strs)}")
            else:
                parts.append(name)
        elif "lifetime" in kind:
            parts.append(f"'{name}")
        elif "const" in kind:
            ty = render_type(kind["const"].get("type"), index, paths)
            parts.append(f"const {name}: {ty}")
        else:
            parts.append(name)

    return f"<{', '.join(parts)}>" if parts else ""


def render_where_clause(generics, index, paths):
    """Render where clause from generics where_predicates."""
    preds = generics.get("where_predicates", [])
    if not preds:
        return ""

    parts = []
    for pred in preds:
        if "bound_predicate" in pred:
            bp = pred["bound_predicate"]
            ty = render_type(bp.get("type"), index, paths)
            bounds = [render_generic_bound(b, index, paths) for b in bp.get("bounds", [])]
            parts.append(f"{ty}: {' + '.join(bounds)}")
        elif "lifetime_predicate" in pred:
            lp = pred["lifetime_predicate"]
            lt = f"'{lp['lifetime']}"
            outlives = [f"'{o}" for o in lp.get("outlives", [])]
            parts.append(f"{lt}: {' + '.join(outlives)}")

    if parts:
        return f"\nwhere\n    " + ",\n    ".join(parts)
    return ""


def render_fn_sig(name, fn_data, index, paths):
    """Render a full function signature."""
    header = fn_data.get("header", {})
    sig = fn_data.get("sig", {})
    generics = fn_data.get("generics", {})

    async_kw = "async " if header.get("is_async") else ""
    unsafe_kw = "unsafe " if header.get("is_unsafe") else ""
    const_kw = "const " if header.get("is_const") else ""

    gen_str = render_generics(generics, index, paths)

    # Render inputs
    input_strs = []
    for param_name, param_type in sig.get("inputs", []):
        if param_name == "self":
            ty_str = render_type(param_type, index, paths)
            if ty_str == "&Self":
                input_strs.append("&self")
            elif ty_str == "&mut Self":
                input_strs.append("&mut self")
            elif ty_str == "Self":
                input_strs.append("self")
            else:
                input_strs.append(f"self: {ty_str}")
        else:
            ty_str = render_type(param_type, index, paths)
            input_strs.append(f"{param_name}: {ty_str}")

    params = ", ".join(input_strs)

    # Render output
    output = sig.get("output")
    ret_str = ""
    if output:
        rendered = render_type(output, index, paths)
        if rendered and rendered != "()":
            ret_str = f" -> {rendered}"

    where_str = render_where_clause(generics, index, paths)

    return f"pub {const_kw}{async_kw}{unsafe_kw}fn {name}{gen_str}({params}){ret_str}{where_str}"


def first_paragraph(docs):
    """Extract first paragraph from docs."""
    if not docs:
        return ""
    lines = []
    for line in docs.strip().split("\n"):
        if line.strip() == "" and lines:
            break
        lines.append(line)
    text = " ".join(l.strip() for l in lines)
    if len(text) > 200:
        text = text[:197] + "..."
    return text


# ---------------------------------------------------------------------------
# Pipeline: version resolution, cargo rustdoc, JSON discovery
# ---------------------------------------------------------------------------

def resolve_version(crate_name: str, project_root: Path) -> str:
    """Look up crate version from Cargo.lock."""
    lockfile = project_root / "Cargo.lock"
    if not lockfile.exists():
        sys.exit(f"Error: {lockfile} not found. Run from the project root.")

    text = lockfile.read_text()
    # Cargo.lock format: [[package]]\nname = "..."\nversion = "..."
    pattern = rf'name = "{re.escape(crate_name)}"\nversion = "([^"]+)"'
    matches = re.findall(pattern, text)

    if not matches:
        sys.exit(f"Error: crate '{crate_name}' not found in Cargo.lock")
    if len(matches) > 1:
        versions = ", ".join(matches)
        sys.exit(f"Error: multiple versions of '{crate_name}' in Cargo.lock: {versions}\n"
                 f"Specify one explicitly: python3 {sys.argv[0]} {crate_name} VERSION")
    return matches[0]


def run_cargo_rustdoc(crate_name: str, project_root: Path) -> Path:
    """Run cargo +nightly rustdoc and return the path to the JSON file."""
    print(f"  Generating rustdoc JSON for {crate_name}...", file=sys.stderr)

    result = subprocess.run(
        ["cargo", "+nightly", "rustdoc", "-p", crate_name, "--lib",
         "--", "-Z", "unstable-options", "--output-format", "json"],
        cwd=project_root,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "no such command: `+nightly`" in stderr or "toolchain 'nightly'" in stderr:
            sys.exit("Error: nightly toolchain not installed.\n"
                     "Install with: rustup toolchain install nightly")
        sys.exit(f"Error: cargo rustdoc failed:\n{stderr}")

    # JSON file uses underscores: iceberg-datafusion → iceberg_datafusion.json
    json_name = crate_name.replace("-", "_") + ".json"
    json_path = project_root / "target" / "doc" / json_name
    if not json_path.exists():
        sys.exit(f"Error: expected JSON at {json_path} but it doesn't exist")

    print(f"  Generated {json_path} ({json_path.stat().st_size / 1024:.0f} KB)", file=sys.stderr)
    return json_path


def find_project_root() -> Path:
    """Walk up from cwd to find Cargo.lock."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "Cargo.lock").exists():
            return parent
    sys.exit("Error: could not find Cargo.lock in any parent directory")


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def generate_api_markdown(data: dict, only_index: bool = False) -> str:
    """Convert parsed rustdoc JSON to markdown string."""
    index = data["index"]
    paths = data.get("paths", {})
    crate_version = data.get("crate_version", "unknown")
    root_id = str(data["root"])
    root_item = index.get(root_id, {})
    crate_name = root_item.get("name", "unknown")

    lines = []
    w = lines.append  # shorthand

    w(f"# {crate_name} {crate_version} — Full API Reference\n")
    w(f"> Generated from rustdoc JSON (format v{data['format_version']})\n")

    # Categorize items
    structs, enums, traits, functions, modules = {}, {}, {}, {}, {}
    for item_id, item in index.items():
        inner = item.get("inner", {})
        name = item.get("name")
        if not name:
            continue
        if "struct" in inner:
            structs[item_id] = item
        elif "enum" in inner:
            enums[item_id] = item
        elif "trait" in inner:
            traits[item_id] = item
        elif "function" in inner:
            functions[item_id] = item
        elif "module" in inner:
            modules[item_id] = item

    # Group methods by parent struct/enum/trait
    methods_by_parent = defaultdict(list)
    for item_id, item in index.items():
        inner = item.get("inner", {})
        if "impl" in inner:
            impl_data = inner["impl"]
            if impl_data.get("trait") is not None:
                continue
            for method_id in impl_data.get("items", []):
                mid = str(method_id)
                if mid in index:
                    method = index[mid]
                    if "function" in method.get("inner", {}):
                        self_type = impl_data.get("for")
                        if self_type and "resolved_path" in self_type:
                            parent_id = str(self_type["resolved_path"].get("id", ""))
                            methods_by_parent[parent_id].append(method)

    # Path lookup
    path_lookup = {}
    for pid, pinfo in paths.items():
        if isinstance(pinfo, dict):
            path_lookup[pid] = "::".join(pinfo.get("path", []))

    # --- Index-only mode ---
    if only_index:
        w("## Structs\n")
        for sid, s in sorted(structs.items(), key=lambda x: x[1].get("name", "")):
            path = path_lookup.get(sid, "")
            desc = first_paragraph(s.get("docs", ""))
            w(f"- **{s['name']}** (`{path}`) — {desc}")

        w("\n## Enums\n")
        for eid, e in sorted(enums.items(), key=lambda x: x[1].get("name", "")):
            path = path_lookup.get(eid, "")
            desc = first_paragraph(e.get("docs", ""))
            w(f"- **{e['name']}** (`{path}`) — {desc}")

        w("\n## Traits\n")
        for tid, t in sorted(traits.items(), key=lambda x: x[1].get("name", "")):
            path = path_lookup.get(tid, "")
            desc = first_paragraph(t.get("docs", ""))
            w(f"- **{t['name']}** (`{path}`) — {desc}")

        return "\n".join(lines) + "\n"

    # --- Full mode ---

    # Structs
    w("## Structs\n")
    for sid, s in sorted(structs.items(), key=lambda x: x[1].get("name", "")):
        name = s["name"]
        docs = s.get("docs", "")
        path = path_lookup.get(sid, name)
        struct_data = s["inner"]["struct"]
        gen_str = render_generics(struct_data.get("generics", {}), index, paths)

        w(f"### `{name}{gen_str}` {{#{name.lower()}}}\n")
        w(f"*Module: `{path}`*\n")

        if docs:
            w(docs.strip() + "\n")

        # Fields
        kind = struct_data.get("kind", {})
        plain = kind.get("plain", {}) if isinstance(kind, dict) else {}
        field_ids = plain.get("fields", []) if isinstance(plain, dict) else []
        fields = []
        for field_id in field_ids:
            fid = str(field_id)
            if fid in index:
                field = index[fid]
                if "struct_field" in field.get("inner", {}):
                    field_type = render_type(field["inner"]["struct_field"], index, paths)
                    field_docs = first_paragraph(field.get("docs", ""))
                    fields.append((field["name"], field_type, field_docs))

        if fields:
            w("**Fields:**\n")
            w("```rust")
            for fname, ftype, _ in fields:
                w(f"pub {fname}: {ftype},")
            w("```\n")
            for fname, _, fdocs in fields:
                if fdocs:
                    w(f"- `{fname}`: {fdocs}")
            w("")

        # Methods
        methods = methods_by_parent.get(sid, [])
        for method in sorted(methods, key=lambda m: m.get("name", "")):
            fn_data = method["inner"]["function"]
            sig = render_fn_sig(method["name"], fn_data, index, paths)
            w(f"#### `{method['name']}`\n")
            w(f"```rust\n{sig}\n```\n")
            mdocs = method.get("docs", "")
            if mdocs:
                w(mdocs.strip() + "\n")

        w("---\n")

    # Enums
    if enums:
        w("## Enums\n")
        for eid, e in sorted(enums.items(), key=lambda x: x[1].get("name", "")):
            name = e["name"]
            docs = e.get("docs", "")
            path = path_lookup.get(eid, name)
            enum_data = e["inner"]["enum"]

            w(f"### `{name}`\n")
            w(f"*Module: `{path}`*\n")

            if docs:
                w(docs.strip() + "\n")

            # Variants
            variants = []
            for vid in enum_data.get("variants", []):
                vid_str = str(vid)
                if vid_str in index:
                    v = index[vid_str]
                    variants.append((v.get("name", ""), v.get("docs", "")))

            if variants:
                w("**Variants:**\n")
                for vname, vdocs in variants:
                    doc_str = f" — {first_paragraph(vdocs)}" if vdocs else ""
                    w(f"- `{vname}`{doc_str}")
                w("")

            # Methods
            methods = methods_by_parent.get(eid, [])
            for method in sorted(methods, key=lambda m: m.get("name", "")):
                fn_data = method["inner"]["function"]
                sig = render_fn_sig(method["name"], fn_data, index, paths)
                w(f"#### `{method['name']}`\n")
                w(f"```rust\n{sig}\n```\n")
                mdocs = method.get("docs", "")
                if mdocs:
                    w(mdocs.strip() + "\n")

            w("---\n")

    # Traits
    if traits:
        w("## Traits\n")
        for tid, t in sorted(traits.items(), key=lambda x: x[1].get("name", "")):
            name = t["name"]
            docs = t.get("docs", "")
            path = path_lookup.get(tid, name)
            trait_data = t["inner"]["trait"]

            w(f"### `{name}`\n")
            w(f"*Module: `{path}`*\n")

            if docs:
                w(docs.strip() + "\n")

            trait_methods = []
            for mid in trait_data.get("items", []):
                mid_str = str(mid)
                if mid_str in index:
                    m = index[mid_str]
                    if "function" in m.get("inner", {}):
                        trait_methods.append(m)

            for method in trait_methods:
                fn_data = method["inner"]["function"]
                sig = render_fn_sig(method["name"], fn_data, index, paths)
                w(f"#### `{method['name']}`\n")
                w(f"```rust\n{sig}\n```\n")
                mdocs = method.get("docs", "")
                if mdocs:
                    w(mdocs.strip() + "\n")

            w("---\n")

    # Top-level functions (not methods)
    impl_items = set()
    for item_id, item in index.items():
        inner = item.get("inner", {})
        if "impl" in inner:
            for mid in inner["impl"].get("items", []):
                impl_items.add(str(mid))

    top_level_fns = [(fid, f) for fid, f in functions.items() if fid not in impl_items]

    if top_level_fns:
        w("## Functions\n")
        for fid, f in sorted(top_level_fns, key=lambda x: x[1].get("name", "")):
            fn_data = f["inner"]["function"]
            sig = render_fn_sig(f["name"], fn_data, index, paths)
            w(f"#### `{f['name']}`\n")
            w(f"```rust\n{sig}\n```\n")
            fdocs = f.get("docs", "")
            if fdocs:
                w(fdocs.strip() + "\n")

    return "\n".join(lines) + "\n"


def write_output(api_markdown: str, output_path: Path, crate_name: str, crate_version: str):
    """Write the API reference to the output file, preserving any curated section."""
    SEPARATOR = "# Full API Reference"

    if output_path.exists():
        existing = output_path.read_text()
        sep_idx = existing.find(f"\n{SEPARATOR}")
        if sep_idx == -1:
            sep_idx = existing.find(SEPARATOR)

        if sep_idx != -1:
            # Preserve curated section, replace API reference
            curated = existing[:sep_idx].rstrip() + "\n\n"
            # Strip the header from api_markdown (it has its own # title)
            # Replace with just the section heading
            api_body = api_markdown.lstrip()
            if api_body.startswith("# "):
                # Skip the first "# crate version — Full API Reference" line
                api_body = api_body.split("\n", 1)[1] if "\n" in api_body else ""
            final = curated + SEPARATOR + "\n\n" + api_body
            output_path.write_text(final)
            print(f"  Updated API reference in {output_path} (curated section preserved)", file=sys.stderr)
            return

    # No existing file or no separator — write full API reference only
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(api_markdown)
    print(f"  Wrote {output_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate Markdown API reference from rustdoc JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Two modes: crate name or JSON file
    parser.add_argument("crate_name", nargs="?", help="Crate name (e.g., datafusion)")
    parser.add_argument("version", nargs="?", help="Crate version (auto-detected from Cargo.lock if omitted)")
    parser.add_argument("--json", metavar="FILE", help="Use existing JSON file instead of running cargo rustdoc")
    parser.add_argument("--output", "-o", metavar="PATH", help="Output file path (default: docs/vendored/rust/{name}-{version}.md)")
    parser.add_argument("--only-index", action="store_true", help="Compact index mode (just type names)")
    parser.add_argument("--skip-build", action="store_true", help="Skip cargo rustdoc, reuse existing JSON in target/doc/")
    parser.add_argument("--stdout", action="store_true", help="Write to stdout instead of file")

    args = parser.parse_args()

    # Validate args
    if not args.json and not args.crate_name:
        parser.error("Provide a crate name or --json FILE")

    if args.json:
        # Direct JSON mode
        json_path = Path(args.json)
        if not json_path.exists():
            sys.exit(f"Error: {json_path} not found")

        with open(json_path) as f:
            data = json.load(f)

        crate_version = data.get("crate_version", "unknown")
        root_item = data["index"].get(str(data["root"]), {})
        crate_name = root_item.get("name", "unknown")
    else:
        # Full pipeline mode
        project_root = find_project_root()
        crate_name = args.crate_name

        if args.version:
            crate_version = args.version
        else:
            crate_version = resolve_version(crate_name, project_root)
            print(f"  Resolved {crate_name} version: {crate_version}", file=sys.stderr)

        if args.skip_build:
            json_name = crate_name.replace("-", "_") + ".json"
            json_path = project_root / "target" / "doc" / json_name
            if not json_path.exists():
                sys.exit(f"Error: {json_path} not found. Run without --skip-build first.")
        else:
            json_path = run_cargo_rustdoc(crate_name, project_root)

        with open(json_path) as f:
            data = json.load(f)

    # Generate markdown
    api_markdown = generate_api_markdown(data, only_index=args.only_index)

    n_structs = sum(1 for v in data["index"].values() if "struct" in v.get("inner", {}))
    n_traits = sum(1 for v in data["index"].values() if "trait" in v.get("inner", {}))
    n_enums = sum(1 for v in data["index"].values() if "enum" in v.get("inner", {}))
    n_lines = api_markdown.count("\n")
    print(f"  {n_structs} structs, {n_traits} traits, {n_enums} enums, {n_lines} lines", file=sys.stderr)

    if args.stdout:
        sys.stdout.write(api_markdown)
        return

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        project_root = find_project_root()
        output_path = project_root / "docs" / "vendored" / "rust" / f"{crate_name}-{crate_version}.md"

    write_output(api_markdown, output_path, crate_name, crate_version)


if __name__ == "__main__":
    main()
