"""
backend/utils/crypto.py
Fernet 对称加密工具，用于加密存储 CAS 密码和 LLM API Key。
Key 通过 settings.FERNET_KEY 注入，生产环境必须替换默认值。

使用方法：
    from backend.utils.crypto import encrypt, decrypt
    ciphertext: bytes = encrypt("my_secret_password")
    plaintext: str    = decrypt(ciphertext)
"""

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

# 延迟初始化，避免模块加载时 settings 未就绪
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FERNET_KEY.encode())
    return _fernet


def encrypt(plaintext: str) -> bytes:
    """
    加密明文字符串，返回加密字节串（可直接存入 LargeBinary 列）。

    Args:
        plaintext: 待加密的明文字符串

    Returns:
        Fernet 加密后的字节串
    """
    # TODO: return _get_fernet().encrypt(plaintext.encode("utf-8"))
    raise NotImplementedError


def decrypt(ciphertext: bytes) -> str:
    """
    解密字节串，返回原始明文字符串。

    Args:
        ciphertext: encrypt() 返回的字节串

    Returns:
        解密后的明文字符串

    Raises:
        InvalidToken: ciphertext 被篡改或 key 错误
    """
    # TODO: return _get_fernet().decrypt(ciphertext).decode("utf-8")
    raise NotImplementedError
