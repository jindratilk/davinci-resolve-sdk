# `color reset-fusion`

Syntax: `cutagent color reset-fusion [--clip VALUE] [--comp VALUE] [--force]`

## Search terms

- reset Fusion grading graph
- remove clip-attached color helpers
- delete Fusion ColorCorrector masks keyers trackers
- restore MediaIn to MediaOut
- clear CutAgent Fusion grade
- remove Fusion primary grade
- wipe Fusion qualifier and windows
- clean broken grading comp
- bypass all Fusion grading tools
- remove chromatic adaptation from clip
- return Fusion comp to clean pipe
- clear Fusion color stack without deleting comp

## What it does

Remove Fusion grading and restore a clean Fusion flow.

## Do not use when

Use `color comp repair` or `color graph normalize` when the helpers should survive and only graph connectivity needs repair. Do not use on a Fusion comp containing hand-authored ColorCorrectors, trackers, masks, ChromaKeyers or ChromaticAdaptation that must survive, even if CutAgent did not create them. Do not use it to remove the entire Fusion composition; it deliberately preserves the comp. If arbitrary remaining effects should stay in the rendered main chain, rebuild that chain explicitly instead of accepting direct MediaIn→MediaOut bypass.

## Preflight and readback

In machine/JSON mode include `--force` only after the preview is accepted. Confirm the exact clip/timeline/comp and ensure no concurrent Fusion render or manual edit is in progress.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- “Grading helpers” means every tool of seven hard-coded types, not only tools created by this CLI.
- It does not delete the composition.
- Dry-run is correctly implemented here, unlike several neighboring qualifier commands.
- A duplicate clip name risks wiping the wrong comp.
- It requires an existing comp; it does not create one merely to reset it.
- There is no explicit Studio-only branch.

## DaVinci Resolve editions

It requires an existing comp; it does not create one merely to reset it. - There is no explicit Studio-only branch.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent color reset-fusion --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
