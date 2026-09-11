# `developer sdk-doctor`

Syntax: `cutagent developer sdk-doctor`

## Search terms

- run sdk-doctor
- check DaVinci Resolve SDK install
- quick Developer SDK diagnosis
- find missing SDK build tool
- inspect macOS Resolve developer paths
- check CMake Xcode Node Python
- troubleshoot plugin SDK environment
- verify Developer README files
- legacy flat SDK doctor alias

## What it does

Check local DaVinci Resolve resources.

## Do not use when

Prefer `developer sdk doctor` for a structurally nested SDK command path or `developer doctor` for the shortest form; neither provides extra checks.

## Preflight and readback

Before invoking, preserve the exact hyphenated spelling (`sdk-doctor`) and run under the target developer account/PATH. Decide which plugin/script/DCTL workflow's prerequisites actually matter.
Afterward, inspect null tool values and individual doc rows, then run version/license checks and build a corresponding SDK example.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- A returned xcodebuild path does not verify Xcode installation selection, license acceptance, target SDK or signing.

## Examples

- `cutagent developer sdk-doctor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
