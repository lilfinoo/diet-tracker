#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 1. Cria a venv se ainda não existir
if [ ! -x ".venv/bin/python" ]; then
    echo "==> Criando ambiente virtual..."
    python3 -m venv .venv
fi

PY=".venv/bin/python"

# 2. Instala dependências se faltar alguma
if ! "$PY" -c "import flask, flask_sqlalchemy, flask_migrate" 2>/dev/null; then
    echo "==> Instalando dependências..."
    "$PY" -m pip install -r requirements.txt
fi

# 3. Aplica migrations no banco local
echo "==> Aplicando migrations..."
DATABASE_URL="sqlite:///diet_tracker.db" "$PY" -m flask --app main db upgrade

# 4. Sobe o servidor
echo "==> Servidor em http://localhost:8081"
exec "$PY" main.py
