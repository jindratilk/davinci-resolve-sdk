# `render import-preset`

Syntax: `cutagent render import-preset PATH`

## Search terms

- import render preset
- import drpx bundle
- import render preset XML
- preset filename conflict
- modified Deliver preset
- render preset round trip
- rename preset XML

## What it does

Import a render preset.

## Do not use when

Do not pass an arbitrary XML, burn-in preset, or unrelated settings file.
Do not pass a bundle containing multiple XML files unless the intended XML file is supplied directly.
The command returns an explicit no-op instead.
Do not edit a preset variant without renaming its XML filename to the desired new preset name.

## Preflight and readback

Before execution, inspect the bundle recursively, require exactly one intended XML file, validate its provenance/content, rename the file to the new preset name, and run `render presets` to rule out normalized-name conflicts.
Use dry-run only to review the provided path text.

## Public arguments and options

- `PATH` (required) — Path to an exported `.drpx` preset bundle directory or a direct XML preset file.

## Boundaries and gotchas

- A missing path and a non-XML file both produce successful dry-run plans.
- That no-op does not verify whether existing settings equal the XML variant.
- It does not load the preset or verify its settings.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render import-preset --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
