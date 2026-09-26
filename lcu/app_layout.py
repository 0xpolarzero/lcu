"""Locate the original Codex CLI files in a supported official app layout."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodexTools:
    cli: Path
    code_mode_host: Path


def _regular_file(root: Path, path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    current = root
    for component in path.relative_to(root).parts[:-1]:
        current = current / component
        if current.is_symlink() or not current.is_dir():
            return False
    return True


def locate_codex_tools(resources: Path, *, windows: bool = False) -> CodexTools:
    """Return a complete original CLI/host pair from one known resource layout."""
    resources = Path(resources)
    suffix = '.exe' if windows else ''
    relative_bases = (Path('.'), Path('codex-cli/bin'))
    matches = []
    for relative in relative_bases:
        cli = resources / relative / f'codex{suffix}'
        host = resources / relative / f'codex-code-mode-host{suffix}'
        if _regular_file(resources, cli) and _regular_file(resources, host):
            matches.append(CodexTools(cli, host))
    if len(matches) > 1:
        raise ValueError(f'Ambiguous original Codex CLI layout in application resources: {resources}')
    if not matches:
        raise ValueError(f'Application is missing a complete original Codex CLI layout: {resources}')
    return matches[0]
