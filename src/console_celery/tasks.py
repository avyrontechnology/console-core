from .celery_app import celery


# A simple task
@celery.task
def add_numbers(x: int, y: int) -> int:
    result = x + y
    return result
