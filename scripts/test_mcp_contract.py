"""GPU-free structural checks for MCP/API generation and recovery parity."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp" / "server.py"


def _functions(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }


def _defaults(fn: ast.FunctionDef) -> dict[str, ast.expr | None]:
    args = [*fn.args.posonlyargs, *fn.args.args]
    values: list[ast.expr | None] = [None] * (len(args) - len(fn.args.defaults))
    values.extend(fn.args.defaults)
    return {arg.arg: default for arg, default in zip(args, values)}


def _is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def main() -> None:
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    funcs = _functions(tree)

    required_tools = {
        "system_status",
        "text_to_3d",
        "image_to_3d",
        "texture_mesh",
        "get_job",
        "wait_for_job",
        "cancel_job",
        "resume_postprocess",
        "list_assets",
        "get_asset",
        "export_asset",
        "get_texture_maps",
    }
    assert required_tools <= funcs.keys(), required_tools - funcs.keys()

    generation_args = (
        "preset",
        "target_polycount",
        "texture_size",
        "adapter",
        "seed",
        "generate_pbr",
        "decimate",
    )
    for name in ("text_to_3d", "image_to_3d"):
        defaults = _defaults(funcs[name])
        for arg in generation_args:
            assert arg in defaults, f"{name} missing {arg}"
            # Named presets must not be silently overridden by MCP-side defaults.
            assert _is_none(defaults[arg]), f"{name}.{arg} must default to None"

    for field in generation_args:
        assert f'"{field}": {field}' in source, f"_options missing {field}"
    assert '/api/assets/{asset_id}/resume' in source
    assert '/api/jobs/{job_id}/cancel' in source
    assert '/api/assets/{asset_id}' in source

    print(
        "PASS: MCP exposes backend presets/options, diagnostics, cancellation, "
        "asset detail, and checkpoint resume"
    )


if __name__ == "__main__":
    main()
