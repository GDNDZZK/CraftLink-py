import base64
import hashlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

BLOCK = AES.block_size
IV = bytes(BLOCK)
PBKDF2_SALT = b"CraftLink.Key.Salt.v1"
PBKDF2_ITERATIONS = 100000


def derive_key(token: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", token.encode("utf-8"), PBKDF2_SALT, PBKDF2_ITERATIONS, dklen=32
    )


def encrypt(key: bytes, text: str) -> str:
    cipher = AES.new(key, AES.MODE_CBC, IV)
    return base64.b64encode(cipher.encrypt(pad(text.encode("utf-8"), BLOCK))).decode("utf-8")


def decrypt(key: bytes, text: str) -> str:
    cipher = AES.new(key, AES.MODE_CBC, IV)
    return unpad(cipher.decrypt(base64.b64decode(text)), BLOCK).decode("utf-8")
