# `clip fusion tools`

Syntax: `cutagent clip fusion tools [--comp VALUE] [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- list Fusion nodes in composition
- inspect Fusion tool graph
- show MediaIn MediaOut nodes
- enumerate tools by comp index
- find node types on clip
- check imported Fusion setting contents
- inspect Fusion comp before editing input

## What it does

List Fusion nodes.

## Do not use when

Use purpose-built graph inspection if connections or modifiers/keyframes matter.

## Preflight and readback

After import or graph mutation, rerun tools and compare the full type sequence, then inspect connections/render because matching types do not prove correct wiring.

## Public arguments and options

- `--comp` (optional, default: `1`) — Composition index
- `--clip` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- UI-only/imported objects can appear as tools.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip fusion tools --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
