"""Launch the untouched official REPL with source-backed Linux host inputs.

The fixed desktop defaults below come from pinned kie/nne/Lre, not LCU.
Linux-native enablement and non-desktop modes intentionally exercise the shipped
runtime beyond the pinned app's product gate. Explicit caller overrides describe
alternate runtime configurations, not a claim that the original app selected them.
"""
import os
from pathlib import Path


def environment(root, caller):
    env = dict(caller)
    codex_home = env.get('CODEX_HOME', str(Path(env.get('HOME', str(Path.home()))) / '.codex'))
    # Original nne trusts selected CODEX_HOME and selected module directories.
    # This fixture deliberately does not reuse LCU's narrower trust policy.
    env.update(
        PATH=str(root / 'bin') + ':' + env.get('PATH', '/usr/bin:/bin'),
        CUA_REPL_NODE_REPL_PATH=str(root / 'bin/node_repl'),
        NODE_REPL_NODE_PATH=str(root / 'bin/node'),
        NODE_REPL_NODE_MODULE_DIRS=str(root / 'lib/node_modules'),
        NODE_REPL_TRUSTED_CODE_PATHS=os.pathsep.join((codex_home, str(root / 'lib/node_modules'))),
        CODEX_HOME=codex_home,
    )
    env.setdefault('CUA_REPL_ENABLED_SURFACES', 'browser,computer')
    env.setdefault('CUA_REPL_BROWSER_ENV', 'codex-app')
    env.setdefault('NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS', '1000')
    if env['CUA_REPL_BROWSER_ENV'] == 'codex-app':
        env.setdefault('BROWSER_USE_TINYSKY_ENABLED', '1')
        flavor = env.get('BUILD_FLAVOR', '').strip()
        if flavor not in ('dev', 'agent', 'nightly', 'internal-alpha', 'public-beta', 'prod'):
            flavor = 'prod'
        env.setdefault('BROWSER_USE_CODEX_APP_BUILD_FLAVOR', flavor)
        env.setdefault('BROWSER_USE_CODEX_APP_VERSION', '26.915.31945')
        backends = env.get('BROWSER_USE_AVAILABLE_BACKENDS', 'chrome,iab').split(',')
        if 'iab' in backends:
            env.setdefault('NODE_REPL_INSTRUCTIONS_USE_CASE_BROWSER',
                'Control the in-app browser in conjunction with the Browser Plugin.')
        if 'chrome' in backends:
            env.setdefault('NODE_REPL_INSTRUCTIONS_USE_CASE_CHROME',
                'Control the Chrome browser in conjunction with the Chrome Plugin. Prefer this method of controlling Chrome over alternatives (such as Computer Use) unless the user explicitly mentions an alternative.')
    # Offline fixture choice, explicitly different from original prod assembly.
    env.setdefault('NODE_REPL_DISABLE_ANALYTICS', '1')
    if (root.parent / 'codex').is_file():
        env.setdefault('CODEX_CLI_PATH', str(root.parent / 'codex'))
    return env


def main():
    root = Path(os.environ['DIFFERENTIAL_UPSTREAM_RUNTIME'])
    env = environment(root, os.environ)
    os.execve(root / 'bin/node', [str(root / 'bin/node'),
              str(root / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')], env)


if __name__ == '__main__':
    main()
