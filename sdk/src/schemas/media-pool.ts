import { z } from "zod";
import {
  sdkMediaPoolAssetKindSchema,
  sdkMediaPoolAssetSnapshotSchema,
  sdkMediaPoolFolderSnapshotSchema,
  sdkMediaPoolMetadataEntrySchema,
  sdkMediaPoolMetadataKeySchema,
  sdkMediaPoolPageSchema,
  sdkMediaPoolSearchSchema,
} from "../generated/sdk-runtime.js";
import type {
  MediaPoolAssetKind,
  MediaPoolAssetSnapshot,
  MediaPoolFolderSnapshot,
  MediaPoolMetadataEntry,
  MediaPoolMetadataKey,
  MediaPoolSearchInput,
} from "../domain/media-pool.js";
import { ProjectIdSchema } from "../value-types/identities.js";

/** Runtime validator for normalized public Media Pool asset categories. @beta */
export const MediaPoolAssetKindSchema = sdkMediaPoolAssetKindSchema as unknown as z.ZodType<MediaPoolAssetKind>;
/** Runtime validator for immutable public Media Pool asset snapshots. @beta */
export const MediaPoolAssetSnapshotSchema = sdkMediaPoolAssetSnapshotSchema.safeExtend({
  projectId: ProjectIdSchema,
}) as unknown as z.ZodType<MediaPoolAssetSnapshot>;
/** Runtime validator for immutable public Media Pool folder snapshots. @beta */
export const MediaPoolFolderSnapshotSchema = sdkMediaPoolFolderSnapshotSchema.extend({
  projectId: ProjectIdSchema,
}) as unknown as z.ZodType<MediaPoolFolderSnapshot>;
/** Runtime validator for one curated public Media Pool metadata entry. @beta */
export const MediaPoolMetadataEntrySchema = sdkMediaPoolMetadataEntrySchema as unknown as z.ZodType<MediaPoolMetadataEntry>;
/** Runtime validator for curated public Media Pool metadata keys. @beta */
export const MediaPoolMetadataKeySchema = sdkMediaPoolMetadataKeySchema as unknown as z.ZodType<MediaPoolMetadataKey>;
/** Runtime validator for the bounded private Media Pool page wire shape. @beta */
export const MediaPoolPageWireSchema = sdkMediaPoolPageSchema as unknown as z.ZodType<unknown>;
/** Runtime validator for deterministic public Media Pool search input. @beta */
export const MediaPoolSearchSchema = z.strictObject({
  query: sdkMediaPoolSearchSchema.shape.query,
  match: sdkMediaPoolSearchSchema.shape.match.default("contains"),
  fields: sdkMediaPoolSearchSchema.shape.fields.default(["name"]),
}) as unknown as z.ZodType<MediaPoolSearchInput>;
