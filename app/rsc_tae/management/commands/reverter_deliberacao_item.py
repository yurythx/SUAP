"""
Management command: reverter_deliberacao_item

Reabre a deliberação de um ou mais ITENS divergentes de um processo RSC-TAE que está
em ``AGUARDANDO_CRSC``, removendo o voto de item (``DeliberacaoItemCRSCRSCTae``) dos
membros indicados.

Ao contrário de ``reverter_deliberacao_final`` — que atua na fase final (votos de
resultado + deliberação consolidada) e exige um processo já finalizado —, este comando
atua na fase anterior: a votação por anexo divergente. A situação do processo **não**
muda; ele já está no estado correto (``AGUARDANDO_CRSC``).

O que trava a edição de um voto de item não é a situação do processo, e sim o quórum
do item: ``deliberar_item_crsc`` bloqueia quando ``status_deliberacao_item`` retorna
``fechado``. Removendo o voto, o total cai abaixo da quantidade configurada, o item
reabre e o membro registra o voto de novo pela própria tela.

Isso vale enquanto o anexo tiver exatamente a quantidade configurada de votos. Se tiver
mais (corrida entre membros submetendo ao mesmo tempo, quórum reduzido na configuração
depois do fechamento, dado legado), remover um voto não derruba o quórum e o item segue
bloqueado — o comando detecta esse caso e avisa em vez de anunciar uma reabertura que
não aconteceu.

Efeitos colaterais tratados:

  * **Voto de desempate**: se o item tinha voto de desempate do presidente, ele é
    removido junto — o desempate foi decidido sobre um conjunto de votos que deixou de
    existir e, mantido, poderia fechar o item indevidamente na rodada seguinte.
  * **Votos da deliberação final**: se os membros já votaram o resultado final sobre as
    notas atuais, reabrir um item mudaria a pontuação consolidada por baixo desses
    votos. O comando aborta, salvo com ``--remover-votos-finais``.

A reabertura vale para o ITEM, não só para o membro: enquanto o quórum não voltar a
fechar, qualquer membro pode rever o próprio voto naquele anexo.

``--somente-desempate`` inverte o alvo: em vez dos votos normais, remove o voto de
minerva. Serve ao caso em que o desempate foi registrado indevidamente e os votos dos
membros continuam válidos — o presidente pode ter só a minerva no anexo (o empate
fechou entre os outros membros antes de ele votar), e aí nenhum filtro por membro o
alcança no modo normal, que enxerga apenas ``desempate=False``.

Removida a minerva, o item NÃO volta a aceitar votos normais: com o quórum ainda
completo e a moda empatada, ``status_deliberacao_item`` devolve ``aguardando_desempate``
e a tela libera apenas o presidente para desempatar de novo. É a forma cirúrgica de
desfazer um desempate — nenhum membro precisa revotar.

Por segurança, roda em modo simulação por padrão: só grava com ``--commit``.

Uso:
    # Um membro refaz o voto em um anexo específico
    python manage.py reverter_deliberacao_item 378 --anexo 11473 --membro-matricula 1234 --commit

    # Um membro refaz todos os votos de item dele no processo
    python manage.py reverter_deliberacao_item 378 --membro-vinculo 999 --commit

    # Reabre o item inteiro para todos os membros
    python manage.py reverter_deliberacao_item 378 --anexo 11473 --todos-votos --commit

    # Desfaz SÓ o voto de desempate do presidente, preservando os votos dos membros
    python manage.py reverter_deliberacao_item 378 --anexo 11473 --membro-matricula 1234 --somente-desempate --commit
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import DeliberacaoItemCRSCRSCTae, ProcessoRSCTae
from rsc_tae.views._helpers import quantidade_deliberacoes_item, status_deliberacao_item


class Command(BaseCommand):
    help = 'Reabre a deliberação de itens divergentes de um processo RSC-TAE, removendo o voto de item dos membros indicados.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('processo_id', type=int, help='ID do ProcessoRSCTae cujos itens serão reabertos.')
        parser.add_argument(
            '--anexo',
            type=int,
            nargs='+',
            dest='anexos',
            help='ID(s) do(s) RolSaberCompetenciaAnexo a reabrir. Sem esta opção, atinge todos os itens votados pelos membros selecionados.',
        )
        grupo_votos = parser.add_mutually_exclusive_group(required=True)
        grupo_votos.add_argument(
            '--membro-vinculo',
            type=int,
            nargs='+',
            dest='membro_vinculos',
            help='ID(s) do(s) Vinculo do(s) membro(s) cujo(s) voto(s) de item devem ser removidos.',
        )
        grupo_votos.add_argument(
            '--membro-matricula',
            nargs='+',
            dest='membro_matriculas',
            help='Matrícula(s) do(s) servidor(es) membro(s) cujo(s) voto(s) de item devem ser removidos. Alternativa a --membro-vinculo.',
        )
        grupo_votos.add_argument(
            '--todos-votos',
            action='store_true',
            dest='todos_votos',
            help='Remove os votos de TODOS os membros nos itens selecionados, reabrindo a rodada inteira daqueles itens.',
        )
        parser.add_argument(
            '--somente-desempate',
            action='store_true',
            dest='somente_desempate',
            help='Remove o voto de DESEMPATE (minerva) em vez dos votos normais, preservando os votos dos membros. '
            'O item volta a aguardar o desempate do presidente, sem que ninguém precise revotar. '
            'Combine com --membro-* para mirar o presidente, ou com --todos-votos para todas as minervas do escopo.',
        )
        parser.add_argument(
            '--remover-votos-finais',
            action='store_true',
            dest='remover_votos_finais',
            help='Remove também os votos da deliberação final já registrados (necessário quando os membros já votaram o resultado). '
            'Atinge os votos finais de TODOS os membros, mesmo selecionando um único membro nos votos de item — a pontuação '
            'consolidada muda para todos, então nenhum voto final continua válido.',
        )
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Aplica as alterações. Sem esta flag, o comando apenas simula (rollback ao final).',
        )

    def handle(self, *args, **options) -> None:
        processo = self._get_processo(options['processo_id'])
        self.itens_ainda_consolidados: list[int] = []
        self.itens_aguardando_desempate: list[int] = []
        self.itens_reabertos: list[int] = []

        try:
            with transaction.atomic():
                self._reverter(processo, options)
                if not options['commit']:
                    raise _Rollback
        except _Rollback:
            self.stdout.write(self.style.WARNING('\nSIMULAÇÃO — nenhuma alteração foi gravada. Rode com --commit para aplicar.'))
            return

        if self.itens_ainda_consolidados:
            anexos = ', '.join(f'#{anexo_id}' for anexo_id in self.itens_ainda_consolidados)
            self.stdout.write(
                self.style.WARNING(
                    f'\nReabertura PARCIAL no processo #{processo.pk}: o(s) anexo(s) {anexos} continuam consolidados '
                    'e seguem bloqueados na tela. Remova mais votos desses itens (ou use --todos-votos) para reabri-los.'
                )
            )
            return

        self.stdout.write(self.style.SUCCESS(f'\n{self._mensagem_final(processo)}'))

    def _mensagem_final(self, processo: ProcessoRSCTae) -> str:
        """Fecho do comando conforme o estado alcançado.

        Anunciar "reabertos para nova deliberação" no modo ``--somente-desempate`` convocaria a
        comissão a revotar um item que só espera a minerva — o oposto do que a flag faz. Como é a
        última linha que o operador lê na tela de manutenção, ela precisa refletir o estado real.
        """
        aguardando = ', '.join(f'#{anexo_id}' for anexo_id in self.itens_aguardando_desempate)
        reabertos = ', '.join(f'#{anexo_id}' for anexo_id in self.itens_reabertos)
        if self.itens_aguardando_desempate and self.itens_reabertos:
            return f'Processo #{processo.pk}: anexo(s) {reabertos} reaberto(s) para nova deliberação; anexo(s) {aguardando} aguardando o desempate do presidente.'
        if self.itens_aguardando_desempate:
            return f'Processo #{processo.pk}: anexo(s) {aguardando} aguardando o desempate do presidente — nenhum membro precisa revotar.'
        return f'Itens do processo #{processo.pk} reabertos para nova deliberação.'

    # ------------------------------------------------------------------ #
    # Passos da reabertura                                                #
    # ------------------------------------------------------------------ #

    def _reverter(self, processo: ProcessoRSCTae, options: dict) -> None:
        somente_desempate = options.get('somente_desempate') or False
        votos = self._selecionar_votos(
            processo,
            anexos=options.get('anexos') or [],
            membro_vinculos=options.get('membro_vinculos') or [],
            membro_matriculas=options.get('membro_matriculas') or [],
            todos_votos=options.get('todos_votos') or False,
            somente_desempate=somente_desempate,
        )
        anexo_ids = {voto.anexo_id for voto in votos}

        self._tratar_votos_finais(processo, options.get('remover_votos_finais') or False)
        self._remover_votos(votos, somente_desempate)
        # No modo minerva os próprios alvos já são os desempates; varrer o anexo atrás de outros
        # derrubaria minervas de membros que não foram pedidos.
        if not somente_desempate:
            self._remover_desempates(processo, anexo_ids, [voto.pk for voto in votos])
        self._relatar_status(processo, anexo_ids)

    def _selecionar_votos(
        self,
        processo: ProcessoRSCTae,
        anexos: list,
        membro_vinculos: list,
        membro_matriculas: list,
        todos_votos: bool,
        somente_desempate: bool = False,
    ) -> list:
        """Votos de item que serão removidos, conforme os filtros de membro e de anexo.

        Por padrão mira os votos normais (``desempate=False``); com ``somente_desempate``,
        mira os votos de minerva.
        """
        consulta = processo.deliberacoes_item_crsc.filter(desempate=somente_desempate)
        if anexos:
            consulta = consulta.filter(anexo_id__in=anexos)
        if not todos_votos:
            filtro = Q()
            if membro_vinculos:
                filtro |= Q(deliberado_por_vinculo_id__in=membro_vinculos)
            if membro_matriculas:
                filtro |= Q(deliberado_por_vinculo__pessoa__pessoafisica__servidor_set__matricula__in=membro_matriculas)
            consulta = consulta.filter(filtro)

        votos = list(consulta.select_related('deliberado_por_vinculo__pessoa', 'anexo').distinct())
        if not votos:
            criterio = 'todos os membros' if todos_votos else (membro_matriculas or membro_vinculos)
            escopo = f' nos anexos {anexos}' if anexos else ''
            tipo = 'voto de desempate' if somente_desempate else 'voto de item'
            raise CommandError(f'Nenhum {tipo} encontrado para {criterio}{escopo} neste processo.')
        return votos

    def _tratar_votos_finais(self, processo: ProcessoRSCTae, remover: bool) -> None:
        """Bloqueia (ou remove, com a flag) os votos da deliberação final já registrados sobre as notas atuais."""
        votos = list(processo.votos_deliberacao_final.select_related('deliberado_por_vinculo__pessoa'))
        if not votos:
            return
        if not remover:
            raise CommandError(
                f'O processo já tem {len(votos)} voto(s) de deliberação final registrados sobre as notas atuais. '
                'Reabrir um item mudaria a pontuação consolidada por baixo desses votos. '
                'Rode novamente com --remover-votos-finais para removê-los junto (os membros votarão o resultado final de novo).'
            )
        for voto in votos:
            self.stdout.write(f'- Removendo voto de deliberação FINAL #{voto.pk} do membro {voto.deliberado_por_vinculo}.')
        processo.votos_deliberacao_final.all().delete()

    def _remover_votos(self, votos: list, somente_desempate: bool = False) -> None:
        rotulo = 'voto de DESEMPATE' if somente_desempate else 'voto de item'
        for voto in votos:
            self.stdout.write(
                f'- Removendo {rotulo} #{voto.pk} — anexo #{voto.anexo_id} — {voto.deliberado_por_vinculo} — '
                f'{voto.get_decisao_display()} (pts: {voto.pontuacao_crsc}) — hash: {voto.assinatura_hash or "—"}.'
            )
        DeliberacaoItemCRSCRSCTae.objects.filter(pk__in=[voto.pk for voto in votos]).delete()

    def _remover_desempates(self, processo: ProcessoRSCTae, anexo_ids: set, votos_removidos: list) -> None:
        """Remove os votos de desempate dos itens reabertos — o desempate valia para um conjunto de votos que deixou de existir."""
        desempates = list(
            processo.deliberacoes_item_crsc.filter(desempate=True, anexo_id__in=anexo_ids)
            .exclude(pk__in=votos_removidos)
            .select_related('deliberado_por_vinculo__pessoa')
        )
        if not desempates:
            return
        for voto in desempates:
            self.stdout.write(
                f'- Removendo voto de DESEMPATE #{voto.pk} — anexo #{voto.anexo_id} — {voto.deliberado_por_vinculo} '
                '(o desempate decidia sobre votos que foram removidos).'
            )
        DeliberacaoItemCRSCRSCTae.objects.filter(pk__in=[voto.pk for voto in desempates]).delete()

    def _relatar_status(self, processo: ProcessoRSCTae, anexo_ids: set) -> None:
        """Informa, por anexo atingido, em que estado o item ficou depois da remoção.

        Remover um voto nem sempre reabre o item: se o anexo tinha mais votos que o quórum (corrida
        entre membros na tela, quórum reduzido na configuração depois do fechamento, dado legado), o
        total continua fechando. Os anexos nessa condição ficam em ``itens_ainda_consolidados`` para
        que a mensagem final não anuncie uma reabertura que não houve.

        No modo ``--somente-desempate`` o quórum permanece completo de propósito: o item não reabre
        para votos normais, volta a aguardar a minerva do presidente.
        """
        quantidade = quantidade_deliberacoes_item()
        self.stdout.write(f'\nSituação dos itens após a remoção (quantidade necessária: {quantidade}):')
        for anexo_id in sorted(anexo_ids):
            votos = list(processo.deliberacoes_item_crsc.filter(anexo_id=anexo_id))
            status = status_deliberacao_item(votos, quantidade)
            if status['fechado']:
                self.itens_ainda_consolidados.append(anexo_id)
            elif status['aguardando_desempate']:
                self.itens_aguardando_desempate.append(anexo_id)
            else:
                self.itens_reabertos.append(anexo_id)
            self.stdout.write(f'  - anexo #{anexo_id}: {self._detalhe_status(status, quantidade)}.')
        self._avisar_consolidados()
        self._orientar_proximo_passo()

    def _detalhe_status(self, status: dict, quantidade: int) -> str:
        """Frase que descreve o estado de um anexo após a remoção.

        A frase do empate é neutra quanto ao modo: ela também é alcançada no modo normal,
        quando o anexo tinha mais votos que o quórum e a remoção deixou a moda empatada —
        aí os votos restantes não "foram mantidos", sobraram.
        """
        if status['fechado']:
            return (
                f'AINDA CONSOLIDADO (nota {status["nota_consolidada"]}) — restaram {status["total"]} voto(s), '
                f'o quórum de {quantidade} continua fechado e a tela segue bloqueada'
            )
        if status['aguardando_desempate']:
            return f'aguardando desempate — restaram {status["total"]} voto(s) dos membros, empatados; só o presidente vota'
        return f'reaberto — {status["total"]} de {quantidade} voto(s); faltam {quantidade - status["total"]}'

    def _avisar_consolidados(self) -> None:
        if not self.itens_ainda_consolidados:
            return
        anexos = ', '.join(f'#{anexo_id}' for anexo_id in self.itens_ainda_consolidados)
        self.stdout.write(
            self.style.WARNING(
                f'\nATENÇÃO: o(s) anexo(s) {anexos} tinham mais votos que o quórum e continuam consolidados '
                'mesmo após a remoção — a tela seguirá bloqueada neles. Remova mais votos desses itens '
                '(ou use --todos-votos) para que reabram de fato.'
            )
        )

    def _orientar_proximo_passo(self) -> None:
        """Orientação por estado alcançado — um lote misto recebe as duas, cada uma com seus anexos."""
        if self.itens_aguardando_desempate:
            anexos = ', '.join(f'#{anexo_id}' for anexo_id in self.itens_aguardando_desempate)
            self.stdout.write(
                f'\nAnexo(s) {anexos}: o presidente da comissão registra o desempate pela tela de Deliberação da CRSC '
                'do processo. Os votos dos membros continuam valendo — ninguém precisa revotar.'
            )
        if not self.itens_reabertos:
            return
        self.stdout.write(
            '\nOs membros reabrem o item pela tela de Deliberação da CRSC do processo e registram o voto novamente. '
            'Enquanto o quórum não fechar, qualquer membro pode rever o próprio voto nesses itens.'
        )

    # ------------------------------------------------------------------ #
    # Resolução de argumentos                                             #
    # ------------------------------------------------------------------ #

    def _get_processo(self, processo_id: int) -> ProcessoRSCTae:
        processo = ProcessoRSCTae.objects.filter(pk=processo_id).select_related('vinculo__pessoa', 'nivel_requisitado').first()
        if processo is None:
            raise CommandError(f'ProcessoRSCTae #{processo_id} não encontrado.')
        if processo.situacao in SituacaoProcesso.FINAIS:
            raise CommandError(
                f'Processo #{processo_id} está finalizado (situação atual: {processo.get_situacao_display()}). '
                'Rode antes "reverter_deliberacao_final" para devolvê-lo a AGUARDANDO_CRSC.'
            )
        if processo.situacao != SituacaoProcesso.AGUARDANDO_CRSC:
            raise CommandError(
                f'Processo #{processo_id} não está em deliberação da CRSC (situação atual: {processo.get_situacao_display()}). '
                'Só é possível reabrir itens de processos em AGUARDANDO_CRSC.'
            )
        if getattr(processo, 'deliberacao_crsc', None) is not None:
            raise CommandError(
                f'Processo #{processo_id} ainda tem uma deliberação de finalização consolidada. '
                'Rode antes "reverter_deliberacao_final" para removê-la.'
            )
        self.stdout.write(f'Processo #{processo_id} — {processo.vinculo} — situação: {processo.get_situacao_display()}.')
        return processo


class _Rollback(Exception):
    """Sentinela para forçar rollback da transação em modo simulação."""
