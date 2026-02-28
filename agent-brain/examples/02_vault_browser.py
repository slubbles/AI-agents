#!/usr/bin/env python3
"""
Example: Credential Vault + Browser Auth

Demonstrates how to:
1. Store credentials securely in the encrypted vault
2. Use them automatically with the stealth browser
3. Fetch pages from auth-required sites (LinkedIn, Indeed, etc.)

Run:
    python examples/02_vault_browser.py

Prerequisites:
    export VAULT_PASSPHRASE="your-secure-passphrase"
    
Note: This example uses mock credentials - replace with real ones.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def example_vault_store():
    """Store credentials in the vault."""
    from utils.credential_vault import CredentialVault
    
    print("\n=== STEP 1: Store Credentials ===\n")
    
    # Check for passphrase
    passphrase = os.environ.get("VAULT_PASSPHRASE")
    if not passphrase:
        print("ERROR: Set VAULT_PASSPHRASE environment variable first")
        print("  export VAULT_PASSPHRASE='your-secure-passphrase'")
        return None
    
    # Initialize vault
    vault = CredentialVault(passphrase=passphrase)
    
    # Store LinkedIn credentials (replace with real ones)
    # Key format: domain with dots replaced by underscores
    vault.store("linkedin_com", {
        "email": "your-email@example.com",
        "password": "your-password"
    })
    print("  ✓ Stored: linkedin_com")
    
    # You can also store:
    # vault.store("indeed_com", {"email": "...", "password": "..."})
    # vault.store("github_com", {"email": "...", "password": "..."})
    
    print("\n  Vault location: vault/credentials.enc")
    return vault


def example_vault_retrieve():
    """Retrieve credentials from the vault."""
    from utils.credential_vault import CredentialVault
    
    print("\n=== STEP 2: Retrieve Credentials ===\n")
    
    passphrase = os.environ.get("VAULT_PASSPHRASE")
    if not passphrase:
        print("ERROR: Set VAULT_PASSPHRASE")
        return
    
    vault = CredentialVault(passphrase=passphrase)
    
    # List all keys
    keys = vault.list_keys()
    print(f"  Keys in vault: {keys}")
    
    # Retrieve specific credential
    if "linkedin_com" in keys:
        creds = vault.retrieve("linkedin_com")
        print(f"  linkedin_com email: {creds.get('email', 'N/A')}")
        print(f"  linkedin_com password: {'*' * len(creds.get('password', ''))}")


async def example_browser_fetch_with_auth():
    """Fetch a LinkedIn page using stored credentials."""
    from utils.credential_vault import CredentialVault
    from browser.session_manager import BrowserSession
    
    print("\n=== STEP 3: Browser Fetch with Auth ===\n")
    
    passphrase = os.environ.get("VAULT_PASSPHRASE")
    if not passphrase:
        print("ERROR: Set VAULT_PASSPHRASE")
        return
    
    # Initialize vault and browser session
    vault = CredentialVault(passphrase=passphrase)
    session = BrowserSession(vault=vault, headless=True)
    
    print("  Fetching LinkedIn profile...")
    print("  (Browser will automatically log in using vault credentials)")
    
    # This would actually fetch the page
    # result = await session.fetch("https://linkedin.com/in/someone")
    # print(f"  Result: {result['success']}")
    
    print("  (Dry run - uncomment to actually fetch)")
    
    # Clean up
    await session.close_all()


def main():
    print("\n" + "="*60)
    print("  VAULT + BROWSER AUTH EXAMPLE")
    print("="*60)
    
    # CLI alternatives
    print("\nCLI equivalents:")
    print("  # Store credentials")
    print("  python main.py --vault-store linkedin_com '{\"email\":\"x\",\"password\":\"y\"}'")
    print("")
    print("  # List vault keys")
    print("  python main.py --vault-list")
    print("")
    print("  # Fetch with browser")
    print("  python main.py --browser-fetch 'https://linkedin.com/in/someone'")
    print("")
    
    # Run examples
    vault = example_vault_store()
    if vault:
        example_vault_retrieve()
        asyncio.run(example_browser_fetch_with_auth())


if __name__ == "__main__":
    main()
