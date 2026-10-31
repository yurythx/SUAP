from django.conf import settings

__all__ = ['get_postgres_uri']


def get_postgres_uri():
    user = settings.DATABASES['default']['USER']
    password = settings.DATABASES['default']['PASSWORD']
    host = settings.DATABASES['default']['HOST']
    database_name = settings.DATABASES['default']['NAME']
    return f'postgresql://{user}:{password}@{host}/{database_name}'
