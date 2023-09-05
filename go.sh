#!/bin/sh
# launch workes locally for background task testing.
celery -A app:celery_app worker --loglevel=DEBUG --concurrency=12 --without-gossip &
celery -A app:celery_app beat &
/app/.heroku/python/bin/python /workspace/app.py


