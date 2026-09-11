# `page switch`

Syntax: `cutagent page switch PAGE`

## Search terms

- go to Color page
- open Edit page
- switch to Fairlight
- go to Deliver page
- open Fusion workspace
- change DaVinci Resolve page
- navigate to Media page
- switch Resolve workspace
- go to Cut page

## What it does

Switch the DaVinci Resolve page.

## Do not use when

Do not use `page switch` as a substitute for a domain operation: going to Color does not add a grade, Fairlight does not change audio, and Deliver does not start rendering. Do not use it to focus a specific inspector, palette, mixer, node, bin, or render preset; page-sensitive GUI commands need their own panel setup. Do not pass UI labels outside the fixed seven-page contract (for example `project manager` or `preferences`).

## Preflight and readback

Run the switch, then verify with `page current` and any command-specific readiness check. After the workflow, switch back to the captured previous page if preserving UI context is part of the operation; page restoration does not restore panel layout or selection automatically.

## Public arguments and options

- `PAGE` (required) — Page name: media, cut, edit, fusion, color, fairlight, deliver

## Boundaries and gotchas

- Page input is case-insensitive, but only the seven exact canonical page names are allowed.
- They do not preserve which panel or control was focused on the previous page.

## Examples

- `cutagent page switch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
