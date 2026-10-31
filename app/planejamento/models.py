from datetime import date, datetime
from decimal import Decimal

from django import template
from django.db.models import Q

from comum.utils import tl
from djtools import db
from djtools.db import models
from djtools.templatetags.filters import in_group
from planejamento.enums import Situacao, TipoUnidade

register = template.Library()

# -------------------------------------------------------------------------------


class Configuracao(models.ModelPlus):
    """
    Responsável por indicar as datas que serão utilizadas em um planejamento
    e o ano base a que ser referem as datas
    """

    ano_base = models.OneToOneField('comum.Ano', verbose_name='Ano Base', on_delete=models.CASCADE)
    # vigência do planejamento
    data_geral_inicial = models.DateField()
    data_geral_final = models.DateField()
    # data para adição de metas (atividade das pró-reitorias)
    data_metas_inicial = models.DateField()
    data_metas_final = models.DateField()
    # data para adição de ações (atividade dos campi e pró-reitorias)
    data_acoes_inicial = models.DateField()
    data_acoes_final = models.DateField()
    # data para a validação das ações cadastradas
    data_validacao_inicial = models.DateField()
    data_validacao_final = models.DateField()
    # data para o envio de planilhas
    data_planilhas_inicial = models.DateField()
    data_planilhas_final = models.DateField()

    class Meta:
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'

        ordering = ['ano_base']

    def __str__(self):
        return f'{self.ano_base}'

    def periodo_sistemico(self):
        return not (
            not in_group(tl.get_user(), ['Administrador de Planejamento']) and not self.data_metas_inicial <= date.today() <= self.data_metas_final
        )

    def periodo_campus(self):
        return not (
            not in_group(tl.get_user(), ['Administrador de Planejamento']) and not self.data_acoes_inicial <= date.today() <= self.data_acoes_final
        )

    def periodo_validacao(self):
        return not (
            not in_group(tl.get_user(), ['Administrador de Planejamento'])
            and not self.data_validacao_inicial <= date.today() <= self.data_validacao_final
        )

    def periodo_envio_planilhas(self):
        return not (
            not in_group(tl.get_user(), ['Administrador de Planejamento'])
            and not self.data_planilhas_inicial <= date.today() <= self.data_planilhas_final
        )


# -------------------------------------------------------------------------------
class Dimensao(models.ModelPlus):
    SEARCH_FIELDS = ['descricao', 'sigla']

    """
    Indica a área da instituição responsável pelos objetivos e metas do planejamento
    """
    descricao = models.CharField('Descrição', max_length=80, unique=True)
    sigla = models.CharField('Sigla', max_length=10, unique=True)
    setor_sistemico = models.ForeignKeyPlus('rh.Setor', on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)

    class Meta:
        verbose_name = 'Dimensão'
        verbose_name_plural = 'Dimensões'

        ordering = ['codigo', 'descricao']

    def __str__(self):
        return self.descricao


# -----------------------------------------------------------------------------
class OrigemRecursoPropriaManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(Q(valor_disponivel__isnull=True) | Q(valor_disponivel=0), dimensao__isnull=True, visivel_campus=True)


class OrigemRecurso(models.ModelPlus):
    configuracao = models.ForeignKeyPlus(Configuracao, verbose_name='Ano base', on_delete=models.CASCADE)
    nome = models.CharField(max_length=70)
    valor_disponivel = models.DecimalFieldPlus('Valor Disponível', null=True)
    dimensao = models.ForeignKeyPlus(Dimensao, verbose_name='Dimensão', null=True, on_delete=models.CASCADE)
    acao_ano = models.ForeignKeyPlus('financeiro.AcaoAno', verbose_name='Ação', null=True, on_delete=models.CASCADE)
    valor_capital = models.DecimalFieldPlus('Valor de Capital')
    valor_custeio = models.DecimalFieldPlus('Valor de Custeio')
    # utilizado para filtrar quais as origens de recurso podem ser escolhidas pelos campi
    visivel_campus = models.BooleanField('Visível', help_text='Indica se a origem do recurso é visualizada pelos campi.', default=False)
    funcionamento_campus = models.BooleanField('Destinado ao funcionamento do Campus', default=False)

    objects = models.Manager()
    propria = OrigemRecursoPropriaManager()

    class Meta:
        verbose_name = 'Origem do Recurso'
        verbose_name_plural = 'Origens dos Recursos'

        unique_together = ('nome', 'dimensao', 'configuracao')
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome}'

    # no momento é considerado origem de recurso propria as origs. de recurso sem valor disponivel e sem dimensao associada
    def origem_propria(self):
        return bool(not self.valor_disponivel and not self.dimensao and self.visivel_campus)


# -----------------------------------------------------------------------------
class UnidadeMedida(models.ModelPlus):
    nome = models.CharField('Nome', max_length=50, unique=True)

    class Meta:
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'

        ordering = ['nome']

    def __str__(self):
        return self.nome


# -------------------------------------------------------------------------------
class UnidadeAdministrativa(models.ModelPlus):
    """
    Responsável pelas informações de uma unidade organizacional que será
    beneficiada por uma meta
    """

    SEARCH_FIELDS = ['codigo_simec', 'setor_equivalente__nome', 'setor_equivalente__sigla']

    configuracao = models.ForeignKeyPlus(Configuracao, verbose_name='Ano base', on_delete=models.CASCADE)
    codigo_simec = models.CharField('Código SIMEC', max_length=6, blank=True)
    codigo_simec_digito = models.CharField('Dígito', max_length=1, blank=True)
    setor_equivalente = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor Equivalente', on_delete=models.CASCADE)
    tipo = models.CharField(choices=TipoUnidade.get_choices(), max_length=20)
    orcamento = models.DecimalFieldPlus('Orçamento Próprio', null=True)

    class Meta:
        verbose_name = 'Unidade Administrativa'
        verbose_name_plural = 'Unidades Administrativas'

        ordering = ['setor_equivalente__nome']

    def __str__(self):
        return self.setor_equivalente.nome

    def get_valor_total(self):
        valor = 0
        for mu in self.metaunidade_set.all():
            valor += sum([acao.get_valor_unitario() for acao in mu.acao_set.all()])
        return valor

    # considera apenas o saldo da propria unidade administrativa
    def get_saldo_proprio(self):
        try:
            gastos = 0
            for mu in self.metaunidade_set.all():
                gastos += sum([acao.get_valor_unitario_proprio() for acao in mu.acao_set.all()])
            saldo = self.orcamento - gastos
        except Exception:
            saldo = None
        else:
            if saldo < 0:
                saldo = False, abs(saldo)
            else:
                saldo = True, saldo
        return saldo

    # considera qualquer tipo de recurso para o cálculo do slado
    def get_saldo(self):
        try:
            saldo = self.orcamento - self.get_valor_total()
        except Exception:
            saldo = None
        else:
            if saldo < 0:
                saldo = False, abs(saldo)
            else:
                saldo = True, saldo
        return saldo

    def save(self, *args, **kwargs):
        if self.codigo_simec:
            if not self.pk or (self.pk and UnidadeAdministrativa.objects.get(pk=self.pk).codigo_simec != self.codigo_simec):
                unidades = UnidadeAdministrativa.objects.filter(codigo_simec=self.codigo_simec)
                self.codigo_simec_digito = str(len(unidades))
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
class OrigemRecursoUA(models.ModelPlus):
    origem_recurso = models.ForeignKeyPlus(OrigemRecurso, verbose_name='Origem de Recurso', on_delete=models.CASCADE)
    unidade = models.ForeignKeyPlus(UnidadeAdministrativa, verbose_name='Unidade Administrativa', on_delete=models.CASCADE)
    valor_capital = models.DecimalFieldPlus('Valor Capital')
    valor_custeio = models.DecimalFieldPlus('Valor Custeio')

    class Meta:
        verbose_name = 'Origem de Recurso de UA'
        verbose_name_plural = 'Origens de Recurso de UA'

        unique_together = ('origem_recurso', 'unidade')

    def __str__(self):
        return f'{self.origem_recurso}'

    @property
    def valor_capital_planejado(self):
        strConsulta = """
            SELECT COALESCE(SUM(at.quantidade * at.valor_unitario), 0) AS total
              FROM planejamento_atividade at,
                   planejamento_acao a,
                   planejamento_metaunidade mu,
                   planejamento_origemrecurso o,
                   planejamento_naturezadespesa n,
                   financeiro_naturezadespesa fn
             WHERE at.tipo_recurso_id = o.id
               AND at.acao_id = a.id
               AND at.elemento_despesa_id = n.id
               AND a.meta_unidade_id = mu.id
               AND a.status != 'Indeferida'
               AND n.naturezadespesa_id = fn.id
               AND o.configuracao_id = {}
               AND fn.tipo = '{}'
               AND mu.unidade_id = {}
               AND o.id = {}
        """.format(
            self.origem_recurso.configuracao.pk,
            'Capital',
            self.unidade.pk,
            self.origem_recurso.pk,
        )

        valor_total = db.get_dict(strConsulta)
        valor_total = valor_total[0]['total']

        return valor_total

    @property
    def valor_custeio_planejado(self):
        strConsulta = """
            SELECT COALESCE(SUM(at.quantidade * at.valor_unitario), 0) AS total
              FROM planejamento_atividade at,
                   planejamento_acao a,
                   planejamento_metaunidade mu,
                   planejamento_origemrecurso o,
                   planejamento_naturezadespesa n,
                   financeiro_naturezadespesa fn
             WHERE at.tipo_recurso_id = o.id
               AND at.acao_id = a.id
               AND at.elemento_despesa_id = n.id
               AND a.meta_unidade_id = mu.id
               AND a.status != 'Indeferida'
               AND n.naturezadespesa_id = fn.id
               AND o.configuracao_id = {}
               AND fn.tipo = '{}'
               AND mu.unidade_id = {}
               AND o.id = {}
        """.format(
            self.origem_recurso.configuracao.pk,
            'Custeio',
            self.unidade.pk,
            self.origem_recurso.pk,
        )

        valor_total = db.get_dict(strConsulta)
        valor_total = valor_total[0]['total']

        return valor_total


# -------------------------------------------------------------------------------
class ObjetivoEstrategico(models.ModelPlus):
    SEARCH_FIELDS = ['macro_projeto_institucional', 'descricao']
    """

    Conforme solicitação, o Objetivo Estratégico deve ser substituido por Macro Projeto Institucional,
    mas para continuar com a coerência dos dados dos planejamentos dos anos anteriores, resolveu-se permanecer com ObjetivoEstrategico e adicionar
    o atributo macro_projeto_institucional, onde "descricao" agora se refere ao objetivo estrategico.

    """
    macro_projeto_institucional = models.CharFieldPlus('Macro Projeto Institucional')
    data_cadastro = models.DateTimeField('Data de Cadastro', default=datetime.now)
    descricao = models.TextField('Objetivo Estratégico')
    configuracao = models.ForeignKeyPlus(Configuracao, verbose_name='Ano Base', on_delete=models.CASCADE)
    dimensao = models.ForeignKeyPlus(Dimensao, verbose_name='Dimensão', on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)

    class Meta:
        verbose_name = 'Macro Projeto Institucional'
        verbose_name_plural = 'Macro Projeto Institucional'

        unique_together = ('configuracao', 'descricao', 'dimensao')
        ordering = ['dimensao', 'codigo', 'descricao']

    def __str__(self):
        return self.macro_projeto_institucional or '-'

    def get_codigo_completo(self):
        cod_dimensao = self.dimensao.codigo or 'x'
        cod_objestra = self.codigo or 'x'
        return f'{cod_dimensao}.{cod_objestra}'

    def ano_base(self):
        return self.configuracao.ano_base

    """Verifica se o objetivo estratégico possui atividades cadastradas para uma determinada unid administrativa"""

    def possui_atividades(self, unidade_administrativa):
        atividades = Atividade.objects.filter(acao__meta_unidade__meta__objetivo_estrategico=self, acao__meta_unidade__unidade=unidade_administrativa)
        return bool(len(atividades))


# -------------------------------------------------------------------------------
class Meta(models.ModelPlus):
    SEARCH_FIELDS = ['titulo']

    """
    """
    data_cadastro = models.DateTimeField('Data de Cadastro', default=datetime.now)
    objetivo_estrategico = models.ForeignKeyPlus(ObjetivoEstrategico, verbose_name='Objetivo Estratégico', on_delete=models.CASCADE)
    titulo = models.TextField('Título')
    justificativa = models.TextField()
    unidade_medida = models.ForeignKeyPlus('planejamento.UnidadeMedida', verbose_name='Unidade de Medida', null=True, on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)

    # período de execução
    data_inicial = models.DateField()
    data_final = models.DateField()

    class Meta:
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'

        unique_together = ('objetivo_estrategico', 'titulo')
        ordering = ['objetivo_estrategico__codigo', 'codigo', 'titulo']

    def __str__(self):
        return self.titulo

    def get_codigo_completo(self):
        cod_obj = self.objetivo_estrategico.get_codigo_completo()
        cod_met = self.codigo or 'x'
        return f'{cod_obj}.{cod_met}'

    def get_quantidade_total(self):
        return sum([muap.quantidade for muap in self.metaunidade_set.all()])

    def get_valor_total(self):
        return sum([muap.valor_total for muap in self.metaunidade_set.all()])


# -------------------------------------------------------------------------------
class MetaUnidade(models.ModelPlus):
    """
    Unidade Administrativa associada a cada Meta
    """

    SEARCH_FIELDS = ['meta__titulo', 'unidade__setor_equivalente__nome', 'unidade__setor_equivalente__sigla']

    meta = models.ForeignKeyPlus(Meta, on_delete=models.CASCADE)
    unidade = models.ForeignKeyPlus(UnidadeAdministrativa, verbose_name='Unidade Administrativa', on_delete=models.CASCADE)
    quantidade = models.IntegerField('Quantidade', default=1)
    valor_total = models.DecimalFieldPlus('Valor Total', default=Decimal('0.0'))

    class Meta:
        verbose_name = 'Unidade Administrativa da Meta'
        verbose_name_plural = 'Unidades Administrativas das Metas'

        unique_together = ('meta', 'unidade')
        ordering = ['meta', 'unidade']

    def __str__(self):
        return f'{self.unidade}'

    def sort(self):
        return f'{self.get_codigo_completo()} {self.meta.titulo}'

    def get_codigo_completo(self):
        return self.meta.get_codigo_completo()

    def acompanhamento_execucao(self):
        acoes = self.acao_set.all().filter(status='Deferida')
        n_total = acoes.count()
        n_concluidas = 0

        for a in acoes:
            if a.execucao == 100:
                n_concluidas += 1

        if n_total:
            return float(n_concluidas) / n_total * 100
        return 0

    def str_acompanhamento_execucao(self):
        acoes = self.acao_set.all().filter(status='Deferida')
        n_total = acoes.count()
        n_concluidas = 0

        for a in acoes:
            if a.execucao == 100:
                n_concluidas += 1

        return f'{n_concluidas}/{n_total}'

    def get_valor_proposto(self):
        return self.valor_total or 0

    def get_valor_total(self):
        return sum([acao.get_valor_unitario() for acao in self.acao_set.all()])

    def get_total_acoes(self):
        return Acao.objects.filter(meta_unidade=self).count()

    def get_total_acoes_parcialmente_deferida(self):
        return Acao.objects.filter(meta_unidade=self, status=Situacao.PARCIALMENTE_DEFERIDA).count()

    def get_total_acoes_pendentes(self):
        if not self.acao_set.exists():
            return None
        return Acao.objects.filter(meta_unidade=self, status=Situacao.PENDENTE).count() + self.get_total_acoes_parcialmente_deferida()

    def get_total_acoes_deferidas(self):
        return Acao.objects.filter(meta_unidade=self, status=Situacao.DEFERIDA).count()

    def get_total_acoes_indeferidas(self):
        return Acao.objects.filter(meta_unidade=self, status=Situacao.INDEFERIDA).count()


# -------------------------------------------------------------------------------
class AcaoProposta(models.ModelPlus):
    SEARCH_FIELDS = ['titulo']

    """
    Cada atividade proposta pela pró-reitoria para os campi
    """
    data_cadastro = models.DateTimeField('Data de Cadastro', default=datetime.now)
    meta = models.ForeignKeyPlus(Meta, on_delete=models.CASCADE)
    titulo = models.CharField('Titulo', max_length=250)
    acao_orcamento = models.ForeignKeyPlus('financeiro.Acao', null=True, on_delete=models.CASCADE)
    fonte_financiamento = models.ForeignKeyPlus('financeiro.FonteRecurso', on_delete=models.CASCADE)
    unidade_medida = models.ForeignKeyPlus('planejamento.UnidadeMedida', null=True, on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)

    # período de execução
    data_inicial = models.DateField(null=True)
    data_final = models.DateField(null=True)

    class Meta:
        verbose_name = 'Ação Proposta'
        verbose_name_plural = 'Ações Propostas'

        unique_together = ('meta', 'titulo')
        ordering = ['codigo', 'titulo']

    def __str__(self):
        return self.titulo

    def sort(self):
        return f'{self.get_codigo_completo()} {self.titulo}'

    def get_codigo_completo(self):
        cod_acao = self.codigo or 'x'
        return f'{self.meta.get_codigo_completo()}.{cod_acao}'

    def get_quantidade_total(self):
        return sum([muap.quantidade for muap in self.metaunidadeacaoproposta_set.all()])

    def get_valor_total(self):
        return sum([(muap.quantidade * muap.valor_unitario) for muap in self.metaunidadeacaoproposta_set.all()])

    def save(self, *args, **kwargs):
        if not self.pk:
            try:
                acao_proposta = AcaoProposta.objects.filter(meta=self.meta).latest('codigo')
                self.codigo = acao_proposta.codigo + 1
            except Exception:
                self.codigo = 1
        super().save(*args, **kwargs)
        for mua in self.metaunidadeacaoproposta_set.all():
            for acao in mua.acao_set.all():
                acao.titulo = self.titulo
                acao.acao_orcamento = self.acao_orcamento
                acao.fonte_financiamento = self.fonte_financiamento
                acao.unidade_medida = self.unidade_medida
                acao.codigo = self.codigo
                acao.save()


# -------------------------------------------------------------------------------
class MetaUnidadeAcaoProposta(models.ModelPlus):
    """
    Relação entre uma ação proposta e a unidade administrativa associada a ela
    """

    meta_unidade = models.ForeignKeyPlus(MetaUnidade, verbose_name='Unid. Administrativa', on_delete=models.CASCADE)
    acao_proposta = models.ForeignKeyPlus(AcaoProposta, verbose_name='Ação Proposta', on_delete=models.CASCADE)
    quantidade = models.IntegerField('Quantidade', null=True)
    valor_unitario = models.DecimalFieldPlus('Valor Unitário', null=True)

    class Meta:
        verbose_name = 'Unid. Administrativa da Ação Proposta'
        verbose_name_plural = 'Unids. Administrativas das Ações Propostas'

        unique_together = ('meta_unidade', 'acao_proposta')
        ordering = ['meta_unidade', 'acao_proposta']

    def __str__(self):
        return f'{self.meta_unidade.unidade}'

    def get_valor_total(self):
        if self.quantidade > 0 and self.valor_unitario > 0:
            return self.quantidade * self.valor_unitario
        return 0


# -------------------------------------------------------------------------------
class Acao(models.ModelPlus):
    """
    Cada atividade que deve ser realizada para cumprir uma meta destinada a um campus
    """

    data_cadastro = models.DateTimeField('Data de Cadastro', default=datetime.now)
    meta_unidade = models.ForeignKeyPlus(MetaUnidade, verbose_name='Meta', on_delete=models.CASCADE)
    titulo = models.CharField('Titulo', max_length=250)
    detalhamento = models.TextField()
    unidade_medida = models.ForeignKeyPlus(
        'planejamento.UnidadeMedida', related_name='planejamento_acao_unidademedida', null=True, on_delete=models.CASCADE
    )
    quantidade = models.IntegerField('Quantidade', null=True)
    setor_responsavel = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor Responsável', on_delete=models.CASCADE)
    acao_orcamento = models.ForeignKeyPlus('financeiro.Acao', null=True, on_delete=models.CASCADE)
    fonte_financiamento = models.ForeignKeyPlus('financeiro.FonteRecurso', on_delete=models.CASCADE)
    codigo = models.IntegerField('Código', null=True)
    execucao = models.SmallIntegerField('Execução', default=0)

    # período de execução
    data_inicial = models.DateField()
    data_final = models.DateField()

    # indica qual a acao cadastrada pela pró-reitoria induziu esta acao
    acao_indutora = models.ForeignKeyPlus(MetaUnidadeAcaoProposta, null=True, on_delete=models.CASCADE)

    # indica se a ação já foi validada pelo pró-reitor
    status = models.CharField(Situacao.get_choices(), default=Situacao.PENDENTE, max_length=30)

    class Meta:
        verbose_name = 'Ação'
        verbose_name_plural = 'Ações'

        unique_together = ('meta_unidade', 'titulo')
        ordering = ['codigo', 'titulo']

    def __str__(self):
        return self.titulo

    def sort(self):
        return f'{self.get_codigo_completo()} {self.titulo}'

    # indica qual o percentual de execucao da acao em relacao ao numero de atividades concluidas
    # utilizado no save de AtividadeExecucao
    def _get_execucao_atividades(self):
        atividades = self.atividade_set.all()
        n_at_total = atividades.count()
        n_at_concluidas = 0

        for at in atividades:
            if at.execucao == 100:
                n_at_concluidas += 1

        if n_at_total:
            return round(float(n_at_concluidas) / n_at_total * 100)
        else:
            return 0

    def acompanhamento_execucao(self):
        atividades = self.atividade_set.all()
        n_at_total = atividades.count()
        n_at_concluidas = 0

        if n_at_total:
            for at in atividades:
                if at.execucao == 100:
                    n_at_concluidas += 1

            if n_at_total:
                return float(n_at_concluidas) / n_at_total * 100
            else:
                return 0
        else:
            return self.execucao

    def str_acompanhamento_execucao(self):
        atividades = self.atividade_set.all()
        n_at_total = atividades.count()
        n_at_concluidas = 0

        if n_at_total:
            for at in atividades:
                if at.execucao == 100:
                    n_at_concluidas += 1
            return f'{n_at_concluidas}/{n_at_total}'
        return '1/1'

    def get_codigo_completo(self):
        cod_acao = self.codigo or 'x'
        return f'{self.meta_unidade.get_codigo_completo()}.{cod_acao}'

    def get_acao_orcamento(self):
        return self.acao_orcamento.nome

    def get_fonte_financiamento(self):
        return self.fonte_financiamento.descricao

    def get_quantidade_proposta(self):
        if self.acao_indutora:
            return self.acao_indutora.quantidade
        return 0

    def get_valor_referencia(self):
        if self.acao_indutora:
            return self.acao_indutora.quantidade * self.acao_indutora.valor_unitario
        return 0

    # indica qual o valor gasto com recursos proprio na acao. considera apenas as ações com status diferente de indeferida
    def get_valor_unitario_proprio(self):
        valor = 0
        if self.status != 'Indeferida':
            for atividade in self.atividade_set.all():
                if atividade.utiliza_recurso_proprio():
                    valor += atividade.quantidade * atividade.valor_unitario
        return valor

    def get_valor_unitario(self):
        return sum([(atividade.quantidade * atividade.valor_unitario) for atividade in self.atividade_set.all()])

    def get_valor_total(self):
        return self.get_valor_unitario()

    def is_pendente(self):
        return self.status == Situacao.PENDENTE

    def is_parcialmente_deferida(self):
        return self.status == Situacao.PARCIALMENTE_DEFERIDA

    def has_comentario(self):
        return self.acaovalidacao_set.exists()

    def pode_comentar(self):
        return self.status != Situacao.DEFERIDA

    def save(self, *args, **kwargs):
        if not self.codigo:
            acoes = Acao.objects.filter(meta_unidade=self.meta_unidade, acao_indutora__isnull=False)
            if acoes.exists():
                acao = acoes.latest('codigo')
                self.codigo = acao.codigo + 1
            else:
                try:
                    acao_proposta = AcaoProposta.objects.filter(meta=self.meta_unidade.meta).latest('codigo')
                    self.codigo = acao_proposta.codigo + 1
                except Exception:
                    self.codigo = 1
        super().save(*args, **kwargs)


# -------------------------------------------------------------------------------
class AcaoExtraTeto(models.ModelPlus):
    """
    Ações que não podem ser adicionadas diretamente no planejamento por que dependem da confirmação do recurso disponível.
    """

    unidade = models.ForeignKeyPlus(UnidadeAdministrativa, verbose_name='Unidade Administrativa', on_delete=models.CASCADE)
    titulo = models.CharField('Titulo', max_length=250)
    detalhamento = models.TextField()
    quantidade = models.IntegerField('Quantidade')
    unidade_medida = models.ForeignKeyPlus(UnidadeMedida, verbose_name='Unidade de Medida', on_delete=models.CASCADE)
    valor_previsto = models.DecimalFieldPlus('Valor Previsto')

    class Meta:
        verbose_name = 'Ação Extra Teto'
        verbose_name_plural = 'Ações Extra Teto'

        ordering = ['titulo']

    def __str__(self):
        return self.titulo


# -------------------------------------------------------------------------------
class AcaoValidacao(models.ModelPlus):
    acao = models.ForeignKeyPlus('planejamento.Acao', on_delete=models.CASCADE)
    data = models.DateTimeField(default=datetime.now)
    status = models.CharField(Situacao.get_choices(), max_length=30)

    class Meta:
        verbose_name = 'Comentário da Ação'
        verbose_name_plural = 'Comentários da Ação'

        ordering = ['acao', 'status']
        get_latest_by = 'data'

    def __str__(self):
        return str(self.acao)


class AcaoExecucao(models.ModelPlus):
    acao = models.ForeignKeyPlus('planejamento.Acao', on_delete=models.CASCADE)
    data = models.DateTimeField(default=datetime.now)
    texto = models.TextField()
    percentual = models.SmallIntegerField('Execução')

    class Meta:
        verbose_name = 'Acompanhamento da Ação'
        verbose_name_plural = 'Acompanhamentos da Ação'

        ordering = ['-data']

    def __str__(self):
        return self.texto

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # atualizacao a acao
        acao = self.acao
        acao.execucao = self.percentual
        acao.save()


# -------------------------------------------------------------------
class NaturezaDespesa(models.ModelPlus):
    naturezadespesa = models.ForeignKeyPlus('financeiro.NaturezaDespesa', verbose_name='Natureza de Despesa', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Natureza de Despesa'
        verbose_name_plural = 'Naturezas de despesas'

        ordering = ['naturezadespesa']

    def __str__(self):
        return f'{self.naturezadespesa}'


# -------------------------------------------------------------------------------
class Atividade(models.ModelPlus):
    acao = models.ForeignKeyPlus(Acao, verbose_name='Ação', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    detalhamento = models.TextField('Detalhamento', null=True)
    unidade_medida = models.ForeignKeyPlus('planejamento.UnidadeMedida', verbose_name='Unidade de Medida', on_delete=models.CASCADE)
    quantidade = models.IntegerField('Quantidade')
    valor_unitario = models.DecimalFieldPlus('Valor Unitário')
    elemento_despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Elemento de Despesa', null=True, on_delete=models.CASCADE)
    tipo_recurso = models.ForeignKeyPlus(OrigemRecurso, verbose_name='Origem de Recurso', null=True, on_delete=models.CASCADE)
    execucao = models.SmallIntegerField('Execução', default=0)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

        unique_together = ('acao', 'descricao', 'elemento_despesa')
        ordering = ['acao', 'descricao']

    def __str__(self):
        return self.descricao

    # no momento é considerado recurso proprio as origs. de recurso sem valor disponivel e sem dimensao
    def utiliza_recurso_proprio(self):
        if self.tipo_recurso:
            return self.tipo_recurso.origem_propria()
        else:
            return False

    def get_valor_total(self):
        return self.quantidade * self.valor_unitario

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # atualiza o percentual de execucao da acao
        # utilizado para evitar que uma atividade seja criada após a validação de uma ação
        # não continha atividades ter sido executada
        if self.acao.execucao:
            acao = self.acao
            acao.execucao = acao._get_execucao_atividades()
            acao.save()

            execucao = AcaoExecucao()
            execucao.acao = acao
            execucao.texto = f"a atividade '{self}' foi criada"
            execucao.percentual = acao._get_execucao_atividades()
            execucao.save()


# -------------------------------------------------------------------------------
class AtividadeExecucao(models.ModelPlus):
    atividade = models.ForeignKeyPlus(Atividade, on_delete=models.CASCADE)
    data = models.DateTimeField(default=datetime.now)
    texto = models.TextField()
    percentual = models.SmallIntegerField('Execução')

    class Meta:
        verbose_name = 'Acompanhamento da Atividade'
        verbose_name_plural = 'Acompanhamentos da Atividade'

        ordering = ['-data']

    def __str__(self):
        return self.texto

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # atualiza a atividade
        atividade = self.atividade
        atividade.execucao = self.percentual
        atividade.save()

        # atualiza a acao
        acao = atividade.acao
        acao.execucao = acao._get_execucao_atividades()
        acao.save()
