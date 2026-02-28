"""Credential vault CLI commands."""

import json
import os


def get_vault():
    """Get an unlocked CredentialVault instance."""
    passphrase = os.environ.get("VAULT_PASSPHRASE", "")
    if not passphrase:
        import getpass
        passphrase = getpass.getpass("Vault passphrase: ")
    if not passphrase:
        print("  ERROR: No vault passphrase provided.")
        print("  Set VAULT_PASSPHRASE env var or enter it when prompted.")
        return None
    try:
        from utils.credential_vault import CredentialVault
        return CredentialVault(passphrase=passphrase)
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def store(key: str, value: str):
    """Store a credential in the vault."""
    print(f"\n{'='*60}")
    print(f"  VAULT — Store Credential")
    print(f"{'='*60}\n")

    vault = get_vault()
    if not vault:
        return

    try:
        parsed = json.loads(value)
        vault.store(key, parsed)
        print(f"  Stored '{key}' (JSON object with {len(parsed)} keys)")
    except json.JSONDecodeError:
        vault.store(key, value)
        print(f"  Stored '{key}' (string, {len(value)} chars)")


def get(key: str):
    """Retrieve a credential from the vault."""
    vault = get_vault()
    if not vault:
        return

    try:
        val = vault.retrieve(key)
        if isinstance(val, dict):
            display = {}
            for k, v in val.items():
                if "password" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    display[k] = f"{str(v)[:3]}{'*' * max(0, len(str(v))-3)}"
                else:
                    display[k] = v
            print(json.dumps(display, indent=2))
        else:
            print(f"  {key}: {str(val)[:5]}{'*' * max(0, len(str(val))-5)}")
    except KeyError:
        print(f"  Key '{key}' not found in vault.")


def delete(key: str):
    """Delete a credential from the vault."""
    vault = get_vault()
    if not vault:
        return

    if vault.delete(key):
        print(f"  Deleted '{key}'")
    else:
        print(f"  Key '{key}' not found.")


def list_all():
    """List all vault credential keys."""
    print(f"\n{'='*60}")
    print(f"  VAULT — Stored Credentials")
    print(f"{'='*60}\n")

    vault = get_vault()
    if not vault:
        return

    keys = vault.list_keys()
    if keys:
        for k in keys:
            entry = vault.retrieve_full(k)
            updated = entry.get("updated_at", "?")[:10]
            accesses = entry.get("access_count", 0)
            print(f"  {k:30s}  updated: {updated}  accesses: {accesses}")
    else:
        print("  (vault is empty)")
    print()


def stats():
    """Show vault statistics."""
    print(f"\n{'='*60}")
    print(f"  VAULT — Statistics")
    print(f"{'='*60}\n")

    vault = get_vault()
    if not vault:
        return

    s = vault.stats()
    print(f"  Total credentials: {s['total_credentials']}")
    print(f"  Vault file size: {s['vault_file_size']} bytes")
    if s["keys"]:
        print(f"  Keys: {', '.join(s['keys'])}")
    print()
