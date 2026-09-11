# `fairlight vca list`

Syntax: `cutagent fairlight vca list`

## Search terms

- list Fairlight VCA labels
- show available VCA names
- inspect VCA label pool
- find VCA 1
- list VCA fader labels
- enumerate VCA 1 through 128
- check VCA naming slots
- discover Fairlight VCA label offsets
- VCA label inventory
- see if VCA label exists

## What it does

Runs the public `fairlight vca list` CutAgent command.

## Do not use when

Do not use the row count as the number of created/configured VCAs.
Use `fairlight bus list` for main-output and bus labels. VCAs, groups, and buses have different mix/edit semantics.
Those fields are not decoded by this route.
It resolves the currently open local Disk project's active timeline.

## Preflight and readback

Before reading, confirm that the intended project and timeline are active with `project info` and `timeline info`.
If the real question is active membership or VCA behavior, continue with manual DaVinci Resolve inspection. Verify the VCA Assign dialog, actual member tracks, fader coupling, mute/solo, automation, and audition/render. There is no CutAgent CLI membership readback to compose after this list.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command cannot distinguish unused defaults, created VCA strips, active membership, or deleted/recreated controls.
- The scanner only recognizes the literal default pattern `VCA N`.
- Thus it does not silently report `VCA 100` from the beginning of `VCA 1000`.
- There is no `--limit`; a default pool may produce a large JSON response.
- No matching row raises a validation error; multiple rows with the same name are treated as ambiguous rather than guessed.
- It does not return an empty list as if there were no labels.
- An agent must branch on them even when `vcas` is non-empty.

## Examples

- `cutagent fairlight vca list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
