# `color page resolvefx-list`

Syntax: `cutagent color page resolvefx-list [--category VALUE]`

## Search terms

- list installed ResolveFX
- get ResolveFX plugin IDs
- browse OFX effects by category
- check whether Box Blur is installed
- find Color Space Transform plugin ID
- see available blur color light effects
- map ResolveFX UI name to technical ID
- check Studio effect availability

## What it does

List installed DaVinci Resolve effects extensions from the live Fusion registry.

## Do not use when

Use `resolvefx-param-discover` after choosing one effect to inspect its possible input descriptors. Use `resolvefx-add` only after confirming an exact plugin ID and then perform visual proof. Do not treat presence in this registry as proof that the current edition/GPU can instantiate or render the effect.

## Preflight and readback

Confirm actual Studio/Free entitlement and instantiate/discover/render the chosen effect before claiming support.

## Public arguments and options

- `--category` (optional) — Filter by ResolveFX category substring

## Boundaries and gotchas

- `--category` searches category text only, never effect name or plugin ID.
- `--category Blur` matched `Resolve FX Blur`; searching `Box Blur` as a category would return nothing.
- A whitespace-only filter searches for that literal whitespace; an empty string is effectively no filter through the wrapper.
- The command has no dry-run branch.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color page resolvefx-list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
