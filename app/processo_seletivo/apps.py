from djtools.apps import SuapAppConfig as AppConfig


class ProcessoSeletivoConfig(AppConfig):
    default = True
    name = 'processo_seletivo'
    verbose_name = 'Processos Seletivos'
    description = 'Gerencia os candidatos aprovados no processo seletivo e as filas de convocações.'
    icon = 'user-edit'
    area = 'Ensino'
