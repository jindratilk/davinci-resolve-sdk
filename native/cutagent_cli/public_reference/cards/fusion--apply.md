# `fusion apply`

Syntax: `cutagent fusion apply PATH [--clip VALUE] [--track VALUE] [--record-frame VALUE] [--verify-frame VALUE] [--export-check VALUE]`

## Search terms

- apply .setting to existing clip
- import Fusion comp onto clip
- attach Fusion graph to timeline item
- load Fusion setting on current clip
- replace clip Fusion composition
- apply motion graphics graph to footage
- import lower third setting onto clip
- add TextPlus graph to existing media
- apply Fusion template without inserting holder
- target Fusion import by track and frame
- import .setting and export verification frame
- add Fusion composition to selected clip

## What it does

Apply a template file to a clip using Fusion import.

## Do not use when

`fusion apply` never creates that holder.
Do not choose among these aliases by name alone; inspect their target semantics.
Importing a whole setting can replace/reinitialize composition content rather than make one small node/input change.
Repeating apply is for existing items and has no batch atomicity or cleanup.
Do not use clip-name targeting when names are duplicated or unstable. Prefer the explicit video track plus record-offset selector after listing the track.
It proves the still export completed, not that the requested content is visible, correctly positioned, or faithful to a reference.

## Preflight and readback

Before applying, inspect the current project/timeline, list the exact video track items, and identify the target by stable track/frame evidence.
Inspect the source with the Fusion setting inspector and source review. Confirm MediaOut connectivity, referenced tools, node layout, frame range, fonts, media paths, modifiers, expressions, masks, external plugins/Fuses, and edition/version dependencies.
Run the exact command with global `--dry-run`.
For visual work, export one or more in-range frames and inspect the pixels manually. Confirm the playhead returned to its prior timecode and the expected application page is restored. Test representative animation times, not only a static first frame.

## Public arguments and options

- `PATH` (required) — .setting file to apply
- `--clip` (optional) — Clip name (or current)
- `--track` (optional) — Video track index used with --record-frame
- `--record-frame` (optional) — Timeline record frame used with --track
- `--verify-frame` (optional) — After apply, export this timeline frame for visual verification
- `--export-check` (optional) — PNG output path for --verify-frame visual verification

## Boundaries and gotchas

- Dry-run deliberately does not connect to DaVinci Resolve or resolve the clip.
- Auto-layout can change only the imported temporary copy.
- `--verify-frame` travels through the timeline playhead setter, whose timecode behavior differs from the selector path.
- Because selector and verification frame parsing differ, do not reuse one raw frame string blindly for both options.
- The default verification output is next to the source setting, which may be read-only or an undesirable location.
- Supply a reviewed writable `--export-check` path.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
