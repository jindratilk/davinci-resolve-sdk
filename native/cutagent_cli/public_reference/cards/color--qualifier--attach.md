# `color qualifier attach`

Syntax: `cutagent color qualifier attach QUALIFIER_NAME [--clip VALUE] [--position VALUE] [--comp VALUE]`

## Search terms

- attach ChromaKeyer to primary grade
- put qualifier in mask chain
- reconnect orphaned qualifier
- reorder Fusion qualifiers
- move chroma qualifier in stack
- activate a qualifier tool
- make ChromaKeyer affect ColorCorrector
- change qualifier mask order
- connect Fusion keyer to grade
- attach qualifier at stack position
- enable existing chroma qualifier

## What it does

Attach a qualifier into the active mask chain.

## Do not use when

Use `color qualifier detach` to remove an active qualifier from the primary's mask chain while keeping the tool. Use `color tracker attach-qualifier` when the intended relationship is a qualifier specifically nested with a tracker rather than placed in the canonical primary mask stack. Use `color window attach` for Rectangle/Ellipse/Polyline masks. Use `color mask stack` or `color graph inspect` before this command when windows, trackers or orphaned tools coexist, because `--position` only orders qualifiers inside the fixed windows→qualifiers→trackers grouping. Do not use on a bespoke branched Fusion graph unless canonical rewiring is acceptable.

## Preflight and readback

Export the Fusion comp when custom connections or animation matter. Calculate `--position` among qualifiers only, starting at zero; it is not a global mask-chain index. Confirm the clip name is unique and the selected comp exists or that creating comp 1 plus a ColorCorrector is intended. Never use `--dry-run` as a safety preview for this command.
Inspect the full graph to verify MediaIn connections, the windows→qualifiers→trackers sequence, the chosen primary and main-pipe wiring. Render/export a representative frame to prove the key actually gates the ColorCorrector.

## Public arguments and options

- `QUALIFIER_NAME` (required) — Qualifier tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--position` (optional) — 0-based stack position
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- `--dry-run` is destructive here.
- Matching is exact and case-sensitive.
- Blank or whitespace-only qualifier names are not rejected.
- The source ordering is built from every ChromaKeyer returned by the composition, not only the current active chain.
- `--position` is clamped silently: negative values become 0 and values larger than the remaining qualifier count become the end.
- With no `--position`, the exactly named existing qualifier is moved to the end of the qualifier subgroup; this is not a no-op “ensure attached.”
- The command name does not signal these additional mutations.
- Named clip resolution picks the first case-insensitive video name/basename match across tracks and has no track/time selector.
- Without `--clip`, the current item under the playhead is used.

## Examples

- `cutagent color qualifier attach --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
