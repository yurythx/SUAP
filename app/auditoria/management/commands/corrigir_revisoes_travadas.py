"""Corrige posicionamentos (e seus monitoramentos) presos em revisão.

Deadlock legado (caso 4.3): ao remover a revisão em andamento, o posicionamento ficava em
``EM_REVISAO`` sem nenhuma ``RevisaoPosicionamento`` e sem como registrar nova revisão
(``pode_revisar`` exige ``REVISAO_PENDENTE``), travando o monitoramento em ``EM_REVISAO``.

Este comando localiza posicionamentos em ``EM_REVISAO`` sem revisão e os reabre
(``reabrir_revisao``), o que ressincroniza o monitoramento para ``AGUARDANDO_REVISAO``.
Roda em *dry-run* por padrão; use ``--apply`` para efetivar.

    python manage.py corrigir_revisoes_travadas            # apenas lista
    python manage.py corrigir_revisoes_travadas --apply     # corrige
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from auditoria.models import Posicionamento
from auditoria.models.posicionamento import PosicionamentoStatus


class Command(BaseCommand):
    help = 'Corrige posicionamentos presos em EM_REVISAO sem revisão (e destrava o monitoramento).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Aplica as correções (o padrão é apenas listar — dry-run).')

    def handle(self, *args, **options):
        aplicar = options['apply']
        travados = self._encontrar_travados()

        if not travados:
            self.stdout.write(self.style.SUCCESS('Nenhum posicionamento travado em revisão encontrado.'))
            return

        modo = 'CORRIGINDO' if aplicar else 'DRY-RUN (use --apply para corrigir)'
        self.stdout.write(f'{len(travados)} posicionamento(s) travado(s) em revisão — {modo}:')

        corrigidos = 0
        for posicionamento in travados:
            if self._processar(posicionamento, aplicar):
                corrigidos += 1

        if aplicar:
            self.stdout.write(self.style.SUCCESS(f'{corrigidos}/{len(travados)} corrigido(s).'))

    def _processar(self, posicionamento, aplicar):
        """Lista (dry-run) ou corrige um único posicionamento travado, isolando falhas:
        um erro ao corrigir um item é reportado e não interrompe o restante do lote.

        Retorna True somente quando o item foi efetivamente corrigido."""
        if not aplicar:
            self._reportar(posicionamento, aplicar=False, resolvido=None)
            return False
        try:
            resolvido = self._corrigir(posicionamento)
        except Exception as erro:
            # Varredura de lote: isola a falha de um item (reporta e segue) para não
            # abortar a correção dos demais posicionamentos travados.
            self._reportar_erro(posicionamento, erro)
            return False
        self._reportar(posicionamento, aplicar=True, resolvido=resolvido)
        return resolvido

    def _encontrar_travados(self):
        """Posicionamentos em EM_REVISAO que não têm nenhuma revisão associada."""
        return list(Posicionamento.objects.filter(status=PosicionamentoStatus.EM_REVISAO, revisoes__isnull=True))

    def _corrigir(self, posicionamento):
        """Reabre o posicionamento para revisão. Retorna True se saiu de EM_REVISAO."""
        with transaction.atomic():
            posicionamento.reabrir_revisao()
            posicionamento.save()
        # Não usar refresh_from_db: status é FSMField protegido.
        atual = Posicionamento.objects.get(pk=posicionamento.pk)
        return atual.status != PosicionamentoStatus.EM_REVISAO

    def _descricao(self, posicionamento):
        return f'  posicionamento #{posicionamento.pk}/{posicionamento.tipo} (monitoramento #{posicionamento.referencia.pk})'

    def _reportar(self, posicionamento, aplicar, resolvido):
        base = self._descricao(posicionamento)
        if not aplicar:
            self.stdout.write(base)
        elif resolvido:
            self.stdout.write(self.style.SUCCESS(f'{base} -> reaberto para revisão'))
        else:
            self.stdout.write(self.style.WARNING(f'{base} -> NÃO resolvido'))

    def _reportar_erro(self, posicionamento, erro):
        base = self._descricao(posicionamento)
        self.stderr.write(self.style.ERROR(f'{base} -> ERRO ({type(erro).__name__}: {erro}) — item ignorado, seguindo o lote'))
