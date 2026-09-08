"""Shared evidence modality truth for the Fusion/DCTL/LUT packet."""

from __future__ import annotations


_FILE_EVIDENCE_COMMANDS = frozenset({
    "fusion.generate",
    "fusion.setting.inspect",
    "fusion.setting.summary",
    "fusion.setting.validate",
    "fusion.template.assets.add",
    "fusion.template.assets.list",
    "fusion.template.dir",
    "fusion.template.icon.set",
    "fusion.template.install",
    "fusion.template.package_drfx",
    "fusion.template.scaffold",
    "fusion.template.show",
    "fusion.template.uninstall",
    "fusion.template.validate",
    "lut.convert",
    "lut.generate.identity",
    "lut.inspect",
    "lut.install",
    "lut.list",
    "lut.remove",
    "lut.validate",
})
_OFFLINE_STRUCTURAL_COMMANDS = frozenset({
    "fusion.setting.center_to_polypath",
    "fusion.setting.polypath_to_center",
})


def fusion_minimum_evidence(command_id: str, operation_class: str) -> tuple[str, ...]:
    """Return the exact minimum modalities declared at policy admission."""

    if command_id == "fusion.template.dir":
        return ("readback", "structural")
    if command_id in _FILE_EVIDENCE_COMMANDS:
        return ("file",)
    if operation_class == "read":
        return ("structural",)
    return ("readback", "structural")


def fusion_emitted_evidence(command_id: str) -> tuple[str, ...]:
    """Return the modalities emitted by independent runtime verification."""

    if command_id == "fusion.template.dir":
        return ("structural", "readback")
    if command_id in _FILE_EVIDENCE_COMMANDS:
        return ("file",)
    if command_id in _OFFLINE_STRUCTURAL_COMMANDS:
        return ("structural", "readback")
    return ("structural", "readback")
