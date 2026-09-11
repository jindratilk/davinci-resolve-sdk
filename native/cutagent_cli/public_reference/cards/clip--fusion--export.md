# `clip fusion export`

Syntax: `cutagent clip fusion export INDEX PATH [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- export Fusion composition setting
- save clip node graph as setting file
- back up Fusion comp
- create reusable .setting
- copy Fusion comp to file
- preserve composition before deleting

## What it does

Export a Fusion composition as template file.

## Do not use when

Use project/timeline export for a whole edit, a macro/template workflow for intentionally portable user controls, and `clip fusion tools`/`tool-get` for inspection without writing a file. Use `clip fusion import` only after reviewing that content and its target semantics.

## Preflight and readback

List comps immediately before export so the numeric index is current, and inspect the selected comp in Fusion.

## Public arguments and options

- `INDEX` (required) — Composition index
- `PATH` (required) — Output .setting file path
- `--clip` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip fusion export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
