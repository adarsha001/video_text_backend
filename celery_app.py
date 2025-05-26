from celery import Celery
import os
app = Celery(
    'backend',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0',
    broker_connection_retry_on_startup=True
)


# Add these essential settings

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)