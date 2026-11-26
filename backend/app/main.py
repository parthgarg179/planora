"""Planora API.

Run from the backend folder:   uvicorn app.main:app --reload
Then open http://localhost:8000  (the website)   or   http://localhost:8000/docs  (API explorer)
"""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .ml import predictor
from .routers import auth, goals, notifications, tasks, users

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("planora")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.secret_key == "change-me":
        log.warning("SECRET_KEY is still 'change-me'. Set a real one in backend/.env.")
    if not settings.gemini_api_key:
        log.warning("GEMINI_API_KEY is not set, so new goals will use the generic fallback plan.")
    init_db()
    # Load the ML duration model in the background now, so the first page that needs it
    # (e.g. Progress) doesn't wait for scikit-learn to load. Startup isn't delayed.
    threading.Thread(target=predictor.load_model, name="preload-model", daemon=True).start()
    yield


app = FastAPI(title="Planora API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def readable_validation_error(_: Request, exc: RequestValidationError):
    """Turn pydantic's error list into one sentence the frontend can show."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    message = str(first.get("msg", "Invalid request")).removeprefix("Value error, ")
    return JSONResponse(status_code=422, content={"detail": f"{field}: {message}"})


@app.middleware("http")
async def always_fresh_frontend(request: Request, call_next):
    """Make browsers re-check the website's files on every load, so they never run an old
    cached copy of the JavaScript. Unchanged files still come back as a quick 304."""
    response = await call_next(request)
    if request.url.path.startswith("/app"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}


for r in (auth.router, users.router, goals.router, tasks.router, notifications.router):
    app.include_router(r)

# Serve the website from the same server: http://localhost:8000/app/
frontend = Path(settings.frontend_dir)
if frontend.is_dir():
    app.mount("/app", StaticFiles(directory=frontend, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/")
else:
    log.warning("Frontend folder not found at %s, so only the API is served.", frontend)
