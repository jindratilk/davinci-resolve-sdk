# `fairlight waveform info`

Syntax: `cutagent fairlight waveform info`

## Search terms

- inspect Fairlight waveform view
- show waveform view option
- get Fairlight audio mark in out
- inspect audio clip height
- inspect UIElementsState waveform keys
- waveform display mode
- Fairlight waveform UI state
- why audio waveforms look different
- inspect waveform panel settings

## What it does

Read Fairlight audio waveform view state from the timeline project.

## Do not use when

Do not use this command to inspect waveform amplitude, peaks, silence, clipping, loudness, sample rate, bit depth, channel layout, or audio contents.
Do not use it to determine whether a click/pop exists or was repaired.
Use timeline mark commands for supported timeline mark-in/out operations.
Do not use it on cloud/PostgreSQL projects or an arbitrary project file; it resolves the currently open local Disk project and active timeline.

## Preflight and readback

Before reading, confirm the intended active project/timeline with `project info`.
The plan correctly states that only UI view state is readable and sample repair/redraw are unsupported.
Treat mark, view-position, and waveform-option integers as opaque raw evidence unless independently correlated with the current DaVinci Resolve UI.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not mean the raw option was visually matched to the GUI.

## Examples

- `cutagent fairlight waveform info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
