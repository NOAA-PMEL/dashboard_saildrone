worker-default: celery -A app:celery_app worker --loglevel=DEBUG --concurrency=8
worker-beat: celery -A app:celery_app beat
worker-default: celery -A tasks worker --loglevel=DEBUG --concurrency=1
worker-beat: celery -A tasks beat
web: gunicorn app:server --workers 4


