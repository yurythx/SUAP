def get_datetime_now():
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        from datetime import datetime

        return datetime.now()
