import datetime

import tqdm
from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_mail, send_notification
from rsc.models import ProcessoAvaliador, ProcessoRSC, ConfiguracaoRSC
from rh import utils


class Command(BaseCommandPlus):
    def seleciona_avaliador(self, tipo_avaliador, processo):
        """
        selecionando avaliadores em espera
        """
        config = ConfiguracaoRSC.objects.first()
        if not config:
            raise Exception('Configuração do RSC não encontrada')
        #
        processos = ProcessoAvaliador.objects.filter(processo=processo, status=ProcessoAvaliador.EM_ESPERA, tipo_avaliador=tipo_avaliador)
        if processos:
            """
            pegando o primeiro registro em espera para setar o status para "AGUARDANDO ACEITE"
            """
            processo = processos[0]
            processo.status = ProcessoAvaliador.AGUARDANDO_ACEITE
            processo.data_convite = datetime.datetime.today()
            processo.save()

            dados = {
                'NOME_AVALIADOR': str(processo.avaliador.vinculo.user.get_profile().nome),
                'NOME_PROFESSOR_AVALIADO': str(processo.processo.servidor.pessoa_fisica.nome),
                'DATA_LIMITE_ACEITE_AVALIACAO': str(processo.data_limite()),
                'DIAS_PARA_AVALIACAO': config.dias_para_avaliacao,
                'SITE_URL': settings.SITE_URL,
            }
            assunto = '[SUAP] Avaliação de Processo RSC'
            mensagem = utils.substituir_marcacoes(config.email_professor_sorteado, dados)
            # só notifica pois o email é diferente do email do vínculo
            send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo.avaliador.vinculo], fail_silently=False, so_notificar=True)
            # envia o email
            send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo.avaliador.email_contato], fail_silently=False)
        else:
            dados = {
                'PROCESSO_RSC': str(processo),
                'SITE_URL': settings.SITE_URL,
            }
            assunto = '[SUAP] Processo RSC sem Avaliador Reserva'
            mensagem = utils.substituir_marcacoes(config.email_sem_avaliador_reserva, dados)
            send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, ['cppd@ifrn.edu.br'], fail_silently=False)

    def handle(self, *args, **options):
        """
        CHECAGEM DOS PROCESSOS COM AVALIADORES QUE PERDERAM O PRAZO DE ACEITO OU DE AVALIAÇÃO
        """
        #
        config = ConfiguracaoRSC.objects.first()
        if not config:
            raise Exception('Configuração do RSC não encontrada')
        #
        hoje = datetime.datetime.today().strftime('%d/%m/%Y')
        for processo_avaliador in tqdm.tqdm(
            ProcessoAvaliador.objects.filter(status__in=[ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.EM_AVALIACAO])
        ):
            if datetime.datetime.strptime(processo_avaliador.data_limite(), '%d/%m/%Y') < datetime.datetime.strptime(hoje, '%d/%m/%Y'):
                if processo_avaliador.avaliador.eh_interno():
                    tipo_avaliador = ProcessoAvaliador.AVALIADOR_INTERNO
                if processo_avaliador.avaliador.eh_externo():
                    tipo_avaliador = ProcessoAvaliador.AVALIADOR_EXTERNO
                """
                pega o processo atual e seta muda o status
                """
                processo_avaliador.status = ProcessoAvaliador.EXCEDEU_TEMPO_ACEITE
                if processo_avaliador.data_aceite:
                    processo_avaliador.status = ProcessoAvaliador.EXCEDEU_TEMPO_AVALIACAO
                    dados = {
                        'PROCESSO_RSC': str(processo_avaliador.processo),
                        'NOME_AVALIADOR': str(processo_avaliador.avaliador.vinculo.user.get_profile().nome),
                    }
                    assunto = '[SUAP] Processo de Avaliação Inativado'
                    mensagem = utils.substituir_marcacoes(config.email_professor_perdeu_prazo, dados)
                    # só notifica pois o email é diferente do email do vínculo
                    send_notification(
                        assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo_avaliador.avaliador.vinculo], fail_silently=False, so_notificar=True
                    )
                    # envia o email
                    send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo_avaliador.avaliador.email_contato], fail_silently=False)

                processo_avaliador.save()
                processo = processo_avaliador.processo
                if (
                    tipo_avaliador == ProcessoAvaliador.AVALIADOR_INTERNO
                    and processo.qtd_avaliadores_internos_ativos() == 0
                    or tipo_avaliador == ProcessoAvaliador.AVALIADOR_EXTERNO
                    and processo.qtd_avaliadores_externos_ativos() < 2
                ):
                    self.seleciona_avaliador(tipo_avaliador, processo_avaliador.processo)

        """
        CHECAGEM DE PROCESSOS QUE ESTÃO COM QUANTIDADE INFERIOR A 1 AVALIADOR INTERNO OU 2 AVALIADORES EXTERNOS
        """
        processos = ProcessoRSC.objects.filter(status__in=[ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoRSC.STATUS_EM_AVALIACAO])

        for processo in processos:
            if processo.qtd_avaliadores_internos_ativos() == 0:
                self.seleciona_avaliador(ProcessoAvaliador.AVALIADOR_INTERNO, processo)
            if processo.qtd_avaliadores_externos_ativos() < 2:
                self.seleciona_avaliador(ProcessoAvaliador.AVALIADOR_EXTERNO, processo)
