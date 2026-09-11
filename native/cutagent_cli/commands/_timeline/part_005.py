"""Timeline and exact video-item output blanking commands."""
from __future__ import annotations

import typer

from ..connection import get_connection
from ..core import output_blanking
from ..errors import ValidationError, handle_errors
from ..output import is_dry_run, output, set_execution_engine, set_verification_status
from ..policy import enforce_mutation_policy

output_blanking_app = typer.Typer(help='Read or set timeline and clip output blanking in pixels.')
app.add_typer(output_blanking_app, name='output-blanking')


@output_blanking_app.command('get')
@handle_errors
def blanking_get(item_id: str | None = typer.Option(None, '--item-id', help='Exact video timeline item ID; omit for timeline blanking')):
    """Read output blanking and clip inheritance without modifying the timeline."""
    set_execution_engine('api_native')
    conn = get_connection(require_timeline=True)
    item = output_blanking.item_by_id(conn, item_id) if item_id else None
    output(output_blanking.read(conn, item), title='Output Blanking')


@output_blanking_app.command('set')
@handle_errors
def blanking_set(
    top: int | None = typer.Option(None, min=0, help='Top blanking in pixels'),
    bottom: int | None = typer.Option(None, min=0, help='Bottom blanking in pixels'),
    left: int | None = typer.Option(None, min=0, help='Left blanking in pixels'),
    right: int | None = typer.Option(None, min=0, help='Right blanking in pixels'),
    item_id: str | None = typer.Option(None, '--item-id', help='Exact video timeline item ID; omit for timeline blanking'),
    use_timeline: bool | None = typer.Option(None, '--use-timeline/--use-clip', help='Use timeline blanking or the stored clip override; mutually exclusive with edge values'),
):
    """Set all four pixel edges, or explicitly select clip inheritance."""
    supplied = [top, bottom, left, right]
    value = dict(zip(('top', 'bottom', 'left', 'right'), supplied)) if all(x is not None for x in supplied) else None
    if any(x is not None for x in supplied) and value is None:
        raise ValidationError('Supply all four output blanking edge values.')
    if (value is None) == (use_timeline is None) or (use_timeline is not None and not item_id):
        raise ValidationError('Supply four edges, or an exact item ID and inheritance choice.')
    enforce_mutation_policy('timeline.output_blanking', intended_engine='api_native', mutating=not is_dry_run())
    conn = get_connection(require_timeline=True)
    item = output_blanking.item_by_id(conn, item_id) if item_id else None
    if is_dry_run():
        output({'changed': False, 'would_change': True, 'before': output_blanking.read(conn, item), 'blanking': value, 'use_timeline': use_timeline})
        return
    result = output_blanking.write(conn, value, item=item, use_timeline=use_timeline)
    set_verification_status('verified')
    output(result, title='Output Blanking')
