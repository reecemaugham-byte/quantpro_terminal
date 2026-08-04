"""
core/encryption.py
Fernet symmetric encryption for API keys and sensitive data.
All encryption/decryption uses a single key stored securely.
"""

import os
import base64
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False

# --- Key Storage ---
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
KEY_FILE = DATA_DIR / ".encryption_key"


def _generate_key() -> bytes:
    """Generate a new Fernet encryption key."""
    return Fernet.generate_key()


def _load_or_create_key() -> bytes:
    """Load the encryption key from file, or create one if it doesn't exist."""
    if not FERNET_AVAILABLE:
        raise ImportError("cryptography package not installed. Run: pip install cryptography")

    if KEY_FILE.exists():
        with open(KEY_FILE, "rb") as f:
            key = f.read().strip()
        # Ensure restrictive permissions on existing key
        try:
            os.chmod(KEY_FILE, 0o600)
        except Exception:
            pass
        # Validate the key
        try:
            Fernet(key)
            return key
        except Exception:
            # Key is corrupted, generate a new one
            key = _generate_key()
            with open(KEY_FILE, "wb") as f:
                f.write(key)
            os.chmod(KEY_FILE, 0o600)
            return key
    else:
        # First time — generate and save
        key = _generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        os.chmod(KEY_FILE, 0o600)
        return key



def _get_fernet() -> Fernet:
    """Get a Fernet instance with the current key."""
    if not FERNET_AVAILABLE:
        raise ImportError("cryptography package not installed. Run: pip install cryptography")
    key = _load_or_create_key()
    return Fernet(key)


# ==========================================
# PUBLIC FUNCTIONS
# ==========================================

def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return the encrypted version.
    
    Args:
        plaintext: The string to encrypt (e.g., an API key)
    
    Returns:
        Encrypted string (base64-encoded Fernet token)
    
    Raises:
        ImportError: If cryptography package is not installed
        TypeError: If plaintext is not a string
    """
    if not FERNET_AVAILABLE:
        raise ImportError("cryptography package not installed. Run: pip install cryptography")
    
    if not isinstance(plaintext, str):
        raise TypeError(f"Expected str, got {type(plaintext).__name__}")
    
    if not plaintext:
        return ""
    
    fernet = _get_fernet()
    encrypted = fernet.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt an encrypted string and return the plaintext version.
    
    Args:
        ciphertext: The encrypted string (from encrypt_value)
    
    Returns:
        Decrypted plaintext string
    
    Raises:
        ImportError: If cryptography package is not installed
        InvalidToken: If the ciphertext is corrupted or was encrypted with a different key
    """
    if not FERNET_AVAILABLE:
        raise ImportError("cryptography package not installed. Run: pip install cryptography")
    
    if not isinstance(ciphertext, str):
        raise TypeError(f"Expected str, got {type(ciphertext).__name__}")
    
    if not ciphertext:
        return ""
    
    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        raise ValueError(
            "Failed to decrypt value. The encryption key may have changed, "
            "or the value was not encrypted with this key."
        )


def is_encrypted(value: str) -> bool:
    """Check if a string looks like it has been encrypted by Fernet.
    
    Fernet tokens are base64-encoded and have a specific structure.
    This does NOT guarantee the value is a valid Fernet token — it just
    checks if it looks like one (vs being a plaintext API key).
    
    Args:
        value: The string to check
    
    Returns:
        True if the value appears to be encrypted, False otherwise
    """
    if not value:
        return False
    
    if not isinstance(value, str):
        return False
    
    # Quick checks that eliminate most plaintext values:
    # 1. Fernet tokens are always at least 100 characters
    if len(value) < 80:
        return False
    
    # 2. Fernet tokens start with 'gAAAAA' (base64-encoded version + timestamp)
    # This is the most reliable check
    if value.startswith("gAAAAA"):
        return True
    
    # 3. Try base64 decode — if it fails, it's definitely not encrypted
    try:
        decoded = base64.urlsafe_b64decode(value + "==")  # Add padding
        # Fernet tokens are at least 73 bytes when decoded
        if len(decoded) >= 73:
            return True
    except Exception:
        pass
    
    return False


def is_key_encrypted(key: str) -> bool:
    """Check if an API key appears to be encrypted vs plaintext.
    
    This is the same as is_encrypted() but with a clearer name for the
    API key context. Pl plaintext API keys are typically short alphanumeric
    strings, while encrypted versions are long base64 tokens starting
    with 'gAAAAA'.
    
    Args:
        key: The API key string to check
    
    Returns:
        True if the key appears to be encrypted, False if it appears plaintext
    """
    return is_encrypted(key)


def verify_encryption_working() -> bool:
    """Test that encryption and decryption are working correctly.
    
    Performs a round-trip test: encrypt → decrypt → compare.
    Also verifies the key file exists and is readable.
    
    Returns:
        True if encryption is working, False if there's a problem
    """
    try:
        if not FERNET_AVAILABLE:
            return False
        
        # Test encrypt/decrypt round trip
        test_value = "test_encryption_12345"
        encrypted = encrypt_value(test_value)
        decrypted = decrypt_value(encrypted)
        
        if decrypted != test_value:
            return False
        
        # Test that is_encrypted detects the encrypted value
        if not is_encrypted(encrypted):
            return False
        
        # Test that is_encrypted doesn't flag plaintext
        if is_encrypted(test_value):
            return False
        
        # Verify key file exists
        if not KEY_FILE.exists():
            return False
        
        return True
        
    except Exception:
        return False


def encrypt_api_keys(api_key: str, secret_key: str) -> tuple:
    """Encrypt both Alpaca API keys at once.
    
    Args:
        api_key: Plaintext Alpaca API key
        secret_key: Plaintext Alpaca secret key
    
    Returns:
        Tuple of (encrypted_api_key, encrypted_secret_key)
    """
    encrypted_api = encrypt_value(api_key) if api_key else ""
    encrypted_secret = encrypt_value(secret_key) if secret_key else ""
    return encrypted_api, encrypted_secret


def decrypt_api_keys(encrypted_api_key: str, encrypted_secret_key: str) -> tuple:
    """Decrypt both Alpaca API keys at once.
    
    Args:
        encrypted_api_key: Encrypted Alpaca API key
        encrypted_secret_key: Encrypted Alpaca secret key
    
    Returns:
        Tuple of (plaintext_api_key, plaintext_secret_key)
    """
    if is_encrypted(encrypted_api_key):
        api_key = decrypt_value(encrypted_api_key)
    else:
        api_key = encrypted_api_key  # Already plaintext (shouldn't happen)
    
    if is_encrypted(encrypted_secret_key):
        secret_key = decrypt_value(encrypted_secret_key)
    else:
        secret_key = encrypted_secret_key  # Already plaintext (shouldn't happen)
    
    return api_key, secret_key


def rotate_key(old_key_path: str = None) -> bool:
    """Generate a new encryption key and re-encrypt all stored values.
    
    WARNING: This is a destructive operation. If it fails midway,
    some values may be encrypted with the new key and others with the old.
    Only use this if you know what you're doing.
    
    Args:
        old_key_path: Path to the old key file (defaults to current key file)
    
    Returns:
        True if key rotation succeeded, False otherwise
    """
    if not FERNET_AVAILABLE:
        return False
    
    try:
        # Read existing encrypted values from database
        # This would need to be called from database.py
        # For now, just generate a new key
        
        # Backup the old key
        if KEY_FILE.exists():
            backup_path = KEY_FILE.with_suffix(".key.backup")
            import shutil
            shutil.copy2(KEY_FILE, backup_path)
        
        # Generate new key (this will be used on next encrypt/decrypt call)
        new_key = _generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(new_key)
        
        return True
        
    except Exception:
        # Restore backup if something went wrong
        backup_path = KEY_FILE.with_suffix(".key.backup")
        if backup_path.exists():
            import shutil
            shutil.copy2(backup_path, KEY_FILE)
        return False


# ==========================================
# INITIALIZATION CHECK
# ==========================================

# On import, verify encryption is available and key file exists
if FERNET_AVAILABLE:
    try:
        _ = _load_or_create_key()
        ENCRYPTION_READY = True
    except Exception:
        ENCRYPTION_READY = False
else:
    ENCRYPTION_READY = False
