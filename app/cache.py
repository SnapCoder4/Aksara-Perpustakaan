"""Cache memori per proses untuk data yang jarang berubah (statistik beranda, daftar kategori).
Dikosongkan setiap ada request tulis (POST/PUT/DELETE) di instance ini, dan kedaluwarsa sendiri setelah TTL.
Di serverless tiap instance punya cache sendiri, jadi instance lain bisa menampilkan data lama maksimal TTL detik."""
import time

TTL = 30
_store: dict = {}


def cached(key: str, fn, ttl: int = TTL):
    hit = _store.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _store[key] = (time.monotonic(), value)
    return value


def clear():
    _store.clear()
