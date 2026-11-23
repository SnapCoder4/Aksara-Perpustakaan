"""Infrastruktur web bersama: template, session flash, dependency auth."""
import hashlib
from datetime import date
from functools import lru_cache
from urllib.parse import quote
from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.database import SessionLocal
from app.paths import STATIC_DIR, TEMPLATES_DIR

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    auto_reload=True,
)


def _tgl(value):
    try:
        d = date.fromisoformat(str(value)[:10])
        return f"{d.day} {BULAN[d.month - 1]} {d.year}"
    except (ValueError, TypeError):
        return value or "-"


env.filters["tgl"] = _tgl
env.filters["rupiah"] = lambda n: "Rp " + f"{int(n or 0):,}".replace(",", ".")
env.filters["angka"] = lambda n: f"{int(n or 0):,}".replace(",", ".")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Redirect(Exception):
    def __init__(self, url: str):
        self.url = url


def safe_next(url: str | None) -> str | None:
    """Hanya izinkan path internal (cegah open redirect)."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


def flash(request: Request, message: str, kind: str = "ok"):
    request.session.setdefault("flash", []).append({"m": message, "k": kind})


def render(request: Request, name: str, http_status: int = 200, **ctx) -> HTMLResponse:
    ctx.update(
        request=request,
        user=request.session.get("user"),
        flashes=request.session.pop("flash", []),
        path=request.url.path,
    )
    return HTMLResponse(env.get_template(name).render(**ctx), status_code=http_status)


def _need(request: Request, role: str):
    user = request.session.get("user")
    if not user or user.get("role") != role:
        nxt = quote(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        raise Redirect(f"/login?next={nxt}")
    return user


def require_admin(request: Request):
    return _need(request, "admin")


def require_member(request: Request):
    return _need(request, "member")


def url_with(request: Request, **kw) -> str:
    """URL halaman ini dengan query diubah (None = hapus parameter)."""
    from urllib.parse import urlencode
    q = dict(request.query_params)
    for k, v in kw.items():
        if v is None or v == "":
            q.pop(k, None)
        else:
            q[k] = v
    return request.url.path + ("?" + urlencode(q) if q else "")


env.globals["url_with"] = url_with


def _storage_globals():
    from app import hero, storage  # impor di sini: hindari impor melingkar
    env.globals["cover_url"] = lambda ref: storage.url("covers", ref)
    env.globals["cloud_mode"] = storage.enabled
    env.globals["hero_max_mb"] = lambda: hero.max_bytes() // (1024 * 1024)


_storage_globals()


@lru_cache(maxsize=None)
def asset(path: str) -> str:
    """URL /static/<path> dengan ?v=<hash isi file>: bisa di-cache selamanya, otomatis berganti saat file berubah."""
    try:
        v = hashlib.md5((STATIC_DIR / path).read_bytes()).hexdigest()[:8]
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={v}"


env.globals["asset"] = asset
