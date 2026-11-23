#!/usr/bin/env python3
"""Release signing and the approved-version ledger for TIHULU Flight Radar.

Three production gates the distribution pipeline needs:
  1. A real signing root. The Ed25519 private key is generated on the OWNER's
     machine and never enters a repository, a CI secret or a log. Everything
     signed here is signed by a human with that key in their own hands.
  2. An approved-version ledger (versions/releases/ledger.json) whose whole
     file is signed by the root key: installers and the version switcher
     refuse versions that are not in it (unknown = unapproved).
  3. Anti-rollback: ledger entries carry a monotonically increasing seq; the
     switcher refuses a lower seq than the locally recorded installed seq
     unless the operator explicitly allows the rollback. A revoked entry
     (tombstone) is refused permanently.

The signing backend is the system openssl binary (Ed25519, raw input): no
third-party Python packages, so the tool runs on the owner's machine and on
target systems with nothing but python3 + openssl.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FORMAT = 1
LEDGER_PATH = Path("versions/releases/ledger.json")
LEDGER_SIG = Path("versions/releases/ledger.json.sig")
PUBLIC_KEY_PATH = Path("versions/releases/root-public.pem")
HEX = "0123456789abcdef"


class SigningError(RuntimeError):
    """Raised when a signing, verification or ledger operation fails."""


# ---------------------------------------------------------------- openssl glue
def _run(args: list[str], stdin_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(["openssl", *args], input=stdin_bytes,
                          capture_output=True)
    if proc.returncode != 0:
        raise SigningError("openssl failed: "
                           + proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def keygen(out_dir: Path) -> dict:
    """Create the root keypair. The private key never leaves out_dir (0600)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    private = out_dir / "root-private.pem"
    public = out_dir / "root-public.pem"
    if private.exists() or public.exists():
        raise SigningError(f"{out_dir} already holds a root keypair; "
                           "move it away or choose another directory.")
    _run(["genpkey", "-algorithm", "ed25519", "-out", str(private)])
    os.chmod(private, 0o600)
    _run(["pkey", "-in", str(private), "-pubout", "-out", str(public)])
    fingerprint = public_fingerprint(public)
    return {"private": str(private), "public": str(public),
            "fingerprint": fingerprint}


def public_fingerprint(public: Path) -> str:
    import hashlib
    raw = _run(["pkey", "-pubin", "-in", str(public), "-pubout",
                "-outform", "DER"])
    return hashlib.sha256(raw).hexdigest()[:32]


def sign_digest(private: Path, digest_hex: str, out: Path) -> Path:
    """Sign the 32-byte SHA-256 digest of a release manifest (raw Ed25519)."""
    if len(digest_hex) != 64 or any(c not in HEX for c in digest_hex):
        raise SigningError("expected a 64-character sha256 hex digest.")
    # openssl cannot size a stdin one-shot Ed25519 message: use a temp file.
    with tempfile.NamedTemporaryFile(prefix="tihulu-digest-",
                                     delete=False) as handle:
        handle.write(bytes.fromhex(digest_hex))
        message = Path(handle.name)
    try:
        signature = _run(["pkeyutl", "-sign", "-inkey", str(private),
                          "-rawin", "-in", str(message)])
    finally:
        message.unlink(missing_ok=True)
    out.write_bytes(signature)
    os.chmod(out, 0o644)
    return out


def verify_digest(public: Path, digest_hex: str, signature: Path) -> bool:
    if len(digest_hex) != 64 or any(c not in HEX for c in digest_hex):
        raise SigningError("expected a 64-character sha256 hex digest.")
    with tempfile.NamedTemporaryFile(prefix="tihulu-digest-",
                                     delete=False) as handle:
        handle.write(bytes.fromhex(digest_hex))
        message = Path(handle.name)
    try:
        proc = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public),
             "-sigfile", str(signature), "-rawin", "-in", str(message)],
            capture_output=True)
    finally:
        message.unlink(missing_ok=True)
    return proc.returncode == 0


# ---------------------------------------------------------------------- ledger
def empty_ledger() -> dict:
    return {"format": FORMAT, "entries": [], "head_seq": 0}


def load_ledger(path: Path = LEDGER_PATH) -> dict:
    if not path.exists():
        return empty_ledger()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT or not isinstance(data.get("entries"), list):
        raise SigningError("ledger format is not supported by this tool.")
    return data


def verify_ledger(public: Path, path: Path = LEDGER_PATH,
                  signature: Path = LEDGER_SIG) -> bool:
    if not path.exists() or not signature.exists():
        return False
    return verify_digest(public, sha256_file(path), signature)


def append_entry(entry: dict, private: Path, path: Path = LEDGER_PATH) -> dict:
    """Append one approved (or revoked) version and re-sign the ledger."""
    ledger = load_ledger(path)
    entries = ledger["entries"]
    for field in ("version", "tag", "source_sha"):
        if not entry.get(field):
            raise SigningError(f"ledger entry needs a {field}.")
    if len(entry["source_sha"]) != 40 or any(
            c not in HEX for c in entry["source_sha"].lower()):
        raise SigningError("source_sha must be a 40-character commit SHA.")
    wanted = entry["source_sha"].lower()
    existing_index = next((i for i, e in enumerate(entries)
                           if e["source_sha"] == wanted), None)
    if entry.get("status", "approved") == "revoked":
        # Tombstone: flip the existing approved entry; refuse to revoke an
        # unknown version (nothing to revoke, and unknown is refused anyway).
        if existing_index is None:
            raise SigningError(
                f"{wanted} is not in the ledger; there is nothing to revoke.")
        entries[existing_index]["status"] = "revoked"
        entries[existing_index]["note"] = (entries[existing_index].get("note", "")
                                           + " | revoked: "
                                           + entry.get("note", "")).strip(" |")
        ledger["head_seq"] = entries[-1]["seq"]
        text = json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        sign_digest(private, sha256_file(path), LEDGER_SIG if path == LEDGER_PATH
                    else path.with_suffix(path.suffix + ".sig"))
        return entries[existing_index]
    if existing_index is not None:
        raise SigningError(
            f"{wanted} is already in the ledger (seq "
            f"{entries[existing_index]['seq']}); use revoke to tombstone it.")
    seq = (entries[-1]["seq"] if entries else 0) + 1
    prev_seq = entries[-1]["seq"] if entries else 0
    record = {
        "seq": seq,
        "status": "approved" if entry.get("status", "approved") == "approved"
                  else "revoked",
        "version": entry["version"],
        "tag": entry["tag"],
        "source_sha": entry["source_sha"].lower(),
        "prev_seq": prev_seq,
        "date": entry.get("date") or datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": entry.get("note", ""),
    }
    if entry.get("sha256sums"):
        record["sha256sums"] = entry["sha256sums"]
    entries.append(record)
    ledger["head_seq"] = seq
    text = json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    sign_digest(private, sha256_file(path), LEDGER_SIG if path == LEDGER_PATH
                else path.with_suffix(path.suffix + ".sig"))
    return record


def find_entry(ledger: dict, source_sha: str) -> dict | None:
    wanted = source_sha.lower()
    for entry in ledger["entries"]:
        if entry["source_sha"] == wanted:
            return entry
    return None


def switch_decision(ledger: dict, source_sha: str,
                    installed_seq: int | None, allow_rollback: bool) -> dict:
    """Pure decision helper used by the version switcher and by the tests."""
    entry = find_entry(ledger, source_sha)
    if entry is None:
        return {"decision": "refuse", "reason": "not-in-ledger",
                "message": f"{source_sha} is not an approved version; "
                           "unknown source is never installed."}
    if entry["status"] == "revoked":
        return {"decision": "refuse", "reason": "revoked",
                "message": f"seq {entry['seq']} ({entry['version']}) is "
                           "revoked by tombstone and can never be installed."}
    if installed_seq is not None and entry["seq"] < installed_seq \
            and not allow_rollback:
        return {"decision": "refuse", "reason": "rollback",
                "message": f"refusing rollback: installed seq {installed_seq} "
                           f"> requested seq {entry['seq']} "
                           f"({entry['version']}). Pass --allow-rollback to "
                           "override, and record why."}
    if installed_seq is not None and entry["seq"] < installed_seq:
        return {"decision": "allow-rollback", "reason": "explicit",
                "message": f"explicit rollback to seq {entry['seq']} "
                           f"({entry['version']}) allowed by operator."}
    return {"decision": "allow", "reason": "in-ledger",
            "message": f"seq {entry['seq']} ({entry['version']}) approved.",
            "entry": entry}


# ------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    key = sub.add_parser("keygen", help="create the root keypair on this machine")
    key.add_argument("--out-dir", required=True, type=Path,
                     help="directory for root-private.pem (0600) and the public key")

    pub = sub.add_parser("fingerprint", help="show the root public key fingerprint")
    pub.add_argument("--pub", required=True, type=Path)

    sig = sub.add_parser("sign", help="sign a file (its sha256 digest)")
    sig.add_argument("--key", required=True, type=Path)
    sig.add_argument("--file", required=True, type=Path)
    sig.add_argument("--out", type=Path, default=None)

    ver = sub.add_parser("verify", help="verify a signed file")
    ver.add_argument("--pub", required=True, type=Path)
    ver.add_argument("--file", required=True, type=Path)
    ver.add_argument("--sig", required=True, type=Path)

    led = sub.add_parser("ledger", help="ledger operations")
    led_sub = led.add_subparsers(dest="ledger_command", required=True)
    append = led_sub.add_parser("append", help="append an approved version")
    append.add_argument("--key", required=True, type=Path)
    append.add_argument("--version", required=True)
    append.add_argument("--tag", required=True)
    append.add_argument("--source-sha", required=True)
    append.add_argument("--sha256sums", default="")
    append.add_argument("--note", default="")
    append.add_argument("--revoke", action="store_true")
    check = led_sub.add_parser("check", help="decide a switch/install request")
    check.add_argument("--pub", required=True, type=Path)
    check.add_argument("--source-sha", required=True)
    check.add_argument("--installed-seq", type=int, default=None)
    check.add_argument("--state-file", type=Path, default=None,
                       help="read the locally recorded installed seq")
    check.add_argument("--allow-rollback", action="store_true")
    show = led_sub.add_parser("show", help="print the ledger with its status")

    args = parser.parse_args(argv)
    try:
        if args.command == "keygen":
            info = keygen(args.out_dir)
            print("Root keypair created:")
            print(f"  private : {info['private']} (0600, never commit this)")
            print(f"  public  : {info['public']}")
            print(f"  fingerprint: {info['fingerprint']}")
            print("Publish ONLY the public key, then start the ledger with "
                  "'ledger append'.")
            return 0
        if args.command == "fingerprint":
            print(public_fingerprint(args.pub))
            return 0
        if args.command == "sign":
            digest = sha256_file(args.file)
            out = args.out or args.file.with_suffix(args.file.suffix + ".sig")
            sign_digest(args.key, digest, out)
            print(f"signed sha256:{digest}")
            print(f"signature: {out}")
            return 0
        if args.command == "verify":
            digest = sha256_file(args.file)
            ok = verify_digest(args.pub, digest, args.sig)
            print(("VALID" if ok else "INVALID") + f" signature for "
                  f"sha256:{digest}")
            return 0 if ok else 1
        if args.command == "ledger":
            if args.ledger_command == "append":
                record = append_entry(
                    {"version": args.version, "tag": args.tag,
                     "source_sha": args.source_sha,
                     "sha256sums": args.sha256sums or None,
                     "note": args.note, "status":
                     "revoked" if args.revoke else "approved"},
                    args.key)
                print(f"ledger seq {record['seq']} ({record['status']}): "
                      f"{record['version']} @ {record['source_sha']}")
                return 0
            if args.ledger_command == "check":
                if not verify_ledger(args.pub):
                    raise SigningError("ledger signature is INVALID or missing; "
                                       "refuse everything and investigate.")
                ledger = load_ledger()
                installed = args.installed_seq
                if installed is None and args.state_file and args.state_file.exists():
                    installed = json.loads(args.state_file.read_text(
                        encoding="utf-8")).get("seq")
                verdict = switch_decision(ledger, args.source_sha, installed,
                                          args.allow_rollback)
                print(verdict["decision"].upper() + " ("
                      + verdict["reason"] + "): " + verdict["message"])
                entry = verdict.get("entry") or find_entry(ledger,
                                                           args.source_sha)
                if entry:
                    print(f"LEDGER seq={entry['seq']} status={entry['status']} "
                          f"version={entry['version']}")
                return 0 if verdict["decision"].startswith("allow") else 2
            if args.ledger_command == "show":
                ledger = load_ledger()
                for entry in ledger["entries"]:
                    print(f"{entry['seq']:>3} {entry['status']:>8} "
                          f"{entry['version']:<14} {entry['source_sha'][:12]} "
                          f"{entry['tag']}")
                print(f"head_seq: {ledger['head_seq']}")
                print("signature: " + ("VALID" if verify_ledger(PUBLIC_KEY_PATH)
                                       else "INVALID/missing"))
                return 0
    except SigningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
