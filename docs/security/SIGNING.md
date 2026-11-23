# Release signing and the approved-version ledger

Production gates for the distribution pipeline (three of them stay HOLD until
this procedure is executed on the owner's machine):

1. **Real signing root** — an Ed25519 root keypair generated on the owner's
   machine. The private key never enters this repository, a CI secret, a chat
   transcript or a log. GitHub Actions intentionally cannot hold it: CI builds,
   a human signs.
2. **OS-protected activation** — installers and the version switcher verify the
   signed ledger before they touch the system; a version that is not approved
   in the ledger is refused (unknown = unapproved).
3. **Durable anti-rollback** — ledger entries carry a monotonically increasing
   `seq`; a switch to a LOWER seq than the locally recorded installed seq is
   refused unless the operator passes `--allow-rollback` explicitly, and a
   `revoked` entry is a permanent tombstone.

## The signing ceremony (owner machine, once)

```bash
# 1) Generate the root keypair OUTSIDE the repository (0600 private key).
python3 tools/release_signing.py keygen --out-dir ~/.tihulu-signing

# 2) Publish ONLY the public key. Never commit the private key; .gitignore
#    blocks root-private.pem, but the ceremony keeps it outside the tree.
cp ~/.tihulu-signing/root-public.pem versions/releases/root-public.pem

# 3) Back up the private key to offline storage you control (paper, hardware
#    token, offline disk). Losing it means a new root and a fresh ledger.
```

Rotating the root = generate a new keypair, append a ledger entry that records
the new public key fingerprint, and re-sign the ledger with the OLD key first.
Tooling for rotation (`ledger rekey`) is a later increment; document any manual
rotation in the commit history.

## Signing a draft release (owner machine, per release)

After the four-gate CI run creates the draft release:

```bash
TAG=desktop-0.3.2.dev4-20261122-2327

# 1) Download SHA256SUMS from the release and verify it against the assets.
gh release download "$TAG" -p SHA256SUMS -D /tmp/rel --clobber

# 2) Sign the manifest digest with the root key and upload the signature.
python3 tools/release_signing.py sign \
  --key ~/.tihulu-signing/root-private.pem --file /tmp/rel/SHA256SUMS
gh release upload "$TAG" /tmp/rel/SHA256SUMS.sig

# 3) Record the version in the signed ledger and commit it.
python3 tools/release_signing.py ledger append --key ~/.tihulu-signing/root-private.pem \
  --version 0.3.2.dev4 --tag "$TAG" --source-sha <main-commit-sha> \
  --sha256sums sha256:<SHA256SUMS digest> --note "four-gate CI verified"
git add versions/releases && git commit -m "release: approve $TAG in the ledger"
```

## Verifying a release (anyone, no private key)

```bash
python3 tools/release_signing.py verify \
  --pub versions/releases/root-public.pem --file SHA256SUMS --sig SHA256SUMS.sig
# or let the tools decide a switch request:
python3 tools/release_signing.py ledger check --pub versions/releases/root-public.pem \
  --source-sha <commit-sha> --state-file ~/.local/state/tihulu-ledger.json
```

Exit codes for `ledger check`: `0` = allow, `2` = refuse (not-in-ledger,
rollback or revoked tombstone). Any other error means the ledger signature is
invalid — refuse everything and investigate.

## Revoking a version (tombstone)

```bash
python3 tools/release_signing.py ledger append --key ~/.tihulu-signing/root-private.pem \
  --version 0.3.2.dev4 --tag <old-tag> --source-sha <old-sha> --revoke \
  --note "reason for the tombstone"
```

The tombstone does not delete history: the entry flips to `revoked`, the file
is re-signed, and every future switch to that SHA is refused permanently.

## What this does NOT do (yet)

- The desktop app does not verify its own bundle at startup against the ledger
  (planned increment, needs packaging changes).
- The one-line `install-linux.sh` path is trust-on-first-use by nature; the
  signed ledger governs the *version switcher* first.
- CI never signs; draft releases stay unsigned until the owner signs them.
