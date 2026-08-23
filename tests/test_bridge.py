import json
import unittest

from plugin import _is_pi_flow_request
from plugin.tools import _parse_json_stream


class PiFlowTriggerTests(unittest.TestCase):
    def test_explicit_spellings_trigger(self):
        for message in (
            "通过 pi_flow 去检查这个项目",
            "use pi-flow to fix the tests",
            "pi flow review this repository",
            "piflow do the task",
        ):
            with self.subTest(message=message):
                self.assertTrue(_is_pi_flow_request(message))

    def test_unrelated_coding_request_does_not_trigger(self):
        self.assertFalse(_is_pi_flow_request("fix the failing tests"))
        self.assertFalse(_is_pi_flow_request("run pi_task on this file"))


class OneShotParserTests(unittest.TestCase):
    def test_turn_end_extracts_text_and_metadata(self):
        event = {
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "model": "worker-model",
                "provider": "worker-provider",
                "content": [{"type": "text", "text": "done"}],
            },
            "toolResults": [{"toolName": "read", "result": "ok"}],
        }
        parsed = _parse_json_stream(json.dumps(event))
        self.assertEqual(parsed["text"], "done")
        self.assertEqual(parsed["model"], "worker-model")
        self.assertEqual(parsed["provider"], "worker-provider")
        self.assertEqual(parsed["tool_names"], ["read"])
        self.assertEqual(parsed["num_turns"], 1)

    def test_error_event_is_reported(self):
        parsed = _parse_json_stream(json.dumps({"type": "error", "message": "boom"}))
        self.assertEqual(parsed["errors"], ["boom"])


if __name__ == "__main__":
    unittest.main()
