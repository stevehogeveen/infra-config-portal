"""SHA-512 crypt ("$6$"), the password hash ESXi's kickstart `rootpw --iscrypted` expects.

Python's `crypt` module is missing on Windows (and removed in Python 3.13), so this implements the
published algorithm (Ulrich Drepper, "Unix crypt using SHA-256 and SHA-512") directly.
"""

from __future__ import annotations

import hashlib
import secrets

ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ROUNDS_DEFAULT = 5000


def _b64(data: bytes) -> str:
    order = [(0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26), (6, 27, 48),
             (28, 49, 7), (50, 8, 29), (9, 30, 51), (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13),
             (56, 14, 35), (15, 36, 57), (37, 58, 16), (59, 17, 38), (18, 39, 60), (40, 61, 19), (62, 20, 41)]
    out = []
    for a, b, c in order:
        value = (data[a] << 16) | (data[b] << 8) | data[c]
        for _ in range(4):
            out.append(ALPHABET[value & 0x3F])
            value >>= 6
    value = data[63]
    for _ in range(2):
        out.append(ALPHABET[value & 0x3F])
        value >>= 6
    return "".join(out)


def sha512_crypt(password: str, salt: str | None = None, rounds: int | None = None) -> str:
    key = password.encode("utf-8")
    salt = (salt if salt is not None else "".join(secrets.choice(ALPHABET) for _ in range(16)))[:16]
    salt_bytes = salt.encode("ascii")
    count = ROUNDS_DEFAULT if rounds is None else min(max(rounds, 1000), 999_999_999)

    b = hashlib.sha512(key + salt_bytes + key).digest()
    a = hashlib.sha512(key + salt_bytes)
    for i in range(len(key) // 64):
        a.update(b)
    a.update(b[: len(key) % 64])
    length = len(key)
    while length:
        a.update(b if length & 1 else key)
        length >>= 1
    a_digest = a.digest()

    dp = hashlib.sha512(key * len(key)).digest()
    p = dp * (len(key) // 64) + dp[: len(key) % 64]
    ds = hashlib.sha512(salt_bytes * (16 + a_digest[0])).digest()
    s = ds * (len(salt_bytes) // 64) + ds[: len(salt_bytes) % 64]

    c = a_digest
    for i in range(count):
        step = hashlib.sha512()
        step.update(p if i & 1 else c)
        if i % 3:
            step.update(s)
        if i % 7:
            step.update(p)
        step.update(c if i & 1 else p)
        c = step.digest()

    prefix = "$6$" if rounds is None else f"$6$rounds={count}$"
    return f"{prefix}{salt}${_b64(c)}"
