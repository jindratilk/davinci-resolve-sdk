# `dctl scaffold`

Syntax: `cutagent dctl scaffold KIND NAME [--output VALUE] [--overwrite]`

## Search terms

- create DCTL file
- scaffold custom color transform
- generate identity DCTL
- start a .dctl source
- make DCTL template
- create ACES IDT source skeleton
- create ACES ODT source skeleton
- start DCTL transition
- boilerplate DaVinci CTL transform

## What it does

Prepare a DCTL file.

## Do not use when

Use the official DaVinci Resolve DCTL/ACES specifications or a role-specific template when authoring a real transition, ACES IDT/ODT, texture transform or DCTL plugin.

## Preflight and readback

Afterward, inspect and replace the identity body, add the exact signatures/macros/UI parameters required by the intended DCTL role, then run `dctl validate` and a real DaVinci Resolve compile/render test. Version-control the source before installing it.

## Public arguments and options

- `KIND` (required) — transform|transition|aces-idt|aces-odt
- `NAME` (required) — DCTL name
- `--output` (optional) — Output .dctl path
- `--overwrite` (optional, default: `false`) — Replace an existing scaffold file

## Boundaries and gotchas

- Kind matching is exact and case-sensitive.
- Without `--output`, the name also becomes the path.
- Dry-run performs the same kind and conflict validation.
- It is only a neutral starting body.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent dctl scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
