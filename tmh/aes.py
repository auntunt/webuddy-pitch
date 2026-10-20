"""AES-CBC in pure Python, for the encrypted callbacks of Feishu and WeCom.

The harness has no third-party dependencies (it has to install on intranet
machines with only a Python interpreter), so the block cipher is written out
here. Messages are a few kilobytes, so speed does not matter. Checked against
the `cryptography` package in the tests' reference vectors.
"""
from __future__ import annotations


def _xt(a: int) -> int:
    a <<= 1
    return (a ^ 0x11B) if a & 0x100 else a


def _mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a, b = _xt(a), b >> 1
    return r


def _sbox():
    inv = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if _mul(a, b) == 1:
                inv[a] = b
                break
    s = []
    for x in range(256):
        b, r = inv[x], inv[x]
        for _ in range(4):
            b = ((b << 1) | (b >> 7)) & 0xFF
            r ^= b
        s.append(r ^ 0x63)
    return s


SBOX = _sbox()
INV = [0] * 256
for _i, _v in enumerate(SBOX):
    INV[_v] = _i
# multiplication tables for MixColumns / InvMixColumns
M2, M3, M9, M11, M13, M14 = ([_mul(x, k) for x in range(256)] for k in (2, 3, 9, 11, 13, 14))


def _expand(key: bytes) -> list[list[int]]:
    nk = len(key) // 4
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [SBOX[x] for x in t]
            t[0] ^= rcon
            rcon = _xt(rcon) & 0xFF
        elif nk > 6 and i % nk == 4:
            t = [SBOX[x] for x in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)]


class AES:
    def __init__(self, key: bytes):
        self.rk = _expand(key)
        self.nr = len(self.rk) - 1

    def encrypt_block(self, b: bytes) -> bytes:
        s = [x ^ k for x, k in zip(b, self.rk[0])]
        for r in range(1, self.nr + 1):
            s = [SBOX[x] for x in s]
            s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]  # ShiftRows (column-major state)
            if r != self.nr:
                t = []
                for c in range(4):
                    a0, a1, a2, a3 = s[4 * c:4 * c + 4]
                    t += [M2[a0] ^ M3[a1] ^ a2 ^ a3, a0 ^ M2[a1] ^ M3[a2] ^ a3,
                          a0 ^ a1 ^ M2[a2] ^ M3[a3], M3[a0] ^ a1 ^ a2 ^ M2[a3]]
                s = t
            s = [x ^ k for x, k in zip(s, self.rk[r])]
        return bytes(s)

    def decrypt_block(self, b: bytes) -> bytes:
        s = [x ^ k for x, k in zip(b, self.rk[self.nr])]
        for r in range(self.nr - 1, -1, -1):
            s = [s[(i - 4 * (i % 4)) % 16] for i in range(16)]  # InvShiftRows
            s = [INV[x] for x in s]
            s = [x ^ k for x, k in zip(s, self.rk[r])]
            if r:
                t = []
                for c in range(4):
                    a0, a1, a2, a3 = s[4 * c:4 * c + 4]
                    t += [M14[a0] ^ M11[a1] ^ M13[a2] ^ M9[a3], M9[a0] ^ M14[a1] ^ M11[a2] ^ M13[a3],
                          M13[a0] ^ M9[a1] ^ M14[a2] ^ M11[a3], M11[a0] ^ M13[a1] ^ M9[a2] ^ M14[a3]]
                s = t
        return bytes(s)


def cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("data must be padded to 16 bytes")
    a, prev, out = AES(key), iv, []
    for i in range(0, len(data), 16):
        prev = a.encrypt_block(bytes(x ^ y for x, y in zip(data[i:i + 16], prev)))
        out.append(prev)
    return b"".join(out)


def cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("ciphertext is not a whole number of blocks")
    a, prev, out = AES(key), iv, []
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        out.append(bytes(x ^ y for x, y in zip(a.decrypt_block(blk), prev)))
        prev = blk
    return b"".join(out)


def pad(data: bytes, block: int = 16) -> bytes:
    n = block - len(data) % block
    return data + bytes([n]) * n


def unpad(data: bytes, block: int = 16) -> bytes:
    n = data[-1] if data else 0
    if not 1 <= n <= block or data[-n:] != bytes([n]) * n:
        raise ValueError("bad padding")
    return data[:-n]
