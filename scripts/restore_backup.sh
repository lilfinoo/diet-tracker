#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Uso: RESTORE_CONFIRM=RESTORE ./scripts/restore_backup.sh backup.dump postgresql://usuario:senha@host:5432/banco" >&2
  exit 2
fi

if [ "${RESTORE_CONFIRM:-}" != "RESTORE" ]; then
  echo "Restauração cancelada. Defina RESTORE_CONFIRM=RESTORE para confirmar a substituição do banco de destino." >&2
  exit 2
fi

backup_file="$1"
target_database_url="$2"

if [ ! -f "$backup_file" ]; then
  echo "Backup não encontrado: $backup_file" >&2
  exit 2
fi

pg_restore --list "$backup_file" >/dev/null
pg_restore \
  --clean \
  --if-exists \
  --exit-on-error \
  --no-owner \
  --no-acl \
  --dbname="$target_database_url" \
  "$backup_file"

psql "$target_database_url" --set=ON_ERROR_STOP=1 --command="SELECT version_num FROM alembic_version;"
echo "Restauração concluída e schema Alembic validado."
