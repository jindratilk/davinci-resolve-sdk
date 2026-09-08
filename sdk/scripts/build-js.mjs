import { build } from "esbuild";

const common = {
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node22.12",
  external: ["zod"],
  legalComments: "none",
  sourcemap: false,
};

const sharedRootClasses = {
  name: "shared-root-error-classes",
  setup(buildContext) {
    buildContext.onResolve({ filter: /(?:core\/sdk-error|(?:value-types\/)?value-error)\.js$/ }, () => ({
      external: true,
      path: "./index.js",
    }));
  },
};

await Promise.all([
  build({ ...common, entryPoints: ["src/index.ts"], outfile: "dist/index.js" }),
  build({ ...common, entryPoints: ["src/actions.ts"], outfile: "dist/actions.js", plugins: [sharedRootClasses] }),
  build({ ...common, entryPoints: ["src/schemas/index.ts"], outfile: "dist/schemas.js" }),
  build({ ...common, entryPoints: ["src/protocol/index.ts"], outfile: "dist/protocol.js", plugins: [sharedRootClasses] }),
  build({ ...common, entryPoints: ["src/preview/v0.1.ts"], outfile: "dist/preview-v0.1.js", plugins: [sharedRootClasses] }),
]);
