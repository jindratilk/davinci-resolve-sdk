# `embedded status`

Syntax: `cutagent embedded status`

## Search terms

- check embedded bridge status
- is CutAgent.lua installed
- inspect Lua bridge version
- diagnose CutAgent bridge auth
- check embedded protocol mismatch
- find installed CutAgent script
- verify App Store sandbox install
- check Windows Lua socket DLL
- show broker host and port
- determine why embedded commands fail

## What it does

Check CutAgent support in DaVinci Resolve.

## Do not use when

Do not use this as evidence that a particular DaVinci Resolve command, project or timeline is ready.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Automation must inspect these fields.
- Auth validity here only checks that a non-empty token exists in parseable JSON.
- It does not cryptographically test the token until the broker request.
- Do not try to infer or log it.
- Installation/current checks do not prove the already-running Lua client loaded the on-disk file.
- Its presence means cleanup is still required even if the Utility script is current.
- This affects broker status only, not file hashing.
- `--dry-run` is not specially handled.

## Examples

- `cutagent embedded status --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
