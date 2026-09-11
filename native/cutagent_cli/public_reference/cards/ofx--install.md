# `ofx install`

Syntax: `cutagent ofx install PATH_OR_BUNDLE [--overwrite]`

## Search terms

- install OpenFX bundle
- copy OFX plugin to user folder
- install .ofx.bundle
- OpenFX install dry-run
- overwrite OFX plugin bundle
- install custom OFX path
- recursive OFX bundle copy

## What it does

Install an OpenFX bundle into the user OFX folder.

## Do not use when

Do not install untrusted code or bundles.
Do not treat `ofx validate` as meaningful bundle validation.
Do not expect immediate discovery by an already-running DaVinci Resolve process. The command does not refresh, restart, load, or interrogate the application.
Do not treat `installed:true`, a list entry, or matching bytes as proof the plugin can load or render.

## Preflight and readback

Run `ofx validate` only as a shallow suffix preflight, then global dry-run.
Restart or refresh DaVinci Resolve only in a controlled environment. Prove host discovery, plugin identifier/version, parameter availability, image processing, and render output separately.
For cleanup, use `ofx uninstall` with the exact installed relative name, prove the destination absent, and rerun the list. Remove newly created empty OFX parent folders only when independent pre-state established that they did not exist.

## Public arguments and options

- `PATH_OR_BUNDLE` (required) — OpenFX bundle/path
- `--overwrite` (optional, default: `false`) — Replace an existing installed bundle

## Boundaries and gotchas

- `--overwrite` is the only command-specific option.
- Installation does not refresh, restart, or contact DaVinci Resolve.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent ofx install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
