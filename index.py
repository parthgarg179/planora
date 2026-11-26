"""Vercel entry point. Vercel looks for a FastAPI `app` in index.py at the project root.
The real app lives in backend/app/main.py, so make `backend/` importable and re-export it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.main import app  # noqa: E402,F401
