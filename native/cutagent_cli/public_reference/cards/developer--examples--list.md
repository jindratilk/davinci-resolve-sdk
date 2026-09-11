# `developer examples list`

Syntax: `cutagent developer examples list [--section VALUE]`

## Search terms

- list DaVinci Resolve SDK examples
- browse DCTL example files
- list OpenFX sample source
- find codec plugin examples
- show workflow integration samples
- find Fusion Fuse examples
- inventory Developer SDK files
- locate Fusion template samples
- get SDK example relative paths

## What it does

List DaVinci Resolve examples.

## Do not use when

Use `developer docs list` for the small curated documentation whitelist, `developer examples copy` to extract one selected row, and a section-specific validator/build command to determine whether a file is usable. Use `dctl list` when the question is installed/user DCTL inventory rather than SDK example content.
Do not use this as proof every row is executable or self-contained.

## Preflight and readback

On machines without the macOS SDK root, expect an empty result rather than a missing-install error.
Verify SDK/application version compatibility and licenses before reusing code.

## Public arguments and options

- `--section` (optional) — Optional SDK section

## Boundaries and gotchas

- Without `--section`, keys are sorted alphabetically as codec → dctl → fuse → fusion-template → openfx → scripting → workflow.
- Section input is trimmed and lowercased; returned file/relative-path matching remains case-sensitive for later copy use.
- Duplicate basenames can occur across directories/sections.
- Preserve section plus relative path; `developer examples copy` given only a basename takes the first match.
- Roots are hard-coded for macOS and do not find Windows SDK examples.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent developer examples list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
