#!/usr/bin/env python3
"""Schema drift checker — validates that server.py and tool_registry.py
match the canonical tools_schema.json.

Compares:
  - Tool names (missing / extra)
  - Parameter names (missing / extra)
  - Parameter types (string / integer / number / boolean)
  - Parameter required vs optional
  - Description first sentences

Tolerant of:
  - Parameter ordering differences
  - Minor docstring formatting (compares first sentence only)
  - Default value differences (only required/optional matters)
  - Schema "string" catch-all for Python list/dict/Any types

Exit code 0: no drift.  Exit code 1: drift detected.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_sentence(text: str) -> str:
    """Extract the first sentence from a docstring or description.

    Splits on '. ' or '.\n' (period + whitespace) and keeps the first
    chunk including its period.  Falls back to the whole text if there
    is no sentence boundary.
    """
    text = text.strip()
    m = re.search(r"\.(?:\s|\n)", text)
    if m:
        end = m.start() + 1
        return text[:end].strip()
    if text.endswith("."):
        return text
    return text


# ---------------------------------------------------------------------------
# Python type → JSON Schema type mapping
# ---------------------------------------------------------------------------

def _is_none_constant(node: ast.expr) -> bool:
    """True if *node* is the literal ``None``."""
    return isinstance(node, ast.Constant) and node.value is None


def py_type_to_schema(annotation: ast.expr | None) -> str:
    """Map a Python AST type annotation to a JSON Schema type name.

    Primitive mappings
    ------------------
    str   → "string"      int   → "integer"
    float → "number"      bool  → "boolean"

    Complex / catch-all
    -------------------
    list[...], dict[...], Any, and unknown annotations all map to
    "string".  tools_schema.json intentionally simplifies nested and
    collection types to "string" — it conveys structural constraints
    through descriptions rather than JSON Schema keywords.

    Union types (``str | None``, ``list[str] | None``) resolve to the
    non-None arm's type.
    """
    if annotation is None:
        return "string"

    # Simple name: str, int, float, bool, Any, ...
    if isinstance(annotation, ast.Name):
        return {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
        }.get(annotation.id, "string")

    # Constant literal (e.g. None)
    if isinstance(annotation, ast.Constant):
        return "string"

    # Subscript: list[str], dict[str, Any], list[dict[...]], ...
    if isinstance(annotation, ast.Subscript):
        return "string"

    # BinOp (``|`` union): str | None, list[str] | None, int | float, ...
    if isinstance(annotation, ast.BinOp):
        return _resolve_union(annotation)

    return "string"


def _resolve_union(node: ast.BinOp) -> str:
    """Resolve ``X | Y`` by picking the non-None side.

    If both sides are non-None and map to the same type, return that
    type; otherwise prefer the side that is not "string".
    """
    left_none = _is_none_constant(node.left)
    right_none = _is_none_constant(node.right)

    if left_none:
        return py_type_to_schema(node.right)
    if right_none:
        return py_type_to_schema(node.left)

    lt = py_type_to_schema(node.left)
    rt = py_type_to_schema(node.right)
    if lt == rt:
        return lt
    if lt != "string":
        return lt
    if rt != "string":
        return rt
    return "string"


# ---------------------------------------------------------------------------
# server.py — AST parser
# ---------------------------------------------------------------------------

def parse_server(path: Path) -> dict[str, dict[str, Any]]:
    """Parse ``@mcp.tool`` decorated async functions from *server.py*.

    Returns
    -------
    dict
        ``{tool_name: {"description": str, "params": {name: {"type": str, "required": bool}}}}``
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    tools: dict[str, dict[str, Any]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        # Detect @mcp.tool (or bare @tool if imported directly)
        is_tool = False
        for deco in node.decorator_list:
            if isinstance(deco, ast.Attribute) and deco.attr == "tool":
                is_tool = True
                break
            if isinstance(deco, ast.Name) and deco.id == "tool":
                is_tool = True
                break
        if not is_tool:
            continue

        tool_name = node.name

        # --- description (first sentence of docstring) ---
        raw = ast.get_docstring(node)
        description = _first_sentence(raw) if raw else ""

        # --- parameters ---
        arg_names = [a.arg for a in node.args.args]
        num_defaults = len(node.args.defaults)
        num_required = len(arg_names) - num_defaults

        params: dict[str, dict[str, Any]] = {}
        for idx, arg in enumerate(node.args.args):
            pname = arg.arg
            if pname in ("self", "cls"):
                continue
            params[pname] = {
                "type": py_type_to_schema(arg.annotation),
                "required": idx < num_required,
            }

        tools[tool_name] = {"description": description, "params": params}

    return tools


# ---------------------------------------------------------------------------
# tool_registry.py — AST parser
# ---------------------------------------------------------------------------

class _ParamAccessVisitor(ast.NodeVisitor):
    """Walk a handler body, recording ``params["k"]`` and ``params.get("k")``.

    Handles both plain assignments (``Assign``) and annotated assignments
    (``AnnAssign``), since the registry uses ``name: Type = params[...]``.
    """

    def __init__(self) -> None:
        self.params: dict[str, dict[str, Any]] = {}  # name → {required, type}

    # --- common extraction helpers ---

    @staticmethod
    def _extract_subscript_key(val: ast.expr) -> str | None:
        """If *val* is ``params["key"]``, return ``"key"``; else None."""
        if not isinstance(val, ast.Subscript):
            return None
        if (
            isinstance(val.value, ast.Name)
            and val.value.id == "params"
            and isinstance(val.slice, ast.Constant)
            and isinstance(val.slice.value, str)
        ):
            return val.slice.value
        return None

    @staticmethod
    def _extract_get_key(val: ast.expr) -> str | None:
        """If *val* is ``params.get("key", ...)``, return ``"key"``; else None."""
        if not isinstance(val, ast.Call):
            return None
        if (
            isinstance(val.func, ast.Attribute)
            and val.func.attr == "get"
            and isinstance(val.func.value, ast.Name)
            and val.func.value.id == "params"
            and len(val.args) >= 1
            and isinstance(val.args[0], ast.Constant)
            and isinstance(val.args[0].value, str)
        ):
            return val.args[0].value
        return None

    # --- visitors ---

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) != 1:
            self.generic_visit(node)
            return
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            self.generic_visit(node)
            return

        self._record_access(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # e.g. run_id: str = params["run_id"]
        if not isinstance(node.target, ast.Name):
            self.generic_visit(node)
            return
        if node.value is None:
            self.generic_visit(node)
            return

        self._record_access(node.value)
        self.generic_visit(node)

    def _record_access(self, val: ast.expr, annotation: ast.expr | None = None) -> None:
        required: bool | None = None
        key = self._extract_subscript_key(val)
        if key is not None:
            required = True
        else:
            key = self._extract_get_key(val)
            if key is not None:
                required = False
        if key is None:
            return

        ptype = py_type_to_schema(annotation)
        self.params[key] = {"required": required, "type": ptype}

    # ----------------------------------------------------------------
    # Assign / AnnAssign visitors
    # ----------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) != 1:
            self.generic_visit(node)
            return
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            self.generic_visit(node)
            return
        self._record_access(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not isinstance(node.target, ast.Name):
            self.generic_visit(node)
            return
        if node.value is None:
            self.generic_visit(node)
            return
        self._record_access(node.value, annotation=node.annotation)
        self.generic_visit(node)


def parse_registry(path: Path) -> dict[str, dict[str, Any]]:
    """Parse ``_oculai_*`` handler functions from *tool_registry.py*.

    Returns
    -------
    dict
        ``{tool_name: {"params": {name: {"required": bool}}}}``

    Tool name is derived by stripping the leading ``_`` from the
    handler function name (e.g. ``_oculai_create_run`` → ``oculai_create_run``).
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    handlers: dict[str, dict[str, Any]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("_oculai_"):
            continue

        tool_name = node.name[1:]  # strip leading underscore
        visitor = _ParamAccessVisitor()
        visitor.visit(node)

        handlers[tool_name] = {"params": dict(visitor.params)}

    return handlers


def parse_registry_mapping(path: Path) -> dict[str, str]:
    """Extract the ``TOOL_REGISTRY`` dict: tool_name → handler_func_name."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    mapping: dict[str, str] = {}

    class V(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            tgt = node.targets[0]
            tgt_name = None
            if isinstance(tgt, ast.Name):
                tgt_name = tgt.id
            elif isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name):
                tgt_name = tgt.value.id
            if tgt_name != "TOOL_REGISTRY":
                self.generic_visit(node)
                return
            if not isinstance(node.value, ast.Dict):
                return
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    if isinstance(v, ast.Name):
                        mapping[k.value] = v.id

    V().visit(tree)
    return mapping


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(
    server_tools: dict[str, Any],
    registry_handlers: dict[str, Any],
    registry_map: dict[str, str],
    schema_tools: dict[str, Any],
) -> list[str]:
    """Run all comparisons; return a list of human-readable drift errors."""
    errors: list[str] = []

    srv = set(server_tools)
    reg = set(registry_handlers)
    sch = set(schema_tools)

    # ==================================================================
    # 1. server.py  ↔  tools_schema.json
    # ==================================================================

    for name in sorted(srv - sch):
        errors.append(
            f"  server.py::{name}: present in server.py but NOT in tools_schema.json"
        )
    for name in sorted(sch - srv):
        errors.append(
            f"  server.py: missing tool '{name}' (in tools_schema.json but not in server.py)"
        )

    for name in sorted(sch & srv):
        _compare_params(
            errors,
            prefix=f"server.py::{name}",
            schema_params=schema_tools[name],
            code_params=server_tools[name]["params"],
            code_label="server.py",
        )

        # Description
        sd = _first_sentence(schema_tools[name].get("description", ""))
        cd = _first_sentence(server_tools[name].get("description", ""))
        if sd and cd and sd != cd:
            errors.append(
                f"  server.py::{name}: description mismatch: "
                f"schema='{sd}' vs server='{cd}'"
            )

    # ==================================================================
    # 2. tool_registry.py  ↔  tools_schema.json
    # ==================================================================

    for name in sorted(sch - reg):
        errors.append(
            f"  tool_registry.py: missing handler for '{name}' "
            f"(in schema but not in registry)"
        )
    for name in sorted(reg - sch):
        errors.append(
            f"  tool_registry.py::{name}: present in registry but NOT in tools_schema.json"
        )

    for name in sorted(sch & reg):
        _compare_params(
            errors,
            prefix=f"tool_registry.py::{name}",
            schema_params=schema_tools[name],
            code_params=registry_handlers[name].get("params", {}),
            code_label="handler",
        )

    # ==================================================================
    # 3. Cross-check: server.py  ↔  tool_registry.py
    # ==================================================================

    for name in sorted(srv - reg):
        errors.append(
            f"  tool_registry.py: missing handler for '{name}' "
            f"(present in server.py)"
        )
    for name in sorted(reg - srv):
        errors.append(
            f"  server.py: missing tool '{name}' (present in tool_registry.py)"
        )

    # Check handler naming convention (TOOL_REGISTRY entries)
    for name, handler_name in sorted(registry_map.items()):
        expected_handler = "_" + name
        if handler_name != expected_handler:
            errors.append(
                f"  tool_registry.py: TOOL_REGISTRY['{name}'] maps to "
                f"'{handler_name}' but expected '{expected_handler}'"
            )

    return errors


def _compare_params(
    errors: list[str],
    prefix: str,
    schema_params: dict[str, Any],
    code_params: dict[str, dict[str, Any]],
    code_label: str,
) -> None:
    """Compare parameter names and types between schema and code."""
    schema_props = schema_params.get("parameters", {}).get("properties", {})
    schema_req = set(schema_params.get("parameters", {}).get("required", []))

    sp = set(schema_props)
    cp = set(code_params)

    for p in sorted(cp - sp):
        errors.append(
            f"  {prefix}: parameter '{p}' present in {code_label} "
            f"but NOT in tools_schema.json"
        )
    for p in sorted(sp - cp):
        errors.append(
            f"  {prefix}: parameter '{p}' in tools_schema.json "
            f"but NOT in {code_label}"
        )

    for p in sorted(sp & cp):
        st = schema_props[p].get("type", "string")
        ct = code_params[p].get("type", "string")

        if st != ct:
            errors.append(
                f"  {prefix}: parameter '{p}' type mismatch: "
                f"expected '{st}' (schema), got '{ct}' ({code_label})"
            )

        # Required / optional
        sr = p in schema_req
        cr = code_params[p].get("required", False)
        if sr != cr:
            errors.append(
                f"  {prefix}: parameter '{p}' required/optional mismatch: "
                f"schema={'required' if sr else 'optional'}, "
                f"{code_label}={'required' if cr else 'optional'}"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    server_path = repo / "oculai-mcp" / "src" / "oculai_mcp" / "server.py"
    registry_path = repo / "oculai-mcp" / "src" / "oculai_mcp" / "tool_registry.py"
    schema_path = repo / "oculai-mcp" / "src" / "oculai_mcp" / "tools_schema.json"

    # CLI overrides
    if len(sys.argv) > 1:
        server_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        registry_path = Path(sys.argv[2])
    if len(sys.argv) > 3:
        schema_path = Path(sys.argv[3])

    for p, label in [
        (server_path, "server.py"),
        (registry_path, "tool_registry.py"),
        (schema_path, "tools_schema.json"),
    ]:
        if not p.exists():
            print(f"ERROR: {label} not found at {p}", file=sys.stderr)
            return 2

    schema_tools = json.loads(schema_path.read_text(encoding="utf-8")).get("tools", {})
    server_tools = parse_server(server_path)
    registry_handlers = parse_registry(registry_path)
    registry_map = parse_registry_mapping(registry_path)

    errors = compare(server_tools, registry_handlers, registry_map, schema_tools)

    if errors:
        print("DRIFT DETECTED:")
        for e in errors:
            print(e)
        return 1

    print("OK: server.py and tool_registry.py match tools_schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
