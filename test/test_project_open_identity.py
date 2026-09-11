from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native"))

from cutagent_cli.private_sdk_descriptors import (  # noqa: E402
    project_render_storage_media_prepared_action as _project_descriptors,
)
from cutagent_cli.private_sdk_descriptors import (  # noqa: E402
    project_media_extended_prepared_action as project_actions,
)


class _Project:
    def __init__(self, name, proxy_token):
        self._name = name
        self._proxy_token = proxy_token

    def GetName(self):
        return self._name

    def GetUniqueId(self):
        return self._proxy_token

    def GetCurrentTimeline(self):
        return None


class _ProjectManager:
    def __init__(self, initial, opened):
        self.current = initial
        self.opened = opened

    def GetCurrentProject(self):
        return self.current

    def LoadProject(self, name):
        if name != self.opened.GetName():
            return None
        self.current = self.opened
        return self.opened


class _Connection:
    def __init__(self, initial, opened):
        self.project_manager = _ProjectManager(initial, opened)
        self.project = initial
        self.timeline = None

    def refresh(self):
        return None


class ProjectOpenIdentityTests(unittest.TestCase):
    def test_open_uses_the_documented_native_project_identity(self):
        conn = _Connection(
            _Project("Before", "volatile-before"),
            _Project("Target", "volatile-after"),
        )
        descriptor = project_actions.ProjectLifecycleDescriptor(
            "cutagent.action.project.open", lambda value: value
        )
        prepared = {
            "lowering": {"input": {"name": "Target"}},
            "targets": [{"nativeId": "volatile-after"}],
        }

        with (
            patch.object(project_actions, "get_connection", return_value=conn),
            patch.object(
                project_actions.project_library_ops,
                "current_project_folder_project_identity",
                return_value="stable-project-db-id",
            ) as stable_identity,
        ):
            result = descriptor.execute({}, prepared)
            verification = descriptor.verify({}, prepared, result)

        self.assertEqual(result["nativeProjectId"], "volatile-after")
        self.assertEqual(verification["outcome"], "passed")
        stable_identity.assert_not_called()

    def test_already_open_uses_the_same_documented_native_identity(self):
        target = _Project("Target", "volatile-current")
        conn = _Connection(target, target)
        descriptor = project_actions.ProjectLifecycleDescriptor(
            "cutagent.action.project.open", lambda value: value
        )
        prepared = {
            "lowering": {"input": {"name": "Target"}},
            "targets": [{"nativeId": "volatile-current"}],
        }

        with (
            patch.object(project_actions, "get_connection", return_value=conn),
            patch.object(
                project_actions.project_library_ops,
                "current_project_folder_project_identity",
                return_value="stable-project-db-id",
            ),
        ):
            result = descriptor.execute({}, prepared)
            verification = descriptor.verify({}, prepared, result)

        self.assertTrue(result["alreadyOpen"])
        self.assertEqual(result["nativeProjectId"], "volatile-current")
        self.assertEqual(verification["outcome"], "passed")


if __name__ == "__main__":
    unittest.main()
