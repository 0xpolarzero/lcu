import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "adapters" / "hermes"
SOURCE_ADAPTERS = ROOT / "adapters"
INSTALLED_ADAPTERS = Path("/opt/lcu/current/adapters")


class FakeContext:
    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.unload_callbacks = []

    def register_tool(self, *, name, toolset, schema, handler):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}
        return object()

    def register_skill(self, name, path):
        self.skill = (name, path)
        return object()

    def on_unload(self, callback):
        self.unload_callbacks.append(callback)
        return object()

    def unload(self):
        for callback in reversed(self.unload_callbacks):
            callback()

    def register_hook(self, event, handler):
        self.hooks[event] = handler


class HermesHarnessTests(unittest.TestCase):
    def make_adapter_tree(self, home):
        """Run fixtures beside the built release dependencies; source checkouts omit node_modules."""
        installed = INSTALLED_ADAPTERS if (INSTALLED_ADAPTERS / "node_modules/@modelcontextprotocol/sdk/package.json").is_file() else SOURCE_ADAPTERS
        adapter_root = home / "adapter" / "adapters"
        (adapter_root / "hermes").mkdir(parents=True)
        (adapter_root / "test").mkdir()
        for name in ("client.mjs", "audio-files.mjs"):
            shutil.copy2(installed / name, adapter_root / name)
        for name in ("bridge.mjs",):
            shutil.copy2(installed / "hermes" / name, adapter_root / "hermes" / name)
        shutil.copy2(SOURCE_ADAPTERS / "test" / "hermes-mcp-fixture.mjs",
                     adapter_root / "test" / "hermes-mcp-fixture.mjs")
        (adapter_root / "node_modules").symlink_to(installed / "node_modules", target_is_directory=True)
        if INSTALLED_ADAPTERS.exists():
            node = Path("/opt/lcu/current/agent-tools/node/bin/node")
        else:
            node = Path(shutil.which("node") or "")
        node = node.resolve()
        self.assertTrue(node.is_file(), f"selected Hermes test Node is missing: {node}")
        return adapter_root, node

    def test_plugin_relays_real_turn_identity_results_instructions_and_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="lcu-hermes-test-") as temporary:
            home = Path(temporary)
            plugin_dir = home / "plugins" / "lcu-cua"
            plugin_dir.mkdir(parents=True)
            shutil.copy2(PLUGIN / "__init__.py", plugin_dir / "__init__.py")
            (plugin_dir / "skills" / "lcu").mkdir(parents=True)
            (plugin_dir / "skills" / "lcu" / "SKILL.md").write_text("Fixture LCU skill content.\n", encoding="utf-8")
            log = home / "fixture.jsonl"
            adapter_root, node = self.make_adapter_tree(home)
            config = {
                "command": [str(node), str(adapter_root / "test/hermes-mcp-fixture.mjs")],
                "node": str(node),
                "bridge": str(adapter_root / "hermes/bridge.mjs"),
            }
            (plugin_dir / "lcu-config.json").write_text(json.dumps(config), encoding="utf-8")
            spec = importlib.util.spec_from_file_location("lcu_hermes_test_plugin", plugin_dir / "__init__.py")
            plugin = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(plugin)
            context = FakeContext()
            previous_log = os.environ.get("LCU_FIXTURE_LOG")
            os.environ["LCU_FIXTURE_LOG"] = str(log)
            try:
                plugin.register(context)
                self.assertEqual(set(context.tools), {"js", "js_reset"})
                self.assertEqual(context.tools["js"]["schema"]["description"], "Original JS description.")
                injected = context.hooks["pre_llm_call"](
                    session_id="hermes-session", turn_id="hermes-turn")
                self.assertIn("Fixture LCU skill content.", injected)
                self.assertIn(str(plugin_dir / "skills/lcu/SKILL.md"), injected)
                self.assertIn("Original CUA initialization guide.", injected)
                self.assertIn('"name": "js"', injected)

                raw = context.tools["js"]["handler"](
                    {"code": "context"}, session_id="hermes-session", turn_id="hermes-turn",
                    tool_call_id="hermes-call")
                result = json.loads(raw)
                self.assertEqual(result["content"], [{"type": "text", "text": "context"}])

                approvals = []
                approval_module = types.ModuleType("tools.approval_prompt")
                approval_module.request_elicitation_consent = lambda message, description, **kwargs: (
                    approvals.append((message, description, kwargs)) or "accept")
                tools_module = types.ModuleType("tools")
                tools_module.__path__ = []
                with patch.dict(sys.modules, {
                    "tools": tools_module, "tools.approval_prompt": approval_module,
                }):
                    approval_raw = context.tools["js"]["handler"](
                        {"code": "approval-native"}, session_id="hermes-session", turn_id="hermes-turn",
                        tool_call_id="approval-call")
                approval_result = json.loads(approval_raw)
                self.assertEqual(json.loads(approval_result["content"][0]["text"])["action"], "accept")
                self.assertIn("Allow once", approvals[0][1])
                self.assertEqual(approvals[0][2]["surface"], "mcp-elicitation/lcu")

                form_raw = context.tools["js"]["handler"](
                    {"code": "approval-form"}, session_id="hermes-session", turn_id="hermes-turn",
                    tool_call_id="form-call")
                self.assertEqual(json.loads(json.loads(form_raw)["content"][0]["text"])["action"], "cancel")

                image_result = context.tools["js"]["handler"](
                    {"code": "image"}, session_id="hermes-session", turn_id="hermes-turn",
                    tool_call_id="image-call")
                self.assertEqual(image_result["content"][1]["image_url"]["url"],
                                 "data:image/png;base64,AAECAw==")
                self.assertNotIn("AAECAw==", image_result["text_summary"])
                audio_raw = context.tools["js"]["handler"](
                    {"code": "audio"}, session_id="hermes-session", turn_id="hermes-turn",
                    tool_call_id="audio-call")
                audio_text = json.loads(audio_raw)["content"][0]["text"]
                self.assertIn("Audio result (original MIME type: audio/wav) saved to ", audio_text)
                audio_path = Path(audio_text.rsplit(" ", 1)[-1])
                try:
                    self.assertEqual(audio_path.read_bytes(), b"\0\0\0")
                finally:
                    audio_dir = audio_path.parent
                    audio_path.unlink(missing_ok=True)
                    audio_dir.rmdir()
                blocked = context.hooks["pre_llm_call"](
                    session_id="concurrent-session", turn_id="other-turn")
                self.assertIn("another Hermes session still owns", blocked)

                context.hooks["on_session_end"](session_id="hermes-session", completed=True, interrupted=False)
                context.hooks["pre_llm_call"](session_id="cleanup-once", turn_id="cleanup-turn")
                context.hooks["on_session_end"](session_id="cleanup-once", turn_id="cleanup-turn",
                                                 completed=True, interrupted=False)
                context.hooks["pre_llm_call"](session_id="next-session", turn_id="next-turn")
                entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
                call = next(item for item in entries if item.get("name") == "js")
                metadata = call["meta"]["x-codex-turn-metadata"]
                self.assertEqual(metadata["session_id"], "hermes-session")
                self.assertEqual(metadata["turn_id"], "hermes-turn")
                self.assertEqual(metadata["call_id"], "hermes-call")
                cleanup = next(item for item in entries if item.get("name") == "turn_ended")
                self.assertEqual(cleanup["args"]["hook_event_name"], "Stop")
                self.assertEqual(cleanup["args"]["turn_id"], "hermes-turn")
                retries = [item for item in entries if item.get("name") == "turn_ended" and
                           item["args"].get("session_id") == "cleanup-once"]
                self.assertEqual([item["args"]["hook_event_name"] for item in retries], ["Stop", "Stop"])
                self.assertEqual(retries[0]["args"]["turn_id"], "cleanup-turn")
                self.assertEqual(context.skill[0], "lcu")
            finally:
                if "context" in locals():
                    context.unload()
                if previous_log is None:
                    os.environ.pop("LCU_FIXTURE_LOG", None)
                else:
                    os.environ["LCU_FIXTURE_LOG"] = previous_log

    def test_missing_exact_turn_identity_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="lcu-hermes-test-") as temporary:
            home = Path(temporary)
            plugin_dir = home / "plugins" / "lcu-cua"
            plugin_dir.mkdir(parents=True)
            shutil.copy2(PLUGIN / "__init__.py", plugin_dir / "__init__.py")
            (plugin_dir / "skills" / "lcu").mkdir(parents=True)
            (plugin_dir / "skills" / "lcu" / "SKILL.md").write_text("Fixture skill.\n", encoding="utf-8")
            adapter_root, node = self.make_adapter_tree(home)
            (plugin_dir / "lcu-config.json").write_text(json.dumps({
                "command": [str(node), str(adapter_root / "test/hermes-mcp-fixture.mjs")], "node": str(node),
                "bridge": str(adapter_root / "hermes/bridge.mjs"),
            }), encoding="utf-8")
            spec = importlib.util.spec_from_file_location("lcu_hermes_missing_context", plugin_dir / "__init__.py")
            plugin = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(plugin)
            context = FakeContext()
            try:
                plugin.register(context)
                injected = context.hooks["pre_llm_call"]()
                self.assertIn("did not provide exact session and turn IDs", injected)
                raw = context.tools["js"]["handler"]({"code": "must-not-run"})
                self.assertTrue(json.loads(raw)["isError"])
            finally:
                context.unload()


if __name__ == "__main__":
    unittest.main()
