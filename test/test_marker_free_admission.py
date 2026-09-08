from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native"))

from cutagent_cli.prepared_action_marker import (
    ACTION_ID,
    TimelineMarkerAddExecutionAuthority,
)


class MarkerFreeAdmissionTests(unittest.TestCase):
    def test_marker_add_enters_exact_prepared_carrier_scope(self):
        calls = []

        def marker_adder(_conn, position, color, name, note, duration):
            calls.append((position, color, name, note, duration))
            return {
                "readback": {
                    "record_frame": 86400,
                    "color": color,
                    "name": name,
                    "note": note,
                    "duration": duration,
                }
            }

        observed_admission = []

        @contextmanager
        def admission(action_id, command_id, authority, handler, context):
            observed_admission.append((action_id, command_id, authority, handler, context))
            yield

        authority = TimelineMarkerAddExecutionAuthority(
            connection_factory=lambda **_kwargs: SimpleNamespace(),
            marker_adder=marker_adder,
            mutation_guard=lambda _conn: None,
        )
        authority.bind_private_timeline_inspector(
            lambda _payload: {
                "mutationGuard": "sha256:" + "a" * 64,
                "snapshot": {
                    "start": {"value": {"value": 86400}},
                    "revision": "revision_after",
                },
            }
        )
        context = {
            "actionId": ACTION_ID,
            "timeline": {"mutationGuard": "sha256:" + "a" * 64},
            "exactRequestBinding": {
                "identities": {
                    "projectId": "project_test",
                    "timelineId": "timeline_test",
                    "targetIds": ["marker_test"],
                }
            },
        }
        marker = {
            "recordFrame": 86400,
            "color": "Blue",
            "name": "Free marker",
            "note": "temporary",
            "durationFrames": 1,
        }

        with patch(
            "cutagent_cli.prepared_action_marker._prepared_action_admission_scope",
            admission,
        ):
            result = authority.invoke_admitted_handler(
                ACTION_ID, context, {}, {"marker": marker}
            )

        self.assertEqual(calls, [("0f", "Blue", "Free marker", "temporary", 1)])
        self.assertEqual(len(observed_admission), 1)
        self.assertEqual(observed_admission[0][0:2], (ACTION_ID, "timeline.marker.add"))
        self.assertIs(observed_admission[0][2], authority)
        self.assertIs(observed_admission[0][3], marker_adder)
        self.assertIs(observed_admission[0][4], context)
        self.assertEqual(result["marker"]["id"], "marker_test")
        self.assertEqual(result["timelineRevision"], "revision_after")


if __name__ == "__main__":
    unittest.main()
