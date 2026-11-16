"""Bridge aiomysql's removed PyMySQL byte-escaping alias, without editing dependencies."""

import aiomysql.connection


def _escape_binary(value: bytes) -> str:
    # ASCII hex literals preserve every byte and do not depend on connection charset
    # or NO_BACKSLASH_ESCAPES. Never decode binary checkpoint payloads as text.
    return "_binary X'" + value.hex() + "'"


def ensure_binary_compatibility() -> bool:
    if callable(getattr(aiomysql.connection, "escape_bytes_prefixed", None)):
        return False
    aiomysql.connection.escape_bytes_prefixed = _escape_binary
    return True
