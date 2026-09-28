"""LCU names mapped to upstream installers; configuration formats belong upstream."""
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
    'pi': Client('Pi', 'pi', '.pi/agent', 'pi', 'pi'),
    'omp': Client('Oh My Pi', 'omp', '.omp', '', ''),
    'hermes': Client('Hermes', 'hermes', '.hermes', '', ''),
}

ALIASES = {'claude': 'claude-code', 'oh-my-pi': 'omp', 'hermes-agent': 'hermes'}
