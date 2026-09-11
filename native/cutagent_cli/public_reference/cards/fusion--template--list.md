# `fusion template list`

Syntax: `cutagent fusion template list`

## Search terms

- list Fusion templates
- discover setting templates
- bundled Fusion template
- user Fusion template
- resolve-templates list
- available .setting files
- CutAgent template catalog
- Fusion template path
- template source bundled user
- inspect available templates

## What it does

List Fusion templates.

## Do not use when

Do not use this command to discover DaVinci Resolve user/system Macros or Templates directories. `fusion template apply` has a broader bare-name resolver than this list command.
Do not use it to recursively inventory nested template folders; only direct children are listed.
Do not use it to prove a listed file is readable, valid, importable, visually correct, or dependency-complete.
Do not expect dry-run to preview a different operation. There is no dry-run branch; discovery is performed normally.
Do not use it to install, remove, rename, or edit templates.

## Preflight and readback

Listing only trusts the filename suffix.
No DaVinci Resolve cleanup is needed.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Duplicate filenames in different directories can appear as separate rows.

## Examples

- `cutagent fusion template list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
