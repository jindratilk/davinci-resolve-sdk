# `clip fusion import`

Syntax: `cutagent clip fusion import PATH [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- import Fusion setting onto clip
- apply .setting composition to timeline item
- load saved Fusion node graph
- transfer Fusion comp from file
- attach exported Fusion effect
- install node graph on shot

## What it does

Import a Fusion composition template file onto a clip.

## Do not use when

Use `clip fusion add` for a fresh default comp, `clip fusion tool-set` for one known parameter, and a purpose-built effect command when the desired workflow requires construction and semantic verification. Do not assume this creates a new indexed comp; use an isolated target or explicitly load/create the intended destination and compare before/after.

## Preflight and readback

Import only after exact clip selection. Then list comps, inspect every affected index with `tools`, compare names/count/graph to the baseline, inspect the Viewer, and render a representative range.

## Public arguments and options

- `PATH` (required) — .setting file path
- `--clip` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.
- Agents must never predict append semantics from the command name.
- Review `layout` diagnostics rather than assuming only processing nodes were changed.
- Imported settings can depend on Studio-only tools, third-party plugins, media paths, fonts, or a different DaVinci Resolve version.

## DaVinci Resolve editions

Review `layout` diagnostics rather than assuming only processing nodes were changed. - Imported settings can depend on Studio-only tools, third-party plugins, media paths, fonts, or a different DaVinci Resolve version.

## Examples

- `cutagent clip fusion import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
