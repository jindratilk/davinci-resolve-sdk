# `burnin preset export`

Syntax: `cutagent burnin preset export NAME PATH`

## Search terms

- export data burn-in preset file
- save window burn configuration to disk
- share timecode overlay preset
- back up burn-in settings
- copy slate overlay configuration
- export review watermark layout
- create portable burn-in preset

## What it does

Export a burn-in preset.

## Do not use when

Use `burnin preset import` to register a preset file in DaVinci Resolve and `burnin load` to activate a saved preset on the current project.

## Preflight and readback

Confirm the preset appears in the Data Burn-In option menu and inspect its fields.

## Public arguments and options

- `NAME` (required) — Burn-in preset name
- `PATH` (required) — Export path

## Boundaries and gotchas

- The selector must first appear in the XML-derived catalog; otherwise the command fails before calling DaVinci Resolve.
- Numeric selectors are 1-based only within the parsed list.
- Name matching supports exact, unique case-insensitive/normalized, unique substring, or catalog index.
- Multiple normalized/partial matches are rejected as ambiguous.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent burnin preset export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
