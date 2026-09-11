# `developer doctor`

Syntax: `cutagent developer doctor`

## Search terms

- check DaVinci Resolve Developer SDK
- diagnose local SDK setup
- developer toolchain check
- find SDK documentation root
- check node npm python cmake make xcodebuild
- inspect developer environment
- verify Resolve Developer files
- SDK installation health
- find user support root
- troubleshoot missing developer tools

## What it does

Check local DaVinci Resolve resources.

## Do not use when

Use `developer docs list/open` for document-specific work, and run each compiler/tool with its version or diagnostic flags when build readiness matters.
Do not use this command as proof an OpenFX/codec/Fuse build will work, that Xcode licensing/signing is configured, or that the SDK matches the installed DaVinci Resolve version. `developer sdk doctor` and `developer sdk-doctor` are aliases of the same function, not deeper tests.

## Preflight and readback

On Windows, do not interpret the hard-coded macOS paths as the real SDK installation.
Afterward, inspect every required field individually. Resolve null tools, verify executable versions/architectures and Xcode license/SDK selection, confirm document readability, and compare SDK files with the installed DaVinci Resolve build.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- A path does not prove the executable runs, has a compatible version/architecture, can find headers/libraries or is licensed/configured.
- `xcodebuild:"/usr/bin/xcodebuild"` does not prove Xcode is selected or its license accepted.
- Documentation is the same static 11-path whitelist used by `developer docs list`; it is not recursive and does not inspect contents or SDK version.

## Examples

- `cutagent developer doctor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
