"""
Management command: remover_avaliador_processo

Remove avaliadores designados indevidamente de um processo RSC-TAE, **sem repor**, e
gravando tudo o que a remoção exige para o processo não ficar inconsistente.

Existe porque tirar o avaliador apenas do M2M — o que o formulário do admin faz — deixa
três rastros ativos, e nenhum dos cálculos do módulo lê o M2M:

  * ``AvaliacaoProcessoRSCTae`` continua com ``substituido=False``, então a nota do
    removido segue entrando em ``media_pontuacao_avaliadores`` e em
    ``todos_avaliadores_finalizaram``;
  * as ``AvaliacaoAnexoRSCTae`` dele continuam nas divergências que a CRSC delibera
    (``_listar_divergencias_para_crsc`` lê todas as avaliações do processo);
  * não fica registro de quem removeu, quando e por quê.

Para trocar um avaliador por outro (1:1, com sorteio do substituto) o caminho é a tela
"Remanejar avaliador" — este comando é para o excedente, quando sobra gente designada.

Regras aplicadas antes de tocar em qualquer coisa:

  * o processo precisa estar em Em Análise ou Aguardando Deliberação da CRSC;
  * precisam restar pelo menos três avaliadores ativos (abaixo disso, o caminho é o
    remanejamento, que repõe);
  * não pode haver voto de deliberação final nem deliberação consolidada — remover
    mudaria a pontuação por baixo de votos já registrados. Nesse caso, rode antes
    ``reverter_deliberacao_final``.

Por segurança, roda em modo simulação por padrão: só grava com ``--commit``.

Uso:
    # Ver os avaliadores atuais, a média e as divergências
    python manage.py remover_avaliador_processo 601 --listar

    # Aplicar
    python manage.py remover_avaliador_processo 601 --avaliador-matricula 1234 \
        --motivo "Designado indevidamente pelo formulário do admin" \
        --responsavel-matricula 4321 --commit
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comum.models import Vinculo
from rsc_tae.enums import SituacaoProcesso
from rsc_tae.management.commands._saneamento import (
    Rollback,
    adicionar_argumentos_comuns,
    exigir_motivo,
    get_processo,
    get_responsavel,
    get_vinculo_por_matricula,
)
from rsc_tae.models import AvaliacaoAnexoRSCTae, AvaliacaoProcessoRSCTae, ProcessoRSCTae, SorteioAvaliadorRSCTae
from rsc_tae.views._helpers import _listar_divergencias_para_crsc

# Remover abaixo do número que o regulamento exige não é saneamento, é desfalque.
MINIMO_AVALIADORES = ProcessoRSCTae.QUANTIDADE_AVALIADORES

SITUACOES_PERMITIDAS = (SituacaoProcesso.EM_ANALISE, SituacaoProcesso.AGUARDANDO_CRSC)


class Command(BaseCommand):
    help = 'Remove avaliadores designados indevidamente de um processo RSC-TAE, limpando as avaliações e registrando a auditoria.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('processo_id', type=int, help='ID do ProcessoRSCTae.')
        alvos = parser.add_mutually_exclusive_group()
        alvos.add_argument(
            '--avaliador-vinculo',
            type=int,
            nargs='+',
            dest='avaliador_vinculos',
            help='ID(s) do(s) Vinculo do(s) avaliador(es) a remover. Alternativa a --avaliador-matricula.',
        )
        alvos.add_argument(
            '--avaliador-matricula',
            nargs='+',
            dest='avaliador_matriculas',
            help='Matrícula(s) do(s) avaliador(es) a remover. Alternativa a --avaliador-vinculo.',
        )
        parser.add_argument(
            '--listar',
            action='store_true',
            dest='listar',
            help='Mostra os avaliadores atuais, a média e as divergências, sem alterar nada.',
        )
        adicionar_argumentos_comuns(parser)

    def handle(self, *args, **options) -> None:
        processo = get_processo(options['processo_id'])
        self.stdout.write(f'Processo #{processo.pk} — {processo.vinculo} — situação: {processo.get_situacao_display()}.')

        if options.get('listar'):
            self._listar_avaliadores(processo)
            return

        self._validar_situacao(processo)
        self._validar_deliberacao(processo)
        alvos = self._resolver_alvos(processo, options.get('avaliador_vinculos') or [], options.get('avaliador_matriculas') or [])
        self._validar_minimo(processo, alvos)

        motivo = exigir_motivo(options.get('motivo'))
        responsavel = get_responsavel(options.get('responsavel_vinculo'), options.get('responsavel_matricula'))

        self._imprimir_resumo(processo, 'Antes')
        try:
            with transaction.atomic():
                for vinculo in alvos:
                    self._remover(processo, vinculo, motivo, responsavel)
                self._imprimir_resumo(processo, 'Depois')
                if not options['commit']:
                    raise Rollback
        except Rollback:
            self.stdout.write(self.style.WARNING('\nSIMULAÇÃO — nenhuma alteração foi gravada. Rode com --commit para aplicar.'))
            return

        nomes = ', '.join(str(v) for v in alvos)
        self.stdout.write(self.style.SUCCESS(f'\nProcesso #{processo.pk}: removido(s) {nomes}.'))

    # ------------------------------------------------------------------ #
    # Validações                                                          #
    # ------------------------------------------------------------------ #

    def _validar_situacao(self, processo: ProcessoRSCTae) -> None:
        if processo.situacao in SITUACOES_PERMITIDAS:
            return
        labels = dict(SituacaoProcesso.get_choices())
        permitidas = ' ou '.join(str(labels.get(s, s)) for s in SITUACOES_PERMITIDAS)
        raise CommandError(
            f'Processo #{processo.pk} está em {processo.get_situacao_display()}. Só é possível remover avaliador com o processo em {permitidas}.'
        )

    def _validar_deliberacao(self, processo: ProcessoRSCTae) -> None:
        """Recusa quando a CRSC já votou sobre as notas atuais — remover as mudaria por baixo dos votos."""
        if getattr(processo, 'deliberacao_crsc', None) is not None:
            raise CommandError(
                f'Processo #{processo.pk} já tem deliberação final consolidada. Rode antes "reverter_deliberacao_final" para desfazê-la.'
            )
        votos = processo.votos_deliberacao_final.count()
        if votos:
            raise CommandError(
                f'Processo #{processo.pk} já tem {votos} voto(s) de deliberação final sobre as notas atuais. '
                'Remover um avaliador mudaria a pontuação consolidada por baixo desses votos — '
                'rode antes "reverter_deliberacao_final".'
            )

    def _resolver_alvos(self, processo: ProcessoRSCTae, vinculo_ids: list, matriculas: list) -> list[Vinculo]:
        if not vinculo_ids and not matriculas:
            raise CommandError('Informe quem sai em --avaliador-vinculo ou --avaliador-matricula (ou rode com --listar para ver os atuais).')

        alvos = [self._vinculo_por_id(pk) for pk in vinculo_ids] + [get_vinculo_por_matricula(m) for m in matriculas]
        self._recusar_repetidos(alvos)
        designados = {v.id for v in processo.avaliadores.all()}
        for vinculo in alvos:
            if vinculo.id not in designados:
                raise CommandError(f'{vinculo} não está designado como avaliador do processo #{processo.pk}.')
        return alvos

    def _recusar_repetidos(self, alvos: list) -> None:
        """Repetição não é idempotente aqui: o registro de auditoria da remoção sairia duplicado.

        O ``remove()`` do M2M e os ``update``/``delete`` das avaliações não se importam com a
        repetição, mas cada passada cria um ``SorteioAvaliadorRSCTae`` — e a contagem do mínimo,
        que usa ``len(alvos)``, veria duas saídas onde só há uma pessoa.
        """
        vistos = set()
        for vinculo in alvos:
            if vinculo.id in vistos:
                raise CommandError(f'{vinculo} foi informado mais de uma vez. Cada avaliador deve aparecer uma única vez.')
            vistos.add(vinculo.id)

    def _vinculo_por_id(self, vinculo_id: int) -> Vinculo:
        vinculo = Vinculo.objects.filter(pk=vinculo_id).first()
        if vinculo is None:
            raise CommandError(f'Vinculo #{vinculo_id} não encontrado.')
        return vinculo

    def _validar_minimo(self, processo: ProcessoRSCTae, alvos: list) -> None:
        restantes = processo.avaliadores.count() - len(alvos)
        if restantes >= MINIMO_AVALIADORES:
            return
        raise CommandError(
            f'A remoção deixaria {restantes} avaliador(es) no processo #{processo.pk}, e o regulamento exige três. '
            'Para trocar um avaliador por outro use a tela "Remanejar avaliador", que sorteia o substituto.'
        )

    # ------------------------------------------------------------------ #
    # Remoção                                                             #
    # ------------------------------------------------------------------ #

    def _remover(self, processo: ProcessoRSCTae, vinculo: Vinculo, motivo: str, responsavel: Vinculo | None) -> None:
        """Tira o avaliador do processo fechando os três rastros que o M2M sozinho deixaria ativos."""
        atualizadas = AvaliacaoProcessoRSCTae.objects.filter(processo=processo, avaliador_vinculo=vinculo).update(substituido=True)
        apagadas, _ = AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=processo, avaliador_vinculo=vinculo).delete()
        processo.avaliadores.remove(vinculo)
        SorteioAvaliadorRSCTae.objects.create(
            processo=processo,
            avaliador_sorteado=None,
            avaliador_substituido=vinculo,
            motivo=SorteioAvaliadorRSCTae.MOTIVO_REMOCAO_ADMINISTRATIVA,
            justificativa=motivo,
            realizado_por_vinculo=responsavel,
        )
        self.stdout.write(
            f'- {vinculo}: removido do processo; {atualizadas} avaliação(ões) marcada(s) como substituída(s) '
            f'e {apagadas} avaliação(ões) de anexo apagada(s).'
        )

    # ------------------------------------------------------------------ #
    # Saída                                                               #
    # ------------------------------------------------------------------ #

    def _listar_avaliadores(self, processo: ProcessoRSCTae) -> None:
        avaliacoes = {a.avaliador_vinculo_id: a for a in processo.avaliacoes_por_avaliador.all()}
        self.stdout.write('\nAvaliadores designados:')
        for vinculo in processo.avaliadores.select_related('pessoa'):
            avaliacao = avaliacoes.get(vinculo.id)
            matricula = getattr(vinculo.relacionamento, 'matricula', '') or '—'
            estado = 'sem avaliação registrada'
            if avaliacao:
                estado = f'finalizada (pontuação {avaliacao.pontuacao_final})' if avaliacao.finalizada else 'em andamento'
            self.stdout.write(f'  - matrícula {matricula} — {vinculo} — {estado}.')
        self._imprimir_resumo(processo, 'Situação atual')

    def _imprimir_resumo(self, processo: ProcessoRSCTae, rotulo: str) -> None:
        """Os três números que a remoção move — é por eles que se confere o efeito."""
        self.stdout.write(
            f'{rotulo}: {processo.avaliadores.count()} avaliador(es) ativo(s), '
            f'média {processo.media_pontuacao_avaliadores}, '
            f'{len(_listar_divergencias_para_crsc(processo))} divergência(s) para a CRSC.'
        )
