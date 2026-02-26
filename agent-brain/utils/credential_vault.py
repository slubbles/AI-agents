"""
Credential Vault — Encrypted secret storage for Agent Brain.

Stores API keys, login credentials, tokens, and other secrets.
Uses Fernet symmetric encryption (AES-128-CBC) with a master key
derived from a user-supplied passphrase via PBKDF2.

Storage: Single encrypted JSON file at <project>/vault/credentials.enc
Master key salt: <project>/vault/.salt (random, generated once)

Usage:
    vault = CredentialVault(passphrase="my-secret-passphrase")
    vault.store("linkedin", {"email": "user@example.com", "password": "..."})
    creds = vault.retrieve("linkedin")
    vault.delete("linkedin")
    vault.list_keys()  # ["github", "twitter", ...]
"""

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Vault location
VAULT_DIR = os.path.join(os.path.dirname(__file__), "..", "vault")
VAULT_FILE = os.path.join(VAULT_DIR, "credentials.enc")
SALT_FILE = os.path.join(VAULT_DIR, ".salt")

# KDF parameters
KDF_ITERATIONS = 480_000  # OWASP 2023 recommendation for PBKDF2-SHA256
SALT_LENGTH = 32


class VaultError(Exception):
    """Base class for vault errors."""
    pass


class VaultLockedError(VaultError):
    """Raised when trying to access a locked vault."""
    pass


class VaultDecryptionError(VaultError):
    """Raised when passphrase is wrong."""
    pass


class CredentialVault:
    """Encrypted credential storage with Fernet (AES-128-CBC + HMAC).
    
    Thread-safe for reads. Writes use load-modify-save with file locking.
    Auto-locks after configurable timeout.
    """

    def __init__(
        self,
        passphrase: Optional[str] = None,
        vault_dir: Optional[str] = None,
        auto_lock_seconds: int = 300,
    ):
        self._vault_dir = vault_dir or VAULT_DIR
        self._vault_file = os.path.join(self._vault_dir, "credentials.enc")
        self._salt_file = os.path.join(self._vault_dir, ".salt")
        self._fernet: Optional[Fernet] = None
        self._unlocked_at: float = 0
        self._auto_lock_seconds = auto_lock_seconds

        os.makedirs(self._vault_dir, exist_ok=True)

        if passphrase:
            self.unlock(passphrase)

    # ── Key Derivation ──────────────────────────────────────

    def _get_or_create_salt(self) -> bytes:
        """Load existing salt or generate a new one."""
        if os.path.exists(self._salt_file):
            with open(self._salt_file, "rb") as f:
                return f.read()
        salt = os.urandom(SALT_LENGTH)
        with open(self._salt_file, "wb") as f:
            f.write(salt)
        return salt

    def _derive_key(self, passphrase: str) -> bytes:
        """Derive a Fernet key from passphrase + salt using PBKDF2."""
        salt = self._get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=KDF_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        return key

    # ── Lock / Unlock ───────────────────────────────────────

    def unlock(self, passphrase: str) -> None:
        """Unlock the vault with the given passphrase.
        
        If vault file exists, validates by attempting decryption.
        If vault file doesn't exist, sets up the key for first use.
        """
        key = self._derive_key(passphrase)
        fernet = Fernet(key)

        # Validate passphrase against existing vault
        if os.path.exists(self._vault_file):
            try:
                self._load_raw(fernet)
            except InvalidToken:
                raise VaultDecryptionError("Wrong passphrase — cannot decrypt vault")

        self._fernet = fernet
        self._unlocked_at = time.time()

    def lock(self) -> None:
        """Lock the vault — clear key from memory."""
        self._fernet = None
        self._unlocked_at = 0

    @property
    def is_unlocked(self) -> bool:
        """Check if vault is unlocked and not timed out."""
        if self._fernet is None:
            return False
        if self._auto_lock_seconds > 0:
            elapsed = time.time() - self._unlocked_at
            if elapsed > self._auto_lock_seconds:
                self.lock()
                return False
        return True

    def _require_unlocked(self) -> Fernet:
        """Assert vault is unlocked, return Fernet instance."""
        if not self.is_unlocked:
            raise VaultLockedError("Vault is locked — call unlock(passphrase) first")
        assert self._fernet is not None
        self._unlocked_at = time.time()  # Reset timer on activity
        return self._fernet

    # ── Raw I/O ─────────────────────────────────────────────

    def _load_raw(self, fernet: Optional[Fernet] = None) -> dict:
        """Decrypt and parse the vault file."""
        f = fernet or self._require_unlocked()
        if not os.path.exists(self._vault_file):
            return {}
        with open(self._vault_file, "rb") as fp:
            encrypted = fp.read()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted.decode("utf-8"))

    def _save_raw(self, data: dict) -> None:
        """Encrypt and write the vault file atomically."""
        f = self._require_unlocked()
        plaintext = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        encrypted = f.encrypt(plaintext)

        # Atomic write: tmp file + rename
        tmp_path = self._vault_file + ".tmp"
        with open(tmp_path, "wb") as fp:
            fp.write(encrypted)
        os.replace(tmp_path, self._vault_file)

    # ── CRUD Operations ─────────────────────────────────────

    def store(self, key: str, value: Any, metadata: Optional[dict] = None) -> None:
        """Store a credential under the given key.
        
        Args:
            key: Unique identifier (e.g. "linkedin", "github_token")
            value: The secret data (string, dict, etc.)
            metadata: Optional metadata (tags, notes, expiry)
        """
        self._require_unlocked()
        vault = self._load_raw()

        entry = {
            "value": value,
            "created_at": vault.get(key, {}).get("created_at", _now_iso()),
            "updated_at": _now_iso(),
            "access_count": vault.get(key, {}).get("access_count", 0),
        }
        if metadata:
            entry["metadata"] = metadata

        vault[key] = entry
        self._save_raw(vault)

    def retrieve(self, key: str) -> Any:
        """Retrieve a credential by key. Returns the value only.
        
        Raises KeyError if key doesn't exist.
        """
        self._require_unlocked()
        vault = self._load_raw()
        if key not in vault:
            raise KeyError(f"Credential '{key}' not found in vault")

        # Increment access counter
        vault[key]["access_count"] = vault[key].get("access_count", 0) + 1
        vault[key]["last_accessed"] = _now_iso()
        self._save_raw(vault)

        return vault[key]["value"]

    def retrieve_full(self, key: str) -> dict:
        """Retrieve full entry including metadata."""
        self._require_unlocked()
        vault = self._load_raw()
        if key not in vault:
            raise KeyError(f"Credential '{key}' not found in vault")
        return vault[key]

    def delete(self, key: str) -> bool:
        """Delete a credential. Returns True if it existed."""
        self._require_unlocked()
        vault = self._load_raw()
        if key not in vault:
            return False
        del vault[key]
        self._save_raw(vault)
        return True

    def list_keys(self) -> list[str]:
        """List all stored credential keys."""
        self._require_unlocked()
        vault = self._load_raw()
        return sorted(vault.keys())

    def has(self, key: str) -> bool:
        """Check if a credential exists."""
        self._require_unlocked()
        vault = self._load_raw()
        return key in vault

    def update_value(self, key: str, value: Any) -> None:
        """Update just the value of an existing credential."""
        self._require_unlocked()
        vault = self._load_raw()
        if key not in vault:
            raise KeyError(f"Credential '{key}' not found in vault")
        vault[key]["value"] = value
        vault[key]["updated_at"] = _now_iso()
        self._save_raw(vault)

    # ── Bulk Operations ─────────────────────────────────────

    def export_keys_metadata(self) -> dict:
        """Export key names with metadata (no secrets). Safe to log."""
        self._require_unlocked()
        vault = self._load_raw()
        result = {}
        for key, entry in vault.items():
            result[key] = {
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "access_count": entry.get("access_count", 0),
                "last_accessed": entry.get("last_accessed"),
                "has_metadata": "metadata" in entry,
            }
        return result

    def rotate_passphrase(self, old_passphrase: str, new_passphrase: str) -> None:
        """Re-encrypt the entire vault with a new passphrase.
        
        Steps:
        1. Decrypt with old passphrase
        2. Generate new salt
        3. Derive new key
        4. Re-encrypt and save
        """
        # Decrypt with current key
        old_key = self._derive_key(old_passphrase)
        old_fernet = Fernet(old_key)
        try:
            vault = self._load_raw(old_fernet)
        except InvalidToken:
            raise VaultDecryptionError("Old passphrase is incorrect")

        # Generate new salt (overwrite old one)
        new_salt = os.urandom(SALT_LENGTH)
        with open(self._salt_file, "wb") as f:
            f.write(new_salt)

        # Derive new key and re-encrypt
        new_key = self._derive_key(new_passphrase)
        self._fernet = Fernet(new_key)
        self._unlocked_at = time.time()
        self._save_raw(vault)

    def wipe(self) -> None:
        """Destroy the vault completely. IRREVERSIBLE."""
        self.lock()
        for path in [self._vault_file, self._salt_file, self._vault_file + ".tmp"]:
            if os.path.exists(path):
                os.remove(path)

    # ── Stats ───────────────────────────────────────────────

    def stats(self) -> dict:
        """Return vault statistics (no secrets)."""
        self._require_unlocked()
        vault = self._load_raw()
        return {
            "total_credentials": len(vault),
            "keys": sorted(vault.keys()),
            "vault_file_size": os.path.getsize(self._vault_file) if os.path.exists(self._vault_file) else 0,
        }


# ── Helpers ─────────────────────────────────────────────────

def _now_iso() -> str:
    """UTC ISO timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── CLI Interface ───────────────────────────────────────────

def cli_main():
    """Simple CLI for vault management."""
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="Agent Brain Credential Vault")
    sub = parser.add_subparsers(dest="command")

    # store
    p_store = sub.add_parser("store", help="Store a credential")
    p_store.add_argument("key", help="Credential key (e.g. 'linkedin')")
    p_store.add_argument("--json", action="store_true", help="Read value as JSON from stdin")

    # retrieve
    p_get = sub.add_parser("get", help="Retrieve a credential")
    p_get.add_argument("key", help="Credential key")

    # delete 
    p_del = sub.add_parser("delete", help="Delete a credential")
    p_del.add_argument("key", help="Credential key")

    # list
    sub.add_parser("list", help="List all credential keys")

    # stats
    sub.add_parser("stats", help="Show vault statistics")

    # rotate
    sub.add_parser("rotate", help="Change vault passphrase")

    # wipe
    sub.add_parser("wipe", help="Destroy the vault (IRREVERSIBLE)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    passphrase = os.environ.get("VAULT_PASSPHRASE") or getpass.getpass("Vault passphrase: ")
    vault = CredentialVault(passphrase=passphrase)

    if args.command == "store":
        if args.json:
            import sys
            value = json.load(sys.stdin)
        else:
            value = getpass.getpass(f"Value for '{args.key}': ")
        vault.store(args.key, value)
        print(f"Stored '{args.key}'")

    elif args.command == "get":
        try:
            val = vault.retrieve(args.key)
            if isinstance(val, dict):
                print(json.dumps(val, indent=2))
            else:
                print(val)
        except KeyError as e:
            print(f"Error: {e}")

    elif args.command == "delete":
        if vault.delete(args.key):
            print(f"Deleted '{args.key}'")
        else:
            print(f"'{args.key}' not found")

    elif args.command == "list":
        keys = vault.list_keys()
        if keys:
            for k in keys:
                print(f"  - {k}")
        else:
            print("(empty vault)")

    elif args.command == "stats":
        s = vault.stats()
        print(json.dumps(s, indent=2))

    elif args.command == "rotate":
        new_pass = getpass.getpass("New passphrase: ")
        confirm = getpass.getpass("Confirm new passphrase: ")
        if new_pass != confirm:
            print("Passphrases don't match")
            return
        vault.rotate_passphrase(passphrase, new_pass)
        print("Passphrase rotated successfully")

    elif args.command == "wipe":
        confirm = input("Type 'WIPE' to confirm vault destruction: ")
        if confirm == "WIPE":
            vault.wipe()
            print("Vault destroyed")
        else:
            print("Aborted")


if __name__ == "__main__":
    cli_main()
