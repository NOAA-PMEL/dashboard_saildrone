worker-default: celery -A app:celery_app worker --loglevel=DEBUG --concurrency=8
worker-beat: celery -A app:celery_app beat
web: gunicorn app:server --workers 4


