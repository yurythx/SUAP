from djtools.apps import SuapAppConfig as AppConfig


class CronConfig(AppConfig):
    default = True
    name = 'cron'
    verbose_name = 'CRON'
    area = 'Tecnologia da Informação'
