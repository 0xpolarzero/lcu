"""Attach to one existing XFCE session owned by the calling account."""
import argparse
import os
from pathlib import Path
import pwd

GUI_KEYS = ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE')


def discover(proc=Path('/proc'), uid=None):
    uid = os.getuid() if uid is None else uid
    sessions = set()
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != uid or (process / 'comm').read_text().strip() != 'xfce4-session':
                continue
            values = dict(item.split('=', 1) for item in (process / 'environ').read_bytes().decode().split('\0') if '=' in item)
            if values.get('DISPLAY') and values.get('DBUS_SESSION_BUS_ADDRESS'):
                sessions.add(tuple((key, values[key]) for key in GUI_KEYS if key in values))
        except (FileNotFoundError, ProcessLookupError, PermissionError, UnicodeError):
            continue
    if len(sessions) != 1:
        raise ValueError(f'Expected one XFCE desktop for UID {uid}; found {len(sessions)}. Start a desktop, or use --session direct with an explicit GUI environment.')
    return dict(sessions.pop())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if pwd.getpwnam(args.user).pw_uid != os.getuid():
        raise ValueError('Run the launcher as the selected desktop account.')
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Provide a command after --')
    env = dict(os.environ)
    for key in GUI_KEYS:
        env.pop(key, None)
    env.update(discover())
    os.execvpe(command[0], command, env)
