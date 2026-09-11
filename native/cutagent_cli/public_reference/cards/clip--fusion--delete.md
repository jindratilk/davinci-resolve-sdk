# `clip fusion delete`

Syntax: `cutagent clip fusion delete INDEX [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- delete Fusion composition from clip
- remove Fusion comp by index
- clear last Fusion comp
- strip Fusion graph from timeline item
- remove alternate Fusion version
- delete clip node composition
- return clip to no Fusion comps

## What it does

Delete a Fusion composition.

## Do not use when

Use node deletion inside Fusion when only one tool/effect should go; this command removes an entire composition. Use `clip fusion load` to switch versions without deleting one, and export first when the comp may be needed later.

## Preflight and readback

For multi-comp deletion, list again and confirm count -1 plus the remaining graph. For last-comp deletion, additionally verify recreated video/audio items, source range, links, transitions, effects, retime state, Viewer output, and playhead; manually restore the playhead if needed. Keep the export until render/readback proves the edit survived.

## Public arguments and options

- `INDEX` (required) — Composition index
- `--clip` (optional) — Clip name
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.
- It does not explicitly preserve transitions, OpenFX, take stacks, speed curves/keyframes, cache state, clip groups, sync metadata, or every future Inspector field.
- Do not reuse a cached index for a subsequent delete without listing again.
- Out-of-range indexes are validated against current count.

## Examples

- `cutagent clip fusion delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
