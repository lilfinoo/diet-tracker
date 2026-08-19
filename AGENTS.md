# Diet Tracker

## Structure
- `main.py` is the Flask entrypoint. It registers `src/routes/user_routes.py` at `/api` and serves the SPA and assets directly from `copilot/` (including the `/admin` page).
- `src/models/user.py` owns the shared Flask-SQLAlchemy `db` instance and all application models. User primary keys are UUIDs (`UUIDType`), not integers.
- The browser client is plain HTML/CSS/JS in `copilot/`; its API base is `/api` and session-authenticated requests must retain `credentials: 'include'`.

## Run And Verify
- Install dependencies with `python -m pip install -r requirements.txt`; create a fresh virtual environment instead of reusing local artifacts.
- `DATABASE_URL` falls back to a local SQLite file (`diet_tracker.db`); set it explicitly for real environments. Schema comes from Alembic migrations (`flask db upgrade`), not `db.create_all()`.
- Run locally with `python main.py` (debug server on port 8081); production runs `gunicorn main:app` per `Procfile` (binds `$PORT`, 1 gthread worker keeping the in-memory rate limiter coherent).
- Verification: `python3 -m py_compile main.py src/models/user.py src/routes/user_routes.py`, `ruff check .`, and `pytest` (see `tests/` and `.github/workflows/ci.yml`).

## Database And Integrations
- Apply migrations with `DATABASE_URL=... python -m flask --app main db upgrade`; generate schema migrations with `DATABASE_URL=... python -m flask --app main db migrate -m "description"`. Keep `migrations/versions/` in sync with model changes.
- AI endpoints use `google-genai` with Gemini and require `GEMINI_API_KEY`; keep calls isolated in `src/services/ai.py`.
- `copilot/minha-pasta/alimentos.json` is loaded by the client at the relative path `minha-pasta/alimentos.json`; preserve that location when changing static assets.

## Repository Hygiene
- `venv/` and `__pycache__/` are local environment/cache artifacts. Do not commit or modify them.
- Deploy (Render): the `web` process applies `flask db upgrade` before starting gunicorn bound to `$PORT`. Healthcheck: `GET /api/health`.
