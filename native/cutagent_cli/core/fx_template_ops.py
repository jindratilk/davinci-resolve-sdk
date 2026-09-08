"""Reviewed Fusion-effect registry with exact targeting and rendered verification."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..connection import ResolveConnection
from ..errors import (
    EffectNotSupported,
    EffectParameterInvalid,
    EffectVerificationFailed,
    ValidationError,
)
from ..output import set_recoverability, set_verification_status
from .effect_render_proof import RenderMutationProof
from .mutation_target import (
    TimelineItemTarget,
    resolve_timeline_item_target,
    revalidate_timeline_item_target,
)
from . import version_ops

_DEFAULT_FX_TEMPLATE_DIR = os.path.expanduser("~/.cutagent-cli/fx-templates")
_TOKEN = re.compile(r"{{\s*([A-Za-z][A-Za-z0-9_]*)\s*}}")


def _number(minimum: float, maximum: float, default: float) -> dict[str, Any]:
    return {
        "type": "number",
        "minimum": minimum,
        "maximum": maximum,
        "default": default,
    }


_BUILTIN_FX_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "fusion.soft_glow",
        "name": "Glow",
        "tool_type": "SoftGlow",
        "aliases": ("glow", "soft glow", "softglow"),
        "parameters": {"Gain": _number(0, 5, 1), "Blend": _number(0, 1, 1)},
    },
    {
        "id": "fusion.blur",
        "name": "Blur",
        "tool_type": "Blur",
        "aliases": ("blur",),
        "parameters": {
            "XBlurSize": _number(0, 100, 0),
            "YBlurSize": _number(0, 100, 0),
            "Blend": _number(0, 1, 1),
        },
    },
    {
        "id": "fusion.unsharp_mask",
        "name": "Sharpen",
        "tool_type": "UnsharpMask",
        "aliases": ("sharpen", "unsharp mask", "unsharpmask"),
        "parameters": {"Gain": _number(0, 5, 1), "Blend": _number(0, 1, 1)},
    },
    {
        "id": "fusion.color_corrector",
        "name": "Color Correct",
        "tool_type": "ColorCorrector",
        "aliases": (
            "color correct",
            "colorcorrect",
            "color corrector",
            "colorcorrector",
        ),
        "parameters": {
            "MasterRGBGain": _number(0, 5, 1),
            "MasterRGBGamma": _number(0.01, 5, 1),
            "Saturation1": _number(0, 5, 1),
            "Blend": _number(0, 1, 1),
        },
    },
    {
        "id": "fusion.transform",
        "name": "Transform",
        "tool_type": "Transform",
        "aliases": ("transform",),
        "parameters": {
            "Size": _number(0.01, 10, 1),
            "Angle": _number(-360, 360, 0),
            "Aspect": _number(-5, 5, 1),
            "Blend": _number(0, 1, 1),
        },
    },
)


def _default_fx_template_dir() -> str:
    return os.environ.get("RESOLVE_FX_TEMPLATE_DIR", _DEFAULT_FX_TEMPLATE_DIR)


def _normalize_fx_name(value: str) -> str:
    token = str(value or "").strip().lower()
    if token.endswith(".setting"):
        token = token[:-8]
    for char in ("-", "_", ".", "/", "\\"):
        token = token.replace(char, " ")
    return " ".join(token.split())


def _compact_fx_name(value: str) -> str:
    return _normalize_fx_name(value).replace(" ", "")


def _builtin_fx_spec(name: str) -> Optional[dict[str, Any]]:
    normalized, compact = _normalize_fx_name(name), _compact_fx_name(name)
    for spec in _BUILTIN_FX_SPECS:
        candidates = (spec["id"], spec["name"], *spec["aliases"])
        if normalized in {_normalize_fx_name(row) for row in candidates} or compact in {
            _compact_fx_name(row) for row in candidates
        }:
            return spec
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_manifest_parameter_schema(
    schema: Any, expected_tool_names: set[str]
) -> bool:
    if not (
        isinstance(schema, dict)
        and schema.get("type") in {"number", "integer", "boolean", "string"}
        and isinstance(schema.get("token"), str)
        and bool(schema.get("token"))
        and isinstance(schema.get("tool_name"), str)
        and schema.get("tool_name") in expected_tool_names
        and isinstance(schema.get("input_id"), str)
        and bool(schema.get("input_id"))
        and ("required" not in schema or isinstance(schema["required"], bool))
    ):
        return False
    kind = schema["type"]
    minimum, maximum = schema.get("minimum"), schema.get("maximum")
    if kind == "number":
        return (
            not isinstance(minimum, bool)
            and isinstance(minimum, (int, float))
            and math.isfinite(float(minimum))
            and not isinstance(maximum, bool)
            and isinstance(maximum, (int, float))
            and math.isfinite(float(maximum))
            and float(minimum) <= float(maximum)
        )
    if kind == "integer":
        return (
            not isinstance(minimum, bool)
            and isinstance(minimum, int)
            and not isinstance(maximum, bool)
            and isinstance(maximum, int)
            and minimum <= maximum
        )
    if kind == "string":
        values = schema.get("enum")
        return (
            isinstance(values, list)
            and bool(values)
            and all(isinstance(value, str) for value in values)
            and len(values) == len(set(values))
        )
    return minimum is None and maximum is None


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path.with_suffix(".json")
    if not manifest_path.is_file():
        raise EffectNotSupported(
            "Custom FX templates require a reviewed sibling JSON manifest.",
            details={"template": str(path), "required_manifest": str(manifest_path)},
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EffectNotSupported(
            "FX manifest JSON is invalid.",
            details={"manifest": str(manifest_path), "error": str(exc)},
        ) from exc
    required = {
        "schema_version",
        "effect_id",
        "display_name",
        "template_sha256",
        "expected_tools",
        "parameters",
    }
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not required.issubset(payload)
    ):
        raise EffectNotSupported(
            "FX manifest does not match reviewed schema version 1.",
            details={
                "manifest": str(manifest_path),
                "required_fields": sorted(required),
            },
        )
    if payload["template_sha256"] != _sha256(path):
        raise EffectNotSupported(
            "FX template hash does not match its reviewed manifest.",
            details={"template": str(path)},
        )
    if (
        not isinstance(payload["effect_id"], str)
        or re.fullmatch(r"custom\.[a-z0-9]+(?:[._-][a-z0-9]+)*", payload["effect_id"])
        is None
    ):
        raise EffectNotSupported(
            "Custom effect_id must be a nonempty stable ID in the 'custom.' namespace.",
            details={"effect_id": payload.get("effect_id")},
        )
    if (
        not isinstance(payload["display_name"], str)
        or not payload["display_name"].strip()
    ):
        raise EffectNotSupported("FX manifest display_name must be a nonempty string.")
    aliases = payload.get("aliases", [])
    normalized_aliases = (
        [_normalize_fx_name(alias) for alias in aliases]
        if isinstance(aliases, list)
        and all(isinstance(alias, str) for alias in aliases)
        else []
    )
    if (
        not isinstance(aliases, list)
        or len(normalized_aliases) != len(aliases)
        or not all(normalized_aliases)
        or len(normalized_aliases) != len(set(normalized_aliases))
    ):
        raise EffectNotSupported("FX manifest aliases must be unique nonempty strings.")
    if (
        not isinstance(payload["expected_tools"], list)
        or not payload["expected_tools"]
        or not all(
            isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and bool(row.get("name").strip())
            and isinstance(row.get("type"), str)
            and bool(row.get("type").strip())
            and row.get("type") not in {"MediaIn", "MediaOut"}
            for row in payload["expected_tools"]
        )
    ):
        raise EffectNotSupported(
            "FX manifest expected_tools must contain exact name/type identities."
        )
    if not isinstance(payload["parameters"], dict):
        raise EffectNotSupported("FX manifest parameters must be an object.")
    expected_tool_names = {row["name"] for row in payload["expected_tools"]}
    if len(expected_tool_names) != len(payload["expected_tools"]):
        raise EffectNotSupported("FX manifest expected tool names must be unique.")
    if not all(
        isinstance(key, str)
        and key
        and _valid_manifest_parameter_schema(schema, expected_tool_names)
        for key, schema in payload["parameters"].items()
    ):
        raise EffectNotSupported("FX manifest contains an invalid parameter schema.")
    tokens = [schema["token"] for schema in payload["parameters"].values()]
    if len(tokens) != len(set(tokens)):
        raise EffectNotSupported("FX manifest parameter tokens must be unique.")
    input_bindings = [
        (schema["tool_name"], schema["input_id"])
        for schema in payload["parameters"].values()
    ]
    if len(input_bindings) != len(set(input_bindings)):
        raise EffectNotSupported(
            "FX manifest parameter tool/input bindings must be unique."
        )
    return payload


def _public_spec(
    spec: dict[str, Any], *, source: str, path: str | None = None
) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "name": spec["name"],
        "source": source,
        "tool_type": spec.get("tool_type"),
        "aliases": list(spec.get("aliases", ())),
        "parameters": spec.get("parameters", {}),
        "path": path,
    }


def _template_rows(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.setting")) if directory.is_dir() else []:
        try:
            manifest = _load_manifest(path)
        except EffectNotSupported:
            continue
        rows.append(
            _public_spec(
                {
                    "id": manifest["effect_id"],
                    "name": manifest["display_name"],
                    "tool_type": None,
                    "aliases": manifest.get("aliases", []),
                    "parameters": manifest["parameters"],
                },
                source="template",
                path=str(path),
            )
        )
    return rows


def list_fx_registry(template_dir: Optional[str] = None) -> dict[str, Any]:
    directory = Path(template_dir or _default_fx_template_dir()).expanduser()
    builtins = [_public_spec(spec, source="builtin") for spec in _BUILTIN_FX_SPECS]
    templates = _template_rows(directory)
    data: dict[str, Any] = {
        "directory": str(directory),
        "directory_exists": directory.is_dir(),
        "effects": [*builtins, *templates],
        "builtins": builtins,
        "templates": templates,
    }
    if not directory.is_dir():
        data["note"] = "Directory does not exist."
    return data


def _resolve_fx_template_path(name: str, explicit_path: Optional[str]) -> Path:
    return _resolve_custom(name, explicit_path)[0]


def _resolve_custom(
    name: str, explicit_path: str | None
) -> tuple[Path, dict[str, Any]]:
    directory = Path(_default_fx_template_dir()).expanduser()
    paths = (
        [Path(explicit_path).expanduser()]
        if explicit_path
        else (sorted(directory.glob("*.setting")) if directory.is_dir() else [])
    )
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        if not path.is_file():
            continue
        manifest = _load_manifest(path)
        candidates = (
            manifest["effect_id"],
            manifest["display_name"],
            *manifest.get("aliases", []),
        )
        if _normalize_fx_name(name) in {_normalize_fx_name(row) for row in candidates}:
            matches.append((path, manifest))
    if len(matches) != 1:
        raise EffectNotSupported(
            "The requested effect did not resolve to exactly one reviewed registry entry.",
            details={
                "effect": name,
                "template": explicit_path,
                "match_count": len(matches),
            },
        )
    return matches[0]


def _validate_value(name: str, value: Any, schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "number":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise EffectParameterInvalid(
                "Effect parameter must be a finite number.",
                details={"parameter": name, "value": value},
            )
        number = float(value)
        if number < float(schema.get("minimum", -math.inf)) or number > float(
            schema.get("maximum", math.inf)
        ):
            raise EffectParameterInvalid(
                "Effect parameter is outside its reviewed range.",
                details={
                    "parameter": name,
                    "value": value,
                    "minimum": schema.get("minimum"),
                    "maximum": schema.get("maximum"),
                },
            )
        return number
    if kind == "integer":
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < int(schema.get("minimum", value))
            or value > int(schema.get("maximum", value))
        ):
            raise EffectParameterInvalid(
                "Effect parameter must be an in-range integer.",
                details={"parameter": name, "value": value},
            )
        return value
    if kind == "boolean":
        if not isinstance(value, bool):
            raise EffectParameterInvalid(
                "Effect parameter must be a boolean.",
                details={"parameter": name, "value": value},
            )
        return value
    if kind == "string" and isinstance(schema.get("enum"), list):
        if not isinstance(value, str) or value not in schema["enum"]:
            raise EffectParameterInvalid(
                "Effect parameter must be one of the reviewed values.",
                details={"parameter": name, "value": value, "enum": schema["enum"]},
            )
        return value
    raise EffectParameterInvalid(
        "Effect parameter schema type is unsupported.",
        details={"parameter": name, "type": kind},
    )


def validate_effect_request(
    name: str,
    *,
    template_path: str | None = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    spec = _builtin_fx_spec(name)
    path = None
    manifest = None
    if spec and template_path:
        raise EffectNotSupported(
            "A built-in effect ID cannot be combined with --template.",
            details={"effect": name},
        )
    if not spec:
        path, manifest = _resolve_custom(name, template_path)
        spec = {
            "id": manifest["effect_id"],
            "name": manifest["display_name"],
            "tool_type": None,
            "parameters": manifest["parameters"],
        }
    supplied = params or {}
    if not isinstance(supplied, dict):
        raise EffectParameterInvalid("Effect params must be an object.")
    unknown = sorted(set(supplied) - set(spec["parameters"]))
    if unknown:
        raise EffectParameterInvalid(
            "Effect contains unsupported parameter IDs.",
            details={
                "effect_id": spec["id"],
                "unsupported": unknown,
                "supported": sorted(spec["parameters"]),
            },
        )
    normalized = {
        key: _validate_value(key, value, spec["parameters"][key])
        for key, value in supplied.items()
    }
    for key, schema in spec["parameters"].items():
        if schema.get("required") and key not in normalized:
            raise EffectParameterInvalid(
                "Required effect parameter is missing.", details={"parameter": key}
            )
    if path is not None and manifest is not None:
        _render_template(path, manifest, normalized)
    return {"spec": spec, "path": path, "manifest": manifest, "params": normalized}


def _comp_count(item: Any) -> int:
    try:
        return int(item.GetFusionCompCount() or 0)
    except Exception:
        return 0


def _comp(item: Any, *, ensure: bool) -> tuple[Any, bool]:
    created = False
    if _comp_count(item) <= 0 and ensure:
        add = getattr(item, "AddFusionComp", None)
        if not callable(add) or add() is False:
            raise EffectVerificationFailed(
                "Failed to add Fusion composition to exact target."
            )
        created = True
    for index in (1, 0):
        try:
            value = item.GetFusionCompByIndex(index)
        except Exception:
            value = None
        if value:
            return value, created
    raise EffectVerificationFailed("Cannot access Fusion composition on exact target.")


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "Name", ""))


def _tool_type(tool: Any) -> str | None:
    attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
    return (attrs or {}).get("TOOLS_RegID", getattr(tool, "ID", None))


def _same_value(expected: Any, actual: Any) -> bool:
    return (
        math.isclose(expected, float(actual), rel_tol=1e-6, abs_tol=1e-6)
        if isinstance(expected, float)
        and isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        else expected == actual
    )


def _write_inputs(tool: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    setter = getattr(tool, "SetInput", None)
    if params and not callable(setter):
        raise EffectVerificationFailed("Effect tool has no SetInput method.")
    checks: list[dict[str, Any]] = []
    for key, value in params.items():
        try:
            result = setter(key, value)
        except Exception as exc:
            raise EffectVerificationFailed(
                "Effect parameter write raised an error.",
                details={"parameter": key, "error": str(exc)},
            ) from exc
        getter = getattr(tool, "GetInput", None)
        actual = getter(key) if callable(getter) else None
        check = {
            "name": "parameter_readback",
            "parameter": key,
            "expected": value,
            "set_input_result": result,
            "actual": actual,
            "ok": (result is True or result is None) and _same_value(value, actual),
        }
        checks.append(check)
        if not check["ok"]:
            raise EffectVerificationFailed(
                "Effect parameter write did not survive readback.",
                details={"check": check},
            )
    return checks


def _failure(
    exc: Exception, target: TimelineItemTarget, rollback: dict[str, Any]
) -> EffectVerificationFailed:
    details = dict(getattr(exc, "details", {}) or {})
    details.update({"target": target.public(), "rollback": rollback})
    return EffectVerificationFailed(str(exc), details=details, recoverability="manual")


def _inspect_exact_pipe(comp: Any, tool: Any) -> dict[str, Any]:
    from . import color_ops

    media_in, media_out = color_ops._find_media_io(comp)
    chain = color_ops._main_chain(media_out, media_in)
    chain_names = [_tool_name(row) for row in chain]
    exact_rows = [
        row
        for row in color_ops._list_comp_tools(comp)
        if row.get("name") == _tool_name(tool) and row.get("type") == _tool_type(tool)
    ]
    valid = (
        len(exact_rows) == 1
        and _tool_name(tool) in chain_names
        and media_in is not None
        and _tool_name(media_in) in chain_names
    )
    return {
        "valid": valid,
        "exact_tool": exact_rows,
        "main_chain": chain_names,
        "media_in": _tool_name(media_in) if media_in else None,
        "media_out": _tool_name(media_out) if media_out else None,
    }


def _graph_without_inline_tool(
    snapshot: dict[str, Any], tool_name: str
) -> dict[str, Any]:
    normalized = deepcopy(snapshot)
    tool_info = normalized.get("tools", {}).get(tool_name, {})
    upstream = tool_info.get("inputs", {}).get("Input", {})
    for info in normalized.get("tools", {}).values():
        if info.get("type") != "MediaOut":
            continue
        input_info = info.get("inputs", {}).get("Input")
        if isinstance(input_info, dict) and input_info.get("source_name") == tool_name:
            input_info["source_name"] = upstream.get("source_name")
            input_info["source_output"] = upstream.get("source_output")
    normalized.get("tools", {}).pop(tool_name, None)
    normalized["order"] = [
        name for name in normalized.get("order", []) if name != tool_name
    ]
    return normalized


def _apply_builtin(
    conn: Any,
    target: TimelineItemTarget,
    request: dict[str, Any],
    proof: RenderMutationProof,
) -> dict[str, Any]:
    from . import color_ops

    spec = request["spec"]
    before = proof.capture("before")
    target = getattr(proof, "target", target)
    comp, created = _comp(target.item, ensure=True)
    graph_before = color_ops._snapshot_comp_graph(comp)
    media_in_before, media_out_before = color_ops._find_media_io(comp)
    chain_before = [
        _tool_name(row)
        for row in color_ops._main_chain(media_out_before, media_in_before)
    ]
    revalidate_timeline_item_target(conn, target)
    with color_ops._locked_comp(comp):
        tool = color_ops._create_comp_tool(
            comp, spec["tool_type"], prefix=spec["tool_type"]
        )
        if not color_ops._connect_tool_inline(comp, tool):
            raise EffectVerificationFailed(
                "Effect tool could not be connected into the main image pipe."
            )
        parameter_checks = _write_inputs(tool, request["params"])
    structural = _inspect_exact_pipe(comp, tool)
    graph_after = color_ops._snapshot_comp_graph(comp)
    expected_chain = [_tool_name(tool), *chain_before]
    graph_preserved = (
        _graph_without_inline_tool(graph_after, _tool_name(tool)) == graph_before
    )
    structural.update(
        {
            "expected_main_chain": expected_chain,
            "prior_graph_preserved": graph_preserved,
        }
    )
    if structural["main_chain"] != expected_chain or not graph_preserved:
        structural["valid"] = False
    if not structural["valid"]:
        raise EffectVerificationFailed(
            "Exact effect identity and topology are not present in the main image pipe.",
            details={"structural": structural},
        )
    tool_name, tool_type = _tool_name(tool), _tool_type(tool)
    after = proof.capture("after")
    target = getattr(proof, "target", target)
    comparison = proof.compare(before, after)
    if not comparison["changed"]:
        raise EffectVerificationFailed(
            "Rendered pixels did not change after effect application.",
            details={"comparison": comparison},
        )
    try:
        restored = proof.restore_playhead()
    except Exception as exc:
        raise EffectVerificationFailed(
            "Original playhead could not be restored.", details={"error": str(exc)}
        ) from exc
    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "effect": {
            "id": spec["id"],
            "display_name": spec["name"],
            "source": "builtin",
            "tool_type": spec["tool_type"],
        },
        "target": target.public(),
        "parameters": request["params"],
        "verification": {
            "status": "verified",
            "checks": [
                {
                    "name": "exact_tool_identity_and_topology",
                    "ok": True,
                    "tool_name": tool_name,
                    "tool_type": tool_type,
                    **structural,
                },
                *parameter_checks,
                {"name": "rendered_pixel_change", "ok": True, **comparison},
            ],
            "render_proof": {
                "before": before,
                "after": after,
                "directory": str(proof.directory),
                "restored_playhead": restored,
            },
        },
    }


def _render_template(
    path: Path, manifest: dict[str, Any], params: dict[str, Any]
) -> str:
    body = path.read_text(encoding="utf-8")
    token_occurrences = _TOKEN.findall(body)
    tokens = set(token_occurrences)
    token_map = {
        str(schema["token"]): key for key, schema in manifest["parameters"].items()
    }
    if tokens != set(token_map):
        raise EffectParameterInvalid(
            "Template tokens must exactly match the reviewed parameter bindings.",
            details={
                "undeclared_tokens": sorted(tokens - set(token_map)),
                "unused_bindings": sorted(set(token_map) - tokens),
            },
        )
    duplicate_tokens = sorted(
        token for token in tokens if token_occurrences.count(token) != 1
    )
    if duplicate_tokens:
        raise EffectParameterInvalid(
            "Each reviewed template parameter token must occur exactly once.",
            details={"duplicate_tokens": duplicate_tokens},
        )
    rendered = body
    for token in tokens:
        key = token_map[token]
        if key not in params:
            raise EffectParameterInvalid(
                "Template replacement parameter is missing.",
                details={"parameter": key, "token": token},
            )
        value = params[key]
        replacement = (
            json.dumps(value)
            if isinstance(value, str)
            else str(value).lower()
            if isinstance(value, bool)
            else str(value)
        )
        rendered = re.sub(r"{{\s*" + re.escape(token) + r"\s*}}", replacement, rendered)
    return rendered


def _comp_names(item: Any) -> list[str]:
    from . import clip_ops

    return clip_ops._fusion_comp_name_list(item)


def _exact_comp_state(item: Any) -> dict[str, Any]:
    from . import color_ops

    count_getter = getattr(item, "GetFusionCompCount", None)
    names_getter = getattr(item, "GetFusionCompNameList", None)
    if not callable(count_getter) or not callable(names_getter):
        raise EffectVerificationFailed(
            "Exact Fusion composition state readback is unavailable."
        )
    try:
        raw_count = count_getter()
        raw_names = names_getter()
        count = int(raw_count)
    except Exception as exc:
        raise EffectVerificationFailed(
            "Exact Fusion composition state readback failed.",
            details={"error": str(exc)},
        ) from exc
    if count < 0 or not isinstance(raw_names, (list, tuple, dict)):
        raise EffectVerificationFailed(
            "Exact Fusion composition state readback is malformed.",
            details={"count": raw_count, "names_type": type(raw_names).__name__},
        )
    names = _comp_names(item)
    if len(names) != count:
        raise EffectVerificationFailed(
            "Fusion composition count and name readback disagree.",
            details={"count": count, "names": names},
        )
    graphs: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        try:
            comp = item.GetFusionCompByIndex(index)
        except Exception as exc:
            raise EffectVerificationFailed(
                "Exact Fusion composition graph readback failed.",
                details={"comp_index": index, "error": str(exc)},
            ) from exc
        if comp is None:
            raise EffectVerificationFailed(
                "Exact Fusion composition graph readback returned no composition.",
                details={"comp_index": index},
            )
        graph = color_ops._snapshot_comp_graph(comp)
        if (
            not isinstance(graph, dict)
            or not isinstance(graph.get("tools"), dict)
            or not graph["tools"]
        ):
            raise EffectVerificationFailed(
                "Exact Fusion composition graph readback is incomplete.",
                details={"comp_index": index},
            )
        graphs.append(graph)
    return {"count": count, "names": names, "graphs": graphs}


def _fusion_comp_at(item: Any, index: int) -> Any:
    for candidate in (index, index - 1, 0, 1):
        if candidate < 0:
            continue
        try:
            comp = item.GetFusionCompByIndex(candidate)
        except Exception:
            comp = None
        if comp:
            return comp
    raise EffectVerificationFailed(
        "Imported Fusion composition could not be read back.",
        details={"comp_index": index},
    )


def _inspect_template_comp(
    comp: Any, manifest: dict[str, Any], params: dict[str, Any]
) -> dict[str, Any]:
    from . import color_ops

    rows = color_ops._list_comp_tools(comp)
    actual_effect_tools = sorted(
        (str(row.get("name")), str(row.get("type")))
        for row in rows
        if row.get("type") not in {"MediaIn", "MediaOut"}
    )
    expected_effect_tools = sorted(
        (str(row["name"]), str(row["type"])) for row in manifest["expected_tools"]
    )
    if actual_effect_tools != expected_effect_tools:
        raise EffectVerificationFailed(
            "Imported template contains undeclared or missing effect tools.",
            details={
                "expected_tools": expected_effect_tools,
                "actual_tools": actual_effect_tools,
            },
        )
    media_in, media_out = color_ops._find_media_io(comp)
    chain = color_ops._main_chain(media_out, media_in)
    chain_names = [_tool_name(tool) for tool in chain]
    expected_checks: list[dict[str, Any]] = []
    for expected in manifest["expected_tools"]:
        matches = [
            row
            for row in rows
            if row.get("name") == expected["name"]
            and row.get("type") == expected["type"]
        ]
        check = {
            "name": expected["name"],
            "type": expected["type"],
            "count": len(matches),
            "in_main_chain": expected["name"] in chain_names,
        }
        expected_checks.append(check)
        if check["count"] != 1 or not check["in_main_chain"]:
            raise EffectVerificationFailed(
                "Imported template tool identity/topology does not match its reviewed manifest.",
                details={"tool_check": check, "tools": rows, "main_chain": chain_names},
            )
    expected_chain = [row["name"] for row in reversed(manifest["expected_tools"])] + [
        _tool_name(media_in)
    ]
    if chain_names != expected_chain:
        raise EffectVerificationFailed(
            "Imported template main image pipe order does not match its reviewed manifest.",
            details={
                "expected_main_chain": expected_chain,
                "actual_main_chain": chain_names,
            },
        )
    if media_in is None or media_out is None or _tool_name(media_in) not in chain_names:
        raise EffectVerificationFailed(
            "Imported template main image pipe does not connect MediaIn to MediaOut.",
            details={"main_chain": chain_names},
        )
    parameter_checks: list[dict[str, Any]] = []
    for parameter, expected in params.items():
        schema = manifest["parameters"][parameter]
        tool = color_ops._find_tool_by_name(comp, schema["tool_name"])
        getter = getattr(tool, "GetInput", None) if tool is not None else None
        try:
            actual = getter(schema["input_id"]) if callable(getter) else None
        except Exception as exc:
            raise EffectVerificationFailed(
                "Imported template parameter readback raised an error.",
                details={"parameter": parameter, "error": str(exc)},
            ) from exc
        check = {
            "name": "parameter_readback",
            "parameter": parameter,
            "tool_name": schema["tool_name"],
            "input_id": schema["input_id"],
            "expected": expected,
            "actual": actual,
            "ok": _same_value(expected, actual),
        }
        parameter_checks.append(check)
        if not check["ok"]:
            raise EffectVerificationFailed(
                "Imported template parameter did not survive exact native readback.",
                details={"check": check},
            )
    return {
        "expected_tools": expected_checks,
        "parameter_checks": parameter_checks,
        "main_chain": chain_names,
    }


def _apply_template(
    conn: Any,
    target: TimelineItemTarget,
    request: dict[str, Any],
    proof: RenderMutationProof,
) -> dict[str, Any]:
    path, manifest = request["path"], request["manifest"]
    before_count = _comp_count(target.item)
    before_names = _comp_names(target.item)
    if before_count != 0 or before_names:
        raise EffectVerificationFailed(
            "Reviewed custom templates require a target with no existing Fusion compositions.",
            details={
                "comp_count": before_count,
                "comp_names": before_names,
                "possible_mutation": False,
            },
        )
    rendered = _render_template(path, manifest, request["params"])
    before = proof.capture("before")
    target = getattr(proof, "target", target)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".setting", encoding="utf-8", delete=False
    ) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    imported_name: str | None = None
    try:
        revalidate_timeline_item_target(conn, target)
        importer = getattr(target.item, "ImportFusionComp", None)
        if (
            not callable(importer)
            or importer(str(temporary)) is False
            or _comp_count(target.item) <= before_count
        ):
            raise EffectVerificationFailed(
                "ImportFusionComp did not create a distinct reviewed composition."
            )
        after_names = _comp_names(target.item)
        added_names = [name for name in after_names if name not in before_names]
        if (
            len(after_names) != before_count + 1
            or len(added_names) != 1
            or len(after_names) != len(set(after_names))
        ):
            raise EffectVerificationFailed(
                "Imported Fusion composition identity is not exact and unique.",
                details={
                    "before_names": before_names,
                    "after_names": after_names,
                    "added_names": added_names,
                },
            )
        imported_name = added_names[0]
        comp = _fusion_comp_at(target.item, after_names.index(imported_name) + 1)
        structural = _inspect_template_comp(comp, manifest, request["params"])
        after = proof.capture("after")
        target = getattr(proof, "target", target)
        comparison = proof.compare(before, after)
        if not comparison["changed"]:
            raise EffectVerificationFailed(
                "Rendered pixels did not change after template import.",
                details={"comparison": comparison},
            )
    finally:
        temporary.unlink(missing_ok=True)
    try:
        restored = proof.restore_playhead()
    except Exception as exc:
        raise EffectVerificationFailed(
            "Original playhead could not be restored.", details={"error": str(exc)}
        ) from exc
    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "effect": {
            "id": manifest["effect_id"],
            "display_name": manifest["display_name"],
            "source": "template",
            "tool_type": None,
        },
        "target": target.public(),
        "parameters": request["params"],
        "template": {
            "path": str(path),
            "sha256": manifest["template_sha256"],
            "schema_version": 1,
            "imported_comp_name": imported_name,
        },
        "verification": {
            "status": "verified",
            "checks": [
                {"name": "exact_comp_identity", "ok": True, "comp_name": imported_name},
                {
                    "name": "expected_tool_identities_and_topology",
                    "ok": True,
                    **structural,
                },
                {"name": "rendered_pixel_change", "ok": True, **comparison},
            ],
            "render_proof": {
                "before": before,
                "after": after,
                "directory": str(proof.directory),
                "restored_playhead": restored,
            },
        },
    }


def _require_checkpoint_restore_available(
    conn: Any, checkpoint: dict[str, Any]
) -> None:
    manager = getattr(conn, "project_manager", None)
    missing = [
        name
        for name in ("CloseProject", "LoadProject")
        if not callable(getattr(manager, name, None))
    ]
    snapshot = Path(str(checkpoint.get("snapshot_path") or "")).expanduser()
    if (
        missing
        or checkpoint.get("database_type") != "Disk"
        or not checkpoint.get("state_hash")
        or not snapshot.is_file()
    ):
        raise EffectVerificationFailed(
            "Exact full-project rollback is unavailable; refusing to mutate the Fusion graph.",
            details={
                "missing_project_manager_apis": missing,
                "database_type": checkpoint.get("database_type"),
                "checkpoint_state_hash": checkpoint.get("state_hash"),
                "checkpoint_snapshot_available": snapshot.is_file(),
                "possible_mutation": False,
            },
        )


def _same_target_identity(before: dict[str, Any], after: dict[str, Any]) -> bool:
    keys = (
        "timeline_id",
        "timeline_item_id",
        "track_type",
        "track_index",
        "name",
        "start",
        "end",
    )
    return all(before.get(key) == after.get(key) for key in keys)


def _restore_effect_checkpoint(
    conn: Any,
    checkpoint: dict[str, Any],
    *,
    clip_name: str | None,
    item_id: str | None,
    track: int | None,
    record_frame: str | int | None,
    before_target: dict[str, Any],
    before_comp_state: dict[str, Any],
) -> dict[str, Any]:
    rollback: dict[str, Any] = {
        "available": True,
        "attempted": True,
        "verified": False,
        "mode": "full_disk_project_checkpoint",
        "checkpoint_id": checkpoint.get("id"),
        "expected_state_hash": checkpoint.get("state_hash"),
    }
    try:
        rollback["restore"] = version_ops.restore_checkpoint(
            conn,
            str(checkpoint["id"]),
            expected_checkpoint_digest=version_ops.checkpoint_binding_digest(
                checkpoint
            ),
        )
        fresh_conn = ResolveConnection.get()
        fresh_conn.refresh()
        status = version_ops.version_status(fresh_conn, include_private_identity=True)
        restored_target = resolve_timeline_item_target(
            fresh_conn,
            clip_name,
            item_id=item_id,
            track=track,
            record_frame=record_frame,
        )
        restored_comp_state = _exact_comp_state(restored_target.item)
        rollback.update(
            {
                "actual_state_hash": status.get("state_hash"),
                "state_hash_verified": status.get("state_hash")
                == checkpoint.get("state_hash"),
                "restored_target": restored_target.public(),
                "target_verified": _same_target_identity(
                    before_target, restored_target.public()
                ),
                "expected_comp_state": before_comp_state,
                "restored_comp_state": restored_comp_state,
                "composition_state_verified": restored_comp_state == before_comp_state,
                "zero_comp_verified": before_comp_state
                == {"count": 0, "names": [], "graphs": []}
                and restored_comp_state == before_comp_state,
            }
        )
        rollback["verified"] = bool(
            rollback["restore"].get("verified")
            and rollback["state_hash_verified"]
            and rollback["target_verified"]
            and rollback["composition_state_verified"]
        )
    except Exception as exc:
        rollback["error"] = str(exc)
        rollback["error_details"] = dict(getattr(exc, "details", {}) or {})
    return rollback


def add_fx_via_template(
    conn: Any,
    name: str,
    *,
    clip_name: Optional[str] = None,
    template_path: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    verify: bool = True,
    item_id: str | None = None,
    track: int | None = None,
    record_frame: str | int | None = None,
    proof_dir: str | None = None,
) -> dict[str, Any]:
    """Apply one reviewed effect to one exact target with structural and rendered proof."""
    if not verify:
        raise ValidationError(
            "Consequential effect mutations require --verify.",
            recoverability="not_applicable",
        )
    request = validate_effect_request(name, template_path=template_path, params=params)
    target = resolve_timeline_item_target(
        conn, clip_name, item_id=item_id, track=track, record_frame=record_frame
    )
    before_target = target.public()
    before_comp_state = _exact_comp_state(target.item)
    checkpoint = version_ops.create_checkpoint(
        conn,
        label=f"Effect recovery: {request['spec']['id']}",
        kind="before_prompt",
    )
    _require_checkpoint_restore_available(conn, checkpoint)
    try:
        proof = RenderMutationProof(conn, target, proof_dir)
        result = (
            _apply_builtin(conn, target, request, proof)
            if request["path"] is None
            else _apply_template(conn, target, request, proof)
        )
    except Exception as exc:
        rollback = _restore_effect_checkpoint(
            conn,
            checkpoint,
            clip_name=clip_name,
            item_id=item_id,
            track=track,
            record_frame=record_frame,
            before_target=before_target,
            before_comp_state=before_comp_state,
        )
        raise _failure(exc, target, rollback) from exc
    result["rollback"] = {
        "available": True,
        "mode": "full_disk_project_checkpoint",
        "checkpoint_id": checkpoint["id"],
        "state_hash": checkpoint["state_hash"],
    }
    return result
