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

The archive includes the unchanged complete `/usr/lib/chatgpt` application, including its original Owl shell, `app.asar`, `cua_node` tree, companion binaries and all plugins. Original declaration closures are also exposed for the standalone IAB host with a byte-span derivation ledger. No original file is rewritten or pruned. Every application file is checked against its architecture-specific inventory; instructions, agent-registration dependencies and notices are bundled too. Downloads happen during this build. Installation verifies and copies the bundled files.

[runtime.lock.json](../runtime.lock.json) pins the official package. Agent-registration dependencies use their own [npm lockfile](../scripts/agent-tools/package-lock.json). Generated archives and binaries stay out of Git.

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

The script builds an archive, then installs and tests it in a fresh container with networking disabled. It checks installation and agent registration, then runs the same desktop behavior oracles against separately extracted untouched upstream and LCU. The mandatory differential gate includes audio, a real XFCE session, alternate configurations, failure/recovery paths, the actual Codex model-input boundary through a local scripted model, native Codex lifecycle-hook delivery, and offline IAB provider, authentication-failure, streamed HTTP IPC, deep-link, settings, permissions, annotations, and effective-configuration fixtures. Browser tests run separately because discovery/authentication-boundary equivalence does not establish browser task completion. It does not use your desktop or agent accounts.

Browser fixture command (the build phase downloads pinned test-only Chromium and the official extension; execution is offline):

```sh
bash tests/browser-run.sh linux/arm64 /absolute/lcu-bundle.tar.gz /absolute/upstream/usr/lib/chatgpt/resources
```

Run `tests/iab_host.py RELEASE_ROOT` in an isolated Linux desktop for original IAB provider integration; its explicit sandbox flag is a root-container fixture setting, never a production launcher default. Authenticated browser-client actions need separate tests.

A passing native or host-delivery gate is not a full-parity sign-off. Browser auth, Electron host and remote provider dependencies must also be resolved and exercised. Do not publish a full-parity release while those entries remain blocked.

See [test results and limits](VERIFICATION.md) for the evidence behind the current release. The original binaries and Linux API come from the pinned upstream package; [runtime sources](PROVENANCE.md) explains what is included and how updates are checked.
