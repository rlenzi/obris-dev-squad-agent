"""Geracao de IDs canonicos do sistema (UUIDv4 por enquanto)."""

import uuid


def new_id() -> uuid.UUID:
    return uuid.uuid4()
