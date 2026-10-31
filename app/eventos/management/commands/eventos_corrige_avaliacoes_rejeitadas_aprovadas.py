from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef

from eventos.enums import Recomendacao, ResultadoAvaliacao
from eventos.models import AvaliacaoSubmissao, Evento, Submissao

"""
python manage.py eventos_corrige_avaliacoes_rejeitadas_aprovadas 7556 --corrigir

Conforme requisito da Issue: #15233
https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/15233

O objetivo deste comando é corrigir submissões que estão com o status de Aprovado, porém algum avaliador rejeitou a submissão.
Embora a média das notas esteja correta, a submissão deve ser marcada como Reprovada se algum avaliador recomendou Recomendacao.REJEITAR.
"""


class Command(BaseCommand):
    help = 'Corrige submissões aprovadas que possuem avaliações com recomendação de rejeição'

    def add_arguments(self, parser):
        parser.add_argument(
            'evento_id',
            type=int,
            help='ID do evento para verificar',
        )
        parser.add_argument(
            '--corrigir',
            action='store_true',
            help='Aplica as correções, alterando o resultado das submissões',
        )

    def handle(self, *args, **options):
        evento_id = options['evento_id']
        corrigir = options.get('corrigir', False)

        # Busca o evento
        try:
            evento = Evento.objects.get(id=evento_id)
        except Evento.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Evento com ID {evento_id} não encontrado'))
            return

        self.stdout.write(f'\n{"=" * 80}')
        self.stdout.write(f'Evento: {evento.nome}')
        self.stdout.write(f'{"=" * 80}\n')

        # Busca submissões aprovadas que possuem pelo menos uma avaliação com recomendação de rejeição
        submissoes_problematicas = (
            Submissao.objects.filter(modalidade__evento=evento, resultado_avaliacao=ResultadoAvaliacao.APROVADO)
            .filter(Exists(AvaliacaoSubmissao.objects.filter(versao__submissao=OuterRef('pk'), recomendacao=Recomendacao.REJEITAR)))
            .select_related('modalidade', 'area_tematica')
            .prefetch_related('versoes__pareceres__avaliador_modalidade')
        )

        if not submissoes_problematicas.exists():
            self.stdout.write(self.style.SUCCESS('✓ Nenhuma submissão problemática encontrada!'))
            return

        self.stdout.write(self.style.WARNING(f'Encontradas {submissoes_problematicas.count()} submissão(ões) aprovada(s) com avaliação rejeitada:\n'))

        total_corrigidas = 0

        for submissao in submissoes_problematicas:
            self.stdout.write(f'\n{"-" * 80}')
            self.stdout.write(f'ID: {submissao.pk}')
            self.stdout.write(f'Título: {submissao.titulo}')
            self.stdout.write(f'Modalidade: {submissao.modalidade}')
            self.stdout.write(f'Área Temática: {submissao.area_tematica}')
            resultado_atual = dict(ResultadoAvaliacao.choices).get(submissao.resultado_avaliacao, 'N/A')
            self.stdout.write(f'Resultado atual: {resultado_atual}')
            self.stdout.write(f'Nota final: {submissao.nota_final}')

            # Lista as avaliações
            ultima_versao = submissao.versoes.first()
            if ultima_versao:
                avaliacoes = ultima_versao.pareceres.all()
                self.stdout.write(f'\nAvaliações ({avaliacoes.count()}):')

                for avaliacao in avaliacoes:
                    recomendacao_display = dict(Recomendacao.choices).get(avaliacao.recomendacao, 'N/A')
                    avaliador = avaliacao.avaliador_modalidade.avaliador.nome

                    status = 'REJEITOU' if avaliacao.recomendacao == Recomendacao.REJEITAR else 'ACEITOU'

                    self.stdout.write(f'  {status} {avaliador}: Nota={avaliacao.nota}, Recomendação={recomendacao_display}')

            if corrigir:
                with transaction.atomic():
                    # Atualiza o resultado para REPROVADO
                    Submissao.objects.filter(pk=submissao.pk).update(resultado_avaliacao=ResultadoAvaliacao.REPROVADO)
                    total_corrigidas += 1
                    self.stdout.write(self.style.SUCCESS(f'\n  Submissão corrigida: {ResultadoAvaliacao.APROVADO} → {ResultadoAvaliacao.REPROVADO}'))

        self.stdout.write(f'\n{"=" * 80}')
        if corrigir:
            self.stdout.write(self.style.SUCCESS(f'RESUMO: {total_corrigidas} submissão(ões) corrigida(s)'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'\nMODO SOMENTE LEITURA\n'
                    f'Para corrigir as submissões, execute:\n'
                    f'python manage.py eventos_corrige_avaliacoes_rejeitadas_aprovadas {evento_id} --corrigir'
                )
            )
        self.stdout.write(f'{"=" * 80}\n')
