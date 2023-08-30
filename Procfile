worker-tasks-background: celery -A app:celery_app worker --loglevel=DEBUG --concurrency=12
worker-beat: celery -A app:celery_app beat
web: gunicorn app:server --workers 4


