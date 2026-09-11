# `color tracker attach-qualifier`

Syntax: `cutagent color tracker attach-qualifier TRACKER_NAME QUALIFIER_NAME [--clip VALUE] [--comp VALUE]`

## Search terms

- attach qualifier to tracker
- track a chroma key mask
- feed keyer into motion tracker
- combine qualifier and tracker
- put ChromaKeyer before Tracker
- track qualified color region
- connect key to tracked mask chain
- make qualifier follow tracking
- reorder qualifier ahead of tracker
- include keyer in tracked grade mask
- wire chroma matte through tracker
- connect qualifier tracker ColorCorrector

## What it does

Ensure a qualifier feeds the tracked mask chain.

## Do not use when

Use `color qualifier chroma` to create/configure the qualifier scaffold first; `attach-qualifier` requires an existing ChromaKeyer and cannot choose green/blue/red or threshold. Use `color qualifier attach` when the goal is only to put a ChromaKeyer into the overall grade-mask chain at a qualifier position, without prioritizing a tracker. Use `color tracker attach-window` for rectangle/ellipse/polygon masks. Use `color secondary create` or the specialized secondary commands for a new combined scaffold.

## Preflight and readback

Record the whole mask-chain order and orphaned tools because this command reintroduces/reorders more than the two arguments.
Run tracking separately and verify animated data; then compare matte/viewer or rendered frames across the range. Command structural validation is necessary but does not show that the qualifier selects pixels or that tracked motion drives the intended region.

## Public arguments and options

- `TRACKER_NAME` (required) — Tracker tool name
- `QUALIFIER_NAME` (required) — Qualifier tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- “Attach qualifier to tracker” does not create a dedicated persistent parent/child association.
- Another qualifier can therefore sit directly against the Tracker; the requested qualifier is only guaranteed to be somewhere upstream.
- It does not validate matte pixels, tracking samples, temporal behavior, or the requested pair's immediate adjacency.
- Dry-run only validates nonblank strings and positive comp index.

## Examples

- `cutagent color tracker attach-qualifier --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
