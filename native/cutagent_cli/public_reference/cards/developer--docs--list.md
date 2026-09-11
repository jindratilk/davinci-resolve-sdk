# `developer docs list`

Syntax: `cutagent developer docs list`

## Search terms

- list DaVinci Resolve SDK docs
- find local developer documentation
- locate scripting README
- find DCTL SDK manual
- show OpenFX developer docs
- locate Fusion Fuse SDK PDF
- check developer docs installation
- find codec plugin README
- list workflow integration docs
- show local Resolve Developer paths

## What it does

List local DaVinci Resolve documentation.

## Preflight and readback

Before running, confirm this machine is expected to have the macOS DaVinci Resolve Developer SDK installed. Use JSON output so paths containing spaces remain unambiguous.
Afterward, filter rows by section and require `exists:true`, then verify the target is a readable regular file.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Only 11 hard-coded relative paths are emitted even if the Developer tree contains many other manuals.
- It does not prove readability, correct file type, nonzero size or valid PDF/text content.
- The command does not locate Windows Developer documentation.

## Examples

- `cutagent developer docs list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
