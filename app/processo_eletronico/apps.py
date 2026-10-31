from django.db.models.signals import post_save, pre_save

from djtools.apps import SuapAppConfig as AppConfig
from processo_eletronico.signals import procotolo_eletronico_post_save, verifica_status_solicitacao_juntada


class ProcessoEletronicoConfig(AppConfig):
    default = True
    name = 'processo_eletronico'
    verbose_name = 'Processos Eletrônicos'
    area = 'Documentos e Processos Eletrônicos'

    def ready(self):
        # importing model classes
        Processo = self.get_model('Processo')
        # registering signals with the model's string label
        post_save.connect(procotolo_eletronico_post_save, sender=Processo)
        SolicitacaoJuntadaDocumento = self.get_model('SolicitacaoJuntadaDocumento')
        pre_save.connect(verifica_status_solicitacao_juntada, sender=SolicitacaoJuntadaDocumento)
