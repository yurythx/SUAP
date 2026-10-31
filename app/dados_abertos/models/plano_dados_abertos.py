from dados_abertos.enums import SituacaoPDA, SituacaoLAI
from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.db.models import Count, Q
from .acao import Acao
from .etapa import Etapa
from .pdaacao import PDAAcao
from .versao_pda import VersaoPDA
from ..enums import TipoVersao


class PlanoDadosAbertos(ModelPlus):
    SEARCH_FIELDS = ['titulo']

    titulo = models.CharFieldPlus(_('Título do PDA'), max_length=255)
    situacao = models.PositiveSmallIntegerField(
        _('Situação'), choices=SituacaoPDA.get_choices(), default=SituacaoPDA.RASCUNHO, help_text=_('Situação atual do Plano de Dados Abertos.')
    )
    vigencia_inicio = models.DateFieldPlus(_('Vigência - início'))
    vigencia_fim = models.DateFieldPlus(_('Vigência - fim'))
    publicado = models.BooleanFieldPlus(_('Publicado'), default=False)
    data_publicacao = models.DateFieldPlus(_('Data de publicação'), null=True, blank=True)

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    etapa_atual = models.ForeignKeyPlus(
        'dados_abertos.Etapa',
        verbose_name=_('Etapa atual'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='planos_em_andamento',
    )

    bases_dados = models.ManyToManyFieldPlus(
        'dados_abertos.BaseDados',
        through='dados_abertos.PDABaseDados',
        related_name='pdas',
        blank=True,
        verbose_name=_('Bases de Dados'),
    )

    versao_major = models.PositiveIntegerFieldPlus(_('Versão Major'), default=1)
    versao_minor = models.PositiveIntegerFieldPlus(_('Versão Minor'), default=0)
    versao_patch = models.PositiveIntegerFieldPlus(_('Versão Patch'), default=0)

    class Meta:
        verbose_name = _('Plano de Dados Abertos (PDA)')
        verbose_name_plural = _('Planos de Dados Abertos (PDA)')

    def __str__(self):
        if self.vigencia_inicio and self.vigencia_fim:
            return f'{self.titulo} ({self.vigencia_inicio.year} - {self.vigencia_fim.year})'
        return self.titulo

    @property
    def versao_atual(self):
        return f'{self.versao_major}.{self.versao_minor}.{self.versao_patch}'

    def _build_snapshot(self):
        return {
            'titulo': self.titulo,
            'situacao': self.situacao,
            'vigencia_inicio': str(self.vigencia_inicio),
            'vigencia_fim': str(self.vigencia_fim),
            'publicado': self.publicado,
            'etapa_atual_id': self.etapa_atual_id,
            'bases_dados': list(self.bases_dados.all().values_list('pk', flat=True)),
        }

    def gerar_versao(self, tipo, justificativa=''):
        # Snapshot do estado ANTES de incrementar
        snapshot = self._build_snapshot()

        VersaoPDA.objects.create(
            pda=self,
            major=self.versao_major,
            minor=self.versao_minor,
            patch=self.versao_patch,
            tipo=tipo,
            situacao_no_momento=self.situacao,
            dados_snapshot=snapshot,
            justificativa=justificativa,
        )

        if tipo == TipoVersao.MAJOR:
            self.versao_major += 1
            self.versao_minor = 0
            self.versao_patch = 0
        elif tipo == TipoVersao.MINOR:
            self.versao_minor += 1
            self.versao_patch = 0
        elif tipo == TipoVersao.PATCH:
            self.versao_patch += 1

        self.save(update_fields=['versao_major', 'versao_minor', 'versao_patch'])

        # Gera documento HTML + PDF da versão
        from dados_abertos.services.documento_pda_service import gerar_documento_pda

        versao_str = f'{self.versao_major}.{self.versao_minor}.{self.versao_patch}'
        gerar_documento_pda(self, versao_str)

    def vigencia(self):
        if self.vigencia_inicio and self.vigencia_fim:
            return f'{self.vigencia_inicio.strftime("%d/%m/%Y")} - {self.vigencia_fim.strftime("%d/%m/%Y")}'
        return '-'

    def tem_base_nao_avaliada(self):
        """Retorna True se houver alguma base de dados vinculada ao PDA que não tenha sido avaliada,
        ou se não houver nenhuma base vinculada (pois ainda é necessário realizar a avaliação)."""
        bases_relacionadas = self.bases_relacionadas.select_related('base_dados').all()
        if not bases_relacionadas.exists():
            return True
        _existe_avaliacao = False
        for pda_base in bases_relacionadas:
            # Se não existe nenhuma avaliação finalizada, a base não foi avaliada
            _avaliacao = pda_base.base_dados.avaliacoes_base_dados
            if _avaliacao.exists():
                _existe_avaliacao = True
                if _avaliacao.filter(finalizado=False).exists():
                    return True
        # Se não existe nenhuma avaliação, considera que há base não avaliada
        return not _existe_avaliacao

    def tem_base_sem_avaliacao(self):
        """Retorna True se houver alguma base de dados vinculada ao PDA que não tenha nenhuma avaliação cadastrada,
        ou se não houver nenhuma base vinculada."""
        bases_relacionadas = self.bases_relacionadas.select_related('base_dados').all()
        if not bases_relacionadas.exists():
            return True
        return any(not pda_base.base_dados.avaliacoes_base_dados.exists() for pda_base in bases_relacionadas)

    # --------- Checklist ---------

    def inicializar_checklist(self):
        """
        Cria os registros de PDAAcao para todas as ações definidas no modelo.
        Pode ser chamado no save() ou na view do dashboard.
        """
        # evita N inserts em loop e também garante consistência caso novas ações
        # sejam cadastradas depois que o PDA já existe.
        with transaction.atomic():
            acoes_faltantes = Acao.objects.exclude(estado_nos_pdas__pda=self).only('id')
            novos = [PDAAcao(pda=self, acao=acao) for acao in acoes_faltantes]
            if novos:
                PDAAcao.objects.bulk_create(novos, ignore_conflicts=True)

            # define etapa_atual como a primeira etapa do fluxo
            if not self.etapa_atual_id:
                primeira_id = Etapa.objects.order_by('ordem').values_list('id', flat=True).first()
                if primeira_id:
                    type(self).objects.filter(pk=self.pk, etapa_atual__isnull=True).update(etapa_atual_id=primeira_id)
                    self.etapa_atual_id = primeira_id

    def etapas_puladas_ids(self) -> set:
        """IDs das etapas dispensadas (puladas) neste PDA."""
        return set(self.etapas_puladas.values_list('etapa_id', flat=True))

    def _acoes_ativas(self):
        """``PDAAcao`` deste PDA, excluindo as ações de etapas dispensadas."""
        puladas = self.etapas_puladas_ids()
        qs = self.acoes.all()
        if puladas:
            qs = qs.exclude(acao__etapa_id__in=puladas)
        return qs

    def get_progresso_etapa(self, etapa):
        if etapa.id in self.etapas_puladas_ids():
            return 100
        dados = self.acoes.filter(acao__etapa=etapa).aggregate(
            total=Count('id'),
            concluidas=Count('id', filter=Q(concluida=True)),
        )
        total = dados['total'] or 0
        if not total:
            return 0
        concluidas = dados['concluidas'] or 0
        return round(concluidas * 100 / total)

    def get_progresso_geral(self):
        """Percentual de ações obrigatórias resolvidas no PDA.

        Ações de etapas dispensadas contam como resolvidas: a dispensa encerra a etapa, então ela
        soma no numerador e permanece no denominador (mesma semântica de ``get_progresso_etapa``,
        que devolve 100 para etapa dispensada).
        """
        # Se todas as ações obrigatórias estiverem concluídas, retorna 100%.
        if self.fluxo_obrigatorio_concluido():
            return 100
        puladas = self.etapas_puladas_ids()
        resolvida = Q(concluida=True)
        if puladas:
            resolvida |= Q(acao__etapa_id__in=puladas)
        dados = self.acoes.filter(acao__obrigatoria=True).aggregate(
            total=Count('id'),
            resolvidas=Count('id', filter=resolvida),
        )
        total = dados['total'] or 0
        if not total:
            return 0
        resolvidas = dados['resolvidas'] or 0
        return round(resolvidas * 100 / total)

    def atualizar_etapa_atual(self):
        self._recalcular_etapa_atual()
        self._disparar_analise_lai_se_necessario()

    def _disparar_analise_lai_se_necessario(self):
        """Ao atingir uma etapa marcada com dispara_analise_lai, envia à análise os datasets PENDENTE COM recurso.

        Só envia datasets que possuem ao menos um recurso — sem recurso não há prévia do conteúdo
        para o LAI avaliar; esses ficam em PENDENTE. Idempotente: só afeta relações em PENDENTE.
        """
        etapa = self.etapa_atual
        if not etapa or not getattr(etapa, 'dispara_analise_lai', False):
            return
        from dados_abertos.services.lai_service import enviar_para_analise

        enviar_para_analise(self.bases_relacionadas.filter(situacao_lai=SituacaoLAI.PENDENTE))

    def _recalcular_etapa_atual(self):
        """
        Define a etapa_atual como a primeira etapa que ainda tem ação obrigatória pendente.
        Se nenhuma estiver pendente, verifica se a última etapa também está totalmente concluída.
        Caso esteja, remove a referência de etapa_atual (marca fluxo como concluído).
        Caso contrário, posiciona na última etapa.
        """
        puladas = self.etapas_puladas_ids()
        etapas = Etapa.objects.all().order_by('ordem')

        for etapa in etapas:
            if etapa.id in puladas:
                # etapa dispensada: o fluxo passa por cima dela
                continue
            pendente = self.acoes.filter(
                acao__etapa=etapa,
                acao__obrigatoria=True,
                concluida=False,
            ).exists()
            if pendente:
                if self.etapa_atual_id != etapa.id:
                    self.etapa_atual = etapa
                    self.save(update_fields=['etapa_atual'])
                return

        # nenhuma etapa ativa tem obrigatória pendente: fluxo concluído
        if self.etapa_atual_id is not None:
            self.etapa_atual = None
            self.save(update_fields=['etapa_atual'])

    def fluxo_concluido(self) -> bool:
        """Retorna True quando todas as ações de todas as etapas estão concluídas."""
        cache_attr = '_fluxo_concluido_cache'
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        valor = not self._acoes_ativas().filter(concluida=False).exists()
        setattr(self, cache_attr, valor)
        return valor

    def fluxo_obrigatorio_concluido(self) -> bool:
        """Retorna True quando todas as ações obrigatórias das etapas ativas (não dispensadas) estão concluídas."""
        cache_attr = '_fluxo_obrigatorio_concluido_cache'
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        valor = not self._acoes_ativas().filter(acao__obrigatoria=True, concluida=False).exists()
        setattr(self, cache_attr, valor)
        return valor
