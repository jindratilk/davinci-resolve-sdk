# `timeline voice-isolation get`

Syntax: `cutagent timeline voice-isolation get TRACK`

## Search terms

- get track voice isolation
- Fairlight voice isolation state
- audio track AI isolation amount
- timeline audio track processing
- DaVinci Resolve 21 voice isolation

## What it does

Read timeline voice isolation state.

## Do not use when

Do not use this for clip-level Voice Isolation.

## Preflight and readback

Before execution, activate the intended timeline; list audio tracks; verify the one-based audio-track index and name; and decide whether track-level or clip-level processing is actually intended.

## Public arguments and options

- `TRACK` (required) — Audio track index

## Boundaries and gotchas

- It does not query audio-track count or name before reading.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline voice-isolation get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
