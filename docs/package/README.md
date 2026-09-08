# DaVinci Resolve SDK

The `davinci-resolve-sdk` source candidate exposes the complete existing TypeScript authoring API, domain objects, durable operations, typed actions, schemas and protocol. It connects to the independently running local native runtime without a commercial account or subscription.

```ts
import { CutAgent as DaVinciResolve, frames } from 'davinci-resolve-sdk';

const client = await DaVinciResolve.connect();
try {
  const project = await client.projects.current();
  const timeline = await project.timelines.current();
  console.log(project.name, timeline.name, await timeline.snapshot());
} finally {
  await client.close();
}
```

The exported `CutAgent` class name remains for source compatibility. The package import and distribution branding are independent. Existing internal protocol identifiers do not require commercial services.

The client package requires the companion local native runtime from the standalone source repository. From that repository, create the Python environment and install its locked dependencies, build the workspace, then use `startNativeLocalRuntime({stateDirectory, transport})` from `runtime/index.mjs`. The state directory must be private to the current OS user. Transport is explicitly `studio_external` or `embedded_free`; Free requires the independent Lua spool broker and script activation described in the repository README. No desktop product is required.

Use ESM on Node.js 22.12+ (22.x) or 24.x, and TypeScript 5.7–5.9 with NodeNext resolution. Browser/CommonJS exports are unsupported. Public subpaths are `/actions`, `/schemas`, `/protocol`, `/preview/v0.1`, `/compatibility.json`, `/compatibility.schema.json` and `/package.json`; other deep imports are unsupported.

Mutation APIs retain their existing preview, exact target/revision and idempotency contracts. Local discovery uses private same-user state, an unpredictable capability and one-use bootstrap. Native operations retain verification/recovery and durable operation state. Hosted transcription, voice generation and video generation are outside this native runtime's scope.

A full-chain Studio marker create/readback/delete smoke passed on 2026-09-08, with original marker and track/clip/audio state preserved. Free marker create/readback/delete acceptance also passed; other native domains and Windows local ACL support remain pending. The npm package is unpublished; method availability is not proof of live native acceptance. See the source repository README and LIFECYCLE.md for scope.
