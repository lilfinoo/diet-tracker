# Diet Tracker

Aplicação Flask com SPA estática para acompanhamento de dieta, medidas, planos e chat com IA.

Planos Premium são criados por questionários guiados. Treinos possuem divisões por dia e permitem substituir temporariamente um exercício durante uma sessão sem alterar o plano original. A rede interna permite perfil público opcional, vínculo consentido entre aluno e profissional, acompanhamento alimentar diário e revisão versionada de planos sem sobrescrever o original.

## Ambiente local

1. Crie um ambiente virtual e instale `python -m pip install -r requirements-dev.txt`.
2. Copie `.env.example` para `.env` e defina `SECRET_KEY`. Configure `DATABASE_URL` para PostgreSQL quando necessário.
3. Aplique o schema com `DATABASE_URL=... python -m flask --app main db upgrade`.
4. Execute `python main.py`.

O fallback local é SQLite em `diet_tracker.db`; produção exige `SECRET_KEY` e `DATABASE_URL`.

## Verificação

```sh
ruff check .
pytest
```

## Imagens de exercícios

As imagens são importadas da API pública do [wger](https://wger.de/) e servidas localmente. Para atualizar a seleção e regenerar o manifesto de autoria e licenças, execute:

```sh
python scripts/import_wger_media.py
```

O aplicativo exibe apenas correspondências revisadas. Exercícios sem mídia segura usam um placeholder neutro. Origem, autoria e licença permanecem registradas em `copilot/assets/exercises/wger/manifest.json`.

As associações aprovadas e seus IDs exatos de imagem ficam em `scripts/wger-overrides.json`, evitando mudanças silenciosas quando a API for atualizada. Algumas mídias aprovadas são identificadas pelo wger como geradas por IA nos metadados; use `--exclude-ai` para omiti-las. Para gerar candidatos em `scripts/wger-match-report.json` sem alterar as mídias publicadas, use `python scripts/import_wger_media.py --allow-automatic --dry-run` e revise o relatório antes de atualizar os overrides.

## Deploy (Render)

Defina as envs: `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`, `WORKOUTX_API_KEY`, `SESSION_COOKIE_SECURE=true`, `CORS_ORIGINS`, `METRICS_ENABLED=true`, `METRICS_TOKEN` e as quatro variáveis `MEDIA_R2_*`. No Render:

- **Start command**: use o `Procfile`, que aplica migrations e aceita `WEB_CONCURRENCY`/`GUNICORN_THREADS`. Mantenha `WEB_CONCURRENCY=1` enquanto as métricas Prometheus não estiverem em modo multiprocess e ajuste threads/pool somente após teste de carga.
- **Health check path**: `/api/health`.
- **Background Worker**: `python -m celery -A main:celery_app worker --loglevel=INFO --concurrency=2`.

Redis, fila de IA, métricas, Grafana Cloud, Asaas e backups estão detalhados em [`OPERATIONS.md`](OPERATIONS.md).

## Segurança

Não use a URL de banco e a chave de sessão que existiam em versões anteriores. Elas devem ser rotacionadas. Nunca versione `.env`.
