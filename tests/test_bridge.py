import json
import unittest

from plugin import _PI_FLOW_REMINDER, _is_pi_flow_request
from plugin import tools as bridge_tools


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

    def test_reminder_uses_namespaced_plugin_skill(self):
        self.assertIn('skill_view("pi-bridge:pi-flow")', _PI_FLOW_REMINDER)
        self.assertNotIn('skill_view("pi-flow")', _PI_FLOW_REMINDER)


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
        parsed = bridge_tools._parse_json_stream(json.dumps(event))
        self.assertEqual(parsed["text"], "done")
        self.assertEqual(parsed["model"], "worker-model")
        self.assertEqual(parsed["provider"], "worker-provider")
        self.assertEqual(parsed["tool_names"], ["read"])
        self.assertEqual(parsed["num_turns"], 1)

    def test_error_event_is_reported(self):
        parsed = bridge_tools._parse_json_stream(
            json.dumps({"type": "error", "message": "boom"})
        )
        self.assertEqual(parsed["errors"], ["boom"])


class _FakePluginContext:
    plugin_id = "pi-bridge"

    def __init__(self, settings):
        self.settings = dict(settings)

    def get_config(self, key, default=None):
        return self.settings.get(key, default)


class EffortRoutingTests(unittest.TestCase):
    def setUp(self):
        self.previous_ctx = bridge_tools._ctx_ref

    def tearDown(self):
        bridge_tools.set_context_ref(self.previous_ctx)

    def test_fast_tier_reads_profile_plugin_settings(self):
        bridge_tools.set_context_ref(_FakePluginContext({
            "fast_provider": "cheap-provider",
            "fast_model": "cheap-model",
            "fast_thinking": "low",
        }))
        effective = bridge_tools._apply_effort_defaults({
            "prompt": "inventory files",
            "effort": "fast",
        })
        self.assertEqual(effective["provider"], "cheap-provider")
        self.assertEqual(effective["model"], "cheap-model")
        self.assertEqual(effective["thinking"], "low")

    def test_explicit_call_overrides_profile_tier(self):
        bridge_tools.set_context_ref(_FakePluginContext({
            "deep_provider": "profile-provider",
            "deep_model": "profile-model",
            "deep_thinking": "high",
        }))
        effective = bridge_tools._apply_effort_defaults({
            "prompt": "hard problem",
            "effort": "deep",
            "provider": "manual-provider",
            "model": "manual-model",
            "thinking": "xhigh",
        })
        self.assertEqual(effective["provider"], "manual-provider")
        self.assertEqual(effective["model"], "manual-model")
        self.assertEqual(effective["thinking"], "xhigh")

    def test_blank_mapping_falls_back_to_pi_default_but_sets_thinking(self):
        bridge_tools.set_context_ref(_FakePluginContext({}))
        effective = bridge_tools._apply_effort_defaults({
            "prompt": "normal task",
            "effort": "standard",
        })
        self.assertNotIn("provider", effective)
        self.assertNotIn("model", effective)
        self.assertEqual(effective["thinking"], "medium")

    def test_invalid_configured_thinking_uses_safe_tier_default(self):
        bridge_tools.set_context_ref(_FakePluginContext({
            "fast_thinking": "unlimited",
        }))
        effective = bridge_tools._apply_effort_defaults({
            "prompt": "mechanical task",
            "effort": "fast",
        })
        self.assertEqual(effective["thinking"], "minimal")


if __name__ == "__main__":
    unittest.main()
