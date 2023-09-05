worker-default: celery -A tasks:celery_app worker --loglevel DEBUG --concurrency=1
worker-beat: celery -A tasks:celery_app beat
web: gunicorn app:server --workers 1


