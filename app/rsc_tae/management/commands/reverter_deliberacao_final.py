"""
Management command: reverter_deliberacao_final

Reverte a deliberação final (CRSC) de um processo RSC-TAE já finalizado,
devolvendo-o ao estado ``AGUARDANDO_CRSC``. A fase final tem dois níveis:

  * os votos dos membros da comissão  (``VotoDeliberacaoFinalRSCTae``);
  * a deliberação de finalização consolidada, que fecha o processo em
    DEFERIDO/INDEFERIDO (``DeliberacaoCRSCRSCTae``).

O comando opera em três modos:

  1. SÓ FINALIZAÇÃO (padrão): remove apenas a deliberação de finalização,
     mantendo os votos dos membros. Como os votos permanecem, a tela de
     deliberação da CRSC exibe a ação "Finalizar deliberação", permitindo que um
     membro ativo consolide novamente o resultado a partir dos votos existentes.
  2. MEMBRO (``--membro-vinculo <id...>`` ou ``--membro-matricula <mat...>``):
     remove o(s) voto(s) do(s) membro(s) indicado(s) E a deliberação de
     finalização (consolidada com base naquele voto); reabre para aquele(s)
     membro(s) votar(em) de novo.
  3. TODOS OS VOTOS (``--todos-votos``): remove todos os votos dos membros E a
     finalização, reabrindo a rodada inteira para uma nova deliberação final.

Em todos os modos a situação volta para ``AGUARDANDO_CRSC`` (com histórico),
o movimento no banco de pontos é estornado (com recálculo do saldo) e os campos
de finalização do processo são limpos — tudo de forma atômica.

Como estados finais (DEFERIDO/INDEFERIDO) não têm transição de saída em
``SituacaoProcesso.TRANSICOES``, a situação é ajustada diretamente, mas o
histórico (``HistoricoSituacaoProcessoRSCTae``) é gravado para auditoria.

Por segurança, roda em modo simulação por padrão: só grava com ``--commit``.

Uso:
    # Modo 1 — remove só a finalização (mantém os votos dos membros)
    python manage.py reverter_deliberacao_final 123

    # Modo 2 — remove o voto de um membro (por vínculo ou matrícula) + a finalização, e aplica
    python manage.py reverter_deliberacao_final 123 --membro-vinculo 999 --commit
    python manage.py reverter_deliberacao_final 123 --membro-matricula 1234 --commit
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from comum.models import Vinculo

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import (
    BancoPontosRSCTae,
    MovimentoBancoPontosRSCTae,
    OrigemTransicao,
    ProcessoRSCTae,
)
from rsc_tae.views._helpers import quantidade_deliberacoes_item, status_deliberacao_final


class Command(BaseCommand):
    help = 'Reverte a deliberação final (CRSC) de um processo RSC-TAE finalizado, devolvendo-o a AGUARDANDO_CRSC.'

    def add_arguments(self, parser):
        parser.add_argument('processo_id', type=int, help='ID do ProcessoRSCTae a reverter.')
        grupo_votos = parser.add_mutually_exclusive_group()
        grupo_votos.add_argument(
            '--membro-vinculo',
            type=int,
            nargs='+',
            dest='membro_vinculos',
            help='ID(s) do(s) Vinculo do(s) membro(s) cujo(s) voto(s) devem ser removidos (+ a finalização). '
            'Sem --membro-vinculo/--membro-matricula/--todos-votos, remove apenas a deliberação de finalização (mantendo os votos).',
        )
        grupo_votos.add_argument(
            '--membro-matricula',
            nargs='+',
            dest='membro_matriculas',
            help='Matrícula(s) do(s) servidor(es) membro(s) cujo(s) voto(s) devem ser removidos (+ a finalização). Alternativa a --membro-vinculo.',
        )
        grupo_votos.add_argument(
            '--todos-votos',
            action='store_true',
            dest='todos_votos',
            help='Remove todos os votos dos membros (+ a finalização), reabrindo a rodada para uma nova deliberação final.',
        )
        parser.add_argument(
            '--responsavel-vinculo',
            type=int,
            dest='responsavel_vinculo',
            help='ID do Vinculo do RH que está realizando a correção (atribuído ao histórico).',
        )
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Aplica as alterações. Sem esta flag, o comando apenas simula (rollback ao final).',
        )

    def handle(self, *args, **options):
        processo = self._get_processo(options['processo_id'])
        responsavel = self._get_responsavel(options.get('responsavel_vinculo'))
        membro_vinculos = options.get('membro_vinculos') or []
        membro_matriculas = options.get('membro_matriculas') or []
        todos_votos = options.get('todos_votos') or False

        try:
            with transaction.atomic():
                self._reverter(processo, membro_vinculos, membro_matriculas, todos_votos, responsavel)
                if not options['commit']:
                    raise _Rollback
        except _Rollback:
            self.stdout.write(self.style.WARNING('\nSIMULAÇÃO — nenhuma alteração foi gravada. Rode com --commit para aplicar.'))
            return

        self.stdout.write(self.style.SUCCESS(f'\nProcesso #{processo.pk} revertido para AGUARDANDO_CRSC.'))

    # ------------------------------------------------------------------ #
    # Passos da reversão                                                  #
    # ------------------------------------------------------------------ #

    def _reverter(self, processo, membro_vinculos, membro_matriculas, todos_votos, responsavel):
        remove_membros = bool(membro_vinculos or membro_matriculas)
        self._remover_finalizacao(processo)
        if todos_votos:
            self._remover_todos_votos(processo)
        elif remove_membros:
            self._remover_votos_membros(processo, membro_vinculos, membro_matriculas)
        self._estornar_banco(processo)
        self._voltar_situacao(processo, responsavel)
        if not todos_votos and not remove_membros:
            self._informar_finalizacao_pendente(processo)

    def _remover_finalizacao(self, processo):
        deliberacao = getattr(processo, 'deliberacao_crsc', None)
        if deliberacao is None:
            self.stdout.write(self.style.WARNING('- Deliberação de finalização: nenhuma encontrada (já removida?).'))
            return
        self.stdout.write(f'- Removendo deliberação de finalização #{deliberacao.pk}.')
        deliberacao.delete()

    def _remover_votos_membros(self, processo, membro_vinculos, membro_matriculas):
        filtro = Q()
        if membro_vinculos:
            filtro |= Q(deliberado_por_vinculo_id__in=membro_vinculos)
        if membro_matriculas:
            filtro |= Q(deliberado_por_vinculo__pessoa__pessoafisica__servidor_set__matricula__in=membro_matriculas)
        votos = list(processo.votos_deliberacao_final.filter(filtro).select_related('deliberado_por_vinculo__pessoa').distinct())
        if not votos:
            criterio = membro_matriculas or membro_vinculos
            raise CommandError(f'Nenhum voto de membro encontrado para {criterio} neste processo.')
        for voto in votos:
            self.stdout.write(f'- Removendo voto #{voto.pk} do membro {voto.deliberado_por_vinculo}.')
        processo.votos_deliberacao_final.filter(pk__in=[v.pk for v in votos]).delete()

    def _remover_todos_votos(self, processo):
        votos = list(processo.votos_deliberacao_final.select_related('deliberado_por_vinculo__pessoa'))
        if not votos:
            self.stdout.write(self.style.WARNING('- Votos dos membros: nenhum voto a remover.'))
            return
        for voto in votos:
            self.stdout.write(f'- Removendo voto #{voto.pk} do membro {voto.deliberado_por_vinculo}.')
        processo.votos_deliberacao_final.all().delete()

    def _estornar_banco(self, processo):
        movimentos = processo.movimentos_banco_pontos.filter(
            tipo__in=[
                MovimentoBancoPontosRSCTae.TIPO_CREDITO_DEFERIMENTO,
                MovimentoBancoPontosRSCTae.TIPO_DEVOLUCAO_INDEFERIMENTO,
            ]
        )
        total = sum((m.valor for m in movimentos), 0)
        if not movimentos:
            self.stdout.write('- Banco de pontos: nenhum movimento da deliberação a estornar.')
            return
        self.stdout.write(f'- Estornando {movimentos.count()} movimento(s) do banco de pontos (total: {total}).')
        movimentos.delete()
        self._recalcular_saldo(processo.vinculo)

    def _recalcular_saldo(self, vinculo):
        banco = BancoPontosRSCTae.get_or_create_for_vinculo(vinculo)
        movimentos = list(banco.movimentos.all())
        creditos = sum((m.valor for m in movimentos if m.tipo in MovimentoBancoPontosRSCTae.TIPOS_CREDITO), 0)
        debitos = sum((m.valor for m in movimentos if m.tipo in MovimentoBancoPontosRSCTae.TIPOS_DEBITO), 0)
        banco.saldo = creditos - debitos
        banco.save(update_fields=['saldo', 'data_atualizacao'])
        self.stdout.write(f'- Saldo do banco recalculado: {banco.saldo}.')

    def _voltar_situacao(self, processo, responsavel):
        # Reversão via transicionar() (caminho único autorizado): grava histórico + motivo + origem
        # e limpa os campos de finalização na mesma transação. A transição DEFERIDO/INDEFERIDO →
        # AGUARDANDO_CRSC é permitida em SituacaoProcesso.TRANSICOES para este fim administrativo.
        processo.transicionar(
            SituacaoProcesso.AGUARDANDO_CRSC,
            motivo='Reversão administrativa da deliberação final (realizada indevidamente).',
            por_vinculo=responsavel,
            origem=OrigemTransicao.MANUAL,
            campos_extras={
                'avaliacao_finalizada_por': None,
                'data_finalizacao_avaliacao': None,
                'avaliacao_motivo_indeferimento': '',
            },
        )
        self.stdout.write('- Situação alterada para AGUARDANDO_CRSC e campos de finalização limpos.')

    def _informar_finalizacao_pendente(self, processo):
        """No modo "só finalização", informa como o processo será re-finalizado, conforme os votos mantidos."""
        votos = list(processo.votos_deliberacao_final.all())
        status = status_deliberacao_final(votos, quantidade_deliberacoes_item())
        if status['fechado']:
            self.stdout.write(
                '- Os votos dos membros foram mantidos e ainda formam quórum. Na tela de deliberação da CRSC, '
                'um membro ativo pode usar "Finalizar deliberação" para consolidar novamente o resultado com esses votos.'
            )
        else:
            faltam = status['quantidade_necessaria'] - status['total']
            self.stdout.write(
                f'- Os votos mantidos ainda não formam quórum (faltam {faltam}). '
                'A deliberação final será concluída quando os membros restantes votarem na tela da CRSC.'
            )

    # ------------------------------------------------------------------ #
    # Resolução de argumentos                                             #
    # ------------------------------------------------------------------ #

    def _get_processo(self, processo_id):
        processo = ProcessoRSCTae.objects.filter(pk=processo_id).select_related('vinculo__pessoa', 'nivel_requisitado').first()
        if processo is None:
            raise CommandError(f'ProcessoRSCTae #{processo_id} não encontrado.')
        if processo.situacao not in SituacaoProcesso.FINAIS:
            raise CommandError(
                f'Processo #{processo_id} não está finalizado (situação atual: {processo.get_situacao_display()}). '
                'Só é possível reverter processos DEFERIDO/INDEFERIDO.'
            )
        self.stdout.write(f'Processo #{processo_id} — {processo.vinculo} — situação: {processo.get_situacao_display()}.')
        return processo

    def _get_responsavel(self, responsavel_vinculo_id):
        if not responsavel_vinculo_id:
            return None
        responsavel = Vinculo.objects.filter(pk=responsavel_vinculo_id).first()
        if responsavel is None:
            raise CommandError(f'Vinculo responsável #{responsavel_vinculo_id} não encontrado.')
        return responsavel


class _Rollback(Exception):
    """Sentinela para forçar rollback da transação em modo simulação."""
