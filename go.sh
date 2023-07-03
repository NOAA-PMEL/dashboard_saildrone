celery -A app:celery_app worker --loglevel=DEBUG --concurrency=8
celery -A app:celery_app beat


