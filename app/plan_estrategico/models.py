import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.utils import timezone

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Q, Subquery, Value
from django.db.models.aggregates import Sum
from django.db.models.functions import Coalesce, Concat
from django.shortcuts import get_object_or_404
from django.template import defaultfilters
from django.utils.safestring import mark_safe

from comum.models import Configuracao, User, UsuarioGrupo
from comum.utils import tl
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.storages import cache_file
from djtools.templatetags.filters.utils import format_iterable, in_group
from djtools.utils import eval_expr, render_to_string, send_notification
from documento_eletronico.models import Documento, DocumentoDigitalizado, DocumentoTexto, TipoDocumento
from financeiro.models import CategoriaApropriacao, ClassificacaoInstitucional, ProgramaTrabalhoResumido
from processo_eletronico.models import Processo
from rh.models import Atividade, ServidorFuncaoHistorico, Setor, UnidadeOrganizacional
from tesouro_gerencial.models import DocumentoEmpenho, DocumentoEmpenhoItem, EventoNotaEmpenho

# Modelos do PDI e Farol de Desempenho -------------------------------------------------------------------------------------------------------


class PDI(ModelPlus):
    qtd_anos = models.IntegerField(verbose_name='Duração em anos', null=True)
    ano_inicial_pdi = models.ForeignKeyPlus(
        'comum.Ano', related_name='ano_inicial_pdi_plan_estrategico', verbose_name='Ano Inicial', help_text='Vigência inicial do PDI'
    )
    ano_final_pdi = models.ForeignKeyPlus(
        'comum.Ano', related_name='ano_final_pdi_plan_estrategico', verbose_name='Ano Final', help_text='Vigência final do PDI'
    )
    documento = models.FileFieldPlus(upload_to='plan_estrategico/anexos/', max_length=255, verbose_name='Documento PDI')
    mapa_estrategico = models.FileFieldPlus(
        upload_to='plan_estrategico/anexos/', max_length=255, verbose_name='Mapa Estratégico', null=True, blank=True, can_view=True
    )
    manual = models.FileFieldPlus(upload_to='plan_estrategico/anexos/', max_length=255, verbose_name='Manual de Indicadores', null=True, blank=True)
    valor_faixa_verde = models.DecimalField(verbose_name='Valor Inicial da Faixa Verde', max_digits=12, decimal_places=2, default=0)
    valor_faixa_amarela = models.DecimalField(verbose_name='Valor Inicial da Faixa Amarela', max_digits=12, decimal_places=2, default=0)
    valor_faixa_vermelha = models.DecimalField(verbose_name='Valor Inicial da Faixa Vermelha ', max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'PDI'
        verbose_name_plural = 'PDIs'
        unique_together = ('ano_inicial_pdi', 'ano_final_pdi')

    def __str__(self):
        return f'De {self.ano_inicial_pdi} até {self.ano_final_pdi}'


class Perspectiva(ModelPlus):
    SEARCH_FIELDS = ['sigla', 'nome']

    sigla = models.CharFieldPlus('Sigla')
    nome = models.CharFieldPlus('Nome')
    descricao = models.TextField('Descrição', blank=True)

    class Meta:
        verbose_name = 'Perspectiva'
        verbose_name_plural = 'Perspectivas'

    def __str__(self):
        return self.nome


class PDIPerspectiva(ModelPlus):
    pdi = models.ForeignKey(PDI, related_name='perspectivas', verbose_name='PDI', on_delete=models.CASCADE)
    perspectiva = models.ForeignKey('Perspectiva', verbose_name='Perspectiva', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Perspectiva do PDI'
        verbose_name_plural = 'Perspectivas do PDI'

        unique_together = ('pdi', 'perspectiva')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.perspectiva.sigla}'


class UnidadeGestora(ModelPlus):
    SEARCH_FIELDS = ['setor_equivalente__sigla', 'setor_equivalente__nome']
    TIPO_GESTOR_SISTEMICO = 'Gestor Sistêmico'
    TIPO_CAMPUS = 'Campus'
    TIPO_CHOICES = ((TIPO_GESTOR_SISTEMICO, TIPO_GESTOR_SISTEMICO), (TIPO_CAMPUS, TIPO_CAMPUS))
    pdi = models.ForeignKey(PDI, on_delete=models.CASCADE)
    setor_equivalente = models.ForeignKey('rh.Setor', verbose_name='Setor equivalente', related_name='unidadegestora_setor', on_delete=models.CASCADE)
    setor_financeiro = models.ForeignKey(
        'rh.Setor',
        verbose_name='Setor responsável financeiro',
        related_name='unidadegestora_setor_financeiro',
        on_delete=models.CASCADE,
        null=True,
    )
    setor_administrativo = models.ForeignKey(
        'rh.Setor',
        verbose_name='Setor responsável administrativo',
        related_name='unidadegestora_setor_adminstrativo',
        on_delete=models.CASCADE,
        null=True,
    )
    setor_ordenador_despesa = models.ForeignKey(
        'rh.Setor',
        verbose_name='Setor responsável ordenador de despesa',
        related_name='unidadegestora_setor_ordenador_despesa',
        on_delete=models.CASCADE,
        null=True,
    )
    setor_anuencia_despesa = models.ForeignKey(
        'rh.Setor',
        verbose_name='Setor Anuência da Despesa',
        related_name='unidadegestora_setor_anuencia_despesa',
        on_delete=models.CASCADE,
        null=True,
    )
    tipo = models.CharField('Tipo', max_length=20, choices=TIPO_CHOICES)
    codigo_projeto = models.CharFieldPlus(verbose_name='Código para projeto', max_length=1, null=True, blank=True)
    codigo_macroprocesso = models.CharFieldPlus(verbose_name='Código para macroprocesso', max_length=2, null=True, blank=True)
    recurso_total = models.BooleanField('Pode Alocar 100% do Recurso no componente especial?', default=False)
    codigo_ug = models.CharField(max_length=6, blank=True, verbose_name='Código UG')
    codigo_ugr = models.CharField(max_length=6, blank=True, verbose_name='Código UGR')
    ug_secundaria = models.CharField(max_length=6, blank=True, verbose_name='UG Secundária')

    class Meta:
        verbose_name = 'Unidade Gestora'
        verbose_name_plural = 'Unidades Gestoras'

        ordering = ('tipo', 'setor_equivalente__nome')
        unique_together = ('pdi', 'setor_equivalente')

    def __str__(self):
        return f'{self.setor_equivalente.sigla} - {self.setor_equivalente.nome}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def participa_planoatividade(self):
        return bool(UnidadeGestoraEtapa.objects.filter(unidade_gestora=self).exists())

    def eh_diretor(self, user: User) -> bool:
        """Indica se o usuário tem função ativa de Diretor, Diretor-Geral ou Reitor no setor equivalente da unidade gestora."""
        vinculo = user.get_vinculo()
        if not vinculo or not vinculo.eh_servidor():
            return False
        return vinculo.relacionamento.historico_funcao_ativa.filter(
            atividade__codigo__in=[Atividade.DIRETOR, Atividade.DIRETOR_GERAL, Atividade.REITOR],
            setor_suap=self.setor_equivalente,
        ).exists()

    def possui_diretor_geral(self) -> bool:
        """Indica se há servidor ativo com função ativa de Diretor-Geral (0009) ou Reitor (0062) no setor equivalente da unidade gestora
        ou no setor do seu campus (ex.: a PROAD, abaixo da Reitoria, tem o Reitor como dirigente)."""
        setores = [self.setor_equivalente]
        uo = self.setor_equivalente.uo
        if uo and uo.setor_id:
            setores.append(uo.setor)
        return self._possui_servidor_com_funcao_ativa([Atividade.DIRETOR_GERAL, Atividade.REITOR], setores)

    def possui_anuente(self) -> bool:
        """Indica se há servidor ativo com função ativa de Diretor, Diretor-Geral ou Reitor no setor equivalente, apto a anuir a despesa."""
        return self._possui_servidor_com_funcao_ativa([Atividade.DIRETOR, Atividade.DIRETOR_GERAL, Atividade.REITOR], [self.setor_equivalente])

    def _possui_servidor_com_funcao_ativa(self, codigos_atividade: list[str], setores: list[Setor]) -> bool:
        hoje = date.today()
        return (
            ServidorFuncaoHistorico.objects.filter(
                atividade__codigo__in=codigos_atividade,
                setor_suap__in=setores,
                servidor__ativo=True,
                data_inicio_funcao__lte=hoje,
            )
            .filter(Q(data_fim_funcao__gte=hoje) | Q(data_fim_funcao__isnull=True))
            .exists()
        )

    def get_ug_secundaria(self):
        """Unidade gestora do mesmo PDI cujo código UG é o informado em UG Secundária."""
        if not self.ug_secundaria:
            return None
        return UnidadeGestora.objects.filter(pdi_id=self.pdi_id, codigo_ug=self.ug_secundaria).exclude(pk=self.pk).first()

    def get_valor_disponivel_movimentacao(self, unidade_gestora=None, origem_recurso=None):
        origem_recurso = get_object_or_404(OrigemRecursoProjeto, pk=origem_recurso.id)
        total_rateio = AtividadeEtapa.objects.filter(
            origem_recurso_etapa__origem_recurso_projeto=origem_recurso, unidade_gestora=unidade_gestora
        ).aggregate(Sum('valor_rateio')).get('valor_rateio__sum') or Decimal(0)
        total_reserva_tecnica = AtividadeEtapa.objects.filter(
            origem_recurso_etapa__origem_recurso_projeto=origem_recurso, unidade_gestora=unidade_gestora
        ).aggregate(Sum('valor_reserva_tecnica')).get('valor_reserva_tecnica__sum') or Decimal(0)
        total_realocado = AtividadeEtapa.objects.filter(origem_recurso_etapa__origem_recurso_projeto=origem_recurso).aggregate(
            Sum('valor_realocado')
        ).get('valor_realocado__sum') or Decimal(0)

        return total_rateio + total_reserva_tecnica + total_realocado


class ObjetivoEstrategico(ModelPlus):
    sigla = models.CharFieldPlus('Sigla')
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Objetivo Estratégico'
        verbose_name_plural = 'Objetivos Estratégicos'

    def __str__(self):
        return f'{self.descricao}'


class PDIObjetivoEstrategico(ModelPlus):
    pdi = models.ForeignKey(PDI, on_delete=models.CASCADE)
    pdi_perspectiva = models.ForeignKey(PDIPerspectiva, verbose_name='Perspectiva', on_delete=models.CASCADE)
    objetivo = models.ForeignKey(ObjetivoEstrategico, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Objetivo Estratégico do PDI'
        verbose_name_plural = 'Objetivos Estratégicos do PDI'
        unique_together = (('pdi', 'objetivo'),)

    def __str__(self):
        return f'{self.objetivo.sigla} - {self.objetivo.descricao}'

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.pdi = self.pdi_perspectiva.pdi
        super().save(*args, **kwargs)

    def get_objetivo_valor_meta(self, uo=None, ano_base=None):
        total_relevancia = 0
        total = 0
        for ind in ObjetivoIndicador.objects.filter(objetivo_estrategico=self).exclude(indicador__indicador__indicador_acompanhamento=True):
            if ind.indicador.verificar_variavel_ideal_vazia(uo, ano_base):
                return 'Indicadores com Variáveis não Informadas.'
            total += ind.indicador.get_metaindicador_valor(uo, ano_base) * ind.relevancia
            total_relevancia += ind.relevancia
        if total_relevancia != 0:
            total = total / total_relevancia
        if total_relevancia != 100:
            return 'Relevância Diferente de 100%'
        return total

    def get_objetivo_valor_real(self, uo=None, ano_base=None):
        total_relevancia = 0
        total = 0
        for ind in ObjetivoIndicador.objects.filter(objetivo_estrategico=self).exclude(indicador__indicador__indicador_acompanhamento=True):
            if ind.indicador.verificar_variavel_real_vazia(uo, ano_base) or ind.indicador.verificar_variavel_ideal_vazia(uo, ano_base):
                return 'Indicadores com variáveis não informadas.'

            if ind.indicador.get_porcentagem_alcancada(uo, ano_base) < 100:
                total += ind.indicador.get_porcentagem_alcancada(uo, ano_base) * ind.relevancia
            else:
                total += ind.relevancia * 100

            total_relevancia += ind.relevancia
        if total_relevancia != 0:
            total = total / total_relevancia
        if total_relevancia != 100:
            return 'Relevância diferente de 100%'
        return total

    def get_status_farol_objetivo(self, uo=None, ano_base=None):
        porcentagem = self.get_objetivo_valor_real(uo, ano_base)
        if type(porcentagem) is not str:
            if self.pdi.valor_faixa_verde <= porcentagem:
                return 'Alcançado'
            elif self.pdi.valor_faixa_amarela <= porcentagem < self.pdi.valor_faixa_verde:
                return 'Parcialmente'
            elif self.pdi.valor_faixa_vermelha <= porcentagem < self.pdi.valor_faixa_amarela:
                return 'Não Alcançado'
        return 'Não Informado'


class ProjetoEstrategico(ModelPlus):
    TIPO_ROTINEIRO = 'Rotineiro'
    TIPO_ESTRATEGICO = 'Estratégico'

    TIPO_PROJETO = ((TIPO_ROTINEIRO, TIPO_ROTINEIRO), (TIPO_ESTRATEGICO, TIPO_ESTRATEGICO))

    codigo = models.CharField(verbose_name='Código', max_length=2, null=True)
    pdi = models.ForeignKey(PDI, verbose_name='PDI', on_delete=models.CASCADE)
    nome = models.CharField(max_length=100, verbose_name='Nome')
    descricao = models.TextField('Descrição', null=True)
    objetivo_estrategico = models.ManyToManyField(PDIObjetivoEstrategico, verbose_name='Objetivo Estratégico')
    unidade_gestora = models.ForeignKey(UnidadeGestora, verbose_name='Unidade Gestora', on_delete=models.CASCADE)
    recurso_total = models.DecimalFieldPlus('Recurso Total', null=True)
    meta_projeto = models.DecimalFieldPlus('Meta do Projeto', help_text='Resultado esperado do projeto', null=True)
    unidade_medida = models.CharField(max_length=50, verbose_name='Unidade de Medida', help_text='Unidade de medida da meta', null=True)
    data_inicio = models.DateField(verbose_name='Data Inicial', null=True)
    data_fim = models.DateField(verbose_name='Data Final', null=True)
    tipo = models.CharFieldPlus('Tipo', choices=TIPO_PROJETO, default=TIPO_ESTRATEGICO)
    anexo = models.FileFieldPlus(upload_to='plan_estrategico/anexos/', max_length=255, verbose_name='Projeto Estratégico', null=True)
    macroprocesso = models.BooleanField('É macroprocesso?', default=False)

    class Meta:
        verbose_name = 'Macroprocesso'
        verbose_name_plural = 'Macroprocessos'

    def pode_editar_projeto(self, usuario=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(in_group(usuario, 'Administrador de Planejamento Estratégico') and not self.projetoplanoatividade_set.all().exists())

    def pode_excluir_projeto(self, usuario=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(in_group(usuario, 'Administrador de Planejamento Estratégico') and not self.projetoplanoatividade_set.all().exists())

    def save(self, *args, **kwargs):
        self.macroprocesso = True
        self.codigo = self.unidade_gestora.codigo_macroprocesso
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo}-{self.nome}'

    def get_valor_total_etapas(self):
        total = Decimal('0')
        if self.etapaprojeto_set.all().exists():
            for etapa in EtapaProjeto.objects.filter(projeto=self):
                total += etapa.valor_etapa
        return total

    def get_saldo_projeto(self):
        return self.recurso_total - self.get_valor_total_etapas()


class PlanoInterno(ModelPlus):
    SEARCH_FIELDS = ['codigo', 'descricao']
    codigo = models.CharField(verbose_name='Código', max_length=11, null=True)
    pdi = models.ForeignKey(PDI, verbose_name='PDI', on_delete=models.CASCADE)
    projeto_estrategico = models.ForeignKeyPlus(ProjetoEstrategico, verbose_name='Macroprocesso', on_delete=models.CASCADE)
    acao = models.ForeignKeyPlus('financeiro.Acao', verbose_name='Ação Orçamentária', on_delete=models.CASCADE)
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, verbose_name='PTRES', null=True)
    categoria_apropriacao = models.ForeignKeyPlus(CategoriaApropriacao, verbose_name='Categoria de Apropriação', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=100, verbose_name='Descrição')
    gnd = models.ForeignKeyPlus('financeiro.GrupoNaturezaDespesa', verbose_name='Grupo Elemento de Despesa', on_delete=models.CASCADE)
    codigo_origemrecurso = models.CharField(verbose_name='Código', max_length=16, null=True)

    class Meta:
        verbose_name = 'Plano Interno'
        verbose_name_plural = 'Planos Internos'

    def pode_excluir(self, usuario=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(in_group(usuario, 'Administrador de Planejamento Estratégico') and not self.planointernoplanoatividade_set.all().exists())


class EtapaProjeto(ModelPlus):
    codigo = models.IntegerField(verbose_name='Código', null=True)
    projeto = models.ForeignKey(ProjetoEstrategico, verbose_name='Macroprocesso', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=100, verbose_name='Descrição')
    data_inicio = models.DateField(verbose_name='Data inicial', null=True)
    data_fim = models.DateField(verbose_name='Data final', null=True)
    objetivo_etapa = models.CharField(max_length=100, verbose_name='Objetivo', null=True)
    responsaveis_etapa = models.CharField(max_length=100, verbose_name='Setores responsáveis', null=True)
    meta_etapa = models.CharField(max_length=50, verbose_name='Meta da etapa', null=True)
    unidade_medida = models.CharField(max_length=50, verbose_name='Unidade de medida', null=True)
    valor_etapa = models.DecimalFieldPlus('Valor', null=True)

    class Meta:
        verbose_name = 'Componente funcional'
        verbose_name_plural = 'Componentes funcionais'

    def __str__(self):
        return f'{self.descricao}'

    def pode_editar_etapa(self, usuario=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(in_group(usuario, 'Administrador de Planejamento Estratégico') and not self.etapaprojetoplanoatividade_set.all().exists())

    def pode_excluir_etapa(self, usuario=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(in_group(usuario, 'Administrador de Planejamento Estratégico') and not self.etapaprojetoplanoatividade_set.all().exists())


def get_siglas_formula(forma_calculo):
    """Extrai as siglas das variáveis citadas na fórmula de cálculo de um indicador.

    Descarta operadores, parênteses e constantes numéricas (inteiras ou decimais),
    preservando a ordem de aparição e sem repetir siglas.
    """
    siglas = []
    for token in re.split(r'[()*/+-]', (forma_calculo or '').replace(' ', '')):
        if token and not token.replace('.', '', 1).isdigit() and token not in siglas:
            siglas.append(token)
    return siglas


class Indicador(ModelPlus):
    DECIMAL_0 = 0
    DECIMAL_1 = 1
    DECIMAL_2 = 2
    DECIMAL_3 = 3
    DECIMAL_4 = 4

    DECIMAL_CHOICES = ((DECIMAL_0, DECIMAL_0), (DECIMAL_1, DECIMAL_1), (DECIMAL_2, DECIMAL_2), (DECIMAL_3, DECIMAL_3), (DECIMAL_4, DECIMAL_4))

    DIRECAO_ALTA = 'Quanto mais melhor'
    DIRECAO_BAIXA = 'Quanto menos melhor'
    DIRECAO_CHOICES = ((DIRECAO_ALTA, DIRECAO_ALTA), (DIRECAO_BAIXA, DIRECAO_BAIXA))

    TIPO_PERCENTUAL = 'Percentual'
    TIPO_ABSOLUTO = 'Absoluto'
    TIPO_VALOR = ((TIPO_PERCENTUAL, TIPO_PERCENTUAL), (TIPO_ABSOLUTO, TIPO_ABSOLUTO))

    sigla = models.CharFieldPlus('Sigla')
    descricao = models.CharFieldPlus('Descrição')
    finalidade = models.TextField('Finalidade', blank=True)
    forma_calculo = models.CharField('Forma de Cálculo', max_length=100)
    casas_decimais = models.PositiveIntegerField('Casas decimais', choices=DECIMAL_CHOICES, default=DECIMAL_0)
    tendencia = models.CharField('Tendência', max_length=20, choices=DIRECAO_CHOICES, default=DIRECAO_ALTA)
    tipo = models.CharFieldPlus('Tipo de Exibição', choices=TIPO_VALOR, default=TIPO_ABSOLUTO)
    calcular_media = models.BooleanField(
        'Calcular Média',
        default=False,
        help_text='Ao marcar esta opção, o valor Hoje exibido para o valor da instituição será consolidado pela média dos resultados das unidades, excluindo-se zeros.',
    )
    indicador_acompanhamento = models.BooleanField(
        'Indicador de acompanhamento', default=False, help_text='Ao marcar esta opção, não haverá comparação Hoje X Meta, nem cor no farol.'
    )
    sem_escalonamento_trimestral = models.BooleanField(
        'Sem Escalonamento Trimestral', default=False, help_text='Ao marcar esta opção, a meta trimestral fica igual à meta anual.'
    )
    nivel_rede = models.BooleanField(
        'É indicador de Rede?', default=False, help_text='Ao marcar esta opção, o indicador será classificado como um indicador de rede da SETEC.'
    )

    class Meta:
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'

    def __str__(self):
        return f'{self.descricao}'

    def clean(self):
        """Valida a fórmula do indicador quando a consolidação por média está marcada.

        A média institucional é aplicada variável a variável (cada somatório é dividido
        pela quantidade de campi com valor), o que só corresponde à média dos campi
        quando a fórmula depende de uma única variável.
        """
        if self.calcular_media and len(get_siglas_formula(self.forma_calculo)) != 1:
            raise ValidationError({'calcular_media': ['A média só pode ser aplicada quando se trabalha com apenas uma variável.']})

        return super().clean()

    def get_variaveis(self):
        """Retorna as variáveis citadas na fórmula de cálculo do indicador.

        Mantém o contrato "tudo ou nada": se alguma sigla da fórmula não estiver
        cadastrada, a fórmula não é valorável e nenhuma variável é retornada.
        """
        variaveis = []
        for sigla in get_siglas_formula(self.forma_calculo):
            try:
                variaveis.append(Variavel.objects.get(sigla=sigla))
            except Variavel.DoesNotExist:
                return []
        return variaveis

    def verificar_variavel_real_vazia(self, uo=None, ano_base=None):
        variaveis = self.get_variaveis()
        if variaveis:
            if uo:
                return VariavelCampus.objects.filter(uo=uo.id, variavel__in=self.get_variaveis(), ano=ano_base, valor_real__isnull=True).exists()
            else:
                return VariavelCampus.objects.filter(variavel__in=self.get_variaveis(), ano=ano_base, valor_real__isnull=True).exists()
        else:
            return True

    def get_formula_valor(self, uo=None, ano_base=None):
        index = None
        if uo:
            uo = get_object_or_404(UnidadeOrganizacional, pk=uo.id)
            index = uo.sigla

        if hasattr(self, 'formula_valorada'):
            if index in self.formula_valorada:
                return self.formula_valorada[index]
        else:
            self.formula_valorada = {}
        formula = ' {} '.format(
            self.forma_calculo.replace(' ', '')
            .replace(')', ' ) ')
            .replace('(', ' ( ')
            .replace('*', ' * ')
            .replace('/', ' / ')
            .replace('+', ' + ')
            .replace('-', ' - ')
        )
        for variavel in self.get_variaveis():
            # O ajuste '{}.0' garante que as divisões internas não serão truncadas.
            # Ex: Com o referido ajuste, a fórmula '(  (1053+187)  * 1 )  +  (  (33+39)  / 2 )  +  (23/ 4 )  ) tem
            # como valor final 1281.75, já sem esse ajuste seria exibido 1281.
            somatorio_variavel = variavel.get_valor(uo=uo, ano_base=ano_base)
            if self.calcular_media and not uo:
                qtd_variaveis_com_valor = VariavelCampus.objects.filter(variavel=variavel, ano=ano_base, valor_real__gt=0).count()
                if qtd_variaveis_com_valor:
                    somatorio_variavel = somatorio_variavel / qtd_variaveis_com_valor
                else:
                    somatorio_variavel = 0

            formula = formula.replace(f' {variavel.sigla} ', f' {somatorio_variavel}')

        try:
            self.formula_valorada[index] = eval_expr(formula.strip())
        except Exception:
            return 0

        try:
            return round(self.formula_valorada[index], self.casas_decimais)
        except Exception:
            return 0

    get_formula_valor.short_description = 'Fórmula Valorada'

    def get_formula_valor_meta(self, uo=None, ano_base=None, force=True):
        index = None
        if uo:
            uo = get_object_or_404(UnidadeOrganizacional, pk=uo.id)
            index = uo.sigla

        if hasattr(self, 'formula_valorada_meta'):
            if index in self.formula_valorada_meta and not force:
                return self.formula_valorada_meta[index]
        else:
            self.formula_valorada_meta = {}
        formula = ' {} '.format(
            self.forma_calculo.replace(' ', '')
            .replace(')', ' ) ')
            .replace('(', ' ( ')
            .replace('*', ' * ')
            .replace('/', ' / ')
            .replace('+', ' + ')
            .replace('-', ' - ')
        )

        for variavel in self.get_variaveis():
            # O ajuste '{}.0' garante que as divisões internas não serão truncadas.
            # Ex: Com o referido ajuste, a fórmula '(  (1053+187)  * 1 )  +  (  (33+39)  / 2 )  +  (23/ 4 )  ) tem
            # como valor final 1281.75, já sem esse ajuste seria exibido 1281.
            somatorio_variavel = variavel.get_valor_meta_variavel(uo=uo, ano_base=ano_base)
            if self.calcular_media and not uo:
                qtd_variaveis_com_valor = VariavelCampus.objects.filter(variavel=variavel, ano=ano_base, valor_ideal__gt=0).count()
                if qtd_variaveis_com_valor:
                    somatorio_variavel = somatorio_variavel / qtd_variaveis_com_valor
                else:
                    somatorio_variavel = 0

            formula = formula.replace(f' {variavel.sigla} ', f' {somatorio_variavel}')

        try:
            self.formula_valorada_meta[index] = eval_expr(formula.strip())
        except Exception:
            return 0.0

        try:
            return round(self.formula_valorada_meta[index], self.casas_decimais)

        except Exception:
            return 0.0

    get_formula_valor.short_description = 'Fórmula Valorada Meta'


class PDIIndicador(ModelPlus):
    TIPO_PERCENTUAL = 'Percentual'
    TIPO_INTEIRO = 'Inteiro'
    TIPO_DECIMAL = 'Decimal'

    TIPO_VALOR = ((TIPO_PERCENTUAL, TIPO_PERCENTUAL), (TIPO_INTEIRO, TIPO_INTEIRO), (TIPO_DECIMAL, TIPO_DECIMAL))

    pdi = models.ForeignKey('PDI', on_delete=models.CASCADE)
    indicador = models.ForeignKey('Indicador', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus('Tipo', choices=TIPO_VALOR, default=TIPO_PERCENTUAL)
    valor_referencia = models.DecimalFieldPlus('Valor Referência', decimal_places=4, null=True)

    objetivos = models.ManyToManyField('PDIObjetivoEstrategico')

    class Meta:
        verbose_name = 'Indicador no PDI'
        verbose_name_plural = 'Indicadores no PDI'
        unique_together = ('pdi', 'indicador')

    def __str__(self):
        return f'{self.indicador.sigla} - {self.indicador.descricao}'

    def save(self, *args, **kwargs):
        edit_indicador = self.pk
        super().save(*args, **kwargs)

        data_inicial = self.pdi.ano_inicial_pdi.ano
        data_final = self.pdi.ano_final_pdi.ano

        if not edit_indicador:
            while data_inicial <= data_final:
                meta = MetaIndicador()
                meta.indicador = self
                meta.ano = data_inicial
                meta.save()
                data_inicial += 1

    @property
    def casas_decimais(self):
        return self.indicador.casas_decimais

    def get_valor_referencia(self):
        return defaultfilters.floatformat(self.valor_referencia, self.casas_decimais)

    def verificar_variavel_real_vazia(self, uo=None, ano_base=None):
        variaveis = self.indicador.get_variaveis()
        if variaveis:
            if uo:
                if not VariavelCampus.objects.filter(uo=uo.id, variavel__in=self.indicador.get_variaveis(), ano=ano_base).exists():
                    return True
                return VariavelCampus.objects.filter(
                    uo=uo.id, variavel__in=self.indicador.get_variaveis(), ano=ano_base, valor_real__isnull=True
                ).exists()
            else:
                return VariavelCampus.objects.filter(variavel__in=self.indicador.get_variaveis(), ano=ano_base, valor_real__isnull=True).exists()
        else:
            return True

    def verificar_variavel_ideal_vazia(self, uo=None, ano_base=None):
        variaveis = self.indicador.get_variaveis()
        if variaveis:
            if uo:
                if not VariavelCampus.objects.filter(uo=uo.id, variavel__in=self.indicador.get_variaveis(), ano=ano_base).exists():
                    return True
                return VariavelCampus.objects.filter(
                    uo=uo.id, variavel__in=self.indicador.get_variaveis(), ano=ano_base, valor_ideal__isnull=True
                ).exists()
            else:
                return VariavelCampus.objects.filter(variavel__in=self.indicador.get_variaveis(), ano=ano_base, valor_ideal__isnull=True).exists()
        else:
            return True

    def verificar_variavel_vazia(self, uo=None, ano_base=None):
        return self.verificar_variavel_real_vazia(uo, ano_base) or self.verificar_variavel_ideal_vazia(uo, ano_base)

    def get_metaindicador_valor(self, uo=None, ano_base=None):
        variavel_ideal = 0
        for variavel in self.indicador.get_variaveis():
            if uo:
                if VariavelCampus.objects.filter(uo=uo.id, variavel=variavel, ano=ano_base).exists():
                    var_ideal = VariavelCampus.objects.filter(uo=uo.id, variavel=variavel, ano=ano_base)
                    variavel_ideal += var_ideal[0].valor_ideal
            else:
                var_ideal = VariavelCampus.objects.filter(variavel=variavel, ano=ano_base).aggregate(total=Sum('valor_ideal'))
                variavel_ideal += var_ideal['total'] or 0
        return variavel_ideal

    def get_porcentagem_alcancada(self, uo=None, ano_base=None, valor_real=None):
        trimestre_atual = int((date.today().month - 1) / 3 + 1)
        valor_meta = self.indicador.get_formula_valor_meta(uo, ano_base)
        if not valor_real:
            valor_real = self.indicador.get_formula_valor(uo, ano_base)

        if ano_base and int(ano_base) == date.today().year:
            if self.indicador.tendencia == Indicador.DIRECAO_ALTA and not self.indicador.sem_escalonamento_trimestral:
                if trimestre_atual == 1:
                    valor_meta = valor_meta / 4
                else:
                    valor_meta = (valor_meta / 4.0) * (trimestre_atual - 1)

        if not (valor_real == 0 or valor_meta == 0):
            porcentagem = float(valor_real * 100) / float(valor_meta * 100) * 100
            if self.indicador.tendencia == Indicador.DIRECAO_BAIXA:
                porcentagem = (float(valor_meta) * 100 / float(valor_real * 100)) * 100
            return porcentagem
        else:
            if (valor_meta == 0 and self.indicador.tendencia == Indicador.DIRECAO_ALTA) or (
                valor_real == 0 and self.indicador.tendencia == Indicador.DIRECAO_BAIXA
            ):
                return 100
            else:
                return 0

    def get_status_farol(self, uo=None, ano_base=None, valor_real=None):
        if not self.indicador.indicador_acompanhamento:
            if not self.verificar_variavel_vazia(uo, ano_base):
                valor_meta = self.indicador.valor_meta
                if not valor_real:
                    valor_real = self.indicador.valor_real
                if not (valor_real == 0 and valor_meta == 0):
                    porcentagem = self.get_porcentagem_alcancada(uo, ano_base, valor_real)
                    if self.pdi.valor_faixa_verde <= porcentagem:
                        return 'Alcançado'
                    elif self.pdi.valor_faixa_amarela <= porcentagem < self.pdi.valor_faixa_verde:
                        return 'Parcialmente'
                    elif self.pdi.valor_faixa_vermelha <= porcentagem < self.pdi.valor_faixa_amarela:
                        return 'Não Alcançado'
                else:
                    return 'Não se Aplica'
            else:
                return 'Não informado'
        else:
            return 'Indicador de Acompanhamento'


class TematicaVariavel(ModelPlus):
    nome = models.CharFieldPlus('Nome da Temática', unique=True)

    class Meta:
        verbose_name = 'Temática da variável'
        verbose_name_plural = 'Temáticas das variáveis'

        ordering = ('nome',)

    def __str__(self) -> str:
        return self.nome


class Variavel(models.ModelPlus):
    sigla = models.CharField(max_length=50, help_text='A sigla é utilizada na fórmula dos indicadores', unique=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField('Descrição', max_length=1000)
    fonte = models.CharField(max_length=255, help_text='Origem do dado')
    tematica = models.ForeignKeyPlus('TematicaVariavel', verbose_name='Temática', null=True, blank=True)
    nivel_rede = models.BooleanField(
        'É variável de rede?', default=False, help_text='Ao marcar esta opção, a variável será classificada como uma variável de rede da SETEC.'
    )

    class Meta:
        verbose_name = 'Variável'
        verbose_name_plural = 'Variáveis'
        ordering = ('sigla',)

    def __str__(self) -> str:
        return f'{self.sigla} - {self.nome}'

    def get_absolute_url(self):
        return f'/plan_estrategico/variavel/{self.id}/visualizar/'

    def get_valor(self, uo=None, ano_base=None):
        if uo and VariavelCampus.objects.filter(uo=uo.id, variavel=self, ano=ano_base).exists():
            variavelcampus = VariavelCampus.objects.filter(uo=uo.id, variavel=self, ano=ano_base)
            return variavelcampus[0].valor_real
        else:
            variavelcampus = VariavelCampus.objects.filter(variavel=self, ano=ano_base).aggregate(total=Sum('valor_real'))
            return variavelcampus['total']

    def get_valor_meta_variavel(self, uo=None, ano_base=None):
        if uo and VariavelCampus.objects.filter(uo=uo.id, variavel=self, ano=ano_base).exists():
            variavelcampus = VariavelCampus.objects.filter(uo=uo.id, variavel=self, ano=ano_base)
            return variavelcampus[0].valor_ideal
        else:
            variavelcampus = VariavelCampus.objects.filter(variavel=self, ano=ano_base).aggregate(total=Sum('valor_ideal'))
            return variavelcampus['total']

    def get_indicadores_variavel(self):
        """Retorna os indicadores cuja fórmula de cálculo cita esta variável."""
        return [indicador for indicador in Indicador.objects.all() if self.sigla in get_siglas_formula(indicador.forma_calculo)]

    def save(self, *args, **kwargs):
        edit_variavel = self.pk
        super().save(*args, **kwargs)
        pdi = PDI.objects.all()[0]
        data_inicial = pdi.ano_inicial_pdi.ano
        data_final = pdi.ano_final_pdi.ano
        if not edit_variavel:
            while data_inicial <= data_final:
                for uo in UnidadeOrganizacional.objects.uo().all():
                    if not VariavelCampus.objects.filter(uo=uo, variavel=self, ano=data_inicial).exists():
                        VariavelCampus.objects.create(variavel=self, uo=uo, ano=data_inicial)
                data_inicial += 1


class VariavelCampus(models.ModelPlus):
    ATIVA = 1
    NAO_SE_APLICA = 2

    SITUACAO_CHOICES = (
        (ATIVA, 'Ativa'),
        (NAO_SE_APLICA, 'Não se aplica'),
    )

    variavel = models.ForeignKeyPlus('Variavel', verbose_name='Variável')
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Unidade administrativa')
    valor_ideal = models.DecimalField('Valor meta', max_digits=15, decimal_places=4, null=True)
    valor_real = models.DecimalField('Valor real', max_digits=15, decimal_places=4, null=True)
    valor_trimestral = models.DecimalField('Valor acumulado', max_digits=15, decimal_places=4, null=True)
    ano = models.PositiveIntegerField('Ano')
    data_atualizacao = models.DateTimeFieldPlus(null=True, verbose_name='Data da importação')
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_CHOICES, default=ATIVA)

    class Meta:
        verbose_name = 'Variável campus/ano'
        verbose_name_plural = 'Variáveis campus/ano'
        ordering = ('variavel__sigla',)

    def __str__(self) -> str:
        return f'{self.variavel}: {self.uo}'

    def get_absolute_url(self):
        return f'/plan_estrategico/variavel/{self.variavel.id}/visualizar/'

    def get_valor(self, uo=None, ano_base=None):
        uo = get_object_or_404(UnidadeOrganizacional, pk=uo)
        try:
            return VariavelCampus.objects.filter(uo=uo, ano=ano_base)[0]
        except Exception:
            return Decimal('0')

    get_valor.short_description = 'Valor'


class PeriodoPreenchimentoVariavel(models.ModelPlus):
    choices_trimestres = ((1, '1º Trimestre'), (2, '2º Trimestre'), (3, '3º Trimestre'), (4, '4º Trimestre'))
    pdi = models.ForeignKey('PDI', verbose_name='PDI', on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano do Período')
    trimestre = models.PositiveIntegerField('Trimestre', choices=choices_trimestres)
    data_inicio = models.DateTimeFieldPlus('Data de Início')
    data_termino = models.DateTimeFieldPlus('Data de Término')

    class Meta:
        verbose_name = 'Período de preenchimento de variável'
        verbose_name_plural = 'Períodos de preenchimento de variáveis'
        unique_together = ('pdi', 'ano', 'trimestre')

    @classmethod
    def get_em_periodo_de_preenchimento(cls):
        agora = datetime.now()
        return cls.objects.filter(data_inicio__lte=agora, data_termino__gte=agora)


class IndicadorTrimestralCampus(models.ModelPlus):
    choices_trimestres = ((1, '1º Trimestre'), (2, '2º Trimestre'), (3, '3º Trimestre'), (4, '4º Trimestre'))
    indicador = models.ForeignKey('PDIIndicador', verbose_name='Indicador', on_delete=models.CASCADE)
    ano = models.PositiveIntegerField('Ano')
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Unidade administrativa', null=True)
    valor = models.DecimalField('Valor', max_digits=15, decimal_places=4, null=True)
    trimestre = models.PositiveIntegerField('Trimestre', choices=choices_trimestres)

    class Meta:
        verbose_name = 'Valor Trimestral do Indicador'
        verbose_name_plural = 'Valores Trimestrais do Indicador'
        unique_together = ('indicador', 'ano', 'uo', 'trimestre')


class MetaIndicador(ModelPlus):
    indicador = models.ForeignKey('PDIIndicador', verbose_name='Indicador', on_delete=models.CASCADE)
    ano = models.PositiveIntegerField('Ano')
    meta = models.DecimalFieldPlus('Meta do Ano', null=True, decimal_places=4)

    class Meta:
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'
        ordering = ['ano']

    def __str__(self):
        return f'{self.meta}'

    @property
    def casas_decimais(self):
        return self.indicador.casas_decimais

    def get_valor_meta(self):
        if self.meta:
            return Decimal(self.meta, self.casas_decimais)
        else:
            return 0


class ObjetivoIndicador(ModelPlus):
    indicador = models.ForeignKey('PDIIndicador', verbose_name='Indicador', on_delete=models.CASCADE)
    objetivo_estrategico = models.ForeignKey('PDIObjetivoEstrategico', verbose_name='Objetivo Estratégico', on_delete=models.CASCADE)
    relevancia = models.PositiveIntegerField('Relevância', default=0)

    class Meta:
        verbose_name = 'Relevância'
        verbose_name_plural = 'Relevâncias'

    def __str__(self):
        return f'{self.objetivo_estrategico}'


def atualizar_metas(self):
    pdi = PDI.objects.latest('id')
    pdi_inicial = pdi.ano_inicial_pdi.ano
    indicadores = PDIIndicador.objects.filter(pdi=pdi)
    while pdi_inicial <= pdi.ano_final_pdi.ano:
        for pdi_indicador in indicadores:
            meta = MetaIndicador.objects.get_or_create(indicador=pdi_indicador, ano=pdi_inicial)[0]
            meta.meta = pdi_indicador.indicador.get_formula_valor_meta(uo=None, ano_base=pdi_inicial, force=True)
            meta.save()
        pdi_inicial += 1


COLUNA_SIGLA_VARIAVEL = 0
COLUNA_NOME_VARIAVEL = 1
COLUNA_SIGLA_CAMPUS = 2
COLUNA_FONTE = 3
PRIMEIRA_COLUNA_META = 4
MAX_DIGITOS_META = 15
CASAS_DECIMAIS_META = 4
LIMITE_META = Decimal(10) ** (MAX_DIGITOS_META - CASAS_DECIMAIS_META)
MAX_ERROS_RELATADOS = 10


def ler_planilha_metas(arquivo):
    import pandas as pd

    return pd.read_excel(arquivo, header=None).fillna('')


def get_valor_celula(row, numero_celula: int):
    if numero_celula >= len(row):
        return ''
    return row.iloc[numero_celula]


def get_texto_celula(row, numero_celula: int) -> str:
    return str(get_valor_celula(row, numero_celula)).strip()


def normalizar_numero(texto: str) -> str:
    texto = texto.strip().replace(' ', '').replace('\xa0', '')
    if ',' in texto and '.' in texto:
        if texto.rfind(',') > texto.rfind('.'):
            return texto.replace('.', '').replace(',', '.')
        return texto.replace(',', '')
    return texto.replace(',', '.')


def converter_decimal_meta(valor) -> Decimal:
    try:
        numero = Decimal(normalizar_numero(str(valor)))
    except InvalidOperation:
        raise ValueError(f'"{valor}" não é um número')
    if not numero.is_finite():
        raise ValueError(f'"{valor}" não é um número')
    if abs(numero) >= LIMITE_META:
        raise ValueError(f'"{valor}" excede o limite de {MAX_DIGITOS_META - CASAS_DECIMAIS_META} dígitos inteiros')
    return numero


def get_decimal_celula(row, numero_celula: int) -> Decimal | None:
    valor = get_valor_celula(row, numero_celula)
    if valor == '':
        return None
    return converter_decimal_meta(valor)


def get_linhas_planilha_metas(df):
    for indice, row in df.iloc[1:].iterrows():
        if get_texto_celula(row, COLUNA_SIGLA_VARIAVEL):
            yield indice + 1, row


def get_campus_desconhecidos(df) -> dict:
    siglas_validas = set(UnidadeOrganizacional.objects.suap().values_list('sigla', flat=True))
    desconhecidos: dict = {}
    for numero_linha, row in get_linhas_planilha_metas(df):
        sigla_campus = get_texto_celula(row, COLUNA_SIGLA_CAMPUS)
        if sigla_campus not in siglas_validas:
            desconhecidos.setdefault(sigla_campus, []).append(numero_linha)
    return desconhecidos


def get_erros_metas(df, anos) -> list:
    erros = []
    total = 0
    for numero_linha, row in get_linhas_planilha_metas(df):
        for indice_ano, ano in enumerate(anos):
            valor = get_valor_celula(row, PRIMEIRA_COLUNA_META + indice_ano)
            if valor == '':
                continue
            try:
                converter_decimal_meta(valor)
            except ValueError as e:
                total += 1
                if len(erros) < MAX_ERROS_RELATADOS:
                    erros.append(f'Linha {numero_linha}, meta de {ano}: {e}.')
    if total > len(erros):
        erros.append(f'... e mais {total - len(erros)} meta(s) com valor inválido.')
    return erros


def validar_planilha_metas(df) -> None:
    pdi = PDI.objects.latest('id')
    anos = range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1)
    erros = []
    colunas_necessarias = PRIMEIRA_COLUNA_META + len(anos)
    if len(df.columns) < colunas_necessarias:
        erros.append(
            f'A planilha tem {len(df.columns)} coluna(s), mas são necessárias ao menos {colunas_necessarias}: '
            f'uma coluna de meta para cada ano do PDI ({anos.start} a {anos.stop - 1}), a partir da coluna {PRIMEIRA_COLUNA_META + 1}.'
        )
    for sigla_campus, linhas in get_campus_desconhecidos(df).items():
        identificacao = f'"{sigla_campus}"' if sigla_campus else 'em branco'
        erros.append(f'Campus {identificacao} não encontrado no SUAP: {len(linhas)} linha(s) da planilha, a partir da linha {linhas[0]}.')
    if len(df.columns) >= colunas_necessarias:
        erros.extend(get_erros_metas(df, anos))
    if erros:
        raise ValidationError(erros)


def importar_linha_meta(row, pdi) -> None:
    sigla = get_texto_celula(row, COLUNA_SIGLA_VARIAVEL)
    nome_variavel = get_texto_celula(row, COLUNA_NOME_VARIAVEL)
    variavel, _ = Variavel.objects.get_or_create(
        sigla=sigla, defaults={'nome': nome_variavel, 'descricao': nome_variavel, 'fonte': get_texto_celula(row, COLUNA_FONTE)}
    )
    campus = UnidadeOrganizacional.objects.suap().get(sigla=get_texto_celula(row, COLUNA_SIGLA_CAMPUS))
    for indice_ano, ano in enumerate(range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1)):
        variavel_campus, _ = VariavelCampus.objects.get_or_create(variavel=variavel, uo=campus, ano=ano)
        variavel_campus.valor_ideal = get_decimal_celula(row, PRIMEIRA_COLUNA_META + indice_ano)
        variavel_campus.save()


def get_planilha_metas_do_storage(instancia):
    local_filename = cache_file(instancia.arquivo.name)
    if not local_filename:
        raise ValidationError(f'Não foi possível recuperar o arquivo "{instancia.arquivo.name}" para importação.')
    try:
        return ler_planilha_metas(local_filename)
    finally:
        os.unlink(local_filename)


def importar_metas(self) -> None:
    df = getattr(self, 'planilha_metas_validada', None)
    if df is None:
        df = get_planilha_metas_do_storage(self)
    validar_planilha_metas(df)
    pdi = PDI.objects.latest('id')
    with transaction.atomic():
        for _numero_linha, row in get_linhas_planilha_metas(df):
            importar_linha_meta(row, pdi)
        atualizar_metas(self)


class ArquivoMeta(ModelPlus):
    data_importacao = models.DateTimeFieldPlus(null=True, auto_now_add=True, verbose_name='Data da importação')
    arquivo = models.FileFieldPlus('Arquivo', upload_to='plan_estrategico/arquivometa', max_length=255)
    usuario = models.CurrentUserField(verbose_name='Usuário')

    class Meta:
        verbose_name = 'Arquivo de Metas'
        verbose_name_plural = 'Arquivo de Metas'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        importar_metas(self)


class TotalizadorIndicador(ModelPlus):
    INDICADOR_ALCANCADO = 'Indicador Alcançado'
    INDICADOR_PARCIALMENTE_ALCANCADO = 'Indicador Parcialmente Alcançado'
    INDICADOR_NAO_ALCANCADO = 'Indicador Não Alcançado'

    TIPO_STATUS = (
        (INDICADOR_ALCANCADO, INDICADOR_ALCANCADO),
        (INDICADOR_PARCIALMENTE_ALCANCADO, INDICADOR_PARCIALMENTE_ALCANCADO),
        (INDICADOR_NAO_ALCANCADO, INDICADOR_NAO_ALCANCADO),
    )

    ano = models.PositiveIntegerField('Ano')
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Unidade administrativa', null=True)
    total_indicadores = models.PositiveIntegerField('Total campus', null=True)
    status = models.CharFieldPlus('Status', choices=TIPO_STATUS)


class VariavelTrimestralCampus(models.ModelPlus):
    choices_trimestres = ((1, '1º Trimestre'), (2, '2º Trimestre'), (3, '3º Trimestre'), (4, '4º Trimestre'))
    variavel = models.ForeignKey(VariavelCampus, verbose_name='Variável campus', on_delete=models.CASCADE)
    ano = models.PositiveIntegerField('Ano')
    valor = models.DecimalField('Valor', max_digits=15, decimal_places=4, null=True)
    trimestre = models.PositiveIntegerField('Trimestre', choices=choices_trimestres)

    class Meta:
        verbose_name = 'Valor Trimestral da Variável Campus'
        verbose_name_plural = 'Valores Trimestrais das Variáveis Campus'


# Modelos do Plano de Atividade ----------------------------------------------------------------------------------------


class PlanoAtividade(ModelPlus):
    pdi = models.ForeignKeyPlus('plan_estrategico.PDI', on_delete=models.CASCADE)
    ano_base = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Base')

    projetos = models.ManyToManyField(ProjetoEstrategico, through='ProjetoPlanoAtividade')

    # vigência do plano de atividade
    data_geral_inicial = models.DateFieldPlus('Início da Vigência')
    data_geral_final = models.DateFieldPlus('Fim da Vigência')

    # data para adição de dados orcamentários
    data_orcamentario_preloa_inicial = models.DateFieldPlus('Início do Cadastro Orçamentário Pré-LOA')
    data_orcamentario_preloa_final = models.DateFieldPlus('Fim do Cadastro Orçamentário Pré-LOA')

    # data para importação de projetos estratégicos do PDI
    data_projetos_preloa_inicial = models.DateFieldPlus('Início do Cadastro de Macroprocessos Pré-LOA')
    data_projetos_preloa_final = models.DateFieldPlus('Fim do Cadastro de Macroprocessos Pré-LOA')

    # data para adição de atividades pela UA
    data_atividades_preloa_inicial = models.DateFieldPlus('Início do Cadastro de Atividades Pré-LOA')
    data_atividades_preloa_final = models.DateFieldPlus('Fim do Cadastro de Atividades Pré-LOA')

    # data pada adicao de valores orçamentários
    data_orcamentario_posloa_inicial = models.DateFieldPlus('Início do Cadastro Orçamentário Pós-LOA')
    data_orcamentario_posloa_final = models.DateFieldPlus('Fim do Cadastro Orçamentário Pós-LOA')

    # data para gerenciar recursos nos projetos
    data_projetos_posloa_inicial = models.DateFieldPlus('Início do Cadastro de Macroprocessos Pós-LOA')
    data_projetos_posloa_final = models.DateFieldPlus('Fim do Cadastro de Macroprocessos Pós-LOA')

    # data para gerenciar recursos das etapas/atividades
    data_atividades_posloa_inicial = models.DateFieldPlus('Início do Cadastro de Atividades Pós-LOA')
    data_atividades_posloa_final = models.DateFieldPlus('Fim do Cadastro de Atividades Pós-LOA')

    percentual_reserva_tecnica = models.IntegerField(verbose_name='Percentual da Reserva Técnica', null=True)

    class Meta:
        verbose_name = 'Plano de Atividade'
        verbose_name_plural = 'Planos de Atividades'

        ordering = ('ano_base',)
        unique_together = ('pdi', 'ano_base')

    def __str__(self):
        return str(self.ano_base)

    @property
    def em_periodo_orcamentario_preloa(self):
        hoje = date.today()
        return self.data_orcamentario_preloa_inicial <= hoje <= self.data_orcamentario_preloa_final

    @property
    def em_periodo_orcamentario_posloa(self):
        hoje = date.today()
        return self.data_orcamentario_posloa_inicial <= hoje <= self.data_orcamentario_posloa_final

    @property
    def em_periodo_projeto_preloa(self):
        hoje = date.today()
        return self.data_projetos_preloa_inicial <= hoje <= self.data_projetos_preloa_final

    @property
    def em_periodo_projeto_posloa(self):
        hoje = date.today()
        return self.data_projetos_posloa_inicial <= hoje <= self.data_projetos_posloa_final

    @property
    def em_periodo_atividades_posloa(self):
        hoje = date.today()
        return self.data_atividades_posloa_inicial <= hoje <= self.data_atividades_posloa_final

    @property
    def plano_concluido(self):
        hoje = date.today()
        usuario = tl.get_user()
        return usuario.groups.filter(
            name__in=[
                'Gestor de Projeto',
                'Gestor de UA',
                'Coordenador de UA',
                'Gestor Orçamentário Sistêmico',
                'Administrador de Planejamento Estratégico',
            ]
        ).exists() and (hoje > self.data_atividades_posloa_final)

    # Se pode incluir plano de atividade é um administrador de projeto estratégico
    def pode_incluir(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.add_planoatividade'))

    @property
    def em_periodo_atividade_preloa(self):
        hoje = date.today()
        return self.data_atividades_preloa_inicial <= hoje <= self.data_atividades_preloa_final

    @property
    def em_periodo_vigencia(self):
        hoje = date.today()
        return self.data_geral_inicial <= hoje <= self.data_geral_final

    @property
    def concluido(self):
        hoje = date.today()
        return hoje > self.data_atividades_posloa_final


class OrigemRecurso(ModelPlus):
    plano_atividade = models.ForeignKeyPlus('PlanoAtividade', on_delete=models.CASCADE)
    acao_financeira = models.ForeignKeyPlus(
        'financeiro.AcaoAno', verbose_name='Ação Orçamentária', related_name='origemrecurso_acaofinanceira', on_delete=models.CASCADE
    )
    gnd = models.ForeignKeyPlus('financeiro.GrupoNaturezaDespesa', verbose_name='Grupo Elemento de Despesa', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Origem do Recurso'
        verbose_name_plural = 'Origens dos Recursos'

        unique_together = ('acao_financeira', 'gnd')

    def __str__(self):
        return f'{self.acao_financeira.acao.codigo_acao}.{self.acao_financeira.ptres}.{self.gnd.codigo}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def get_codigo(self):
        return f'{self.acao_financeira.acao.codigo_acao}.{self.acao_financeira.ptres}.{self.gnd.codigo}'

    @classmethod
    def pode_incluir(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.add_origemrecurso') and plano_atividade.em_periodo_orcamentario_preloa)

    @classmethod
    def pode_alterar(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.change_origemrecurso') and plano_atividade.em_periodo_orcamentario_preloa)

    @classmethod
    def pode_excluir(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.delete_origemrecurso') and plano_atividade.em_periodo_orcamentario_preloa)

    @classmethod
    def pode_incluir_dados_orcamentarios(cls, usuario, plano_atividade):
        return bool(
            usuario.has_perm('plan_estrategico.add_origemrecurso')
            and (plano_atividade.em_periodo_orcamentario_preloa or plano_atividade.em_periodo_orcamentario_posloa)
        )

    def valor_total(self):
        if self.gnd.codigo == '4':
            return self.acao_financeira.valor_capital
        else:
            return self.acao_financeira.valor_custeio

    def valor_distribuido_projeto(self, plano_atividade, origem_recurso):
        origens_projeto = (
            OrigemRecursoProjeto.objects.filter(projeto_plano_atividade__plano_atividade=plano_atividade, origem_recurso=origem_recurso).aggregate(
                total_distribuido=Sum('valor')
            )
            or 0
        )
        return origens_projeto['total_distribuido'] or 0


class NaturezaDespesaPlanoAtividade(ModelPlus):
    SEARCH_FIELDS = ['natureza_despesa__codigo', 'natureza_despesa__nome']

    plano_atividade = models.ForeignKeyPlus('PlanoAtividade', verbose_name='Plano de Atividade')
    natureza_despesa = models.ForeignKeyPlus('financeiro.NaturezaDespesa', verbose_name='Natureza de Despesa')

    class Meta:
        verbose_name = 'Natureza de Despesa do Plano de Atividade'
        verbose_name_plural = 'Naturezas de Despesa do Plano de Atividade'

    def __str__(self):
        return f'{self.natureza_despesa.codigo} - {self.natureza_despesa.nome}'

    @classmethod
    def pode_gerenciar(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('financeiro.add_naturezadespesa') and plano_atividade.em_periodo_orcamentario_preloa)

    @classmethod
    def pode_excluir(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.delete_naturezadespesaplanoatividade') and plano_atividade.em_periodo_orcamentario_preloa)


class ProjetoPlanoAtividade(ModelPlus):
    SEARCH_FIELDS = ['projeto']
    etapas_projeto_plano_atividade = models.ManyToManyField(EtapaProjeto, through='EtapaProjetoPlanoAtividade')
    OrigensRecurso = models.ManyToManyField(OrigemRecurso, through='OrigemRecursoProjeto')
    projeto = models.ForeignKey('ProjetoEstrategico', verbose_name='Macroprocesso', on_delete=models.CASCADE)
    plano_atividade = models.ForeignKey('PlanoAtividade', verbose_name='Plano de Atividade', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Macroprocesso do plano de Atividade'
        verbose_name_plural = 'Macroprocessos do Plano de Atividade'

        unique_together = ('projeto', 'plano_atividade')

    def __str__(self):
        return f'{self.projeto}'

    @classmethod
    def pode_incluir(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.add_projetoplanoatividade') and plano_atividade.em_periodo_projeto_preloa)

    @classmethod
    def eh_administrador(cls, usuario):
        return bool(usuario.has_perm('plan_estrategico.add_pdi'))

    @classmethod
    def eh_gestor(cls, usuario):
        return bool(usuario.has_perm('plan_estrategico.add_projetoplanoatividade'))

    @classmethod
    def eh_coordenador(cls, usuario):
        return bool(usuario.has_perm('plan_estrategico.add_atividadeetapa'))

    def get_valor_total_origem_recurso(self):
        total = Decimal('0')
        for origem in self.origemrecursoprojeto_set.all():
            if origem.valor:
                total += origem.valor
        return total

    def get_valor_disponivel_origem_recurso(self):
        total = Decimal('0')
        for origem in self.origemrecursoprojeto_set.all():
            if origem.get_valor_distribuido():
                total += origem.get_valor_distribuido()
        return total

    def eh_dono(self, usuario=None):
        from plan_estrategico.utils import get_setor_unidade_gestora

        if not usuario:
            usuario = tl.get_user()
        return bool(
            ProjetoPlanoAtividade.objects.filter(pk=self.id, projeto__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=usuario))
        )

    def tem_atividade(self):
        return bool(AtividadeEtapa.objects.filter(etapa_projeto_plano_atividade__projeto_plano_atividade=self))


class OrigemRecursoProjeto(ModelPlus):
    SEARCH_FIELDS = ['projeto_plano_atividade__projeto__codigo', 'origem_recurso']

    valor = models.DecimalFieldPlus('Valor do Projeto', null=True)
    projeto_plano_atividade = models.ForeignKeyPlus(
        'ProjetoPlanoAtividade', verbose_name='Macroprocesso do plano de atividade', on_delete=models.CASCADE
    )
    origem_recurso = models.ForeignKeyPlus(
        'OrigemRecurso', verbose_name='Origem de recurso do macroprocesso do plano de atividade', on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = 'Origem de recurso do macroprocesso'
        verbose_name_plural = 'Origens de recursos do macroprocesso'

        unique_together = ('projeto_plano_atividade', 'origem_recurso')

    def __str__(self):
        return f'{self.projeto_plano_atividade.projeto.codigo}.{self.origem_recurso}'

    @classmethod
    def pode_incluir_valor(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.add_origemrecurso') and plano_atividade.em_periodo_orcamentario_posloa)

    @classmethod
    def pode_ratear_valor(cls, plano_atividade):
        return bool(plano_atividade.em_periodo_projeto_posloa)

    @classmethod
    def pode_ratear_valor_atividade(cls, usuario, plano_atividade):
        return bool(usuario.has_perm('plan_estrategico.view_atividadeetapa') and plano_atividade.em_periodo_atividades_posloa)

    @classmethod
    def valor_executado(self, plano_atividade):
        valor_executado = (
            OrigemRecursoProjeto.objects.filter(projeto_plano_atividade__plano_atividade=plano_atividade).aggregate(Sum('valor')).values()[0] or 0
        )
        return valor_executado

    def get_valor_distribuido(self):
        return OrigemRecursoProjetoEtapa.objects.filter(origem_recurso_projeto=self).aggregate(total=Sum('valor'))['total'] or 0

    def get_valor_rateado(self):
        return self.get_valor() == self.get_valor_distribuido()

    def get_valor(self):
        return self.valor or 0


class EtapaProjetoPlanoAtividade(ModelPlus):
    projeto_plano_atividade = models.ForeignKey('ProjetoPlanoAtividade', verbose_name='Macroprocesso', on_delete=models.CASCADE)
    etapa = models.ForeignKey('EtapaProjeto', verbose_name='Componente funcional do macroprocesso', on_delete=models.CASCADE)
    origens_recurso_projeto_etapa = models.ManyToManyField(OrigemRecursoProjeto, through='OrigemRecursoProjetoEtapa')
    tipo_especial = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Componente funcional do macroprocesso'
        verbose_name_plural = 'Componentes funcionais dos macroprocessos'

        unique_together = ('projeto_plano_atividade', 'etapa')

    def __str__(self):
        return f'{self.projeto_plano_atividade} | {self.etapa}'

    def etapa_dono(self, usuario=None):
        from plan_estrategico.utils import get_setor_unidade_gestora

        if not usuario:
            usuario = tl.get_user()
        return bool(
            EtapaProjetoPlanoAtividade.objects.filter(
                pk=self.id, projeto_plano_atividade__projeto__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=usuario)
            )
        )

    def eh_especial(self):
        return self.tipo_especial is True

    def tem_unidade_adm(self, usuario=None):
        from plan_estrategico.utils import get_setor_unidade_gestora

        if not usuario:
            usuario = tl.get_user()
        return bool(
            UnidadeGestoraEtapa.objects.filter(
                etapa_projeto_plano_atividade=self, unidade_gestora__setor_equivalente=get_setor_unidade_gestora(usuario)
            ).exists()
        )

    def tem_atividades(self, unidade=None):
        return bool(AtividadeEtapa.objects.filter(etapa_projeto_plano_atividade=self, unidade_gestora=unidade).exists())

    def get_valor_total_origem_recurso(self):
        total = Decimal('0')
        for origem in OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade=self):
            if origem.valor:
                total += origem.valor
        return total

    def get_unidades_etapa(self):
        total_unidades_etapa = []
        total_unidades_etapa.append(
            {'campi': ', '.join(self.unidades_gestoras.all().values_list('unidade_gestora__setor_equivalente__sigla', flat=True))}
        )
        return total_unidades_etapa

    def tem_valor_rateado_unidades(self):
        origens_recurso = OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade=self).exists()
        if origens_recurso:
            for origem in OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade=self):
                if UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=origem, valor__gt=0).exists():
                    return True
        return False


class OrigemRecursoProjetoEtapa(ModelPlus):
    SEARCH_FIELDS = ['origem_recurso_projeto']
    etapa_projeto_plano_atividade = models.ForeignKeyPlus(
        'EtapaProjetoPlanoAtividade',
        verbose_name='Componente funcional do macroprocesso',
        related_name='origens_recurso_etapa',
        on_delete=models.CASCADE,
    )
    origem_recurso_projeto = models.ForeignKeyPlus(
        'OrigemRecursoProjeto', verbose_name='Origem de recurso do macroprocesso do plano de atividade', on_delete=models.CASCADE
    )
    valor = models.DecimalFieldPlus('Valor Solicitado', null=True, blank=True)
    tipo_especial = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Origem de recurso do componente funcional do macroprocesso'
        verbose_name_plural = 'Origens de recurso dos componentes funcionais do macroprocesso'

        unique_together = ('etapa_projeto_plano_atividade', 'origem_recurso_projeto')

    def __str__(self):
        return f'{self.origem_recurso_projeto}'

    def get_valor(self):
        return self.valor or 0

    def get_valor_unidade(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        usuario = tl.get_user()
        valor = 0

        if UnidadeOrigemEtapa.objects.filter(
            origem_recurso_etapa=self, unidade_gestora__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=usuario)
        ).exists():
            valor = UnidadeOrigemEtapa.objects.filter(
                origem_recurso_etapa=self, unidade_gestora__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=usuario)
            )[0].valor
        return valor

    def tem_valor_distribuido(self):
        return bool(AtividadeEtapa.objects.filter(origem_recurso_etapa=self, valor_rateio__isnull=False).exists())

    def tem_valor_especial_distribuido(self):
        return bool(AtividadeEtapa.objects.filter(origem_recurso_etapa=self, valor_reserva_tecnica__isnull=False).exists())

    def get_valor_distribuido_uas(self):
        total = 0
        if UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=self).exists():
            unidades = UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=self)
            total = unidades.aggregate(total=Sum('valor'))['total'] or 0
        return total

    def get_valor_rateado_uas(self):
        return self.get_valor() == self.get_valor_distribuido_uas()

    def get_valor_compatibilizado(self, unidade=None):
        atividades = AtividadeEtapa.objects.filter(origem_recurso_etapa=self, etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade)
        atividades_reserva_tecnica = AtividadeEtapa.objects.filter(origem_recurso_reserva_tecnica=self)
        if unidade:
            atividades = atividades.filter(unidade_gestora=unidade)
            atividades_reserva_tecnica = atividades_reserva_tecnica.filter(unidade_gestora=unidade)

        total_valor = atividades.aggregate(total=Sum('valor_rateio'))['total'] or 0
        total_reserva_tecnica = atividades_reserva_tecnica.aggregate(total=Sum('valor_reserva_tecnica'))['total'] or 0
        total = total_valor + total_reserva_tecnica
        return total

    def get_valor_recebido_unidade(self, unidade):
        valor = 0
        if UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=self, unidade_gestora__unidade_gestora=unidade).exists():
            valor = UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=self, unidade_gestora__unidade_gestora=unidade)[0].valor
        return valor or 0

    def get_valor_total_compatibilizado(self, unidade=None):
        if unidade:
            if self.get_valor_recebido_unidade(unidade) == self.get_valor_compatibilizado(unidade):
                return True
        return self.get_valor() == self.get_valor_compatibilizado(unidade)


class UnidadeGestoraEtapa(ModelPlus):
    etapa_projeto_plano_atividade = models.ForeignKeyPlus(
        'EtapaProjetoPlanoAtividade',
        verbose_name='Componente funcional do macroprocesso',
        related_name='unidades_gestoras',
        on_delete=models.CASCADE,
    )
    unidade_gestora = models.ForeignKey('UnidadeGestora', verbose_name='Unidade gestora do componente funcional', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Unidade gestora do componente funcional'
        verbose_name_plural = 'Unidades gestoras do componente funcional'
        ordering = ['unidade_gestora__setor_equivalente']
        unique_together = ('etapa_projeto_plano_atividade', 'unidade_gestora')

    def __str__(self):
        return f'{self.etapa_projeto_plano_atividade} | {self.unidade_gestora}'


class UnidadeOrigemEtapa(ModelPlus):
    origem_recurso_etapa = models.ForeignKeyPlus(
        'OrigemRecursoProjetoEtapa', verbose_name='Origem recurso do componente funcional', on_delete=models.CASCADE
    )
    unidade_gestora = models.ForeignKey('UnidadeGestoraEtapa', verbose_name='Unidade gestora do componente funcional', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Valor', null=True, blank=True)

    class Meta:
        verbose_name = 'Unidade gestora do componente funcional'
        verbose_name_plural = 'Unidades gestoras do componente funcional'
        ordering = ['unidade_gestora__unidade_gestora__setor_equivalente']
        unique_together = ('origem_recurso_etapa', 'unidade_gestora')

    def __str__(self):
        return f'{self.origem_recurso_etapa} | {self.unidade_gestora}'

    def get_total_valor_rateado(self):
        total = 0
        atividades = AtividadeEtapa.objects.filter(
            origem_recurso_etapa=self.origem_recurso_etapa,
            etapa_projeto_plano_atividade=self.origem_recurso_etapa.etapa_projeto_plano_atividade,
            unidade_gestora=self.unidade_gestora.unidade_gestora,
        )
        if atividades:
            total = atividades.aggregate(total=Sum('valor_rateio'))['total'] or 0
        return total

    def get_total_valor_reserva_tecnica(self):
        total = 0
        atividades = AtividadeEtapa.objects.filter(
            origem_recurso_etapa=self.origem_recurso_etapa,
            etapa_projeto_plano_atividade=self.origem_recurso_etapa.etapa_projeto_plano_atividade,
            unidade_gestora=self.unidade_gestora.unidade_gestora,
        )
        if atividades:
            total = atividades.aggregate(total=Sum('valor_reserva_tecnica'))['total'] or 0
        return total

    def get_total_valor_proposto(self):
        total = 0
        atividades = AtividadeEtapa.objects.filter(
            origem_recurso_etapa=self.origem_recurso_etapa,
            etapa_projeto_plano_atividade=self.origem_recurso_etapa.etapa_projeto_plano_atividade,
            unidade_gestora=self.unidade_gestora.unidade_gestora,
        )
        if atividades:
            total = atividades.aggregate(total=Sum('valor'))['total'] or 0
        return total

    def get_total_unidade(self):
        return self.get_total_valor_rateado() + self.get_total_valor_reserva_tecnica()


class AtividadeEtapa(ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']
    etapa_projeto_plano_atividade = models.ForeignKeyPlus(
        'EtapaProjetoPlanoAtividade', verbose_name='Componente funcional do macroprocesso', on_delete=models.CASCADE
    )
    origem_recurso_etapa = models.ForeignKeyPlus(
        'OrigemRecursoProjetoEtapa', verbose_name='Origem de recurso do componente funcional', blank=True, on_delete=models.CASCADE, null=True
    )
    naturezadespesa = models.ForeignKeyPlus(
        'NaturezaDespesaPlanoAtividade', verbose_name='Natureza de Despesa', blank=True, on_delete=models.CASCADE, null=True
    )
    valor = models.DecimalFieldPlus('Valor Proposto', default=0)
    nome = models.CharField(max_length=200, verbose_name='Nome da Atividade')
    descricao = models.TextField('Descrição', max_length=1500)
    unidade_gestora = models.ForeignKey(
        'UnidadeGestora', verbose_name='Unidade gestora da atividade', on_delete=models.CASCADE, null=True, blank=True
    )
    valor_rateio = models.DecimalFieldPlus('Valor Rateio', null=True, blank=True)
    valor_reserva_tecnica = models.DecimalFieldPlus('Valor Rateio', null=True, blank=True)
    origem_recurso_reserva_tecnica = models.ForeignKeyPlus(
        'OrigemRecursoProjetoEtapa',
        related_name='origem_especial',
        verbose_name='Origem Reserva Técnica',
        blank=True,
        on_delete=models.CASCADE,
        null=True,
    )
    valor_realocado = models.DecimalFieldPlus('Valor de Rateio', null=True, blank=True, default=0)
    valor_corrigido_plano = models.DecimalFieldPlus('Valor de Rateio', null=True, blank=True, default=0)
    plano_interno = models.ForeignKeyPlus(
        'PlanoInternoPlanoAtividade', verbose_name='Plano  Interno', blank=True, on_delete=models.CASCADE, null=True
    )
    atividade_complementar = models.BooleanField('Atividade complementar', default=False)
    usuario = models.CurrentUserField(verbose_name='Cadastrado por')

    class Meta:
        verbose_name = 'Atividade do componente funcional'
        verbose_name_plural = 'Atividades dos componentes funcionais'

    def __str__(self):
        return f'{self.nome}'

    @classmethod
    def pode_editar_atividade(self, usuario=None, plano_atividade=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(usuario.has_perm('plan_estrategico.change_atividadeetapa') and plano_atividade.em_periodo_atividade_preloa)

    @classmethod
    def pode_incluir_atividade(self, usuario=None, plano_atividade=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(usuario.has_perm('plan_estrategico.add_atividadeetapa') and plano_atividade.em_periodo_atividade_preloa)

    @classmethod
    def pode_excluir_atividade(self, usuario=None, plano_atividade=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(usuario.has_perm('plan_estrategico.delete_atividadeetapa') and plano_atividade.em_periodo_atividade_preloa)

    @classmethod
    def eh_coordenadorUA(cls, usuario):
        return bool(usuario.has_perm('plan_estrategico.add_atividadeetapa'))

    @classmethod
    def pode_ver_atividade(self, usuario=None, plano_atividade=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(
            usuario.has_perm('plan_estrategico.view_atividadeetapa')
            and (plano_atividade.em_periodo_atividade_preloa or plano_atividade.em_periodo_atividades_posloa)
        )

    def eh_dono(self, usuario=None):
        from plan_estrategico.utils import get_setor_unidade_gestora

        if not usuario:
            usuario = tl.get_user()
        return bool(AtividadeEtapa.objects.filter(pk=self.id, unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=usuario)).exists())

    @classmethod
    def pode_ver_todas_atividades(self, usuario=None, plano_atividade=None):
        if not usuario:
            usuario = tl.get_user()
        return bool(
            (
                usuario.groups.filter(name='Gestor de Projeto').exists()
                or usuario.groups.filter(name='Administrador de Planejamento Estratégico').exists()
            )
            and (
                plano_atividade.em_periodo_atividade_preloa
                or plano_atividade.em_periodo_orcamentario_posloa
                or plano_atividade.em_periodo_projeto_posloa
                or plano_atividade.em_periodo_atividades_posloa
            )
        )

    def get_total(self):
        return (self.valor_rateio or 0) + (self.valor_reserva_tecnica or 0)

    def get_valor_rateio(self):
        return self.valor_rateio or 0

    def get_valor_reserva_tecnica(self):
        return self.valor_reserva_tecnica or 0

    def get_valor_realocado(self):
        requisicoes_concedentes = RequisicaoRealocacao.objects.filter(
            atividade_concedente=self, status=RequisicaoRealocacao.STATUS_DEFERIDA
        ).aggregate(Sum('valor_final')).get('valor_final__sum') or Decimal(0)
        requisicoes_recebedoras = RequisicaoRealocacao.objects.filter(
            atividade_recebedora=self, status=RequisicaoRealocacao.STATUS_DEFERIDA
        ).aggregate(Sum('valor_final')).get('valor_final__sum') or Decimal(0)
        return requisicoes_recebedoras - requisicoes_concedentes

    def get_valor_disponivel_execucao(self):
        return (self.valor_realocado or 0) + self.get_total()

    def get_total_pi_em_realocacao(self, excluir_requisicao=None):
        requisicoes_concedentes = RequisicaoRealocacao.objects.filter(
            atividade_concedente__plano_interno=self.plano_interno, unidade_concedente=self.unidade_gestora
        ).exclude(status__in=[RequisicaoRealocacao.STATUS_DEFERIDA, RequisicaoRealocacao.STATUS_INDEFERIDA, RequisicaoRealocacao.STATUS_CANCELADA])
        if excluir_requisicao:
            requisicoes_concedentes = requisicoes_concedentes.exclude(id=excluir_requisicao.id)
        requisicoes_concedentes = requisicoes_concedentes.aggregate(Sum('valor_requisicao')).get('valor_requisicao__sum') or Decimal(0)

        return requisicoes_concedentes

    def get_limite_a_realocar(self):
        if self.plano_interno is None:
            return 0
        saldo_plano_interno = self.plano_interno.saldo_plano_interno(unidade_gestora=self.unidade_gestora)
        limite_pi = saldo_plano_interno - (abs(self.get_total_pi_em_realocacao()))
        valor_atividade = self.get_valor_disponivel_realocacao() - self.get_total_empenhados()
        if valor_atividade > limite_pi:
            return limite_pi
        else:
            return valor_atividade

    def get_limite_a_realocar_mesmo_pi_ua(self):
        return self.get_valor_disponivel_realocacao() - self.get_total_empenhados()

    def limitar_deferimento_realocacao(self, requisicao=None):
        saldo_plano_interno = self.plano_interno.saldo_plano_interno(unidade_gestora=self.unidade_gestora)
        limite_pi = saldo_plano_interno - (abs(self.get_total_pi_em_realocacao(excluir_requisicao=requisicao)))
        valor_atividade = self.get_valor_disponivel_realocacao() - self.get_total_empenhados()
        if requisicao:
            valor_atividade += requisicao.valor_requisicao or 0

        if valor_atividade >= limite_pi:
            return limite_pi
        else:
            return valor_atividade

    def get_valor_disponivel_movimentacao(self, unidade_gestora=None):
        total_rateio = 0
        total_reserva_tecnica = 0
        total_realocado = 0
        if self.origem_recurso_etapa:
            total_rateio = AtividadeEtapa.objects.filter(
                origem_recurso_etapa__origem_recurso_projeto=self.origem_recurso_etapa.origem_recurso_projeto, unidade_gestora=unidade_gestora
            ).aggregate(Sum('valor_rateio')).get('valor_rateio__sum') or Decimal(0)
            total_reserva_tecnica = AtividadeEtapa.objects.filter(
                origem_recurso_etapa__origem_recurso_projeto=self.origem_recurso_etapa.origem_recurso_projeto, unidade_gestora=unidade_gestora
            ).aggregate(Sum('valor_reserva_tecnica')).get('valor_reserva_tecnica__sum') or Decimal(0)
            total_realocado = AtividadeEtapa.objects.filter(
                origem_recurso_etapa__origem_recurso_projeto=self.origem_recurso_etapa.origem_recurso_projeto, unidade_gestora=unidade_gestora
            ).aggregate(Sum('valor_realocado')).get('valor_realocado__sum') or Decimal(0)
        return total_rateio + total_reserva_tecnica + total_realocado

    def get_valor_disponivel_plano_interno(self, unidade_gestora=None):
        atividades = AtividadeEtapa.objects.filter(plano_interno__isnull=False)
        if atividades:
            total_rateio = AtividadeEtapa.objects.filter(plano_interno=self.plano_interno).aggregate(Sum('valor_rateio')).get(
                'valor_rateio__sum'
            ) or Decimal(0)
            total_reserva_tecnica = AtividadeEtapa.objects.filter(plano_interno=self.plano_interno).aggregate(Sum('valor_reserva_tecnica')).get(
                'valor_reserva_tecnica__sum'
            ) or Decimal(0)
            total_realocado = AtividadeEtapa.objects.filter(plano_interno=self.plano_interno).aggregate(Sum('valor_realocado')).get(
                'valor_realocado__sum'
            ) or Decimal(0)

            return total_rateio + total_reserva_tecnica + total_realocado
        else:
            return Decimal(0)

    def get_total_em_realocacao(self):
        valor = RequisicaoRealocacao.objects.filter(atividade_concedente=self).exclude(
            status__in=[RequisicaoRealocacao.STATUS_DEFERIDA, RequisicaoRealocacao.STATUS_INDEFERIDA, RequisicaoRealocacao.STATUS_CANCELADA]
        ).aggregate(Sum('valor_requisicao')).get('valor_requisicao__sum') or Decimal(0)
        requisicoes_concedentes = -valor if valor > 0 else valor
        return requisicoes_concedentes

    def get_valor_disponivel_realocacao(self):
        return (self.get_total() + self.get_valor_realocado()) - abs(self.get_total_em_realocacao())

    def get_total_empenhados_atividade(self):
        total = RequisicaoDespesa.objects.filter(
            atividade=self, status__in=[RequisicaoDespesa.STATUS_CONCLUIDA, RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO]
        ).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)
        return total

    def get_total_em_tramitacao(self):
        dotacao = RequisicaoDespesa.objects.filter(atividade=self, tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO).exclude(
            status__in=[RequisicaoDespesa.STATUS_CANCELADA, RequisicaoDespesa.STATUS_CONCLUIDA]
        ).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)
        reforco = RequisicaoDespesa.objects.filter(atividade=self, tipo_requisicao=RequisicaoDespesa.TIPO_REFORCO_EMPENHO).exclude(
            status__in=[RequisicaoDespesa.STATUS_CANCELADA, RequisicaoDespesa.STATUS_CONCLUIDA]
        ).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)
        anulacao = RequisicaoDespesa.objects.filter(atividade=self, tipo_requisicao=RequisicaoDespesa.TIPO_ANULACAO_EMPENHO).exclude(
            status__in=[RequisicaoDespesa.STATUS_CANCELADA, RequisicaoDespesa.STATUS_CONCLUIDA]
        ).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)
        return (dotacao + reforco) - anulacao

    def get_total_em_realocacao_recebedora(self):
        requisicoes_recebedoras = RequisicaoRealocacao.objects.filter(atividade_recebedora=self).exclude(
            status__in=[RequisicaoRealocacao.STATUS_DEFERIDA, RequisicaoRealocacao.STATUS_INDEFERIDA, RequisicaoRealocacao.STATUS_CANCELADA]
        ).aggregate(Sum('valor_requisicao')).get('valor_requisicao__sum') or Decimal(0)
        return requisicoes_recebedoras

    def saldo_disponivel_empenho_atividade(self):
        return self.get_valor_disponivel_realocacao() - self.get_total_empenhados()

    def get_total_empenhados(self):
        """Total comprometido da atividade pelas requisições de despesa."""
        anulacao_nao_validada = Q(tipo_requisicao=RequisicaoDespesa.TIPO_ANULACAO_EMPENHO) & ~Q(status=RequisicaoDespesa.STATUS_CONCLUIDA)
        total = RequisicaoDespesa.objects.filter(atividade=self).exclude(
            Q(status=RequisicaoDespesa.STATUS_CANCELADA) | Q(tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA) | anulacao_nao_validada
        ).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)
        return total

    def get_caminho_as_html(self):
        caminho = self.get_caminho()
        caminho_html = []
        for s in caminho:
            if hasattr(s, 'unidadeorganizacional'):
                s_repr = f'<span class="admin-setor-uo" title="{s.nome}">{s}</span>'
            elif s == caminho[-1]:
                s_repr = f'<span class="admin-setor" title="{s.nome}">{s} ({s.nome})</span>'
            else:
                s_repr = f'<span title="{s.nome}">{s}</span>'
            caminho_html.append(s_repr)
        return mark_safe(' &rarr; '.join(caminho_html))


class CompartilhamentoPoderdeGestorUA(models.ModelPlus):
    setor_dono = models.ForeignKeyPlus('rh.Setor')

    vinculo_permitido = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Pessoa com Poder de Gestor de UA', null=True)

    data_criacao = models.DateTimeFieldPlus('Data de Criação', editable=False, null=True, blank=True)
    usuario_criacao = models.ForeignKeyPlus(User, verbose_name='Usuário de Criação', editable=False, null=True, blank=True)

    class Meta:
        verbose_name = 'Configuração de Compartilhamento de Poder de Gestor de Unid. Administrativa'
        verbose_name_plural = 'Configurações de Compartilhamento Poder de Gestor de Unid. Administrativa'
        permissions = (('pode_gerenciar_permissoes_da_ua', 'Pode gerenciar permissoes da Unidade'),)

    def __str__(self):
        return f'Poder de Gestor de UA no setor {self.setor_dono} para {self.vinculo_permitido}'

    @staticmethod
    def atualizar_poder_gestor(usuario_criacao, setor_dono, vinculos_poder_gestor):
        for vinculo in vinculos_poder_gestor:
            comp = CompartilhamentoPoderdeGestorUA()
            comp.setor_dono = setor_dono
            comp.vinculo_permitido = vinculo
            comp.data_criacao = date.today()
            comp.usuario_criacao = usuario_criacao
            comp.save()
            vinculo.user.save()
        grupo_tem_poder_gestor = Group.objects.get(name='Coordenador de UA')
        for comp in CompartilhamentoPoderdeGestorUA.objects.filter(setor_dono=setor_dono):
            if comp.vinculo_permitido not in vinculos_poder_gestor:
                user = comp.vinculo_permitido.user
                if user:
                    user.groups.remove(grupo_tem_poder_gestor)
                comp.delete()
        return True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def delete(self):
        super().delete()


class RequisicaoRealocacao(ModelPlus):
    STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE = 1
    STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA = 2
    STATUS_DEFERIDA = 3
    STATUS_INDEFERIDA = 4
    STATUS_CANCELADA = 5

    STATUS_CHOICES = (
        (STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE, 'Aguardando aprovação do gestor da unidade concedente'),
        (STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA, 'Aguardando aprovação do gestor da unidade recebedora'),
        (STATUS_DEFERIDA, 'Deferida'),
        (STATUS_INDEFERIDA, 'Indeferida'),
        (STATUS_CANCELADA, 'Cancelada'),
    )

    TIPO_REALOCACAO_UA_CONCEDENTE = 1
    TIPO_REALOCACAO_UA_RECEBEDORA = 2
    TIPO_REALOCACAO_AMBAS = 3

    TIPO_REALOCACAO_CHOICES = (
        (TIPO_REALOCACAO_UA_CONCEDENTE, 'Realocação Unidade Concedente'),
        (TIPO_REALOCACAO_UA_RECEBEDORA, 'Realocação Unidade Recebedora'),
        (TIPO_REALOCACAO_AMBAS, 'Realocação Ambas'),
    )
    data_cadastro = models.DateTimeFieldPlus('Data', auto_now_add=True)
    usuario = models.CurrentUserField(verbose_name='Cadastrado por')
    plano_atividade = models.ForeignKeyPlus('PlanoAtividade', on_delete=models.CASCADE)
    unidade_concedente = models.ForeignKey(
        'UnidadeGestora', verbose_name='Unidade Concedente', related_name='unidade_concedente', on_delete=models.CASCADE, null=True, blank=True
    )
    atividade_concedente = models.ForeignKey(
        'AtividadeEtapa', verbose_name='Atividade Concedente', related_name='atividade_concedente', on_delete=models.CASCADE, null=True, blank=True
    )
    unidade_recebedora = models.ForeignKey(
        'UnidadeGestora', verbose_name='Unidade Recebedora', related_name='unidade_recebedora', on_delete=models.CASCADE, null=True, blank=True
    )
    atividade_recebedora = models.ForeignKey(
        'AtividadeEtapa', verbose_name='Atividade Recebedora', related_name='atividade_recebedora', on_delete=models.CASCADE, null=True, blank=True
    )
    projeto_concedente = models.ForeignKey(
        'ProjetoPlanoAtividade',
        verbose_name='Macroprocesso Concedente',
        related_name='projeto_concedente',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    projeto_recebedor = models.ForeignKey(
        'ProjetoPlanoAtividade',
        verbose_name='Macroprocesso Recebedor',
        related_name='projeto_recebedor',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    origem_concedente = models.ForeignKey(
        'OrigemRecursoProjeto',
        verbose_name='Origem de Recurso Concedente',
        related_name='origemrecurso_concedente',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    origem_recebedora = models.ForeignKey(
        'OrigemRecursoProjeto',
        verbose_name='Origem de Recurso Recebedora',
        related_name='origemrecurso_recebedor',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    valor_requisicao = models.DecimalField(verbose_name='Valor da Requisição', max_digits=12, decimal_places=2, default=0)
    status = models.PositiveIntegerField('Situação', choices=STATUS_CHOICES, default=STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE)
    justificativa = models.TextField('Justificativa', blank=True)
    comentario_indeferimento = models.TextField('Motivo do indeferimento', blank=True)
    motivo_cancelamento = models.TextField('Motivo do cancelamento', blank=True)
    tipo_requisicao = models.PositiveIntegerField('Tipo', choices=TIPO_REALOCACAO_CHOICES, default=TIPO_REALOCACAO_UA_CONCEDENTE)
    restringir_ao_mesmo_macroprocesso = models.BooleanField(
        verbose_name='Restringir a atividade recebedora ao mesmo macroprocesso',
        help_text='Se marcado, a Unidade Recebedora somente poderá indicar, no deferimento desta requisição de realocação, uma atividade vinculada ao mesmo macroprocesso da atividade concedente.',
        default=False,
    )
    numero = models.CharField(verbose_name='Nº da Requisição', max_length=12, null=True)
    valor_aprovado_unidade = models.DecimalField(verbose_name='Valor Concedido Unidade', max_digits=12, decimal_places=2, default=0)
    valor_aprovado_projeto = models.DecimalField(verbose_name='Valor Concedido Macroprocesso', max_digits=12, decimal_places=2, default=0)
    valor_final = models.DecimalField(verbose_name='Valor Deferido', max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Requisição de Realocação'
        verbose_name_plural = 'Requisições de Realocações'

    def get_absolute_url(self):
        return f'/plan_estrategico/detalhar_requisicao_realocacao/{self.pk}/'

    @classmethod
    def get_qs_aguardando_aprovacao_gestor_concedente(cls, user, qs=None):
        from plan_estrategico.utils import get_setor_unidade_gestora

        if qs is None:
            qs = cls.objects.all()
        return qs.filter(
            status=cls.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE, unidade_concedente__setor_equivalente=get_setor_unidade_gestora(user=user)
        )

    @classmethod
    def get_qs_aguardando_aprovacao_gestor_recebedor(cls, user, qs=None):
        from plan_estrategico.utils import get_setor_unidade_gestora

        if qs is None:
            qs = cls.objects.all()
        return qs.filter(
            status=cls.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA, unidade_recebedora__setor_equivalente=get_setor_unidade_gestora(user)
        )

    def get_status(self):
        if self.status == RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE:
            return f'<span class="status status-alert"> {self.get_status_display()} </span>'
        elif self.status == RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA:
            return f'<span class="status status-alert">{self.get_status_display()} </span>'
        elif self.status == RequisicaoRealocacao.STATUS_CANCELADA:
            return f'<span class="status status-cancelado">{self.get_status_display()} </span>'
        elif self.status == RequisicaoRealocacao.STATUS_INDEFERIDA:
            return f'<span class="status status-rejeitado">{self.get_status_display()} </span>'
        elif self.status == RequisicaoRealocacao.STATUS_DEFERIDA:
            return f'<span class="status status-success">{self.get_status_display()} </span>'

    def pode_avaliar(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        return (
            (
                self.status == RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA
                and self.unidade_recebedora.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
            or (
                self.status == RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE
                and self.unidade_concedente.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
        ) and (in_group(user, 'Gestor de UA') or in_group(user, 'Coordenador de UA'))

    def pode_cancelar(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        return (
            (
                self.status == RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA
                and self.unidade_concedente.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
            or (
                self.status == RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE
                and self.unidade_recebedora.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
        ) and (in_group(user, 'Gestor de UA') or in_group(user, 'Coordenador de UA'))

    @transaction.atomic()
    def cancelar_requisicaorealocacao(self, user):
        self.status = RequisicaoRealocacao.STATUS_CANCELADA
        self.save()
        RequisicaoRealocacaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

    @transaction.atomic()
    def indeferir_requisicaorealocacao(self, user):
        self.status = RequisicaoRealocacao.STATUS_INDEFERIDA
        self.save()
        RequisicaoRealocacaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

    @transaction.atomic()
    def deferir_requisicaorealocacao(self, user, valor_aprovado_unidade=None, atividade_concedente=None, atividade_recebedora=None):
        if self.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_AMBAS:
            self.valor_aprovado_unidade = self.valor_requisicao
            self.valor_final = self.valor_requisicao
            self.status = RequisicaoRealocacao.STATUS_DEFERIDA
            self.save()
        else:
            self.valor_aprovado_unidade = valor_aprovado_unidade
            self.valor_final = valor_aprovado_unidade
            self.status = RequisicaoRealocacao.STATUS_DEFERIDA
            self.atividade_concedente = atividade_concedente
            self.atividade_recebedora = atividade_recebedora
            self.projeto_concedente = atividade_concedente.etapa_projeto_plano_atividade.projeto_plano_atividade
            self.origem_concedente = atividade_concedente.origem_recurso_etapa.origem_recurso_projeto
            self.projeto_recebedor = atividade_recebedora.etapa_projeto_plano_atividade.projeto_plano_atividade
            self.origem_recebedora = atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto
            self.save()

        self.atividade_concedente.valor_realocado -= self.valor_final
        self.atividade_recebedora.valor_realocado += self.valor_final
        self.atividade_concedente.save()
        self.atividade_recebedora.save()
        RequisicaoRealocacaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)


class RequisicaoRealocacaoHistorico(models.ModelPlus):
    requisicao = models.ForeignKeyPlus(RequisicaoRealocacao, on_delete=models.CASCADE)
    status = models.PositiveIntegerField(choices=RequisicaoRealocacao.STATUS_CHOICES)
    alterado_em = models.DateTimeField(auto_now_add=True)
    alterado_por = models.CurrentUserField()

    class Meta:
        verbose_name = 'Histórico de Requisição de Realocação'
        verbose_name_plural = 'Históricos de Requisições de Realocações'

        ordering = ('alterado_em',)
        unique_together = ('requisicao', 'status')

    def get_status(self):
        self.requisicao.status = self.status
        return self.requisicao.get_status()

    def get_status_class(self):
        status = self.status
        if status == RequisicaoRealocacao.STATUS_DEFERIDA:
            return 'success'
        elif status == RequisicaoRealocacao.STATUS_CANCELADA or status == RequisicaoRealocacao.STATUS_INDEFERIDA:
            return 'error'
        else:
            return 'warning'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class PlanoInternoPlanoAtividade(ModelPlus):
    SEARCH_FIELDS = ['plano_interno__codigo', 'plano_interno__descricao']

    plano_atividade = models.ForeignKeyPlus('PlanoAtividade', verbose_name='Plano de Atividade')
    plano_interno = models.ForeignKeyPlus('PlanoInterno', verbose_name='Plano Interno')

    class Meta:
        verbose_name = 'Plano Interno do Plano de Atividade'
        verbose_name_plural = 'Planos Internos do Plano de Atividade'

    def __str__(self):
        return f'{self.plano_interno.codigo} - {self.plano_interno.descricao}'

    @classmethod
    def pode_gerenciar(cls, usuario, plano_atividade):
        return bool(in_group(usuario, 'Administrador de Planejamento Estratégico') and plano_atividade.em_periodo_orcamentario_preloa)

    def get_disponivel_plano_interno(self, unidade_gestora):
        atividades = AtividadeEtapa.objects.filter(plano_interno=self)
        if unidade_gestora:
            atividades = AtividadeEtapa.objects.filter(plano_interno=self, unidade_gestora=unidade_gestora)
        if atividades:
            total_rateio = atividades.aggregate(Sum('valor_rateio')).get('valor_rateio__sum') or 0

            total_reserva_tecnica = atividades.aggregate(Sum('valor_reserva_tecnica')).get('valor_reserva_tecnica__sum') or 0
            total_realocado = atividades.aggregate(Sum('valor_realocado')).get('valor_realocado__sum') or 0

            return total_rateio + total_reserva_tecnica + total_realocado
        else:
            return 0

    def get_total_em_movimentacao_plano_interno(self, unidade_gestora=None):
        total_movimentacoes = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=self, movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO, unidade=unidade_gestora
            )
            .exclude(
                movimentacao__status__in=[
                    MovimentacaoCredito.STATUS_CONCLUIDA,
                    MovimentacaoCredito.STATUS_CANCELADA,
                    MovimentacaoCredito.STATUS_REJEITADA,
                ]
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        total_ajuste_interno = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno_recebedor=self,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO,
                unidade=unidade_gestora,
            )
            .exclude(
                movimentacao__status__in=[
                    MovimentacaoCredito.STATUS_CONCLUIDA,
                    MovimentacaoCredito.STATUS_CANCELADA,
                    MovimentacaoCredito.STATUS_REJEITADA,
                ]
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        return total_movimentacoes + total_ajuste_interno

    def get_total_movimentado_plano_interno(self, unidade_gestora=None):
        total_movimentacoes_credito = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=self,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        total_estorno = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=self,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_ESTORNO_CREDITO,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )

        ajuste_interno_recebido = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno_recebedor=self,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        ajuste_interno_debitado = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=self,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        total_ajuste_interno = ajuste_interno_recebido - ajuste_interno_debitado
        total_movimentacoes = (total_movimentacoes_credito + total_ajuste_interno) - total_estorno
        return total_movimentacoes

    def get_total_devolucao_plano_interno(self, unidade_gestora=None):
        total_devolucao = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=self, movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_ESTORNO_CREDITO, unidade=unidade_gestora
            )
            .exclude(
                movimentacao__status__in=[
                    MovimentacaoCredito.STATUS_CONCLUIDA,
                    MovimentacaoCredito.STATUS_CANCELADA,
                    MovimentacaoCredito.STATUS_REJEITADA,
                ]
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )

        total_ajuste_interno = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=self, movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO, unidade=unidade_gestora
            )
            .exclude(
                movimentacao__status__in=[
                    MovimentacaoCredito.STATUS_CONCLUIDA,
                    MovimentacaoCredito.STATUS_CANCELADA,
                    MovimentacaoCredito.STATUS_REJEITADA,
                ]
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        return total_devolucao + total_ajuste_interno

    def saldo_plano_interno(self, unidade_gestora):
        return self.get_disponivel_plano_interno(unidade_gestora=unidade_gestora) - (
            self.get_total_movimentado_plano_interno(unidade_gestora=unidade_gestora)
            + self.get_total_em_movimentacao_plano_interno(unidade_gestora=unidade_gestora)
        )

    def valor_disponivel_movimentado(self, unidade_gestora):
        return self.get_total_movimentado_plano_interno(unidade_gestora=unidade_gestora) - self.get_total_devolucao_plano_interno(
            unidade_gestora=unidade_gestora
        )


class MovimentacaoCredito(ModelPlus):
    STATUS_AGUARDANDO_ANALISE_GOS = 1
    STATUS_AGUARDANDO_CIENCIA_GESTOR_MACROPROCESSO = 2
    STATUS_AGUARDANDO_VALIDACAO_SISTEMA = 3
    STATUS_INCONSISTENTE = 4
    STATUS_REJEITADA = 5
    STATUS_CONCLUIDA = 6
    STATUS_CANCELADA = 7
    STATUS_CHOICES = (
        (STATUS_AGUARDANDO_ANALISE_GOS, 'Aguardando análise do Gestor Orçamentário'),
        (STATUS_AGUARDANDO_CIENCIA_GESTOR_MACROPROCESSO, 'Indeferida - Aguardando ciência do Gestor de Macroprocesso'),
        (STATUS_AGUARDANDO_VALIDACAO_SISTEMA, 'Aguardando validação do SIAFI'),
        (STATUS_INCONSISTENTE, 'Requisição com inconsistências'),
        (STATUS_REJEITADA, 'Indeferida - Gestor de Macroprocesso Ciente'),
        (STATUS_CONCLUIDA, 'Concluída'),
        (STATUS_CANCELADA, 'Cancelada'),
    )
    TIPO_MOVIMENTACAO_CREDITO = 1
    TIPO_ESTORNO_CREDITO = 2
    TIPO_AJUSTE_INTERNO = 3

    TIPO_MOVIMENTACAO_CHOICES = (
        (TIPO_MOVIMENTACAO_CREDITO, 'Movimentação de crédito'),
        (TIPO_ESTORNO_CREDITO, 'Estorno de crédito'),
        (TIPO_AJUSTE_INTERNO, 'Ajuste interno'),
    )
    data_cadastro = models.DateTimeFieldPlus('Data', auto_now_add=True)
    usuario = models.CurrentUserField(verbose_name='Cadastrado por')
    plano_atividade = models.ForeignKeyPlus('PlanoAtividade', on_delete=models.CASCADE)
    projeto_estrategico = models.ForeignKey(
        'ProjetoPlanoAtividade',
        verbose_name='Macroprocesso',
        related_name='projeto_estrategico',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    origem_recurso = models.ForeignKey(
        'OrigemRecursoProjeto', verbose_name='Origem de recurso', related_name='origemrecurso', on_delete=models.CASCADE, null=True, blank=True
    )
    plano_interno = models.ForeignKeyPlus('PlanoInternoPlanoAtividade', verbose_name='Plano interno', blank=True, on_delete=models.CASCADE, null=True)
    justificativa = models.TextField('Justificativa', blank=True)
    motivo_indeferimento = models.TextField('Motivo do Indeferimento', blank=True)
    motivo_correcao = models.TextField('Motivo da Correção', blank=True)
    motivo_cancelamento = models.TextField('Motivo do Cancelamento', blank=True)
    tipo_requisicao = models.PositiveIntegerField('Tipo', choices=TIPO_MOVIMENTACAO_CHOICES)
    numero = models.CharField(verbose_name='Nº da Requisição', max_length=12, null=True)
    status = models.PositiveIntegerField('Situação', choices=STATUS_CHOICES, default=STATUS_AGUARDANDO_ANALISE_GOS)
    ciencia_indeferimento = models.BooleanField('Ciente', default=False)
    projeto_recebedor = models.ForeignKey(
        'ProjetoPlanoAtividade',
        verbose_name='Projeto Estratégico',
        related_name='projeto_estrategico_recebedor',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    origem_recurso_recebedor = models.ForeignKey(
        'OrigemRecursoProjeto',
        related_name='origem_recurso_recebedor',
        verbose_name='Origem de recurso',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    plano_interno_recebedor = models.ForeignKeyPlus(
        'PlanoInternoPlanoAtividade',
        related_name='plano_interno_recebedor',
        verbose_name='Plano interno',
        blank=True,
        on_delete=models.CASCADE,
        null=True,
    )
    conferencia_requisicao_siafi = models.BooleanField('Conferencia Requisição SIAFI', null=True)

    class Meta:
        verbose_name = 'Requisição de movimentação de crédito'
        verbose_name_plural = 'Requisições de movimentações de créditos'

    def get_absolute_url(self):
        return f'/plan_estrategico/detalhar_movimentacao_credito/{self.pk}/'

    def get_status(self):
        if self.status == MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS:
            return f'<span class="status status-alert"> {self.get_status_display()} </span>'
        elif (
            self.status == MovimentacaoCredito.STATUS_AGUARDANDO_CIENCIA_GESTOR_MACROPROCESSO
            or self.status == MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA
        ):
            return f'<span class="status status-alert">{self.get_status_display()} </span>'
        elif self.status == MovimentacaoCredito.STATUS_INCONSISTENTE:
            return f'<span class="status status-error">{self.get_status_display()} </span>'
        elif self.status == MovimentacaoCredito.STATUS_REJEITADA:
            return f'<span class="status status-rejeitado">{self.get_status_display()} </span>'
        elif self.status == MovimentacaoCredito.STATUS_CANCELADA:
            return f'<span class="status status-cancelado">{self.get_status_display()} </span>'
        elif self.status == MovimentacaoCredito.STATUS_CONCLUIDA:
            return f'<span class="status status-success">{self.get_status_display()} </span>'

    def pode_aprovar(self):
        user = tl.get_user()
        notas_dotacao = NotaDotacao.objects.filter(movimentacao=self).first()
        notas_credito = NotaCredito.objects.filter(movimentacao=self).first()
        from plan_estrategico.utils import get_setor_unidade_gestora

        unidade = MovimentacaoCreditoUnidade.objects.filter(movimentacao=self)[0].unidade
        return (notas_credito or notas_dotacao) and (
            (
                self.tipo_requisicao == MovimentacaoCredito.TIPO_AJUSTE_INTERNO
                and (self.status == MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS or self.status == MovimentacaoCredito.STATUS_INCONSISTENTE)
                and in_group(user, 'Gestor Orçamentário de UA')
                and unidade.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
            or (
                (
                    self.tipo_requisicao == MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO
                    or self.tipo_requisicao == MovimentacaoCredito.TIPO_ESTORNO_CREDITO
                )
                and (self.status == MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS or self.status == MovimentacaoCredito.STATUS_INCONSISTENTE)
            )
            and (in_group(user, 'Gestor Orçamentário Sistêmico'))
        )

    def pode_avaliar(self):
        user = tl.get_user()
        from plan_estrategico.utils import get_setor_unidade_gestora

        unidade = MovimentacaoCreditoUnidade.objects.filter(movimentacao=self)[0].unidade
        GOU_pode_avaliar = (
            self.tipo_requisicao == MovimentacaoCredito.TIPO_AJUSTE_INTERNO
            and (self.status == MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS or self.status == MovimentacaoCredito.STATUS_INCONSISTENTE)
            and in_group(user, 'Gestor Orçamentário de UA')
            and unidade.setor_equivalente == get_setor_unidade_gestora(user=user)
        )
        GOS_pode_avaliar = (
            self.tipo_requisicao != MovimentacaoCredito.TIPO_AJUSTE_INTERNO
            and (self.status == MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS or self.status == MovimentacaoCredito.STATUS_INCONSISTENTE)
            and in_group(user, 'Gestor Orçamentário Sistêmico')
        )
        return GOU_pode_avaliar or GOS_pode_avaliar

    def pode_cancelar(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        return (
            self.status == MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS
            and (in_group(user, 'Gestor de Projeto'))
            and self.projeto_estrategico.projeto.unidade_gestora.setor_equivalente == get_setor_unidade_gestora(user=user)
            and self.tipo_requisicao != MovimentacaoCredito.TIPO_AJUSTE_INTERNO
        )

    def pode_remover_notas(self):
        user = tl.get_user()
        return (
            self.tipo_requisicao != MovimentacaoCredito.TIPO_AJUSTE_INTERNO
            and self.status
            in [
                MovimentacaoCredito.STATUS_INCONSISTENTE,
                MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS,
                MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA,
            ]
            and (in_group(user, 'Gestor Orçamentário Sistêmico'))
        ) or (
            self.status
            in [
                MovimentacaoCredito.STATUS_INCONSISTENTE,
                MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS,
                MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA,
            ]
            and (in_group(user, 'Gestor Orçamentário Sistêmico'))
        )

    def pode_dar_ciencia(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        return (
            self.status == MovimentacaoCredito.STATUS_AGUARDANDO_CIENCIA_GESTOR_MACROPROCESSO
            and (in_group(user, 'Gestor de Projeto'))
            and self.projeto_estrategico.projeto.unidade_gestora.setor_equivalente == get_setor_unidade_gestora(user=user)
        )

    def tipo_ajuste(self):
        return self.tipo_requisicao == MovimentacaoCredito.TIPO_AJUSTE_INTERNO

    def total_notas_credito(self):
        return NotaCredito.objects.filter(movimentacao=self).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)

    def total_notas_dotacao(self):
        return NotaDotacao.objects.filter(movimentacao=self).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)

    def get_status_conferencia_siafi(self):
        if self.conferencia_requisicao_siafi is None:
            return '<span class="status status-alert"> Aguardando validação </span>'
        elif self.conferencia_requisicao_siafi is True:
            return '<span class="status status-success"> Validado </span>'
        elif self.conferencia_requisicao_siafi is False:
            return '<span class="status status-error"> Invalidado </span>'

    @transaction.atomic()
    def aprovar_movimentacaocredito(self):
        user = tl.get_user()
        self.status = MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA
        self.conferencia_requisicao_siafi = None
        MovimentacaoCreditoUnidade.objects.filter(movimentacao=self).update(
            valor_nc_conferido=None, valor_nd_conferido=None, conferencia_unidade_siafi=None
        )
        NotaDotacao.objects.filter(movimentacao=self).update(conferencia_pi_ptres_gnd=None, valor=None)
        NotaCredito.objects.filter(movimentacao=self).update(conferencia_pi_ptres_gnd=None, valor=None)
        self.save()
        MovimentacaoCreditoHistorico.objects.create(movimentacao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)
        grupos = Group.objects.filter(name__in=['Gestor de Projeto'])
        setores = self.projeto_estrategico.projeto.unidade_gestora.setor_equivalente.descendentes
        for grupo in grupos:
            for usuario in UsuarioGrupo.objects.filter(group=grupo, user__vinculo__setor__in=setores):
                titulo = f'[SUAP] Planejamento Estratégico: Requisição de movimentação de crédito {self.numero} aprovada'
                texto = (
                    '<h1>Planejamento Estratégico</h1>'
                    '<h2>Aprovação da requisição de movimentação de crédito</h2>'
                    '<p>A Requisição {0} foi <strong>aprovada.</strong></p>'
                    'Para mais informações, acesse: <a href = "{1}{2}">{1}{2}</a> </p>'.format(
                        self.numero, settings.SITE_URL, self.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.user.get_vinculo()],
                    categoria='Planejamento Estratégico: Aprovação da requisição de movimentação de crédito',
                )

    @transaction.atomic()
    def indeferir_movimentacaocredito(self):
        user = tl.get_user()
        self.status = MovimentacaoCredito.STATUS_AGUARDANDO_CIENCIA_GESTOR_MACROPROCESSO
        self.save()
        MovimentacaoCreditoHistorico.objects.create(movimentacao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

        grupos = Group.objects.filter(name__in=['Gestor de Projeto'])
        setores = self.projeto_estrategico.projeto.unidade_gestora.setor_equivalente.descendentes
        for grupo in grupos:
            for usuario in UsuarioGrupo.objects.filter(group=grupo, user__vinculo__setor__in=setores):
                titulo = f'[SUAP] Planejamento Estratégico: Indeferimento da requisição de movimentação de Crédito {self.numero}'
                texto = (
                    '<h1>Planejamento Estratégico</h1>'
                    '<h2>Indeferimento da requisição de movimentação de crédito.</h2>'
                    '<p>A Requisição {0} foi <strong>indeferida. </strong></p>'
                    'Para dar ciência a requisição e mais informações, acesse: <a href = "{1}{2}">{1}{2}</a> </p>'.format(
                        self.numero, settings.SITE_URL, self.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.user.get_vinculo()],
                    categoria='Planejamento Estratégico: Indeferimento da requisição de movimentação de Crédito',
                )

    @transaction.atomic()
    def cancelar_movimentacaocredito(self, user):
        self.status = MovimentacaoCredito.STATUS_CANCELADA
        self.save()
        MovimentacaoCreditoHistorico.objects.create(movimentacao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)
        grupos = Group.objects.filter(name__in=['Gestor de Projeto'])
        setores = self.projeto_estrategico.projeto.unidade_gestora.setor_equivalente.descendentes
        for grupo in grupos:
            for usuario in UsuarioGrupo.objects.filter(group=grupo, user__vinculo__setor__in=setores):
                titulo = f'[SUAP] Planejamento Estratégico: Cancelamento da requisição de movimentação de Crédito {self.numero}'
                texto = (
                    '<h1>Planejamento Estratégico</h1>'
                    '<h2>Cancelamento da requisição de movimentação de crédito.</h2>'
                    '<p>A Requisição {0} foi <strong>cancelada.</strong></p>'
                    'Para mais informações, acesse: <a href = "{1}{2}">{1}{2}</a> </p>'.format(
                        self.numero, settings.SITE_URL, self.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.user.get_vinculo()],
                    categoria='Planejamento Estratégico: Cancelamento da requisição de movimentação de Crédito',
                )

    def get_total_unidades(self):
        total_unidades = MovimentacaoCreditoUnidade.objects.filter(movimentacao=self).aggregate(Sum('valor')).get('valor__sum') or 0
        return total_unidades


class MovimentacaoCreditoUnidade(ModelPlus):
    movimentacao = models.ForeignKeyPlus(MovimentacaoCredito, on_delete=models.CASCADE)
    unidade = models.ForeignKey('UnidadeGestora', verbose_name='Unidade', related_name='unidade', on_delete=models.CASCADE, null=True, blank=True)
    valor = models.DecimalFieldPlus(null=True, blank=True)
    valor_nc_conferido = models.DecimalFieldPlus(null=True, blank=True)
    valor_nd_conferido = models.DecimalFieldPlus(null=True, blank=True)
    conferencia_unidade_siafi = models.BooleanField('Conferencia Unidade SIAFI', null=True)

    class Meta:
        verbose_name = 'Unidade da movimentação'
        verbose_name_plural = 'Unidades da movimentação'

        unique_together = ('movimentacao', 'unidade')

    @classmethod
    def get_total_em_movimentacao_unidade(cls, unidade_gestora=None, projeto=None, origem_recurso=None, plano_interno=None):
        total_movimentacoes = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=plano_interno,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO,
                movimentacao__projeto_estrategico=projeto,
                movimentacao__origem_recurso=origem_recurso,
                unidade=unidade_gestora,
            )
            .exclude(
                movimentacao__status__in=[
                    MovimentacaoCredito.STATUS_CONCLUIDA,
                    MovimentacaoCredito.STATUS_CANCELADA,
                    MovimentacaoCredito.STATUS_REJEITADA,
                ]
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        total_ajuste_interno = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno_recebedor=plano_interno,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO,
                movimentacao__projeto_recebedor=projeto,
                movimentacao__origem_recurso_recebedor=origem_recurso,
                unidade=unidade_gestora,
            )
            .exclude(
                movimentacao__status__in=[
                    MovimentacaoCredito.STATUS_CONCLUIDA,
                    MovimentacaoCredito.STATUS_CANCELADA,
                    MovimentacaoCredito.STATUS_REJEITADA,
                ]
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        return total_movimentacoes + total_ajuste_interno

    @classmethod
    def get_total_movimentado_unidade(cls, unidade_gestora=None, projeto=None, origem_recurso=None, plano_interno=None):
        total_movimentacoes_credito = MovimentacaoCreditoUnidade.objects.filter(
            movimentacao__plano_interno=plano_interno,
            movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO,
            movimentacao__projeto_estrategico=projeto,
            movimentacao__origem_recurso=origem_recurso,
            unidade=unidade_gestora,
            movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
        ).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)
        total_estorno = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=plano_interno,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_ESTORNO_CREDITO,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        ajuste_interno_recebido = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno_recebedor=plano_interno,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO,
                movimentacao__projeto_recebedor=projeto,
                movimentacao__origem_recurso_recebedor=origem_recurso,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        ajuste_interno_debitado = (
            MovimentacaoCreditoUnidade.objects.filter(
                movimentacao__plano_interno=plano_interno,
                movimentacao__tipo_requisicao=MovimentacaoCredito.TIPO_AJUSTE_INTERNO,
                movimentacao__projeto_estrategico=projeto,
                movimentacao__origem_recurso=origem_recurso,
                unidade=unidade_gestora,
                movimentacao__status=MovimentacaoCredito.STATUS_CONCLUIDA,
            )
            .aggregate(Sum('valor'))
            .get('valor__sum')
            or 0
        )
        total_ajuste_interno = ajuste_interno_recebido - ajuste_interno_debitado
        total_movimentacoes = (total_movimentacoes_credito + total_ajuste_interno) - total_estorno
        return total_movimentacoes

    def get_total_unidade(self):
        valor_nc = 0
        valor_nd = 0
        if self.valor_nc_conferido:
            valor_nc = self.valor_nc_conferido
        if self.valor_nd_conferido:
            valor_nd = self.valor_nd_conferido
        return valor_nc + valor_nd

    def get_status_conferencia(self):
        if self.conferencia_unidade_siafi is None:
            return '<span class="status status-alert"> Aguardando validação </span>'
        elif self.conferencia_unidade_siafi is True:
            return '<span class="status status-success"> Validado </span>'
        elif self.conferencia_unidade_siafi is False:
            return '<span class="status status-error"> Invalidado </span>'


class MovimentacaoCreditoHistorico(models.ModelPlus):
    movimentacao = models.ForeignKeyPlus(MovimentacaoCredito, on_delete=models.CASCADE)
    status = models.PositiveIntegerField(choices=MovimentacaoCredito.STATUS_CHOICES)
    alterado_em = models.DateTimeField(auto_now_add=True)
    alterado_por = models.CurrentUserField(blank=True)

    class Meta:
        ordering = ('alterado_em',)
        verbose_name = 'Histórico de requisição de movimentação de crédito'
        verbose_name_plural = 'Históricos de requisições de movimentações de crédito'

    def get_status(self):
        self.movimentacao.status = self.status
        return self.movimentacao.get_status()

    def get_status_class(self):
        status = self.status
        if status == MovimentacaoCredito.STATUS_CONCLUIDA:
            return 'success'
        elif (
            status == MovimentacaoCredito.STATUS_REJEITADA
            or status == MovimentacaoCredito.STATUS_INCONSISTENTE
            or status == MovimentacaoCredito.STATUS_CANCELADA
        ):
            return 'error'
        else:
            return 'warning'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class NotaCredito(models.ModelPlus):
    STATUS_AGUARDANDO_CONFIRMACAO_TESOURO = 1
    STATUS_CONFIRMADA = 2
    STATUS_CANCELADA = 3

    STATUS_NOTACREDITO_CHOICES = (
        (STATUS_AGUARDANDO_CONFIRMACAO_TESOURO, 'Aguardando confirmação do tesouro'),
        (STATUS_CONFIRMADA, 'Confirmada'),
        (STATUS_CANCELADA, 'Cancelada'),
    )
    numero = models.CharField('Número', max_length=23)
    movimentacao = models.ForeignKeyPlus(MovimentacaoCredito, on_delete=models.CASCADE)
    unidade = models.ForeignKeyPlus(UnidadeGestora, verbose_name='Unidade gestora', null=True)
    codigo_ug = models.IntegerFieldPlus('Código UG', null=True)
    unidade_orcamentaria = models.ForeignKeyPlus(ClassificacaoInstitucional, verbose_name='Unidade Orçamentária')
    ano = models.IntegerFieldPlus('Ano')
    documento_siafi = models.IntegerFieldPlus('Documento SIAFI')
    valor = models.DecimalFieldPlus('Valor', null=True)
    status = models.PositiveIntegerField('Situação', choices=STATUS_NOTACREDITO_CHOICES, default=STATUS_AGUARDANDO_CONFIRMACAO_TESOURO)
    conferencia_pi_ptres_gnd = models.BooleanField('Conferência PI/PTRES/GND', null=True)

    class Meta:
        verbose_name = 'Nota de crédito'
        verbose_name_plural = 'Notas de crédito'

    def __str__(self):
        return self.numero

    def pode_remover(self):
        user = tl.get_user()
        status_valido = self.movimentacao.status in [
            MovimentacaoCredito.STATUS_INCONSISTENTE,
            MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS,
            MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA,
        ]
        return status_valido and in_group(user, 'Gestor Orçamentário Sistêmico')

    def eh_cancelada(self):
        return self.status == NotaCredito.STATUS_CANCELADA

    def get_status(self):
        if self.status == NotaCredito.STATUS_AGUARDANDO_CONFIRMACAO_TESOURO:
            return f'<span class="status status-alert"> {self.get_status_display()} </span>'
        elif self.status == NotaCredito.STATUS_CONFIRMADA:
            return f'<span class="status status-success">{self.get_status_display()} </span>'
        elif self.status == NotaCredito.STATUS_CANCELADA:
            return f'<span class="status status-error">{self.get_status_display()} </span>'

    def get_status_pi_ptres_gnd(self):
        if self.conferencia_pi_ptres_gnd is None:
            return '<span class="status status-alert"> Aguardando validação </span>'
        elif self.conferencia_pi_ptres_gnd is True:
            return '<span class="status status-success"> Validado </span>'
        elif self.conferencia_pi_ptres_gnd is False:
            return '<span class="status status-error"> Invalidado </span>'


class NotaDotacao(models.ModelPlus):
    STATUS_AGUARDANDO_CONFIRMACAO_TESOURO = 1
    STATUS_CONFIRMADA = 2
    STATUS_CANCELADA = 3

    STATUS_NOTADOTACAO_CHOICES = (
        (STATUS_AGUARDANDO_CONFIRMACAO_TESOURO, 'Aguardando confirmação do tesouro'),
        (STATUS_CONFIRMADA, 'Confirmada'),
        (STATUS_CANCELADA, 'Cancelada'),
    )
    numero = models.CharField('Número', max_length=23)
    movimentacao = models.ForeignKeyPlus(MovimentacaoCredito, on_delete=models.CASCADE)
    unidade = models.ForeignKeyPlus(UnidadeGestora, verbose_name='Unidade gestora', null=True)
    codigo_ug = models.IntegerFieldPlus('Código UG', null=True)
    unidade_orcamentaria = models.ForeignKeyPlus(ClassificacaoInstitucional, verbose_name='Unidade orçamentária')
    ano = models.IntegerFieldPlus('Ano')
    documento_siafi = models.IntegerField('Documento SIAFI')
    valor = models.DecimalFieldPlus('Valor', null=True)
    status = models.PositiveIntegerField('Situação', choices=STATUS_NOTADOTACAO_CHOICES, default=STATUS_AGUARDANDO_CONFIRMACAO_TESOURO)
    conferencia_pi_ptres_gnd = models.BooleanField('Conferência PI/PTRES/GND', null=True)
    unidade_atendida = models.ForeignKeyPlus(UnidadeGestora, verbose_name='Unidade atendida', related_name='unidade_atendida', null=True)

    class Meta:
        verbose_name = 'Nota de dotação'
        verbose_name_plural = 'Notas de dotação'

    def __str__(self):
        return self.numero

    def get_status(self):
        if self.status == NotaDotacao.STATUS_AGUARDANDO_CONFIRMACAO_TESOURO:
            return f'<span class="status status-alert"> {self.get_status_display()} </span>'
        elif self.status == NotaDotacao.STATUS_CONFIRMADA:
            return f'<span class="status status-success">{self.get_status_display()} </span>'
        elif self.status == NotaDotacao.STATUS_CANCELADA:
            return f'<span class="status status-error">{self.get_status_display()} </span>'

    def get_status_pi_ptres_gnd(self):
        if self.conferencia_pi_ptres_gnd is None:
            return '<span class="status status-alert"> Aguardando validação </span>'
        elif self.conferencia_pi_ptres_gnd is True:
            return '<span class="status status-success"> Validado </span>'
        elif self.conferencia_pi_ptres_gnd is False:
            return '<span class="status status-error"> Invalidado </span>'

    def eh_cancelada(self):
        return self.status == NotaDotacao.STATUS_CANCELADA

    def pode_remover(self):
        user = tl.get_user()
        status_valido = self.movimentacao.status in [
            MovimentacaoCredito.STATUS_INCONSISTENTE,
            MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS,
            MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA,
        ]
        return status_valido and in_group(user, 'Gestor Orçamentário Sistêmico')


class RequisicaoDespesa(ModelPlus):
    STATUS_CADASTRADA = 1
    STATUS_AGUARDANDO_EMISSAO_CDO = 2
    STATUS_AGUARDANDO_VALIDACAO = 3
    STATUS_AGUARDANDO_AUTORIZACAO = 4
    STATUS_AUTORIZADA = 5
    STATUS_AGUARDANDO_PROCESSO_LICITATORIO = 6
    STATUS_AGUARDANDO_EMISSAO_EMPENHO = 7
    STATUS_CANCELADA = 8
    STATUS_INCONSISTENTE = 9
    STATUS_CONCLUIDA = 10
    STATUS_AGUARDANDO_ANUENCIA = 11

    STATUS_CHOICES = (
        (STATUS_CADASTRADA, 'Cadastrada'),
        (STATUS_AGUARDANDO_EMISSAO_CDO, 'Aguardando emissão do CDO'),
        (STATUS_AGUARDANDO_VALIDACAO, 'Aguardando validação do SIAFI'),
        (STATUS_AGUARDANDO_ANUENCIA, 'Aguardando anuência de despesa'),
        (STATUS_AGUARDANDO_AUTORIZACAO, 'Aguardando autorização de despesa'),
        (STATUS_AUTORIZADA, 'Despesa Autorizada'),
        (STATUS_AGUARDANDO_PROCESSO_LICITATORIO, 'Aguardando processo licitatório'),
        (STATUS_AGUARDANDO_EMISSAO_EMPENHO, 'Aguardando emissão de empenho'),
        (STATUS_CANCELADA, 'Cancelada'),
        (STATUS_INCONSISTENTE, 'Requisição com inconsistências'),
        (STATUS_CONCLUIDA, 'Concluída'),
    )
    TIPO_DOTACAO_PROVISORIA = 1
    TIPO_DOTACAO_EMPENHO = 2
    TIPO_REFORCO_EMPENHO = 3
    TIPO_ANULACAO_EMPENHO = 4

    TIPO_DESPESA_CHOICES = (
        (TIPO_DOTACAO_PROVISORIA, 'Dotação provisória'),
        (TIPO_DOTACAO_EMPENHO, 'Dotação para empenho'),
        (TIPO_REFORCO_EMPENHO, 'Reforço de empenho'),
        (TIPO_ANULACAO_EMPENHO, 'Anulação de empenho'),
    )

    FINALIDADE_LICITATORIO = 1
    FINALIDADE_CONTRATACAO_COM_PARECER = 2
    FINALIDADE_CONTRATACAO_SEM_PARECER = 3

    UA_PRINCIPAL = 1
    UA_SECUNDARIA = 2

    UA_VINCULADA_CHOICES = (
        (UA_PRINCIPAL, 'UA Principal'),
        (UA_SECUNDARIA, 'UA Secundária'),
    )

    FINALIDADE_CHOICES = (
        (FINALIDADE_LICITATORIO, 'Procedimento licitatório (Pregão ou concorrência)'),
        (FINALIDADE_CONTRATACAO_COM_PARECER, 'Contratação/Aditivo de Contrato — Com parecer jurídico referencial'),
        (FINALIDADE_CONTRATACAO_SEM_PARECER, 'Contratação/Aditivo de Contrato — Sem parecer jurídico referencial'),
    )
    data_cadastro = models.DateTimeFieldPlus('Data', auto_now_add=True)
    usuario = models.CurrentUserField(verbose_name='Cadastrado por')
    plano_atividade = models.ForeignKeyPlus('PlanoAtividade', on_delete=models.CASCADE)
    macroprocesso = models.ForeignKey(
        'ProjetoPlanoAtividade',
        verbose_name='Macroprocesso',
        related_name='macroprocesso_despesa',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    origem_recurso = models.ForeignKey(
        'OrigemRecursoProjeto',
        verbose_name='Origem de recurso',
        related_name='origemrecurso_despesa',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    plano_interno = models.ForeignKeyPlus('PlanoInternoPlanoAtividade', verbose_name='Plano interno', blank=True, on_delete=models.CASCADE, null=True)
    processo = models.ForeignKeyPlus(
        Processo, related_name='despesa_processo_set', null=True, blank=False, verbose_name='Processo', on_delete=models.CASCADE
    )
    atividade = models.ForeignKey(
        'AtividadeEtapa', verbose_name='Atividade', related_name='atividade_despesa', on_delete=models.CASCADE, null=True, blank=True
    )
    motivo_cancelamento = models.TextField('Motivo do Cancelamento', blank=True)
    tipo_requisicao = models.PositiveIntegerField('Tipo', choices=TIPO_DESPESA_CHOICES)
    numero = models.CharField(verbose_name='Nº da Requisição', max_length=12, null=True, unique=True)
    valor_inicial = models.DecimalFieldPlus('Valor inicial', null=True)
    valor_provisorio = models.DecimalFieldPlus('Valor provisório', null=True)
    valor = models.DecimalFieldPlus('Valor', null=True)
    status = models.PositiveIntegerField('Situação', choices=STATUS_CHOICES, default=STATUS_AGUARDANDO_EMISSAO_CDO)
    finalidade = models.TextField('Finalidade', blank=True)
    tipo_finalidade = models.PositiveIntegerField('Tipo de Finalidade', choices=FINALIDADE_CHOICES, null=True, blank=True)
    fonte = models.CharField(verbose_name='Fonte', max_length=10, null=True)
    unidade_gestora = models.ForeignKey(
        'UnidadeGestora', verbose_name='Unidade Gestora', related_name='unidade_gestora', on_delete=models.CASCADE, null=True, blank=True
    )
    ua_vinculada = models.PositiveSmallIntegerField('Despesa vinculada à', choices=UA_VINCULADA_CHOICES, default=UA_PRINCIPAL)

    # Requisição provisória
    cdo_provisorio = models.ForeignKeyPlus(DocumentoTexto, verbose_name='Documento CDO provisório', null=True, related_name='cdo_provisorio')
    despacho_autorizacao_provisoria = models.TextField('Despacho de autorização da despesa provisória', null=True, blank=True)
    vinculo_autorizacao_provisoria = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autorizador da despesa provisória', null=True, related_name='vinculo_autorizacao_despesa_provisoria'
    )
    data_autorizacao_provisoria = models.DateTimeFieldPlus('Data de autorização da despesa provisória', null=True)

    # Requisição de empenho
    cdo = models.ForeignKeyPlus(DocumentoTexto, verbose_name='Documento CDO', null=True, related_name='cdo')
    despacho_autorizacao_despesa = models.TextField('Despacho de autorização da despesa', null=True, blank=True)
    vinculo_autorizacao_despesa = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autorizador da despesa provisória', null=True, related_name='vinculo_autorizacao_despesa'
    )
    data_autorizacao_despesa = models.DateTimeFieldPlus('Data de autorização da despesa', null=True)
    autorizacao_ordenador_declarada_no_processo = models.BooleanField(
        'Autorização do ordenador declarada no processo',
        default=False,
        help_text=(
            'Indica que o operador declarou que a autorização do ordenador já consta no processo administrativo vinculado, não sendo realizada diretamente nesta RD.'
        ),
    )

    # Anuência da despesa
    despacho_anuencia = models.TextField('Despacho de anuência da despesa', null=True, blank=True)
    vinculo_anuencia = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Anuente da despesa', null=True, related_name='vinculo_anuencia_despesa')
    data_anuencia = models.DateTimeFieldPlus('Data de anuência da despesa', null=True)

    class Meta:
        verbose_name = 'Requisição de despesa'
        verbose_name_plural = 'Requisições de despesas'

    def get_absolute_url(self):
        return f'/plan_estrategico/detalhar_requisicaodespesa/{self.pk}/'

    @property
    def eh_tipo_reforco(self):
        return self.tipo_requisicao == RequisicaoDespesa.TIPO_REFORCO_EMPENHO

    @property
    def eh_tipo_anulacao(self):
        return self.tipo_requisicao == RequisicaoDespesa.TIPO_ANULACAO_EMPENHO

    @staticmethod
    def get_proximo_numero_requisicao(ano_planoatividade):
        """Obtém o próximo número disponível para a requisição"""
        with transaction.atomic():
            ultimo_numero = (RequisicaoDespesa.objects.filter(numero__startswith=f'{ano_planoatividade}RD').aggregate(Max('numero')))['numero__max']

            if ultimo_numero:
                ultimo_sequencial = int(ultimo_numero[-6:])
            else:
                ultimo_sequencial = 0

            novo_sequencial = str(ultimo_sequencial + 1).zfill(6)
            numero = f'{ano_planoatividade}RD{novo_sequencial}'

        return numero

    def pode_emitir_cdo_provisorio(self):
        user = tl.get_user()

        return (
            self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO
            and self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA
            and (in_group(user, 'Gestor Orçamentário de UA') or in_group(user, 'Gestor Orçamentário Sistêmico'))
            and self.unidade_gestora.setor_administrativo.sigla == user.get_vinculo().relacionamento.setor.sigla
        )

    def pode_adicionar_natureza_despesa(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        valor_requisicao = self.valor_inicial
        if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA:
            valor_requisicao = self.valor_provisorio
        saldo = valor_requisicao - self.total_naturezas_despesa()
        return (
            self.status == RequisicaoDespesa.STATUS_CADASTRADA
            and (in_group(user, 'Gestor de UA') or in_group(user, 'Coordenador de UA'))
            and self.unidade_gestora.setor_equivalente.sigla == get_setor_unidade_gestora(user=user).sigla
            and saldo > 0
        )

    def pode_encaminhar_para_emissao_cdo(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        valor_requisicao = self.valor_inicial
        if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA:
            valor_requisicao = self.valor_provisorio
        return (
            self.status == RequisicaoDespesa.STATUS_CADASTRADA
            and (in_group(user, 'Gestor de UA') or in_group(user, 'Coordenador de UA'))
            and self.unidade_gestora.setor_equivalente.sigla == get_setor_unidade_gestora(user=user).sigla
            and valor_requisicao == self.total_naturezas_despesa()
        )

    def pode_emitir_cdo(self):
        user = tl.get_user()
        return (
            self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO
            and (self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO or self.tipo_requisicao == RequisicaoDespesa.TIPO_REFORCO_EMPENHO)
            and (in_group(user, 'Gestor Orçamentário de UA') or in_group(user, 'Gestor Orçamentário Sistêmico'))
            and self.unidade_gestora.setor_administrativo.sigla == user.get_vinculo().relacionamento.setor.sigla
        )

    def pode_converter_para_empenho(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        return (
            self.status == RequisicaoDespesa.STATUS_CONCLUIDA
            and (in_group(user, 'Gestor Orçamentário de UA'))
            and self.atividade.unidade_gestora.setor_equivalente == get_setor_unidade_gestora(user=user)
        )

    def pode_emitir_empenho(self):
        user = tl.get_user()
        return (
            (self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO or self.status == RequisicaoDespesa.STATUS_INCONSISTENTE)
            and (in_group(user, 'Executor Orçamentário'))
            and self.unidade_gestora.setor_financeiro.sigla == user.get_vinculo().relacionamento.setor.sigla
        )

    def pode_editar_empenho(self) -> bool:
        """Indica se o número do empenho/RO já registrado pode ser corrigido.

        Além do fluxo de emissão, a correção é permitida enquanto a requisição aguarda a validação do
        SIAFI, situação em que um número informado incorretamente impede a conferência com o tesouro.

        Returns:
            bool: True se o executor orçamentário do setor financeiro da unidade gestora pode editar o empenho/RO.
        """
        if self.pode_emitir_empenho():
            return True

        user = tl.get_user()
        return bool(
            self.status == RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO
            and in_group(user, 'Executor Orçamentário')
            and self.unidade_gestora.setor_financeiro
            and self.unidade_gestora.setor_financeiro.sigla == user.get_vinculo().relacionamento.setor.sigla
        )

    @property
    def eh_ua_secundaria(self):
        return self.ua_vinculada == RequisicaoDespesa.UA_SECUNDARIA

    def precisa_anuencia(self) -> bool:
        """A despesa passa por anuência quando vinculada à UA secundária ou quando a UA não tem Diretor-Geral.

        Sem Setor Anuência da Despesa cadastrado na unidade gestora, não há anuência e o processo segue direto para autorização.
        """
        if not self.unidade_gestora.setor_anuencia_despesa_id:
            return False
        return self.eh_ua_secundaria or not self.unidade_gestora.possui_diretor_geral()

    def get_unidade_gestora_autorizadora(self):
        """Unidade gestora cujo ordenador autoriza a despesa: a UG secundária, se a despesa for vinculada a ela."""
        if self.eh_ua_secundaria:
            return self.unidade_gestora.get_ug_secundaria()
        return self.unidade_gestora

    def get_setor_destino_autorizacao(self):
        unidade_gestora = self.get_unidade_gestora_autorizadora()
        return unidade_gestora.setor_ordenador_despesa if unidade_gestora else None

    def get_setor_destino_apos_cdo(self):
        """Setor para onde o processo tramita após o CDO: anuência da despesa, se precisar, senão o ordenador de despesa."""
        if self.precisa_anuencia():
            return self.unidade_gestora.setor_anuencia_despesa
        return self.get_setor_destino_autorizacao()

    def get_status_apos_cdo(self) -> int:
        if self.precisa_anuencia():
            return RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA
        return RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO

    def pode_anuir_despesa(self):
        user = tl.get_user()
        return self.status == RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA and self.unidade_gestora.eh_diretor(user)

    def pode_avaliar_despesa(self):
        user = tl.get_user()
        unidade_gestora = self.get_unidade_gestora_autorizadora()
        if self.status != RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO or not unidade_gestora:
            return False
        ordenadores_despesa = unidade_gestora.setor_equivalente.uo.get_diretor_geral()
        usuario_eh_ordenador = user.get_vinculo().relacionamento in ordenadores_despesa
        return bool(
            usuario_eh_ordenador
            and (
                unidade_gestora.setor_equivalente.uo.sigla == user.get_vinculo().relacionamento.setor.uo.sigla
                or unidade_gestora.setor_equivalente.superior.uo.sigla == user.get_vinculo().relacionamento.setor.uo.sigla
            )
        )

    def pode_editar_natureza_despesa(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        valor_requisicao = self.valor_inicial
        if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA:
            valor_requisicao = self.valor_provisorio
        saldo = valor_requisicao - self.total_naturezas_despesa()
        return (
            self.status == RequisicaoDespesa.STATUS_CADASTRADA
            and (in_group(user, 'Gestor de UA') or in_group(user, 'Coordenador de UA'))
            and self.unidade_gestora.setor_equivalente.sigla == get_setor_unidade_gestora(user=user).sigla
            and saldo >= 0
        )

    def pode_encaminhar_validacao_siafi(self):
        user = tl.get_user()
        eh_executor_orcamentario = in_group(user, 'Executor Orçamentário')
        mesma_sigla = (
            self.unidade_gestora.setor_financeiro and self.unidade_gestora.setor_financeiro.sigla == user.get_vinculo().relacionamento.setor.sigla
        )
        aguardando_emissao = self.status in (RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO, RequisicaoDespesa.STATUS_INCONSISTENTE)

        if not (eh_executor_orcamentario and mesma_sigla and aguardando_emissao):
            return False

        if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO:
            return not NotaEmpenho.objects.filter(requisicao=self).exclude(numero_empenho__isnull=False).exists()

        if self.tipo_requisicao in [RequisicaoDespesa.TIPO_REFORCO_EMPENHO, RequisicaoDespesa.TIPO_ANULACAO_EMPENHO]:
            return not NotaEmpenho.objects.filter(requisicao=self).exclude(numero_ro__isnull=False).exists()

        return False

    def pode_cancelar_dotacao_provisoria(self):
        from plan_estrategico.utils import get_setor_unidade_gestora

        user = tl.get_user()
        # if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO:
        #    return (self.status in [RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO, RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO]
        #            and (in_group(user, 'Gestor Orçamentário de UA')) and self.atividade.unidade_gestora.setor_equivalente == get_setor_unidade_gestora(user=user))
        eh_gestor_orcamentario = in_group(user, 'Gestor Orçamentário de UA') or in_group(user, 'Gestor Orçamentário Sistêmico')
        if self.atividade.unidade_gestora.setor_administrativo:
            eh_setor_administrativo = self.atividade.unidade_gestora.setor_administrativo.sigla == user.get_vinculo().relacionamento.setor.sigla
        else:
            eh_setor_administrativo = False
        return (
            (self.status == RequisicaoDespesa.STATUS_CONCLUIDA and (in_group(user, 'Administrador de Planejamento Estratégico')))
            or (
                self.status == RequisicaoDespesa.STATUS_CADASTRADA
                and (in_group(user, 'Gestor UA') or in_group(user, 'Coordenador de UA'))
                and self.atividade.unidade_gestora.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
            or (
                (
                    self.status
                    in [
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
                    ]
                )
                and (in_group(user, 'Gestor UA') or in_group(user, 'Coordenador de UA'))
                and self.atividade.unidade_gestora.setor_equivalente == get_setor_unidade_gestora(user=user)
            )
            or (
                (
                    self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
                    or self.status == RequisicaoDespesa.STATUS_INCONSISTENTE
                    or self.status == RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO
                )
                and (in_group(user, 'Executor Orçamentário'))
                and self.atividade.unidade_gestora.setor_financeiro.sigla == user.get_vinculo().relacionamento.setor.sigla
            )
            or (
                self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
                and (in_group(user, 'Executor Orçamentário'))
                and self.atividade.unidade_gestora.setor_financeiro.sigla == user.get_vinculo().relacionamento.setor.sigla
            )
            or (self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO and eh_gestor_orcamentario and eh_setor_administrativo)
            or (self.status == RequisicaoDespesa.STATUS_AGUARDANDO_PROCESSO_LICITATORIO and eh_gestor_orcamentario and eh_setor_administrativo)
            or self.pode_avaliar_despesa()
        )

    def pode_gerar_despesa_definitiva(self):
        user = tl.get_user()
        eh_gestor_orcamentario = in_group(user, 'Gestor Orçamentário de UA') or in_group(user, 'Gestor Orçamentário Sistêmico')
        if self.atividade.unidade_gestora.setor_administrativo:
            eh_setor_administrativo = self.atividade.unidade_gestora.setor_administrativo.sigla == user.get_vinculo().relacionamento.setor.sigla
        else:
            eh_setor_administrativo = False
        return (
            self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA
            and self.status == RequisicaoDespesa.STATUS_AGUARDANDO_PROCESSO_LICITATORIO
            and eh_gestor_orcamentario
            and eh_setor_administrativo
        )

    def total_naturezas_despesa(self):
        return NotaEmpenho.objects.filter(requisicao=self).aggregate(Sum('valor')).get('valor__sum') or Decimal(0)

    def get_status(self):
        if self.status == RequisicaoDespesa.STATUS_CADASTRADA:
            return f'<span class="status status-info"> {self.get_status_display()} </span>'
        elif self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO:
            return f'<span class="status status-alert"> {self.get_status_display()} </span>'
        elif (
            self.status == RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO
            or self.status == RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA
            or self.status == RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO
            or self.status == RequisicaoDespesa.STATUS_AGUARDANDO_PROCESSO_LICITATORIO
            or self.status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
        ):
            return f'<span class="status status-alert">{self.get_status_display()} </span>'
        elif self.status == RequisicaoDespesa.STATUS_CANCELADA or self.status == RequisicaoDespesa.STATUS_INCONSISTENTE:
            return f'<span class="status status-cancelado">{self.get_status_display()} </span>'
        elif self.status == RequisicaoDespesa.STATUS_CONCLUIDA:
            return f'<span class="status status-success">{self.get_status_display()} </span>'

    def atualizar_valor_total(self, commit=True):
        self.valor = self.total_naturezas_despesa()
        if commit:
            self.save(update_fields=['valor'])

    @transaction.atomic()
    def cancelar_requisicaodespesa(self, user):
        for empenho in self.empenhos.all():
            empenho.status = NotaEmpenho.STATUS_CANCELADA
            empenho.save()
        self.status = RequisicaoDespesa.STATUS_CANCELADA
        self.save()
        RequisicaoDespesaHistorico.objects.create(despesa=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

    def get_cdo_provisorio_html(self, despacho):
        return render_to_string('doc_cdo_provisorio.html', {'requisicao_despesa': self, 'despacho': despacho})

    def get_cdo_empenho_html(self, despacho):
        return render_to_string('doc_cdo_empenho.html', {'requisicao_despesa': self, 'despacho': despacho})

    def gerar_documento_requisicao(self, request):
        tipo_documento_requisicao_despesa = TipoDocumento.objects.get(
            pk=Configuracao.get_valor_por_chave('plan_estrategico', 'tipo_documento_requisicao_despesa')
        )

        title = f'Requisição Nº {self.numero}'
        html = render_to_string(
            'plan_estrategico/templates/detalhar_requisicaodespesa_documento.html',
            {
                'requisicao_despesa': self,
                'title': title,
                'request': request,
                'historico_requisicaodespesa': RequisicaoDespesaHistorico.objects.filter(despesa=self),
            },
        )
        documento_digitalizado_requisicao = DocumentoDigitalizado.criar(
            file_content=html.encode('utf-8'),
            file_name='requisicaodespesa.html',
            tipo_documento=tipo_documento_requisicao_despesa,
            assunto=title,
            user=request.user,
            papel=request.user.get_relacionamento().papeis_ativos.first(),
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
        )
        self.processo.adicionar_documento_digitalizado(documento_digitalizado_requisicao)

    def cancelar_documento_requisicao(self, request):
        tipo_documento_requisicao_despesa = TipoDocumento.objects.get(
            pk=Configuracao.get_valor_por_chave('plan_estrategico', 'tipo_documento_requisicao_despesa')
        )

        title = f'Cancelamento da Requisição Nº {self.numero}'
        html = render_to_string(
            'plan_estrategico/templates/detalhar_requisicaodespesa_cancelamento.html',
            {
                'requisicao_despesa': self,
                'title': title,
                'request': request,
                'historico_requisicaodespesa': RequisicaoDespesaHistorico.objects.filter(despesa=self),
            },
        )
        documento_digitalizado_requisicao = DocumentoDigitalizado.criar(
            file_content=html.encode('utf-8'),
            file_name='requisicaodespesa_cancelamento.html',
            tipo_documento=tipo_documento_requisicao_despesa,
            assunto=title,
            user=request.user,
            papel=request.user.get_relacionamento().papeis_ativos.first(),
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
        )
        self.processo.adicionar_documento_digitalizado(documento_digitalizado_requisicao)

    def gerar_documento_requisicao_empenho(self, request):
        tipo_documento_requisicao_despesa = TipoDocumento.objects.get(
            pk=Configuracao.get_valor_por_chave('plan_estrategico', 'tipo_documento_requisicao_despesa')
        )

        title = f'Requisição Nº {self.numero}'
        html = render_to_string(
            'plan_estrategico/templates/detalhar_requisicaodespesa_empenho_documento.html',
            {
                'requisicao_despesa': self,
                'title': title,
                'request': request,
                'historico_requisicaodespesa': RequisicaoDespesaHistorico.objects.filter(despesa=self),
            },
        )
        documento_digitalizado_requisicao = DocumentoDigitalizado.criar(
            file_content=html.encode('utf-8'),
            file_name='requisicaodespesa.html',
            tipo_documento=tipo_documento_requisicao_despesa,
            assunto=title,
            user=request.user,
            papel=request.user.get_relacionamento().papeis_ativos.first(),
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
        )
        self.processo.adicionar_documento_digitalizado(documento_digitalizado_requisicao)

    def pode_ver_status_empenho(self):
        return (
            self.status in (self.STATUS_AGUARDANDO_VALIDACAO, self.STATUS_INCONSISTENTE, self.STATUS_CONCLUIDA, self.STATUS_CANCELADA)
            and self.empenhos.filter(numero_empenho__isnull=False).exists()
        )

    def eh_linha_reforco(self, empenho_plan):
        """Indica se a linha é um reforço lançado sobre o empenho de uma requisição de dotação.

        Numa requisição de dotação a linha nasce sem RO; o RO só é preenchido pelo reforço
        vinculado ao empenho já emitido. Nos demais tipos de requisição a classificação continua
        sendo dada pelo próprio tipo.

        Returns:
            bool: True se a linha representa um reforço dentro de uma requisição de dotação.
        """
        return self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO and bool(empenho_plan.numero_ro)

    def get_numero_documento_tesouro(self, empenho_plan):
        """Número do documento do tesouro que confere a linha: o RO do reforço ou a nota de empenho.

        Returns:
            str: Número a procurar no tesouro, ou None quando o tipo da requisição não confere.
        """
        if self.eh_linha_reforco(empenho_plan):
            return empenho_plan.numero_ro
        if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO:
            return empenho_plan.numero_empenho
        if self.tipo_requisicao in (RequisicaoDespesa.TIPO_REFORCO_EMPENHO, RequisicaoDespesa.TIPO_ANULACAO_EMPENHO):
            return empenho_plan.numero_ro
        return None

    def get_documento_empenho_tesouro(self, empenho_plan):
        numero = self.get_numero_documento_tesouro(empenho_plan)
        if not numero:
            return None
        empenho_tesouro = DocumentoEmpenho.objects.filter(numero=numero)
        if not empenho_tesouro.exists():
            return None
        return empenho_tesouro.first()

    def get_documentos_empenho_tesouro(self):
        numeros = [numero for numero in (self.get_numero_documento_tesouro(empenho) for empenho in self.empenhos.all()) if numero]
        return DocumentoEmpenho.objects.filter(numero__in=numeros)

    def get_evento_empenho_tesouro(self):
        evento_empenho_tesouro = None
        if self.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO:
            evento_empenho_tesouro = EventoNotaEmpenho.INCLUSAO
        elif self.tipo_requisicao == RequisicaoDespesa.TIPO_REFORCO_EMPENHO:
            evento_empenho_tesouro = EventoNotaEmpenho.REFORCO
        elif self.tipo_requisicao == RequisicaoDespesa.TIPO_ANULACAO_EMPENHO:
            evento_empenho_tesouro = EventoNotaEmpenho.ANULACAO
        return evento_empenho_tesouro

    def get_valor_documento_empenho_tesouro(self, empenho_tesouro, empenho_plan=None):
        """Valor que o tesouro registra para o documento que confere a linha.

        O reforço lançado dentro de uma requisição de dotação é conferido pelo evento de reforço,
        e não pelo evento do tipo da requisição, por isso a linha precisa ser informada.

        Returns:
            Decimal: Soma dos itens do documento para o evento correspondente.
        """
        eh_reforco_em_dotacao = empenho_plan is not None and self.eh_linha_reforco(empenho_plan)
        if eh_reforco_em_dotacao:
            evento_empenho_tesouro = EventoNotaEmpenho.REFORCO
        else:
            evento_empenho_tesouro = self.get_evento_empenho_tesouro()

        empenhos = DocumentoEmpenhoItem.objects.filter(
            evento__codigo=evento_empenho_tesouro,
        )

        if eh_reforco_em_dotacao or self.tipo_requisicao in (
            RequisicaoDespesa.TIPO_REFORCO_EMPENHO,
            RequisicaoDespesa.TIPO_ANULACAO_EMPENHO,
        ):
            empenhos = empenhos.filter(documento_empenho=empenho_tesouro)
        else:
            empenhos = empenhos.filter(documento_empenho__documento_empenho_inicial=empenho_tesouro)

        return empenhos.aggregate(Sum('valor')).get('valor__sum') or Decimal(0)

    def validar_requisicao(self):
        if self.status != self.STATUS_AGUARDANDO_VALIDACAO:
            return
        ultima_data_historico = RequisicaoDespesaHistorico.objects.filter(despesa=self).order_by('-id')[0].alterado_em
        diferenca_tempo = timezone.now() - ultima_data_historico
        empenhos_plan = self.empenhos.all()
        empenhos_tesouro = self.get_documentos_empenho_tesouro()
        if diferenca_tempo < timedelta(days=5) and empenhos_plan.count() != empenhos_tesouro.count():
            return

        requisicao_validada = True
        valor_total_empenho = Decimal(0)
        for empenho_plan in self.empenhos.all():
            empenho_tesouro = self.get_documento_empenho_tesouro(empenho_plan)
            if empenho_tesouro is None:
                requisicao_validada = False
                continue

            valor_empenho_tesouro = self.get_valor_documento_empenho_tesouro(empenho_tesouro, empenho_plan)

            if empenho_plan.valor == valor_empenho_tesouro:
                empenho_plan.conferencia_valor = True
            else:
                empenho_plan.conferencia_valor = False

            gnd_empenho = empenho_plan.naturezadespesa.natureza_despesa.grupo_natureza_despesa.codigo
            if gnd_empenho == empenho_tesouro.grupo_despesa_original:
                empenho_plan.conferencia_gnd = True
            else:
                empenho_plan.conferencia_gnd = False

            if self.plano_interno.plano_interno.ptres.codigo == empenho_tesouro.ptres.codigo:
                empenho_plan.conferencia_ptres = True
            else:
                empenho_plan.conferencia_ptres = False

            if self.plano_interno.plano_interno.codigo == empenho_tesouro.plano_interno.codigo:
                empenho_plan.conferencia_pi = True
            else:
                empenho_plan.conferencia_pi = False

            if empenho_plan.conferencia_valor and empenho_plan.conferencia_gnd and empenho_plan.conferencia_ptres and empenho_plan.conferencia_pi:
                empenho_plan.status = NotaEmpenho.STATUS_CONFIRMADA
                requisicao_validada = requisicao_validada and True
            else:
                empenho_plan.status = NotaEmpenho.STATUS_INCONSISTENTE
                requisicao_validada = requisicao_validada and False

            empenho_plan.save()
            valor_total_empenho += valor_empenho_tesouro

        if self.valor != valor_total_empenho:
            requisicao_validada = False

        empenhos_total = self.empenhos.count()
        empenhos_processados = sum(1 for e in self.empenhos.all() if self.get_documento_empenho_tesouro(e) is not None)
        if empenhos_total == empenhos_processados:
            if requisicao_validada:
                self.status = RequisicaoDespesa.STATUS_CONCLUIDA
            else:
                self.status = RequisicaoDespesa.STATUS_INCONSISTENTE
        else:
            if diferenca_tempo >= timedelta(days=5):
                self.status = RequisicaoDespesa.STATUS_INCONSISTENTE

        RequisicaoDespesaHistorico.objects.create(despesa=self, status=self.status)
        self.save()


class RequisicaoDespesaHistorico(models.ModelPlus):
    despesa = models.ForeignKeyPlus(RequisicaoDespesa, on_delete=models.CASCADE)
    status = models.PositiveIntegerField(choices=RequisicaoDespesa.STATUS_CHOICES)
    alterado_em = models.DateTimeField(auto_now_add=True)
    alterado_por = models.CurrentUserField()

    class Meta:
        ordering = ('alterado_em',)
        verbose_name = 'Histórico de requisição de despesa'
        verbose_name_plural = 'Históricos de requisições de despesas'

    def get_status(self):
        self.despesa.status = self.status
        return self.despesa.get_status()

    def get_status_class(self):
        status = self.status
        if status == RequisicaoDespesa.STATUS_CONCLUIDA:
            return 'success'
        elif status == RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO:
            return 'warning'
        elif status == RequisicaoDespesa.STATUS_CANCELADA:
            return 'error'
        elif status == RequisicaoDespesa.STATUS_CADASTRADA:
            return 'info'
        elif status == RequisicaoDespesa.STATUS_INCONSISTENTE:
            return 'danger'
        else:
            return 'warning'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class NotaEmpenho(models.ModelPlus):
    STATUS_AGUARDANDO_CONFIRMACAO_TESOURO = 1
    STATUS_CONFIRMADA = 2
    STATUS_INCONSISTENTE = 3
    STATUS_CANCELADA = 4

    STATUS_NOTADOTACAO_CHOICES = (
        (STATUS_AGUARDANDO_CONFIRMACAO_TESOURO, 'Aguardando confirmação do tesouro'),
        (STATUS_CONFIRMADA, 'Confirmada'),
        (STATUS_INCONSISTENTE, 'Inconsistente'),
        (STATUS_CANCELADA, 'Cancelada'),
    )
    numero_empenho = models.CharField('Número do empenho', max_length=23, null=True)
    numero_ro = models.CharField('Número do RO', max_length=23, null=True)
    requisicao = models.ForeignKeyPlus(RequisicaoDespesa, on_delete=models.CASCADE, related_name='empenhos')
    unidade = models.ForeignKeyPlus(UnidadeGestora, verbose_name='Unidade gestora', null=True)
    codigo_ug = models.IntegerFieldPlus('Código UG', null=True)
    unidade_orcamentaria = models.ForeignKeyPlus(ClassificacaoInstitucional, verbose_name='Unidade orçamentária', null=True)
    ano = models.IntegerFieldPlus('Ano', null=True)
    documento_siafi = models.IntegerField('Documento SIAFI', null=True)
    valor = models.DecimalFieldPlus('Valor', null=True)
    status = models.PositiveIntegerField('Situação', choices=STATUS_NOTADOTACAO_CHOICES, default=STATUS_AGUARDANDO_CONFIRMACAO_TESOURO)
    naturezadespesa = models.ForeignKeyPlus(
        'NaturezaDespesaPlanoAtividade', verbose_name='Natureza de Despesa', blank=True, on_delete=models.CASCADE, null=True
    )
    conferencia_valor = models.BooleanField(null=True, default=None)
    conferencia_gnd = models.BooleanField(null=True, default=None)
    conferencia_ptres = models.BooleanField(null=True, default=None)
    conferencia_pi = models.BooleanField(null=True, default=None)

    class Meta:
        verbose_name = 'Nota de empenho'
        verbose_name_plural = 'Notas de empenhos'

    def __str__(self):
        return f'{self.numero_empenho}'

    def get_status(self):
        if self.status == NotaEmpenho.STATUS_AGUARDANDO_CONFIRMACAO_TESOURO:
            return f'<span class="status status-alert"> {self.get_status_display()} </span>'
        elif self.status == NotaEmpenho.STATUS_CONFIRMADA:
            return f'<span class="status status-success">{self.get_status_display()} </span>'
        elif self.status == NotaEmpenho.STATUS_INCONSISTENTE or self.status == NotaEmpenho.STATUS_CANCELADA:
            return f'<span class="status status-error">{self.get_status_display()} </span>'

    def get_status_conferencia(self):
        conferencias = []
        if not self.conferencia_valor:
            conferencias.append('Valor')
        if not self.conferencia_gnd:
            conferencias.append('GND')
        if not self.conferencia_ptres:
            conferencias.append('PTRES')
        if not self.conferencia_pi:
            conferencias.append('PI')

        if conferencias:
            return f'<span class="status status-error">{format_iterable(conferencias)} inconsistente{defaultfilters.pluralize(conferencias)}</span>'

    def pode_remover(self):
        user = tl.get_user()
        status_valido = self.requisicao.status in [
            RequisicaoDespesa.STATUS_CADASTRADA,
            RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
            RequisicaoDespesa.STATUS_INCONSISTENTE,
        ]
        grupos_permitidos = ['Gestor de UA', 'Coordenador de UA', 'Executor Orçamentário']
        usuario_autorizado = in_group(user, grupos_permitidos)

        return status_valido and usuario_autorizado

    def pode_remover_reforco(self):
        return self.requisicao.tipo_requisicao != RequisicaoDespesa.TIPO_REFORCO_EMPENHO or self != self.requisicao.empenhos.order_by('id').first()

    def pode_reforcar(self):
        """Indica se esta linha permite vincular um reforço ao empenho já emitido.

        O vínculo é oferecido apenas na linha do empenho de uma requisição de dotação, nunca em
        outra linha de reforço, e na mesma janela da edição do empenho: etapa de emissão ou
        enquanto a requisição aguarda a validação do SIAFI.

        Returns:
            bool: True se um reforço pode ser vinculado a partir desta linha.
        """
        return bool(
            self.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO
            and self.numero_empenho
            and not self.numero_ro
            and self.requisicao.pode_editar_empenho()
        )

    @classmethod
    def get_total_empenhado(cls, numero_empenho):
        return cls.objects.filter(
            numero_empenho=numero_empenho,
            numero_ro__isnull=True,
            requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
            requisicao__status=RequisicaoDespesa.STATUS_CONCLUIDA,
        ).exclude(status=cls.STATUS_CANCELADA).aggregate(total=Sum('valor'))['total'] or Decimal(0)

    @classmethod
    def get_total_reforco_empenho(cls, numero_empenho):
        """Soma dos reforços do empenho, seja na requisição de reforço, seja na requisição de dotação."""
        return cls.objects.filter(
            Q(requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_REFORCO_EMPENHO)
            | Q(requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO, numero_ro__isnull=False),
            numero_empenho=numero_empenho,
            requisicao__status=RequisicaoDespesa.STATUS_CONCLUIDA,
        ).exclude(status=cls.STATUS_CANCELADA).aggregate(total=Sum('valor'))['total'] or Decimal(0)

    @classmethod
    def get_total_anulado(cls, numero_empenho):
        return cls.objects.filter(
            numero_empenho=numero_empenho,
            requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_ANULACAO_EMPENHO,
        ).exclude(status=cls.STATUS_CANCELADA).aggregate(total=Sum('valor'))['total'] or Decimal(0)

    @staticmethod
    def get_documentos_empenho_do_plano(plano_atividade, codigos_ug=None):
        """Documentos de empenho do SIAFI no escopo do plano: ano, UGs emitentes, planos internos do plano e UO da instituição."""
        if codigos_ug is None:
            codigos_ug = UnidadeGestora.objects.filter(pdi=plano_atividade.pdi).exclude(codigo_ug='').values('codigo_ug')
        codigos_pi = PlanoInternoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).values('plano_interno__codigo')
        documentos = DocumentoEmpenho.objects.filter(
            data_emissao__year=plano_atividade.ano_base.ano,
            emitente_ug__codigo__in=codigos_ug,
            plano_interno__codigo__in=codigos_pi,
        )
        codigo_unidade_orcamentaria = Configuracao.get_valor_por_chave('plan_estrategico', 'codigo_unidade_orcamentaria')
        if codigo_unidade_orcamentaria:
            documentos = documentos.filter(unidade_orcamentaria__codigo=codigo_unidade_orcamentaria)
        return documentos

    @classmethod
    def get_empenhos_sem_requisicao(cls, plano_atividade, codigos_ug=None):
        """Documentos de empenho do SIAFI que nenhuma requisição de despesa informou."""
        notas = cls.objects.exclude(status=cls.STATUS_CANCELADA)
        numeros_ne = notas.filter(numero_empenho__isnull=False).values('numero_empenho')
        numeros_ro = notas.filter(numero_ro__isnull=False).values('numero_ro')
        reforco, anulacao = str(EventoNotaEmpenho.REFORCO), str(EventoNotaEmpenho.ANULACAO)
        itens = DocumentoEmpenhoItem.objects.filter(documento_empenho=OuterRef('pk'))
        itens_reforco_anulacao = itens.filter(evento__codigo__in=[reforco, anulacao])
        itens_inclusao = itens.filter(evento__codigo=str(EventoNotaEmpenho.INCLUSAO))
        documentos = (
            cls.get_documentos_empenho_do_plano(plano_atividade, codigos_ug)
            .annotate(
                evento_ro=Subquery(itens_reforco_anulacao.values('evento__codigo')[:1]),
                inclusao=Exists(itens_inclusao),
                tem_itens=Exists(itens),
                numero_empenho=Coalesce('documento_empenho_inicial__numero', 'numero'),
            )
            .filter(
                (Q(tipo=DocumentoEmpenho.TIPO_NE, tem_itens=True) & ~Q(numero__in=numeros_ne))
                | (Q(tipo=DocumentoEmpenho.TIPO_RO, inclusao=True) & ~Q(numero_empenho__in=numeros_ne) & ~Q(numero__in=numeros_ro))
                | (Q(tipo=DocumentoEmpenho.TIPO_RO, evento_ro__isnull=False) & ~Q(numero__in=numeros_ro))
            )
        )
        ids = cls.excluir_empenhos_zerados_sem_requisicao(documentos, numeros_ne, numeros_ro)
        return (
            DocumentoEmpenho.objects.filter(pk__in=ids)
            .annotate(numero_empenho=Coalesce('documento_empenho_inicial__numero', 'numero'))
            .select_related('emitente_ug', 'plano_interno', 'documento_empenho_inicial')
            .order_by('data_emissao', 'numero')
        )

    @staticmethod
    def excluir_empenhos_zerados_sem_requisicao(documentos, numeros_ne, numeros_ro):
        """Ids dos documentos sem requisição que restam ao remover os que se compensam e não têm o que regularizar."""
        empenho_por_documento = dict(documentos.values_list('pk', 'numero_empenho'))
        empenhos = set(empenho_por_documento.values())
        empenhos_zerados = NotaEmpenho.get_empenhos_com_saldo_zero(empenhos)
        empenhos_zerados -= NotaEmpenho.get_empenhos_em_requisicao(empenhos_zerados, numeros_ne, numeros_ro)
        saldo_sem_requisicao = defaultdict(Decimal)
        itens = DocumentoEmpenhoItem.objects.filter(documento_empenho__in=empenho_por_documento).values_list('documento_empenho', 'valor')
        for documento_id, valor in itens:
            saldo_sem_requisicao[empenho_por_documento[documento_id]] += valor
        ocorrencias_zeradas = {numero for numero, saldo in saldo_sem_requisicao.items() if saldo == 0}
        excluidos = empenhos_zerados | ocorrencias_zeradas
        return [pk for pk, numero in empenho_por_documento.items() if numero not in excluidos]

    @staticmethod
    def get_empenhos_com_saldo_zero(empenhos):
        """Números das NEs, dentre ``empenhos``, cujo saldo (itens da NE e de todos os seus ROs, de qualquer ano) é zero."""
        saldos = (
            DocumentoEmpenhoItem.objects.filter(
                Q(documento_empenho__numero__in=empenhos) | Q(documento_empenho__documento_empenho_inicial__numero__in=empenhos)
            )
            .annotate(numero_empenho=Coalesce('documento_empenho__documento_empenho_inicial__numero', 'documento_empenho__numero'))
            .values('numero_empenho')
            .annotate(saldo=Sum('valor'))
            .filter(saldo=0)
        )
        return set(saldos.values_list('numero_empenho', flat=True))

    @staticmethod
    def get_empenhos_em_requisicao(empenhos, numeros_ne, numeros_ro):
        """Números das NEs, dentre ``empenhos``, informados em requisição: pela própria NE ou por um dos seus ROs."""
        if not empenhos:
            return set()
        pela_ne = numeros_ne.filter(numero_empenho__in=empenhos).values_list('numero_empenho', flat=True)
        pelo_ro = DocumentoEmpenho.objects.filter(numero__in=numeros_ro, documento_empenho_inicial__numero__in=empenhos).values_list(
            'documento_empenho_inicial__numero', flat=True
        )
        return set(pela_ne) | set(pelo_ro)

    @classmethod
    def get_registros_empenhos_sem_requisicao(cls, plano_atividade, codigos_ug=None):
        """Registros (itens) dos documentos de empenho sem requisição, cada um com o próprio valor e evento."""
        documentos = cls.get_empenhos_sem_requisicao(plano_atividade, codigos_ug)
        macroprocesso = PlanoInternoPlanoAtividade.objects.filter(
            plano_atividade=plano_atividade, plano_interno__codigo=OuterRef('documento_empenho__plano_interno__codigo')
        ).annotate(
            descricao_macroprocesso=Concat('plano_interno__projeto_estrategico__codigo', Value('-'), 'plano_interno__projeto_estrategico__nome')
        )
        return (
            DocumentoEmpenhoItem.objects.filter(documento_empenho__in=documentos.values('pk'))
            .annotate(macroprocesso=Subquery(macroprocesso.values('descricao_macroprocesso')[:1]))
            .select_related(
                'evento',
                'documento_empenho__emitente_ug',
                'documento_empenho__responsavel_ug',
                'documento_empenho__plano_interno',
                'documento_empenho__ptres',
                'documento_empenho__documento_empenho_inicial',
            )
            .annotate(numero_empenho=Coalesce('documento_empenho__documento_empenho_inicial__numero', 'documento_empenho__numero'))
            .order_by('numero_empenho', 'documento_empenho__data_emissao', 'documento_empenho__numero', 'pk')
        )
