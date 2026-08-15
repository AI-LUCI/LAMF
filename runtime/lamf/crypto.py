"""LAMF instance key + export bundle encryption (DECISIONS.md §M, §U-13).

InstanceKey
    Ed25519 signing identity of the instance (created at `lamf init`, private
    part in a 0600 file, NEVER exported — U-13a). Also provides the X25519
    wrapping counterpart used by store.py to wrap per-record data keys
    (U-13a: "Ed25519 signing + X25519/symmetric wrapping counterpart").

export_encrypt / export_decrypt
    Passphrase-based bundle encryption (floor F3, §M.1):
    XChaCha20-Poly1305; key = Argon2id(passphrase, salt, m=64 MiB, t=3).
    Container:  magic b'LAMF1' || salt(16) || nonce(24) || ciphertext.

    DEVIATION (documented): DECISIONS.md §M.1 pins Argon2id p=4, but the
    runtime dependency set is pinned to pynacl only (W-02) and libsodium's
    crypto_pwhash API hard-codes parallelism = 1. opslimit=3 (t) and
    memlimit=64 MiB (m) are exactly as pinned; p=1 is a libsodium constant,
    identical on encrypt and decrypt, so the format is self-consistent.
    Cross-implementation parity with a future p=4 KDF would require a format
    version bump.

Pinned interface (runtime/README.md):
    class InstanceKey with .generate(path), .load(path), .sign(data) -> bytes,
        .verify(data, sig) -> bool, .pub_hex -> str
    export_encrypt(passphrase: str, blob: bytes) -> bytes
    export_decrypt(passphrase: str, blob: bytes) -> bytes
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import stat
from pathlib import Path

import nacl.bindings
import nacl.exceptions
import nacl.pwhash
import nacl.signing

# Export container constants (§M.1 / U-13)
EXPORT_MAGIC = b"LAMF1"
_ARGON2_OPSLIMIT = 3                     # t = 3
_ARGON2_MEMLIMIT = 64 * 1024 * 1024      # m = 64 MiB
_SALTBYTES = nacl.pwhash.argon2id.SALTBYTES                     # 16
_NONCEBYTES = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES  # 24
_KEYBYTES = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES     # 32


class InstanceKey:
    """Ed25519 instance identity; private seed in a 0600 file (U-13a).

    File format: 32 raw seed bytes, mode 0600. The X25519 wrapping
    counterpart (for envelope encryption of per-record data keys) is derived
    from the same key material via libsodium's Ed25519->X25519 conversion.
    """

    def __init__(self, signing_key: nacl.signing.SigningKey):
        self._sk = signing_key

    # -- lifecycle ---------------------------------------------------------
    @classmethod
    def generate(cls, path) -> "InstanceKey":
        """Create a fresh instance key, write the seed to `path` (0600), and
        return the key. Refuses to overwrite an existing key."""
        path = Path(path)
        if path.exists():
            raise FileExistsError(f"instance key already exists: {path}")
        sk = nacl.signing.SigningKey.generate()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Windows CRT text mode can expand a random 0x0a seed byte to 0x0d0a,
        # corrupting the fixed 32-byte Ed25519 seed.  O_BINARY is zero/absent
        # on POSIX and mandatory for raw key material on Windows.
        binary = getattr(os, "O_BINARY", 0)
        fd = os.open(
            str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | binary, 0o600)
        try:
            os.write(fd, bytes(sk))
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
        return cls(sk)

    @classmethod
    def load(cls, path) -> "InstanceKey":
        """Load an existing instance key from `path`."""
        path = Path(path)
        raw = path.read_bytes()
        if len(raw) != 32:
            raise ValueError(f"corrupt instance key file {path}: {len(raw)} bytes, want 32")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            try:
                os.chmod(path, 0o600)  # tighten silently where POSIX modes apply
            except PermissionError:
                # Windows ACLs, managed sandboxes, and mounted Windows drives
                # may reject chmod even when the caller can securely read the
                # key. Access control remains the host filesystem's job.
                if os.name != "nt":
                    raise
        return cls(nacl.signing.SigningKey(raw))

    # -- signing -----------------------------------------------------------
    def sign(self, data: bytes) -> bytes:
        """Ed25519 signature over `data` (raw 64 bytes). PINNED."""
        return self._sk.sign(data).signature

    def verify(self, data: bytes, sig: bytes) -> bool:
        """Verify an Ed25519 signature; returns False (never raises) on
        malformed input. PINNED."""
        try:
            self._sk.verify_key.verify(data, sig)
            return True
        except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
            return False

    @property
    def pub_hex(self) -> str:
        """Lowercase hex of the 32-byte Ed25519 public key. PINNED."""
        return bytes(self._sk.verify_key).hex()

    @property
    def pub_b64url(self) -> str:
        """base64url (RFC 4648 §5, padded) public key, for instance_identity."""
        return base64.urlsafe_b64encode(bytes(self._sk.verify_key)).decode("ascii")

    def fingerprint(self) -> str:
        """Short display fingerprint for out-of-band confirmation (§H/U-13d):
        first8…last4 of the pubkey hex."""
        h = self.pub_hex
        return f"{h[:8]}…{h[-4:]}"

    def derive_key(self, purpose: str, length: int = 32) -> bytes:
        """Derive an instance-local subkey without exposing identity material.

        Protocol 3 uses this for keyed blind search indexes.  Purpose labels
        are domain-separated and the signing seed never leaves this object.
        """
        if not purpose or length < 16 or length > 32:
            raise ValueError("purpose is required and length must be 16..32")
        return hmac.new(bytes(self._sk),
                        b"LAMF3\x00" + purpose.encode("utf-8"),
                        hashlib.sha256).digest()[:length]

    # -- X25519 wrapping counterpart (U-13a) --------------------------------
    def _x25519_sk(self) -> bytes:
        seed = bytes(self._sk)
        sk64 = seed + bytes(self._sk.verify_key)
        return nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(sk64)

    def wrap_key(self, data_key: bytes) -> bytes:
        """Wrap (seal) a per-record data key to this instance's X25519 public
        key (anonymous sealed box)."""
        xpk = nacl.bindings.crypto_scalarmult_base(self._x25519_sk())
        return nacl.bindings.crypto_box_seal(data_key, xpk)

    def unwrap_key(self, wrapped: bytes) -> bytes:
        """Unwrap a sealed per-record data key."""
        xsk = self._x25519_sk()
        xpk = nacl.bindings.crypto_scalarmult_base(xsk)
        return nacl.bindings.crypto_box_seal_open(wrapped, xpk, xsk)


def _derive_export_key(passphrase: str, salt: bytes) -> bytes:
    return nacl.pwhash.argon2id.kdf(
        _KEYBYTES,
        passphrase.encode("utf-8"),
        salt,
        opslimit=_ARGON2_OPSLIMIT,
        memlimit=_ARGON2_MEMLIMIT,
    )


def export_encrypt(passphrase: str, blob: bytes) -> bytes:
    """Encrypt a bundle with a passphrase (floor F3). PINNED SIGNATURE.

    Format: b'LAMF1' || salt(16) || nonce(24) || XChaCha20-Poly1305(blob).
    """
    if not passphrase:
        raise ValueError("export passphrase is mandatory (floor F3)")
    salt = os.urandom(_SALTBYTES)
    nonce = os.urandom(_NONCEBYTES)
    key = _derive_export_key(passphrase, salt)
    ct = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(blob, None, nonce, key)
    return EXPORT_MAGIC + salt + nonce + ct


def export_decrypt(passphrase: str, blob: bytes) -> bytes:
    """Decrypt a bundle produced by export_encrypt. PINNED SIGNATURE.

    Raises ValueError on a bad container or wrong passphrase (fail closed).
    """
    if not blob.startswith(EXPORT_MAGIC):
        raise ValueError("not a LAMF export container (bad magic)")
    off = len(EXPORT_MAGIC)
    salt = blob[off : off + _SALTBYTES]
    off += _SALTBYTES
    nonce = blob[off : off + _NONCEBYTES]
    off += _NONCEBYTES
    ct = blob[off:]
    if len(salt) != _SALTBYTES or len(nonce) != _NONCEBYTES or not ct:
        raise ValueError("truncated LAMF export container")
    key = _derive_export_key(passphrase, salt)
    try:
        return nacl.bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(ct, None, nonce, key)
    except nacl.exceptions.CryptoError as e:
        raise ValueError("export decryption failed (wrong passphrase or tampered bundle)") from e
