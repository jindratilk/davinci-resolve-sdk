# `render burnin import`

Syntax: `cutagent render burnin import PATH`

## Search terms

- import burn-in preset for rendering
- install data burn preset from render workflow
- add timecode overlay preset file
- restore render window burn settings
- register burn-in preset before delivery
- import slate overlay configuration
- add review watermark preset
- load portable data burn-in file

## What it does

Import a burn-in preset.

## Do not use when

Use `render burnin load` after import to activate the preset for subsequent rendering, or `clip burnin load` for one timeline item. The shorter `burnin preset import` is behaviorally equivalent when not already in a render-oriented workflow.

## Preflight and readback

Inventory the global Data Burn-In preset menu and settings XML, validate provenance/content in a disposable user profile, and ensure the basename will not collide. After import, inspect the UI/XML for the derived name, load it, check every field/style, and render a test frame.

## Public arguments and options

- `PATH` (required) — Burn-in preset file path

## Boundaries and gotchas

- Dry-run, when set globally, does not inspect the file or detect an existing same-name preset.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent render burnin import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
