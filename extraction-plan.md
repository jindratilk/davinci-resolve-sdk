# Standalone DaVinci Resolve SDK: extraction boundary

Status: dependency plan complete; implementation and release unstarted. Source inspected: `eb934734f5cb2d223192980a3b951f7509b0beec`. User authorization permits a separate open-source distribution of the selected SDK/runtime. Existing commercial release rules continue to apply to the original product; they are not a reason to refuse the authorized fork.

## Smallest complete distribution

The SDK folder alone is insufficient. Its `CutAgent.connect()` calls `connectDesktop()`, discovers a live desktop process and negotiates the desktop distribution contract. The SDK has no independent native execution engine. The working chain needs all of the following owners:

| Proposed standalone directory | Source responsibility | Extraction rule |
| --- | --- | --- |
| `packages/sdk/` | Public `sdk/src/`, public generated schemas and typed operations | Preserve existing semantic API initially; introduce an explicit standalone connector/distribution contract. Do not masquerade as the installed desktop app. |
| `packages/local-runtime/` | Selected SDK bridge services, operation repository, mutation policy, artifact handling | New small composition root. Import selected SDK services and their reviewed dependencies; never copy `bridge/app/create-app.js` wholesale. |
| `packages/native-runtime/` | Selected Python prepared-action host, descriptor handlers and needed `core` modules | Real native implementation required. Keep exact target, revision, prepare/execute, recovery and verification semantics. Do not replace them with a raw command wrapper. |
| `packages/native-runtime/assets/` | Installed Free Lua transport and necessary templates | Incorporate the pending reviewed Free spool commit from its owner. Keep the Studio external scripting adapter. |
| `contracts/` | Relevant shared SDK contract source and generators | A standalone source of truth must generate its own consumers without the CutAgent monorepo. New local-principal and standalone distribution contracts belong here. |
| `tests/` and `examples/` | Selected SDK, authority and transport tests plus one representative local edit/render | Run from a clean standalone checkout with no CutAgent install, account, cloud, private documentation or monorepo paths. |

These are proposed directories, not placeholder packages claiming functionality. Only this plan and source inventory have been created. The generated SDK snapshot attempt is quarantined separately.

## Commercial admission seams that must change together

1. `sdk/src/connection/desktop-transport.ts`: replace the hard-coded desktop connector for the new distribution with same-user local-runtime discovery. Keep PID/instance binding, restrictive discovery ownership, bounded bootstrap, protocol/version negotiation and session closure. Update distribution compatibility schemas and generator consumers together; do not set the new runtime's type to `desktop_managed`.
2. `bridge/app/sdk-runtime-route.js:156`: the current `refreshAndRequireSubscription()` refreshes commercial credentials and requires an active subscription before bootstrap. The standalone composition needs a local bootstrap authority instead. Keep exact-route bootstrap consumption and replay protection in `sdk-runtime-service.js`.
3. `bridge/services/sdk-authenticated-request.js`: `captureAuthenticatedSdkRequest()` demands an access token, refresh-token state and account subject from the desktop broker. Replace this abstraction in the fork with an immutable **local principal snapshot**: installation identity, OS-user ownership, runtime-instance identity and credential generation. Retain the generation/current-identity assertion around asynchronous work. Do not fabricate a paid account or everlasting subscription to satisfy existing interfaces.
4. `bridge/services/sdk-prepared-action-coordinator.js`: `authorizationService.authorizePreparedAction()` currently obtains a cloud-signed authorization token after exact receipt/impact capture. Replace the commercial issuer with a local receipt-bound admission issuer. Admission remains after mutation-policy evaluation and before execute dispatch. Keep expiration, one-use execution, cancellation and recovery binding.
5. `cutagent-cli/cutagent_cli/sdk_prepared_action.py`: `_verify_authorization()` pins commercial issuer/audience and `_assert_current_context()` hashes account and subscription alongside session/project/timeline/artifacts. Change the standalone contract to local principal and runtime generation on both sides. Verify locally issued short-lived tokens against a runtime-pinned public key established through the private bootstrap. Preserve receipt, impact, private binding, project, timeline, artifact and idempotency checks. A token-verification bypass or `true` entitlement result is not an implementation.
6. `cutagent-cli/cutagent_cli/authz.py` and import-time guards in `adapters.py`/`core/__init__.py`: extract local command admission separately from the commercial token verifier. Standalone subprocesses must still accept only bounded parent-authorized work. Do not enable the development bypass, accept arbitrary unauthenticated requests, reuse cloud issuer keys, or modify the original commercial runtime.

Local authority keys must be created with exclusive ownership in the standalone application's private state directory. Bootstrap must prove same-user endpoint possession before pinning an instance key. User ownership/ACL checks are platform-specific. There is no security boundary against a malicious process with full access to the same user's account; the existing product does not justify pretending otherwise.

## Protections retained unchanged in meaning

`bridge/services/sdk-operation-authority.js` and `bridge/repos/sdk-operation-repo.js` own durable operation identity, cancellation and terminal recovery. `sdk-direct-mutation-policy-authority.js`, `sdk-prepared-action-mutation-base-authority.js` and `mutation-policy/mutation-policy-gate.js` own scope and inspected live-state binding. These must bind the new local principal rather than losing ownership altogether.

Keep project/timeline identity checks, revision drift rejection, protected-scope enforcement, exact-impact preview, content hash binding, stale receipt rejection, filesystem destination safety, checkpoint/restore and post-reopen native verification. A database byte match is still insufficient for native acceptance. Hosted voice generation is unavailable in the standalone base; do not copy billing, cloud auth, provider orchestration or telemetry just to populate those capabilities.

## Free transport dependency

The inspected local commit implements LuaSocket with HTTP-polling fallback in `assets/CutAgent.lua`; there are no spool implementation files in this commit. The parent identified a separate implemented Free spool lane: task `01a07e1e-8b3b-79c2-aa77-c65edb446044`, host `j-mac`, checkout `/private/tmp/cutagent-p2-13-free-e2e`. Its coherent transport commit was requested by the parent. **Consume that commit; do not write another spool transport.** No remote files or transport tests were inspected in this extraction task, so spool correctness/support remains unverified here.

After integration, inventory its actual files and test both Free spool and Studio external transport through the same local public SDK entry point. Spool request ownership, exclusive/atomic files, request/response correlation, symlink/traversal rejection, bounded payloads, stale instance cleanup and restart behavior require retained evidence.

## Licenses and runtime inventory before copying

- `sdk/LICENSE` is MIT; `sdk/package.json` declares MIT. Preserve the copyright and license with copied public code.
- Root `LICENSE` and `cutagent-cli/LICENSE` are proprietary. The user's explicit extraction authorization permits selecting first-party runtime for a new open-source distribution; record the exact selected inventory and apply the chosen license there, without changing unrelated app/cloud licenses. No blanket relicensing or runtime copy occurred in this batch.
- The SDK declares `zod` at runtime and API Extractor, TypeScript, esbuild, AJV and Node.js types for development. Preserve notices using the resolved standalone lockfile, not only manifest ranges.
- Python currently requires certifi, click, typer, rich, PyYAML, cryptography, jsonschema, numpy, scipy, zstandard and conditional tomli. This is the package-wide inventory, not evidence that every dependency is needed by the extracted native subset. Resolve the selected handlers' dependency closure before reducing it.
- `assets/windows-luasocket/socket.dll` is present in the old transport. Do not carry it into the spool distribution unless still required and its exact origin and license are recorded.
- `frontend/src-tauri/licenses/cutagent-cli-runtime/PACKAGE-LICENSE-INDEX.txt` and the FFmpeg notice are notice inputs, not proof that every binary can be redistributed under MIT. Bundle only required runtimes after checking their exact build notices. Never copy the entire Electron resources tree.
- DaVinci Resolve itself and `DaVinciResolveScript` should be loaded from the user's installation, not redistributed in the repository. Media probes/render verification may need FFmpeg/FFprobe; make their dependency explicit and retain the exact binary's notices if bundling.

## Verification and implementation order

First implement one complete read-only connection: standalone package install → same-user local bootstrap → local principal → native adapter → current project read → session closure. Launch it with all CutAgent/cloud credentials absent and outbound networking denied. Then add one revision-bound marker mutation through the preserved durable authority, receipt admission, native readback and recovery path. Broaden native action extraction only after this chain works.

Adapt and run the existing `bridge/tests/sdk-account-session-binding.test.js`, `sdk-runtime-route.test.js`, `sdk-prepared-action-coordinator.test.js`, `sdk-prepared-action-production-path.test.js`, `sdk-operation-authority.test.js`, `sdk-direct-mutation-policy-authority.test.js`, `mutation-policy-gate.test.js` and `cutagent-cli/tests/test_embedded_transport.py` against the standalone entry point. New assertions must reject replayed/expired tokens, wrong OS user or runtime instance, changed local principal generation, wrong project/timeline, stale revision, altered impact, unauthorized artifact paths and writes outside protected scope. Do not keep account-subscription requirements in standalone fixtures.

Then verify clean checkout build, independent dependency installation, imports, packaging allowlist, notices, absence of commercial URLs/credentials, no monorepo paths, and no CutAgent installation requirement. Real project inspection, a disposable project mutation, checkpoint/reopen and render verification must run on macOS/Windows × Free/Studio before claiming those supported combinations. No such live test ran in this batch because no standalone runtime exists yet.

## Observed export failure

The existing command `node sdk/scripts/create-public-source-snapshot.mjs --output <separate-directory>` copied its reviewed allowlist, then exited 1 at the final public-content policy. `sdk/dist/schemas.js:5850` contains `privatePathText`, a defensive public-text rejection regex containing `sqlite`; `scripts/public-artifact-policy.mjs` flags that literal as proprietary database detail. This appears to be scanner self-matching, not a disclosed database implementation, but it still means the export is unapproved. Do not weaken the original product scanner globally. The new standalone source release needs its own reviewed source/binary inventory policy, and this exact failure should become a narrow regression case if the old SDK export is repaired separately.

The exporter ran under local Node.js 20.20.2, outside the SDK's declared 22/24 support; only its policy failure was observed. No build, import or compatibility success is claimed.
