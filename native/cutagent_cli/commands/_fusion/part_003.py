from __future__ import annotations

@node_app.command("delete")
@handle_errors
def node_delete(
    tool_name: str = typer.Argument(..., help="Tool/node name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a Fusion node; alias for `fusion tool delete`."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_name = tool_name.strip()
    if not tool_name:
        raise ValidationError(
            "Fusion node delete requires TOOL_NAME.",
            details={
                "tool_name": tool_name,
                "example": 'cutagent fusion node delete TextPlus1 --json',
                "discovery_hint": "Use `cutagent fusion tool list --json` to inspect node names before deleting.",
            },
        )
    if is_dry_run():
        dry_run_message(f"Would delete Fusion node '{tool_name}'.")
        return
    require_force_for_machine_mode(
        force=force,
        action="fusion.node.delete",
        target_kind="fusion_tool",
        target_name=tool_name,
        prompt=f"Delete Fusion node '{tool_name}'?",
    )
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.delete_tool(tool_name)
    output(
        {
            "action": "fusion.node.delete",
            "name": tool_name,
            "deleted": True,
            "route": "fusion_tool.Delete",
        },
        title="Fusion Node Delete",
    )


@node_app.command("connect")
@handle_errors
def node_connect(
    src_tool: str = typer.Argument(..., help="Source tool/node name"),
    src_output: str = typer.Argument(..., help="Source output name (e.g., Output)"),
    dst_tool: str = typer.Argument(..., help="Destination tool/node name"),
    dst_input: str = typer.Argument(..., help="Destination input name (e.g., Input, Foreground, Background)"),
):
    """Connect two Fusion nodes; alias for `fusion tool connect`."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    src_tool = src_tool.strip()
    src_output = src_output.strip()
    dst_tool = dst_tool.strip()
    dst_input = dst_input.strip()
    missing = [
        name
        for name, value in (
            ("src_tool", src_tool),
            ("src_output", src_output),
            ("dst_tool", dst_tool),
            ("dst_input", dst_input),
        )
        if not str(value or "").strip()
    ]
    if missing:
        raise ValidationError(
            "Fusion node connect requires SRC_TOOL SRC_OUTPUT DST_TOOL DST_INPUT.",
            details={
                "missing": missing,
                "example": 'cutagent fusion node connect TextPlus1 Output Merge1 Foreground --json',
                "common_inputs": ["Input", "Foreground", "Background", "EffectMask"],
                "discovery_hint": "Use `cutagent fusion tool list --json`, `fusion tool outputs NODE --json`, and `fusion tool inputs NODE --json` before connecting.",
            },
        )
    if is_dry_run():
        dry_run_message(f"Would connect Fusion node {src_tool}.{src_output} to {dst_tool}.{dst_input}.")
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.connect_tools(src_tool, src_output, dst_tool, dst_input)
    output(
        {
            "action": "fusion.node.connect",
            "source": {"node": src_tool, "output": src_output},
            "destination": {"node": dst_tool, "input": dst_input},
            "connected": True,
            "route": "fusion_input.ConnectTo",
        },
        title="Fusion Node Connect",
    )


@node_app.command("disconnect")
@handle_errors
def node_disconnect(
    tool_name: str = typer.Argument(..., help="Tool/node name"),
    input_name: str = typer.Argument(..., help="Input name to disconnect"),
):
    """Disconnect a Fusion node input; alias for `fusion tool disconnect`."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_name = tool_name.strip()
    input_name = input_name.strip()
    missing = [
        name
        for name, value in (("tool_name", tool_name), ("input_name", input_name))
        if not str(value or "").strip()
    ]
    if missing:
        raise ValidationError(
            "Fusion node disconnect requires TOOL_NAME INPUT_NAME.",
            details={
                "missing": missing,
                "example": 'cutagent fusion node disconnect Merge1 Foreground --json',
                "common_inputs": ["Input", "Foreground", "Background", "EffectMask"],
                "discovery_hint": "Use `cutagent fusion tool list --json` and `fusion tool inputs NODE --json` before disconnecting.",
            },
        )
    if is_dry_run():
        dry_run_message(f"Would disconnect Fusion node input {tool_name}.{input_name}.")
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.disconnect_tool(tool_name, input_name)
    output(
        {
            "action": "fusion.node.disconnect",
            "node": tool_name,
            "input": input_name,
            "disconnected": True,
            "route": "fusion_input.ConnectToNone",
        },
        title="Fusion Node Disconnect",
    )


@tool_app.command("delete")
@handle_errors
def tool_delete(
    tool_name: str = typer.Argument(..., help="Tool name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a tool from the composition."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_name = tool_name.strip()
    if not tool_name:
        raise ValidationError(
            "Fusion tool delete requires TOOL_NAME.",
            details={
                "tool_name": tool_name,
                "example": "cutagent fusion tool delete Background1 --json",
                "discovery_hint": "Use `cutagent fusion tool list --json` before deleting.",
            },
        )
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would delete Fusion tool '{tool_name}'.",
                "action": "fusion.tool.delete",
                "tool": tool_name,
                "would_delete": True,
                "route": "fusion_tool.Delete",
                "readback_command": "cutagent fusion tool list --json",
            },
            title="Fusion Tool Delete",
        )
        return
    require_force_for_machine_mode(
        force=force,
        action="fusion.tool.delete",
        target_kind="fusion_tool",
        target_name=tool_name,
        prompt=f"Delete Fusion tool '{tool_name}'?",
    )
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.delete_tool(tool_name)
    success(f"Deleted tool: {tool_name}")


@tool_app.command("connect")
@handle_errors
def tool_connect(
    src_tool: str = typer.Argument(..., help="Source tool name"),
    src_output: str = typer.Argument(..., help="Source output name (e.g., Output)"),
    dst_tool: str = typer.Argument(..., help="Destination tool name"),
    dst_input: str = typer.Argument(..., help="Destination input name (e.g., Input, Foreground, Background)"),
):
    """Connect two tools together."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    src_tool = src_tool.strip()
    src_output = src_output.strip()
    dst_tool = dst_tool.strip()
    dst_input = dst_input.strip()
    missing = [
        name
        for name, value in (
            ("src_tool", src_tool),
            ("src_output", src_output),
            ("dst_tool", dst_tool),
            ("dst_input", dst_input),
        )
        if not value
    ]
    if missing:
        raise ValidationError(
            "Fusion tool connect requires SRC_TOOL SRC_OUTPUT DST_TOOL DST_INPUT.",
            details={
                "missing": missing,
                "example": "cutagent fusion tool connect Loader1 Output Merge1 Foreground --json",
                "common_inputs": ["Input", "Foreground", "Background", "EffectMask"],
                "discovery_hint": "Use `cutagent fusion tool list --json`, `fusion tool outputs TOOL --json`, and `fusion tool inputs TOOL --json` before connecting.",
            },
        )
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would connect Fusion tool {src_tool}.{src_output} to {dst_tool}.{dst_input}.",
                "action": "fusion.tool.connect",
                "source": {"tool": src_tool, "output": src_output},
                "destination": {"tool": dst_tool, "input": dst_input},
                "would_connect": True,
                "route": "fusion_input.ConnectTo",
            },
            title="Fusion Tool Connect",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.connect_tools(src_tool, src_output, dst_tool, dst_input)
    success(f"Connected: {src_tool}.{src_output} → {dst_tool}.{dst_input}")


@tool_app.command("disconnect")
@handle_errors
def tool_disconnect(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name to disconnect"),
):
    """Disconnect a tool input."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_name = tool_name.strip()
    input_name = input_name.strip()
    missing = [
        name
        for name, value in (("tool_name", tool_name), ("input_name", input_name))
        if not value
    ]
    if missing:
        raise ValidationError(
            "Fusion tool disconnect requires TOOL_NAME INPUT_NAME.",
            details={
                "missing": missing,
                "example": "cutagent fusion tool disconnect Text1 Background --json",
                "common_inputs": ["Input", "Foreground", "Background", "EffectMask"],
                "discovery_hint": "Use `cutagent fusion tool inputs TOOL --json` before disconnecting.",
            },
        )
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would disconnect Fusion tool input {tool_name}.{input_name}.",
                "action": "fusion.tool.disconnect",
                "tool": tool_name,
                "input": input_name,
                "would_disconnect": True,
                "route": "fusion_input.ConnectToNone",
                "readback_command": f"cutagent fusion tool inputs {tool_name} --json",
            },
            title="Fusion Tool Disconnect",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.disconnect_tool(tool_name, input_name)
    success(f"Disconnected: {tool_name}.{input_name}")


@tool_app.command("get")
@handle_errors
def tool_get(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: Optional[str] = typer.Argument(None, help="Input name (omit to show all)"),
    time: Optional[int] = typer.Option(None, "--time", help="Frame time (default: current)"),
):
    """Get tool input value(s)."""
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    if input_name:
        # Get specific input
        value = api.get_tool_input(tool_name, input_name, time)
        output({input_name: value})
    else:
        # Get all inputs
        inputs = api.get_tool_inputs(tool_name)
        output(inputs, title=f"{tool_name} Inputs")


@tool_app.command("set")
@handle_errors
def tool_set(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
    value: str = typer.Argument(..., help="Value to set"),
    time: Optional[int] = typer.Option(None, "--time", help="Frame time (creates keyframe if set)"),
):
    """Set tool input value.
    
    Examples:
        cutagent fusion tool set TextPlus1 StyledText "Hello World"
        cutagent fusion tool set TextPlus1 Size 0.08
        cutagent fusion tool set TextPlus1 Size 0.1 --time 30  # Keyframe at frame 30
    """
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_name = tool_name.strip()
    input_name = input_name.strip()
    missing = [
        name
        for name, field_value in (("tool_name", tool_name), ("input_name", input_name))
        if not field_value
    ]
    if missing:
        raise ValidationError(
            "Fusion tool set requires TOOL_NAME INPUT_NAME VALUE.",
            details={
                "missing": missing,
                "example": 'cutagent fusion tool set TextPlus1 Size 0.08 --json',
                "discovery_hint": "Use `cutagent fusion tool inputs TOOL --json` before setting a value.",
            },
        )
    
    # Try to parse value as number, otherwise use as string
    try:
        parsed_value = float(value)
        if parsed_value.is_integer():
            parsed_value = int(parsed_value)
    except ValueError:
        parsed_value = value
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would set Fusion tool input {tool_name}.{input_name} = {value}.",
                "action": "fusion.tool.set",
                "tool": tool_name,
                "input": input_name,
                "value": parsed_value,
                "raw_value": value,
                "time": time,
                "would_create_keyframe": time is not None,
                "route": "fusion_tool.SetInput",
                "readback_command": f"cutagent fusion tool get {tool_name} {input_name} --json",
            },
            title="Fusion Tool Set",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.set_tool_input(tool_name, input_name, parsed_value, time)
    success(f"Set {tool_name}.{input_name} = {value}")


@tool_app.command("inputs")
@handle_errors
def tool_inputs(
    tool_name: str = typer.Argument(..., help="Tool name"),
):
    """List all inputs of a tool with their current values."""
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    inputs = api.get_tool_inputs(tool_name)
    
    # Format for display
    rows = []
    for input_name, info in inputs.items():
        rows.append({
            "name": input_name,
            "id": info.get("id", ""),
            "value": str(info.get("value", ""))[:50],  # Truncate long values
        })
    
    output(rows, columns=[("name", "Input"), ("id", "ID"), ("value", "Value")], title=f"{tool_name} Inputs")


@tool_app.command("outputs")
@handle_errors
def tool_outputs(
    tool_name: str = typer.Argument(..., help="Tool name"),
):
    """List all outputs of a tool."""
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    outputs = api.get_tool_outputs(tool_name)
    
    rows = []
    for output_name, info in outputs.items():
        rows.append({
            "name": output_name,
            "id": info.get("id", ""),
        })
    
    output(rows, columns=[("name", "Output"), ("id", "ID")], title=f"{tool_name} Outputs")


@tool_app.command("attrs")
@handle_errors
def tool_attrs(
    tool_name: str = typer.Argument(..., help="Tool name"),
):
    """Get tool attributes."""
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    attrs = api.get_tool_attrs(tool_name)
    output(attrs, title=f"{tool_name} Attributes")


@tool_app.command("active")
@handle_errors
def tool_active(
    tool_name: Optional[str] = typer.Argument(None, help="Tool name to activate (omit to show current)"),
):
    """Get or set the active tool."""
    if tool_name:
        enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
        if is_dry_run():
            output(
                {
                    "message": f"DRY-RUN: Would set active Fusion tool to '{tool_name}'.",
                    "action": "fusion.tool.active",
                    "tool": tool_name,
                    "would_set": True,
                    "route": "fusion_comp.ActiveTool",
                },
                title="Fusion Active Tool",
            )
            return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    if tool_name:
        api.set_active_tool(tool_name)
        success(f"Set active tool: {tool_name}")
    else:
        active = api.get_active_tool()
        output({"active_tool": active or "(none)"})


@tool_app.command("copy")
@handle_errors
def tool_copy(
    tool_names: List[str] = typer.Argument(..., help="Tool names to copy"),
):
    """Copy tools to clipboard."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    normalized_tool_names = [name.strip() for name in tool_names if name.strip()]
    if not normalized_tool_names:
        raise ValidationError(
            "Fusion tool copy requires at least one TOOL_NAME.",
            details={
                "tool_names": tool_names,
                "example": "cutagent fusion tool copy Merge1 Background1 --json",
                "discovery_hint": "Use `cutagent fusion tool list --json` before copying.",
            },
        )
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would copy {len(normalized_tool_names)} Fusion tool(s) to clipboard.",
                "action": "fusion.tool.copy",
                "tools": normalized_tool_names,
                "tool_count": len(normalized_tool_names),
                "would_copy_to_clipboard": True,
                "route": "fusion_comp.Copy",
            },
            title="Fusion Tool Copy",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.copy_tools(normalized_tool_names)
    success(f"Copied {len(normalized_tool_names)} tool(s) to clipboard.")


@tool_app.command("paste")
@handle_errors
def tool_paste():
    """Paste tools from clipboard."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    if is_dry_run():
        output(
            {
                "message": "DRY-RUN: Would paste Fusion tools from clipboard.",
                "action": "fusion.tool.paste",
                "would_paste_from_clipboard": True,
                "route": "fusion_comp.Paste",
                "readback_command": "cutagent fusion tool list --json",
            },
            title="Fusion Tool Paste",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.paste_tools()
    success("Pasted tools from clipboard.")


# === Keyframe Commands ===

keyframe_app = typer.Typer(help="Keyframe operations.")
app.add_typer(keyframe_app, name="keyframe")


def _parse_keyframe_value(value: str):
    try:
        parsed_value = float(value)
        if parsed_value.is_integer():
            return int(parsed_value)
        return parsed_value
    except ValueError:
        return value


@keyframe_app.command("add")
@handle_errors
def keyframe_add(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
    frame: int = typer.Argument(..., help="Frame number"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Add a Fusion keyframe; alias for `fusion keyframe set`."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    if not tool_name.strip() or not input_name.strip() or not value.strip():
        raise ValidationError(
            "Fusion keyframe add requires TOOL_NAME INPUT_NAME FRAME VALUE.",
            details={
                "example": "cutagent fusion keyframe add TextPlus1 Size 30 0.1 --json",
                "discovery_hint": "Use `cutagent fusion tool list --json` and `fusion tool inputs NODE --json` before adding keyframes.",
                "active_comp_hint": "Open a Fusion comp or select a timeline clip with an existing Fusion comp.",
            },
        )
    if is_dry_run():
        dry_run_message(f"Would add Fusion keyframe {tool_name}.{input_name}[{frame}] = {value}.")
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    parsed_value = _parse_keyframe_value(value)

    api.set_keyframe(tool_name, input_name, frame, parsed_value)
    output(
        {
            "action": "fusion.keyframe.add",
            "tool": tool_name,
            "input": input_name,
            "frame": frame,
            "value": parsed_value,
            "route": "fusion_tool.SetInput",
        },
        title="Fusion Keyframe Add",
    )


@keyframe_app.command("set")
@handle_errors
def keyframe_set(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
    frame: int = typer.Argument(..., help="Frame number"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a keyframe.
    
    Examples:
        cutagent fusion keyframe set TextPlus1 Size 0 0.05    # Frame 0 = 0.05
        cutagent fusion keyframe set TextPlus1 Size 30 0.1    # Frame 30 = 0.1
    """
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    if is_dry_run():
        dry_run_message(f"Would set Fusion keyframe {tool_name}.{input_name}[{frame}] = {value}.")
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    parsed_value = _parse_keyframe_value(value)
    
    api.set_keyframe(tool_name, input_name, frame, parsed_value)
    success(f"Set keyframe: {tool_name}.{input_name}[{frame}] = {value}")


@keyframe_app.command("list")
@handle_errors
def keyframe_list(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
):
    """List keyframes for an input.
    
    Note: Keyframe detection is limited by the Fusion API.
    This command may not detect all keyframes reliably.
    """
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    keyframes = api.list_keyframes(tool_name, input_name)
    
    if not keyframes:
        from ..output import warning
        warning("No keyframes detected (or keyframe detection not supported for this input).")
        return
    
    output(
        keyframes,
        columns=[("frame", "Frame"), ("value", "Value")],
        title=f"{tool_name}.{input_name} Keyframes"
    )


@keyframe_app.command("delete")
@handle_errors
def keyframe_delete(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
    frame: int = typer.Argument(..., help="Frame number"),
):
    """Remove one Fusion spline keyframe while preserving the remaining animation."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    if not tool_name.strip() or not input_name.strip():
        raise ValidationError(
            "Fusion keyframe delete requires TOOL_NAME INPUT_NAME FRAME.",
            details={
                "example": "cutagent fusion keyframe delete TextPlus1 Size 30 --json",
                "discovery_hint": "Use `cutagent fusion keyframe list TOOL INPUT --json` before deleting a keyframe.",
                "active_comp_hint": "Open a Fusion comp or select a timeline clip with an existing Fusion comp.",
                "api_note": "The input must be animated by a modifier that exposes native DeleteKeyFrames support.",
            },
        )
    if is_dry_run():
        dry_run_message(f"Would delete Fusion keyframe {tool_name}.{input_name}[{frame}].")
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.delete_keyframe(tool_name, input_name, frame)
    output(
        {
            "action": "fusion.keyframe.delete",
            "tool": tool_name,
            "input": input_name,
            "frame": frame,
            "deleted": True,
            "route": "fusion_keyframe_delete",
        },
        title="Fusion Keyframe Delete",
    )


@keyframe_app.command("clear")
@handle_errors
def keyframe_clear(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Clear all keyframes for an input (convert to constant value)."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    if is_dry_run():
        dry_run_message(f"Would clear all Fusion keyframes for {tool_name}.{input_name}.")
        return
    require_force_for_machine_mode(
        force=force,
        action="fusion.keyframe.clear",
        target_kind="fusion_keyframes",
        target_name=f"{tool_name}.{input_name}",
        prompt=f"Clear all Fusion keyframes for {tool_name}.{input_name}?",
    )
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    api.clear_keyframes(tool_name, input_name)
    success(f"Cleared all keyframes for {tool_name}.{input_name}")


# === Effect Commands ===

effect_app = typer.Typer(help="Add Fusion effects (blur, glow, sharpen, transform, color-correct).")
app.add_typer(effect_app, name="effect")


@effect_app.command("blur")
@handle_errors
def effect_blur(
    strength: float = typer.Option(5.0, "--strength", "-s", help="Blur strength"),
):
    """Add a blur effect inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_effect_blur(strength=strength)
    tool_name = tool.Name if hasattr(tool, "Name") else "Blur"
    success(f"Added blur effect ({tool_name}), strength={strength}")


@effect_app.command("glow")
@handle_errors
def effect_glow(
    intensity: float = typer.Option(0.5, "--intensity", "-i", help="Glow intensity"),
):
    """Add a soft glow effect inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_effect_glow(intensity=intensity)
    tool_name = tool.Name if hasattr(tool, "Name") else "SoftGlow"
    success(f"Added glow effect ({tool_name}), intensity={intensity}")


@effect_app.command("sharpen")
@handle_errors
def effect_sharpen(
    amount: float = typer.Option(0.5, "--amount", "-a", help="Sharpen amount"),
):
    """Add a sharpen (unsharp mask) effect inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_effect_sharpen(amount=amount)
    tool_name = tool.Name if hasattr(tool, "Name") else "UnsharpMask"
    success(f"Added sharpen effect ({tool_name}), amount={amount}")


@effect_app.command("transform")
@handle_errors
def effect_transform(
    zoom: float = typer.Option(1.0, "--zoom", "-z", help="Zoom factor (1.0 = 100%)"),
    x: float = typer.Option(0.0, "--x", help="X offset from center"),
    y: float = typer.Option(0.0, "--y", help="Y offset from center"),
    rotation: float = typer.Option(0.0, "--rotation", "-r", help="Rotation in degrees"),
):
    """Add a transform effect inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_effect_transform(zoom=zoom, x=x, y=y, rotation=rotation)
    tool_name = tool.Name if hasattr(tool, "Name") else "Transform"
    success(f"Added transform ({tool_name}): zoom={zoom}, x={x}, y={y}, rotation={rotation}")


@effect_app.command("color-correct")
@handle_errors
def effect_color_correct(
    gain_r: float = typer.Option(1.0, "--gain-r", help="Red gain"),
    gain_g: float = typer.Option(1.0, "--gain-g", help="Green gain"),
    gain_b: float = typer.Option(1.0, "--gain-b", help="Blue gain"),
    gamma: float = typer.Option(1.0, "--gamma", help="Master gamma"),
    saturation: float = typer.Option(1.0, "--saturation", "--sat", help="Saturation"),
):
    """Add a ColorCorrector effect inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_effect_color_correct(
        gain_r=gain_r, gain_g=gain_g, gain_b=gain_b,
        gamma=gamma, saturation=saturation,
    )
    tool_name = tool.Name if hasattr(tool, "Name") else "ColorCorrector"
    success(f"Added color corrector ({tool_name})")


# === Mask Commands ===

mask_app = typer.Typer(help="Add Fusion masks (rectangle, ellipse, polygon).")
app.add_typer(mask_app, name="mask")


def _parse_xy_option(raw: str, *, option_name: str) -> tuple[float, float]:
    parts = [part.strip() for part in str(raw or "").split(",")]
    if len(parts) != 2 or not all(parts):
        raise ValidationError(
            f"{option_name} must use X,Y format.",
            details={"parameter": option_name, "value": raw, "expected_format": "x,y", "example": "0.5,0.5"},
        )
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as error:
        raise ValidationError(
            f"{option_name} must contain numeric X,Y values.",
            details={"parameter": option_name, "value": raw, "expected_format": "x,y", "example": "0.5,0.5"},
        ) from error


def _parse_xy_points(raw: str, *, parameter: str = "points") -> list[tuple[float, float]]:
    pairs = [pair.strip() for pair in str(raw or "").split(";")]
    if not pairs or any(not pair for pair in pairs):
        raise ValidationError(
            f"{parameter} must use x,y;x,y;... format.",
            details={
                "parameter": parameter,
                "value": raw,
                "expected_format": "x,y;x,y;...",
                "example": "0.1,0.1;0.8,0.1;0.5,0.8",
            },
        )

    parsed: list[tuple[float, float]] = []
    for pair in pairs:
        parts = [part.strip() for part in pair.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ValidationError(
                f"{parameter} must use x,y;x,y;... format.",
                details={
                    "parameter": parameter,
                    "value": raw,
                    "expected_format": "x,y;x,y;...",
                    "example": "0.1,0.1;0.8,0.1;0.5,0.8",
                },
            )
        try:
            parsed.append((float(parts[0]), float(parts[1])))
        except ValueError as error:
            raise ValidationError(
                f"{parameter} must contain numeric x,y pairs.",
                details={
                    "parameter": parameter,
                    "value": raw,
                    "expected_format": "x,y;x,y;...",
                    "example": "0.1,0.1;0.8,0.1;0.5,0.8",
                },
            ) from error
    return parsed
