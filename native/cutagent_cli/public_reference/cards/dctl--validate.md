# `dctl validate`

Syntax: `cutagent dctl validate PATH`

## Search terms

- validate DCTL file
- check .dctl source
- inspect DCTL before install
- test custom color transform file
- verify DCTL extension
- check DCTL entry point marker
- preflight DaVinci CTL
- is this DCTL valid
- lint DCTL source
- check generated DCTL

## What it does

Check a DCTL file.

## Do not use when

Do not use this boolean as proof that DaVinci Resolve can compile or execute the source. Install/test in an isolated user location and run a real DaVinci Resolve render for that. Use role-specific review for transitions, ACES IDTs/ODTs, alpha modes, textures and DCTL plugins; this validator cannot distinguish them.
Use `dctl list` to discover candidates, `dctl scaffold` to create a starting file, and `dctl install` only after manual/source validation.

## Preflight and readback

Before validation, resolve the intended local file and know its expected role.
If false, inspect suffix and required entry-point markers. If true, review the complete source and compile/render it in the intended DaVinci Resolve version/edition before installation or production use.

## Public arguments and options

- `PATH` (required) — .dctl path

## Boundaries and gotchas

- Invalid UTF-8 does not fail validation and can obscure byte-level source corruption.
- Dry-run does not skip reading.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent dctl validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
