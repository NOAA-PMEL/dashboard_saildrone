worker-default: celery -A app worker --loglevel DEBUG --concurrency=12
worker-beat: celery -A app beat
web: gunicorn app:server --workers 10


