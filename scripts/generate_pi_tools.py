#!/usr/bin/env python3
"""
Generate TypeScript tool definitions for Pi extension registration.

Reads oculai-mcp/src/oculai_mcp/tools_schema.json (the single source of truth
for all Oculai MCP tool parameter schemas) and produces
oculai-desktop/src/main/generated-tools.ts — a standalone TypeScript module
that exports the OCULAI_TOOLS constant consumed by pi-session.ts.

Usage:
    python scripts/generate_pi_tools.py
"""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "oculai-mcp" / "src" / "oculai_mcp" / "tools_schema.json"
OUTPUT_PATH = ROOT / "oculai-desktop" / "src" / "main" / "generated-tools.ts"

HEADER = """\
// AUTO-GENERATED from tools_schema.json. DO NOT EDIT.
// Regenerate: python scripts/generate_pi_tools.py

export const OCULAI_TOOLS: Record<
  string,
  { description: string; parameters: Record<string, unknown> }
> = {
"""

FOOTER = "};\n"


def _json_type_to_ts(value: str) -> str:
    """Map a JSON Schema type string to a TypeScript-compatible type string."""
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
    }
    if value in mapping:
        return mapping[value]
    # "array" and "object" are handled upstream — this should not happen,
    # but return as-is for forward compatibility.
    return value


def _build_property_def(param_schema: dict[str, Any]) -> str:
    """Build the TS property definition for a single parameter."""
    jtype = param_schema.get("type", "string")

    if jtype == "array":
        # Determine items type.  The JSON schema currently only uses the
        # top-level param type, so we infer item type from the description
        # or default to "string".  If the schema is later enriched with an
        # "items" key, honour it.
        items_meta = param_schema.get("items")
        if isinstance(items_meta, dict) and "type" in items_meta:
            item_type = _json_type_to_ts(items_meta["type"])
        else:
            item_type = "string"
        return f'{{ type: "array", items: {{ type: "{item_type}" }} }}'

    if jtype == "object":
        return '{ type: "object" }'

    normalised = _json_type_to_ts(jtype)
    return f'{{ type: "{normalised}" }}'


def generate() -> str:
    """Read the JSON schema and return the full TypeScript source string."""
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)

    tools: dict[str, dict[str, Any]] = schema["tools"]
    lines: list[str] = [HEADER]

    tool_names = sorted(tools.keys())

    for idx, name in enumerate(tool_names):
        tool = tools[name]
        desc = tool["description"]
        params = tool["parameters"]
        props: dict[str, Any] = params.get("properties", {})
        required: list[str] = params.get("required", [])

        # Tool-level doc comment
        lines.append(f"  // {tool.get('group', '')}")
        lines.append(f"  {name}: {{")
        # Escape double-quotes and backslashes in the description
        safe_desc = desc.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'    description: "{safe_desc}",')
        lines.append("    parameters: {")
        lines.append('      type: "object",')
        lines.append("      properties: {")

        prop_names = list(props.keys())
        for pi, pname in enumerate(prop_names):
            pschema = props[pname]
            prop_def = _build_property_def(pschema)
            comma = "," if pi < len(prop_names) - 1 else ""
            lines.append(f"        {pname}: {prop_def}{comma}")

        lines.append("      },")

        if required:
            req_items = ", ".join(f'"{r}"' for r in required)
            lines.append(f"      required: [{req_items}],")

        lines.append("    },")
        # Close tool entry — no trailing comma on last entry
        comma = "," if idx < len(tool_names) - 1 else ""
        lines.append(f"  }}{comma}")

        # Blank line between groups
        next_idx = idx + 1
        if next_idx < len(tool_names):
            next_group = tools[tool_names[next_idx]].get("group", "")
            if next_group != tool.get("group", ""):
                lines.append("")

    lines.append(FOOTER)
    return "\n".join(lines) + "\n"


def main() -> None:
    ts_source = generate()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ts_source)
    print(f"Wrote {len(ts_source)} bytes to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
