# Build and test

Use a [release archive](https://github.com/0xpolarzero/lcu/releases) to install LCU. The source checkout contains the installer, instructions, and build scripts; it does not contain the runtime binaries.

## Build a release

Build on Linux with Python 3.12+, `dpkg-deb`, CA certificates, and network access. Use the target architecture or a matching Linux container:

```sh
python3 scripts/build_bundle.py --output dist
```

To reuse a downloaded official package:

```sh
python3 scripts/build_bundle.py --output dist --package /absolute/chatgpt_arm64.deb
```

The builder verifies the package checksum even when using a local file. It creates an architecture-specific `.tar.gz` and `.sha256` file in `dist/`. Existing output files are not overwritten.

The archive includes the desktop engine, Node, the MCP server, Linux JavaScript, instructions, agent-registration dependencies, and license notices. Downloads happen during this build. Installation verifies and copies the bundled files.

[runtime.lock.json](../runtime.lock.json) pins the official package and build tool. Agent-registration dependencies use their own [npm lockfile](../scripts/agent-tools/package-lock.json). Generated archives and binaries stay out of Git.

## Run tests

These commands require Docker:

```sh
./tests/run.sh linux/arm64
./tests/run.sh linux/amd64
```

A cached official package can be passed as the second argument:

```sh
./tests/run.sh linux/arm64 /absolute/chatgpt_arm64.deb
```

The script builds an archive, then installs and tests it in a fresh container with networking disabled. It checks installation, agent registration, and desktop actions against GTK and Xlib test applications. It does not use your desktop or agent accounts.

See [test results and limits](VERIFICATION.md) for the evidence behind the current release. The original binaries and Linux API come from the pinned upstream package; [runtime sources](PROVENANCE.md) explains what is included and how updates are checked.
