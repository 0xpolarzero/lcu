"""Run the same synthetic MCP result cases through the installed Codex CLI.

The MCP server uses the official SDK. The model endpoint is a scripted provider
bound to loopback; no account key, real model, desktop, or browser is involved.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "adapters/test/result-fixture.mjs"
CASES = ("text", "image", "audio", "error")


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def response_item(item, index):
    response = {
        "id": f"fixture-response-{index}",
        "object": "response",
        "model": "fixture",
        "status": "completed",
        "output": [item],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    events = [
        {"type": "response.created", "response": {**response, "status": "in_progress", "output": []}},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": response},
    ]
    return "".join("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n" for event in events).encode()


def assert_delivery(case, records, requests, tool_result, codex_events):
    calls = [item for item in records if item.get("kind") == "call" and item.get("name") == "js"]
    originals = [item["result"] for item in records if item.get("kind") == "result"]
    payload = next((item for item in records if item.get("kind") == "payload"), None)
    if len(calls) != 1 or calls[0].get("args", {}).get("code") != f"lcu-result:{case}":
        raise AssertionError(f"Codex did not make exactly one original js call for {case}")
    if len(originals) != 1:
        raise AssertionError(f"Codex fixture returned {len(originals)} original results for {case}")
    original = originals[0]
    if tool_result.get("call_id") != f"fixture-{case}" or tool_result.get("type") != "function_call_output":
        raise AssertionError(f"Codex provider result was correlated to the wrong call for {case}")
    output = tool_result.get("output")
    output_blocks = output if isinstance(output, list) else [{"type": "input_text", "text": str(output)}]
    texts = [block.get("text", "") for block in output_blocks if isinstance(block, dict)]

    events = [json.loads(line) for line in codex_events.splitlines() if line.strip()]
    tool_calls = [event["item"] for event in events if event.get("type") == "item.completed" and
                  isinstance(event.get("item"), dict) and event["item"].get("type") == "mcp_tool_call" and
                  event["item"].get("tool") == "js"]
    if len(tool_calls) != 1:
        raise AssertionError(f"Codex emitted {len(tool_calls)} original js tool events for {case}")
    host_status = tool_calls[0].get("status")
    summary = {"host": "Codex CLI", "case": case, "original_types": [
        block.get("type") for block in original.get("content", [])],
        "original_isError": bool(original.get("isError", False)), "provider_result_types": [
            block.get("type") for block in output_blocks if isinstance(block, dict)],
        "host_tool_status": host_status, "provider_error_flag": any(
            key in tool_result for key in ("is_error", "isError", "error"))}

    if case == "text":
        expected = original["content"][0]["text"]
        if expected not in texts or original.get("isError", False) or host_status != "completed":
            raise AssertionError("Codex did not preserve the original text result")
    elif case == "image":
        expected = original["content"][0]
        if not payload or expected.get("type") != "image":
            raise AssertionError("image fixture did not produce an original image result")
        images = [block for block in output_blocks if isinstance(block, dict) and block.get("type") == "input_image"]
        if len(images) != 1:
            raise AssertionError("Codex did not forward exactly one image to the provider")
        image_url = images[0].get("image_url", "")
        prefix = f"data:{expected['mimeType']};base64,"
        if not image_url.startswith(prefix):
            raise AssertionError("Codex changed the original image MIME type")
        provider_bytes = base64.b64decode(image_url[len(prefix):])
        expected_bytes = base64.b64decode(expected["data"])
        if provider_bytes != expected_bytes or host_status != "completed":
            raise AssertionError("Codex changed the original image bytes")
        summary["original_sha256"] = payload["sha256"]
        summary["provider_sha256"] = hashlib.sha256(provider_bytes).hexdigest()
    elif case == "audio":
        expected = original["content"][0]
        marker = "<audio content omitted because you do not support audio input>"
        if not payload or expected.get("type") != "audio" or marker not in texts or \
                expected["data"] in json.dumps(tool_result) or host_status != "completed":
            raise AssertionError("Codex audio fixture did not produce the observed omission marker")
        summary["original_sha256"] = payload["sha256"]
        summary["provider_received_audio_bytes"] = False
        summary["omission_marker"] = marker
    else:
        expected = original["content"][0]["text"]
        if not original.get("isError") or host_status != "failed" or expected not in texts:
            raise AssertionError("Codex did not preserve the MCP error text and host failure status")
        if summary["provider_error_flag"]:
            raise AssertionError("Codex unexpectedly encoded an explicit error flag in function_call_output")

    return summary


def run_case(cli: Path, node: str, output: Path, case: str, version: str):
    work = output / case
    home, codex_home, project = work / "home", work / "home/.codex", work / "project"
    home.mkdir(parents=True)
    codex_home.mkdir()
    project.mkdir()
    result_log = work / "mcp-result.jsonl"
    provider_path = work / "provider-requests.json"
    host_path = work / "codex-events.jsonl"
    requests, failures = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                provider_path.write_text(json.dumps(requests, indent=2), encoding="utf-8")
                index = len(requests)
                if index == 1:
                    server = next(tool for tool in body.get("tools", []) if tool.get("name") == "mcp__lcu")
                    if not any(tool.get("name") == "js" for tool in server.get("tools", [])):
                        raise AssertionError(f"Codex model request omitted original js: {server}")
                    item = {"id": f"fixture-call-{case}", "type": "function_call", "call_id": f"fixture-{case}",
                            "name": "js", "namespace": "mcp__lcu",
                            "arguments": json.dumps({"code": f"lcu-result:{case}"})}
                else:
                    item = {"id": f"fixture-message-{case}", "type": "message", "status": "completed",
                            "role": "assistant", "content": [{"type": "output_text", "text": "Fixture complete.", "annotations": []}]}
                payload = response_item(item, index)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as error:
                failures.append(repr(error))
                self.send_error(500, "Local Codex result fixture failed")

        def log_message(self, *_args):
            pass

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    config = [
        'approval_policy = "on-request"',
        'sandbox_mode = "read-only"',
        'model_provider = "fixture"',
        'model = "fixture"',
        "",
        f"[projects.{quote(project)}]",
        'trust_level = "trusted"',
        "",
        "[mcp_servers.lcu]",
        "required = true",
        f"command = {quote(node)}",
        f"args = [{quote(FIXTURE)}]",
        'enabled_tools = ["js", "js_reset"]',
        "startup_timeout_sec = 10",
        "",
        "[mcp_servers.lcu.tools.js]",
        'approval_mode = "approve"',
        "output_token_limit = 1000",
        "",
        "[mcp_servers.lcu.env]",
        f"LCU_RESULT_LOG = {quote(result_log)}",
        "",
        "[model_providers.fixture]",
        'name = "Local result fixture"',
        f'base_url = "http://127.0.0.1:{provider.server_port}/v1"',
        'wire_api = "responses"',
        "requires_openai_auth = false",
        "",
    ]
    (codex_home / "config.toml").write_text("\n".join(config), encoding="utf-8")
    env = {
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "CODEX_CLI_PATH": str(cli),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": str(work),
        "TERM": "xterm-256color",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
    }
    command = [str(cli), "--strict-config", "-a", "on-request", "-c", 'model_provider="fixture"',
               "-c", 'model="fixture"', "exec", "--ephemeral", "--skip-git-repo-check", "--json",
               "-C", str(project), f"Call original LCU js once with code lcu-result:{case}, then finish."]
    try:
        result = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, timeout=90)
        host_path.write_text(result.stdout, encoding="utf-8")
        (work / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            raise AssertionError(f"Codex {case} exited {result.returncode}: {result.stderr[-2000:]}")
        if failures:
            raise AssertionError("Provider failure: " + "; ".join(failures))
        if len(requests) != 2:
            raise AssertionError(f"Expected a tool request and result request, received {len(requests)}")
        records = [json.loads(line) for line in result_log.read_text(encoding="utf-8").splitlines()]
        tool_result = next(item for item in requests[1].get("input", [])
                            if item.get("type") == "function_call_output" and item.get("call_id") == f"fixture-{case}")
        delivery = assert_delivery(case, records, requests, tool_result, result.stdout)
        return {"case": case, "work": str(work), "requests": requests, "records": records,
                "tool_result": tool_result, "codex_events": result.stdout, "delivery": delivery,
                "version": version}
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True, help="exact installed Codex CLI executable")
    parser.add_argument("--node", default=shutil.which("node"), help="Node.js executable used by the official SDK fixture")
    parser.add_argument("--output", type=Path, default=None, help="private evidence directory")
    parser.add_argument("--version", required=True, help="exact Codex CLI version reported by this pinned app/package")
    args = parser.parse_args()
    cli = args.cli.expanduser().resolve(strict=True)
    node = str(Path(args.node).expanduser().resolve(strict=True)) if args.node else None
    if not node:
        parser.error("node must be on PATH or supplied with --node")
    output = args.output or Path(tempfile.mkdtemp(prefix="lcu-result-codex-"))
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    for case in CASES:
        result = run_case(cli, node, output, case, args.version)
        summary.append(result)
        print(json.dumps({**result["delivery"], "version": args.version,
                          "evidence": str(output / case), "requests": 2}, sort_keys=True), flush=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
