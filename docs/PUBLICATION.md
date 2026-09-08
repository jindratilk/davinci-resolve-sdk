# Prepared public source release

Standalone Free marker acceptance is retained in the source evidence. The initial public release uses the clean source snapshot procedure below; npm publication remains inactive.

Proposed independent repository: `jindratilk/davinci-resolve-sdk`. Authenticated GitHub lookup on 2026-09-08 could not resolve that repository. Proposed npm name `davinci-resolve-sdk` returned E404. Neither observation reserves a name; check availability again immediately before publication. Do not create an official Blackmagic affiliation or imply endorsement.

`LICENSE` retains the original MIT copyright attribution to CutAgent because the grant requires preservation of that notice. This is legal provenance, not product branding. README, package name and consumer imports use DaVinci Resolve SDK. Preserve `PROVENANCE.md` and `THIRD_PARTY_NOTICES/` in the public source release. Retained internal symbols remain compatibility details.

## Local artifact preparation

From a clean reviewed standalone commit, run the documented source tests, `npm run build`, `npm run verify:source` and `node scripts/smoke-packed-consumer.mjs`. Create the source archive using `git archive` of that exact commit; it includes tracked files only and therefore excludes rejected-sdk-export, local dependencies, venvs and private runtime state. Record its SHA256 alongside the exact source SHA. The client tarball is an additional artifact and does not replace the companion native runtime source.

## Publication commands, after acceptance

Create a fresh empty directory outside the source tree and unpack the reviewed source archive there. Initialize a fresh public history from those reviewed files; do not push the private transfer repository or its unrelated branches. Inspect `git status --short` before committing.

```sh
git init -b main
git add .
git commit -m 'Initial independent DaVinci Resolve SDK source release'
gh repo create jindratilk/davinci-resolve-sdk --public --source . --remote origin --push
```

The `gh repo create` line is the first public write and remains unexecuted. Before running it, replace neither the owner nor repository name silently, confirm exact reviewed archive hash/Free acceptance and recheck name availability. This publishes source only. Keep npm packages `private: true` until a separate package activation review; no npm publish command is part of this source release.

No installer/signature/attestation assets are fabricated here. Source and client archives are accompanied by their checksums and exact acceptance evidence; native acceptance must name the actual tested commit and transport/platform.
