# `fairlight track duplicate`

Syntax: `cutagent fairlight track duplicate INDEX [--include-clips] [--include-processing] [--copy-volume] [--copy-pan] [--copy-clip-eq] [--copy-clip-fx] [--copy-color]`

## Search terms

- duplicate Fairlight track
- copy audio track
- clone dialogue track
- duplicate A1 with clips
- make an empty copy of an audio track
- copy track name and format
- duplicate audio lane without effects
- copy clips to a new audio track
- clone track volume
- copy mono pan to duplicate track
- duplicate clip EQ
- duplicate clip Fairlight FX

## What it does

Duplicate Fairlight track without processing.

## Do not use when

Use `timeline track add` for general video/audio track creation rather than Fairlight-specific duplication semantics.
Use `media append`, `media append batch`, clip move/copy commands, or explicit editing commands when only selected clips should be placed on another track. `--include-clips` is all-or-nothing for every supported item on the source track; it has no clip selector or time-range filter.
Do not use the default command, or describe `--include-processing` as working, when the user expects EQ, dynamics, mute, stereo/surround pan, buses, routing, sends, plugin inserts or automation to be cloned.
Use `fairlight mixer fader` when only track volume should change, `fairlight mixer pan` for an explicit supported pan change, `fairlight clip eq` for clip EQ, and the appropriate clip-FX command for a specific effect. The `--copy-*` flags here are copying aids tied to creation of a new track, not general setters.
Do not use `--copy-pan` for stereo, surround, adaptive or 3D panner state. Do not use `--copy-clip-eq` or `--copy-clip-fx` with `--empty`; those combinations are validation errors because there are no target clips.
Use `fairlight track-color set` when recoloring an existing track without duplicating it. Use track rename/enable/lock commands when only one metadata property should change.

## Preflight and readback

Record the source index, name, subtype, enabled/locked state and clip count, and remember that inserting after the source renumbers every lower audio track. For `--include-clips`, inspect every source item and confirm it is Media Pool backed, has valid start/end/left-offset readback, and has positive duration. If only some clips are wanted, stop and use selective clip placement instead.
Run the exact `--no-processing` request with `--dry-run`.
Before any `--copy-volume`, `--copy-pan`, `--copy-clip-eq`, `--copy-clip-fx` or `--copy-color` request, save/checkpoint the test project and run the corresponding narrow readback.
Run `fairlight tracks` again and verify the shifted identities of all tracks below the insertion point. Verify any requested fader, pan, clip-EQ, clip-FX or color subset with its narrow readback after the final project reopen.

## Public arguments and options

- `INDEX` (required) — Audio track index to duplicate
- `--include-clips/--empty` (optional, default: `true`) — Whether the duplicate should include clips
- `--include-processing/--no-processing` (optional, default: `true`) — Whether the duplicate should include mixer processing
- `--copy-volume/--no-copy-volume` (optional, default: `false`)
- `--copy-pan/--no-copy-pan` (optional, default: `false`)
- `--copy-clip-eq/--no-copy-clip-eq` (optional, default: `false`)
- `--copy-clip-fx/--no-copy-clip-fx` (optional, default: `false`)
- `--copy-color/--no-copy-color` (optional, default: `false`)

## Boundaries and gotchas

- A working invocation must explicitly include `--no-processing`.
- `fairlight track duplicate 999` without `--no-processing` reports unsupported processing, not “track 999 does not exist.”
- `--empty` means no timeline items, not “metadata-free.” Name, subtype, enabled state and locked state are still copied.
- It does not clone the opaque timeline-item object.
- There is no “skip bad clip” mode; one unsupported item prevents the entire requested clip duplicate.
- Do not assume unusual speed, slip, elastic-wave or layered-audio semantics survive without audition/render verification.
- That cleanup is best-effort; the error is recoverable only by inspecting the timeline and removing any residual partial track manually.
- The duplicate is locked only after clips are appended.
- `--copy-volume` is not full mixer copying.
- Missing, out-of-range or unequal lanes block before track creation.
- `--copy-clip-eq` and `--copy-clip-fx` require `--include-clips` and media-pool-backed target items.
- Dry-run never contacts DaVinci Resolve.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight track duplicate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
