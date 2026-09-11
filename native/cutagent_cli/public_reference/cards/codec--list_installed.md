# `codec list-installed`

Syntax: `cutagent codec list-installed`

## Search terms

- list installed codec plugins
- show DaVinci Resolve IOPlugins
- find custom encoder installation
- inspect user codec bundles
- verify codec plugin was copied
- inventory local codec dylibs

## What it does

List installed codec add-ons.

## Do not use when

Use `codec validate PATH` to check one candidate’s existence and accepted suffix, and operating-system tools plus a real DaVinci Resolve render smoke to prove architecture, signing, loadability, or encoder operation.

## Preflight and readback

Run it before install/uninstall to capture the existing exact relative paths and again afterward to compare the inventory. For install verification, also inspect the returned path and compare it to the source.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The list does not report size, version, architecture, signature, manifest, checksum, load status, or compatibility with the running DaVinci Resolve version.

## Examples

- `cutagent codec list-installed --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
