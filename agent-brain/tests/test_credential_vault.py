"""Tests for credential vault — encrypted secret storage."""

import json
import os
import time
import pytest

from utils.credential_vault import (
    CredentialVault,
    VaultLockedError,
    VaultDecryptionError,
    VaultError,
)


@pytest.fixture
def vault_dir(tmp_path):
    """Temporary vault directory."""
    return str(tmp_path / "vault")


@pytest.fixture
def vault(vault_dir):
    """Unlocked vault for testing."""
    return CredentialVault(passphrase="test-passphrase-123", vault_dir=vault_dir)


class TestVaultBasics:
    """Core CRUD operations."""

    def test_store_and_retrieve(self, vault):
        vault.store("github", "ghp_abc123")
        assert vault.retrieve("github") == "ghp_abc123"

    def test_store_dict_value(self, vault):
        creds = {"email": "user@example.com", "password": "secret", "token": "tok_123"}
        vault.store("linkedin", creds)
        retrieved = vault.retrieve("linkedin")
        assert retrieved == creds
        assert retrieved["email"] == "user@example.com"

    def test_retrieve_nonexistent_raises(self, vault):
        with pytest.raises(KeyError, match="not found"):
            vault.retrieve("doesnt_exist")

    def test_delete_existing(self, vault):
        vault.store("temp", "value")
        assert vault.delete("temp") is True
        with pytest.raises(KeyError):
            vault.retrieve("temp")

    def test_delete_nonexistent(self, vault):
        assert vault.delete("ghost") is False

    def test_list_keys(self, vault):
        vault.store("alpha", "a")
        vault.store("beta", "b")
        vault.store("gamma", "c")
        assert vault.list_keys() == ["alpha", "beta", "gamma"]

    def test_list_keys_empty(self, vault):
        assert vault.list_keys() == []

    def test_has(self, vault):
        vault.store("exists", "yes")
        assert vault.has("exists") is True
        assert vault.has("nope") is False

    def test_update_value(self, vault):
        vault.store("key", "v1")
        vault.update_value("key", "v2")
        assert vault.retrieve("key") == "v2"

    def test_update_nonexistent_raises(self, vault):
        with pytest.raises(KeyError):
            vault.update_value("ghost", "val")


class TestVaultEncryption:
    """Encryption and decryption."""

    def test_vault_file_is_encrypted(self, vault, vault_dir):
        vault.store("secret", "plaintext-value")
        vault_file = os.path.join(vault_dir, "credentials.enc")
        with open(vault_file, "rb") as f:
            raw = f.read()
        # Raw file should NOT contain plaintext
        assert b"plaintext-value" not in raw
        assert b"secret" not in raw

    def test_wrong_passphrase_fails(self, vault, vault_dir):
        vault.store("key", "value")
        with pytest.raises(VaultDecryptionError):
            CredentialVault(passphrase="wrong-passphrase", vault_dir=vault_dir)

    def test_correct_passphrase_works(self, vault, vault_dir):
        vault.store("key", "value")
        vault2 = CredentialVault(passphrase="test-passphrase-123", vault_dir=vault_dir)
        assert vault2.retrieve("key") == "value"

    def test_new_vault_no_file(self, vault_dir):
        """Creating a new vault with no existing file doesn't error."""
        v = CredentialVault(passphrase="fresh", vault_dir=vault_dir)
        assert v.list_keys() == []


class TestVaultLocking:
    """Lock/unlock and auto-lock behavior."""

    def test_locked_vault_raises(self, vault_dir):
        v = CredentialVault(vault_dir=vault_dir)  # No passphrase
        with pytest.raises(VaultLockedError):
            v.list_keys()

    def test_explicit_lock(self, vault):
        assert vault.is_unlocked
        vault.lock()
        assert not vault.is_unlocked
        with pytest.raises(VaultLockedError):
            vault.list_keys()

    def test_unlock_after_lock(self, vault, vault_dir):
        vault.store("key", "val")
        vault.lock()
        vault.unlock("test-passphrase-123")
        assert vault.retrieve("key") == "val"

    def test_auto_lock_timeout(self, vault_dir):
        v = CredentialVault(
            passphrase="pass",
            vault_dir=vault_dir,
            auto_lock_seconds=1,
        )
        assert v.is_unlocked
        time.sleep(1.5)
        assert not v.is_unlocked

    def test_activity_resets_timer(self, vault_dir):
        v = CredentialVault(
            passphrase="pass",
            vault_dir=vault_dir,
            auto_lock_seconds=2,
        )
        v.store("a", "1")
        time.sleep(1)
        v.store("b", "2")  # Resets timer
        time.sleep(1)
        assert v.is_unlocked  # Still unlocked because timer was reset


class TestVaultMetadata:
    """Metadata and access tracking."""

    def test_access_count_increments(self, vault):
        vault.store("counted", "val")
        vault.retrieve("counted")
        vault.retrieve("counted")
        vault.retrieve("counted")
        full = vault.retrieve_full("counted")
        assert full["access_count"] == 3

    def test_timestamps_set(self, vault):
        vault.store("timed", "val")
        full = vault.retrieve_full("timed")
        assert "created_at" in full
        assert "updated_at" in full

    def test_custom_metadata(self, vault):
        vault.store("api_key", "key123", metadata={"service": "openai", "tier": "free"})
        full = vault.retrieve_full("api_key")
        assert full["metadata"]["service"] == "openai"

    def test_export_no_secrets(self, vault):
        vault.store("secret1", "PRIVATE_DATA")
        vault.store("secret2", "MORE_PRIVATE")
        export = vault.export_keys_metadata()
        assert "secret1" in export
        assert "PRIVATE_DATA" not in str(export)
        assert "value" not in export["secret1"]

    def test_stats(self, vault):
        vault.store("a", "1")
        vault.store("b", "2")
        s = vault.stats()
        assert s["total_credentials"] == 2
        assert "a" in s["keys"]


class TestVaultRotation:
    """Passphrase rotation."""

    def test_rotate_passphrase(self, vault, vault_dir):
        vault.store("key", "value")
        vault.rotate_passphrase("test-passphrase-123", "new-passphrase-456")
        
        # Old passphrase should fail
        with pytest.raises(VaultDecryptionError):
            CredentialVault(passphrase="test-passphrase-123", vault_dir=vault_dir)
        
        # New passphrase should work
        vault2 = CredentialVault(passphrase="new-passphrase-456", vault_dir=vault_dir)
        assert vault2.retrieve("key") == "value"

    def test_rotate_wrong_old_passphrase(self, vault):
        vault.store("key", "value")
        with pytest.raises(VaultDecryptionError):
            vault.rotate_passphrase("wrong-old-pass", "new-pass")


class TestVaultWipe:
    """Destruction."""

    def test_wipe_removes_files(self, vault, vault_dir):
        vault.store("key", "value")
        vault.wipe()
        assert not os.path.exists(os.path.join(vault_dir, "credentials.enc"))
        assert not os.path.exists(os.path.join(vault_dir, ".salt"))

    def test_wipe_locks_vault(self, vault):
        vault.store("key", "value")
        vault.wipe()
        assert not vault.is_unlocked


class TestVaultEdgeCases:
    """Edge cases and robustness."""

    def test_store_complex_structure(self, vault):
        """Complex nested data survives round-trip."""
        data = {
            "cookies": [{"name": "session", "value": "abc"}, {"name": "csrf", "value": "def"}],
            "headers": {"Authorization": "Bearer xyz"},
            "numbers": [1, 2.5, -3],
            "nested": {"a": {"b": {"c": True}}},
        }
        vault.store("complex", data)
        assert vault.retrieve("complex") == data

    def test_overwrite_preserves_created_at(self, vault):
        vault.store("key", "v1")
        full1 = vault.retrieve_full("key")
        created_at = full1["created_at"]
        
        time.sleep(0.01)
        vault.store("key", "v2")
        full2 = vault.retrieve_full("key")
        
        assert full2["created_at"] == created_at  # Preserved
        assert full2["updated_at"] != created_at  # Updated

    def test_empty_string_key(self, vault):
        vault.store("", "empty-key")
        assert vault.retrieve("") == "empty-key"

    def test_unicode_values(self, vault):
        vault.store("unicode", "日本語のパスワード 🔐")
        assert vault.retrieve("unicode") == "日本語のパスワード 🔐"

    def test_large_value(self, vault):
        big = "x" * 100_000
        vault.store("big", big)
        assert vault.retrieve("big") == big
