"""Public-facing labels for CutAgent CLI command history.

These labels are for CutAgent UI chrome, not command documentation. They should
sound like completed editor-visible work, avoid command names/flags, and use the
full DaVinci Resolve product name wherever the product is mentioned.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .command_catalog import command_catalog_rows


SCHEMA_VERSION = 1

HELP_FLAGS = ("--help", "-h")
DRY_RUN_FLAGS = ("--dry-run", "-n")
OUTPUT_ONLY_FLAGS = frozenset(
    {
        "--json",
        "-j",
        "--plain",
        "-p",
        "--tsv",
        "--quiet",
        "-q",
        "--verbose",
        "-v",
        "--output-mode",
        "--select",
        "--ffmpeg-path",
        "--ffprobe-path",
    }
)

TARGET_DETAIL_NAMES = frozenset(
    {
        "album",
        "angle",
        "at",
        "audio_angle_map",
        "audio_source",
        "audio_target",
        "clip",
        "clip_name",
        "clip_or_name",
        "codec",
        "color",
        "db",
        "file",
        "folder",
        "format",
        "frame",
        "index",
        "input",
        "input_media",
        "job",
        "job_json",
        "limit",
        "mark_in",
        "mark_out",
        "marker_id",
        "name",
        "output",
        "output_file",
        "path",
        "preset",
        "project",
        "selector",
        "timeline",
        "timeline_name",
        "track_type",
        "value",
    }
)

BEHAVIOR_NAMES = frozenset(
    {
        "append",
        "audio_sync",
        "clear",
        "delete",
        "disable",
        "enable",
        "export",
        "fail_fast",
        "force",
        "full",
        "generate",
        "include_generated",
        "include_ui",
        "mode",
        "plan_only",
        "recursive",
        "replace",
        "replace_media",
        "replace_program_audio",
        "set",
        "sync",
        "verify",
        "wait",
        "write_plan",
    }
)

COMMAND_LABEL_OVERRIDES = {
    "dctl encrypt": "Created an encrypted DCTL artifact",
    "audio beat-detect": "Detected musical beats and phrase candidates",
    "asset artifact-index": "Listed recent exports",
    "bulk select": "Previewed which clips match a bulk selector",
    "bulk lut-set": "Applied a LUT to the selected clips in bulk",
    "bulk clip-color-set": "Set the clip color on the selected clips in bulk",
    "bulk enable": "Enabled the selected clips in bulk",
    "bulk disable": "Disabled the selected clips in bulk",
    "bulk property-set": "Changed a clip property on the selected clips in bulk",
    "capabilities": "Checked DaVinci Resolve automation capabilities",
    "connect": "Tested the DaVinci Resolve connection",
    "context": "Checked the current DaVinci Resolve editing context",
    "info": "Read DaVinci Resolve environment information",
    "launch": "Launched DaVinci Resolve",
    "lut-refresh": "Refreshed the DaVinci Resolve LUT list",
    "page current": "Checked the current DaVinci Resolve page",
    "page switch": "Switched the DaVinci Resolve page",
    "product": "Checked DaVinci Resolve product information",
    "project cleanup-scratch": "Cleaned up DaVinci Resolve scratch projects",
    "quit": "Quit DaVinci Resolve",
    "status": "Checked DaVinci Resolve status",
    "timeline current-item": "Inspected the clip under the playhead",
    "timeline info": "Read the current timeline",
    "timeline duration": "Checked the current timeline duration",
    "timeline marker list": "Listed timeline markers",
    "timeline clip-markers list": "Listed timeline clip markers",
    "timeline mark get": "Read timeline mark in and out points",
    "timeline mark set": "Set timeline mark in and out points",
    "timeline mark clear": "Cleared timeline mark in and out points",
    "asset resolve": "Located an asset file",
    "audio duck": "Applied dialogue ducking",
    "audio info": "Read audio processing information",
    "audio reverb": "Prepared audio reverb processing",
    "auto-edit multicam": "Created a multicam edit",
    "auto-edit podcast-edit": "Created a podcast multicam edit from a transcript",
    "auto-edit podcast-multicam": "Created a podcast multicam edit",
    "auto-edit run": "Ran an automatic edit",
    "batch run": "Ran an edit plan",
    "batch validate": "Checked an edit plan",
    "clip audio-eq": "Applied audio EQ to a linked clip",
    "clip audio-gain": "Set linked audio gain",
    "clip audio-normalize": "Normalized linked audio level",
    "clip audio-pan": "Set linked audio pan",
    "clip audio-pitch": "Set linked audio pitch",
    "clip cache": "Checked clip cache state",
    "clip cache-set": "Updated clip cache state",
    "clip cache-state": "Checked clip cache state",
    "clip color": "Checked clip color",
    "clip composite": "Checked clip composite settings",
    "clip fade-in": "Applied fade-ins to linked clips",
    "clip freeze": "Froze linked clips",
    "clip fusion by-name": "Found a Fusion composition",
    "clip fusion tool-get": "Read a Fusion node value",
    "clip fusion tool-set": "Set a Fusion node value",
    "clip fusion tools": "Listed Fusion nodes",
    "clip keyframe get": "Read keyframes",
    "clip link": "Linked timeline clips",
    "clip magic-mask": "Checked Magic Mask availability",
    "clip properties": "Checked clip properties",
    "clip reverse": "Reversed linked clips",
    "clip speed": "Checked clip speed",
    "clip speed-ramp": "Applied a speed ramp across an adjacent cut",
    "clip transform": "Checked clip transform properties",
    "clip voice-isolation": "Checked clip voice isolation",
    "fairlight clip nudge": "Adjusted Fairlight audio clip timing",
    "fairlight record info": "Checked Fairlight record setup",
    "fairlight sound-library delete": "Removed a Fairlight Sound Library entry",
    "fairlight sound-library audition": "Auditioned a Fairlight Sound Library result",
    "fairlight sound-library index-folder": "Added a Fairlight Sound Library folder",
    "fairlight sound-library index-file": "Added a Fairlight Sound Library file",
    "fairlight sound-library preview": "Previewed a Fairlight Sound Library result",
    "color arri-cdl-lut": "Applied ARRI CDL and LUT color adjustments",
    "color auto-color": "Generated auto-color correction",
    "color comp doctor": "Checked a Fusion color composition",
    "color comp export": "Exported a Fusion color composition",
    "color comp flatten": "Flattened a Fusion color composition",
    "color comp repair": "Repaired a Fusion color composition",
    "color fx apply": "Applied a Fusion grading effect",
    "color fx list": "Listed Fusion grading effects",
    "color graph normalize": "Cleaned up the grading node graph",
    "color lut": "Checked a LUT on a color node",
    "color page magic-mask": "Checked Color Page Magic Mask availability",
    "color page magic-mask-draw-stroke": "Drew a DaVinci Resolve Color Page Magic Mask stroke",
    "color page magic-mask-refine": "Drew a DaVinci Resolve Color Page Magic Mask refinement stroke",
    "color page auto-color-ai": "Applied DaVinci Resolve native Auto Color",
    "color page alpha-output-connect": "Connected a Color node to native Alpha Output",
    "color page node-cleanup": "Removed empty Color Page nodes",
    "color page node-cleanup-general": "Removed empty Color Page nodes",
    "color page power-window-track": "Tracked a DaVinci Resolve Color Page Power Window",
    "color page qualifier-matte-refine": "Refined a DaVinci Resolve Color Page HSL qualifier matte",
    "color page qualifier-sample": "Sampled Color Page viewer color values",
    "color page resolvefx-param-discover": "Read DaVinci Resolve effect controls",
    "color page white-balance-picker": "Balanced clip color from a sampled neutral patch",
    "color power-grade apply": "Checked PowerGrade library apply availability",
    "color reset-fusion": "Removed Fusion grading and restored a clean Fusion flow",
    "color version activate": "Activated a color version",
    "color version duplicate": "Duplicated a color version",
    "color version rollback": "Rolled back to a color version",
    "edit trim": "Trimmed the head or tail of a clip",
    "edit ripple-delete": "Removed a timeline segment and closed the gap",
    "edit ripple-delete-selected": "Removed the selected clip and closed the gap",
    "edit slide-selected": "Slid the selected clip in DaVinci Resolve",
    "edit slip-selected": "Slipped the selected clip in DaVinci Resolve",
    "project cloud restore": "Restored a cloud project folder",
    "project cloud create": "Created a cloud project",
    "project cloud import": "Imported a cloud project",
    "project cloud open": "Opened a cloud project",
    "project db backup": "Backed up the project",
    "project db create": "Created a project storage location",
    "project db current": "Checked the current project storage location",
    "project db list": "Listed project storage locations",
    "project db restore": "Restored a project backup",
    "project db switch": "Switched project storage locations",
    "project preset save": "Saved current project settings as a preset",
    "project preset delete": "Deleted a project settings preset",
    "project preset export": "Exported a project settings preset",
    "project preset import": "Imported a project settings preset",
    "render settings-set-json": "Updated render settings",
    "render settings-set-key": "Updated one render setting",
    "render export-file": "Rendered one exact timeline output with complete validation",
    "render transcript-audio": "Rendered transcript-ready audio from the active timeline",
    "script doctor": "Checked DaVinci Resolve diagnostics",
    "storage reveal": "Revealed a path in DaVinci Resolve media storage",
    "text insert-preset": "Inserted a DaVinci Resolve title preset",
    "text insert-captions": "Created designed captions from the transcript",
    "timeline captions": "Chose a caption approach",
    "timeline clip-color batch": "Updated timeline clip colors",
    "timeline dolby analyze": "Ran Dolby Vision analysis",
    "timeline items set-duration": "Set a timeline item duration",
    "timeline marker batch": "Updated timeline markers",
    "timeline overlay-stack insert": "Inserted a layered overlay",
    "timeline frame-export": "Exported a still image from the timeline",
    "timeline frame-export batch": "Exported still images from the timeline",
    "timeline start-tc": "Checked timeline start timecode",
    "timeline subtitle export": "Exported subtitles",
    "timeline subtitles": "Chose a subtitle approach",
    "timeline sync-clips": "Placed synchronized clips on timeline tracks",
    "version": "Checked DaVinci Resolve version information",
    "version create": "Created a project checkpoint",
    "version inspect": "Inspected a project checkpoint",
    "version list": "Listed project checkpoints",
    "version prune": "Cleaned up old project checkpoints",
    "version restore": "Restored a project checkpoint",
    "version status": "Checked project checkpoint status",
    "workflow node check": "Checked custom edit logic",
    "workflow callback script create": "Created a custom edit callback",
    "workflow script install": "Installed a custom DaVinci Resolve edit",
    "workflow ui scaffold": "Created a custom edit panel",
    "fusion insert-settings batch": "Inserted multiple Fusion and Text+ clips from templates",
    "fusion template list": "Listed Fusion templates",
    "fusion preview": "Previewed styled Fusion text",
    "fusion setting inspect": "Inspected a Fusion template graph",
    "fusion setting summary": "Summarized a Fusion template graph",
    "fusion setting validate": "Validated a Fusion template",
    "fusion template apply": "Applied a Fusion template to a clip",
    "fusion template package-drfx": "Packaged a Fusion template folder",
    "fusion template unpack-drfx": "Unpacked a Fusion template package",
    "multicam create": "Created a multicam clip in the media pool",
    "multicam match-frame": "Matched a multicam frame to its source",
    "multicam flatten": "Flattened multicam clips on the timeline",
    "multicam convert": "Converted tracks into a multicam clip",
    "multicam set-start-timecode": "Changed the multicam start timecode",
    "multicam angle rename": "Renamed a multicam angle",
    "multicam angle set-enabled": "Changed whether a multicam angle is enabled",
    "multicam angle remove": "Removed a multicam angle",
    "multicam source move": "Moved a source item inside a multicam angle",
    "multicam source remove": "Removed a source item from a multicam angle",
    "multicam source property-set": "Changed a multicam source property",
    "multicam source grade-cdl": "Validated an unavailable multicam source CDL target",
    "multicam source raw-braw-set": "Changed Blackmagic RAW settings inside a multicam angle",
    "multicam smart-switch": "Created a speaker-aware multicam cut",
    "multicam settings": "Checked multicam settings",
    "multicam timeline-create": "Created a multicam timeline",
    "multicam replace audio": "Updated audio items inside multicam angles",
    "multicam replace video": "Updated video items inside multicam angles",
    "fairlight dynamics disable": "Disabled Fairlight dynamics",
    "fairlight effect list": "Listed Fairlight clip FX",
    "fairlight effect params": "Read Fairlight clip FX parameters",
    "fairlight effect set-param": "Set Fairlight clip FX parameter",
        "fairlight dynamics enable": "Enabled Fairlight dynamics",
        "fairlight effect slot-scan": "Checked Fairlight effect slot candidates",
        "fairlight add": "Added an audio track",
    "fairlight delete": "Deleted an audio track",
    "fairlight ensure-tracks": "Ensured enough audio tracks",
    "fairlight ensure-stereo-tracks": "Ensured enough stereo audio tracks",
    "fairlight clip slip": "Updated Fairlight audio source timing",
    "fairlight bounce mix-to-track": "Bounced the main Fairlight mix to an audio track",
    "fairlight bounce track": "Bounced a Fairlight audio track to another audio track",
    "fairlight adr record": "Recorded the selected Fairlight ADR cue",
    "fairlight solo-restore": "Restored audio tracks after solo mode",
    "fairlight track hide": "Hid a Fairlight audio track",
    "fairlight track show": "Showed a Fairlight audio track",
    "fairlight track-color": "Set an audio track color",
}

COMMAND_LABEL_OVERRIDES.update(
    {
        "auto-edit run": "Created an automatic edit",
        "batch run": "Applied an edit plan",
        "capabilities": "Checked available DaVinci Resolve features",
        "doctor": "Checked DaVinci Resolve readiness",
        "info": "Read the DaVinci Resolve setup",
        "product": "Checked the installed DaVinci Resolve edition",
        "version": "Checked the installed DaVinci Resolve version",
        "audio info": "Read audio processing settings",
        "audio reverb": "Prepared reverb audio processing",
        "codec build": "Built a codec add-on project",
        "codec install": "Installed a codec add-on",
        "codec list-installed": "Listed installed codec add-ons",
        "codec package": "Packaged a codec add-on",
        "codec sample copy": "Copied a codec example",
        "codec scaffold": "Prepared a codec add-on project",
        "codec uninstall": "Removed a codec add-on",
        "codec validate": "Checked a codec add-on",
        "developer capability audit": "Checked feature coverage",
        "developer capability diff": "Compared feature coverage",
        "developer docs list": "Listed local DaVinci Resolve documentation",
        "developer docs open": "Opened local DaVinci Resolve documentation",
        "developer doctor": "Checked local DaVinci Resolve resources",
        "developer examples copy": "Copied a DaVinci Resolve example",
        "developer examples list": "Listed DaVinci Resolve examples",
        "developer sdk doctor": "Checked local DaVinci Resolve resources",
        "developer sdk-doctor": "Checked local DaVinci Resolve resources",
        "dctl scaffold": "Prepared a DCTL file",
        "dctl validate": "Checked a DCTL file",
        "edit auto-subtitle": "Created subtitles from timeline audio",
        "edit blade": "Added blade cuts at the playhead",
        "edit split": "Added blade cuts at the playhead",
        "edit camera-pip": "Created a picture-in-picture camera layout",
        "edit from-edl": "Imported and assembled a timeline from an EDL",
        "edit fx add": "Added an effect to a clip",
        "edit overwrite": "Overwrote clips at the timeline position",
        "edit social-crop": "Applied a social crop and reframe",
        "edit transition add": "Added a transition",
        "edit transition batch": "Added transitions after checking targets",
        "embedded install": "Installed CutAgent support in DaVinci Resolve",
        "embedded ping": "Checked the CutAgent connection to DaVinci Resolve",
        "embedded start-server": "Started CutAgent support for DaVinci Resolve",
        "embedded status": "Checked CutAgent support in DaVinci Resolve",
        "embedded uninstall": "Removed CutAgent support from DaVinci Resolve",
        "fairlight item-source patch": "Updated audio source timing",
        "fairlight automation list": "Read audio-clip volume envelopes and diagnostic mixer tokens",
        "fairlight automation write": "Wrote an audio-clip volume-envelope point",
        "fairlight audio-gain batch": "Adjusted gain on multiple audio clips",
        "fairlight bus level": "Checked or updated main-output sequence gain",
        "fairlight record arm": "Set Fairlight audio track record arm in DaVinci Resolve",
        "fairlight track duplicate": "Duplicated Fairlight track without processing",
        "fairlight track folder": "Created a Fairlight folder track",
        "fuse scaffold": "Prepared a Fuse file",
        "fusion comp current": "Read the current Fusion composition",
        "fusion generate": "Generated a Fusion template",
        "fusion image batch": "Updated images in Fusion templates",
        "fusion image set": "Updated a Fusion image source",
        "fusion insert-setting": "Inserted a Fusion composition from a template",
        "fusion keyframe add": "Added a Fusion keyframe",
        "fusion nested-text batch": "Updated nested Fusion text templates",
        "fusion nested-text update": "Updated nested Fusion text",
        "fusion node add": "Added a Fusion node",
        "fusion node connect": "Connected Fusion nodes",
        "fusion node delete": "Deleted a Fusion node",
        "fusion node disconnect": "Disconnected a Fusion node input",
        "fusion template scaffold": "Prepared a Fusion template",
        "fusion text batch": "Updated text in Fusion templates",
        "fusion text set": "Updated Fusion text",
        "fusion tool active": "Checked the active Fusion node",
        "fusion tool add": "Added a Fusion node",
        "fusion tool attrs": "Read Fusion node attributes",
        "fusion tool connect": "Connected Fusion nodes",
        "fusion tool copy": "Copied Fusion nodes",
        "fusion tool delete": "Deleted a Fusion node",
        "fusion tool disconnect": "Disconnected a Fusion node control",
        "fusion tool get": "Read a Fusion node control",
        "fusion tool inputs": "Listed Fusion node controls",
        "fusion tool list": "Listed Fusion nodes",
        "fusion tool outputs": "Listed Fusion node outputs",
        "fusion tool paste": "Pasted Fusion nodes",
        "fusion tool set": "Set a Fusion node control",
        "fusion tracker add": "Added a Fusion tracker",
        "layout save": "Saved the current layout as a preset",
        "layout update": "Updated the current layout preset",
        "lut convert": "Checked LUT format support",
        "media append": "Appended media to the timeline",
        "media metadata": "Checked clip metadata",
        "media third-party-metadata set-json": "Updated third-party metadata",
        "media transcribe": "Transcribed clip audio",
        "multicam recover-timing": "Recovered multicam timing",
        "multicam reorder-angles": "Reordered multicam angles",
        "ofx build": "Built an OpenFX effect project",
        "ofx package": "Packaged an OpenFX effect",
        "ofx sample copy": "Copied an OpenFX example",
        "ofx scaffold": "Prepared an OpenFX effect project",
        "ofx validate": "Checked an OpenFX effect",
        "render archive-settings": "Configured archive render settings",
        "render export-preset": "Exported a render preset",
        "render import-preset": "Imported a render preset",
        "render preset-delete": "Deleted a render preset",
        "render preset-save": "Saved current render settings as a preset",
        "render wait": "Waited for rendering to finish",
        "script env print": "Checked DaVinci Resolve setup diagnostics",
        "script install": "Installed a DaVinci Resolve custom edit",
        "script list": "Listed DaVinci Resolve custom edits",
        "script run": "Applied a DaVinci Resolve custom edit",
        "script uninstall": "Uninstalled a DaVinci Resolve custom edit",
        "text insert": "Inserted a styled text overlay",
        "text insert-template": "Inserted a Fusion title template",
        "timeline layer ensure-media": "Filled a video layer across the selected range",
        "timeline layout free-stack": "Planned a layered timeline layout",
        "timeline media-pool-item": "Checked the source clip for the current timeline item",
        "timeline preview-export": "Exported a short timeline preview",
        "timeline track disable": "Muted a track",
        "workflow callback script create": "Prepared a custom edit connection",
        "workflow node check": "Checked a custom edit",
        "workflow plugin info": "Checked custom add-on details",
        "workflow plugin install": "Installed a custom add-on",
        "workflow plugin list": "Listed installed custom add-ons",
        "workflow plugin package": "Packaged a custom add-on",
        "workflow plugin scaffold": "Prepared a custom add-on",
        "workflow plugin uninstall": "Removed a custom add-on",
        "workflow plugin validate": "Checked a custom add-on",
        "workflow script install": "Installed a custom DaVinci Resolve edit",
        "workflow ui scaffold": "Created a custom edit panel",
    }
)

HELP_LABEL_OVERRIDES = {
    "bulk select": "Reviewed how to preview clips matched by a bulk selector",
    "bulk lut-set": "Reviewed how to apply a LUT to clips in bulk",
    "bulk clip-color-set": "Reviewed how to set clip colors in bulk",
    "bulk enable": "Reviewed how to enable clips in bulk",
    "bulk disable": "Reviewed how to disable clips in bulk",
    "bulk property-set": "Reviewed how to change clip properties in bulk",
    "status": "Reviewed how to check DaVinci Resolve status",
    "color page power-window-track": "Reviewed how to track a DaVinci Resolve Color Page Power Window",
    "color page qualifier-matte-refine": "Reviewed how to refine a DaVinci Resolve Color Page HSL qualifier matte",
    "color page qualifier-sample": "Reviewed how to sample Color Page viewer color values",
    "color page white-balance-picker": "Reviewed how to balance clip color from a sampled neutral patch",
    "timeline current-item": "Reviewed how to inspect the clip under the playhead",
    "timeline info": "Reviewed how to read the current timeline",
    "timeline duration": "Reviewed how to check the current timeline duration",
    "timeline marker list": "Reviewed how to list timeline markers",
    "timeline clip-markers list": "Reviewed how to list timeline clip markers",
    "project db backup": "Reviewed how to back up the project",
    "fairlight adr record": "Reviewed how to record the selected Fairlight ADR cue",
    "fairlight bounce mix-to-track": "Reviewed how to bounce the main Fairlight mix to an audio track",
    "fairlight bounce track": "Reviewed how to bounce a Fairlight audio track to another audio track",
    "workflow node check": "Reviewed how to check a custom edit",
}

EDITOR_COPY_REPLACEMENTS = (
    (r"\bso agents can find exported frames/settings\b", "for review"),
    (r"\bagents\b", "CutAgent"),
    (r"\bagent\b", "CutAgent"),
    (r"\balias for\b.*", ""),
    (r"\busing ffmpeg pipeline with optional media relink\b", "to balance dialogue and music"),
    (r"\bffmpeg\b", "audio"),
    (r"\bdeterministic recipe YAML schema \(version=1\)\b", "edit plan format"),
    (r"\bdeterministic recipe steps\b", "edit plan steps"),
    (r"\bdeterministic\b", ""),
    (r"\brecipe YAML\b", "edit plan"),
    (r"\brecipe\b", "edit plan"),
    (r"\bone-command auto-edit pipeline\b", "automatic edit"),
    (r"\bpipeline\b", "edit"),
    (r"\bcommand\b", "edit"),
    (r"\bcommands\b", "edits"),
    (r"\bnative\b", ""),
    (r"\barchive-backed\b", ""),
    (r"\bEffectFiltersBA\b", ""),
    (r"\bpayloads?\b", ""),
    (r"\bvia\s+\.", ""),
    (r"\bvia\b", "using"),
    (r"\broute\b", ""),
    (r"\broutes\b", ""),
    (r"\bthrough the project database\b", ""),
    (r"\bthrough project database\b", ""),
    (r"\bproject database\b", "project"),
    (r"\bdatabase-backed\b", ""),
    (r"\bdatabase\b", "project"),
    (r"\bDisk Project\.db\b", "project checkpoint"),
    (r"\bProject\.db\b", "project checkpoint"),
    (r"\bdisk project\b", "project storage"),
    (r"\bif runtime supports it\b", ""),
    (r"\bDaVinci Resolve exposes that DaVinci Resolve\b", "DaVinci Resolve supports it"),
    (r"\bDaVinci Resolve exposes the automation DaVinci Resolve\b", "DaVinci Resolve supports it"),
    (r"\bwhen DaVinci Resolve exposes the DaVinci Resolve\b", "when available"),
    (r"\bwhen DaVinci Resolve exposes the automation DaVinci Resolve\b", "when available"),
    (r"\bwhen DaVinci Resolve exposes [A-Za-z0-9_]+\b", "when available"),
    (r"\bwhen DaVinci Resolve exposes it\b", "when available"),
    (r"\bDaVinci Resolve availability\b", "availability"),
    (r"\bautomation API\b", "DaVinci Resolve"),
    (r"\bAPI\b", "DaVinci Resolve"),
    (r"\bCLI\b", "CutAgent"),
    (r"\bJSON\b", "file"),
    (r"\bstructured data spec\b", "saved setup"),
    (r"\bstructured data\b", "saved setup"),
    (r"\bdict import options\b", "import options"),
    (r"\bscript stub\b", "custom edit template"),
    (r"\bscripts\b", "custom edits"),
    (r"\bscript\b", "custom edit"),
    (r"\bscripting\b", "automation"),
    (r"\bworkflow plugins\b", "custom extensions"),
    (r"\bworkflow plugin\b", "custom extension"),
    (r"\bworkflow\b", "custom edit"),
    (r"\bmanifest\b", "details"),
    (r"\bcallback\b", "connection"),
    (r"\bplugins\b", "extensions"),
    (r"\bplugin\b", "extension"),
    (r"\bhelper\b", ""),
    (r"\bhelpers\b", ""),
    (r"\bUtility\b", ""),
    (r"\bDeveloper\b", ""),
    (r"\bwith make when available\b", ""),
    (r"\bmake when available\b", ""),
    (r"\bSDK\b", ""),
    (r"\bruntime\b", ""),
    (r"\bScaffolded a minimal\b", "Prepared a"),
    (r"\bScaffolded\b", "Prepared"),
    (r"\bminimal\b", ""),
    (r"\blocalhost\b", "local"),
    (r"\bbroker\b", "support service"),
    (r"\bCutAgent\.lua\b", "CutAgent support"),
    (r"\bembedded bridge server\b", "CutAgent support"),
    (r"\bembedded bridge\b", "CutAgent support"),
    (r"\bembedded\b", "CutAgent"),
    (r"\bLua client\b", "DaVinci Resolve connection"),
    (r"\blua\b", "custom edit"),
    (r"\bworkaround\b", ""),
    (r"\bidempotent\b", ""),
    (r"\bwith optional\b", "with"),
    (r"\brepo-recorded manual DaVinci Resolve interface verdicts\b", "multicam review notes"),
    (r"\brepo-recorded manual DaVinci Resolve interface verdict\b", "multicam review note"),
    (r"\bmanual DaVinci Resolve interface verdicts\b", "multicam review notes"),
    (r"\bmanual DaVinci Resolve interface verdict\b", "multicam review note"),
    (r"\bstructured job\b", "edit setup"),
    (r"\bstructured multicam job\b", "multicam setup"),
    (r"\bstructured multicam switch plan\b", "multicam switch plan"),
    (r"\bstructured multicam plan\b", "multicam plan"),
    (r"\bstructured\b", "saved"),
    (r"\bwith all-entry preflight\b", "after checking every item"),
    (r"\bpreflight\b", "check"),
    (r"\bno-interface\b", "clean"),
    (r"\bcanonical\b", "clean"),
    (r"\binvariants\b", "checks"),
    (r"\bfixture\b", "preset"),
    (r"\bImportFusionComp\b", "Fusion import"),
    (r"\bMediaPoolItem\b", "media pool item"),
    (r"\btemplate template\b", "template"),
    (r"\btemplate templates\b", "templates"),
    (r"\btemplate specs\b", "templates"),
    (r"\bruntime node diagnostics\b", "node checks"),
    (r"\bDRX file\b", "grade file"),
    (r"\ba\.cube LUT\b", "LUT"),
    (r"\bfrom RGB curve points\b", "from RGB curves"),
    (r"\busing project \(Disk projects only\)", ""),
    (r"\busing project \([^)]*\)", ""),
    (r"\bsource-domain\b", "source"),
    (r"\brecord-frame\b", "timeline frame"),
    (r"\bstate captured by fairlight solo\b", "saved by solo mode"),
    (r"\bFairlight automation write availability\b", "Fairlight automation availability"),
    (r"\bwhat Fairlight features are and aren't available using the DaVinci Resolve\b", "Fairlight feature availability"),
    (r"\bMediaIn -> MediaOut pipe\b", "Fusion flow"),
    (r"\b->\b", "to"),
    (r"\bGUI\b", "interface"),
    (r"\btool inputs\b", "node controls"),
    (r"\btool input\b", "node control"),
    (r"\btools in a Fusion composition\b", "Fusion nodes"),
    (r"\btools\b", "nodes"),
    (r"\btool\b", "node"),
    (r"\bsource In/Duration\b", "audio source timing"),
    (r"\brecord-domain\b", "timeline"),
    (r"\bRecord-domain\b", "Timeline"),
    (r"\bstable alias\b", "name"),
    (r"\btranscript or audio activity\b", "podcast audio"),
    (r"\bvideo/audio\b", "video and audio"),
    (r"\bcolor/fusion\b", "color and Fusion"),
    (r"\bselected/current\b", "selected"),
    (r"\bSRT or VTT\b", "subtitle file"),
    (r"\btrack type/index\b", "track details"),
    (r"\bset or clear\b", "update"),
    (r"\bSet or clear\b", "Update"),
    (r"\bRead, set, or cleared\b", "Updated"),
    (r"\bRead or updated\b", "Checked"),
    (r"\bRead and set\b", "Checked"),
    (r"\bRead full\b", "Read"),
    (r"\bCreated or updated\b", "Updated"),
    (r"\bCreated and update\b", "Updated"),
    (r"\bAnalyze a video file and generate\b", "Generated"),
    (r"\bLoaded or switched\b", "Switched"),
    (r"\bLoaded and switch\b", "Switched"),
    (r"\bOpened or navigated\b", "Opened"),
    (r"\bOpened and navigate\b", "Opened"),
    (r"\bInstalled or updated\b", "Updated"),
    (r"\bCreate or regenerate\b", "Created"),
    (r"\bCreated or regenerate\b", "Created"),
    (r"\bor stable alias\b", ""),
    (r"\bor end frame\b", ""),
    (r"\bor Fusion Text\+\b", ""),
    (r"\bor single-frame\b", ""),
    (r"\bor a direct XML preset path\b", ""),
    (r"\bor remove\b", ""),
    (r"\bfrom transcript and audio activity\b", "from podcast audio"),
    (r"\bfrom transcript or audio activity\b", "from podcast audio"),
    (r";\s*also accepts.*", ""),
    (r"\(\s*compatibility alias\s*\)", ""),
    (r"\(\.setting file\)", "template file"),
    (r"\.setting", "template"),
    (r"\.drpx", "preset package"),
    (r"\.drfx", "preset package"),
    (r"\bProject\.SetRenderSettings keys?\b", "render setting"),
    (r"\bcustom edit custom edit\b", "custom edit"),
    (r"\bcustom edit UI custom edit\b", "custom edit panel"),
    (r"\bclean clean\b", "clean"),
    (r"\ba edit setup\b", "an edit setup"),
    (r"\bfile file\b", "file"),
    (r"\bInstalled and update\b", "Updated"),
    (r"\bSaved and update\b", "Saved"),
    (r"\bConverted and validate\b", "Checked"),
    (r"\bImported and assemble\b", "Imported and assembled"),
    (r"\ban transition\b", "a transition"),
    (r"\(replaces existing clips\)", ""),
    (r"\(clean blocking wait\)", ""),
    (r"\bwhen available DaVinci Resolve\b", ""),
    (r"\bDaVinci Resolve timeline and Fusion DaVinci Resolve only\b", "DaVinci Resolve and Fusion"),
    (r"\ball-target check\b", "target check"),
)

VERB_REWRITES = (
    ("Show current ", "Read current "),
    ("Show the current ", "Read the current "),
    ("Show ", "Checked "),
    ("List ", "Listed "),
    ("Read ", "Read "),
    ("Return ", "Read "),
    ("Get or set ", "Read or updated "),
    ("Get ", "Read "),
    ("Inspect ", "Inspected "),
    ("Validate ", "Validated "),
    ("Verify ", "Verified "),
    ("Analyze ", "Analyzed "),
    ("Audit ", "Audited "),
    ("Create or update ", "Created or updated "),
    ("Create/update ", "Created or updated "),
    ("Create and switch ", "Created and switched "),
    ("Create ", "Created "),
    ("Build ", "Built "),
    ("Compose ", "Composed "),
    ("Generate ", "Generated "),
    ("Generate, link, and unlink ", "Managed "),
    ("Set or clear ", "Set or cleared "),
    ("Get, set, or clear ", "Read, set, or cleared "),
    ("Get, set, and clear ", "Updated "),
    ("Get/set ", "Read or updated "),
    ("Set ", "Set "),
    ("Clear ", "Cleared "),
    ("Add ", "Added "),
    ("Apply ", "Applied "),
    ("Append ", "Appended "),
    ("Archive ", "Archived "),
    ("Assign ", "Assigned "),
    ("Attach ", "Attached "),
    ("Auto-sync ", "Synced "),
    ("Backup ", "Backed up "),
    ("Batch-add ", "Added "),
    ("Batch ", "Updated "),
    ("Bounce ", "Bounced "),
    ("Clarify ", "Clarified "),
    ("Close ", "Closed "),
    ("Connect ", "Connected "),
    ("Convert ", "Converted "),
    ("Detach ", "Detached "),
    ("Disable ", "Disabled "),
    ("Disconnect ", "Disconnected "),
    ("Emulate ", "Emulated "),
    ("Enable ", "Enabled "),
    ("Ensure ", "Ensured "),
    ("Extract ", "Extracted "),
    ("Finalize ", "Finalized "),
    ("Find ", "Found "),
    ("Flatten ", "Flattened "),
    ("Freeze ", "Froze "),
    ("Go ", "Opened "),
    ("Grab ", "Grabbed "),
    ("Insert ", "Inserted "),
    ("Link ", "Linked "),
    ("Load/switch ", "Loaded or switched "),
    ("Lock ", "Locked "),
    ("Manage ", "Managed "),
    ("Measure ", "Measured "),
    ("Mute ", "Muted "),
    ("Navigate ", "Navigated "),
    ("Open/navigate ", "Opened or navigated "),
    ("Overwrite ", "Overwrote "),
    ("Package ", "Packaged "),
    ("Paste ", "Pasted "),
    ("Ping ", "Pinged "),
    ("Play ", "Played "),
    ("Place ", "Placed "),
    ("Plan ", "Planned "),
    ("Preview ", "Previewed "),
    ("Probe ", "Probed "),
    ("Prune ", "Pruned "),
    ("Queue ", "Queued "),
    ("Recover ", "Recovered "),
    ("Relink ", "Relinked "),
    ("Reorder ", "Reordered "),
    ("Repair ", "Repaired "),
    ("Report ", "Checked "),
    ("Recommend ", "Recommended "),
    ("Replace ", "Replaced "),
    ("Reset ", "Reset "),
    ("Reverse ", "Reversed "),
    ("Scaffold ", "Scaffolded "),
    ("Search ", "Searched "),
    ("Select ", "Selected "),
    ("Solo ", "Soloed "),
    ("Split ", "Split "),
    ("Snapshot ", "Captured "),
    ("Summarize ", "Summarized "),
    ("Transcode ", "Transcoded "),
    ("Transcribe ", "Transcribed "),
    ("Unlink ", "Unlinked "),
    ("Unlock ", "Unlocked "),
    ("Unmute ", "Unmuted "),
    ("Unpack ", "Unpacked "),
    ("Update ", "Updated "),
    ("Wait ", "Waited "),
    ("Remove ", "Removed "),
    ("Delete ", "Deleted "),
    ("Rename ", "Renamed "),
    ("Duplicate ", "Duplicated "),
    ("Import ", "Imported "),
    ("Export ", "Exported "),
    ("Open ", "Opened "),
    ("Switch ", "Switched "),
    ("Start ", "Started "),
    ("Stop ", "Stopped "),
    ("Cancel ", "Canceled "),
    ("Load ", "Loaded "),
    ("Save ", "Saved "),
    ("Copy ", "Copied "),
    ("Move ", "Moved "),
    ("Normalize ", "Normalized "),
    ("Trigger ", "Triggered "),
    ("Configure ", "Configured "),
    ("Render ", "Rendered "),
    ("Run ", "Ran "),
    ("Patch ", "Patched "),
    ("Print ", "Printed "),
    ("Restore ", "Restored "),
    ("Reveal ", "Revealed "),
    ("Resolve ", "Resolved "),
    ("Test ", "Tested "),
    ("Trim ", "Trimmed "),
    ("Ripple-delete ", "Removed "),
    ("Install or update ", "Installed or updated "),
    ("Install ", "Installed "),
    ("Uninstall ", "Uninstalled "),
    ("Refresh ", "Refreshed "),
    ("Quit ", "Quit "),
    ("Launch ", "Launched "),
)

INFINITIVE_REWRITES = {
    "Changed": "change",
    "Read": "read",
    "Checked": "check",
    "Measured": "measure",
    "Probed": "probe",
    "Listed": "list",
    "Inspected": "inspect",
    "Validated": "validate",
    "Verified": "verify",
    "Analyzed": "analyze",
    "Audited": "audit",
    "Created": "create",
    "Built": "build",
    "Composed": "compose",
    "Generated": "generate",
    "Set": "set",
    "Cleared": "clear",
    "Activated": "activate",
    "Added": "add",
    "Adjusted": "adjust",
    "Applied": "apply",
    "Appended": "append",
    "Archived": "archive",
    "Assigned": "assign",
    "Attached": "attach",
    "Auditioned": "audition",
    "Backed": "back up",
    "Balanced": "balance",
    "Bounced": "bounce",
    "Clarified": "clarify",
    "Closed": "close",
    "Connected": "connect",
    "Compared": "compare",
    "Converted": "convert",
    "Detached": "detach",
    "Detected": "detect",
    "Disabled": "disable",
    "Disconnected": "disconnect",
    "Drew": "draw",
    "Emulated": "emulate",
    "Enabled": "enable",
    "Ensured": "ensure",
    "Extracted": "extract",
    "Finalized": "finalize",
    "Found": "find",
    "Filled": "fill",
    "Flattened": "flatten",
    "Froze": "freeze",
    "Grabbed": "grab",
    "Hid": "hide",
    "Inserted": "insert",
    "Linked": "link",
    "Locked": "lock",
    "Managed": "manage",
    "Matched": "match",
    "Muted": "mute",
    "Navigated": "navigate",
    "Overwrote": "overwrite",
    "Packaged": "package",
    "Pasted": "paste",
    "Pinged": "ping",
    "Played": "play",
    "Placed": "place",
    "Planned": "plan",
    "Previewed": "preview",
    "Pruned": "prune",
    "Queued": "queue",
    "Recovered": "recover",
    "Recorded": "record",
    "Recommended": "recommend",
    "Relinked": "relink",
    "Reordered": "reorder",
    "Repaired": "repair",
    "Replaced": "replace",
    "Reset": "reset",
    "Refined": "refine",
    "Reversed": "reverse",
    "Scaffolded": "scaffold",
    "Sampled": "sample",
    "Searched": "search",
    "Selected": "select",
    "Slid": "slide",
    "Slipped": "slip",
    "Soloed": "solo",
    "Split": "split",
    "Captured": "capture",
    "Summarized": "summarize",
    "Synced": "sync",
    "Tracked": "track",
    "Transcoded": "transcode",
    "Transcribed": "transcribe",
    "Unlinked": "unlink",
    "Unlocked": "unlock",
    "Unmuted": "unmute",
    "Unpacked": "unpack",
    "Updated": "update",
    "Waited": "wait",
    "Removed": "remove",
    "Rolled": "roll",
    "Deleted": "delete",
    "Renamed": "rename",
    "Duplicated": "duplicate",
    "Imported": "import",
    "Exported": "export",
    "Opened": "open",
    "Switched": "switch",
    "Started": "start",
    "Stopped": "stop",
    "Canceled": "cancel",
    "Cleaned": "clean",
    "Loaded": "load",
    "Saved": "save",
    "Showed": "show",
    "Copied": "copy",
    "Moved": "move",
    "Normalized": "normalize",
    "Triggered": "trigger",
    "Configured": "configure",
    "Rendered": "render",
    "Ran": "run",
    "Patched": "patch",
    "Printed": "print",
    "Prepared": "prepare",
    "Restored": "restore",
    "Revealed": "reveal",
    "Located": "locate",
    "Resolved": "resolve",
    "Tested": "test",
    "Trimmed": "trim",
    "Installed": "install",
    "Uninstalled": "uninstall",
    "Refreshed": "refresh",
    "Quit": "quit",
    "Launched": "launch",
}


@dataclass(frozen=True)
class ParameterLabel:
    name: str
    kind: str
    cli_names: tuple[str, ...]
    classification: str
    public_effect: str
    label: str | None = None
    modifier_label: str | None = None
    help_label: str | None = None
    dry_run_label: str | None = None


def _first_sentence(value: str) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    # Keep explanatory suffixes out of compact UI labels.
    text = re.split(r"\s+Workaround:\s+", text, maxsplit=1)[0]
    text = re.split(r"\s+Use when:\s+", text, maxsplit=1)[0]
    match = re.match(r"(.+?[.!?])(?:\s|$)", text)
    return (match.group(1) if match else text).strip()


def _clean_label_text(value: str) -> str:
    text = value.strip().strip(".")
    text = text.replace("cutagent-cli", "DaVinci Resolve automation")
    text = text.replace("Resolve-native", "DaVinci Resolve native")
    text = text.replace("DaVinci Resolve's", "DaVinci Resolve")
    text = text.replace("Resolve's", "DaVinci Resolve")
    text = text.replace("ResolveFX/OFX", "DaVinci Resolve and OFX")
    text = text.replace("ResolveFX", "DaVinci Resolve effects")
    text = re.sub(
        r"\bResolve (Developer|Utility|runtime|scripts|script|page|render|automation|dict|UI|exposes|support|Scripting)\b",
        r"DaVinci Resolve \1",
        text,
    )
    text = text.replace("DaVinci Resolve UI", "DaVinci Resolve interface")
    text = text.replace("Media Pool", "media pool")
    text = text.replace("Disk DB", "project database")
    text = text.replace("DB", "database")
    text = text.replace("GUI", "interface")
    text = text.replace("API", "automation API")
    text = text.replace("JSON", "structured data")
    text = text.replace("LUT", "LUT")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = _apply_editor_copy_replacements(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _apply_editor_copy_replacements(value: str) -> str:
    text = value
    for pattern, replacement in EDITOR_COPY_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("/", " and ")
    text = re.sub(r"\bor\b", "and", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\busing\s+using\b", "using", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwith\s+with\b", "with", text, flags=re.IGNORECASE)
    text = re.sub(r"\band\s+and\b", "and", text, flags=re.IGNORECASE)
    text = text.replace("DaVinci DaVinci Resolve", "DaVinci Resolve")
    text = text.replace("DaVinci Resolve DaVinci Resolve", "DaVinci Resolve")
    text = text.replace("CutCutAgent", "CutAgent")
    text = text.replace("settingss", "settings")
    return text.strip(" -:;,.")


def _sanitize_public_label(value: str) -> str:
    text = re.sub(r"(?<!DaVinci )\bResolve\b", "DaVinci Resolve", value)
    text = text.replace("DaVinci DaVinci Resolve", "DaVinci Resolve")
    text = text.replace("daVinci Resolve", "DaVinci Resolve")
    text = text.replace("automation APIs", "automation API")
    text = _apply_editor_copy_replacements(text)
    return re.sub(r"\s+", " ", text).strip()


def _label_from_summary(command: dict[str, Any]) -> str:
    path = str(command.get("path") or "")
    if path in COMMAND_LABEL_OVERRIDES:
        return _sanitize_public_label(COMMAND_LABEL_OVERRIDES[path])

    summary = _clean_label_text(_first_sentence(str(command.get("summary") or "")))
    if not summary:
        return _sanitize_public_label(f"Finished {path.split(' ', 1)[0]} work")

    summary_lower = summary.lower()
    for prefix, replacement in VERB_REWRITES:
        if summary_lower.startswith(prefix.lower()):
            return _sanitize_public_label(replacement + summary[len(prefix) :].strip())

    return _sanitize_public_label("Finished " + summary[0].lower() + summary[1:])


def _help_label_from_label(path: str, label: str) -> str:
    if path in HELP_LABEL_OVERRIDES:
        return _sanitize_public_label(HELP_LABEL_OVERRIDES[path])
    return _help_label_from_action_label(label)


def _help_label_from_action_label(label: str) -> str:
    phrase = _infinitive_phrase_from_label(label)
    if phrase:
        phrase = phrase.replace("current timeline", "the current timeline")
        phrase = phrase.replace("current DaVinci Resolve", "the current DaVinci Resolve")
        phrase = re.sub(r"\bthe the\b", "the", phrase)
        return _sanitize_public_label(f"Reviewed how to {phrase}")
    return "Reviewed DaVinci Resolve action help"


def _infinitive_phrase_from_label(label: str) -> str:
    words = label.split(" ", 1)
    if not words:
        return ""
    verb = INFINITIVE_REWRITES.get(words[0], words[0].lower())
    rest = words[1] if len(words) > 1 else ""
    if verb == "back up" and rest.startswith("up "):
        rest = rest[3:]
    phrase = f"{verb} {rest}".strip()
    phrase = phrase.replace(" and restored ", " and restore ")
    phrase = phrase.replace(" and generated ", " and generate ")
    phrase = phrase.replace(" and updated ", " and update ")
    return phrase


def _dry_run_label(label: str) -> str:
    return _dry_run_label_from_action_label(label)


def _dry_run_label_from_action_label(label: str) -> str:
    phrase = _infinitive_phrase_from_label(label)
    if not phrase:
        return "Previewed a DaVinci Resolve action"
    phrase = re.sub(r"\bthe the\b", "the", phrase)
    return _sanitize_public_label(f"Previewed how to {phrase}")


def _public_phrase_from_name(name: str) -> str:
    text = name.replace("_", " ").replace("-", " ").strip()
    replacements = {
        "cls": "",
        "db": "dB",
        "dst": "destination",
        "json": "file",
        "or": "and",
        "payload": "file",
        "plugin": "extension",
        "route": "method",
        "runtime": "validation",
        "src": "source",
        "tc": "timecode",
        "tool": "node",
        "ui": "interface",
    }
    words = [replacements.get(word, word) for word in re.split(r"\s+", text) if word]
    return " ".join(words)


def _behavior_modifier_phrase(name: str) -> str | None:
    suffixes = {
        "allow_existing": "allowing existing items",
        "allow_extend": "allowing timeline extensions",
        "allow_insert": "allowing timeline inserts",
        "allow_multiple": "allowing multiple matches",
        "allow_partial": "allowing partial matches",
        "allow_temp_append": "allowing a temporary append",
        "apply": "and applied the result",
        "audio": "including audio output",
        "audio_sync": "using audio synchronization",
        "cleanup": "and cleaned up temporary items",
        "clamp_half_clip": "with fades clamped to half the clip",
        "cleaner": "with dialogue cleanup enabled",
        "comp_enable": "with compression enabled",
        "enable": "and enabled the setting",
        "ensure_tracks": "while ensuring tracks exist",
        "fail_fast": "and stopped at the first failure",
        "flip_x": "with horizontal flip",
        "flip_y": "with vertical flip",
        "gate_enable": "with gate processing enabled",
        "include_audio": "including audio",
        "include_nested": "including nested items",
        "lifter": "with voice lifting enabled",
        "limiter_enable": "with limiter processing enabled",
        "mode": "using the selected mode",
        "multi_pass": "using multi-pass encoding",
        "network_optimization": "with network optimization",
        "patch_db_subtype": "and matched the track format",
        "replace_active_timeline": "and replaced the active timeline",
        "replace_media": "and replaced existing media",
        "replace_program_audio": "and replaced program audio",
        "require_count_match": "requiring count matches",
        "retain_embedded_audio": "while retaining embedded audio",
        "retain_video_metadata": "while retaining video metadata",
        "rename_tracks": "and renamed tracks",
        "shift": "and shifted overlapping items",
        "skip_adjacent_same_track": "skipping adjacent same-track fades",
        "skip_first_segment": "skipping the first segment",
        "start": "and started the job",
        "strict": "requiring strict matches",
        "style_markdown": "using styled Markdown",
        "sync": "and synchronized sources",
        "video": "including video output",
    }

    if name == "include_ui":
        return "with interface details"
    if name == "recursive":
        return "across nested folders"
    if name == "include_generated":
        return "including generated items"
    if name == "wait":
        return "and waited for completion"
    if name == "verify":
        return "with verification"
    if name == "plan_only":
        return "as a planning pass"
    if name == "write_plan":
        return "and saved the plan"
    if name == "force":
        return "with forced cleanup"
    if name == "full":
        return "in full detail"
    if name == "clear":
        return "with clearing enabled"
    if name == "set":
        return "with updating enabled"
    if name in suffixes:
        return suffixes[name]
    return None


PARAMETER_MODIFIER_OVERRIDES = {
    "audio duck:threshold_db": "with ducking threshold",
    "audio duck:ratio": "with ducking ratio",
    "audio duck:attack_ms": "with attack time",
    "audio duck:release_ms": "with release time",
    "clip audio-eq:preset": "with EQ preset",
    "clip audio-eq:band": "with EQ band",
    "clip audio-eq:ui_band": "with EQ band",
    "clip audio-eq:filter_type": "with EQ filter type",
    "clip audio-eq:freq": "with EQ frequency",
    "clip audio-eq:gain_db": "with EQ gain",
    "clip audio-eq:q": "with EQ Q",
    "clip audio-gain:db": "with gain amount",
    "clip audio-normalize:target_dbfs": "with target peak level",
    "clip audio-pan:value": "with pan value",
    "clip audio-pitch:semitones": "with semitone shift",
    "clip audio-pitch:cents": "with cent offset",
    "fairlight audio-gain batch:db": "with gain amount",
    "fairlight dynamics set:comp_threshold": "with compressor threshold",
    "fairlight dynamics set:comp_ratio": "with compressor ratio",
    "fairlight dynamics set:comp_knee": "with compressor knee",
    "fairlight dynamics set:comp_mix": "with compressor mix",
    "fairlight dynamics set:gate_threshold": "with gate threshold",
    "fairlight dynamics set:limiter_threshold": "with limiter threshold",
    "timeline marker add:color": "with marker color",
    "timeline marker add:name": "with marker name",
    "timeline marker add:duration": "with marker duration",
    "timeline marker batch:default_color": "with marker color",
    "clip marker add:color": "with marker color",
    "clip marker add:marker_name": "with marker name",
    "clip marker add:duration": "with marker duration",
    "clip marker add:frame_domain": "using marker frame domain",
    "media marker add:color": "with marker color",
    "media marker add:marker_name": "with marker name",
    "media marker add:duration": "with marker duration",
    "clip color:set": "with clip color",
    "media color set:color": "with clip color",
    "timeline clip-color batch:track_type": "with track type",
    "timeline clip-color batch:track_index": "with track number",
    "fairlight track-color:color": "with track color",
}

def _append_modifier(base_label: str, modifier: str) -> str:
    if not modifier:
        return base_label
    if modifier.startswith("and "):
        return f"{base_label} {modifier}"
    if modifier.startswith("with ") and re.search(r"\bwith\b", base_label):
        return f"{base_label} and {modifier[5:]}"
    return f"{base_label} {modifier}"


def _parameter_modifier_phrase(command: dict[str, Any], name: str, public_phrase: str) -> str:
    path = str(command.get("path") or "")
    override = PARAMETER_MODIFIER_OVERRIDES.get(f"{path}:{name}")
    if override:
        return override
    if name == "start" or name.startswith("start_"):
        return "from the chosen start point"
    if name.startswith("allow_"):
        return f"allowing {_public_phrase_from_name(name[6:])}"
    if name == "mode":
        return "using the chosen mode"
    return f"with {public_phrase or 'selected details'}"


def _label_for_behavior_option(base_label: str, name: str, path: str = "") -> str:
    if name == "include_ui":
        return _sanitize_public_label(f"{base_label} with interface details")
    if name == "recursive":
        return _sanitize_public_label(f"{base_label} across nested folders")
    if name == "include_generated":
        return _sanitize_public_label(f"{base_label} including generated items")
    if name == "wait":
        return _sanitize_public_label(f"{base_label} and waited for completion")
    if name == "verify":
        return _sanitize_public_label(f"{base_label} with verification")
    if name == "plan_only":
        return _sanitize_public_label(f"Prepared a plan for: {base_label[0].lower() + base_label[1:]}")
    if name == "write_plan":
        return _sanitize_public_label(f"Saved a plan for: {base_label[0].lower() + base_label[1:]}")
    if name == "force":
        if path == "project delete":
            return _sanitize_public_label(f"{base_label} without an interactive confirmation")
        return _sanitize_public_label(f"{base_label} with forced cleanup")
    if name == "full":
        return _sanitize_public_label(f"{base_label} in full detail")
    if name == "clear":
        if base_label.startswith("Set "):
            return _sanitize_public_label(base_label.replace("Set ", "Cleared ", 1))
        if base_label.startswith("Read or updated "):
            return _sanitize_public_label(base_label.replace("Read or updated ", "Cleared ", 1))
        return _sanitize_public_label(f"{base_label} with clearing enabled")
    if name == "set":
        if base_label.startswith("Read or updated "):
            return _sanitize_public_label(base_label.replace("Read or updated ", "Updated ", 1))
        if base_label.startswith("Read "):
            return _sanitize_public_label(base_label.replace("Read ", "Updated ", 1))
        if base_label.startswith("Checked "):
            return _sanitize_public_label(base_label.replace("Checked ", "Set ", 1))
        return _sanitize_public_label(f"{base_label} with updating enabled")
    modifier = _behavior_modifier_phrase(name)
    return _sanitize_public_label(f"{base_label} {modifier or f'with {_public_phrase_from_name(name)}'}")


def _classify_parameter(command: dict[str, Any], parameter: dict[str, Any]) -> ParameterLabel:
    name = str(parameter.get("name") or "")
    kind = str(parameter.get("kind") or "")
    cli_names = tuple(str(item) for item in parameter.get("cli_names") or ())
    public_phrase = _public_phrase_from_name(name)

    if kind != "option":
        modifier_label = _parameter_modifier_phrase(command, name, public_phrase)
        variant_label = _append_modifier(_label_from_summary(command), modifier_label)
        return ParameterLabel(
            name=name,
            kind=kind,
            cli_names=cli_names,
            classification="argument",
            public_effect=f"Supplies the {public_phrase or 'target'} for this DaVinci Resolve action.",
            modifier_label=modifier_label,
            help_label=_help_label_from_action_label(variant_label),
            dry_run_label=_dry_run_label_from_action_label(variant_label),
        )

    clean_cli_names = {item.split("/", 1)[0] for item in cli_names}
    if clean_cli_names & OUTPUT_ONLY_FLAGS:
        return ParameterLabel(
            name=name,
            kind=kind,
            cli_names=cli_names,
            classification="output_format",
            public_effect="Changes only the private output format, not the public action label.",
        )

    if name in BEHAVIOR_NAMES or any("/" in item for item in cli_names):
        path = str(command.get("path") or "")
        label = _label_for_behavior_option(_label_from_summary(command), name, path)
        modifier_label = (
            "without an interactive confirmation"
            if path == "project delete" and name == "force"
            else _behavior_modifier_phrase(name)
        )
        return ParameterLabel(
            name=name,
            kind=kind,
            cli_names=cli_names,
            classification="behavior",
            public_effect=f"Changes how the DaVinci Resolve action behaves through {public_phrase}.",
            label=label,
            modifier_label=modifier_label or f"with {public_phrase}",
            help_label=_help_label_from_action_label(label),
            dry_run_label=_dry_run_label_from_action_label(label),
        )

    if name in TARGET_DETAIL_NAMES or any(token in name for token in ("path", "file", "name", "timeline", "clip", "track")):
        modifier_label = _parameter_modifier_phrase(command, name, public_phrase)
        variant_label = _append_modifier(_label_from_summary(command), modifier_label)
        return ParameterLabel(
            name=name,
            kind=kind,
            cli_names=cli_names,
            classification="target_detail",
            public_effect=f"Identifies the {public_phrase or 'target'} for the same public action.",
            modifier_label=modifier_label,
            help_label=_help_label_from_action_label(variant_label),
            dry_run_label=_dry_run_label_from_action_label(variant_label),
        )

    modifier_label = _parameter_modifier_phrase(command, name, public_phrase)
    variant_label = _append_modifier(_label_from_summary(command), modifier_label)
    return ParameterLabel(
        name=name,
        kind=kind,
        cli_names=cli_names,
        classification="option",
        public_effect=f"Adjusts {public_phrase or 'options'} without requiring a separate public action label.",
        modifier_label=modifier_label,
        help_label=_help_label_from_action_label(variant_label),
        dry_run_label=_dry_run_label_from_action_label(variant_label),
    )


def _parameter_to_json(parameter: ParameterLabel) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": parameter.name,
        "kind": parameter.kind,
        "classification": parameter.classification,
        "public_effect": _sanitize_public_label(parameter.public_effect),
    }
    if parameter.cli_names:
        payload["cli_names"] = list(parameter.cli_names)
    if parameter.label:
        payload["label"] = _sanitize_public_label(parameter.label)
    if parameter.modifier_label:
        payload["modifier_label"] = _sanitize_public_label(parameter.modifier_label)
    if parameter.help_label:
        payload["help_label"] = _sanitize_public_label(parameter.help_label)
    if parameter.dry_run_label:
        payload["dry_run_label"] = _sanitize_public_label(parameter.dry_run_label)
    return payload


def build_public_command_label_catalog() -> dict[str, Any]:
    commands = [
        row
        for row in command_catalog_rows(include_parameters=True)
        if row.get("path") != "discover" and not row.get("legacy")
    ]

    entries: dict[str, dict[str, Any]] = {}
    for command in commands:
        path = str(command["path"])
        label = _label_from_summary(command)
        parameters = [
            _parameter_to_json(_classify_parameter(command, parameter))
            for parameter in command.get("parameters", [])
        ]
        entries[path] = {
            "label": label,
            "help_label": _help_label_from_label(path, label),
            "dry_run_label": _dry_run_label(label),
            "parameters": parameters,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_from": "cutagent_cli.command_catalog.command_catalog_rows",
        "command_count": len(commands),
        "global_flags": {
            "help": list(HELP_FLAGS),
            "dry_run": list(DRY_RUN_FLAGS),
            "output_only": sorted(OUTPUT_ONLY_FLAGS),
        },
        "commands": entries,
    }
