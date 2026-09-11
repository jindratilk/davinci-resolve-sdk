# `fairlight effect catalog`

Syntax: `cutagent fairlight effect catalog`

## Search terms

- list Track FX presets
- find Macro FX names
- list BMD effects in timeline
- check Fairlight effect catalog tokens
- find Duck Clean Levelling presets
- see timeline audio processing vocabulary

## What it does

Runs the public `fairlight effect catalog` CutAgent command.

## Do not use when

Do not use this command to answer “which effects are on this clip”; use `fairlight effect list --clip NAME`. Do not treat returned BMD tokens as installed AU/VST3 plugins; use `fairlight effect plugin-catalog` for local availability. For actual current dynamics or EQ values, use `fairlight dynamics read`, `fairlight eq read`, or `fairlight effect params` with the correct scope.

## Preflight and readback

Before running, confirm the intended Disk project and active timeline; this command addresses the current timeline only and requires one to exist. Save the project first when the GUI has just changed mixer configuration and disk freshness matters. If the next decision concerns an active clip effect, follow with `fairlight effect list` or `slot-scan`; if it concerns plugin availability, follow with `plugin-catalog`.

## Public arguments and options

This command has no command-specific arguments or options.

## Examples

- `cutagent fairlight effect catalog --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
