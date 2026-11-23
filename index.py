# Entrypoint Vercel: mengekspos aplikasi FastAPI. Tidak dipakai saat menjalankan lokal (uvicorn app.main:app).
from app.main import app  # noqa: F401
