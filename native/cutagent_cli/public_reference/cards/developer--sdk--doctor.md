# `developer sdk doctor`

Syntax: `cutagent developer sdk doctor`

## Search terms

- diagnose Developer SDK
- check SDK under developer namespace
- inspect DaVinci Resolve SDK tools
- verify local plugin build prerequisites
- locate Resolve Developer root
- check SDK docs and toolchain
- find missing cmake for SDK
- inspect macOS developer setup
- verify node npm python Xcode tools
- SDK doctor report

## What it does

Check local DaVinci Resolve resources.

## Do not use when

Use `developer doctor` if a shorter equivalent invocation is preferred, or `developer sdk-doctor` only for the flat hyphenated compatibility surface.
Do not use the report as a plugin build, compiler-version, SDK compatibility or code-signing check. Follow it with tool-specific version/license/build commands and a real SDK sample build.

## Preflight and readback

Before running, launch it from the same user and PATH used for development; version-manager paths and missing tools are shell-dependent. Treat it as macOS-only path discovery.
Afterward, explicitly decide which of the six tools and 11 docs the intended SDK task needs. Execute found tools to verify version/architecture, check Xcode selection/license and CMake availability, confirm headers/examples, then build/run the smallest relevant sample.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The tool list mixes unrelated workflows; CMake is not required for every DCTL/script task, while other plugin dependencies may be absent from the list entirely.
- Dry-run is not hypothetical.

## Examples

- `cutagent developer sdk doctor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
