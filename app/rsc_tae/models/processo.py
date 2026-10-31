import datetime

from djtools.db import models
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Now
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from rsc_tae.enums import SituacaoProcesso


class OrigemTransicao:
    """Origem de uma transição de situação: ação humana ou rotina do sistema."""

    MANUAL = 'manual'
    AUTOMATICO = 'automatico'

    CHOICES = (
        (MANUAL, _('Manual')),
        (AUTOMATICO, _('Automático')),
    )


class TransicaoInvalidaError(Exception):
    """Transição de situação não permitida pelo mapa ``SituacaoProcesso.TRANSICOES``."""


class HistoricoSituacaoProcessoRSCTae(models.ModelPlus):
    """Registra cada transição de estado de um ProcessoRSCTae.

    Permite calcular quanto tempo o processo ficou em cada situação,
    comparar com SLAs configurados e identificar gargalos.
    """

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='historico_situacoes',
    )
    situacao_anterior = models.PositiveIntegerField(
        _('Situação anterior'),
        choices=SituacaoProcesso.get_choices(),
        null=True,
        blank=True,
        help_text=_('Situação antes da transição. Nulo na criação inicial do processo.'),
    )
    situacao_nova = models.PositiveIntegerField(
        _('Situação nova'),
        choices=SituacaoProcesso.get_choices(),
    )
    realizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Realizado por'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_historico_transicoes_set',
    )
    motivo = models.TextField(
        _('Motivo'),
        blank=True,
        help_text=_('O que motivou a mudança de situação. Obrigatório em ações manuais.'),
    )
    origem = models.CharField(
        _('Origem'),
        max_length=20,
        choices=OrigemTransicao.CHOICES,
        default=OrigemTransicao.MANUAL,
        help_text=_('Se a transição foi disparada por uma pessoa (manual) ou por rotina do sistema (automático).'),
    )
    data_transicao = models.DateTimeField(_('Data da transição'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Histórico de situação (RSC TAE)')
        verbose_name_plural = _('Histórico de situações (RSC TAE)')
        ordering = ('data_transicao',)

    def __str__(self):
        ant = self.get_situacao_anterior_display() if self.situacao_anterior else '—'
        nova = self.get_situacao_nova_display()
        return f'Processo {self.processo_id}: {ant} → {nova}'

    def classe_timeline(self) -> str:
        """Classe de status do componente ``.timeline`` do Design System para a situação nova."""
        classes = {
            SituacaoProcesso.DEFERIDO: 'success',
            SituacaoProcesso.INDEFERIDO: 'danger',
            SituacaoProcesso.EM_ANALISE: 'info',
            SituacaoProcesso.AGUARDANDO_CRSC: 'info',
            SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: 'warning',
            SituacaoProcesso.AGUARDANDO_CORRECAO: 'warning',
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: 'warning',
        }
        return classes.get(self.situacao_nova, 'default')


class ProcessoRSCTae(models.ModelPlus):
    SEARCH_FIELDS = (
        'vinculo__pessoa__nome',
        'vinculo__pessoa__pessoafisica__servidor_set__matricula',
    )

    INTERSTICIO_ANOS = 3

    # Art. 18 do regulamento: a avaliação é feita por três avaliadores auxiliares. Fonte única
    # do número — usada pelo sorteio, pela trava do formulário do admin e pelo command de remoção.
    QUANTIDADE_AVALIADORES = 3

    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name=_('Vínculo'), on_delete=models.CASCADE)
    nivel_requisitado = models.ForeignKeyPlus('rsc_tae.Nivel', verbose_name=_('Nível Requisitado'), on_delete=models.CASCADE)
    avaliador_atual = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliador atual'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_processos_como_avaliador_atual_set',
        help_text=_('Avaliador responsável por continuar/iniciar a avaliação do processo.'),
    )

    avaliadores = models.ManyToManyFieldPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliadores'),
        blank=True,
        related_name='rsc_tae_processos_como_avaliador_set',
        help_text=_('Avaliadores designados para avaliar este processo.'),
    )
    situacao = models.PositiveIntegerField(
        _('Situação'),
        choices=SituacaoProcesso.get_choices(),
        default=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO,
    )

    memorial = models.TextField(
        _('Memorial'),
        blank=True,
        help_text=_('Exposição das atividades realizadas e sua relação com o rol de saberes e competências, conforme Art. 11 do Decreto.'),
    )
    declaracao_conformidade = models.BooleanField(
        _('Declaração de conformidade'),
        default=False,
        help_text=_(
            'O servidor declara que todos os fatos apresentados ocorreram, não foram utilizados em requerimentos anteriores, e a documentação é autêntica.'
        ),
    )
    saldo_pontuacao_anterior = models.DecimalField(
        _('Saldo de pontuação anterior'),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_('Saldo de pontuação não aproveitado de concessão anterior (banco de pontos), conforme Art. 3º, §2º.'),
    )
    processo_anterior = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo anterior'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='processos_subsequentes',
        help_text=_('Referência ao processo RSC-PCCTAE de concessão anterior, quando houver.'),
    )
    data_exercicio_cargo = models.DateField(
        _('Data de exercício no cargo'),
        null=True,
        blank=True,
        help_text=_(
            'Confirmada/corrigida pela comissão na validação. Documentos com período anterior a esta data '
            'não devem ser aceitos. Se vazia, usa-se a data cadastrada do servidor.'
        ),
    )

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeField(_('Data de alteração'), auto_now=True, db_default=Now())

    avaliacao_finalizada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliação finalizada por'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_processos_finalizados_set',
    )
    data_finalizacao_avaliacao = models.DateTimeField(_('Data de finalização da avaliação'), null=True, blank=True)
    data_entrada_requerimento = models.DateTimeField(
        _('Data de entrada do requerimento'),
        null=True,
        blank=True,
        help_text=_(
            'Data-chave: momento em que o servidor concluiu o preenchimento e protocolou o requerimento. Determina prazos e a concessão do benefício.'
        ),
    )
    requerimento_arquivo = models.FileFieldPlus(
        _('Requerimento protocolado (PDF)'),
        upload_to='rsc_tae/requerimentos',
        max_length=255,
        null=True,
        blank=True,
        filetypes=['pdf'],
        help_text=_('Snapshot do requerimento (modelo Portaria MEC nº 608/2026) gerado na conclusão do preenchimento.'),
    )
    # Assinatura de integridade do preenchimento — gerada quando o servidor conclui/assina o
    # preenchimento (mesmo padrão SHA-256 de AvaliacaoProcessoRSCTae/DeliberacaoCRSCRSCTae).
    assinatura_preenchimento_hash = models.CharField(
        _('Hash da assinatura do preenchimento'),
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 do conteúdo assinado na conclusão do preenchimento. Permite detectar alterações posteriores.'),
    )
    assinatura_preenchimento_conteudo = models.TextField(
        _('Conteúdo assinado do preenchimento'),
        null=True,
        blank=True,
        help_text=_('JSON com o snapshot do processo na conclusão (servidor, nível, declarações e itens/unidades declaradas).'),
    )
    processo_eletronico = models.ForeignKeyPlus(
        'processo_eletronico.Processo',
        verbose_name=_('Processo Eletrônico'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_processos',
        help_text=_('Processo eletrônico gerado a partir do processo RSC-TAE finalizado.'),
    )
    avaliacao_motivo_indeferimento = models.TextField(_('Motivo do indeferimento'), blank=True)
    data_entrada_crsc = models.DateTimeField(
        _('Data de entrada na CRSC'),
        null=True,
        blank=True,
        help_text=_('Preenchida automaticamente quando o processo entra em "Aguardando Deliberação da CRSC".'),
    )

    class Meta:
        verbose_name = _('Processo RSC-TAE')
        verbose_name_plural = _('Processos RSC-TAE')
        ordering = ('-data_cadastro',)
        permissions = (
            ('avaliar_processorsctae', _('Pode avaliar processo RSC-TAE')),
            ('definir_avaliador_processorsctae', _('Pode definir o avaliador do processo RSC-TAE')),
            ('deliberar_crsc_processorsctae', _('Pode registrar a deliberação da CRSC em processo RSC-TAE')),
        )

    def __str__(self):
        return f'Processo {self.nivel_requisitado} - {self.vinculo}'

    def get_absolute_url(self):
        return reverse('rsc_tae:visualizar', kwargs={'id': self.pk})

    @classmethod
    def _subquery_ultima_entrada_situacao(cls):
        """Subquery da última transição para a situação atual. Devolve NULL quando não há histórico."""
        ultima_entrada_situacao = (
            HistoricoSituacaoProcessoRSCTae.objects.filter(processo_id=OuterRef('pk'), situacao_nova=OuterRef('situacao'))
            .order_by('-data_transicao')
            .values('data_transicao')[:1]
        )
        return Subquery(ultima_entrada_situacao)

    @classmethod
    def expressao_data_entrada_situacao_atual(cls):
        """Expressão ORM: quando o processo entrou na situação atual (última transição para ela).

        Fonte única da ordenação "mais antigo na fila primeiro" — usada na listagem de
        processos do admin e em Minhas Avaliações, para a ordem de avaliação ser a mesma.
        Cai para ``data_cadastro`` quando não há histórico (processos criados antes do
        histórico de situações).
        """
        from django.db.models import F
        from django.db.models.functions import Coalesce

        return Coalesce(cls._subquery_ultima_entrada_situacao(), F('data_cadastro'))

    @classmethod
    def mapa_de_posicoes(cls, situacoes=None) -> dict:
        """``{processo_id: {'posicao', 'total'}}`` para os processos das etapas que têm fila.

        UMA consulta para todas as filas pedidas, contra ``expressao_data_entrada_situacao_atual``
        — a mesma ordenação da listagem do admin e de Minhas Avaliações, com ``data_cadastro``
        desempatando. Existe para a listagem não pagar duas consultas por linha.

        A fila é sempre a etapa INTEIRA. Quem exibe não deve recalcular sobre um queryset já
        filtrado: filtrar por nível ou buscar por nome renumeraria de 1 a N dentro do resultado e
        mostraria uma posição falsa.

        Situações fora de ``COM_FILA_DE_ESPERA`` são descartadas — sem elas na lista, nem consulta
        é feita.
        """
        if situacoes is None:
            pedidas = SituacaoProcesso.COM_FILA_DE_ESPERA
        elif isinstance(situacoes, int):
            # Aceita um único valor: o parâmetro é plural, mas passar a constante solta é o erro
            # natural de quem chama, e falhar com TypeError seria uma aspereza sem ganho.
            pedidas = (situacoes,)
        else:
            pedidas = situacoes
        situacoes_com_fila = [s for s in pedidas if s in SituacaoProcesso.COM_FILA_DE_ESPERA]
        if not situacoes_com_fila:
            return {}

        linhas = (
            cls.objects.filter(situacao__in=situacoes_com_fila)
            .annotate(entrada_na_fila=cls.expressao_data_entrada_situacao_atual())
            .order_by('situacao', 'entrada_na_fila', 'data_cadastro')
            .values_list('id', 'situacao')
        )

        ids_por_situacao: dict = {}
        for processo_id, situacao in linhas:
            ids_por_situacao.setdefault(situacao, []).append(processo_id)

        mapa = {}
        for ids in ids_por_situacao.values():
            total = len(ids)
            for posicao, processo_id in enumerate(ids, start=1):
                mapa[processo_id] = {'posicao': posicao, 'total': total}
        return mapa

    def posicao_na_fila(self):
        """Posição deste processo na fila da etapa em que ele está, ou ``None`` quando não há fila.

        Devolve ``{'posicao': int, 'total': int}``. Delega a ``mapa_de_posicoes`` para que exista
        uma única implementação da ordem — duas versões divergiriam na primeira alteração.

        Só existe fila nos estados de ``SituacaoProcesso.COM_FILA_DE_ESPERA``, em que o processo
        depende de outra pessoa. Em preenchimento/correção a ação é do próprio servidor, e em
        DEFERIDO/INDEFERIDO não há mais espera — nos dois casos devolve ``None``.

        Ressalva: a ordem descreve como as listas são apresentadas, não uma ordem que o sistema
        imponha. Ninguém é impedido de validar ou deliberar fora dela, e na etapa da CRSC a mesa é
        puxada (qualquer membro pega qualquer processo). A posição informa, não promete.
        """
        if self.situacao not in SituacaoProcesso.COM_FILA_DE_ESPERA:
            return None
        return ProcessoRSCTae.mapa_de_posicoes([self.situacao]).get(self.pk)

    def anular_fases_posteriores(self) -> dict[str, int]:
        """Apaga o que foi produzido depois do preenchimento: avaliação e deliberação.

        Chamada pela devolução do processo ao servidor a partir da deliberação da CRSC. As notas
        e os votos mediram um preenchimento que vai mudar — e, se o nível pretendido mudar junto,
        muda a régua (`pontuacao_minima`, `numero_minimo_itens`) contra a qual foram dados.
        Mantê-los produziria um processo internamente contraditório, e os votos sobreviventes
        contaminariam a deliberação seguinte.

        Preserva os sorteios, porque o sorteio aconteceu e anular a avaliação não desfaz o ato,
        e o banco de pontos, que só se move na finalização e portanto nada creditou ainda.

        É reentrante: numa segunda passada apaga zero linhas. Isso permite que a view conte o
        que será removido antes da transição e que `transicionar` a chame de novo sem efeito.

        Returns:
            Contadores do que foi removido, por peça (``{'avaliacoes_anexo': 3, ...}``).
        """
        from rsc_tae.models.avaliacao import AvaliacaoAnexoRSCTae
        from rsc_tae.models.avaliacao_processo import AvaliacaoProcessoRSCTae
        from rsc_tae.models.deliberacao_crsc import DeliberacaoCRSCRSCTae
        from rsc_tae.models.deliberacao_item_crsc import DeliberacaoItemCRSCRSCTae
        from rsc_tae.models.voto_deliberacao_final import VotoDeliberacaoFinalRSCTae

        with transaction.atomic():
            removidos = {
                'avaliacoes_anexo': AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=self).delete()[0],
                'avaliacoes_processo': AvaliacaoProcessoRSCTae.objects.filter(processo=self).delete()[0],
                'deliberacoes_item': DeliberacaoItemCRSCRSCTae.objects.filter(processo=self).delete()[0],
                'votos_finais': VotoDeliberacaoFinalRSCTae.objects.filter(processo=self).delete()[0],
                # Normalmente inexistente em AGUARDANDO_CRSC (nasce na finalização), mas um processo
                # revertido por `reverter_deliberacao_final` pode chegar aqui com resíduo dela.
                'deliberacoes_consolidadas': DeliberacaoCRSCRSCTae.objects.filter(processo=self).delete()[0],
            }
            self.avaliadores.clear()
            # Campos que só fazem sentido com a avaliação e a deliberação de pé.
            ProcessoRSCTae.objects.filter(pk=self.pk).update(
                avaliacao_finalizada_por=None,
                data_finalizacao_avaliacao=None,
                avaliacao_motivo_indeferimento='',
                data_entrada_crsc=None,
            )
            self.avaliacao_finalizada_por = None
            self.data_finalizacao_avaliacao = None
            self.avaliacao_motivo_indeferimento = ''
            self.data_entrada_crsc = None
        return removidos

    def transicionar(self, situacao_nova, *, motivo, por_vinculo=None, origem=OrigemTransicao.MANUAL, campos_extras=None):
        """Único caminho autorizado para alterar a situação do processo.

        Valida a transição contra ``SituacaoProcesso.TRANSICOES``, grava o
        histórico (data + motivo + origem) e atualiza a situação — junto dos
        ``campos_extras`` opcionais — de forma atômica.

        Args:
            situacao_nova: Situação de destino (constante de ``SituacaoProcesso``).
            motivo: Texto que justifica a transição. Obrigatório (não pode ser vazio).
            por_vinculo: Vínculo que realizou a transição (``None`` para o sistema).
            origem: ``OrigemTransicao.MANUAL`` ou ``AUTOMATICO``.
            campos_extras: Campos adicionais do processo a atualizar na mesma transação.

        Raises:
            TransicaoInvalidaError: Se a transição não for permitida.
            ValueError: Se o motivo estiver vazio.
        """
        situacao_atual = self.situacao
        if situacao_nova not in SituacaoProcesso.TRANSICOES.get(situacao_atual, ()):
            labels = dict(SituacaoProcesso.get_choices())
            raise TransicaoInvalidaError(
                f'Transição não permitida: {labels.get(situacao_atual, situacao_atual)} → {labels.get(situacao_nova, situacao_nova)}.'
            )

        motivo = (motivo or '').strip()
        if not motivo:
            raise ValueError('O motivo da transição de situação é obrigatório.')

        campos_extras = dict(campos_extras or {})
        with transaction.atomic():
            # A anulação pertence à transição, não à tela: o formulário do admin e o command de
            # saneamento também chegam aqui, e um processo devolvido por eles com avaliações e
            # votos de pé contaminaria a deliberação seguinte.
            if situacao_atual == SituacaoProcesso.AGUARDANDO_CRSC and situacao_nova == SituacaoProcesso.AGUARDANDO_CORRECAO:
                self.anular_fases_posteriores()
            HistoricoSituacaoProcessoRSCTae.objects.create(
                processo=self,
                situacao_anterior=situacao_atual,
                situacao_nova=situacao_nova,
                realizado_por_vinculo=por_vinculo,
                motivo=motivo,
                origem=origem,
            )
            type(self).objects.filter(pk=self.pk).update(situacao=situacao_nova, **campos_extras)

        self.situacao = situacao_nova
        for campo, valor in campos_extras.items():
            setattr(self, campo, valor)
        return self

    def rsc_equivalente(self):
        return ', '.join([str(titulo) for titulo in self.nivel_requisitado.iq_equivalente.all()])

    def _conteudo_assinatura_preenchimento(self):
        """Monta o dicionário-snapshot do preenchimento que será serializado e assinado."""
        from rsc_tae.models.anexo import RolSaberCompetenciaAnexo

        anexos = (
            RolSaberCompetenciaAnexo.objects.filter(processo=self)
            .select_related('rol_saber_competencia')
            .order_by('rol_saber_competencia__numero', 'id')
        )
        itens = [
            {
                'anexo_id': a.id,
                'item_id': a.rol_saber_competencia_id,
                'item': str(a.rol_saber_competencia),
                'unidades': str(a.pontuacao if a.pontuacao is not None else ''),
                'descricao': a.descricao or '',
                'arquivo': a.nome_original or (a.arquivo.name if a.arquivo else ''),
                'data_inicio': a.data_inicio.isoformat() if a.data_inicio else None,
                'data_fim': a.data_fim.isoformat() if a.data_fim else None,
            }
            for a in anexos
        ]
        return {
            'processo_id': self.pk,
            'avaliado_vinculo_id': self.vinculo_id,
            'avaliado_nome': str(self.vinculo.pessoa.nome),
            'nivel_requisitado_id': self.nivel_requisitado_id,
            'nivel_requisitado_nome': str(self.nivel_requisitado),
            'declaracao_conformidade': bool(self.declaracao_conformidade),
            'data_entrada_requerimento': self.data_entrada_requerimento.isoformat() if self.data_entrada_requerimento else None,
            'total_anexos': len(itens),
            'anexos': itens,
        }

    def assinatura_preenchimento_conteudo_formatado(self):
        """Retorna o conteúdo assinado do preenchimento como JSON legível (indentado) para conferência."""
        import json

        if not self.assinatura_preenchimento_conteudo:
            return ''
        try:
            return json.dumps(json.loads(self.assinatura_preenchimento_conteudo), indent=2, ensure_ascii=False)
        except ValueError, TypeError:
            return self.assinatura_preenchimento_conteudo

    def gerar_assinatura_preenchimento(self):
        """Gera e persiste o hash SHA-256 do preenchimento no momento da conclusão/assinatura.

        Mesmo padrão de ``AvaliacaoProcessoRSCTae``/``DeliberacaoCRSCRSCTae``: serializa um snapshot
        do processo (servidor, nível, declarações, data e itens/unidades declaradas) e grava o hash
        + o conteúdo assinado, para conferência posterior de integridade.
        """
        import hashlib
        import json

        conteudo = self._conteudo_assinatura_preenchimento()
        conteudo_json = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str)
        hash_valor = hashlib.sha256(conteudo_json.encode('utf-8')).hexdigest()

        ProcessoRSCTae.objects.filter(pk=self.pk).update(
            assinatura_preenchimento_conteudo=conteudo_json,
            assinatura_preenchimento_hash=hash_valor,
        )
        self.assinatura_preenchimento_conteudo = conteudo_json
        self.assinatura_preenchimento_hash = hash_valor
        return conteudo_json, hash_valor

    def get_situacao_badge(self):
        cor_por_situacao = {
            SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: 'alert',
            SituacaoProcesso.AGUARDANDO_CORRECAO: 'warning',
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: 'warning',
            SituacaoProcesso.AGUARDANDO_AVALIADOR: 'warning',
            SituacaoProcesso.AGUARDANDO_ACEITE_AVALIADOR: 'warning',
            SituacaoProcesso.EM_ANALISE: 'info',
            SituacaoProcesso.AGUARDANDO_CRSC: 'info',
            SituacaoProcesso.DEFERIDO: 'success',
            SituacaoProcesso.INDEFERIDO: 'error',
        }
        cor = cor_por_situacao.get(self.situacao, 'default')
        texto = self.get_situacao_display()
        return mark_safe(f'<span class="status status-{cor}">{texto}</span>')

    @classmethod
    def anotar_sla_data_entrada(cls, queryset):
        """Anota ``sla_data_entrada`` com a data de entrada na situação atual de cada processo.

        Sem essa anotação, ``get_sla_status`` consulta o histórico uma vez por processo. Use este
        helper sempre que for calcular SLA em cima de vários processos (listagens e dashboard).

        Diferente de ``expressao_data_entrada_situacao_atual``, não faz ``Coalesce`` para
        ``data_cadastro``: o SLA só admite essa substituição em AGUARDANDO_PREENCHIMENTO, regra
        aplicada em ``_resolver_data_entrada_sla``.
        """
        return queryset.annotate(sla_data_entrada=cls._subquery_ultima_entrada_situacao())

    def _resolver_data_entrada_sla(self, data_entrada=None):
        """Descobre quando o processo entrou na situação atual.

        Ordem de busca: valor recebido pronto, anotação ``sla_data_entrada`` (mesmo que nula, para
        não refazer a consulta que o queryset já resolveu) e, por último, o histórico. Processos
        criados antes do log de histórico caem na data de cadastro.
        """
        if data_entrada is None:
            if 'sla_data_entrada' in self.__dict__:
                data_entrada = self.sla_data_entrada
            else:
                historico = (
                    HistoricoSituacaoProcessoRSCTae.objects.filter(
                        processo=self,
                        situacao_nova=self.situacao,
                    )
                    .order_by('-data_transicao')
                    .first()
                )
                data_entrada = historico.data_transicao if historico else None

        if data_entrada is None and self.situacao == SituacaoProcesso.AGUARDANDO_PREENCHIMENTO:
            return self.data_cadastro
        return data_entrada

    def get_sla_status(self, configuracao=None, data_entrada=None):
        """Retorna o status do SLA para a situação atual do processo.

        Retorna None para processos finalizados ou sem SLA configurado.

        Args:
            configuracao: ``ConfiguracaoRSCTae`` já carregada. Em laços, buscar uma vez e repassar
                evita uma consulta por processo.
            data_entrada: data de entrada na situação atual, quando o chamador já a conhece. Se
                omitida, usa a anotação de ``anotar_sla_data_entrada`` ou consulta o histórico.

        Retorna dict com:
        - ``data_entrada``: quando entrou no estado atual
        - ``dias_decorridos``: dias desde a entrada
        - ``dias_sla``: prazo configurado para este estado
        - ``dias_restantes``: positivo = dentro do prazo, negativo = atrasado
        - ``atrasado``: bool
        - ``alerta``: bool (dentro do prazo mas faltam 3 dias ou menos)
        """
        from django.utils import timezone

        if self.situacao in SituacaoProcesso.FINAIS:
            return None

        config = configuracao or self._get_configuracao()
        if not config:
            return None

        sla_por_situacao = {
            SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: config.dias_prazo_preenchimento,
            SituacaoProcesso.AGUARDANDO_CORRECAO: config.dias_prazo_correcao,
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: config.dias_prazo_validacao_rh,
            SituacaoProcesso.EM_ANALISE: config.dias_prazo_avaliacao,
        }
        dias_sla = sla_por_situacao.get(self.situacao)
        if not dias_sla:
            return None

        data_entrada = self._resolver_data_entrada_sla(data_entrada)
        if data_entrada is None:
            return None

        agora = timezone.now()
        dias_decorridos = (agora - data_entrada).days
        dias_restantes = dias_sla - dias_decorridos

        return {
            'data_entrada': data_entrada,
            'dias_decorridos': dias_decorridos,
            'dias_sla': dias_sla,
            'dias_restantes': dias_restantes,
            'atrasado': dias_restantes < 0,
            'alerta': 0 <= dias_restantes <= 3,
        }

    @property
    def todos_avaliadores_finalizaram(self) -> bool:
        """True se todos os avaliadores ativos (não substituídos) já finalizaram."""
        ativos = self.avaliacoes_por_avaliador.filter(substituido=False)
        return ativos.exists() and not ativos.filter(finalizada=False).exists()

    @property
    def media_pontuacao_avaliadores(self):
        """Média aritmética das pontuações finais dos avaliadores não substituídos."""
        from decimal import Decimal
        from django.db.models import Avg

        media = self.avaliacoes_por_avaliador.filter(
            substituido=False,
            finalizada=True,
            pontuacao_final__isnull=False,
        ).aggregate(media=Avg('pontuacao_final'))['media']
        return Decimal(str(media)) if media is not None else Decimal('0')

    @property
    def prazo_vencido_algum_avaliador(self) -> bool:
        """True se algum avaliador ativo tem data_limite_avaliacao vencida e ainda não finalizou."""
        hoje = datetime.date.today()
        return self.avaliacoes_por_avaliador.filter(
            substituido=False,
            finalizada=False,
            data_limite_avaliacao__lt=hoje,
        ).exists()

    @staticmethod
    def _get_configuracao():
        from rsc_tae.models.configuracao_rsc_tae import ConfiguracaoRSCTae

        return ConfiguracaoRSCTae.objects.first()

    @classmethod
    def calcular_novo_processo(cls, usuario, nivel_id=None):
        from dateutil.relativedelta import relativedelta
        from django.utils import timezone

        servidor = usuario.get_relacionamento()
        vinculo = servidor.get_vinculo()

        titulacao = servidor.titulacao
        if not titulacao:
            raise ValueError('Servidor não possui titulação cadastrada.')

        # Verificar interstício de 3 anos (Art. 3º, §3º)
        ultimo_deferido = cls.objects.filter(vinculo=vinculo, situacao=SituacaoProcesso.DEFERIDO).order_by('-data_finalizacao_avaliacao').first()
        if ultimo_deferido and ultimo_deferido.data_finalizacao_avaliacao:
            data_limite = ultimo_deferido.data_finalizacao_avaliacao + relativedelta(years=cls.INTERSTICIO_ANOS)
            if timezone.now() < data_limite:
                raise ValueError(
                    f'É necessário aguardar o interstício de {cls.INTERSTICIO_ANOS} anos desde a última concessão '
                    f'({ultimo_deferido.data_finalizacao_avaliacao.strftime("%d/%m/%Y")}). '
                    f'Novo requerimento poderá ser feito a partir de {data_limite.strftime("%d/%m/%Y")}.'
                )

        from .nivel import Nivel

        niveis = Nivel.objects.filter(iq_requisito__in=[titulacao])
        if not niveis.exists():
            raise ValueError('Nenhum nível encontrado para a titulação do servidor.')

        if nivel_id:
            # Tenta primeiro dentro dos habilitados; se não achar, aceita qualquer nível
            # superior ao máximo habilitado (servidor pode ter titulação recente não cadastrada)
            nivel_requisitado = niveis.filter(pk=nivel_id).first()
            if not nivel_requisitado:
                maior_ordem = niveis.order_by('-ordem').values_list('ordem', flat=True).first() or 0
                nivel_requisitado = Nivel.objects.filter(pk=nivel_id, ordem__gt=maior_ordem).first()
                if not nivel_requisitado:
                    raise ValueError('O nível selecionado não é válido para a sua situação atual.')
        else:
            nivel_requisitado = niveis.order_by('-valor_iq').first()

        # Saldo de pontuação anterior (Art. 3º, §2º) — lido do banco de pontos
        from rsc_tae.models.banco_pontos import BancoPontosRSCTae, MovimentoBancoPontosRSCTae

        banco = BancoPontosRSCTae.objects.filter(vinculo=vinculo).first()
        saldo = (banco.saldo if banco else 0) or 0

        processo = cls.objects.create(
            vinculo=vinculo,
            nivel_requisitado=nivel_requisitado,
            saldo_pontuacao_anterior=saldo,
            processo_anterior=ultimo_deferido,
        )

        # Debita o saldo utilizado no banco
        if saldo and banco:
            banco.debitar(
                saldo,
                tipo=MovimentoBancoPontosRSCTae.TIPO_DEBITO_UTILIZACAO,
                processo=processo,
                descricao=f'Saldo utilizado no processo #{processo.pk}.',
                realizado_por=vinculo,
            )

        HistoricoSituacaoProcessoRSCTae.objects.create(
            processo=processo,
            situacao_anterior=None,
            situacao_nova=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO,
            realizado_por_vinculo=vinculo,
            motivo='Processo iniciado pelo servidor — aguardando preenchimento do requerimento.',
            origem=OrigemTransicao.MANUAL,
        )

        return processo
