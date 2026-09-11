"""AI video generation provided by the CutAgent desktop app."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import handle_errors
from ..standalone_hosted import unavailable as hosted_service_unavailable


app = typer.Typer(
    no_args_is_help=True,
    help="AI video generation in the CutAgent desktop app.",
)


@app.command("generate")
@handle_errors
def generate(
    prompt: str = typer.Option(..., "--prompt", help="Text prompt for the generated video"),
    resolution: str = typer.Option("720P", "--resolution", help="Requested output resolution: 720P or 1080P"),
    ratio: str = typer.Option("16:9", "--ratio", help="Requested aspect ratio, such as 16:9 or 9:16"),
    duration: int = typer.Option(5, "--duration", min=3, max=15, help="Requested duration in seconds"),
    seed: Optional[int] = typer.Option(None, "--seed", min=0, max=2_147_483_647, help="Optional deterministic provider seed"),
) -> None:
    """Learn where AI video generation is available."""
    # Keep the complete proposed interface discoverable while failing before
    # validation, authentication, billing, upload, provider I/O, or downloads.
    del prompt, resolution, ratio, duration, seed
    hosted_service_unavailable("video_generation")
