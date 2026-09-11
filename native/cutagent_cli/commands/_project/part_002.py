from __future__ import annotations

@preset_app.command("save")
@handle_errors
def preset_save(
    name: str = typer.Argument(..., help="Preset name"),
):
    """Save current project settings as preset when runtime supports it."""
    candidate_methods = list(SAVE_METHODS)
    enforce_mutation_policy("project.preset_save", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            mutation_payload(
                action="project.preset.save",
                target={"kind": "project_preset", "name": name},
                changed=False,
                candidate_methods=candidate_methods,
                runtime_method_checked=False,
                message=f"DRY-RUN: Would save project preset: {name}",
            )
        )
        return

    conn = get_connection(require_project=True)
    output(project_preset_api.save_project_preset(conn.project, name), title="Project Preset Save")


@preset_app.command("export")
@handle_errors
def preset_export(
    name: str = typer.Argument(..., help="Exact preset name"),
    path: str = typer.Argument(..., help="New export file path"),
):
    """Export one project-settings preset without replacing a file."""
    project_preset_api.requested_project_preset_name(name)
    enforce_mutation_policy("project.preset_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(action="project.preset.export", target={"kind": "project_preset", "name": name}, changed=False, path=path))
        return
    conn = get_connection(require_project=True)
    output(project_preset_api.export_project_preset(conn.project, name, path), title="Project Preset Export")


@preset_app.command("import")
@handle_errors
def preset_import(
    path: str = typer.Argument(..., help="Project preset file path"),
    name: str = typer.Option(..., "--name", help="Exact new preset name"),
):
    """Import one project-settings preset under an explicit new name."""
    project_preset_api.requested_project_preset_name(name)
    enforce_mutation_policy("project.preset_import", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(action="project.preset.import", target={"kind": "project_preset", "name": name}, changed=False, path=path))
        return
    conn = get_connection(require_project=True)
    output(project_preset_api.import_project_preset(conn.project, path, name), title="Project Preset Import")


@preset_app.command("delete")
@handle_errors
def preset_delete(
    name: str = typer.Argument(..., help="Exact preset name"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm deletion"),
):
    """Delete one exact project-settings preset with a private recovery backup."""
    project_preset_api.requested_project_preset_name(name)
    enforce_mutation_policy("project.preset_delete", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(action="project.preset.delete", target={"kind": "project_preset", "name": name}, changed=False))
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired("Machine-mode deletion requires --force.", details={"preset_name": name})
        if not typer.confirm(f"Delete project preset {name!r}?"):
            raise typer.Abort()
    conn = get_connection(require_project=True)
    output(project_preset_api.delete_project_preset(conn.project, name), title="Project Preset Delete")


@app.command("import")
@handle_errors
def import_project(
    path: str = typer.Argument(..., help="Path to .drp file"),
):
    """Import a project from file."""
    enforce_mutation_policy("project.import_drp", intended_engine="api_native")
    conn = get_connection(require_project=False)
    result = conn.project_manager.ImportProject(path)
    if result:
        conn.refresh()
        success(f"Imported project from: {path}")
    else:
        raise APICallFailed(f"Failed to import project from: {path}")


@app.command("export")
@handle_errors
def export_project(
    name: str = typer.Argument(..., help="Project name"),
    path: str = typer.Argument(..., help="Export path"),
    with_stills: bool = typer.Option(True, "--with-stills/--no-stills"),
):
    """Export a project to file."""
    export_path = _normalize_project_export_output_path(path)
    enforce_mutation_policy("project.export_drp", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=False)
    project_exists = _project_exists_in_current_folder(conn, name)
    current_project_matches = _current_project_name_matches(conn, name)
    if current_project_matches:
        project_exists = True
    if project_exists is False:
        raise ValidationError(
            f"Project '{name}' was not found in the current project folder.",
            details={"name": name, "export_path": export_path},
        )

    if is_dry_run():
        output(
            mutation_payload(
                action="project.export",
                target={"kind": "project", "name": name},
                changed=False,
                export_path=export_path,
                with_stills=with_stills,
                project_exists=project_exists,
                current_project_matches=current_project_matches,
                runtime_export_called=False,
                message=f"DRY-RUN: Would export project '{name}' to: {export_path}",
            )
        )
        return

    result = conn.project_manager.ExportProject(name, export_path, with_stills)
    artifact_path = _resolve_project_export_artifact_path(export_path)
    if result and artifact_path:
        set_verification_status("verified")
        output(
            mutation_payload(
                action="project.export",
                target={"kind": "project", "name": name},
                export_path=artifact_path,
                requested_path=export_path,
                with_stills=with_stills,
                verification_status="verified",
                message=f"Exported '{name}' to: {artifact_path}",
            )
        )
    elif result:
        raise APICallFailed(
            f"DaVinci Resolve reported a successful export for '{name}', but no .drp artifact was found.",
            details={
                "name": name,
                "export_path": export_path,
                "api_result": "export_file_missing",
            },
        )
    else:
        raise APICallFailed(f"Failed to export project '{name}'.")


# --- Folder management ---

folders_app = typer.Typer(help="Database folder management.")
app.add_typer(folders_app, name="folders")


@folders_app.command("list")
@handle_errors
def folders_list():
    """List folders in current database location."""
    conn = get_connection(require_project=False)
    folders = conn.project_manager.GetFolderListInCurrentFolder()
    projects = conn.project_manager.GetProjectListInCurrentFolder()
    current_folder = current_project_folder_name(conn)
    data = {
        "current_folder": current_folder or "",
        "current_path": project_folder_path_label(current_folder),
        "folders": folders or [],
        "projects": projects or [],
    }
    output(data, title="Current Folder")


@folders_app.command("create")
@handle_errors
def folders_create(name: str = typer.Argument(..., help="Folder name")):
    """Create a new folder."""
    enforce_mutation_policy("project.folder_management", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=False)
    exists_before = _folder_exists(conn, name)
    if is_dry_run():
        output(
            mutation_payload(
                action="project.folders.create",
                target={"kind": "folder", "name": name},
                changed=False,
                would_create=not exists_before,
                folder_exists=exists_before,
                runtime_create_called=False,
                message=(
                    f"DRY-RUN: Folder already exists: {name}"
                    if exists_before
                    else f"DRY-RUN: Would create folder: {name}"
                ),
            )
        )
        return

    result = conn.project_manager.CreateFolder(name)
    exists_after = _folder_exists(conn, name)
    if result or exists_after:
        set_verification_status("verified")
        output(
            mutation_payload(
                action="project.folders.create",
                target={"kind": "folder", "name": name},
                changed=bool(result),
                verification_status="verified",
                message=f"Created folder: {name}" if result else f"Folder already exists: {name}",
            )
        )
        return
    raise APICallFailed(f"Failed to create folder '{name}'.")


@folders_app.command("open")
@handle_errors
def folders_open(name: str = typer.Argument(..., help="Folder name")):
    """Open/navigate to a folder."""
    enforce_mutation_policy("project.folder_management", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=False)
    previous_folder = current_project_folder_name(conn)
    if is_dry_run():
        folder_exists = _folder_exists(conn, name)
        output(
            mutation_payload(
                action="project.folders.open",
                target={"kind": "folder", "name": name},
                changed=False,
                would_open=folder_exists,
                folder_exists=folder_exists,
                current_folder=previous_folder or "",
                current_path=project_folder_path_label(previous_folder),
                runtime_open_called=False,
                message=(
                    f"DRY-RUN: Would open folder: {name}"
                    if folder_exists
                    else f"DRY-RUN: Folder '{name}' not found."
                ),
            )
        )
        return

    result = conn.project_manager.OpenFolder(name)
    if result:
        current_folder = current_project_folder_name(conn)
        verified = current_folder == str(name)
        if verified:
            set_verification_status("verified")
        output(
            mutation_payload(
                action="project.folders.open",
                target={"kind": "folder", "name": name},
                changed=previous_folder != str(name),
                previous_folder=previous_folder or "",
                current_folder=current_folder or "",
                current_path=project_folder_path_label(current_folder),
                verification_status="verified" if verified else "not_requested",
                message=f"Opened folder: {name}",
            )
        )
    else:
        raise APICallFailed(f"Folder '{name}' not found.")


@folders_app.command("up")
@handle_errors
def folders_up():
    """Go to parent folder."""
    enforce_mutation_policy("project.folder_management", intended_engine="api_native")
    conn = get_connection(require_project=False)
    result = conn.project_manager.GotoParentFolder()
    if result:
        success("Moved to parent folder.")
    else:
        warning("Already at root or cannot go up.")


@folders_app.command("root")
@handle_errors
def folders_root():
    """Go to the root project database folder."""
    enforce_mutation_policy("project.folder_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message("Would navigate to the root project database folder.")
        return
    conn = get_connection(require_project=False)
    data = project_ops.goto_project_folder_root(conn)
    output(data, title="Project Folder Root")


@folders_app.command("delete")
@handle_errors
def folders_delete(
    name: str = typer.Argument(..., help="Folder name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a project database folder in the current folder."""
    enforce_mutation_policy("project.folder_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would delete project folder: {name}")
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode mutation requires --force.",
                details={"action": "project.folders.delete", "target_kind": "project_folder", "target_name": name},
            )
        typer.confirm(f"Delete project folder '{name}'?", abort=True)
    conn = get_connection(require_project=False)
    data = project_ops.delete_project_folder(conn, name)
    output(mutation_payload(action="project.folders.delete", target={"kind": "project_folder", "name": name}, **data))


cloud_app = typer.Typer(help="Cloud project operations.")
app.add_typer(cloud_app, name="cloud")


@cloud_app.command("create")
@handle_errors
def cloud_create(
    name: str = typer.Argument(..., help="Cloud project name"),
    media_path: Optional[str] = typer.Option(None, "--media-path", help="Cloud media path"),
    sync_mode: Optional[str] = typer.Option(None, "--sync-mode", help="Cloud sync mode"),
    collab: bool = typer.Option(False, "--collab", help="Enable collaboration when supported"),
):
    """Create a cloud project when the DaVinci Resolve runtime exposes that API."""
    enforce_mutation_policy("project.cloud.create", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would create cloud project: {name}")
        return
    conn = get_connection(require_project=False)
    output(project_ops.create_cloud_project(conn, name, media_path, sync_mode, collab), title="Cloud Project Create")


@cloud_app.command("open")
@handle_errors
def cloud_open(
    name: str = typer.Argument(..., help="Cloud project name"),
    media_path: Optional[str] = typer.Option(None, "--media-path", help="Cloud media path"),
    sync_mode: Optional[str] = typer.Option(None, "--sync-mode", help="Cloud sync mode"),
):
    """Open a cloud project when the DaVinci Resolve runtime exposes that API."""
    enforce_mutation_policy("project.cloud.open", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would open cloud project: {name}")
        return
    conn = get_connection(require_project=False)
    output(project_ops.open_cloud_project(conn, name, media_path, sync_mode), title="Cloud Project Open")


@cloud_app.command("import")
@handle_errors
def cloud_import(
    file_path: str = typer.Argument(..., help="Cloud project file"),
    name: Optional[str] = typer.Option(None, "--name", help="Imported project name"),
    media_path: Optional[str] = typer.Option(None, "--media-path", help="Cloud media path"),
):
    """Import a cloud project file when the DaVinci Resolve runtime exposes that API."""
    enforce_mutation_policy("project.cloud.import", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import cloud project file: {file_path}")
        return
    conn = get_connection(require_project=False)
    output(project_ops.import_cloud_project(conn, file_path, name, media_path), title="Cloud Project Import")


@cloud_app.command("restore")
@handle_errors
def cloud_restore(
    folder: str = typer.Argument(..., help="Cloud project backup folder"),
    name: Optional[str] = typer.Option(None, "--name", help="Restored project name"),
    media_path: Optional[str] = typer.Option(None, "--media-path", help="Cloud media path"),
):
    """Restore a cloud project folder when the DaVinci Resolve runtime exposes that API."""
    enforce_mutation_policy("project.cloud.restore", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would restore cloud project folder: {folder}")
        return
    conn = get_connection(require_project=False)
    output(project_ops.restore_cloud_project(conn, folder, name, media_path), title="Cloud Project Restore")


# --- Project Archive/Restore ---

@app.command("archive")
@handle_errors
def archive_project(
    name: str = typer.Argument(..., help="Project name"),
    path: str = typer.Argument(..., help="Archive path (directory)"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Actually call DaVinci Resolve archive API; machine mode requires this because DaVinci Resolve may show a confirmation modal.",
    ),
):
    """Archive a project to disk."""
    enforce_mutation_policy("project.archive_restore", intended_engine="api_native", mutating=not is_dry_run())
    archive_path = _normalize_archive_output_path(path)
    conn = get_connection(require_project=False)
    project_exists = _project_exists_in_current_folder(conn, name)
    if project_exists is False:
        raise ValidationError(
            f"Project '{name}' not found in the current database folder.",
            details={
                "project": name,
                "archive_path": archive_path,
            },
        )

    if is_dry_run():
        output(
            mutation_payload(
                action="project.archive",
                target={"kind": "project", "name": name},
                changed=False,
                archive_path=archive_path,
                archive_path_dra=archive_path if archive_path.lower().endswith(".dra") else f"{archive_path}.dra",
                project_exists=project_exists,
                message=f"DRY-RUN: Would archive '{name}' to: {archive_path}",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Project archive may show a DaVinci Resolve confirmation modal; rerun with --force to call the live archive API.",
                details={
                    "action": "project.archive",
                    "project": name,
                    "archive_path": archive_path,
                    "required_option": "--force",
                },
            )
        if not typer.confirm(
            f"Archive project '{name}' to '{archive_path}'? DaVinci Resolve may show a confirmation modal.",
            default=False,
        ):
            raise ConfirmationRequired(
                "Project archive cancelled.",
                details={
                    "action": "project.archive",
                    "project": name,
                    "archive_path": archive_path,
                    "required_option": "--force",
                },
            )

    result = conn.project_manager.ArchiveProject(name, archive_path)
    artifact_path = _resolve_archive_artifact_path(archive_path)
    if result or artifact_path:
        set_verification_status("verified")
        output(
            mutation_payload(
                action="project.archive",
                target={"kind": "project", "name": name},
                verification_status="verified",
                archive_path=artifact_path or archive_path,
                message=f"Archived '{name}' to: {artifact_path or archive_path}",
            )
        )
        return
    raise APICallFailed(f"Failed to archive project '{name}'.")


@app.command("restore")
@handle_errors
def restore_project(
    path: str = typer.Argument(..., help="Path to archived project file"),
):
    """Restore a project from archive."""
    enforce_mutation_policy("project.archive_restore", intended_engine="api_native")
    conn = get_connection(require_project=False)
    result = conn.project_manager.RestoreProject(path)
    if result:
        conn.refresh()
        success(f"Restored project from: {path}")
    else:
        raise APICallFailed(f"Failed to restore project from: {path}")


# --- Database management ---

db_app = typer.Typer(help="Database management.")
app.add_typer(db_app, name="db")


@db_app.command("list")
@handle_errors
def db_list():
    """List available databases."""
    conn = get_connection(require_project=False)
    dbs = conn.project_manager.GetDatabaseList()
    if not dbs:
        output([])
        return
    
    # GetDatabaseList returns list of dicts with keys: DbType, DbName, IpAddress
    rows = []
    for i, db in enumerate(dbs, 1):
        rows.append({
            "index": i,
            "type": db.get("DbType", ""),
            "name": db.get("DbName", ""),
            "ip": db.get("IpAddress", ""),
        })
    output(rows, columns=[("index", "#"), ("type", "Type"), ("name", "Name"), ("ip", "IP")], 
           title="Databases", quiet_key="name")


@db_app.command("current")
@handle_errors
def db_current():
    """Show current database."""
    conn = get_connection(require_project=False)
    try:
        db = get_current_database_details(conn)
    except APICallFailed:
        warning("Could not get current database.")
        return
    output(db, title="Current Database")


@db_app.command("switch")
@handle_errors
def db_switch(
    name: str = typer.Argument(..., help="Database name"),
    db_type: str = typer.Option("Disk", "--type", help="Database type (currently only Disk)"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Actually switch databases when the target differs from the current database.",
    ),
):
    """Switch to a different database."""
    enforce_mutation_policy("project.db_switch", intended_engine="api_native", mutating=not is_dry_run())
    normalized_type = _normalize_database_type_for_switch(db_type)
    conn = get_connection(require_project=False)
    target_db = _find_database(conn, name=name, db_type=normalized_type)
    if target_db is None:
        raise ValidationError(
            f"Database '{name}' with type '{normalized_type}' was not found.",
            details={
                "name": name,
                "db_type": normalized_type,
            },
        )
    try:
        current_db = get_current_database_details(conn)
    except APICallFailed:
        current_db = None
    already_current = isinstance(current_db, dict) and _database_matches(current_db, name=name, db_type=normalized_type)
    db_info = {"DbType": normalized_type, "DbName": name}

    if is_dry_run():
        output(
            mutation_payload(
                action="project.db.switch",
                target={"kind": "database", "name": name, "type": normalized_type},
                changed=False,
                would_change=not already_current,
                current_database=current_db,
                message=f"DRY-RUN: Would switch to database: {name}",
            )
        )
        return

    if already_current:
        output(
            mutation_payload(
                action="project.db.switch",
                target={"kind": "database", "name": name, "type": normalized_type},
                changed=False,
                current_database=current_db,
                message=f"Already on database: {name}",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Switching databases can close the current DaVinci Resolve project; rerun with --force to switch.",
                details={
                    "action": "project.db.switch",
                    "target": db_info,
                    "current_database": current_db,
                    "required_option": "--force",
                },
            )
        if not typer.confirm(
            f"Switch database to '{name}' ({normalized_type})? This can close the current DaVinci Resolve project.",
            default=False,
        ):
            raise ConfirmationRequired(
                "Project database switch cancelled.",
                details={
                    "action": "project.db.switch",
                    "target": db_info,
                    "current_database": current_db,
                    "required_option": "--force",
                },
            )

    result = conn.project_manager.SetCurrentDatabase(db_info)
    if result:
        output(
            mutation_payload(
                action="project.db.switch",
                target={"kind": "database", "name": name, "type": normalized_type},
                changed=True,
                previous_database=current_db,
                message=f"Switched to database: {name}",
            )
        )
    else:
        raise APICallFailed(f"Failed to switch to database '{name}'.")


@db_app.command("create")
@handle_errors
def db_create(
    name: str = typer.Argument(..., help="Database name"),
    dir_path: str = typer.Option(..., "--dir", help="Database directory path"),
):
    """Create and verify an explicitly targeted Disk project library."""
    enforce_mutation_policy("project.db_create", intended_engine="db_workaround", mutating=not is_dry_run())
    preflight = project_library_ops.preflight_create(name=name, dir_path=dir_path)
    if is_dry_run():
        output(
            mutation_payload(
                action="project.db.create",
                target={"kind": "database", "name": preflight["name"], "type": "Disk"},
                changed=False,
                db_type="Disk",
                dir_path=str(preflight["target_root"]),
                directory_exists=False,
                overwrite_supported=False,
                verification_plan=["registration_readback", "two_reopen_readbacks", "original_context_restore"],
                message=f"DRY-RUN: Would create Disk project library '{preflight['name']}' at: {preflight['target_root']}",
            )
        )
        return

    conn = get_connection(require_project=False)
    result = project_library_ops.create_library(conn, name=name, dir_path=dir_path)
    output(
        mutation_payload(
            action="project.db.create",
            target={"kind": "database", "name": result["library"]["name"], "type": "Disk"},
            **result,
            message=f"Created and verified Disk project library: {result['library']['name']}",
        )
    )


@db_app.command("backup")
@handle_errors
def db_backup(
    name: str = typer.Argument(..., help="Database name"),
    path: str = typer.Argument(..., help="Backup output path"),
):
    """Create and verify a deterministic Disk project-library backup."""
    enforce_mutation_policy("project.db_backup", intended_engine="db_workaround", mutating=not is_dry_run())
    preflight = project_library_ops.preflight_backup(name=name, path=path)
    if is_dry_run():
        output(
            mutation_payload(
                action="project.db.backup",
                target={"kind": "database", "name": preflight["name"], "type": "Disk"},
                changed=False,
                backup_path=str(preflight["destination"]),
                overwrite_supported=False,
                verification_plan=["sqlite_integrity", "per_file_sha256", "manifest_identity", "original_context_restore"],
                message=f"DRY-RUN: Would back up Disk project library '{preflight['name']}' to: {preflight['destination']}",
            )
        )
        return

    conn = get_connection(require_project=False)
    result = project_library_ops.backup_library(conn, name=name, path=path)
    output(
        mutation_payload(
            action="project.db.backup",
            target={"kind": "database", "name": result["library"]["name"], "type": "Disk"},
            **result,
            message=f"Backed up and verified Disk project library '{result['library']['name']}' to: {result['backup']['path']}",
        )
    )


@db_app.command("restore")
@handle_errors
def db_restore(
    path: str = typer.Argument(..., help="Backup file path"),
    name: str = typer.Option(..., "--name", help="Explicit target project-library name"),
    dir_path: str = typer.Option(..., "--dir", help="Explicit new target project-library directory"),
):
    """Restore a verified backup to an explicit new Disk project library."""
    enforce_mutation_policy("project.db_restore", intended_engine="db_workaround", mutating=not is_dry_run())
    preflight = project_library_ops.preflight_restore(path=path, name=name, dir_path=dir_path)
    if is_dry_run():
        output(
            mutation_payload(
                action="project.db.restore",
                target={"kind": "database", "name": preflight["name"], "type": "Disk"},
                changed=False,
                backup_path=str(preflight["backup"]["root"]),
                backup_id=preflight["backup"]["manifest"]["backup_id"],
                target_name=preflight["name"],
                dir_path=str(preflight["target_root"]),
                overwrite_supported=False,
                verification_plan=["backup_integrity", "registration_readback", "two_reopen_readbacks", "original_context_restore"],
                message=f"DRY-RUN: Would restore Disk project library '{preflight['name']}' from: {preflight['backup']['root']}",
            )
        )
        return

    conn = get_connection(require_project=False)
    result = project_library_ops.restore_library(conn, path=path, name=name, dir_path=dir_path)
    output(
        mutation_payload(
            action="project.db.restore",
            target={"kind": "database", "name": result["library"]["name"], "type": "Disk"},
            **result,
            message=f"Restored and verified Disk project library: {result['library']['name']}",
        )
    )
