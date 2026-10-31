from djtools.apps import SuapAppConfig as AppConfig


class EnccejaConfig(AppConfig):
    default = True
    name = 'encceja'
    verbose_name = 'ENCCEJA'
    area = 'Ensino'
    description = 'Realiza a emissão de Certificados ENCCEJA, exame aplicado pelo governo federal que oferece a jovens e adultos que não concluíram seus estudos a oportunidade de conseguir o certificado do ensino fundamental ou do ensino médio.'
    icon = 'user-graduate'
