# Installed application inventory

LCU's source and thin archives carry the [pin and selected component hashes](../runtime.lock.json), not a copy of the official application. Installation verifies the exact architecture-specific official `.deb` SHA-256 before extraction. The package supplies the complete application, including its original CUA runtime, CLI, Chrome plugin, instructions, notices and optional code that LCU does not expose.

## Local verification

[The installer](../scripts/installed_app.py) checks package identity, runtime manifest, required executables, links, modes and component hashes. It derives an inventory of every file, directory and symlink from the verified package. A supplied existing app must match that inventory before selection. The managed generation stores its inventory locally and is checked on reuse; it is shared by agents and retained across LCU upgrades. The inventory is not redistributed.

[Instruction setup](../lcu/setup.py) copies the applicable original Linux and Chrome guides byte for byte from the selected app into the target account's local skill directory before agent registration. The source wrapper in [SKILL.md](../skills/lcu/SKILL.md) has no checked-in reference tree. [Installation tests](../tests/test_installation.py), [instruction tests](../tests/test_instructions.py) and the [source-distribution test](../tests/test_distribution.py) cover the corresponding boundaries.

## Historical source audit

The earlier full-copy candidate catalogued the entire pinned package, including inactive platforms and embedded-browser UI. That design is retired. Its large architecture inventories were removed from the active source because the current installer authenticates the package and derives the complete local tree at install time. The compact [host source index](../scripts/host-source-inventory.json) retains source coordinates and hashes for the host-environment and authentication analysis; [historical instruction hashes](../scripts/instructions.lock.json) remain provenance only. Neither record is loaded by the current installer or included in the thin release.

The fixed official package is version 26.915.31945 with CUA 0.0.16/20260915001755-492f19756c31. ARM64 and amd64 package hashes are in `runtime.lock.json`. A SHA-256 pin proves that the acquired bytes match the reviewed package; it does not verify an independent publisher signature.
