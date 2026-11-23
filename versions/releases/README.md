# Release signing — approved-version ledger

Production distribution gates for TIHULU Flight Radar. Full procedure, custody
rules and the signing ceremony: [docs/security/SIGNING.md](../../../docs/security/SIGNING.md).

- `root-public.pem` — the release signing root's PUBLIC key (committed here).
  The matching private key lives only on the owner's machine
  (`~/.tihulu-signing/root-private.pem`, mode 0600) and is never committed,
  uploaded or placed in a CI secret.
- `ledger.json` — the approved-version ledger; `ledger.json.sig` is its
  whole-file Ed25519 signature by the root key. An installer or the version
  switcher that cannot verify this signature refuses every version.
- Entries are append-only with a monotonically increasing `seq`. A `revoked`
  entry is a tombstone: that version can never be installed again.
- Starting the ledger and appending versions is an OWNER action performed on
  the owner's machine with `tools/release_signing.py` (see the doc for the
  exact ceremony).
