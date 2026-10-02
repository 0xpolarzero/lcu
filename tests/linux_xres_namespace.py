"""LCU's X helper against a real X server: process identity is trusted only from a server in LCU's PID namespace.

SO_PEERCRED process ids, which the X server reports through X-Resource, are relative to the server's PID
namespace. The helper (lcu/linux_sky_service.mjs, XRES_HELPER_SCRIPT) therefore first asks the server for its
own client's id over the same connection and requires it to equal getpid(). This test runs the helper from
this namespace (it must report the process owning a window) and from a child PID namespace against the same
server (it must report nothing). The second part needs `unshare` privileges and is skipped with a notice
where the environment does not allow a PID namespace. The helper's `at` question must work in both, so a
failed identity query cannot come from an unreachable X server.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parent.parent
script = subprocess.run(
    ['node', '--input-type=module', '-e',
     f'import {{XRES_HELPER_SCRIPT}} from {json.dumps((repo / "lcu/linux_sky_service.mjs").as_uri())};'
     'process.stdout.write(XRES_HELPER_SCRIPT);'],
    capture_output=True, text=True, check=True).stdout
path = Path(tempfile.mkdtemp()) / 'helper.py'
path.write_text(script)


def helper(*arguments, prefix=()):
    result = subprocess.run([*prefix, sys.executable, str(path), *arguments], capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


# A window of this very process: the server must attribute it to os.getpid().
import ctypes as c
x11 = c.CDLL('libX11.so.6')
x11.XOpenDisplay.restype = c.c_void_p
x11.XOpenDisplay.argtypes = [c.c_char_p]
x11.XDefaultRootWindow.restype = c.c_ulong
x11.XDefaultRootWindow.argtypes = [c.c_void_p]
x11.XCreateSimpleWindow.restype = c.c_ulong
x11.XCreateSimpleWindow.argtypes = [c.c_void_p, c.c_ulong, c.c_int, c.c_int, c.c_uint, c.c_uint, c.c_uint, c.c_ulong, c.c_ulong]
x11.XFlush.argtypes = [c.c_void_p]
display = x11.XOpenDisplay(None)
assert display, 'no X display'
window_id = str(x11.XCreateSimpleWindow(display, x11.XDefaultRootWindow(display), 0, 0, 20, 20, 0, 0, 0))
x11.XFlush(display)
expected = str(os.getpid())
assert helper('pid', window_id) == expected, ('same namespace', helper('pid', window_id), expected)
assert helper('at', window_id, '0', '0') in ('0', '1')

def child(*prefix):
    inside = subprocess.run([*prefix, 'sh', '-c', 'echo $$'], capture_output=True, text=True)
    if inside.returncode != 0 or inside.stdout.strip() != '1':
        return None
    return {'identity': helper('pid', window_id, prefix=prefix), 'at': helper('at', window_id, '0', '0', prefix=prefix)}

result = None
for prefix in (('unshare', '--pid', '--fork', '--mount-proc'),
               ('unshare', '--user', '--map-root-user', '--pid', '--fork', '--mount-proc')):
    result = child(*prefix)
    if result is not None:
        break
if result is None:
    print('INFO: no PID namespace available here; the cross-namespace refusal was not exercised', flush=True)
else:
    assert result['at'] in ('0', '1'), ('the X server was not reachable from the child namespace', result)
    assert result['identity'] == '', ('a server in another PID namespace was trusted', result)
    print('PASS: X helper trusts the X server in this namespace and fails closed from a child PID namespace', flush=True)
