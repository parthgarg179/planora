"""Test setup: in-memory SQLite, fallback AI plan, fixed 'today'. Nothing touches your real database."""
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = ""          # forces the fallback plan, so tests never call Gemini
os.environ["SECRET_KEY"] = "test-secret"
os.environ["PLANORA_TODAY"] = ""
os.environ["REVIEW_LOOKBACK_DAYS"] = "3"
