"""
Management command: alterar_situacao_processo

Move um processo RSC-TAE para outra situação **pelo caminho autorizado**
(``ProcessoRSCTae.transicionar``), validando a transição contra
``SituacaoProcesso.TRANSICOES`` e gravando ``HistoricoSituacaoProcessoRSCTae``
com motivo, responsável e origem.

Existe por causa do que acontece quando a situação é alterada direto no formulário
do admin: o campo muda, mas nenhum histórico é gravado. Como a listagem ordena por
``expressao_data_entrada_situacao_atual`` — que é ``Coalesce(<última entrada na
situação atual>, data_cadastro)`` —, sem o registro de histórico a expressão cai na
data de cadastro e um processo antigo aparece no TOPO da fila da etapa, e não no fim.
Aplicar a mudança por aqui devolve o processo à posição correta.

O que este comando NÃO faz:

  * **Deferir ou indeferir.** Os estados finais são alcançados apenas pela deliberação
    da CRSC, que exige quórum, consolida as divergências e credita o banco de pontos.
    Passar por fora deixaria o processo finalizado sem nada disso.
  * **Reverter um processo finalizado.** Para isso existe ``reverter_deliberacao_final``,
    que também estorna o banco de pontos e limpa os campos de finalização.

Pré-condições do destino (avaliadores que ainda não finalizaram, processo sem avaliador
designado, documento preliminar ausente) são exibidas como AVISO, não como bloqueio: a
ferramenta é de saneamento e costuma ser usada justamente sobre registros que já estão
inconsistentes. O motivo informado fica no histórico.

Por segurança, roda em modo simulação por padrão: só grava com ``--commit``.

Uso:
    # Ver a situação atual, a posição na fila e os destinos válidos
    python manage.py alterar_situacao_processo 601 --listar

    # Aplicar
    python manage.py alterar_situacao_processo 601 --para aguardando-crsc \
        --motivo "Situação alterada pelo admin sem registro de histórico" \
        --responsavel-matricula 1234 --commit
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.management.commands._saneamento import Rollback, adicionar_argumentos_comuns, exigir_motivo, get_processo, get_responsavel
from rsc_tae.models import DocumentoPreliminarRSCTae, OrigemTransicao, ProcessoRSCTae


def mapa_de_slugs() -> dict[str, int]:
    """``{'aguardando-crsc': 9, ...}`` — um slug por situação declarada em ``SituacaoProcesso``.

    O nome do slug vem da constante (legível, sem acento); o conjunto do que é situação vem de
    ``LABELS``, a fonte declarativa. Cruzar os dois evita que uma constante int qualquer
    acrescentada à classe no futuro vire um pseudo-slug aceito por ``--para``.

    Os dois estados legados continuam com slug de propósito: há processos antigos parados neles,
    e o saneamento precisa alcançá-los.
    """
    situacoes = dict(SituacaoProcesso.get_choices())
    return {
        nome.lower().replace('_', '-'): valor
        for nome, valor in vars(SituacaoProcesso).items()
        if nome.isupper() and isinstance(valor, int) and valor in situacoes
    }


def slug_da_situacao(situacao: int) -> str:
    """Slug de uma situação (o inverso de ``mapa_de_slugs``), ou o código quando não houver."""
    return next((slug for slug, valor in mapa_de_slugs().items() if valor == situacao), str(situacao))


class Command(BaseCommand):
    help = 'Altera a situação de um processo RSC-TAE pelo caminho autorizado, gravando histórico e reposicionando-o na fila.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('processo_id', type=int, help='ID do ProcessoRSCTae.')
        parser.add_argument(
            '--para',
            dest='para',
            help='Situação de destino, por slug (ex.: aguardando-crsc) ou código numérico. Use --listar para ver as válidas.',
        )
        parser.add_argument(
            '--listar',
            action='store_true',
            dest='listar',
            help='Mostra a situação atual, a posição na fila e os destinos válidos, sem alterar nada.',
        )
        adicionar_argumentos_comuns(parser)

    def handle(self, *args, **options) -> None:
        processo = get_processo(options['processo_id'])
        self._imprimir_cabecalho(processo)

        if options.get('listar'):
            self._listar_destinos(processo)
            return

        destino = self._destino_valido(processo, options.get('para'))
        motivo = exigir_motivo(options.get('motivo'))
        responsavel = get_responsavel(options.get('responsavel_vinculo'), options.get('responsavel_matricula'))
        self._avisar_precondicoes(processo, destino)

        try:
            with transaction.atomic():
                processo.transicionar(destino, motivo=motivo, por_vinculo=responsavel, origem=OrigemTransicao.MANUAL)
                self._imprimir_posicao(processo, 'Posição na fila após a mudança')
                if not options['commit']:
                    raise Rollback
        except Rollback:
            self.stdout.write(self.style.WARNING('\nSIMULAÇÃO — nenhuma alteração foi gravada. Rode com --commit para aplicar.'))
            return

        self.stdout.write(self.style.SUCCESS(f'\nProcesso #{processo.pk} movido para {processo.get_situacao_display()}.'))

    # ------------------------------------------------------------------ #
    # Resolução e validação do destino                                    #
    # ------------------------------------------------------------------ #

    def _destino_valido(self, processo: ProcessoRSCTae, para: str | None) -> int:
        """Destino resolvido e aceito, ou ``CommandError`` explicando a recusa."""
        if not para:
            raise CommandError('Informe o destino em --para (rode com --listar para ver os destinos válidos).')

        destino = self._resolver_situacao(para)
        atual = processo.situacao

        if atual in SituacaoProcesso.FINAIS:
            raise CommandError(
                f'Processo #{processo.pk} está finalizado ({processo.get_situacao_display()}). '
                'Rode "reverter_deliberacao_final" para devolvê-lo à deliberação da CRSC — ele também estorna o banco de pontos.'
            )
        if destino in SituacaoProcesso.FINAIS:
            raise CommandError(
                'Deferimento e indeferimento só podem ser registrados pela deliberação da CRSC, que exige quórum, '
                'consolida as divergências e credita o banco de pontos. Este comando não substitui esse rito.'
            )
        if destino == atual:
            raise CommandError(f'Processo #{processo.pk} já está em {processo.get_situacao_display()}.')
        if not SituacaoProcesso.pode_transicionar(atual, destino):
            labels = dict(SituacaoProcesso.get_choices())
            raise CommandError(
                f'{labels.get(atual, atual)} → {labels.get(destino, destino)} não é uma transição válida. '
                f'Destinos válidos: {self._descrever_destinos(processo) or "nenhum"}.'
            )
        return destino

    def _resolver_situacao(self, texto: str) -> int:
        """Aceita slug (``aguardando-crsc``/``aguardando_crsc``) ou código numérico."""
        chave = texto.strip().lower().replace('_', '-')
        slugs = mapa_de_slugs()
        if chave.isdigit():
            codigo = int(chave)
            if codigo not in dict(SituacaoProcesso.get_choices()):
                raise CommandError(f'Código de situação desconhecido: {texto}.')
            return codigo
        if chave not in slugs:
            raise CommandError(f'Situação desconhecida: "{texto}". Valores aceitos: {", ".join(sorted(slugs))}.')
        return slugs[chave]

    def _descrever_destinos(self, processo: ProcessoRSCTae) -> str:
        """Slugs dos destinos válidos e não finais, para as mensagens de erro e a listagem."""
        labels = dict(SituacaoProcesso.get_choices())
        destinos = [s for s in SituacaoProcesso.transicoes_validas(processo.situacao) if s not in SituacaoProcesso.FINAIS]
        return ', '.join(f'{slug_da_situacao(s)} ({labels.get(s, s)})' for s in destinos)

    # ------------------------------------------------------------------ #
    # Saída                                                               #
    # ------------------------------------------------------------------ #

    def _imprimir_cabecalho(self, processo: ProcessoRSCTae) -> None:
        self.stdout.write(f'Processo #{processo.pk} — {processo.vinculo} — situação: {processo.get_situacao_display()}.')
        self._imprimir_posicao(processo, 'Posição na fila atual')

    def _imprimir_posicao(self, processo: ProcessoRSCTae, rotulo: str) -> None:
        fila = processo.posicao_na_fila()
        if fila is None:
            self.stdout.write(f'- {rotulo}: a etapa não tem fila de espera.')
            return
        self.stdout.write(f'- {rotulo}: {fila["posicao"]}º de {fila["total"]}.')

    def _listar_destinos(self, processo: ProcessoRSCTae) -> None:
        destinos = self._descrever_destinos(processo)
        if not destinos:
            self.stdout.write(self.style.WARNING('\nNenhum destino disponível por este comando a partir da situação atual.'))
            return
        self.stdout.write(f'\nDestinos válidos: {destinos}.')
        self.stdout.write('Use --para <slug> --motivo "..." --commit para aplicar.')
        if processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC:
            self.stdout.write('Deferir/indeferir não sai daqui: é a deliberação da CRSC que finaliza o processo.')

    def _avisar_precondicoes(self, processo: ProcessoRSCTae, destino: int) -> None:
        """Exibe o que normalmente teria acontecido antes desta transição no fluxo automático.

        São avisos, e não bloqueios: o comando é usado sobre registros já inconsistentes,
        e travar aqui impediria justamente o saneamento. O motivo fica no histórico.
        """
        avisos = self._precondicoes_pendentes(processo, destino)
        if not avisos:
            return
        self.stdout.write(self.style.WARNING('\nATENÇÃO — pré-condições que o fluxo normal teria satisfeito:'))
        for aviso in avisos:
            self.stdout.write(self.style.WARNING(f'  - {aviso}'))

    def _precondicoes_pendentes(self, processo: ProcessoRSCTae, destino: int) -> list[str]:
        if destino == SituacaoProcesso.AGUARDANDO_CRSC:
            return self._pendencias_da_analise(processo)
        if destino == SituacaoProcesso.EM_ANALISE and not processo.avaliadores.exists():
            return ['O processo não tem avaliadores designados — normalmente o sorteio automático os define.']
        if (
            destino == SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR
            and not DocumentoPreliminarRSCTae.objects.filter(processo=processo).exists()
        ):
            return ['Nenhum documento preliminar foi enviado — não há o que o RH validar.']
        return []

    def _pendencias_da_analise(self, processo: ProcessoRSCTae) -> list[str]:
        total = processo.avaliadores.count()
        if not total:
            return ['O processo não tem avaliadores designados — a CRSC deliberaria sem parecer dos avaliadores.']
        if processo.todos_avaliadores_finalizaram:
            return []
        finalizadas = processo.avaliacoes_por_avaliador.filter(substituido=False, finalizada=True).count()
        return [f'{finalizadas} de {total} avaliações finalizadas — a CRSC deliberaria sobre uma avaliação incompleta.']
