"""Report whether the selected app and CUA runtime are a pair LCU's own tests covered.

App versions are date stamps and the CUA runtime is 0.0.x, so neither version
signals compatibility. `tested-versions.json` lists the exact pairs the checked-in
verification records prove. An untested pair produces a warning and nothing else:
LCU never refuses an app because its version is not listed.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

RECORD = 'tested-versions.json'
_FIELDS = ('platform', 'architecture', 'app_version', 'runtime', 'lcu_version')
_SHA256 = re.compile(r'[0-9a-f]{64}')


def load_entries(root):
    """Return (entries, problem). A missing or malformed record is a problem, not an error."""
    path = Path(root) / RECORD
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None, f'the tested-versions record is missing ({path})'
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f'the tested-versions record is unreadable ({path}: {exc})'
    entries = data.get('entries') if isinstance(data, dict) and data.get('format') == 1 else None
    if not isinstance(entries, list):
        return None, f'the tested-versions record has an unsupported format ({path})'
    for entry in entries:
        if (not isinstance(entry, dict) or any(not isinstance(entry.get(field), str) or not entry[field]
                                               for field in _FIELDS)
                or ('app_sha256' in entry and not (isinstance(entry['app_sha256'], str)
                                                  and _SHA256.fullmatch(entry['app_sha256'])))):
            return None, f'the tested-versions record has an invalid entry ({path})'
    return entries, None


def assess(root, *, platform, architecture, app_version, runtime):
    """Compare one observed app/runtime pair with the record.

    status is "tested" (exact pair listed), "untested" (record present, pair not
    listed) or "unknown" (no usable record). `tested` is true, false or null to
    match. Only an exact platform, architecture, app version and runtime match counts.
    """
    result = {'status': 'unknown', 'tested': None, 'platform': platform, 'architecture': architecture,
              'app_version': app_version, 'runtime': runtime, 'tested_with_lcu': None,
              'app_sha256': None, 'evidence': None, 'tested_pairs': [], 'warning': None}
    entries, problem = load_entries(root)
    if entries is None:
        result['warning'] = (f'LCU cannot tell whether ChatGPT {app_version} with CUA {runtime} is a tested pair: '
                             f'{problem}. LCU will still use it.')
        return result
    same_target = [entry for entry in entries
                   if entry['platform'] == platform and entry['architecture'] == architecture]
    result['tested_pairs'] = [{'app_version': entry['app_version'], 'runtime': entry['runtime'],
                               'lcu_version': entry['lcu_version']} for entry in same_target]
    match = next((entry for entry in same_target
                  if entry['app_version'] == app_version and entry['runtime'] == runtime), None)
    if match:
        result.update(status='tested', tested=True, tested_with_lcu=match['lcu_version'],
                      app_sha256=match.get('app_sha256'), evidence=match.get('evidence'))
        return result
    listed = '; '.join(f"ChatGPT {pair['app_version']} with CUA {pair['runtime']}" for pair in result['tested_pairs'])
    result.update(status='untested', tested=False)
    result['warning'] = (f'ChatGPT {app_version} with CUA {runtime} is not a pair LCU has tested on {platform} '
                         f'{architecture}. LCU will still use it, but behavior has not been verified. '
                         + (f'Tested: {listed}.' if listed else 'No pair is recorded for this platform and architecture.'))
    return result


def observe(root, descriptor=None, metadata=None):
    """Read the selected app's platform, architecture, version and runtime from a release.

    The version and runtime come from the installed app itself when it can be read, so an
    app updated in place after installation is judged by what is installed now.
    """
    root = Path(root)
    if descriptor is None:
        descriptor = json.loads((root / 'installation.json').read_text())
    if metadata is None:
        from .runtime import paths
        metadata = paths(root, descriptor)[3]
    return {'platform': descriptor.get('platform', 'linux'), 'architecture': descriptor.get('architecture'),
            'app_version': metadata['version'], 'runtime': metadata['runtime']}


def assess_release(root, descriptor=None, metadata=None):
    observed = observe(root, descriptor, metadata)
    return assess(root, **observed)


def status_lines(result):
    """Plain-text lines for setup, install and doctor output; the last is a warning when untested."""
    if result['status'] == 'tested':
        return [f"Tested pair: yes (ChatGPT {result['app_version']} with CUA {result['runtime']}; "
                f"tested with LCU {result['tested_with_lcu']})."]
    return [f"Tested pair: {'no' if result['status'] == 'untested' else 'unknown'}.",
            f"Warning: {result['warning']}"]


def report(root, *, descriptor=None, metadata=None, file=None):
    """Print the tested-pair status for a release; never raises and never blocks."""
    try:
        lines = status_lines(assess_release(root, descriptor, metadata))
    except (ValueError, KeyError, OSError, TypeError) as exc:
        lines = [f'Tested pair: unknown (the selected app could not be read: {exc}).']
    print('\n'.join(lines), file=file or sys.stdout)
