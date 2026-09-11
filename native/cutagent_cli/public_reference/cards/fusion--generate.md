# `fusion generate`

Syntax: `cutagent fusion generate --template VALUE [--text VALUE] [--image VALUE] [--bold-style VALUE] [--output VALUE]`

## Search terms

- generate Fusion setting
- render setting template
- substitute TextPlus text
- CharacterLevelStyling template
- generate setting with image
- styled text setting generator
- generated setting dry-run writes
- validate generated setting
- template unresolved placeholder
- Fusion setting text escaping

## What it does

Generate a Fusion template.

## Do not use when

Do not treat generation success as proof of a valid Fusion graph.
Use frame export for actual visual proof.
Do not omit `--text` when the template requires resolved text/styling placeholders.
Do not use global dry-run to protect an output path.
Do not use an untrusted template or output location without reviewing both.
Do not assume an existing `--image` path is a usable image.

## Preflight and readback

Before execution, inspect the template placeholders, graph topology, MediaOut path, node classes, ViewInfo layout, and any hard-coded media/font dependencies.
Confirm every supplied option has a matching recognized placeholder. An image option is rejected when no image placeholder exists, but text/styling options do not receive an equivalent required-placeholder check.
Choose a unique output path and preserve any existing file yourself. Global dry-run is not safe for path preview.
After generation, inspect unresolved placeholder tokens and verify escaped text, image path, styling ranges, and custom style quoting.
Run `fusion setting validate OUTPUT`; generation performs no structural validation.

## Public arguments and options

- `--template/-t` (required) — Path to .setting template file
- `--text` (optional) — Text to insert (supports **bold**)
- `--image` (optional) — Image path to insert
- `--bold-style` (optional, default: `"ExtraBold"`)
- `--output/-o` (optional) — Output .setting file path

## Boundaries and gotchas

- Without `--output`, JSON includes the entire rendered setting text.
- The generator does not add MediaOut, repair topology, add ViewInfo, resolve fonts, or validate node registrations.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion generate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
