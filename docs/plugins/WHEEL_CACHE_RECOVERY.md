# Wheel extraction cache recovery

Wheel entry modules and adjacent `.whl` dependencies use the same validated extraction path. Existence of `__whl_extracted__/<package>` alone is not evidence that extraction completed.

The host extracts into a private sibling directory and checks all ZIP entries, including CRC, unsafe paths, duplicates, and file/directory or filesystem case aliases. Only a complete extraction is published. If extraction fails, a previous destination is retained unchanged; the failed wheel is not imported from that previous cache. Publication failure attempts to restore the previous directory and reports its retained path if restoration fails.

Wheel caches contain `.orca-wheel-cache.json` with a version, the source wheel SHA-256, and required file names/sizes. Every load verifies that record against the wheel and required files. Legacy unmarked caches, invalid records, missing/truncated files, and changed wheels are rebuilt. Complete caches are reused without rewriting their extracted files, which also avoids replacing already loaded native modules unnecessarily on Windows. Files added by Python, such as `__pycache__`, do not invalidate a cache. The record is a completion/recovery contract, not a signature or a promise to detect same-size local file tampering. Abandoned hidden staging/previous directories after an abrupt process exit are never treated as importable caches.

The extraction mutex serializes these filesystem operations within one process. It does not make all plugin business operations thread safe or provide a multi-process profile lock.

## Repeat the native regression

Build the explicit target `orca_plugin_wheel_cache_recovery_test` from an existing plugin-enabled build, then run:

```sh
python3 scripts/test_plugin_wheel_cache_recovery.py \
  --native /absolute/path/to/orca_plugin_wheel_cache_recovery_test \
  --output /absolute/path/to/new-wheel-cache-run-中文
python3 scripts/test_plugin_wheel_cache_recovery_contracts.py
```

The output directory must be new. It preserves deterministic original/corrupt/repaired/updated wheels, their manifest hashes, every native result and log, and a summary. No package is fetched and no GUI, account, device, or shared user profile is used. Ten recovery cases run in fresh processes/profiles: entry wheel and adjacent dependency wheel, each with a late CRC failure, unsafe entry, duplicate entry, file/directory conflict, or a damaged legacy unmarked cache. Each applicable case verifies repeated failure, actual Script callback values after repair, valid-cache reuse, damaged-record/file recovery, source-wheel replacement, preservation of an existing destination on extraction failure, and interpreter shutdown. A separate process reuses the completed entry profile to verify persistence and reuse.

The twelfth case probes the actual output filesystem's case sensitivity. On a case-insensitive volume, `resource.txt` and `RESOURCE.TXT` must be rejected as a collision; on a case-sensitive volume both distinct entries must be retained with their original bytes. The result records which branch actually ran. Python verifier contracts exercise both result shapes, without claiming a native run on an unavailable platform.

Acceptance requires wrapper exit 0, `results.json` with `ok: true`, and all twelve process records with `ok: true` and `returncode: 0`. The wrapper checks exact load phases, real callback strings, completion records, failure diagnostics, and interpreter shutdown; it does not accept a native executable's exit code alone. Windows/Linux source and commands are provided, while native platform acceptance requires running them there.
