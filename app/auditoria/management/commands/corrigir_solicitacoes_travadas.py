"""Corrige solicitações de providência presas em "Aguardando Posicionamento".

Deadlock de máquina de estado: quando um posicionamento sem handler de
pós-transição era publicado (notadamente o de Rejeição — ``REJEITAR_SOLICITACAO``),
``Posicionamento.handle_post_transition`` não avançava a manifestação nem a
solicitação, deixando-a presa em ``AGUARDANDO_POSICIONAMENTO`` apesar do
posicionamento já publicado.

Este comando localiza esses casos e reaplica a transição que faltou,
reaproveitando o próprio ``handle_post_transition`` (agora que o handler existe).
Roda em *dry-run* por padrão; use ``--apply`` para efetivar.

    python manage.py corrigir_solicitacoes_travadas            # apenas lista
    python manage.py corrigir_solicitacoes_travadas --apply     # corrige
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from auditoria.models import SolicitacaoProvidencia
from auditoria.models.manifestacao import ManifestacaoStatus
from auditoria.models.posicionamento import PosicionamentoStatus
from auditoria.models.providencia import SolicitacaoProvidenciaStatus


class Command(BaseCommand):
    help = 'Corrige solicitações de providência presas em "Aguardando Posicionamento" com posicionamento já publicado.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Aplica as correções (o padrão é apenas listar — dry-run).')

    def handle(self, *args, **options):
        aplicar = options['apply']
        travadas = self._encontrar_travadas()

        if not travadas:
            self.stdout.write(self.style.SUCCESS('Nenhuma solicitação travada encontrada.'))
            return

        modo = 'CORRIGINDO' if aplicar else 'DRY-RUN (use --apply para corrigir)'
        self.stdout.write(f'{len(travadas)} solicitação(ões) travada(s) — {modo}:')

        corrigidas = 0
        for solicitacao, manifestacao, posicionamento in travadas:
            if self._processar(solicitacao, manifestacao, posicionamento, aplicar):
                corrigidas += 1

        if aplicar:
            self.stdout.write(self.style.SUCCESS(f'{corrigidas}/{len(travadas)} corrigida(s).'))

    def _processar(self, solicitacao, manifestacao, posicionamento, aplicar):
        """Lista (dry-run) ou corrige uma única travada, isolando falhas: um erro ao
        corrigir um item é reportado e não interrompe o restante do lote.

        Retorna True somente quando o item foi efetivamente corrigido."""
        if not aplicar:
            self._reportar(solicitacao, manifestacao, posicionamento, aplicar=False, resolvida=None)
            return False
        try:
            resolvida = self._corrigir(solicitacao, posicionamento)
        except Exception as erro:
            # Varredura de lote: isola a falha de um item (reporta e segue) para não
            # abortar a correção das demais solicitações travadas.
            self._reportar_erro(solicitacao, manifestacao, posicionamento, erro)
            return False
        self._reportar(solicitacao, manifestacao, posicionamento, aplicar=True, resolvida=resolvida)
        return resolvida

    def _encontrar_travadas(self):
        """Solicitação em AGUARDANDO_POSICIONAMENTO, com a última manifestação ainda
        em RECEBIDA e já tendo um posicionamento PUBLICADO — ou seja, o auditor agiu
        mas o estado não avançou."""
        resultado = []
        qs = SolicitacaoProvidencia.objects.filter(status=SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO)
        for solicitacao in qs:
            manifestacao = solicitacao.ultima_manifestacao()
            if manifestacao is None or manifestacao.status != ManifestacaoStatus.RECEBIDA:
                continue
            posicionamento = manifestacao.posicionamentos.filter(status=PosicionamentoStatus.PUBLICADO).order_by('-id').first()
            if posicionamento is not None:
                resultado.append((solicitacao, manifestacao, posicionamento))
        return resultado

    def _corrigir(self, solicitacao, posicionamento):
        """Reaplica a pós-transição do posicionamento publicado. Retorna True se a
        solicitação saiu de AGUARDANDO_POSICIONAMENTO."""
        with transaction.atomic():
            posicionamento.handle_post_transition()
        # Não usar refresh_from_db: status é FSMField protegido (atribuição direta proibida).
        atual = SolicitacaoProvidencia.objects.get(pk=solicitacao.pk)
        return atual.status != SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO

    def _descricao(self, solicitacao, manifestacao, posicionamento):
        return (
            f'  solicitacao #{solicitacao.pk} (monitoramento #{solicitacao.monitoramento_id}) '
            f'manifestacao #{manifestacao.pk}/{manifestacao.tipo} posicionamento #{posicionamento.pk}/{posicionamento.tipo}'
        )

    def _reportar(self, solicitacao, manifestacao, posicionamento, aplicar, resolvida):
        base = self._descricao(solicitacao, manifestacao, posicionamento)
        if not aplicar:
            self.stdout.write(base)
        elif resolvida:
            self.stdout.write(self.style.SUCCESS(f'{base} -> corrigida'))
        else:
            self.stdout.write(self.style.WARNING(f'{base} -> NÃO resolvida (sem handler para o tipo do posicionamento)'))

    def _reportar_erro(self, solicitacao, manifestacao, posicionamento, erro):
        base = self._descricao(solicitacao, manifestacao, posicionamento)
        self.stderr.write(self.style.ERROR(f'{base} -> ERRO ({type(erro).__name__}: {erro}) — item ignorado, seguindo o lote'))
