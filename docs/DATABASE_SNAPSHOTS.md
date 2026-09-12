# Verified whole-database snapshots

`emergent-rpg-backup` creates a directly usable SQLite snapshot of the complete engine database rather than exporting one logical session at a time.

```bash
emergent-rpg-backup backups/emergent-rpg.db --db emergent-rpg.db
```

An existing destination is refused by default. Replacement is explicit:

```bash
emergent-rpg-backup backups/emergent-rpg.db --db emergent-rpg.db --overwrite
```

## Publication contract

The source database is never opened through `SQLiteStore`; it is opened read-only by SQLite's online backup API. This matters because opening an exact pre-version legacy database through the ordinary store is allowed to adopt the current schema marker, while creating a snapshot must not mutate the source merely by reading it.

A snapshot follows this path:

```text
existing source SQLite, opened mode=ro
→ SQLite online backup into a same-directory temporary file
→ PRAGMA quick_check on the temporary copy
→ SQLiteStore schema compatibility gate on the copy
→ verify_session() for every persisted session
→ SHA-256 + byte-size report
→ os.replace(temp, destination)
```

The destination is not published until every check succeeds. Temporary files are removed after a failed verification or publication attempt. When `--overwrite` is used, an existing destination is replaced only after the candidate copy has already passed verification, so a corrupt logical source cannot clobber the previous backup.

The temporary file is created in the destination directory so final publication does not cross filesystems. The implementation deliberately does **not** claim fsync-backed power-loss durability or a complete crash-recovery protocol; `os.replace()` provides the publication step used here, but that is not presented as stronger storage durability evidence.

## Verification layers

A successful report requires all of the following:

- SQLite `PRAGMA quick_check` returns exactly `ok`.
- The copied database passes the current schema compatibility/version gate.
- Every session can be loaded through the ordinary persistence models.
- Every session's persisted current state equals event replay.
- Every current state passes canonical state validation.
- Every session can build a consistent portable session archive.

The emitted JSON report includes source/destination paths, schema version, verified session ids/count, `quick_check` result, SHA-256, file size, and `passed=true`.

The resulting file is already an ordinary engine database. No separate restore mutation path is introduced; point any existing `--db` surface at the snapshot file to inspect or use it.

## Safety boundaries

- Missing sources are rejected without creating a source or destination database.
- Source and destination may not resolve to the same path.
- Existing destinations require `--overwrite`.
- Failed verification does not publish a destination and does not overwrite an existing one.
- The source database is read through SQLite `mode=ro`; regression coverage also verifies source database bytes are unchanged by snapshot creation.
- Snapshotting does not modify canonical world state, events, turns, episodes, or gameplay scheduling.

## Verification evidence

The first fully green implementation candidate passed package/browser-asset verification, Ruff, strict mypy across **56 source files**, **233 pytest tests**, the seeded 1,000-accepted-turn consistency evaluation, and the autonomy integration evaluation.

For seed `20260911`, the long-run gate remained at 1,058 submissions / 1,000 accepted turns / 58 deterministic rejections / 2,274 events / final canonical clock minute 4,361, with replay equality and all tracked continuity invariants true and `failures=[]`.

The autonomy scenario also remained green for 20 rounds with 63 events, 27 persisted turns, every one of its 10 subsystem milestone checks true, and `failures=[]`. These results are correctness/integration evidence, not backup throughput or crash-durability benchmarks.
