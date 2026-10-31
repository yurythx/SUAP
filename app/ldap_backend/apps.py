from djtools.apps import SuapAppConfig as AppConfig


class LdapBackendConfig(AppConfig):
    default = True
    name = 'ldap_backend'
    verbose_name = 'LDAP Backend'
    description = 'Comunica-se com o Active Directory para autenticação com outros serviços oferecidos pela TI: Microsoft, Google, Acesso pasta da rede, acesso a computadores etc.'
    icon = 'server'
    area = 'Tecnologia da Informação'
