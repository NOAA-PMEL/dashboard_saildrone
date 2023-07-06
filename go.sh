# launch workes locally for bacground task testing.
celery -A app:celery_app worker --loglevel=DEBUG --concurrency=8 &
celery -A app:celery_app beat &
/app/.heroku/python/bin/python /workspace/app.py


