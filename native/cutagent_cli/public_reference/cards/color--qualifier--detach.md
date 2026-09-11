# `color qualifier detach`

Syntax: `cutagent color qualifier detach QUALIFIER_NAME [--clip VALUE] [--comp VALUE]`

## Search terms

- detach chroma qualifier
- disable qualifier without deleting it
- remove ChromaKeyer from mask chain
- make qualifier orphaned
- stop keyer affecting ColorCorrector
- disconnect Fusion qualifier
- bypass existing chroma mask
- remove qualifier from grade stack
- keep keyer tool but deactivate it
- unhook ChromaKeyer from primary
- take qualifier out of EffectMask chain
- temporarily disable Fusion key

## What it does

Detach a qualifier from the active mask chain.

## Do not use when

Use `fusion tool delete ChromaKeyerN` when the tool should be permanently removed from the composition rather than retained as an orphan. Use `color qualifier attach` when reactivating/reordering a detached tool, but verify its known false-success and dry-run hazards. Use `color tracker detach-qualifier` or the tracker-specific relationship command when only a nested tracker/qualifier association should change. Use `color primary set` or Color page commands when the goal is to disable/change the grade itself rather than its Fusion mask. Do not use this to preserve the ChromaKeyer's MediaIn or custom Garbage/Solid Matte wiring: detach explicitly disconnects all four recognized inputs.

## Preflight and readback

Export the Fusion comp if the keyer has custom wiring, animation or expressions. Capture/render a representative frame and matte so the expected unmasked grade is known. Never use global `--dry-run` as a preview; it executes the real detach.
Inspect the full mask chain to ensure all survivors kept the intended order and the correct primary remains connected. Decide explicitly whether to reattach or delete the orphan so it is not mistaken for an active qualifier later.

## Public arguments and options

- `QUALIFIER_NAME` (required) — Qualifier tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- `--dry-run` performs the mutation.
- The command has no dry-run branch.
- Detach does not delete the ChromaKeyer.
- The target must both exist and be active.
- Without `--clip`, the current item or item under the playhead is used.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color qualifier detach --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
