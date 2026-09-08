from __future__ import annotations

@template_icon_app.command("set")
@handle_errors
def template_icon_set(
    template: str = typer.Argument(..., help="Template name or path"),
    png: str = typer.Argument(..., help="PNG icon path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing icon"),
):
    """Set a Fusion template icon."""
    output(sdk_tools.fusion_template_set_icon(template, png, dry_run=is_dry_run(), overwrite=overwrite), title="Fusion Template Icon")


template_assets_app = typer.Typer(help="Fusion template asset operations.")
template_app.add_typer(template_assets_app, name="assets")


@template_assets_app.command("list")
@handle_errors
def template_assets_list(
    template: str = typer.Argument(..., help="Template path"),
):
    """List template-adjacent assets."""
    output(sdk_tools.fusion_template_assets_list(template), title="Fusion Template Assets")


@template_assets_app.command("add")
@handle_errors
def template_assets_add(
    template: str = typer.Argument(..., help="Template path"),
    file: str = typer.Argument(..., help="Asset path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing asset"),
):
    """Add an asset beside a Fusion template."""
    output(sdk_tools.fusion_template_assets_add(template, file, dry_run=is_dry_run(), overwrite=overwrite), title="Fusion Template Asset")
