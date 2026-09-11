# `page current`

Syntax: `cutagent page current`

## Search terms

- which DaVinci Resolve page is open
- current Edit Color Fairlight page
- am I on Color page
- DaVinci Resolve UI context
- verify page switch
- current Resolve workspace
- get current page

## What it does

Check the current DaVinci Resolve page.

## Do not use when

Do not use `page current` to navigate; use `page switch`. Do not treat `page: color` as proof that a specific Color panel, node, clip, or viewer control is selected; use the relevant color readback/preflight.

## Preflight and readback

Page-sensitive commands may still need their own panel/selection/readiness check after this readback.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- A successful value establishes application page state only.
- It does not detect loading transitions, overlays, popups, or modal dialogs.

## Examples

- `cutagent page current --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
