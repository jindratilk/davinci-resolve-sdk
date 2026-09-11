import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HostedServiceStubTests(unittest.TestCase):
    def run_cli(self, arguments):
        digest = hashlib.sha256(
            json.dumps(arguments, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "native"),
            "DAVINCI_RESOLVE_SDK_COMMAND_SHA256": digest,
            "DAVINCI_RESOLVE_SDK_PARENT_PID": str(os.getpid()),
            # These values would make an accidental broker call observable.
            "CUTAGENT_CLI_BROKER_URL": "https://127.0.0.1:1/must-not-connect",
            "CUTAGENT_CLI_BROKER_TOKEN": "must-not-authenticate",
            "CUTAGENT_CLI_BROKER_CAPABILITY": "must-not-authorize",
            "DASHSCOPE_API_KEY": "must-not-contact-provider",
            "DASHSCOPE_WORKSPACE_ENDPOINT": "https://127.0.0.1:1/must-not-connect",
        }
        return subprocess.run(
            [sys.executable, str(ROOT / "native" / "cutagent"), *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def assert_stub(self, result, service, message):
        self.assertEqual(result.returncode, 4, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "HOSTED_SERVICE_REQUIRES_CUTAGENT_APP")
        self.assertEqual(payload["error"]["details"]["service"], service)
        self.assertEqual(payload["error"]["details"]["landing_page_url"], "https://cutagent.ai")
        self.assertEqual(payload["error"]["message"], f"{message} Explore plans: https://cutagent.ai.")
        self.assertEqual(payload["error"]["suggested_fix"], "Explore the CutAgent desktop app at https://cutagent.ai.")
        for key in ("network_attempted", "upload_attempted", "billing_attempted", "authentication_attempted"):
            self.assertFalse(payload["error"]["details"][key])

    def test_voice_catalog_is_a_local_stub(self):
        self.assert_stub(
            self.run_cli(["--json", "audio", "voice-list"]),
            "AI voice selection",
            "AI voice selection is available in the CutAgent desktop app.",
        )

    def test_voice_generation_is_a_local_stub_before_output_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "voice.mp3"
            self.assert_stub(
                self.run_cli(["--json", "audio", "voice-generate", "--voice-id", "voice1234", "--text", "Hello", "--output", str(output)]),
                "AI voice generation",
                "AI voice generation is available in the CutAgent desktop app.",
            )
            self.assertFalse(output.exists())

    def test_hosted_transcription_is_a_local_stub_before_render_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "transcript.json"
            self.assert_stub(
                self.run_cli(["--json", "transcript", "create", str(output)]),
                "AI transcription",
                "AI transcription is available in the CutAgent desktop app.",
            )
            self.assertFalse(output.exists())

    def test_video_generation_is_discoverable_and_a_local_stub(self):
        help_result = self.run_cli(["video", "generate", "--help"])
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--prompt", help_result.stdout)
        self.assertIn("--resolution", help_result.stdout)
        self.assertIn("--ratio", help_result.stdout)
        self.assertIn("--duration", help_result.stdout)
        self.assertIn("--seed", help_result.stdout)
        self.assert_stub(
            self.run_cli([
                "--json", "video", "generate", "--prompt", "A quiet editing suite",
                "--resolution", "1080P", "--ratio", "16:9", "--duration", "5", "--seed", "42",
            ]),
            "AI video generation",
            "AI video generation is available in the CutAgent desktop app.",
        )


if __name__ == "__main__":
    unittest.main()
