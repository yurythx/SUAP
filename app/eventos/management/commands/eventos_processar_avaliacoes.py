from django.utils import timezone

from djtools.management.commands import BaseCommandPlus
from eventos.models import AvaliacaoSubmissao, EtapaPeriodoSubmissao, FluxoSubmissao, Submissao
from eventos.utils import Notificar

"""
    Este comando processa avaliações e resultados finais de eventos, enviando notificações
    para avaliadores e coordenadores sobre pendências e atualizações de status.
    como executar:
    python manage.py eventos_processar_avaliacoes
"""


class Command(BaseCommandPlus):
    help = 'Processa avaliações, resultados finais e envia notificações de pendências próximo ao fim do prazo'

    def handle(self, *args, **options):
        hoje = timezone.now().date()
        fluxos_ativos = FluxoSubmissao.objects.filter(data_inicio__lte=hoje, data_fim__gte=hoje)

        for fluxo in fluxos_ativos:
            evento = fluxo.evento

            # Checa se está faltando <= 2 dias para o fim do prazo e envia notificações de pendências
            dias_restantes = (fluxo.data_fim - hoje).days
            self.stdout.write(self.style.NOTICE(f'Fluxo: {fluxo}, Hoje: {hoje}, Dias restantes: {dias_restantes}'))
            if (fluxo.etapa in [EtapaPeriodoSubmissao.AVALIACAO, EtapaPeriodoSubmissao.REAVALIACAO]) and dias_restantes <= 2:
                if evento.possui_avaliacao_pendente():
                    self.stdout.write(self.style.NOTICE(f'Notificando pendências de avaliação no evento #{evento.id} - {evento.nome}'))

                    # Agrupa avaliações pendentes por avaliador
                    avaliacoes_pendentes = AvaliacaoSubmissao.objects.filter(
                        versao__submissao__modalidade__evento=evento, nota__isnull=True
                    ).select_related('avaliador_modalidade__avaliador', 'versao')

                    avaliacoes_por_avaliador = {}
                    for avaliacao_submissao in avaliacoes_pendentes:
                        if avaliacao_submissao.avaliador_modalidade.avaliador not in avaliacoes_por_avaliador:
                            avaliacoes_por_avaliador[avaliacao_submissao.avaliador_modalidade.avaliador] = []
                        avaliacoes_por_avaliador[avaliacao_submissao.avaliador_modalidade.avaliador].append(avaliacao_submissao.versao)

                    # Envia notificações para cada avaliador
                    for avaliador, versoes_pendentes in avaliacoes_por_avaliador.items():
                        Notificar.pendencias_do_avaliador(avaliador, versoes_pendentes)

                    # Agrupa informações para coordenadores
                    pendencias_por_avaliador = {avaliador: len(versoes) for avaliador, versoes in avaliacoes_por_avaliador.items()}

                    # Envia notificação para os coordenadores
                    Notificar.coordenadores_pendencias_dos_avaliadores(evento, pendencias_por_avaliador)
                    evento.cria_log_processamento('Notificações enviadas para os avaliadores e coordenadores sobre pendências.')
                    self.stdout.write(self.style.SUCCESS(f'Notificações enviadas para o evento {evento.id}'))

            if evento.pode_processar_avaliacoes():
                # Só irá processar as avaliações se o evento estiver na etapa de correções
                self.stdout.write(self.style.NOTICE(f'Processando avaliações do evento #{evento.id} - {evento.nome}'))
                mensagem, status = evento.processar_avaliacoes(fluxo)
                if status == 'success':
                    self.stdout.write(self.style.SUCCESS(mensagem))
                else:
                    self.stdout.write(self.style.ERROR(f'Erro ao processar avaliações do evento: {mensagem}'))

            elif evento.pode_processar_resultados_para_avaliacao_presencial():
                # Só irá processar os resultados para avaliação presencial se o evento estiver na etapa de avaliação presencial
                self.stdout.write(self.style.NOTICE(f'Processando resultados para avaliação presencial do #evento {evento.id} - {evento.nome}'))
                mensagem, status = evento.processar_resultados_para_avaliacao_presencial()

                if status == 'success':
                    self.stdout.write(self.style.SUCCESS(mensagem))
                else:
                    self.stdout.write(self.style.ERROR(f'Erro ao processar resultados finais: {mensagem}'))
            elif evento.pode_processar_resultados_finais():
                # Só irá processar os resultados finais se o evento estiver na etapa de resultados finais
                self.stdout.write(self.style.NOTICE(f'Processando resultados finais do #evento {evento.id} - {evento.nome}'))
                mensagem, status = evento.processar_resultados_finais()
                if evento.configuracao is None:
                    self.stdout.write(self.style.ERROR('Erro ao processar resultados finais: Configuração do evento não encontrada.'))

                elif status == 'success':
                    self.stdout.write(self.style.SUCCESS(mensagem))
                    if evento.configuracao.notificar_resultados_automaticamente is True and evento.configuracao.notificacao_realizada_em is None:
                        notificou = Submissao.notificar_resultado_avaliacao(evento, notificar_todos=True)
                        if notificou > 0:
                            evento.configuracao.registrar_notificacao(automatica=True)
                            self.stdout.write(self.style.SUCCESS(f'{notificou} trabalhos notificados para o evento "{evento.nome}"'))
                else:
                    self.stdout.write(self.style.ERROR(f'Erro ao processar resultados finais: {mensagem}'))

            else:
                self.stdout.write(
                    self.style.NOTICE(
                        f'Evento #{evento.id} - {evento.nome} está na etapa {fluxo.get_etapa_display()}, nenhum processamento necessário.'
                    )
                )
