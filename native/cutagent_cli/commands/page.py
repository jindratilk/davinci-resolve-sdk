"""Page navigation commands."""

from __future__ import annotations

import typer

from ..connection import get_connection
from ..errors import handle_errors, APICallFailed, ValidationError
from ..output import mutation_payload, output
from ..policy import enforce_mutation_policy

app = typer.Typer(help="Navigate between DaVinci Resolve pages.")

PAGES = ["media", "cut", "edit", "fusion", "color", "fairlight", "deliver"]


@app.command()
@handle_errors
def current():
    """Show the current page."""
    conn = get_connection(require_project=False)
    page = conn.resolve.GetCurrentPage()
    output({"page": page})


@app.command("switch")
@handle_errors
def switch_page(
    page: str = typer.Argument(..., help=f"Page name: {', '.join(PAGES)}"),
):
    """Switch to a specific page."""
    enforce_mutation_policy("page.navigation", intended_engine="api_native")
    page_lower = page.lower()
    if page_lower not in PAGES:
        raise ValidationError(
            f"Unknown page: {page}. Must be one of: {', '.join(PAGES)}",
            details={"page": page, "allowed_pages": PAGES},
        )

    conn = get_connection(require_project=False)
    current_page = str(conn.resolve.GetCurrentPage() or "").lower()
    if current_page == page_lower:
        output(
            mutation_payload(
                action="page.switch",
                target={"kind": "page", "name": page_lower},
                changed=False,
                previous_page=current_page,
                current_page=current_page,
                message=f"Already on {page_lower} page.",
            )
        )
        return

    result = conn.resolve.OpenPage(page_lower)
    if result:
        updated_page = str(conn.resolve.GetCurrentPage() or page_lower).lower()
        output(
            mutation_payload(
                action="page.switch",
                target={"kind": "page", "name": page_lower},
                changed=True,
                previous_page=current_page or None,
                current_page=updated_page,
                message=f"Switched to {page_lower} page.",
            )
        )
    else:
        raise APICallFailed(
            f"Failed to switch to page '{page_lower}'.",
            details={"page": page_lower},
        )
