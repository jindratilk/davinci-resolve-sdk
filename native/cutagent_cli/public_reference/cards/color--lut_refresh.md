# `color lut-refresh`

Syntax: `cutagent color lut-refresh`

## Search terms

- refresh LUT list
- rescan DaVinci Resolve LUT folder
- make newly installed LUT appear
- reload project LUT library

## What it does

Refresh the project LUT list.

## Do not use when

Use `color lut --set` to install/attach a local file, `color page lut-library-import` for managed library import, and `color lut` getter to verify a node assignment. Do not use refresh as proof that a particular file was found, parsed, compatible, or applied; the response contains no library diff or file list.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not create the `LUT/CutAgent` folder or copy source files.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color lut-refresh --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
