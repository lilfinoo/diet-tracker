web: python -m flask --app main db upgrade && gunicorn --workers ${WEB_CONCURRENCY:-1} --worker-class gthread --threads ${GUNICORN_THREADS:-8} --bind 0.0.0.0:$PORT --timeout 120 main:app
worker: python -m celery -A main:celery_app worker --loglevel=INFO --concurrency=2
