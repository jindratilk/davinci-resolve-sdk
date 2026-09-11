# `fusion insert-setting`

Syntax: `cutagent fusion insert-setting [PATH] [--name VALUE] [--timeline VALUE] [--at VALUE] [--duration VALUE] [--holder VALUE] [--track VALUE] [--record-frame VALUE] [--position-x VALUE] [--position-y VALUE] [--holder-kind VALUE] [--render-template VALUE] [--text VALUE] [--image VALUE] [--style-markdown] [--bold-style VALUE] [--param VALUE] [--require-text] [--require-image] [--require-styling] [--keep-rendered] [--rendered-output VALUE]`

## Search terms

- Fusion Composition holder clip
- import setting into timeline
- precise Fusion placement
- Text+ holder insertion
- Fusion duration mismatch
- inserted setting readback

## What it does

Insert a Fusion composition from a template.

## Do not use when

Do not use this command to modify an existing clip. Use `fusion apply`, `fusion template apply`, or `fusion macro apply` with an explicit clip selector.
Do not request precise placement casually.
Do not use `fusion comp current` alone to verify the inserted holder. It can follow the GUI-selected Fusion clip rather than the clip under the playhead. Use an explicit clip selector, export the inserted comp, and export a representative frame.
Do not pass a bare numeric duration when frames are intended. Bare values are seconds; use the `f` suffix for frames.

## Preflight and readback

Choose one source only. For `--render-template`, inspect the template placeholders and provide `--require-text`, `--require-image`, or `--require-styling` when omission would make the graph invalid. Validate every `--param` as `KEY=VALUE`.
Use a unique `--name`. Express frame durations as `48f`, not `48` or `48frames`.
Use `clip fusion list --clip NAME`, export that exact composition, inspect its tools and source text, and export a frame from inside the holder.
Compare requested and read-back name, start, track, duration, position, tool count, and visible pixels.
Clean up by deleting the exact inserted timeline-item range without ripple, list the track again, restore the original playhead/timeline, and confirm the pre-existing clip and Fusion graph remain unchanged.

## Public arguments and options

- `PATH` (optional) — .setting file to insert as a Fusion Composition clip
- `--name` (optional) — Timeline clip name after insertion
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--at` (optional, default: `"0s"`) — Timeline position: timecode, seconds, or frames
- `--duration` (optional, default: `"5s"`) — Clip duration: timecode, seconds, or frames
- `--holder` (optional, default: `"Fusion Composition"`) — Generator name used as the holder clip
- `--track` (optional)
- `--record-frame` (optional) — Exact DaVinci Resolve recordFrame; takes precedence over --at
- `--position-x` (optional) — Optional inspector X position
- `--position-y` (optional) — Optional inspector Y position
- `--holder-kind` (optional, default: `"fusion"`) — fusion or textplus
- `--render-template` (optional) — Render this .setting template before insertion
- `--text` (optional) — Text replacement for template text placeholders
- `--image` (optional) — Image path replacement for template image placeholders
- `--style-markdown/--plain-text` (optional, default: `true`) — Parse **bold** markdown into CharacterLevelStyling
- `--bold-style` (optional, default: `"ExtraBold"`) — Fusion font style used for markdown bold ranges
- `--param` (optional, repeatable, default: `[]`) — Raw template replacement as KEY=VALUE; repeatable
- `--require-text` (optional, default: `false`) — Require a recognized text placeholder to be replaced
- `--require-image` (optional, default: `false`) — Require a recognized image placeholder to be replaced
- `--require-styling` (optional, default: `false`) — Require a recognized styling placeholder to be replaced
- `--keep-rendered` (optional, default: `false`) — Keep the rendered temporary .setting file
- `--rendered-output` (optional) — Write rendered .setting to this path instead of a temporary file

## Boundaries and gotchas

- `--holder-kind` accepts only `fusion` and `textplus`.
- `--record-frame` is used only by the precise route and takes precedence over `--at`.
- Without `--track`, `--record-frame` does not trigger precise placement.
- `--at` and `--duration` accept seconds, timecode, or the short frame suffix such as `48f`.
- The default holder is `Fusion Composition`; `--holder-kind textplus` changes that default holder to `Text+`.
- Template rendering parses `**bold**` into CharacterLevelStyling by default; use `--plain-text` to disable it.
- Temporary rendered settings are deleted after import and after dry-run unless `--keep-rendered` or `--rendered-output` retains them.
- `--rendered-output` creates missing parent directories and deliberately leaves the file in place.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion insert-setting --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
