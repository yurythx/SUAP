from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from eventos.enums import (
    EtapaPeriodoSubmissao,
    Recomendacao,
    ResultadoAvaliacao,
    SituacaoSubmissao,
)
from eventos.models import AutorSubmissao, AvaliacaoSubmissao, Evento, Submissao, VersaoSubmissao

"""
python manage.py eventos_forcar_processamento 8042
"""


class Command(BaseCommandPlus):
    help = 'Forçar processamento das avaliações presenciais de um evento específico'

    def add_arguments(self, parser):
        parser.add_argument(
            'evento_id',
            type=int,
            help='ID do evento para verificar',
        )

    def handle(self, *args, **options):
        evento_id = options['evento_id']

        # Busca o evento uma única vez
        evento = Evento.objects.get(id=evento_id)
        self.stdout.write(f'\n{"=" * 80}')
        self.stdout.write(f'Evento: {evento.nome}')
        self.stdout.write(f'{"=" * 80}\n')

        with transaction.atomic():
            # Após migrar submissões, verifica se é necessário preparar para avaliação presencial
            submissoes_processadas = 0
            fluxo_atual = evento.get_fluxo_atual()

            if fluxo_atual and fluxo_atual.etapa == EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL:
                # Se houver avaliação presencial, prepara novas versões para aprovados
                for submissao in Submissao.objects.filter(
                    modalidade__evento=evento, resultado_avaliacao=ResultadoAvaliacao.APROVADO, situacao=SituacaoSubmissao.AVALIADO
                ):
                    ultima_versao = submissao.versoes.order_by('-id').first()
                    etiqueta = 'Versão criada durante o processamento para avaliação presencial'
                    nova_versao = VersaoSubmissao.objects.create(
                        submissao=submissao,
                        numero=ultima_versao.numero + 1,
                        arquivo=ultima_versao.arquivo,
                        etiqueta=etiqueta,
                    )
                    for avaliacao in ultima_versao.pareceres.all():
                        AvaliacaoSubmissao.objects.create(
                            avaliador_modalidade=avaliacao.avaliador_modalidade,
                            versao=nova_versao,
                            recomendacao=Recomendacao.ACEITAR,
                        )
                    submissao.situacao = SituacaoSubmissao.AGUARDANDO_AVALIACAO_PRESENCIAL
                    submissao.save(update_fields=['situacao'])

                    submissoes_processadas += 1
                    for participante in submissao.autores:
                        autor_novo = participante.cria_autor_de_trabalho()
                        if autor_novo.id != participante.id:
                            # Substitui o autor antigo pelo novo na submissão
                            AutorSubmissao.objects.filter(submissao=submissao, participante=participante).update(participante=autor_novo)

                mensagem = f'{submissoes_processadas} submissões preparadas para avaliação presencial.'
                evento.cria_log_processamento(mensagem, fluxo_atual)
