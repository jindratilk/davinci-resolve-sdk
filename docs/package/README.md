# CutAgent SDK

The `cutagent` source candidate exposes the complete existing TypeScript authoring API, domain objects, durable operations, typed actions, schemas and protocol. It connects to DaVinci Resolve locally without an account or subscription.

```ts
import { CutAgent as DaVinciResolve, frames } from 'cutagent';

const client = await DaVinciResolve.connect();
try {
  const project = await client.projects.current();
  const timeline = await project.timelines.current();
  console.log(project.name, timeline.name, await timeline.snapshot());
} finally {
  await client.close();
}
```

The exported `CutAgent` class name remains for source compatibility. The package import and distribution branding are independent. Local editing does not require paid services.

The root `cutagent` package includes this client and the companion local native runtime source. Run `npx cutagent setup`, then start `cutagent runtime start --transport studio_external` or `embedded_free`. The state directory must be private to the current OS user. DaVinci Resolve Free requires the independent Lua spool broker and script activation described in the repository README. No desktop product or account is required.

Use ESM on Node.js 22.12+ (22.x) or 24.x, and TypeScript 5.7–5.9 with NodeNext resolution. Browser/CommonJS exports are unsupported. Public subpaths are `/actions`, `/schemas`, `/protocol`, `/preview/v0.1`, `/compatibility.json`, `/compatibility.schema.json` and `/package.json`; other deep imports are unsupported.

Mutation APIs retain their existing preview, exact target/revision and idempotency contracts. Local discovery uses private same-user state, an unpredictable capability and one-use bootstrap. Native operations retain verification/recovery and durable operation state. AI transcription, voice generation and video generation are available in the CutAgent desktop app. Explore plans: https://cutagent.ai.

Historical marker baselines passed on 2026-09-08 for Studio at commit fb4ad93 and Free at commit 172232a, with protected state restored. Those records do not qualify this candidate head. Current-candidate Studio and Free native revalidation, other native domains, and Windows local ACL support remain pending. The npm package is unpublished; method availability is not proof of live native acceptance. See the source repository README and LIFECYCLE.md for scope.
