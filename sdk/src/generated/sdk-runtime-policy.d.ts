export declare const CUTAGENT_SDK_PREVIEW_VERSION: "0.2.0";
export declare const CUTAGENT_SDK_SUPPORTED_PACKAGE_MAJOR: 0;
export declare const CUTAGENT_SDK_SUPPORTED_PACKAGE_MINOR: 2;
export declare const CUTAGENT_SDK_RUNTIME_MIN_VERSION: "3.0.0";
export declare const CUTAGENT_SDK_RUNTIME_MAX_EXCLUSIVE_VERSION: "3.1.0";
export type CutAgentSdkRuntimeCompatibilityAxis = "runtime" | "distribution" | "cli";
export interface CutAgentSdkRuntimeCompatibilityInput {
    runtimeVersion: string;
    distribution: "standalone_local" | "plugin_managed";
    distributionVersion: string;
    cliVersion: string;
}
export interface CutAgentSdkRuntimeCompatibilityIssue {
    axis: CutAgentSdkRuntimeCompatibilityAxis;
    received: string;
    supported: string;
}
export interface CutAgentSdkRuntimeCompatibilityPolicy {
    runtimeRange: string;
    desktopManagedRange: string | null;
    pluginManagedRange: string | null;
    cliRange: string;
    expectedDistribution?: "standalone_local" | "plugin_managed";
}
export type CutAgentSdkRuntimeCompatibilityDecision = {
    compatible: true;
} | {
    compatible: false;
    issues: CutAgentSdkRuntimeCompatibilityIssue[];
};
/** Evaluate the independently versioned runtime, distribution, and CutAgent CLI axes. */
export declare function evaluateCutAgentSdkRuntimeCompatibility(input: CutAgentSdkRuntimeCompatibilityInput, policy?: CutAgentSdkRuntimeCompatibilityPolicy): CutAgentSdkRuntimeCompatibilityDecision;
