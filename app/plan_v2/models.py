import datetime
from decimal import Decimal

from django.db.models import Sum
from django.db.models.fields import BooleanField

from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.templatetags.filters import in_group
from financeiro.models import NaturezaDespesa as NaturezaDespesaFin

# Modelos gerais -------------------------------------------------------------------------------------------------------


class Eixo(ModelPlus):
    nome = models.CharFieldPlus('Nome')

    class Meta:
        verbose_name = 'Eixo'
        verbose_name_plural = 'Eixos'

        ordering = ('nome',)

    def __str__(self):
        return self.nome


class Dimensao(ModelPlus):
    SEARCH_FIELDS = ['nome']

    codigo = models.IntegerField('Código', null=True)
    nome = models.CharFieldPlus('Nome', unique=True)
    setor_sistemico = models.ForeignKeyPlus(
        'rh.Setor', related_name='dimensao_setor', help_text='Setor sistêmico responsável pela dimensão', on_delete=models.CASCADE
    )
    eixo = models.ForeignKeyPlus('plan_v2.Eixo', null=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Dimensão'
        verbose_name_plural = 'Dimensões'

        ordering = ('codigo',)

    def save(self, *args, **kwargs):
        atualizacao = False
        codigo = None
        if self.pk:
            atualizacao = True
            dimensao = Dimensao.objects.get(pk=self.pk)
            codigo = dimensao.codigo

        super().save(*args, **kwargs)

        if atualizacao:
            if codigo != self.codigo:
                for pdi_macro in PDIMacroprocesso.objects.filter(macroprocesso__dimensao=self):
                    pdi_macro.codigo_dimensao = self.codigo
                    pdi_macro.save()

                for objetivo in ObjetivoEstrategico.objects.filter(pdi_macroprocesso__macroprocesso__dimensao=self):
                    objetivo.codigo_dimensao = self.codigo
                    objetivo.save()

                for meta in Meta.objects.filter(objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao=self):
                    meta.codigo_dimensao = self.codigo
                    meta.save()

                for acao in PDIAcao.objects.filter(acao__macroprocesso__dimensao=self):
                    acao.codigo_dimensao = self.codigo
                    acao.save()

    def __str__(self):
        return f'{self.codigo}. {self.nome}'


class Macroprocesso(ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']

    dimensao = models.ForeignKeyPlus('plan_v2.Dimensao', verbose_name='Dimensão', on_delete=models.CASCADE)
    nome = models.CharFieldPlus('Nome')
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Macroprocesso'
        verbose_name_plural = 'Macroprocessos'

    def __str__(self):
        return self.nome


class Acao(ModelPlus):
    SEARCH_FIELDS = ['detalhamento']

    SITUACAO_DEFERIDA = 'Deferida'
    SITUACAO_INDEFERIDA = 'Indeferida'
    SITUACAO_ANALISADA = 'Em análise'
    SITUACAO_NAO_ANALISADA = 'Não analisada'
    SITUACAO_CHOICE = (
        (SITUACAO_DEFERIDA, SITUACAO_DEFERIDA),
        (SITUACAO_INDEFERIDA, SITUACAO_INDEFERIDA),
        (SITUACAO_ANALISADA, SITUACAO_ANALISADA),
        (SITUACAO_NAO_ANALISADA, SITUACAO_NAO_ANALISADA),
    )

    macroprocesso = models.ForeignKeyPlus('plan_v2.Macroprocesso', on_delete=models.CASCADE)
    detalhamento = models.TextField('Detalhamento')
    eh_vinculadora = models.BooleanField('Vinculadora?', default=False)
    ativa = models.BooleanField('Ativa?', default=True)

    class Meta:
        verbose_name = 'Ação'
        verbose_name_plural = 'Ações'

        permissions = (('vincular_acao', 'Pode vincular ação'), ('desvincular_acao', 'Pode desvincular ação'))

    def __str__(self):
        return self.detalhamento

    @classmethod
    def pode_vincular(cls, usuario, plano_acao):
        return bool(usuario.has_perm('plan_v2.vincular_acao') and plano_acao.em_periodo_sistemico)

    @classmethod
    def pode_desvincular(cls, usuario, meta, plano_acao):
        atividades = Atividade.objects.filter(acao_pa__meta_pa=meta)
        return bool(usuario.has_perm('plan_v2.desvincular_acao') and plano_acao.em_periodo_sistemico and not atividades.exists())


class UnidadeMedida(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', unique=True)

    class Meta:
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'

        ordering = ('nome',)

    def __str__(self):
        return self.nome


# Modelos do PDI -------------------------------------------------------------------------------------------------------


class PDI(ModelPlus):
    ano_inicial = models.ForeignKeyPlus('comum.Ano', related_name='ano_inicial_pdi', verbose_name='Ano Inicial', help_text='Vigência inicial do PDI')
    ano_final = models.ForeignKeyPlus('comum.Ano', related_name='ano_final_pdi', verbose_name='Ano Final', help_text='Vigência final do PDI')

    class Meta:
        verbose_name = 'PDI'
        verbose_name_plural = 'PDIs'
        unique_together = ('ano_inicial', 'ano_final')

    def __str__(self):
        return f'De {self.ano_inicial} até {self.ano_final}'


class PDIMacroprocesso(ModelPlus):
    SEARCH_FIELDS = ['codigo', 'codigo_dimensao', 'macroprocesso__nome']
    pdi = models.ForeignKeyPlus(PDI, related_name='macroprocessos', verbose_name='PDI', on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)
    codigo_dimensao = models.IntegerField('Código da Dimensão', null=True)
    macroprocesso = models.ForeignKeyPlus('plan_v2.Macroprocesso', verbose_name='Macroprocesso', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'MacroProcesso do PDI'
        verbose_name_plural = 'MacroProcessos do PDI'

        ordering = ('codigo_dimensao', 'codigo')

        unique_together = ('pdi', 'macroprocesso')

    def save(self, *args, **kwargs):
        atualizacao = False
        codigo = None
        if self.pk:
            atualizacao = True
            macro = PDIMacroprocesso.objects.get(pk=self.pk)
            codigo = macro.codigo
        else:
            if not self.codigo:
                self.codigo = PDIMacroprocesso.objects.filter(pdi=self.pdi, macroprocesso__dimensao=self.macroprocesso.dimensao).count() + 1

        super().save(*args, **kwargs)

        if atualizacao:
            if codigo != self.codigo:
                for objetivo in self.objetivoestrategico_set.all():
                    objetivo.codigo_macroprocesso = self.codigo
                    objetivo.save()
                for pdi_acao in PDIAcao.objects.filter(pdi=self.pdi, acao__macroprocesso=self.macroprocesso):
                    pdi_acao.codigo_macroprocesso = self.codigo
                    pdi_acao.save()

    def __str__(self):
        return f'{self.codigo_completo} {self.macroprocesso!s}'

    @property
    def codigo_completo(self):
        return f'{self.codigo_dimensao}.{self.codigo}.'


class ObjetivoEstrategico(ModelPlus):
    pdi_macroprocesso = models.ForeignKeyPlus('plan_v2.PDIMacroprocesso', verbose_name='Macroprocesso', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    codigo = models.IntegerField('Código', null=True)
    codigo_dimensao = models.IntegerField('Código da Dimensão', null=True)
    codigo_macroprocesso = models.IntegerField('Código do Macroprocesso', null=True)

    class Meta:
        verbose_name = 'Objetivo Estratégico'
        verbose_name_plural = 'Objetivos Estratégicos'
        unique_together = ('pdi_macroprocesso', 'descricao')

        permissions = (
            ('pode_ver_planoacao_objetivoestrategico', 'Pode ver objetivo estratégico no plano de ação'),
            ('pode_importar_objetivoestrategico', 'Pode importar objetivo estratégico no plano de ação'),
        )

    def save(self, *args, **kwargs):
        atualizacao = False
        codigo = None
        if self.pk:
            atualizacao = True
            objetivo = ObjetivoEstrategico.objects.get(pk=self.pk)
            codigo = objetivo.codigo
        else:
            if not self.codigo:
                self.codigo = ObjetivoEstrategico.objects.filter(pdi_macroprocesso=self.pdi_macroprocesso).count() + 1

        super().save(*args, **kwargs)

        if atualizacao:
            if codigo != self.codigo:
                for meta in self.meta_set.all():
                    meta.codigo_objetivo = self.codigo
                    meta.save()

    def __str__(self):
        return f'{self.codigo_completo} {self.descricao}'

    @property
    def codigo_completo(self):
        return f'{self.codigo_dimensao}.{self.codigo_macroprocesso}.{self.codigo}.'


class Meta(ModelPlus):
    objetivo_estrategico = models.ForeignKeyPlus('plan_v2.ObjetivoEstrategico', verbose_name='Objetivo Estratégico', on_delete=models.CASCADE)
    titulo = models.TextField('Título')
    associado = BooleanField(default=False)
    responsavel = models.ForeignKeyPlus('rh.Setor', verbose_name='Responsável', related_name='meta_setor', null=True, on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)
    codigo_dimensao = models.IntegerField('Código da Dimensão', null=True)
    codigo_macroprocesso = models.IntegerField('Código do Macroprocesso', null=True)
    codigo_objetivo = models.IntegerField('Código do Objetivo', null=True)

    class Meta:
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'

    def __str__(self):
        return f'{self.codigo_completo} {self.titulo}'

    @property
    def codigo_completo(self):
        return f'{self.codigo_dimensao}.{self.codigo_macroprocesso}.{self.codigo_objetivo}.{self.codigo}.'

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.codigo:
                self.codigo = Meta.objects.filter(objetivo_estrategico=self.objetivo_estrategico).count() + 1

        super().save(*args, **kwargs)

        hoje = datetime.datetime.now()

        for plano_acao in PlanoAcao.objects.filter(
            pdi=self.objetivo_estrategico.pdi_macroprocesso.pdi, data_metas_inicial__lte=hoje, data_metas_final__gte=hoje
        ):
            # Adiciona a meta ao plano de ação
            if MetaPA.objects.filter(plano_acao=plano_acao).exists() and not MetaPA.objects.filter(plano_acao=plano_acao, meta=self):
                meta_pa = MetaPA()
                meta_pa.plano_acao = plano_acao
                meta_pa.meta = self
                meta_pa.save()


class Indicador(ModelPlus):
    METODO_SOMA = 'Soma'
    METODO_MEDIA = 'Média'
    METODO_MAXIMO = 'Máximo'
    METODO_MINIMO = 'Mínimo'
    METODO_ULTIMO = 'Último'
    METODO_RELACAO = 'Relação com a referência'
    METODO_CHOICES = (
        (METODO_SOMA, METODO_SOMA),
        (METODO_MEDIA, METODO_MEDIA),
        (METODO_MAXIMO, METODO_MAXIMO),
        (METODO_MINIMO, METODO_MINIMO),
        (METODO_ULTIMO, METODO_ULTIMO),
        (METODO_RELACAO, METODO_RELACAO),
    )
    meta = models.ForeignKeyPlus('plan_v2.Meta', on_delete=models.CASCADE)

    denominacao = models.CharFieldPlus('Denominação')
    criterio_analise = models.CharFieldPlus('Críterio de Análise')
    forma_calculo = models.TextField('Forma de Cálculo')
    valor_fisico_inicial = models.DecimalFieldPlus('Valor Físico Inicial', null=True, blank=True)
    valor_fisico_final = models.DecimalFieldPlus('Valor Físico Final', null=True, blank=True)
    metodo_incremento = models.CharFieldPlus('Método de Incremento', choices=METODO_CHOICES)

    class Meta:
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'

    def __str__(self):
        return self.denominacao

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        hoje = datetime.datetime.now()

        for plano_acao in PlanoAcao.objects.filter(
            pdi=self.meta.objetivo_estrategico.pdi_macroprocesso.pdi, data_metas_inicial__lte=hoje, data_metas_final__gte=hoje
        ):
            for meta_pa in MetaPA.objects.filter(plano_acao=plano_acao, meta=self.meta):
                if not IndicadorPA.objects.filter(meta_pa=meta_pa, indicador=self).exists():
                    indicador_pa = IndicadorPA()
                    indicador_pa.meta_pa = meta_pa
                    indicador_pa.indicador = self
                    indicador_pa.save()
                    for unidade_administrativa in UnidadeAdministrativa.objects.filter(pdi=plano_acao.pdi):
                        indicador_ua = IndicadorPAUnidadeAdministrativa()
                        indicador_ua.indicador_pa = indicador_pa
                        indicador_ua.unidade_administrativa = unidade_administrativa
                        indicador_ua.save()


class PDIAcao(ModelPlus):
    SEARCH_FIELDS = ['acao__detalhamento']

    pdi = models.ForeignKeyPlus(PDI, related_name='acoes', verbose_name='PDI', on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)
    codigo_dimensao = models.IntegerField('Código da Dimensão', null=True)
    codigo_macroprocesso = models.IntegerField('Código do Macroprocesso', null=True)
    acao = models.ForeignKeyPlus('plan_v2.Acao', verbose_name='Ação', on_delete=models.CASCADE)
    ativa_planoacao = models.BooleanField('Ativa para o Plano Ação Vigente', default=True)

    class Meta:
        verbose_name = 'Ação do PDI'
        verbose_name_plural = 'Ações do PDI'

        ordering = ('codigo_dimensao', 'codigo_macroprocesso', 'codigo')

        unique_together = ('pdi', 'acao')

    def __str__(self):
        return f'{self.codigo_completo} - {self.acao.detalhamento}'

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.codigo:
                self.codigo = self.acao.id
        super().save(*args, **kwargs)

    @property
    def codigo_completo(self):
        return f'{self.acao.id}'


class UnidadeAdministrativa(ModelPlus):
    TIPO_CAMPUS = 'Campus'
    TIPO_DIRETORIA = 'Diretoria Sistêmica'
    TIPO_PRO_REITORIA = 'Pró-Reitoria'
    TIPO_CHOICES = ((TIPO_CAMPUS, TIPO_CAMPUS), (TIPO_DIRETORIA, TIPO_DIRETORIA), (TIPO_PRO_REITORIA, TIPO_PRO_REITORIA))
    pdi = models.ForeignKeyPlus('plan_v2.PDI', on_delete=models.CASCADE)
    setor_equivalente = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor Equivalente', related_name='unidade_setor', on_delete=models.CASCADE)
    tipo = models.CharField('Tipo', max_length=20, choices=TIPO_CHOICES)
    setores_participantes = models.ManyToManyField('rh.Setor', related_name='unidade_setor_participante', verbose_name='Participantes')

    class Meta:
        verbose_name = 'Unidade Administrativa'
        verbose_name_plural = 'Unidades Administrativas'

        ordering = ('tipo', 'setor_equivalente__nome')
        unique_together = ('pdi', 'setor_equivalente')

    def __str__(self):
        return f'{self.setor_equivalente.sigla} - {self.setor_equivalente.nome}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        hoje = datetime.datetime.now()

        # Adiciono a unidade as origens de recurso ua
        for plano_acao in PlanoAcao.objects.filter(pdi=self.pdi, data_metas_inicial__lte=hoje, data_metas_final__gte=hoje):
            # Adiciono a unidade as origens de recurso ua
            for origem_recurso in OrigemRecurso.objects.filter(plano_acao=plano_acao):
                if (
                    OrigemRecursoUA.objects.filter(origem_recurso=origem_recurso).exists()
                    and not OrigemRecursoUA.objects.filter(origem_recurso=origem_recurso, unidade_administrativa=self).exists()
                ):
                    origem_ua = OrigemRecursoUA()
                    origem_ua.origem_recurso = origem_recurso
                    origem_ua.unidade_administrativa = self
                    origem_ua.valor_capital = 0
                    origem_ua.valor_custeio = 0
                    origem_ua.save()
            # Adiciona os indicadores
            for indicador in IndicadorPA.objects.filter(meta_pa__plano_acao=plano_acao):
                if (
                    IndicadorPAUnidadeAdministrativa.objects.filter(indicador_pa=indicador).exists()
                    and not IndicadorPAUnidadeAdministrativa.objects.filter(indicador_pa=indicador, unidade_administrativa=self).exists()
                ):
                    indicador_ua = IndicadorPAUnidadeAdministrativa()
                    indicador_ua.unidade_administrativa = self
                    indicador_ua.indicador_pa = indicador
                    indicador_ua.save()


# Modelos do Plano de Ação --------------------------------------------------------------------------------------------


class PlanoAcao(ModelPlus):
    pdi = models.ForeignKeyPlus('plan_v2.PDI', on_delete=models.CASCADE)
    ano_base = models.OneToOneFieldPlus('comum.Ano', verbose_name='Ano Base')

    # vigência do plano de acao
    data_geral_inicial = models.DateFieldPlus('Início da Vigência')
    data_geral_final = models.DateFieldPlus('Fim da Vigência')

    # data para adição de metas (atividade das pró-reitorias)
    data_metas_inicial = models.DateFieldPlus('Início do Cadastro Sistêmico')
    data_metas_final = models.DateFieldPlus('Fim do Cadastro Sistêmico')

    # data para adição de ações (atividade dos campi e pró-reitorias)
    data_acoes_inicial = models.DateFieldPlus('Início do Cadastro do Campus')
    data_acoes_final = models.DateFieldPlus('Fim dp Cadastro do Campus')

    # data para a validação das ações cadastradas
    data_validacao_inicial = models.DateFieldPlus('Início da Validação')
    data_validacao_final = models.DateFieldPlus('Fim da Validação')

    class Meta:
        verbose_name = 'Plano de Ação'
        verbose_name_plural = 'Planos de Ação'

        ordering = ('ano_base',)
        unique_together = ('pdi', 'ano_base')

        permissions = (
            ('pode_detalhar_planoacao', 'Pode ver detalhe do plano de ação'),
            ('pode_ver_todo_planoacao', 'Pode acessar todo o plano de acao'),
        )

    def __str__(self):
        return str(self.ano_base)

    @property
    def em_periodo_vigencia(self):
        hoje = datetime.date.today()
        return self.data_geral_inicial <= hoje <= self.data_geral_final

    @property
    def em_periodo_sistemico(self):
        hoje = datetime.date.today()
        return self.data_metas_inicial <= hoje <= self.data_metas_final

    @property
    def em_periodo_plano_acao(self):
        hoje = datetime.date.today()
        return self.data_acoes_inicial <= hoje <= self.data_acoes_final

    @property
    def em_periodo_validacao(self):
        hoje = datetime.date.today()
        return self.data_validacao_inicial <= hoje <= self.data_validacao_final


class MetaPA(ModelPlus):
    plano_acao = models.ForeignKeyPlus('plan_v2.PlanoAcao', on_delete=models.CASCADE)
    meta = models.ForeignKeyPlus('plan_v2.Meta', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Meta no Plano de Ação'
        verbose_name_plural = 'Metas no Plano de Ação'

        unique_together = ('plano_acao', 'meta')

    def __str__(self):
        return f'{self.plano_acao}: {self.meta}'


class IndicadorPA(ModelPlus):
    COMPOSICAO_SOMA = 'Soma'
    COMPOSICAO_MEDIA = 'Média'
    COMPOSICAO_CHOICES = ((COMPOSICAO_SOMA, COMPOSICAO_SOMA), (COMPOSICAO_MEDIA, COMPOSICAO_MEDIA))

    indicador = models.ForeignKeyPlus('plan_v2.Indicador')
    meta_pa = models.ForeignKeyPlus('plan_v2.MetaPA')

    valor_inicial = models.DecimalFieldPlus('Valor Físico Inicial', null=True, blank=True)
    valor_final = models.DecimalFieldPlus('Valor Físico Final', null=True, blank=True)
    tipo_composicao = models.CharFieldPlus('Tipo de Composição', choices=COMPOSICAO_CHOICES, default=COMPOSICAO_SOMA)

    class Meta:
        verbose_name = 'Indicador no Plano de Ação'
        verbose_name_plural = 'Indicadores no Plano de Ação'

        unique_together = ('indicador', 'meta_pa')

    def __str__(self):
        return f'{self.meta_pa.plano_acao}: {self.indicador}'

    def save(self, *args, **kwargs):
        old = None
        if self.pk:
            old = IndicadorPA.objects.get(pk=self.pk)

        if old and self.tipo_composicao != old.tipo_composicao:
            soma = next(iter(IndicadorPAUnidadeAdministrativa.objects.filter(indicador_pa=self).aggregate(Sum('valor_inicial')).values())) or 0
            qtd = IndicadorPAUnidadeAdministrativa.objects.filter(indicador_pa=self).count()
            if self.tipo_composicao == IndicadorPA.COMPOSICAO_SOMA:
                self.valor_inicial = soma
            else:
                self.valor_inicial = soma / qtd

        super().save(*args, **kwargs)


class IndicadorPAUnidadeAdministrativa(ModelPlus):
    indicador_pa = models.ForeignKeyPlus('plan_v2.IndicadorPA', on_delete=models.CASCADE)
    unidade_administrativa = models.ForeignKeyPlus('plan_v2.UnidadeAdministrativa', on_delete=models.CASCADE)

    valor_inicial = models.DecimalFieldPlus('Valor Físico Inicial', null=True, blank=True)
    valor_final = models.DecimalFieldPlus('Valor Físico Final', null=True, blank=True)

    class Meta:
        verbose_name = 'Indicador da unidade no Plano de Ação'
        verbose_name_plural = 'Indicador da unidade no Plano de Ação'
        unique_together = ('indicador_pa', 'unidade_administrativa')

    def __str__(self):
        return f'{self.indicador_pa.indicador}: {self.unidade_administrativa}'

    @classmethod
    def pode_incluir(cls, usuario, plano_acao):
        return False

    @classmethod
    def pode_alterar(cls, usuario, plano_acao):
        return bool(
            usuario.has_perm('plan_v2.change_indicadorpaunidadeadministrativa')
            and (plano_acao.em_periodo_sistemico or plano_acao.em_periodo_plano_acao)
        )

    @classmethod
    def pode_excluir(cls, usuario, plano_acao, origem_recurso_pk=None):
        return False


class OrigemRecurso(ModelPlus):
    plano_acao = models.ForeignKeyPlus('plan_v2.PlanoAcao', on_delete=models.CASCADE)
    dimensao = models.ForeignKeyPlus('plan_v2.Dimensao', verbose_name='Dimensão', on_delete=models.CASCADE)
    acao_financeira = models.ForeignKeyPlus(
        'financeiro.AcaoAno', verbose_name='Ação Orçamentária', related_name='origem_recurso_acaofinanceira', on_delete=models.CASCADE
    )
    valor_capital = models.DecimalFieldPlus('Valor de Capital')
    valor_custeio = models.DecimalFieldPlus('Valor de Custeio')
    visivel_campus = models.BooleanField('Visível', help_text='Indica se a origem do recurso é visualizada pelos campi.', default=True)
    codigo = models.CharFieldPlus('Código')
    destinacao = models.CharFieldPlus('Destinação', blank=True)

    class Meta:
        verbose_name = 'Origem do Recurso'
        verbose_name_plural = 'Origens dos Recursos'

        permissions = (('pode_ver_planoacao_origemrecurso', 'Pode ver origem de recurso no plano de ação'),)

    def __str__(self):
        return f'{self.codigo}.{self.acao_financeira.acao.codigo_acao}.{self.acao_financeira.ptres} - {self.destinacao}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        ua_ids = OrigemRecursoUA.objects.filter(origem_recurso=self).values_list('unidade_administrativa__pk', flat=True)

        for unidade in UnidadeAdministrativa.objects.filter(pdi=self.plano_acao.pdi).exclude(pk__in=ua_ids):
            OrigemRecursoUA.objects.create(origem_recurso=self, unidade_administrativa=unidade, valor_capital=0, valor_custeio=0)

    @classmethod
    def pode_incluir(cls, usuario, plano_acao):
        return bool(
            usuario.has_perm('plan_v2.add_origemrecurso')
            and (plano_acao.em_periodo_sistemico or plano_acao.em_periodo_plano_acao or plano_acao.em_periodo_validacao)
        )

    @classmethod
    def pode_alterar(cls, usuario, plano_acao):
        return bool(
            usuario.has_perm('plan_v2.change_origemrecurso')
            and (plano_acao.em_periodo_sistemico or plano_acao.em_periodo_plano_acao or plano_acao.em_periodo_validacao)
        )

    @classmethod
    def pode_excluir(cls, usuario, plano_acao, origem_recurso_pk=None):
        verificar_uso_origem = False

        if origem_recurso_pk:
            verificar_uso_origem = Atividade.objects.filter(origem_recurso=origem_recurso_pk).exists()

        return bool(
            usuario.has_perm('plan_v2.delete_origemrecurso')
            and (plano_acao.em_periodo_sistemico or plano_acao.em_periodo_plano_acao or plano_acao.em_periodo_validacao)
            and not verificar_uso_origem
        )


class OrigemRecursoUA(ModelPlus):
    origem_recurso = models.ForeignKeyPlus('plan_v2.OrigemRecurso', on_delete=models.CASCADE)
    unidade_administrativa = models.ForeignKeyPlus('plan_v2.UnidadeAdministrativa', on_delete=models.CASCADE)
    valor_capital = models.DecimalFieldPlus('Valor Capital')
    valor_custeio = models.DecimalFieldPlus('Valor Custeio')

    class Meta:
        verbose_name = 'Origem de Recurso de UA'
        verbose_name_plural = 'Origens de Recurso de UA'

        unique_together = ('origem_recurso', 'unidade_administrativa')

        permissions = (('pode_detalhar_origemrecursoua', 'Pode detalhar a origem de recurso UA no plano de ação'),)

    def __str__(self):
        return str(self.origem_recurso)

    @property
    def valor_capital_comprometido(self):
        status = [Acao.SITUACAO_DEFERIDA, Acao.SITUACAO_ANALISADA, Acao.SITUACAO_NAO_ANALISADA]

        return next(
            iter(
                Atividade.objects.filter(
                    origem_recurso=self.origem_recurso,
                    acao_pa__unidade_administrativa=self.unidade_administrativa,
                    validacao__in=status,
                    natureza_despesa__natureza_despesa__tipo=NaturezaDespesaFin.VALOR_CAPTAL,
                )
                .aggregate(Sum('valor'))
                .values()
            )
        ) or Decimal(0)

    @property
    def valor_custeio_comprometido(self):
        status = [Acao.SITUACAO_DEFERIDA, Acao.SITUACAO_ANALISADA, Acao.SITUACAO_NAO_ANALISADA]

        return next(
            iter(
                Atividade.objects.filter(
                    origem_recurso=self.origem_recurso,
                    acao_pa__unidade_administrativa=self.unidade_administrativa,
                    validacao__in=status,
                    natureza_despesa__natureza_despesa__tipo=NaturezaDespesaFin.VALOR_CUSTEIO,
                )
                .aggregate(Sum('valor'))
                .values()
            )
        ) or Decimal(0)

    @classmethod
    def pode_incluir(cls, usuario, plano_acao):
        return False

    @classmethod
    def pode_alterar(cls, usuario, plano_acao):
        return bool(
            usuario.has_perm('plan_v2.pode_detalhar_origemrecursoua')
            and (plano_acao.em_periodo_sistemico or plano_acao.em_periodo_plano_acao or plano_acao.em_periodo_validacao)
        )

    @classmethod
    def pode_excluir(cls, usuario, plano_acao, origem_recurso_pk=None):
        return False


class NaturezaDespesaPA(ModelPlus):
    SEARCH_FIELDS = ['natureza_despesa__codigo', 'natureza_despesa__nome']

    plano_acao = models.ForeignKeyPlus('plan_v2.PlanoAcao', verbose_name='Plano de Ação')
    natureza_despesa = models.ForeignKeyPlus('financeiro.NaturezaDespesa', verbose_name='Natureza de Despesa')

    class Meta:
        verbose_name = 'Natureza de Despesa do PDI'
        verbose_name_plural = 'Naturezas de Despesa do PDI'

        permissions = (
            ('pode_ver_planoacao_naturezadespesapa', 'Pode ver natureza de despesa no plano de ação'),
            ('pode_vincular_naturezadespesapa', 'Pode vincular natureza de despesa no plano de ação'),
        )

    def __str__(self):
        return f'{self.natureza_despesa.codigo} - {self.natureza_despesa.nome}'


class AcaoPA(ModelPlus):
    meta_pa = models.ForeignKeyPlus('plan_v2.MetaPA', verbose_name='Meta', on_delete=models.CASCADE)
    unidade_administrativa = models.ForeignKeyPlus('plan_v2.UnidadeAdministrativa', verbose_name='Unidade Administrativa', on_delete=models.CASCADE)
    acao = models.ForeignKeyPlus('plan_v2.PDIAcao', verbose_name='Ação', on_delete=models.CASCADE)

    setores_responsaveis = models.ManyToManyField('rh.Setor', related_name='acao_setores_responsaveis', verbose_name='Setores Responsáveis')
    data_cadastro = models.DateTimeFieldPlus('Data de cadastro', auto_now_add=True)

    data_inicial = models.DateFieldPlus('Data Inicial', null=True)
    data_final = models.DateFieldPlus('Data Final', null=True)

    execucao = models.SmallIntegerField('Execução', default=0)

    cadastro_sistemico = models.BooleanField('Cadastrada pelo sistêmico', default=False)

    validacao = models.CharFieldPlus('Validação', choices=Acao.SITUACAO_CHOICE, default=Acao.SITUACAO_NAO_ANALISADA)

    class Meta:
        verbose_name = 'Ação no Plano de Ação'
        verbose_name_plural = 'Ações no Plano de Ação'
        unique_together = ('meta_pa', 'unidade_administrativa', 'acao')

    def __str__(self):
        return self.acao.acao.detalhamento

    def get_atividades_vincudadas(self):
        return Atividade.objects.filter(acao_pa_vinculadora=self)

    def get_atividades_origem_recurso(self):
        return Atividade.objects.filter(acao_pa=self)

    @property
    def dimensao(self):
        return self.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao

    @classmethod
    def pode_incluir(cls, usuario, plano_acao):
        eh_sistemico = in_group(usuario, 'Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional Sistêmico')

        return bool(eh_sistemico and plano_acao.em_periodo_sistemico)

    @classmethod
    def pode_alterar(cls, usuario, plano_acao):
        eh_sistemico = in_group(usuario, 'Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional Sistêmico')

        return bool(
            usuario.has_perm('plan_v2.change_acaopa') and plano_acao.em_periodo_plano_acao or eh_sistemico and plano_acao.em_periodo_sistemico
        )

    @classmethod
    def pode_incluir_atividade(cls, usuario, plano_acao):
        eh_campus = in_group(usuario, 'Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional')

        return bool(
            usuario.has_perm('plan_v2.change_acaopa')
            and plano_acao.em_periodo_plano_acao
            or eh_campus
            and plano_acao.em_periodo_plano_acao
            or eh_campus
            and plano_acao.em_periodo_validacao
        )

    @classmethod
    def pode_excluir(cls, usuario, plano_acao, acao_pa_pk=None):
        eh_sistemico = in_group(usuario, 'Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional Sistêmico')
        verificar_atividades = False

        if acao_pa_pk:
            verificar_atividades = Atividade.objects.filter(acao_pa=acao_pa_pk).exists()

        return bool((eh_sistemico and plano_acao.em_periodo_sistemico) and not verificar_atividades)


class Atividade(ModelPlus):
    acao_pa = models.ForeignKeyPlus('plan_v2.AcaoPA', verbose_name='Ação', on_delete=models.CASCADE)
    acao_pa_vinculadora = models.ForeignKeyPlus(
        'plan_v2.AcaoPA', verbose_name='Ação Vinculadora', related_name='acao_vinculada', null=True, on_delete=models.CASCADE
    )
    detalhamento = models.TextField('Detalhamento')
    observacao = models.TextField('Observação', blank=True)

    valor = models.DecimalFieldPlus('Valor', null=True)

    natureza_despesa = models.ForeignKeyPlus('plan_v2.NaturezaDespesaPA', verbose_name='Natureza de Despesa', null=True, on_delete=models.CASCADE)
    origem_recurso = models.ForeignKeyPlus(OrigemRecurso, verbose_name='Origem de Recurso', null=True, on_delete=models.CASCADE)
    execucao = models.SmallIntegerField('Execução', default=0)

    validacao = models.CharFieldPlus('Validação', choices=Acao.SITUACAO_CHOICE, default=Acao.SITUACAO_NAO_ANALISADA)
    validacao_vinculadora = models.CharFieldPlus('Validação Vinculadora', choices=Acao.SITUACAO_CHOICE, default=Acao.SITUACAO_NAO_ANALISADA)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

    def __str__(self):
        return self.detalhamento

    @classmethod
    def pode_incluir(cls, usuario, plano_acao):
        return bool(usuario.has_perm('plan_v2.add_atividade') and plano_acao.em_periodo_plano_acao)

    @classmethod
    def pode_alterar(cls, usuario, plano_acao):
        return bool(usuario.has_perm('plan_v2.change_atividade') and plano_acao.em_periodo_plano_acao)

    @classmethod
    def pode_incluir_validacao(cls, usuario, plano_acao):
        return bool(usuario.has_perm('plan_v2.add_atividade') and plano_acao.em_periodo_validacao)

    def pode_alterar_validacao(self):
        return bool(self.validacao == Acao.SITUACAO_ANALISADA or self.validacao_vinculadora == Acao.SITUACAO_ANALISADA)

    @classmethod
    def pode_excluir(cls, usuario, plano_acao):
        return bool(usuario.has_perm('plan_v2.delete_atividade') and plano_acao.em_periodo_plano_acao)


class Solicitacao(ModelPlus):
    TIPO_ACAO = 'Ação'
    TIPO_CHOICES = ((TIPO_ACAO, TIPO_ACAO),)

    PARECER_ACEITO = 'Aceito'
    PARECER_REJEITADO = 'Rejeitado'
    PARECER_ESPERA = 'Em espera'
    PARECER_CHOICES = ((PARECER_ACEITO, PARECER_ACEITO), (PARECER_REJEITADO, PARECER_REJEITADO), (PARECER_ESPERA, PARECER_ESPERA))

    unidade_administrativa = models.ForeignKeyPlus('plan_v2.UnidadeAdministrativa')
    data_solicitacao = models.DateTimeFieldPlus('Data Solicitação', auto_now_add=True)
    solicitante = models.CurrentUserField(verbose_name='Solicitante')
    tipo = models.CharFieldPlus('Tipo', choices=TIPO_CHOICES, default=TIPO_ACAO)
    solicitacao = models.TextField('Solicitação')
    parecer = models.CharFieldPlus('Parecer', choices=PARECER_CHOICES, default=PARECER_ESPERA)
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação'
        verbose_name_plural = 'Solicitações'

    def __str__(self):
        return self.solicitacao

    @property
    def em_espera(self):
        return self.parecer == self.PARECER_ESPERA
