# Side-by-side cutover runbook

This runbook intentionally makes no changes by itself.

1. Confirm the legacy service is healthy and record its immutable chain head and counts.
2. Freeze legacy writes for the shortest practical interval.
3. Create an encrypted export and verify it before leaving the legacy host boundary.
4. Initialize a brand-new LAMF 3 directory; never reuse or overwrite a v2 database.
5. Import, run deep verification, and compare counts and representative scoped searches.
6. Register only one canary client against LAMF 3 and exercise orientation, search, remember, correction, and cross-session recall.
7. Move remaining clients individually, preserving their prior registration as the rollback value.
8. Observe errors, latency, queue depth, authentication blocks, and integrity checks through the acceptance window.
9. Roll back by restoring client registrations to the untouched legacy instance. Do not reverse-copy the v3 database.

The promotion script must retain a timestamped source backup and the migration's
verified pre-v3 database backup. If post-update verification fails, restore the
source overlay backup and database backup before allowing clients to reconnect.
