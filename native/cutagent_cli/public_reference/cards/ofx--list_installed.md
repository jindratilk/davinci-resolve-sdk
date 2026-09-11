# `ofx list-installed`

Syntax: `cutagent ofx list-installed`

## Search terms

- list installed OpenFX plugins
- inspect user OFX bundles
- find .ofx.bundle
- list .bundle plugins
- recursive OFX bundle list
- OFX duplicate list rows
- user OpenFX plugin paths
- verify OFX installation

## What it does

List user-installed OpenFX bundles.

## Do not use when

Do not interpret one row as one unique installed plugin.
Do not count rows without deduplicating by canonical path. Do not uninstall twice based on duplicate rows.
Do not treat a matching suffix as proof of a valid OpenFX bundle.
Do not use global dry-run as a hypothetical inventory.
Do not use listing as proof that DaVinci Resolve has discovered, loaded, trusted, or successfully rendered with a plugin.

## Preflight and readback

Before execution, establish the expected user OFX root and whether nested bundle directories are intentional. If the root is absent, expect a successful empty array.
Run in JSON mode. Canonicalize and deduplicate rows by exact resolved path before counting, selecting, or removing plugins.
After selecting a path, inspect its complete bundle structure, identifier, version, executable permissions, architectures, dependencies, signatures, hashes, provenance, and license.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Even `ofx validate` would only check existence and suffix, not plugin correctness.

## Examples

- `cutagent ofx list-installed --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
