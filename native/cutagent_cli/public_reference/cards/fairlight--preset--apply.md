# `fairlight preset apply`

Syntax: `cutagent fairlight preset apply NAME`

## Search terms

- apply Fairlight preset
- load audio mix preset
- use saved Fairlight setup
- apply preset to current timeline
- recall Fairlight preset
- load dialogue audio preset
- use broadcast mix preset
- apply saved audio configuration
- apply timeline audio preset
- reuse Fairlight mix settings
- load Equalizer preset from CLI
- apply Dialogue Cleaner preset

## What it does

Apply a Fairlight preset to the current timeline.

## Do not use when

Do not use this command for the presets shown inside a track's Equalizer panel, Fairlight FX plug-in, dynamics panel, or another GUI subpanel unless `fairlight preset list` returns the exact same name.
Use specific commands such as Fairlight EQ, dynamics, track state, clip gain, voice isolation, or bus operations when the user names an individual setting rather than a previously saved whole-timeline preset. Those routes provide narrower targets and more meaningful readback.
Do not use it to create, import, export, rename, or delete presets.
Do not use it when the active timeline is uncertain. The target is always whatever timeline is current at execution, not a timeline named by an option. Switch and verify the timeline first.

## Preflight and readback

Before applying, identify the active project and timeline, save/checkpoint the project, and capture the current Fairlight state that the intended preset might affect: track names/counts, enable/lock states, buses, EQ/dynamics, routing, plug-ins, and any mix values for which a supported readback exists.
The command itself has no post-apply preset-state getter and does not prove which settings changed. Save only after confirming the correct timeline and intended mix result.

## Public arguments and options

- `NAME` (required) — Fairlight preset name

## Boundaries and gotchas

- Do not patch those bytes from this command.
- Because the CLI cannot enumerate its contents, assume it can replace multiple current-timeline Fairlight settings and checkpoint before a positive apply.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight preset apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
