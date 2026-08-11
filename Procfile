release: python -m flask --app main db upgrade
web: gunicorn --workers 1 --worker-class gthread --threads 4 --bind 0.0.0.0:$PORT --timeout 120 main:app
