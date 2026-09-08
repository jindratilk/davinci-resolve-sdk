"""Local DaVinci Resolve SDK/developer tooling helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Iterable, Optional

from ..errors import ValidationError

DEVELOPER_ROOT = Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer")

DOC_SECTIONS = {
    "scripting": ("Scripting/README.txt", "Scripting/CHANGELOG.txt"),
    "workflow": ("Workflow Integrations/README.txt", "Workflow Integrations/CHANGELOG.txt"),
    "dctl": ("DaVinciCTL/README.txt",),
    "lut": ("LUT/README.txt",),
    "fusion-template": ("Fusion Templates/README.txt",),
    "fuse": ("Fusion Fuse/Fuse Read Me.txt", "Fusion Fuse/Fusion Fuse SDK.pdf"),
    "openfx": ("OpenFX/README.txt",),
    "codec": ("CodecPlugin/README.txt",),
}

SCRIPT_PAGES = ("Utility", "Edit", "Color", "Deliver", "Fusion")


def _home_app_support() -> Path:
    return Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve"


def _system_app_support() -> Path:
    return Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve")


def _not_available(feature: str, reason: str, **fields: Any) -> dict[str, Any]:
    payload = {"status": "not_available", "feature": feature, "reason": reason}
    payload.update(fields)
    return payload


def not_available(feature: str, reason: str, **fields: Any) -> dict[str, Any]:
    """Public helper for SDK commands that intentionally report diagnostics only."""
    return _not_available(feature, reason, **fields)


def _safe_child_path(root: Path, name: str, *, label: str) -> Path:
    candidate_name = Path(name).expanduser()
    if candidate_name.is_absolute():
        raise ValidationError(f"{label} must be relative to the DaVinci Resolve support folder.", details={label: name})
    root_resolved = root.expanduser().resolve()
    candidate = (root_resolved / candidate_name).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValidationError(
            f"{label} escapes the DaVinci Resolve support folder.",
            details={label: name, "root": str(root_resolved), "resolved": str(candidate)},
        ) from exc
    return candidate


def _existing_conflict(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValidationError(
            "Destination already exists.",
            details={"path": str(path), "required_option": "--overwrite"},
        )


def _remove_existing(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _planned_file_operation(operation: str, *, dry_run: bool, **fields: Any) -> dict[str, Any]:
    return {"operation": operation, "dry_run": dry_run, **fields}


def _copy_path(
    source: Path,
    dest: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
    into_existing_dir: bool = False,
) -> dict[str, Any]:
    """Copy a file/folder to an exact destination, or into an existing directory when requested."""
    source = source.expanduser()
    dest = dest.expanduser()
    if not source.exists():
        raise ValidationError("Source path does not exist.", details={"source": str(source)})
    if source.is_dir():
        if dest.exists() and dest.is_file():
            raise ValidationError("Destination is a file; expected directory path.", details={"destination": str(dest)})
        target = dest / source.name if into_existing_dir and dest.exists() and dest.is_dir() else dest
        existed = target.exists()
        _existing_conflict(target, overwrite=overwrite)
        if dry_run:
            return _planned_file_operation(
                "copy_directory",
                dry_run=True,
                source=str(source),
                destination=str(target),
                would_overwrite=existed,
                overwrite=overwrite,
            )
        if existed:
            _remove_existing(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    else:
        if dest.exists() and dest.is_dir() and not into_existing_dir:
            raise ValidationError("Destination is a directory; expected file path.", details={"destination": str(dest)})
        target = dest / source.name if into_existing_dir and dest.exists() and dest.is_dir() else dest
        existed = target.exists()
        _existing_conflict(target, overwrite=overwrite)
        if dry_run:
            return _planned_file_operation(
                "copy_file",
                dry_run=True,
                source=str(source),
                destination=str(target),
                would_overwrite=existed,
                overwrite=overwrite,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            _remove_existing(target)
        shutil.copy2(source, target)
    return {"source": str(source), "destination": str(target), "installed": True, "overwritten": existed}


def _list_files(root: Path, patterns: Iterable[str]) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if path.is_file():
                rows.append({"name": path.name, "path": str(path), "relative_path": str(path.relative_to(root))})
    return rows


def _write_text_file(path: Path, text: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    path = path.expanduser()
    existed = path.exists()
    _existing_conflict(path, overwrite=overwrite)
    if dry_run:
        return _planned_file_operation(
            "write_file",
            dry_run=True,
            path=str(path),
            would_overwrite=existed,
            overwrite=overwrite,
            bytes=len(text.encode("utf-8")),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "created": True, "overwritten": existed}


def _write_scaffold(root: Path, files: dict[str, str], *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    root = root.expanduser()
    if root.exists() and not root.is_dir():
        raise ValidationError("Scaffold destination is a file; expected directory path.", details={"path": str(root)})
    file_paths = [root / rel_path for rel_path in files]
    conflicts = [str(path) for path in file_paths if path.exists()]
    if conflicts and not overwrite:
        raise ValidationError(
            "Scaffold destination already contains generated file(s).",
            details={"path": str(root), "conflicts": conflicts, "required_option": "--overwrite"},
        )
    if dry_run:
        return _planned_file_operation(
            "scaffold",
            dry_run=True,
            path=str(root),
            files=[str(path) for path in file_paths],
            would_overwrite=conflicts,
            overwrite=overwrite,
        )
    root.mkdir(parents=True, exist_ok=True)
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return {"path": str(root), "files": [str(path) for path in file_paths], "created": True, "overwritten": conflicts}


def _package_zip(source: Path, output: Path, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    source = source.expanduser()
    output = output.expanduser()
    if not source.exists():
        raise ValidationError("Package source does not exist.", details={"source": str(source)})
    if source.resolve() == output.resolve():
        raise ValidationError("Package output must be different from the source path.", details={"source": str(source), "output": str(output)})
    existed = output.exists()
    _existing_conflict(output, overwrite=overwrite)
    if dry_run:
        return _planned_file_operation(
            "package_zip",
            dry_run=True,
            source=str(source),
            output=str(output),
            would_overwrite=existed,
            overwrite=overwrite,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if existed:
        _remove_existing(output)
    output_resolved = output.resolve()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if source.is_file():
            archive.write(source, arcname=source.name)
        else:
            for path in source.rglob("*"):
                if path.is_file() and path.resolve() != output_resolved:
                    archive.write(path, arcname=str(path.relative_to(source.parent)))
    return {"source": str(source), "output": str(output), "packaged": True, "overwritten": existed}


def package_path(path: str, output: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Package a file or folder into a zip-compatible archive."""
    return _package_zip(Path(path).expanduser(), Path(output).expanduser(), dry_run=dry_run, overwrite=overwrite)


def list_developer_docs(root: Path = DEVELOPER_ROOT) -> list[dict[str, Any]]:
    """List known DaVinci Resolve Developer documentation files."""
    rows: list[dict[str, Any]] = []
    for section, rel_paths in DOC_SECTIONS.items():
        for rel_path in rel_paths:
            path = root / rel_path
            rows.append({"section": section, "path": str(path), "exists": path.exists()})
    return rows


def developer_doc(section: str, root: Path = DEVELOPER_ROOT) -> dict[str, Any]:
    """Return the local documentation path for a developer docs section."""
    key = section.strip().lower()
    if key not in DOC_SECTIONS:
        raise ValidationError("Unknown developer docs section.", details={"section": section, "allowed": sorted(DOC_SECTIONS)})
    paths = [root / rel_path for rel_path in DOC_SECTIONS[key]]
    existing = [path for path in paths if path.exists()]
    return {
        "section": key,
        "paths": [str(path) for path in paths],
        "existing_paths": [str(path) for path in existing],
        "exists": bool(existing),
        "open_command": f"open {json.dumps(str(existing[0] if existing else paths[0]))}",
    }


def open_developer_doc(section: str, root: Path = DEVELOPER_ROOT, *, dry_run: bool = False) -> dict[str, Any]:
    """Open a local DaVinci Resolve Developer documentation section with macOS open."""
    doc = developer_doc(section, root)
    target = doc["existing_paths"][0] if doc["existing_paths"] else doc["paths"][0]
    if dry_run:
        doc.update({"opened": False, "dry_run": True, "would_open": str(target)})
        return doc
    if not Path(target).exists():
        doc.update({"opened": False, "status": "not_found"})
        return doc
    result = subprocess.run(["open", target], capture_output=True, text=True, check=False)
    doc.update({"opened": result.returncode == 0, "returncode": result.returncode, "stderr": result.stderr})
    return doc


def list_examples(section: Optional[str] = None, root: Path = DEVELOPER_ROOT) -> list[dict[str, Any]]:
    """List local DaVinci Resolve Developer examples."""
    section_map = {
        "scripting": root / "Scripting" / "Examples",
        "workflow": root / "Workflow Integrations",
        "dctl": root / "DaVinciCTL",
        "fusion-template": root / "Fusion Templates",
        "fuse": root / "Fusion Fuse",
        "openfx": root / "OpenFX",
        "codec": root / "CodecPlugin",
    }
    keys = [section.strip().lower()] if section else sorted(section_map)
    rows: list[dict[str, Any]] = []
    for key in keys:
        example_root = section_map.get(key)
        if example_root is None:
            raise ValidationError("Unknown developer example section.", details={"section": section, "allowed": sorted(section_map)})
        if not example_root.exists():
            continue
        for path in sorted(example_root.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                rows.append({"section": key, "name": path.name, "path": str(path), "relative_path": str(path.relative_to(example_root))})
    return rows


def copy_example(
    section: str,
    name: str,
    dest: str,
    root: Path = DEVELOPER_ROOT,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Copy one named SDK example to a destination path."""
    matches = [row for row in list_examples(section, root) if row["name"] == name or row["relative_path"] == name]
    if not matches:
        raise ValidationError("SDK example not found.", details={"section": section, "name": name})
    return _copy_path(
        Path(matches[0]["path"]),
        Path(dest).expanduser(),
        dry_run=dry_run,
        overwrite=overwrite,
        into_existing_dir=True,
    )


def sdk_doctor(root: Path = DEVELOPER_ROOT) -> dict[str, Any]:
    """Inspect local DaVinci Resolve Developer SDK availability."""
    tools = {name: shutil.which(name) for name in ("node", "npm", "python3", "cmake", "make", "xcodebuild")}
    return {
        "developer_root": str(root),
        "developer_root_exists": root.exists(),
        "docs": list_developer_docs(root),
        "toolchain": tools,
        "user_support_root": str(_home_app_support()),
    }


def capability_audit() -> dict[str, Any]:
    """Return a command/capability parity summary."""
    from ..command_catalog import catalog_metadata_redacted, get_command_catalog
    from ..capabilities import get_capabilities

    commands = get_command_catalog()
    feature_graph = get_capabilities().get("feature_graph", {})
    engine_metadata_redacted = catalog_metadata_redacted()
    command_capabilities = {cmd.capability_id for cmd in commands if cmd.capability_id}
    commands_missing_capability_metadata = [
        {
            "path": cmd.path,
            "command_id": cmd.command_id,
            "capability_id": cmd.capability_id,
            "status": cmd.capability_status,
            "engine": cmd.engine,
        }
        for cmd in commands
        if (
            not cmd.capability_id
            or not cmd.capability_status
            or (not engine_metadata_redacted and not cmd.engine)
        )
    ]
    commands_with_full_capability_metadata = len(commands) - len(commands_missing_capability_metadata)
    return {
        "status": "ok" if not commands_missing_capability_metadata else "gaps_found",
        "command_count": len(commands),
        "capability_count": len(feature_graph),
        "commands_with_capabilities": sum(1 for cmd in commands if cmd.capability_id),
        "commands_with_full_capability_metadata": commands_with_full_capability_metadata,
        "engine_metadata_redacted": engine_metadata_redacted,
        "commands_missing_capability_metadata_count": len(commands_missing_capability_metadata),
        "commands_missing_capability_metadata": commands_missing_capability_metadata,
        "capabilities_without_direct_command_hint": sorted(set(feature_graph) - command_capabilities),
    }


def capability_diff() -> dict[str, Any]:
    """Return a compact diff between the source command catalog and capability graph."""
    audit = capability_audit()
    return {"status": audit["status"], "diff": audit}


def script_env() -> dict[str, Any]:
    """Describe DaVinci Resolve scripting environment variables and search paths."""
    roots = [
        _home_app_support() / "Fusion" / "Scripts",
        _system_app_support() / "Fusion" / "Scripts",
        DEVELOPER_ROOT / "Scripting" / "Modules",
    ]
    return {
        "RESOLVE_SCRIPT_API": os.environ.get("RESOLVE_SCRIPT_API"),
        "RESOLVE_SCRIPT_LIB": os.environ.get("RESOLVE_SCRIPT_LIB"),
        "PYTHONPATH": os.environ.get("PYTHONPATH"),
        "script_roots": [{"path": str(path), "exists": path.exists()} for path in roots],
    }


def _script_page_dir(page: str, *, all_users: bool = False) -> Path:
    page_name = page.strip()
    if page_name not in SCRIPT_PAGES:
        raise ValidationError("Unknown DaVinci Resolve script page.", details={"page": page, "allowed": list(SCRIPT_PAGES)})
    root = _system_app_support() if all_users else _home_app_support()
    return root / "Fusion" / "Scripts" / page_name


def list_scripts() -> list[dict[str, Any]]:
    """List installed DaVinci Resolve scripts in known page directories."""
    rows: list[dict[str, Any]] = []
    for scope, all_users in (("user", False), ("all_users", True)):
        for page in SCRIPT_PAGES:
            root = _script_page_dir(page, all_users=all_users)
            for item in _list_files(root, ("*.py", "*.lua")):
                rows.append({"scope": scope, "page": page, **item})
    return rows


def install_script(
    path: str,
    page: str = "Utility",
    name: Optional[str] = None,
    *,
    all_users: bool = False,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Install a DaVinci Resolve script into a page directory."""
    source = Path(path).expanduser()
    target_dir = _script_page_dir(page, all_users=all_users)
    target_name = name or source.name
    return _copy_path(source, target_dir / target_name, dry_run=dry_run, overwrite=overwrite)


def uninstall_script(name: str, page: str, *, all_users: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Remove an installed DaVinci Resolve script by file name."""
    target = _safe_child_path(_script_page_dir(page, all_users=all_users), name, label="name")
    if not target.exists():
        return {"path": str(target), "removed": False, "status": "not_found"}
    if dry_run:
        return _planned_file_operation("remove", dry_run=True, path=str(target), would_remove=True)
    target.unlink()
    return {"path": str(target), "removed": True}


def run_script(path: str, args: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    """Run a local helper script outside DaVinci Resolve."""
    script = Path(path).expanduser()
    if not script.is_file():
        raise ValidationError("Script path does not exist.", details={"path": str(script)})
    if script.suffix == ".py":
        command = [shutil.which("python3") or "python3", str(script), *args]
    elif script.suffix == ".lua":
        lua = shutil.which("lua")
        if not lua:
            return _not_available("script.run", "Lua runtime was not found on PATH.", required_manual_step="Install Lua or run the script inside DaVinci Resolve.", path=str(script))
        command = [lua, str(script), *args]
    else:
        command = [str(script), *args]
    if dry_run:
        return _planned_file_operation("run_script", dry_run=True, command=command, would_run=True)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def validate_dctl(path: str) -> dict[str, Any]:
    """Validate a DCTL file using lightweight static checks."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValidationError("DCTL file does not exist.", details={"path": str(source)})
    text = source.read_text(encoding="utf-8", errors="replace")
    has_transform = "__DEVICE__" in text or "transform(" in text or "DEFINE_DCTL_ALPHA_MODE" in text
    return {"path": str(source), "valid": source.suffix.lower() == ".dctl" and has_transform, "size_bytes": source.stat().st_size}


def scaffold_dctl(
    kind: str,
    name: str,
    output: Optional[str] = None,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a minimal DCTL source file."""
    allowed = {"transform", "transition", "aces-idt", "aces-odt"}
    if kind not in allowed:
        raise ValidationError("Unknown DCTL scaffold kind.", details={"kind": kind, "allowed": sorted(allowed)})
    target = Path(output or f"{name}.dctl").expanduser()
    template = f"""// {name} ({kind}) generated by CutAgent CLI
__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, float p_R, float p_G, float p_B)
{{
    return make_float3(p_R, p_G, p_B);
}}
"""
    return _write_text_file(target, template, dry_run=dry_run, overwrite=overwrite)


def _dctl_install_root(kind: str) -> Path:
    if kind == "aces-idt":
        return _home_app_support() / "ACES Transforms" / "IDT"
    if kind == "aces-odt":
        return _home_app_support() / "ACES Transforms" / "ODT"
    return _home_app_support() / "LUT"


def install_dctl(path: str, kind: str = "lut", *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a DCTL file into the user DaVinci Resolve support tree."""
    return _copy_path(Path(path).expanduser(), _dctl_install_root(kind) / Path(path).name, dry_run=dry_run, overwrite=overwrite)


def list_dctl() -> list[dict[str, Any]]:
    """List DCTL files from user and SDK roots."""
    rows = []
    for root in (_home_app_support() / "LUT", DEVELOPER_ROOT / "DaVinciCTL"):
        for item in _list_files(root, ("*.dctl",)):
            rows.append({"root": str(root), **item})
    return rows


def validate_lut(path: str) -> dict[str, Any]:
    """Validate a .cube LUT header."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValidationError("LUT file does not exist.", details={"path": str(source)})
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    size_line = next((line for line in lines if line.strip().startswith("LUT_3D_SIZE")), None)
    return {"path": str(source), "valid": source.suffix.lower() == ".cube" and bool(size_line), "size_line": size_line}


def inspect_lut(path: str) -> dict[str, Any]:
    """Inspect a .cube LUT."""
    data = validate_lut(path)
    source = Path(path).expanduser()
    entries = 0
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped[0].isdigit():
            entries += 1
    data["entries"] = entries
    return data


def install_lut(path: str, folder: Optional[str] = None, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a LUT into the user DaVinci Resolve LUT folder."""
    target_dir = _home_app_support() / "LUT"
    if folder:
        target_dir = _safe_child_path(target_dir, folder, label="folder")
    return _copy_path(Path(path).expanduser(), target_dir / Path(path).name, dry_run=dry_run, overwrite=overwrite)


def list_luts(resolve: bool = False) -> list[dict[str, Any]]:
    """List LUT files from user support and optionally SDK roots."""
    roots = [_home_app_support() / "LUT"]
    if resolve:
        roots.extend([_system_app_support() / "LUT", DEVELOPER_ROOT / "LUT"])
    rows = []
    for root in roots:
        for item in _list_files(root, ("*.cube", "*.dctl")):
            rows.append({"root": str(root), **item})
    return rows


def remove_lut(name: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Remove a user-installed LUT by relative path or file name."""
    root = _home_app_support() / "LUT"
    candidates = [_safe_child_path(root, name, label="name")]
    if root.exists() and Path(name).name == name:
        candidates.extend(path for path in root.rglob("*") if path.is_file() and path.name == name)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            if dry_run:
                return _planned_file_operation("remove", dry_run=True, name=name, path=str(candidate), would_remove=True)
            candidate.unlink()
            return {"name": name, "path": str(candidate), "removed": True}
    return {"name": name, "removed": False, "status": "not_found"}


def generate_identity_lut(size: int, output: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Generate an identity .cube LUT."""
    from . import lut_generator

    if size < 2:
        raise ValidationError("LUT size must be at least 2.", details={"size": size})
    target = Path(output).expanduser()
    _existing_conflict(target, overwrite=overwrite)
    if dry_run:
        return _planned_file_operation("generate_identity_lut", dry_run=True, path=str(target), size=size, would_overwrite=target.exists(), overwrite=overwrite)
    path = lut_generator.generate_curves_lut(str(target), size=size)
    return {"path": path, "size": size, "generated": True}


def convert_lut(path: str, fmt: str) -> dict[str, Any]:
    """Return conversion diagnostics for LUT formats."""
    if fmt.lower() != "cube":
        return _not_available("lut.convert", "Only .cube passthrough is currently implemented.", requested_format=fmt)
    source = Path(path).expanduser()
    data = validate_lut(str(source))
    data["converted"] = False
    data["format"] = "cube"
    return data


def workflow_plugin_scaffold(
    plugin_id: str,
    name: str,
    output: Optional[str] = None,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a minimal workflow integration plugin folder."""
    root = Path(output or plugin_id).expanduser()
    manifest = {"id": plugin_id, "name": name, "version": "0.1.0", "main": "main.py"}
    data = _write_scaffold(
        root,
        {
            "manifest.json": json.dumps(manifest, indent=2) + "\n",
            "main.py": "def main():\n    return None\n",
        },
        dry_run=dry_run,
        overwrite=overwrite,
    )
    data.update({"id": plugin_id, "name": name})
    return data


def validate_workflow_plugin(path: str) -> dict[str, Any]:
    """Validate a workflow plugin folder."""
    root = Path(path).expanduser()
    manifest = root / "manifest.json"
    return {"path": str(root), "valid": root.is_dir() and manifest.is_file(), "manifest": str(manifest), "manifest_exists": manifest.is_file()}


def _workflow_plugin_root(all_users: bool = False) -> Path:
    return (_system_app_support() if all_users else _home_app_support()) / "Workflow Integration Plugins"


def install_workflow_plugin(path: str, *, all_users: bool = False, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a workflow plugin folder."""
    source = Path(path).expanduser()
    return _copy_path(source, _workflow_plugin_root(all_users) / source.name, dry_run=dry_run, overwrite=overwrite)


def uninstall_workflow_plugin(plugin_id: str, *, all_users: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Uninstall a workflow plugin by folder name."""
    target = _safe_child_path(_workflow_plugin_root(all_users), plugin_id, label="plugin_id")
    if not target.exists():
        return {"id": plugin_id, "removed": False, "status": "not_found", "path": str(target)}
    if dry_run:
        return _planned_file_operation("remove_directory", dry_run=True, id=plugin_id, path=str(target), would_remove=True)
    shutil.rmtree(target)
    return {"id": plugin_id, "removed": True, "path": str(target)}


def list_workflow_plugins() -> list[dict[str, Any]]:
    """List installed workflow plugins."""
    rows = []
    for scope, root in (("user", _workflow_plugin_root(False)), ("all_users", _workflow_plugin_root(True))):
        if root.exists():
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    rows.append({"scope": scope, "id": child.name, "path": str(child)})
    return rows


def workflow_plugin_info(path: str) -> dict[str, Any]:
    """Read workflow plugin manifest information."""
    root = Path(path).expanduser()
    manifest_path = root / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"path": str(root), "manifest_path": str(manifest_path), "manifest": manifest, "valid": bool(manifest)}


def node_check(path: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Check whether Node.js can parse a workflow JavaScript file."""
    node = shutil.which("node")
    if not node:
        return _not_available("workflow.node.check", "Node.js was not found on PATH.", path=str(Path(path).expanduser()))
    command = [node, "--check", str(Path(path).expanduser())]
    if dry_run:
        return _planned_file_operation("node_check", dry_run=True, command=command, would_run=True)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {"path": path, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "ok": result.returncode == 0}


def create_callback_script(kind: str, output: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Create a workflow callback script stub."""
    allowed = {"render-start", "render-stop", "resolve-quit"}
    if kind not in allowed:
        raise ValidationError("Unknown workflow callback kind.", details={"kind": kind, "allowed": sorted(allowed)})
    text = f"""// {kind} callback generated by CutAgent CLI
module.exports = async function callback(event) {{
  console.log("{kind}", event || {{}});
}};
"""
    return _write_text_file(Path(output).expanduser(), text, dry_run=dry_run, overwrite=overwrite)


def workflow_ui_scaffold(
    language: str,
    name: str,
    output: Optional[str] = None,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Scaffold a minimal workflow UI script."""
    root = Path(output or name).expanduser()
    suffix = "py" if language == "python" else "lua"
    body = "print('Workflow UI scaffold')\n"
    data = _write_scaffold(root, {f"{name}.{suffix}": body}, dry_run=dry_run, overwrite=overwrite)
    data.update({"script": str(root / f"{name}.{suffix}"), "language": language})
    return data


def fusion_template_scaffold(
    kind: str,
    name: str,
    output: Optional[str] = None,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a minimal Fusion .setting template."""
    allowed = {"title", "generator", "effect", "transition"}
    if kind not in allowed:
        raise ValidationError("Unknown Fusion template kind.", details={"kind": kind, "allowed": sorted(allowed)})
    path = Path(output or f"{name}.setting").expanduser()
    text = f"""{{ Tools = ordered() {{ {name} = TextPlus {{ Inputs = {{ StyledText = Input {{ Value = \"{name}\" }} }} }} }} }}\n"""
    return _write_text_file(path, text, dry_run=dry_run, overwrite=overwrite)


def validate_fusion_template(path: str) -> dict[str, Any]:
    """Validate a Fusion template file by extension/content."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValidationError("Fusion template path does not exist.", details={"path": str(source)})
    text = source.read_text(encoding="utf-8", errors="replace")
    return {"path": str(source), "valid": source.suffix == ".setting" and "Tools" in text}


def _fusion_template_root(kind: str) -> Path:
    mapping = {
        "title": "Titles",
        "generator": "Generators",
        "effect": "Effects",
        "transition": "Transitions",
    }
    folder = mapping.get(kind, kind)
    return _home_app_support() / "Fusion" / "Templates" / "Edit" / folder


def install_fusion_template(path: str, kind: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a Fusion template."""
    return _copy_path(Path(path).expanduser(), _fusion_template_root(kind) / Path(path).name, dry_run=dry_run, overwrite=overwrite)


def fusion_template_set_icon(template: str, png: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Place a PNG icon next to a Fusion template."""
    template_path = Path(template).expanduser()
    if not template_path.exists():
        found = None
        for kind in ("title", "generator", "effect", "transition"):
            candidate = _fusion_template_root(kind) / template
            if candidate.exists():
                found = candidate
                break
            if not str(template).endswith(".setting"):
                candidate = _fusion_template_root(kind) / f"{template}.setting"
                if candidate.exists():
                    found = candidate
                    break
        if found is None:
            raise ValidationError("Fusion template not found.", details={"template": template})
        template_path = found
    source = Path(png).expanduser()
    if source.suffix.lower() != ".png":
        raise ValidationError("Fusion template icons must be PNG files.", details={"png": str(source)})
    target = template_path.with_suffix(".png")
    return _copy_path(source, target, dry_run=dry_run, overwrite=overwrite)


def fusion_template_assets_list(template: str) -> dict[str, Any]:
    """List files in a template-adjacent asset folder."""
    template_path = Path(template).expanduser()
    asset_dir = template_path.with_suffix("") / "assets"
    assets = []
    if asset_dir.exists():
        assets = [{"name": path.name, "path": str(path)} for path in sorted(asset_dir.iterdir()) if path.is_file()]
    return {"template": str(template_path), "asset_dir": str(asset_dir), "assets": assets}


def fusion_template_assets_add(template: str, file: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Copy an asset into a template-adjacent asset folder."""
    template_path = Path(template).expanduser()
    asset_dir = template_path.with_suffix("") / "assets"
    source = Path(file).expanduser()
    return _copy_path(source, asset_dir / source.name, dry_run=dry_run, overwrite=overwrite)


def uninstall_fusion_template(name: str, kind: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Remove an installed Fusion template."""
    target = _safe_child_path(_fusion_template_root(kind), name, label="name")
    if not target.exists() and not name.endswith(".setting"):
        target = _safe_child_path(_fusion_template_root(kind), f"{name}.setting", label="name")
    if not target.exists():
        return {"name": name, "kind": kind, "removed": False, "status": "not_found"}
    if dry_run:
        return _planned_file_operation("remove", dry_run=True, name=name, kind=kind, path=str(target), would_remove=True)
    target.unlink()
    return {"name": name, "kind": kind, "path": str(target), "removed": True}


def _safe_zip_targets(archive: zipfile.ZipFile, dest: Path) -> list[tuple[zipfile.ZipInfo, Path]]:
    dest_resolved = dest.resolve()
    targets: list[tuple[zipfile.ZipInfo, Path]] = []
    for member in archive.infolist():
        target = (dest_resolved / member.filename).resolve()
        try:
            target.relative_to(dest_resolved)
        except ValueError as exc:
            raise ValidationError(
                "Archive member escapes the destination directory.",
                details={"member": member.filename, "destination": str(dest_resolved), "resolved": str(target)},
            ) from exc
        targets.append((member, target))
    return targets


def unpack_drfx(path: str, output: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Unpack a .drfx zip bundle."""
    source = Path(path).expanduser()
    dest = Path(output).expanduser()
    if not source.is_file():
        raise ValidationError("DRFX bundle does not exist.", details={"path": str(source)})
    with zipfile.ZipFile(source, "r") as archive:
        targets = _safe_zip_targets(archive, dest)
        conflicts = [str(target) for member, target in targets if not member.is_dir() and target.exists()]
        if conflicts and not overwrite:
            raise ValidationError(
                "Archive extraction would overwrite existing file(s).",
                details={"output": str(dest), "conflicts": conflicts, "required_option": "--overwrite"},
            )
        if dry_run:
            return _planned_file_operation(
                "unpack_drfx",
                dry_run=True,
                path=str(source),
                output=str(dest),
                members=[member.filename for member, _target in targets],
                would_overwrite=conflicts,
                overwrite=overwrite,
            )
        dest.mkdir(parents=True, exist_ok=True)
        archive.extractall(dest)
    return {"path": str(source), "output": str(dest), "unpacked": True, "overwritten": conflicts}


def package_drfx(path: str, output: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Package a Fusion template folder as a .drfx bundle."""
    return _package_zip(Path(path).expanduser(), Path(output).expanduser(), dry_run=dry_run, overwrite=overwrite)


def fuse_scaffold(name: str, output: Optional[str] = None, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Create a minimal Fusion Fuse file."""
    path = Path(output or f"{name}.fuse").expanduser()
    text = f"""FuRegisterClass(\"{name}\", CT_Tool, {{ REGS_Name = \"{name}\" }})\n"""
    return _write_text_file(path, text, dry_run=dry_run, overwrite=overwrite)


def validate_fuse(path: str) -> dict[str, Any]:
    """Validate a Fuse source file by lightweight checks."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValidationError("Fuse path does not exist.", details={"path": str(source)})
    text = source.read_text(encoding="utf-8", errors="replace")
    return {"path": str(source), "valid": source.suffix == ".fuse" and "FuRegisterClass" in text}


def _fuse_root() -> Path:
    return _home_app_support() / "Fusion" / "Fuses"


def install_fuse(path: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a Fuse file."""
    return _copy_path(Path(path).expanduser(), _fuse_root() / Path(path).name, dry_run=dry_run, overwrite=overwrite)


def uninstall_fuse(name: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Remove an installed Fuse file."""
    target = _safe_child_path(_fuse_root(), name, label="name")
    if not target.exists() and not name.endswith(".fuse"):
        target = _safe_child_path(_fuse_root(), f"{name}.fuse", label="name")
    if not target.exists():
        return {"name": name, "removed": False, "status": "not_found"}
    if dry_run:
        return _planned_file_operation("remove", dry_run=True, name=name, path=str(target), would_remove=True)
    target.unlink()
    return {"name": name, "path": str(target), "removed": True}


def list_fuses() -> list[dict[str, Any]]:
    """List user-installed Fuse files."""
    return _list_files(_fuse_root(), ("*.fuse",))


def fuse_examples_list() -> list[dict[str, Any]]:
    """List SDK Fuse examples."""
    return _list_files(DEVELOPER_ROOT / "Fusion Fuse", ("*.fuse",))


def fuse_example_install(name: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a Fuse example by file name."""
    matches = [row for row in fuse_examples_list() if row["name"] == name]
    if not matches:
        raise ValidationError("Fuse example not found.", details={"name": name})
    return install_fuse(matches[0]["path"], dry_run=dry_run, overwrite=overwrite)


def generic_scaffold(
    kind: str,
    name: str,
    output: Optional[str],
    extension: str,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a small generic SDK project/source scaffold."""
    root = Path(output or name).expanduser()
    data = _write_scaffold(
        root,
        {
            f"{name}.{extension}": f"// {kind} {name} generated by CutAgent CLI\n",
            "README.md": f"# {name}\n\nGenerated {kind} scaffold.\n",
        },
        dry_run=dry_run,
        overwrite=overwrite,
    )
    data.update({"kind": kind, "name": name})
    return data


def build_with_make(path: str, backend: Optional[str] = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Run make in a source directory when available."""
    source = Path(path).expanduser()
    make = shutil.which("make")
    if not make:
        return _not_available("sdk.build", "make was not found on PATH.", path=str(source), backend=backend)
    if not (source / "Makefile").exists():
        return _not_available("sdk.build", "No Makefile found in the source directory.", path=str(source), backend=backend)
    env = os.environ.copy()
    if backend:
        env["BACKEND"] = backend
    if dry_run:
        return _planned_file_operation("make", dry_run=True, path=str(source), backend=backend, command=[make], would_run=True)
    result = subprocess.run([make], cwd=source, capture_output=True, text=True, check=False, env=env)
    return {"path": str(source), "backend": backend, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "ok": result.returncode == 0}


def validate_bundle(path: str, suffixes: tuple[str, ...] = ()) -> dict[str, Any]:
    """Validate that a bundle/file exists and optionally has an expected suffix."""
    source = Path(path).expanduser()
    valid_suffix = not suffixes or source.suffix.lower() in suffixes
    return {"path": str(source), "exists": source.exists(), "valid": source.exists() and valid_suffix, "suffix": source.suffix}


def list_installed_bundles(root: Path, patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    """List installed plugin bundles under a root."""
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            rows.append({
                "name": path.name,
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "is_dir": path.is_dir(),
            })
    return rows


def _ofx_root() -> Path:
    return Path.home() / "Library" / "OFX" / "Plugins"


def ofx_scaffold(kind: str, name: str, output: Optional[str] = None, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Create a minimal OpenFX plugin scaffold."""
    if kind not in {"filter", "transition"}:
        raise ValidationError("Unknown OpenFX scaffold kind.", details={"kind": kind, "allowed": ["filter", "transition"]})
    return generic_scaffold(f"openfx-{kind}", name, output, "cpp", dry_run=dry_run, overwrite=overwrite)


def ofx_install(path_or_bundle: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install an OpenFX bundle into the user OFX Plugins folder."""
    source = Path(path_or_bundle).expanduser()
    return _copy_path(source, _ofx_root() / source.name, dry_run=dry_run, overwrite=overwrite)


def ofx_uninstall(plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Uninstall a user OpenFX bundle by folder/file name."""
    root = _ofx_root()
    candidates = [
        _safe_child_path(root, plugin_id, label="plugin_id"),
        _safe_child_path(root, f"{plugin_id}.ofx.bundle", label="plugin_id"),
        _safe_child_path(root, f"{plugin_id}.bundle", label="plugin_id"),
    ]
    for candidate in candidates:
        if candidate.exists():
            if dry_run:
                return _planned_file_operation("remove", dry_run=True, plugin_id=plugin_id, path=str(candidate), would_remove=True)
            if candidate.is_dir():
                shutil.rmtree(candidate)
            else:
                candidate.unlink()
            return {"plugin_id": plugin_id, "path": str(candidate), "removed": True}
    return {"plugin_id": plugin_id, "removed": False, "status": "not_found", "root": str(root)}


def ofx_list_installed() -> list[dict[str, Any]]:
    """List user-installed OpenFX bundles."""
    return list_installed_bundles(_ofx_root(), ("*.ofx.bundle", "*.bundle"))


def ofx_package(path: str, output: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Package an OpenFX project/bundle."""
    return package_path(path, output, dry_run=dry_run, overwrite=overwrite)


def ofx_sample_copy(name: str, dest: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Copy an OpenFX SDK sample from local Developer docs."""
    return copy_example("openfx", name, dest, dry_run=dry_run, overwrite=overwrite)


def _codec_root() -> Path:
    return _home_app_support() / "IOPlugins"


def codec_scaffold(kind: str, name: str, output: Optional[str] = None, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Create a minimal codec plugin scaffold."""
    if kind != "encoder":
        raise ValidationError("Unknown codec scaffold kind.", details={"kind": kind, "allowed": ["encoder"]})
    return generic_scaffold("codec-encoder", name, output, "cpp", dry_run=dry_run, overwrite=overwrite)


def codec_install(bundle: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Install a codec plugin bundle into the user DaVinci Resolve support folder."""
    source = Path(bundle).expanduser()
    return _copy_path(source, _codec_root() / source.name, dry_run=dry_run, overwrite=overwrite)


def codec_uninstall(name: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Uninstall a user codec plugin bundle."""
    root = _codec_root()
    candidates = [
        _safe_child_path(root, name, label="name"),
        _safe_child_path(root, f"{name}.bundle", label="name"),
        _safe_child_path(root, f"{name}.plugin", label="name"),
    ]
    for candidate in candidates:
        if candidate.exists():
            if dry_run:
                return _planned_file_operation("remove", dry_run=True, name=name, path=str(candidate), would_remove=True)
            if candidate.is_dir():
                shutil.rmtree(candidate)
            else:
                candidate.unlink()
            return {"name": name, "path": str(candidate), "removed": True}
    return {"name": name, "removed": False, "status": "not_found", "root": str(root)}


def codec_list_installed() -> list[dict[str, Any]]:
    """List user-installed codec plugin bundles."""
    return list_installed_bundles(_codec_root(), ("*.bundle", "*.plugin", "*.dylib"))


def codec_package(path: str, arch: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Package a codec plugin project for a target architecture label."""
    source = Path(path).expanduser()
    output = source.with_name(f"{source.name}-{arch}.zip")
    data = package_path(str(source), str(output), dry_run=dry_run, overwrite=overwrite)
    data["arch"] = arch
    return data


def codec_sample_copy(name: str, dest: str, *, dry_run: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Copy a codec SDK sample from local Developer docs."""
    if name.strip().lower() in {"x264", "x264-encoder", "x264_encoder", "x264_encoder_plugin"}:
        sample = DEVELOPER_ROOT / "CodecPlugin" / "Examples" / "x264_encoder_plugin"
        return _copy_path(sample, Path(dest).expanduser(), dry_run=dry_run, overwrite=overwrite)
    return copy_example("codec", name, dest, dry_run=dry_run, overwrite=overwrite)
