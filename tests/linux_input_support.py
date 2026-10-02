"""Shared helpers for the Linux window-targeted input tests: fixtures, window lookup and file oracles."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from mcp_client import Client, text

output = Path(os.environ['LCU_TEST_OUTPUT'])
here = Path(__file__).resolve().parent
fixtures = []


def settle(predicate, attempts=40, delay=0.1):
    for _ in range(attempts):
        if predicate():
            return True
        time.sleep(delay)
    return False


def read(name):
    path = output / name
    return path.read_text() if path.exists() else None


def start_fixture(script, *arguments, **environment):
    process = subprocess.Popen([sys.executable, str(here / script), *arguments],
                               env={**os.environ, **environment}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fixtures.append(process)
    return process


def stop_fixtures():
    for process in fixtures:
        process.terminate()
    for process in fixtures:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    fixtures.clear()


class Session:
    """One stdio MCP client to the installed lcu with the sky service imported for direct calls."""

    def __init__(self, command, env=None):
        self.client = Client(command, env=env)
        self.run('await cua.getState();')
        self.run('globalThis.sky = (await import("@oai/sky")).sky;'
                 'globalThis.byTitle = async title => (await sky.list_windows()).find(w => w.title === title);')

    def run(self, code, error=False):
        return text(self.client.js(code, error=error))

    def windows(self):
        # The engine can fail a listing that races with a window closing (X BadWindow); retry once settled.
        for attempt in range(10):
            result = self.client.call('tools/call', {'name': 'js', 'arguments': {
                'code': 'nodeRepl.write(JSON.stringify(await sky.list_windows()));'}})
            if not result.get('isError'):
                return json.loads(text(result))
            time.sleep(0.2)
        raise AssertionError(text(result))

    def window(self, title, attempts=60):
        for _ in range(attempts):
            found = next((w for w in self.windows() if w.get('title') == title), None)
            if found:
                return found
            time.sleep(0.2)
        raise AssertionError(f'window not found: {title}: {self.windows()}')

    def focused_id(self):
        focused = [w['id'] for w in self.windows() if w.get('focused')]
        return focused[0] if focused else None

    def activate(self, title):
        self.run(f'await sky.activate_window({{window: await byTitle({json.dumps(title)})}});')
        window = self.window(title)
        assert settle(lambda: self.focused_id() == window['id']), (title, self.windows())
        return window

    def close(self):
        self.client.close()
