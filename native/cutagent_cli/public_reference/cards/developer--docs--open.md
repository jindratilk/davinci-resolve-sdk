# `developer docs open`

Syntax: `cutagent developer docs open SECTION`

## Search terms

- open DaVinci Resolve SDK docs
- show DCTL README
- view OpenFX developer manual
- open Fusion Fuse SDK PDF
- launch workflow integration docs
- show codec plugin README
- open local developer documentation
- view LUT SDK README
- open Fusion template docs

## What it does

Open local DaVinci Resolve documentation.

## Do not use when

Use `developer docs list` to inspect all 11 known documentation paths and existence states. Use `developer examples list` for sample source and `developer sdk doctor` for overall SDK/toolchain availability.
Do not use this macOS GUI launcher in a headless job or on Windows. Do not use it to open arbitrary paths—the section is restricted to the eight predefined SDK categories.

## Preflight and readback

Ensure a GUI launch and possible focus change are acceptable.
Afterward, require both `opened:true` and `returncode:0`, then confirm the expected application/document actually appeared. Read/search the document separately and record its version. A zero launcher status proves only that macOS accepted the open request, not that a human saw readable content.

## Public arguments and options

- `SECTION` (required) — scripting|workflow|dctl|lut|fusion-template|fuse|openfx|codec

## Boundaries and gotchas

- The command opens only the first existing candidate, not every document in the section.
- The command does not verify window creation, foreground focus, document readability or the default application used.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent developer docs open --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
