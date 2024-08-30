workers: celery -A app:celery_app worker --loglevel DEBUG --concurrency=1
worker-beat: celery -A app:celery_app beat
web: gunicorn app:server --workers 1
