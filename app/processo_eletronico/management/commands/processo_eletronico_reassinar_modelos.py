from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import Assinatura
from documento_eletronico.utils import EstagioProcessamentoVariavel, get_variaveis, processar_template_ckeditor
from processo_eletronico.models import (
    AssinaturaTramite,
    ModeloDespacho,
    Tramite,
    gerar_assinatura_tramite_senha,
)


class Command(BaseCommandPlus):
    """
    Command criado para reassinar os depachos devido a um erro ao processamento
    das variáveis
    """

    def handle(self, *args, **options):
        self.reassinar_despachos()

    def reassinar_despachos(self) -> None:
        for tramite in Tramite.objects.all():
            sid = transaction.savepoint()
            try:
                # Removendo assinatura
                modelo = ModeloDespacho.get_modelo()
                assinatura_tramite_antiga = AssinaturaTramite.objects.filter(tramite=tramite).first()

                hash_antigo = tramite.hash_conteudo

                variaveis = get_variaveis(
                    documento_identificador='',
                    estagio_processamento_variavel=EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
                    usuario=tramite.remetente_vinculo.user,
                )
                tramite.cabecalho_observacao_encaminhamento = processar_template_ckeditor(texto=modelo.cabecalho, variaveis=variaveis)
                tramite.rodape_observacao_encaminhamento = processar_template_ckeditor(texto=modelo.rodape, variaveis=variaveis)

                if hash_antigo == tramite.hash_conteudo:
                    self.stdout.write(f'Tramite {tramite} já processado ')
                    continue

                # Assinando encaminhamento
                assinatura = Assinatura()
                assinatura.pessoa = assinatura_tramite_antiga.assinatura.pessoa
                assinatura.papel = assinatura_tramite_antiga.assinatura.papel
                assinatura.nome_papel = assinatura_tramite_antiga.assinatura.nome_papel
                assinatura.hmac = gerar_assinatura_tramite_senha(tramite, tramite.remetente_vinculo)

                #
                self.stdout.write(f'Removendo assinatura {assinatura_tramite_antiga}')
                assinatura_tramite_antiga.delete()

                tramite.save()
                assinatura.save()
                #
                assinatura_tramite = AssinaturaTramite()
                assinatura_tramite.tramite = tramite
                assinatura_tramite.assinatura = assinatura
                assinatura_tramite.save()
                self.stdout.write(f'Criando {assinatura_tramite}')
                transaction.savepoint_commit(sid)
            except Exception:
                transaction.savepoint_rollback(sid)
                raise
