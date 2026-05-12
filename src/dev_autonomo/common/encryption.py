"""Wrapper Fernet para encrypt-at-rest de segredos no banco."""

from cryptography.fernet import Fernet, InvalidToken

from dev_autonomo.config import get_settings


class SecretEncryptor:
    """Encryptador simetrico baseado em Fernet (AES-128-CBC + HMAC)."""

    def __init__(self, master_key: bytes | None = None) -> None:
        if master_key is None:
            settings = get_settings()
            if not settings.MASTER_ENCRYPTION_KEY:
                raise RuntimeError(
                    "MASTER_ENCRYPTION_KEY ausente no .env. "
                    "Gere com SecretEncryptor.generate_master_key()."
                )
            master_key = settings.MASTER_ENCRYPTION_KEY.get_secret_value().encode()
        self._fernet = Fernet(master_key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as exc:
            raise RuntimeError(
                "Ciphertext invalido ou MASTER_ENCRYPTION_KEY rotacionada."
            ) from exc

    @staticmethod
    def generate_master_key() -> str:
        return Fernet.generate_key().decode()
