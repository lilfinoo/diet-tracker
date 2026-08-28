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

## AI Agent Behavior
1. **Pensar antes de codificar** — Não assumir. Não esconder confusão. Apresentar tradeoffs. Antes de implementar: declarar suposições explicitamente. Se incerto, perguntar. Se múltiplas interpretações existirem, apresentar todas — não escolher silenciosamente. Se uma abordagem mais simples existir, dizer. Parar se algo estiver confuso e nomear o que é confuso.
2. **Simplicidade primeiro** — Código mínimo que resolve o problema. Nada especulativo. Sem funcionalidades além do pedido. Sem abstrações para código de uso único. Sem "flexibilidade" ou "configurabilidade" não solicitada. Sem tratamento de erros para cenários impossíveis. Se escreveu 200 linhas e poderia ser 50, reescrever.
3. **Mudanças cirúrgicas** — Mexer apenas no necessário. Não "melhorar" código adjacente, comentários ou formatação. Não refatorar o que não está quebrado. Manter estilo existente, mesmo que faria diferente. Quando as mudanças criam órfãos: remover imports/variáveis/funções que SUAS mudanças tornaram não utilizadas. Não remover código morto pré-existente sem ser pedido.
4. **Execução orientada a objetivo** — Definir critérios de sucesso. Rodar até verificar. Transformar tarefas em metas verificáveis. Para tarefas multi-etapa, declarar plano breve: 1. [Etapa] → verificar: [check]. Critérios fortes permitem loop independente; critérios fracos exigem constante clarificação.
