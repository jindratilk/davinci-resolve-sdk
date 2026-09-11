# `layout load`

Syntax: `cutagent layout load NAME`

## Search terms

- load DaVinci Resolve layout preset
- switch workspace layout
- restore saved UI layout
- load layout by name
- layout preset dry-run
- embedded layout method unsupported
- verify DaVinci Resolve panels

## What it does

Load a layout preset.

## Do not use when

Do not use an unverified or ambiguous name.
Do not load a preset while the user has an important transient workspace arrangement unless changing global UI layout is intended. Panels, page arrangement, viewer placement, dual-screen state, and other UI state may move.
Do not expect the command to load project, timeline, Fusion, or render presets. This command is only for DaVinci Resolve workspace layout presets.

## Preflight and readback

Before execution, normalize and record the exact name through an independent source such as the Workspace > Layout Presets menu. Capture the current page, visible panels, viewer mode, project/timeline, and any dual-screen state.
Remember that a successful dry-run does not establish existence.
Save the current layout to a uniquely named recovery preset before loading a materially different preset.
If the loaded layout is only a test, load the recovery preset and delete all uniquely named test presets.

## Public arguments and options

- `NAME` (required) — Layout preset name

## Boundaries and gotchas

- Dry-run with padded input reported the trimmed name.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent layout load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
