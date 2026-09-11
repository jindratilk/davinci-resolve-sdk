# `color page resolvefx-param-discover`

Syntax: `cutagent color page resolvefx-param-discover --fx VALUE`

## Search terms

- discover ResolveFX parameters
- list OFX input descriptors
- find plugin parameter IDs
- inspect ResolveFX controls and types
- get valid parameter names for effect
- find min max and default OFX values
- determine bool int double string parameter type
- inspect installed ResolveFX through Fusion
- prepare resolvefx-param-set

## What it does

Read DaVinci Resolve effect controls.

## Do not use when

Use `resolvefx-list` when only installed effect names/categories/IDs are needed. Use `resolvefx-param-set` only after selecting a descriptor ID/type and still require rendered proof.

## Preflight and readback

Before discovery, identify the exact installed effect with `resolvefx-list`; prefer its full plugin ID when similarly named versions exist.

## Public arguments and options

- `--fx` (required) — ResolveFX name or plugin id to inspect through a temporary Fusion comp

## Boundaries and gotchas

- The result is intentionally marked descriptor-readback-only/partial.
- It does not export a frame or verify a Color-page grade.
- `--dry-run` only echoes the requested text.
- It does not normalize/resolve the plugin, create a comp, or prove that any descriptor exists; even a nonexistent name previews successfully.

## Examples

- `cutagent color page resolvefx-param-discover --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
