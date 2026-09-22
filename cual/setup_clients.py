"""Cual names mapped to upstream installers; configuration formats belong upstream."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Client:
    label: str
    executable: str
    detect_path: str
    skills_agent: str
    mcp_agent: str


CLIENTS = {
    'codex': Client('Codex', 'codex', '.codex', 'codex', 'codex'),
    'claude-code': Client('Claude Code', 'claude', '.claude.json', 'claude-code', 'claude-code'),
    'cursor': Client('Cursor', 'cursor', '.cursor', 'cursor', 'cursor'),
    'gemini-cli': Client('Gemini CLI', 'gemini', '.gemini', 'gemini-cli', 'gemini-cli'),
    'opencode': Client('OpenCode', 'opencode', '.config/opencode', 'opencode', 'opencode'),
    'vscode': Client('VS Code (default local Linux profile)', 'code', '.config/Code', 'github-copilot', 'vscode'),
    'copilot-cli': Client('GitHub Copilot CLI', 'copilot', '.copilot', 'github-copilot', 'github-copilot-cli'),
}

ALIASES = {'claude': 'claude-code', 'gemini': 'gemini-cli', 'copilot': 'copilot-cli'}
