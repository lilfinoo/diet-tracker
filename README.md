# Diet Tracker

Aplicação Flask com SPA estática para acompanhamento de dieta, medidas, planos e chat com IA.

Planos Premium são criados por questionários guiados. Treinos possuem divisões por dia e permitem substituir temporariamente um exercício durante uma sessão sem alterar o plano original.

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

O aplicativo exibe apenas correspondências revisadas. Exercícios sem mídia segura usam um placeholder neutro. Os créditos ficam disponíveis em **Perfil > Créditos das imagens** e em `copilot/assets/exercises/wger/manifest.json`.

As associações aprovadas e seus IDs exatos de imagem ficam em `scripts/wger-overrides.json`, evitando mudanças silenciosas quando a API for atualizada. Algumas mídias aprovadas são identificadas pelo wger como geradas por IA e recebem essa indicação nos créditos; use `--exclude-ai` para omiti-las. Para gerar candidatos em `scripts/wger-match-report.json` sem alterar as mídias publicadas, use `python scripts/import_wger_media.py --allow-automatic --dry-run` e revise o relatório antes de atualizar os overrides.

## Deploy (Render)

Defina as envs: `SECRET_KEY`, `DATABASE_URL`, `GEMINI_API_KEY`, `WORKOUTX_API_KEY`, `FLASK_ENV=production`, `SESSION_COOKIE_SECURE=true` e `CORS_ORIGINS` (domínio do site). No Render:

- **Start command**: `python -m flask --app main db upgrade && gunicorn --workers 1 --worker-class gthread --threads 4 --bind 0.0.0.0:$PORT --timeout 120 main:app` (equivalente ao `Procfile` e aplica migrations uma única vez antes do servidor).
- **Health check path**: `/api/health`.

## Segurança

Não use a URL de banco e a chave de sessão que existiam em versões anteriores. Elas devem ser rotacionadas. Nunca versione `.env`.
