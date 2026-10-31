import os
import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils.termcolors import colorize

from catalogo_provedor_servico.models import SolicitacaoEtapa, Solicitacao
from catalogo_provedor_servico.providers.factory import get_service_provider_factory
from catalogo_provedor_servico.utils import Notificar


class Command(BaseCommand):
    help = (
        'Executa correções em solicitações do edital "Integrado IFRN 2026 de 2026/1"\n\n'
        'Público alvo: Solicitações de alunos PCD com Etapa 4 com json "antigo", criadas antes da atualização do edu, ocorria em 08/01/2026, por volta das 14:39."\n\n'
        'Uso:\n'
        '  python manage.py correcao_tecnico_integrado_ifrn --modo_execucao=simulacao\n'
        '  python manage.py correcao_tecnico_integrado_ifrn --modo_execucao=execucao_real\n'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--modo_execucao', type=str, choices=['simulacao', 'execucao_real'], help="Modo de execução do comando: 'simulacao' ou 'execucao_real'"
        )

    def enviar_notificacao(self, solicitacao):
        # MatriculaTecnicoServiceProvider
        service_provider = get_service_provider_factory().get_service_provider(id_servico_portal_govbr=solicitacao.servico.id_servico_portal_govbr)
        dados_email = service_provider.get_dados_email(solicitacao=solicitacao)
        service_provider.registrar_acompanhamento(solicitacao)
        Notificar.solicitacao_correcao_de_dados(solicitacao, dados_email)

    def handle(self, *args, **options):
        modo = options.get('modo_execucao')
        if not modo:
            self.stdout.write(self.style.WARNING('Você deve informar --modo_execucao=simulacao|execucao_real'))
            modo = input('Informe o modo de execução (simulacao/execucao_real): ').strip().lower()

        if modo not in ('simulacao', 'execucao_real'):
            self.stderr.write(self.style.ERROR('Valor inválido para --modo_execucao.'))
            return

        modo_is_execucao_real = modo == 'execucao_real'

        start_time = time.time()
        now = datetime.now()

        command_name = os.path.splitext(os.path.basename(__file__))[0]
        log_filename = f'{command_name}_{now.strftime("%Y_%m_%d_%Hh%Mmin%Ss")}.log'
        log_path = os.path.join(os.getcwd(), log_filename)

        with open(log_path, 'w', encoding='utf-8') as log:

            def log_write(text, stream=True):
                log.write(text + '\n')
                if stream:
                    self.stdout.write(text)

            log_write(
                colorize(
                    f'==> [{command_name.upper()}] - INICIADO EM {now:%Y-%m-%d %H:%M:%S} | MODO EXECUÇÃO: {modo.upper()}', fg='green', opts=('bold',)
                )
            )

            qs_base = (
                SolicitacaoEtapa.objects.filter(
                    # servico: Matricular-se em curso de Educação Profissional Técnica (Educação de Jovens e Adultos, Integrado e Subsequente) - IFRN
                    solicitacao__servico__id=3,
                    solicitacao__extra_dados__contains='Integrado IFRN 2026 de 2026/1',
                    numero_etapa=4,
                    dados__icontains='superdotacao',
                )
                # No caso só precisamos corrigir quem é de lista PCD. Quem não é, consegue ter a matrícula gerada mesmo com a etapa 4 com json "antigo".
                # Ex: "Etapa 2.edital_lista": "AC_PCD".
                .filter(solicitacao__extra_dados__contains='_PCD')
                .exclude(solicitacao__status__in=Solicitacao.STATUS_DEFINITIVOS)
            )

            log_write('\nResumo por status:\n')
            status_counts = qs_base.values('solicitacao__status').annotate(total=Count('solicitacao__id')).order_by('solicitacao__status')

            total_geral = 0
            for item in status_counts:
                total_geral += item['total']
                log_write(colorize(f'  - {item["solicitacao__status"]}: {item["total"]}', fg='magenta'))
            log_write(colorize(f'  (Total Geral: {total_geral})', fg='magenta'))

            qs = qs_base.select_related('solicitacao', 'solicitacao__servico').order_by('solicitacao__status')

            if qs.exists():
                log_write('\nProcessando solicitações...\n')
            else:
                log_write('\nNenhuma solicitação a ser processada!\n')

            for idx, solicitacao_etapa in enumerate(qs, start=1):
                solicitacao = solicitacao_etapa.solicitacao
                status_antes_processamento = solicitacao.status

                log_write(
                    colorize(
                        f'[N° {idx}] {solicitacao}\nstatus: {status_antes_processamento}\nservico: {solicitacao.servico}\nextra_dados: {solicitacao.extra_dados})',
                        fg='cyan',
                    )
                )

                try:
                    with transaction.atomic():
                        if status_antes_processamento == Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS:
                            if modo_is_execucao_real:
                                solicitacao_etapa.delete()
                                solicitacao.status_detalhamento = 'Por favor, refazer Etapa 4 e corrigir demais dados solicitados.'
                                solicitacao.save(update_fields=['status_detalhamento'])
                                self.enviar_notificacao(solicitacao)

                            log_write(colorize('  -> Etapa 4 apagada;', fg='yellow'))
                            log_write(colorize(f'  -> Status mantido ({status_antes_processamento}).', fg='yellow'))
                            log_write(
                                colorize(
                                    '  -> Notificação enviada para o usuário solicitado que ele refaça a etapa 4, além de corrigir os dados já solicitados.',
                                    fg='yellow',
                                )
                            )

                        elif status_antes_processamento in (
                            Solicitacao.STATUS_DADOS_CORRIGIDOS,
                            Solicitacao.STATUS_EM_ANALISE,
                            Solicitacao.STATUS_PRONTO_PARA_EXECUCAO,
                        ):
                            if modo_is_execucao_real:
                                solicitacao_etapa.delete()
                                solicitacao.status = Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS
                                solicitacao.status_detalhamento = 'Por favor, refazer a Etapa 4.'
                                solicitacao.save(update_fields=['status', 'status_detalhamento'])
                                self.enviar_notificacao(solicitacao)

                            log_write(colorize('  -> Etapa 4 apagada;', fg='yellow'))
                            log_write(
                                colorize(
                                    f'  -> Status alterado de {status_antes_processamento} para {Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS}.',
                                    fg='yellow',
                                )
                            )
                            log_write(colorize('  -> Notificação enviada para o usuário solicitado que ele refaça a etapa 4.', fg='yellow'))

                        elif status_antes_processamento == Solicitacao.STATUS_INCOMPLETO:
                            if modo_is_execucao_real:
                                solicitacao_etapa.delete()

                            log_write(colorize('  -> Etapa 4 apagada;', fg='yellow'))
                            log_write(colorize(f'  -> Status mantido ({status_antes_processamento}).', fg='yellow'))
                            log_write(colorize('  -> Nenhuma notifição enviada para o usuário já que a solicitação está incompleta.', fg='yellow'))

                        else:
                            log_write(colorize('  -> Status não tratado.', fg='red'))

                except Exception as exc:
                    log_write(colorize(f'  -> ERRO ao processar solicitação: {exc}', fg='red', opts=('bold',)))

                log_write('')

            end_time = time.time()
            log_write(
                colorize(
                    f'\n==> FINALIZADO EM {datetime.now():%Y-%m-%d %H:%M:%S} | '
                    f'DURAÇÃO: {round(end_time - start_time, 2)}s | '
                    f'MODO EXECUÇÃO: {modo.upper()}',
                    fg='green',
                    opts=('bold',),
                )
            )

            log_write(colorize(f'\nArquivo de log salvo em: {log_path}', fg='blue', opts=('bold',)))
