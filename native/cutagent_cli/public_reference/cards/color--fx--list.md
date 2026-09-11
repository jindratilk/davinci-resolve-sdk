# `color fx list`

Syntax: `cutagent color fx list`

## Search terms

- list available color effects
- show Fusion grading templates
- find built-in Glow Blur Sharpen
- inspect FX template registry
- discover CutAgent color FX names
- check template effect paths

## What it does

List Fusion grading effects.

## Preflight and readback

Run it before effect application to capture the exact canonical/alias spelling and template path. After application, do not re-run this registry as verification—the registry is independent of the clip; inspect the target Fusion tools and render instead.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command does not parse the Fusion text or the optional sibling manifest, so it cannot tell what tools a template imports.
- Although it does not contact DaVinci Resolve, the CLI authorization layer still applies.

## Stable public error codes

- `AUTH_REQUIRED`

## Examples

- `cutagent color fx list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
