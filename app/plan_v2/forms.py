from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

from comum.models import Ano
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, RenderableSelectMultiple
from djtools.templatetags.filters import format_money
from financeiro.models import AcaoAno, NaturezaDespesa
from plan_v2.models import (
    PDI,
    Acao,
    AcaoPA,
    Atividade,
    Dimensao,
    Eixo,
    Indicador,
    IndicadorPA,
    IndicadorPAUnidadeAdministrativa,
    Macroprocesso,
    Meta,
    MetaPA,
    NaturezaDespesaPA,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoUA,
    PDIAcao,
    PDIMacroprocesso,
    PlanoAcao,
    Solicitacao,
    UnidadeAdministrativa,
    UnidadeMedida,
)
from rh.models import Setor


class EixoForm(forms.ModelFormPlus):
    class Meta:
        model = Eixo
        fields = ('nome',)


class DimensaoForm(forms.ModelFormPlus):
    setor_sistemico = forms.ModelChoiceField(
        label='Setor',
        help_text='Responsável sistêmico',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )

    class Meta:
        model = Dimensao
        fields = ('codigo', 'nome', 'eixo', 'setor_sistemico')


class MacroprocessoForm(forms.ModelFormPlus):
    class Meta:
        model = Macroprocesso
        fields = ('dimensao', 'nome', 'descricao')


class AcaoForm(forms.ModelFormPlus):
    macroprocesso = forms.ModelChoiceField(
        label='Macroprocesso', queryset=Macroprocesso.objects, widget=AutocompleteWidget(search_fields=Macroprocesso.SEARCH_FIELDS)
    )

    class Meta:
        model = Acao
        fields = ('macroprocesso', 'detalhamento', 'eh_vinculadora')


class UnidadeMedidaForm(forms.ModelFormPlus):
    class Meta:
        model = UnidadeMedida
        fields = ('nome',)


class PDIForm(forms.ModelFormPlus):
    ano_inicial = forms.ModelChoiceField(label='Ano Inicial', help_text='Vigência inicial do PDI', queryset=Ano.objects)
    ano_final = forms.ModelChoiceField(label='Ano Final', help_text='Vigência final do PDI', queryset=Ano.objects)

    class Meta:
        model = PDI
        fields = ('ano_inicial', 'ano_final')

    def clean(self):
        super().clean()

        if 'ano_inicial' in self.cleaned_data and 'ano_final' in self.cleaned_data:
            if self.cleaned_data['ano_inicial'].ano > self.cleaned_data['ano_final'].ano:
                self.add_error('ano_final', 'O ano final deve ser maior que o inicial.')
            elif self.cleaned_data['ano_final'].ano - self.cleaned_data['ano_inicial'].ano != 4:
                self.add_error('ano_final', 'O ano final deve ter 4 anos de diferença.')

        return self.cleaned_data


class AssociarMacroProcessoPDIForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    macroprocessos = forms.MultipleModelChoiceField(
        Macroprocesso.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/macroprocessos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)

        m_pdis = PDIMacroprocesso.objects.filter(pdi=self.pdi).values_list('pdi__pk', flat=True)
        m_initial = PDIMacroprocesso.objects.filter(pdi=self.pdi).values_list('macroprocesso__pk', flat=True)
        qs = Macroprocesso.objects.all()
        qs = qs.exclude(pk__in=m_pdis)
        qs = qs.order_by('dimensao__eixo__nome', 'dimensao__nome', 'nome')

        self.fields['macroprocessos'].querset = qs
        self.fields['macroprocessos'].initial = m_initial

    @transaction.atomic()
    def save(self):
        # Adiciona os macroprocessos novos
        m_ids = []
        for macroprocesso in self.cleaned_data['macroprocessos']:
            m_ids.append(macroprocesso.pk)
            if not PDIMacroprocesso.objects.filter(pdi=self.pdi, macroprocesso=macroprocesso).exists():
                PDIMacroprocesso.objects.create(pdi=self.pdi, macroprocesso=macroprocesso)

        # Excluir os macroprocessos que foram desmarcados
        for pdi_macroprocesso in PDIMacroprocesso.objects.filter(pdi=self.pdi).exclude(macroprocesso__pk__in=m_ids):
            if not ObjetivoEstrategico.objects.filter(pdi_macroprocesso=pdi_macroprocesso).exists():
                pdi_macroprocesso.delete()


class ObjetivoEstrategicoPDIForm(forms.ModelFormPlus):
    class Meta:
        model = ObjetivoEstrategico
        fields = ('pdi_macroprocesso', 'descricao')

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)
        self.fields['pdi_macroprocesso'].queryset = PDIMacroprocesso.objects.filter(pdi=self.pdi)


class MetaForm(forms.ModelFormPlus):
    responsavel = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor',
        help_text='Setor responsável pela sistematização',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )

    class Meta:
        model = Meta
        fields = ('titulo', 'responsavel')

    def __init__(self, *args, **kwargs):
        objetivo = kwargs.pop('objetivo_estrategico')
        super().__init__(*args, **kwargs)
        self.instance.objetivo_estrategico = objetivo


class IndicadorForm(forms.ModelFormPlus):
    class Meta:
        model = Indicador
        fields = ('denominacao', 'criterio_analise', 'forma_calculo', 'valor_fisico_inicial', 'valor_fisico_final', 'metodo_incremento')

    def __init__(self, *args, **kwargs):
        meta = kwargs.pop('meta')
        super().__init__(*args, **kwargs)
        self.instance.meta = meta


class AcaoSistemicoForm(forms.FormPlus):
    acao = forms.ModelChoiceFieldPlus2(
        label='Ação',
        help_text='',
        queryset=PDIAcao.objects.values_list('acao__detalhamento', flat=True),
        widget=AutocompleteWidget(search_fields=PDIAcao.SEARCH_FIELDS, readonly=False),
    )
    unidades_administrativa = forms.MultipleModelChoiceField(
        UnidadeAdministrativa.objects,
        label='Unid. Adm.',
        required=False,
        widget=RenderableSelectMultiple('widgets/unidade_administrativa_widget.html'),
    )

    def __init__(self, *args, **kwargs):
        plano_acao = kwargs.pop('plano_acao')
        meta_pa = kwargs.pop('meta_pa')
        acao = kwargs.pop('acao')
        super().__init__(*args, **kwargs)
        self.fields['acao'].queryset = PDIAcao.objects.filter(
            pdi=plano_acao.pdi, ativa_planoacao=True, acao__macroprocesso=meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.id
        )
        self.fields['unidades_administrativa'].queryset = UnidadeAdministrativa.objects.filter(pdi=plano_acao.pdi).order_by(
            'tipo', 'setor_equivalente__sigla'
        )
        if acao:
            self.fields['acao'].widget.readonly = True
            self.fields['acao'].initial = acao

            unidades = AcaoPA.objects.filter(acao=acao, meta_pa=meta_pa).values_list('unidade_administrativa', flat=True)
            self.fields['unidades_administrativa'].initial = unidades


class AssociarAcaoPlanoAcaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    acoes = forms.MultipleModelChoiceField(PDIAcao.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/pdiacoes_widget.html'))

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)

        a_initial = PDIAcao.objects.filter(pdi=self.pdi).values_list('acao__pk', flat=True)

        self.fields['acoes'].queryset = (
            PDIAcao.objects.filter(pdi=self.pdi).order_by('acao').order_by('acao__macroprocesso__nome', 'acao__detalhamento')
        )
        self.fields['acoes'].initial = a_initial

    @transaction.atomic()
    def save(self):
        # Adiciona as ações novas
        a_ids = []
        for acao in self.cleaned_data['acoes']:
            a_ids.append(acao.acao.pk)
            acao_planoacao = PDIAcao.objects.get(pdi=self.pdi, acao=acao.acao)
            acao_planoacao.ativa_planoacao = True
            acao_planoacao.save()

        # Excluir as ações que estão desativadas
        for acao in PDIAcao.objects.filter(pdi=self.pdi).exclude(acao__pk__in=a_ids):
            acao.ativa_planoacao = False
            acao.save()


class AssociarAcaoPDIForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    acoes = forms.MultipleModelChoiceField(Acao.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/acoes_widget.html'))

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)

        a_initial = PDIAcao.objects.filter(pdi=self.pdi).values_list('acao__pk', flat=True)

        self.fields['acoes'].queryset = Acao.objects.filter(ativa=True).order_by('macroprocesso__nome', 'detalhamento')
        self.fields['acoes'].initial = a_initial

    @transaction.atomic()
    def save(self):
        # Adiciona as ações novas
        a_ids = []
        for acao in self.cleaned_data['acoes']:
            a_ids.append(acao.pk)
            if not PDIAcao.objects.filter(pdi=self.pdi, acao=acao).exists():
                PDIAcao.objects.create(pdi=self.pdi, acao=acao)

        # Excluir os macroprocessos que foram desmarcados
        PDIAcao.objects.filter(pdi=self.pdi).exclude(acao__pk__in=a_ids).delete()


class PlanoAcaoPDIForm(forms.ModelFormPlus):
    pdi = forms.ModelChoiceField(label='Pdi', queryset=PDI.objects)
    ano_base = forms.ModelChoiceField(label='Ano Base', help_text='Ano de realização das atividades', queryset=Ano.objects)
    data_geral_inicial = forms.DateFieldPlus(label='Início da Vigência')
    data_geral_final = forms.DateFieldPlus(label='Fim da Vigência')
    data_metas_inicial = forms.DateFieldPlus(label='Início do Cadastro de Sistêmico')
    data_metas_final = forms.DateFieldPlus(label='Fim do Cadastro de Sistêmico')
    data_acoes_inicial = forms.DateFieldPlus(label='Início do Cadastro do Campus')
    data_acoes_final = forms.DateFieldPlus(label='Fim do Cadastro do Campus')
    data_validacao_inicial = forms.DateFieldPlus(label='Início da Validação')
    data_validacao_final = forms.DateFieldPlus(label='Fim da Validação')


class ImportarObjetivosPlanoAcaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    objetivos = forms.MultipleModelChoiceField(
        ObjetivoEstrategico.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/objetivos_estrategicos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.plano_acao = kwargs.pop('plano_acao')
        super().__init__(*args, **kwargs)

        obj_ids = MetaPA.objects.filter(plano_acao=self.plano_acao).values_list('meta__objetivo_estrategico__pk')

        objetivos = ObjetivoEstrategico.objects.filter(pdi_macroprocesso__pdi=self.plano_acao.pdi)
        objetivos = objetivos.exclude(pk__in=obj_ids)

        self.fields['objetivos'].queryset = objetivos

    @transaction.atomic()
    def save(self):
        # Adiciona as ações novas

        obj_ids = []
        for objetivo in self.cleaned_data['objetivos']:
            obj_ids.append(objetivo.pk)
            for meta in Meta.objects.filter(objetivo_estrategico=objetivo):
                if not MetaPA.objects.filter(plano_acao=self.plano_acao, meta=meta).exists():
                    meta_pa = MetaPA.objects.create(plano_acao=self.plano_acao, meta=meta)
                    for indicador in Indicador.objects.filter(meta=meta):
                        indicador_pa = IndicadorPA.objects.create(
                            indicador=indicador,
                            meta_pa=meta_pa,
                            # metodo_incremento = indicador.metodo_incremento
                        )
                        for unidade_administrativa in UnidadeAdministrativa.objects.filter(pdi=self.plano_acao.pdi):
                            IndicadorPAUnidadeAdministrativa.objects.create(indicador_pa=indicador_pa, unidade_administrativa=unidade_administrativa)


class AlterarIndicadorPlanoAcaoForm(forms.ModelFormPlus):
    class Meta:
        model = IndicadorPA
        fields = ('indicador', 'meta_pa', 'tipo_composicao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['indicador'].widget.attrs['readonly'] = 'readonly'
        self.fields['meta_pa'].widget.attrs['readonly'] = 'readonly'
        self.fields['meta_pa'].label = 'Meta'


def alterar_indicador_ua_form_factory(indicador_pa):
    class AlterarIndicadorUnidadeAdm(forms.FormPlus):
        SUBMIT_LABEL = 'Salvar'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @transaction.atomic()
        def save(self):
            valor_total = 0
            qtd_indicadores = 0
            for nome_campo, valor_inicial in list(self.cleaned_data.items()):
                if not nome_campo.startswith('ua_'):
                    continue
                _, pk, compl = nome_campo.split('_')

                if compl == 'valor':
                    indicador_ua = IndicadorPAUnidadeAdministrativa.objects.get(pk=pk)
                    indicador_ua.valor_inicial = valor_inicial
                    indicador_ua.save()

                    valor_total += valor_inicial
                    qtd_indicadores += 1

            if self.indicador_pa.tipo_composicao == IndicadorPA.COMPOSICAO_SOMA:
                self.indicador_pa.valor_inicial = valor_total
            else:
                self.indicador_pa.valor_inicial = valor_total / qtd_indicadores

            self.indicador_pa.save()

    # Adiciona os indicadores das unidades administrativas
    fieldset = []
    indicadores_ua = IndicadorPAUnidadeAdministrativa.objects.filter(indicador_pa=indicador_pa)
    indicadores_ua = indicadores_ua.order_by('unidade_administrativa__tipo', 'unidade_administrativa__setor_equivalente__sigla')
    for indicador_ua in indicadores_ua:
        nome_campo = f'ua_{indicador_ua.pk}_nome'
        valor_campo = f'ua_{indicador_ua.pk}_valor'
        AlterarIndicadorUnidadeAdm.base_fields[nome_campo] = forms.CharFieldPlus(
            label='', initial=indicador_ua.unidade_administrativa.setor_equivalente, required=False
        )
        AlterarIndicadorUnidadeAdm.base_fields[nome_campo].widget.attrs['readonly'] = 'readonly'

        valor_inicial = Decimal(0)
        if indicador_ua.valor_inicial:
            valor_inicial = indicador_ua.valor_inicial
        AlterarIndicadorUnidadeAdm.base_fields[valor_campo] = forms.DecimalFieldPlus(
            label='Valor proposto', help_text='', initial=valor_inicial, required=False
        )
        fieldset.append((nome_campo, valor_campo))

    AlterarIndicadorUnidadeAdm.indicador_pa = indicador_pa
    AlterarIndicadorUnidadeAdm.fieldsets = ((None, {'fields': fieldset}),)

    return AlterarIndicadorUnidadeAdm


class UnidadeAdministrativaForm(forms.ModelFormPlus):
    setor_equivalente = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor',
        help_text='Setor que responde pela unidade administrativa',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    setores_participantes = forms.ModelMultipleChoiceField(
        label='Setores Participantes', queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'), required=False
    )

    class Meta:
        model = UnidadeAdministrativa
        fields = ('tipo', 'setor_equivalente', 'setores_participantes')

    def __init__(self, *args, **kwargs):
        pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)
        self.instance.pdi = pdi

    def clean(self):
        if not self.errors:
            if self.cleaned_data['setor_equivalente']:
                if (
                    not self.instance.pk
                    and UnidadeAdministrativa.objects.filter(setor_equivalente=self.cleaned_data['setor_equivalente'], pdi=self.instance.pdi).exists()
                ):
                    self.add_error('setor_equivalente', 'Unidade Administrativa com este Setor Equivalente já existe para este PDI.')
        return self.cleaned_data


class OrigemRecursoForm(forms.ModelFormPlus):
    dimensao = forms.ModelChoiceFieldPlus2(
        label_template='{{ obj.nome" }}',
        label='Dimensão',
        help_text='',
        queryset=Dimensao.objects,
        widget=AutocompleteWidget(search_fields=Dimensao.SEARCH_FIELDS),
    )
    acao_financeira = forms.ModelChoiceFieldPlus2(
        label_template='{{ obj.acao.codigo_acao }}',
        label='Ação Orçamentária',
        help_text='',
        queryset=AcaoAno.objects,
        widget=AutocompleteWidget(label_value='codigo_e_ptres', search_fields=AcaoAno.SEARCH_FIELDS),
    )

    fieldsets = ((None, {'fields': ('dimensao', 'acao_financeira', ('valor_custeio', 'valor_capital'), 'visivel_campus', 'codigo', 'destinacao')}),)

    class Meta:
        model = OrigemRecurso
        fields = ('dimensao', 'acao_financeira', 'valor_capital', 'valor_custeio', 'visivel_campus', 'codigo', 'destinacao')

    def __init__(self, *args, **kwargs):
        self.plano_acao = kwargs.pop('plano_acao')
        super().__init__(*args, **kwargs)
        self.instance.plano_acao = self.plano_acao

        m_ids = PDIMacroprocesso.objects.filter(pdi=self.plano_acao.pdi).values_list('macroprocesso__dimensao__id', flat=True)

        self.fields['dimensao'].queryset = Dimensao.objects.filter(id__in=m_ids)
        self.fields['acao_financeira'].queryset = AcaoAno.objects.filter(ano_base=self.plano_acao.ano_base_id)

    def clean(self):
        super().clean()
        if not self.errors:
            acao_financeira = self.cleaned_data['acao_financeira']
            origens_recurso = OrigemRecurso.objects.filter(acao_financeira=acao_financeira)

            if not self.instance.pk:
                origens = OrigemRecurso.objects.filter(plano_acao=self.plano_acao)
                origens = origens.filter(dimensao=self.cleaned_data['dimensao'], acao_financeira=self.cleaned_data['acao_financeira'])

            if self.instance.pk:
                erro = False
                if self.instance.valor_capital > self.cleaned_data['valor_capital']:
                    uas_valor_capital = (
                        next(iter(OrigemRecursoUA.objects.filter(origem_recurso=self.instance).aggregate(Sum('valor_capital')).values())) or 0
                    )
                    if uas_valor_capital > self.cleaned_data['valor_capital']:
                        self.add_error(
                            'valor_capital',
                            f'O valor de capital é menor que o programado para as unidades administrativas. Valor comprometido: {format_money(uas_valor_capital)}',
                        )
                        erro = True
                if self.instance.valor_custeio > self.cleaned_data['valor_custeio']:
                    uas_valor_custeio = (
                        next(iter(OrigemRecursoUA.objects.filter(origem_recurso=self.instance).aggregate(Sum('valor_custeio')).values())) or 0
                    )
                    if uas_valor_custeio > self.cleaned_data['valor_custeio']:
                        self.add_error(
                            'valor_custeio',
                            f'O valor de custeio é menor que o programado para as unidades administrativas. Valor comprometido: {format_money(uas_valor_custeio)}',
                        )
                        erro = True
                if erro:
                    return self.cleaned_data
                else:
                    origens_recurso = origens_recurso.exclude(pk=self.instance.pk)

            total_valor_capital = next(iter(origens_recurso.aggregate(Sum('valor_capital')).values())) or 0
            total_valor_custeio = next(iter(origens_recurso.aggregate(Sum('valor_custeio')).values())) or 0

            total_valor_capital_atual = total_valor_capital + self.cleaned_data['valor_capital']
            total_valor_custeio_atual = total_valor_custeio + self.cleaned_data['valor_custeio']

            disponivel_valor_capital = acao_financeira.valor_capital - total_valor_capital
            disponivel_valor_custeio = acao_financeira.valor_custeio - total_valor_custeio

            if total_valor_capital_atual > acao_financeira.valor_capital:
                self.add_error(
                    'valor_capital', f'O valor de capital ultrapassou o disponível. Saldo disponível: {format_money(disponivel_valor_capital)}'
                )

            if total_valor_custeio_atual > acao_financeira.valor_custeio:
                self.add_error(
                    'valor_custeio', f'O valor de custeio ultrapassou o disponível. Saldo disponível: {format_money(disponivel_valor_custeio)}'
                )

        return self.cleaned_data


class NaturezaDespesaPAForm(forms.ModelFormPlus):
    class Meta:
        model = NaturezaDespesaPA
        fields = ('natureza_despesa',)

    def __init__(self, *args, **kwargs):
        self.plano_acao = kwargs.pop('plano_acao')
        super().__init__(*args, **kwargs)

        self.instance.plano_acao = self.plano_acao
        pa_naturezas = NaturezaDespesaPA.objects.filter(plano_acao=self.plano_acao).values_list('natureza_despesa__id', flat=True)
        naturezas = NaturezaDespesa.objects.all().exclude(id__in=pa_naturezas)
        naturezas = naturezas.order_by('categoria_economica_despesa', 'grupo_natureza_despesa', 'modalidade_aplicacao', 'elemento_despesa')

        self.fields['natureza_despesa'].queryset = naturezas


def alterar_origem_recurso_ua_form_factory(origem_recurso):
    class AlterarOrigemRecursoUnidadeAdm(forms.FormPlus):
        SUBMIT_LABEL = 'Salvar'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @transaction.atomic()
        def save(self):
            origens = {}
            for nome_campo, valor in list(self.cleaned_data.items()):
                if not nome_campo.startswith('or_'):
                    continue
                _, pk, compl = nome_campo.split('_')

                if compl != 'nome':
                    if pk not in origens:
                        origens[pk] = OrigemRecursoUA.objects.get(pk=pk)
                    if compl == 'valorcapital':
                        origens[pk].valor_capital = valor
                    elif compl == 'valorcusteio':
                        origens[pk].valor_custeio = valor
            for origem in list(origens.values()):
                origem.save()

        def clean(self):
            super().clean()

            # Montagem do dicionário para cada unidade administrativa nas origens de recurso
            origens_ua = {}
            for campo, valor in list(self.cleaned_data.items()):
                _, pk, tipo = campo.split('_')

                if pk not in origens_ua:
                    origens_ua[pk] = {'original': OrigemRecursoUA.objects.get(pk=pk), 'chave': campo, 'valorcapital': 0, 'valorcusteio': 0}
                origens_ua[pk][tipo] = valor

            # Iniciando a validação de dados - Capital
            total_capital = 0
            total_custeio = 0
            for dados in list(origens_ua.values()):
                atividades_custeio = Atividade.objects.filter(
                    acao_pa__unidade_administrativa=dados['original'].unidade_administrativa,
                    origem_recurso=self.origem_recurso,
                    natureza_despesa__natureza_despesa__tipo=NaturezaDespesa.VALOR_CUSTEIO,
                )

                atividades_capital = Atividade.objects.filter(
                    acao_pa__unidade_administrativa=dados['original'].unidade_administrativa,
                    origem_recurso=self.origem_recurso,
                    natureza_despesa__natureza_despesa__tipo=NaturezaDespesa.VALOR_CAPTAL,
                )

                total_atividade_custeio = next(iter(atividades_custeio.aggregate(Sum('valor')).values())) or 0
                total_atividade_capital = next(iter(atividades_capital.aggregate(Sum('valor')).values())) or 0
                if dados['valorcapital'] is None or dados['valorcusteio'] is None:
                    self.add_error(dados['chave'], 'Campo Obrigatório')
                else:
                    if dados['valorcapital'] < total_atividade_capital:
                        self.add_error(
                            dados['chave'],
                            f'O valor de capital é menor que o programado para as atividades. Valor comprometido: {format_money(total_atividade_capital)}',
                        )

                    if dados['valorcusteio'] < total_atividade_custeio:
                        self.add_error(
                            dados['chave'],
                            f'O valor de custeio é menor que o programado para as atividades. Valor comprometido: {format_money(total_atividade_custeio)}',
                        )

                total_capital += dados['valorcapital'] or 0
                total_custeio += dados['valorcusteio'] or 0

            if self.origem_recurso.valor_capital < total_capital:
                self.add_error(None, 'A soma dos valores para capital é maior que a disponível.')

            if self.origem_recurso.valor_custeio < total_custeio:
                self.add_error(None, 'A soma dos valores para custeio é maior que a disponível.')

            return self.cleaned_data

    # Adiciona os indicadores das unidades administrativas
    fieldset = []
    origens_recurso_ua = OrigemRecursoUA.objects.filter(origem_recurso=origem_recurso)
    origens_recurso_ua = origens_recurso_ua.order_by('unidade_administrativa__tipo', 'unidade_administrativa__setor_equivalente__sigla')

    for origem in origens_recurso_ua:
        ua_campo = f'or_{origem.pk}_nome'
        valor_capital = f'or_{origem.pk}_valorcapital'
        valor_custeio = f'or_{origem.pk}_valorcusteio'

        AlterarOrigemRecursoUnidadeAdm.base_fields[ua_campo] = forms.CharFieldPlus(
            label='', initial=origem.unidade_administrativa.setor_equivalente, required=False
        )
        AlterarOrigemRecursoUnidadeAdm.base_fields[ua_campo].widget.attrs['readonly'] = 'readonly'

        AlterarOrigemRecursoUnidadeAdm.base_fields[valor_capital] = forms.DecimalFieldPlus(
            label='Valor Capital', help_text='', initial=origem.valor_capital, required=False
        )
        AlterarOrigemRecursoUnidadeAdm.base_fields[valor_capital].widget.attrs = {'style': 'width: 100px'}
        AlterarOrigemRecursoUnidadeAdm.base_fields[valor_custeio] = forms.DecimalFieldPlus(
            label='Valor Custeio', help_text='', initial=origem.valor_custeio, required=False
        )
        AlterarOrigemRecursoUnidadeAdm.base_fields[valor_custeio].widget.attrs = {'style': 'width: 100px'}
        fieldset.append((ua_campo, valor_capital, valor_custeio))

    AlterarOrigemRecursoUnidadeAdm.origem_recurso = origem_recurso
    AlterarOrigemRecursoUnidadeAdm.fieldsets = ((None, {'fields': fieldset}),)

    return AlterarOrigemRecursoUnidadeAdm


class AcaoPAForm(forms.ModelFormPlus):
    acao = forms.ModelChoiceField(
        label='Ação',
        help_text='',
        queryset=PDIAcao.objects,
        widget=AutocompleteWidget(label_value='acao.detalhamento', search_fields=PDIAcao.SEARCH_FIELDS, readonly=True),
    )

    setores_responsaveis = forms.MultipleModelChoiceFieldPlus(
        label='Setores Responsáveis',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(multiple=True, extraParams={'force_generic_search': '1'}, form_filters=[('sigla', 'nome')]),
    )

    class Meta:
        model = AcaoPA
        fields = ('acao', 'setores_responsaveis')

    def __init__(self, *args, **kwargs):
        acao_add = kwargs.pop('acao_add')
        self.meta_pa = kwargs.pop('meta_pa')
        self.unidade_administrativa = kwargs.pop('unidade_administrativa')
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.instance.meta_pa = self.meta_pa
            self.instance.unidade_administrativa = self.unidade_administrativa
        self.fields['setores_responsaveis'].queryset = Setor.objects.suap_ativos().filter(
            uo=self.instance.unidade_administrativa.setor_equivalente.uo
        )
        self.fields['acao'].queryset = PDIAcao.objects.filter(
            pdi=self.meta_pa.plano_acao.pdi,
            ativa_planoacao=True,
            acao__macroprocesso=self.instance.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.id,
        )

        if acao_add:
            self.fields['acao'].widget.readonly = False


class AtividadeForm(forms.ModelFormPlus):
    natureza_despesa = forms.ModelChoiceField(
        label='Natureza de Despesa',
        help_text='',
        queryset=NaturezaDespesaPA.objects,
        widget=AutocompleteWidget(search_fields=NaturezaDespesaPA.SEARCH_FIELDS),
    )

    class Meta:
        model = Atividade
        fields = ('detalhamento', 'acao_pa_vinculadora', 'observacao', 'origem_recurso', 'natureza_despesa', 'valor')

    def __init__(self, *args, **kwargs):
        acao_pa = kwargs.pop('acao_pa')
        super().__init__(*args, **kwargs)
        self.instance.acao_pa = acao_pa

        self.fields['acao_pa_vinculadora'].queryset = AcaoPA.objects.filter(
            unidade_administrativa=acao_pa.unidade_administrativa, acao__acao__eh_vinculadora=True
        ).order_by('acao__acao__detalhamento')
        self.fields['acao_pa_vinculadora'].required = False

        origens_pk = OrigemRecursoUA.objects.filter(
            unidade_administrativa=acao_pa.unidade_administrativa, origem_recurso__plano_acao=acao_pa.meta_pa.plano_acao
        )
        origens_pk = origens_pk.filter(Q(valor_capital__gt=0) | Q(valor_custeio__gt=0))
        origens_pk = origens_pk.values_list('origem_recurso__pk', flat=True)

        self.fields['origem_recurso'].queryset = OrigemRecurso.objects.filter(pk__in=origens_pk, visivel_campus=True).order_by(
            'codigo', 'acao_financeira__acao__codigo_acao', 'acao_financeira__ptres'
        )

        self.fields['origem_recurso'].required = False
        self.fields['natureza_despesa'].queryset = NaturezaDespesaPA.objects.filter(plano_acao=acao_pa.meta_pa.plano_acao)
        self.fields['natureza_despesa'].required = False
        self.fields['valor'].required = False

    def clean(self):
        super().clean()

        if self.cleaned_data.get('acao_pa_vinculadora'):
            if self.instance.acao_pa == self.cleaned_data.get('acao_pa_vinculadora'):
                self.add_error('acao_pa_vinculadora', 'Ação Vinculadora não deve ser igual a Ação.')

        if self.cleaned_data.get('valor') and self.cleaned_data.get('valor') > 0:
            tem_natureza_despesa = self.cleaned_data.get('natureza_despesa', None)
            tem_origem_recurso = self.cleaned_data.get('origem_recurso', None)

            if tem_natureza_despesa is None:
                self.add_error('natureza_despesa', 'É obrigatório o preenchimento quando o valor é definido.')

            if tem_origem_recurso is None:
                self.add_error('origem_recurso', 'É obrigatório o preenchimento quando o valor é definido.')

            if tem_natureza_despesa is not None and tem_origem_recurso is not None:
                origem_recurso = self.cleaned_data['origem_recurso']
                origem_recurso_ua = OrigemRecursoUA.objects.get(
                    origem_recurso=origem_recurso, unidade_administrativa=self.instance.acao_pa.unidade_administrativa
                )
                tipo_natureza = self.cleaned_data['natureza_despesa'].natureza_despesa.tipo

                total_atividades = 0

                if self.instance.pk:
                    atividade = Atividade.objects.get(pk=self.instance.pk)
                    if atividade.origem_recurso == self.cleaned_data['origem_recurso']:
                        total_atividades -= self.instance.valor or 0

                valor_origem_recurso = 0
                if tipo_natureza == NaturezaDespesa.VALOR_CUSTEIO:
                    total_atividades += origem_recurso_ua.valor_custeio_comprometido
                    valor_origem_recurso = origem_recurso_ua.valor_custeio
                else:
                    total_atividades += origem_recurso_ua.valor_capital_comprometido
                    valor_origem_recurso = origem_recurso_ua.valor_capital

                if total_atividades + self.cleaned_data['valor'] > valor_origem_recurso:
                    self.add_error(
                        'valor',
                        f'O valor solicitado é maior do que o disponível. Disponível: {format_money(valor_origem_recurso - total_atividades)}',
                    )

        return self.cleaned_data


class UnidadeDisponibilidadeForm(forms.FormPlus):
    unidade_administrativa = forms.ModelChoiceFieldPlus2(label='Unidade Adm.', queryset=UnidadeAdministrativa.objects)

    def __init__(self, *args, **kwargs):
        plano_acao = kwargs.pop('plano_acao')
        super().__init__(*args, **kwargs)

        unidades = UnidadeAdministrativa.objects.filter(pdi=plano_acao.pdi)
        unidades = unidades.order_by('tipo', 'setor_equivalente__sigla')

        self.fields['unidade_administrativa'].queryset = unidades
        self.fields['unidade_administrativa'].widget.attrs['onchange'] = "$('#unidadedisponibilidade_form').submit();"
        self.fields['unidade_administrativa'].widget.attrs['class'] = 'filter-large-select'


class SolicitacaoForm(forms.ModelFormPlus):
    class Meta:
        model = Solicitacao
        fields = ('solicitacao',)

    def __init__(self, *args, **kwargs):
        unidade = kwargs.pop('unidade_administrativa')
        super().__init__(*args, **kwargs)
        self.instance.unidade_administrativa = unidade[0]


class SolicitacaoParecerForm(forms.ModelFormPlus):
    unidade_administrativa = forms.ModelChoiceField(
        label='Unidade Administrativa', help_text='', queryset=UnidadeAdministrativa.objects, widget=AutocompleteWidget(readonly=True)
    )
    parecer = forms.ChoiceField(label='Parecer', widget=forms.RadioSelect(), choices=Solicitacao.PARECER_CHOICES)

    class Meta:
        model = Solicitacao
        fields = ('unidade_administrativa', 'solicitacao', 'parecer', 'justificativa')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['solicitacao'].widget.attrs['readonly'] = 'readonly'

    def clean_parecer(self):
        if 'parecer' not in self.cleaned_data or self.cleaned_data['parecer'] == Solicitacao.PARECER_ESPERA:
            raise forms.ValidationError(f'O parecer não pode ser "{Solicitacao.PARECER_ESPERA}".')
        return self.cleaned_data['parecer']

    def clean(self):
        super().clean()
        parecer = self.cleaned_data.get('parecer', '')

        if parecer == Solicitacao.PARECER_REJEITADO:
            justificativa = self.cleaned_data.get('justificativa', '')
            if justificativa == '':
                self.add_error('justificativa', f'A justificativa é obrigatória para parecer "{Solicitacao.PARECER_REJEITADO}".')

        return self.cleaned_data


class ValidarAcaoForm(forms.FormPlus):
    situacao = forms.ChoiceField(label='Status', choices=Acao.SITUACAO_CHOICE)


class RelatorioDetalhamentoForm(forms.FormPlus):
    campus = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeAdministrativa.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )


class PlanoAcaoFiltroForm(forms.FormPlus):
    planoacao = None

    def __init__(self, *args, **kwargs):
        if 'id_planoacao' in kwargs:
            id_planoacao = kwargs.pop('id_planoacao')
            empty_label = kwargs.pop('empty_label') if 'empty_label' in kwargs else None

            super().__init__(*args, **kwargs)
            self.fields['planoacao'] = forms.ModelChoiceField(
                label='Plano de Ação',
                queryset=PlanoAcao.objects.all().order_by('-ano_base__ano'),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                empty_label=empty_label,
            )

            if id_planoacao:
                planoacao = PlanoAcao.objects.get(id=id_planoacao)
                self.fields['planoacao'].initial = planoacao.id
        else:
            super().__init__(*args, **kwargs)
            planoacao = PlanoAcao.objects.all().order_by('-ano_base__ano')[0].id
            self.fields['planoacao'] = forms.ModelChoiceField(
                label='Plano de Ação',
                queryset=PlanoAcao.objects.all().order_by('-ano_base__ano'),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                initial=planoacao,
            )
