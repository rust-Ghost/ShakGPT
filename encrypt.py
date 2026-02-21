"""
encrypt.py — Application-layer encryption (Fernet / AES-128-CBC + HMAC-SHA256)

Replaces the old trivially-broken XOR cipher.

How it works
────────────
• Fernet is a symmetric authenticated encryption scheme from the `cryptography`
  package.  It uses AES-128 in CBC mode for confidentiality, HMAC-SHA256 for
  integrity, and a cryptographically-random IV for every message.
• The key is a 32-byte secret shared out-of-band (e.g. from crypto_key.py or
  negotiated via the SSL/TLS handshake).
• Every encrypted payload includes a timestamp; messages older than
  MAX_AGE_SECONDS are rejected, preventing replay attacks.

Install once:
    pip install cryptography
"""

import struct
from cryptography.fernet import Fernet, InvalidToken

# Reject any message whose embedded timestamp is older than this.
MAX_AGE_SECONDS = 300  # 5 minutes


class Encryption:
    """
    Drop-in replacement for the old XOR-based Encryption class.

    Usage
    ─────
    key = Fernet.generate_key()          # 32 url-safe base64-encoded bytes
    enc = Encryption(key)

    # Sending
    enc.send_encrypted_message(sock, "hello world")

    # Receiving
    plaintext = enc.receive_encrypted_message(sock)
    """

    def __init__(self, key: bytes):
        """
        Parameters
        ----------
        key : bytes
            A valid Fernet key — 32 url-safe base64-encoded bytes.
            Generate with:  from cryptography.fernet import Fernet; Fernet.generate_key()
        """
        self._fernet = Fernet(key)

    # ─────────────────────────────────────────────────────────────
    #  Public API  (same surface as the old XOR class)
    # ─────────────────────────────────────────────────────────────

    def send_encrypted_message(self, sock, message: str) -> None:
        """Encrypt *message*, frame it with a 4-byte length prefix, send it."""
        token = self._fernet.encrypt(message.encode("utf-8"))
        # 4-byte big-endian length prefix so the receiver knows exactly how
        # many bytes to read (identical framing used by _send/_recv elsewhere).
        sock.sendall(struct.pack(">I", len(token)) + token)

    def receive_encrypted_message(self, sock, buffer_size: int = 4096) -> str:
        """
        Read a length-prefixed Fernet token from *sock* and return the
        decrypted plaintext.  Returns "" on connection close or decryption
        failure.
        """
        try:
            header = _recv_exact(sock, 4)
            if not header:
                return ""
            n = struct.unpack(">I", header)[0]
            if n > 10 * 1024 * 1024:          # sanity: refuse >10 MB tokens
                return ""
            token = _recv_exact(sock, n)
            if not token:
                return ""
            return self._decrypt(token)
        except (OSError, struct.error):
            return ""

    # ─────────────────────────────────────────────────────────────
    #  Convenience helpers (raw bytes, no socket I/O)
    # ─────────────────────────────────────────────────────────────

    def encrypt_bytes(self, plaintext: bytes) -> bytes:
        """Return raw Fernet token for *plaintext*."""
        return self._fernet.encrypt(plaintext)

    def decrypt_bytes(self, token: bytes) -> bytes:
        """Decrypt *token* and return plaintext bytes, or b"" on failure."""
        try:
            return self._fernet.decrypt(token, ttl=MAX_AGE_SECONDS)
        except InvalidToken:
            return b""

    def encrypt_str(self, plaintext: str) -> str:
        """Return Fernet token as a UTF-8 string (url-safe base64)."""
        return self.encrypt_bytes(plaintext.encode()).decode()

    def decrypt_str(self, token: str) -> str:
        """Decrypt a string token; return "" on failure."""
        raw = self.decrypt_bytes(token.encode())
        return raw.decode("utf-8") if raw else ""

    # ─────────────────────────────────────────────────────────────
    #  Internal
    # ─────────────────────────────────────────────────────────────

    def _decrypt(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token, ttl=MAX_AGE_SECONDS).decode("utf-8")
        except InvalidToken:
            print("[WARN] encrypt.py: Invalid or expired token — message dropped")
            return ""


# ─────────────────────────────────────────────────────────────────
#  Helper: recv exactly n bytes
# ─────────────────────────────────────────────────────────────────

def _recv_exact(sock, n: int) -> bytes:
    """Read exactly *n* bytes from *sock*; return b"" if the connection closes."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return b""
        buf += chunk
    return buf


# ─────────────────────────────────────────────────────────────────
#  Key utilities
# ─────────────────────────────────────────────────────────────────

def generate_key() -> bytes:
    """Generate a fresh Fernet key."""
    return Fernet.generate_key()


def key_from_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """
    Derive a Fernet key from a human-readable password using PBKDF2-HMAC-SHA256.

    Returns (key, salt) — store the salt alongside the key so you can
    reproduce the same key for decryption.

    Example
    ───────
    key, salt = key_from_password("my-secret-passphrase")
    enc = Encryption(key)
    ...
    # later, to recreate the key:
    key, _ = key_from_password("my-secret-passphrase", salt=salt)
    """
    import os, base64, hashlib
    if salt is None:
        salt = os.urandom(16)
    raw = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
    key = base64.urlsafe_b64encode(raw)
    return key, salt