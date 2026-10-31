import datetime

import tqdm
from django.conf import settings
from django.utils import timezone

from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_mail, send_notification
from professor_titular.models import ProcessoAvaliador, ProcessoTitular, ConfiguracaoTitular
from rh import utils
from comum.models import Configuracao


class Command(BaseCommandPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Controla processos que já receberam notificação de falta de avaliador reserva nesta execução
        self._processos_sem_reserva_notificados = set()

    def seleciona_avaliador(self, tipo_avaliador, processo):
        """
        selecionando avaliadores em espera
        """
        config = ConfiguracaoTitular.objects.first()
        if not config:
            raise Exception('Configuração do Professor Titular não encontrada')
        #
        processos_reserva = ProcessoAvaliador.objects.filter(
            processo=processo, status=ProcessoAvaliador.EM_ESPERA, tipo_avaliador=tipo_avaliador
        ).order_by('data_cadastro')
        if processos_reserva:
            """
            pegando o primeiro registro em espera para setar o status para "AGUARDANDO ACEITE"
            """
            pa = processos_reserva[0]
            pa.status = ProcessoAvaliador.AGUARDANDO_ACEITE
            pa.data_convite = timezone.now()
            pa.save()

            dados = {
                'NOME_AVALIADOR': str(pa.avaliador.vinculo.pessoa.nome),
                'NOME_PROFESSOR_AVALIADO': str(pa.processo.servidor.pessoa_fisica.nome),
                'DATA_LIMITE_ACEITE_AVALIACAO': str(pa.data_limite()),
                'DIAS_PARA_AVALIACAO': config.dias_para_avaliacao,
                'SITE_URL': settings.SITE_URL,
            }
            assunto = '[SUAP] Avaliação de Processo de Professor Titular'
            mensagem = utils.substituir_marcacoes(config.email_professor_sorteado, dados)
            if tipo_avaliador == ProcessoAvaliador.AVALIADOR_INTERNO:
                # notifica via SUAP
                send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [pa.avaliador.vinculo], fail_silently=False)
            # envia e-mail
            send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [pa.avaliador.email_contato], fail_silently=False)
        else:
            # Envia apenas UMA notificação por processo nesta execução, mesmo que faltem múltiplos avaliadores
            if processo.pk not in self._processos_sem_reserva_notificados:
                dados = {
                    'PROCESSO_TITULAR': str(processo),
                    'SITE_URL': settings.SITE_URL,
                }
                assunto = '[SUAP] Processo Professor Titular sem Avaliador Reserva'
                mensagem = utils.substituir_marcacoes(config.email_sem_avaliador_reserva, dados)
                email_cppd = Configuracao.get_valor_por_chave('rh', 'email_cppd')
                if not email_cppd:
                    raise Exception('Configuração de email_cppd não encontrada em Configuração Geral do RH')
                send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [email_cppd], fail_silently=False)
                self._processos_sem_reserva_notificados.add(processo.pk)

    def _qtd_avaliadores_internos_ativos(self, processo):
        return ProcessoAvaliador.objects.filter(
            processo=processo,
            tipo_avaliador=ProcessoAvaliador.AVALIADOR_INTERNO,
            status__in=[
                ProcessoAvaliador.AGUARDANDO_ACEITE,
                ProcessoAvaliador.EM_AVALIACAO,
                ProcessoAvaliador.AVALIACAO_FINALIZADA,
            ],
        ).count()

    def _qtd_avaliadores_externos_ativos(self, processo):
        return ProcessoAvaliador.objects.filter(
            processo=processo,
            tipo_avaliador=ProcessoAvaliador.AVALIADOR_EXTERNO,
            status__in=[
                ProcessoAvaliador.AGUARDANDO_ACEITE,
                ProcessoAvaliador.EM_AVALIACAO,
                ProcessoAvaliador.AVALIACAO_FINALIZADA,
            ],
        ).count()

    def handle(self, *args, **options):
        """
        CHECAGEM DOS PROCESSOS COM AVALIADORES QUE PERDERAM O PRAZO DE ACEITO OU DE AVALIAÇÃO
        """
        #
        config = ConfiguracaoTitular.objects.first()
        if not config:
            raise Exception('Configuração do Professor Titular não encontrada')
        #
        hoje = datetime.date.today()
        for processo_avaliador in tqdm.tqdm(
            ProcessoAvaliador.objects.filter(status__in=[ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.EM_AVALIACAO])
        ):
            data_limite_avaliador = datetime.datetime.strptime(processo_avaliador.data_limite(), '%d/%m/%Y').date()
            if data_limite_avaliador < hoje:
                if processo_avaliador.avaliador.eh_interno():
                    tipo_avaliador = ProcessoAvaliador.AVALIADOR_INTERNO
                if processo_avaliador.avaliador.eh_externo():
                    tipo_avaliador = ProcessoAvaliador.AVALIADOR_EXTERNO
                """
                pega o processo atual e muda o status
                """
                processo_avaliador.status = ProcessoAvaliador.EXCEDEU_TEMPO_ACEITE
                if processo_avaliador.data_aceite:
                    processo_avaliador.status = ProcessoAvaliador.EXCEDEU_TEMPO_AVALIACAO
                    dados = {
                        'PROCESSO_TITULAR': str(processo_avaliador.processo),
                        'NOME_AVALIADOR': str(processo_avaliador.avaliador.get_nome_completo()),
                    }
                    assunto = '[SUAP] Processo de Avaliação Inativado'
                    mensagem = utils.substituir_marcacoes(config.email_professor_perdeu_prazo, dados)
                    # notifica via SUAP e envia e-mail
                    send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo_avaliador.avaliador.vinculo], fail_silently=False)
                    send_mail(
                        assunto,
                        mensagem,
                        settings.DEFAULT_FROM_EMAIL,
                        [processo_avaliador.avaliador.email_contato],
                        fail_silently=False,
                    )
                else:
                    # excedeu prazo de aceite
                    dados = {
                        'PROCESSO_TITULAR': str(processo_avaliador.processo),
                        'NOME_AVALIADOR': str(processo_avaliador.avaliador.get_nome_completo()),
                    }
                    assunto = '[SUAP] Convite de Avaliação Expirado'
                    mensagem = utils.substituir_marcacoes(config.email_professor_perdeu_prazo, dados)
                    send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo_avaliador.avaliador.vinculo], fail_silently=False)
                    send_mail(
                        assunto,
                        mensagem,
                        settings.DEFAULT_FROM_EMAIL,
                        [processo_avaliador.avaliador.email_contato],
                        fail_silently=False,
                    )

                processo_avaliador.save()
                processo = processo_avaliador.processo
                if (tipo_avaliador == ProcessoAvaliador.AVALIADOR_INTERNO and self._qtd_avaliadores_internos_ativos(processo) == 0) or (
                    tipo_avaliador == ProcessoAvaliador.AVALIADOR_EXTERNO and self._qtd_avaliadores_externos_ativos(processo) < 2
                ):
                    self.seleciona_avaliador(tipo_avaliador, processo_avaliador.processo)

        """
        CHECAGEM DE PROCESSOS QUE ESTÃO COM QUANTIDADE INFERIOR A 1 AVALIADOR INTERNO OU 2 AVALIADORES EXTERNOS
        """
        processos = ProcessoTitular.objects.filter(
            status__in=[ProcessoTitular.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoTitular.STATUS_EM_AVALIACAO]
        )

        for processo in processos:
            if self._qtd_avaliadores_internos_ativos(processo) == 0:
                self.seleciona_avaliador(ProcessoAvaliador.AVALIADOR_INTERNO, processo)
            if self._qtd_avaliadores_externos_ativos(processo) < 3:
                self.seleciona_avaliador(ProcessoAvaliador.AVALIADOR_EXTERNO, processo)
