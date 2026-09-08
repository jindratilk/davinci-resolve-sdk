"""Private signed-carrier descriptor contributions.

These modules are runtime implementation details. Imports stay lazy because
some maintainer-only descriptor families depend on inventory modules that are
intentionally absent from the distributable CutAgent CLI wheel.
"""

from __future__ import annotations

from importlib import import_module


_EXPORT_MODULES = {
    "PROFESSIONAL_PRIMITIVE_ACTION_IDS": ".professional_primitive_prepared_action",
    "REVIEWED_CLIP_PRIMITIVE_ACTION_IDS": ".professional_primitive_prepared_action",
    "ProfessionalPrimitivePreparedActionDescriptor": ".professional_primitive_prepared_action",
    "SystemKeyframeModeSemanticOwner": ".professional_primitive_prepared_action",
    "professional_primitive_prepared_action_descriptors": ".professional_primitive_prepared_action",
    "PrivateDescriptorUnavailable": ".project_render_storage_media",
    "prepare_project_render_storage_media_action": ".project_render_storage_media",
    "project_render_storage_media_descriptor_packet": ".project_render_storage_media",
    "project_render_storage_media_public_summary": ".project_render_storage_media",
    "PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS": ".project_render_storage_media_prepared_action",
    "project_render_storage_media_prepared_action_descriptors": ".project_render_storage_media_prepared_action",
}


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "PROFESSIONAL_PRIMITIVE_ACTION_IDS",
    "PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS",
    "REVIEWED_CLIP_PRIMITIVE_ACTION_IDS",
    "PrivateDescriptorUnavailable",
    "ProfessionalPrimitivePreparedActionDescriptor",
    "SystemKeyframeModeSemanticOwner",
    "prepare_project_render_storage_media_action",
    "professional_primitive_prepared_action_descriptors",
    "project_render_storage_media_descriptor_packet",
    "project_render_storage_media_prepared_action_descriptors",
    "project_render_storage_media_public_summary",
]
