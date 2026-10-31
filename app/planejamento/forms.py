# imports ----------------------------------------------------------------------
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

import financeiro
from comum.models import Ano
from djtools import db, forms
from djtools.forms.widgets import AutocompleteWidget, BrDataWidget
from djtools.templatetags.filters import format_money, in_group
from financeiro.models import AcaoAno, FonteRecurso
from planejamento.enums import PercentualExecucao, Situacao, TipoUnidade
from planejamento.models import (
    Acao,
    AcaoExecucao,
    AcaoExtraTeto,
    AcaoProposta,
    Atividade,
    AtividadeExecucao,
    Configuracao,
    Dimensao,
    Meta,
    MetaUnidade,
    MetaUnidadeAcaoProposta,
    NaturezaDespesa,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoUA,
    UnidadeAdministrativa,
    UnidadeMedida,
)
from planejamento.utils import get_setor_unidade_administrativa
from rh.models import Setor, UnidadeOrganizacional

# -------------------------------------------------------------------------------


# método comuns ----------------------------------------------------------------
# retorna um choice onde o tipo (campus/pró-reitoria/diretoria sistemica) é utilizado para categorizar as unidades
def unidades_agrupadas_as_choices():
    tipos_unidades = [['', '---------']]
    for tipo in TipoUnidade.get_lista_simples():
        unidades = []
        for unidade in UnidadeAdministrativa.objects.filter(tipo=tipo):
            unidades.append([unidade.id, unidade])
        if len(unidades) != 0:
            tipos_unidades.append([tipo.nome, unidades])

    return tipos_unidades


# retorna um choice com todas as possíveis unidades administrativas
def unidades_as_choices():
    unidades = [['', '---------']]

    for setor in (
        Setor.objects.suap_ativos()
        .filter(Q(uo__isnull=True, superior__isnull=False) | Q(pk__in=UnidadeOrganizacional.objects.suap().all().values_list('setor_id', flat=True)))
        .order_by('nome')
    ):
        unidades.append([setor.id, setor])

    return unidades


# retorna um choice contendo todas as unidades para um tipo
def unidades_tipo_as_choices(tipo_unidade):
    unidades_tipo = UnidadeAdministrativa.objects.filter(tipo=tipo_unidade)
    unidades = [['', '---------']]
    for unidade in unidades_tipo:
        unidades.append([unidade.id, unidade])
    return unidades


# retorna um choice contendo as unidades que ainda nao foram cadastradas
def unidades_disponiveis_as_choices(id_meta, id_unidade=None):
    meta = Meta.objects.get(pk=id_meta)
    unidades_cadastradas = list(MetaUnidade.objects.filter(meta=id_meta).values_list('unidade_id', flat=True))
    total_unidades = list(UnidadeAdministrativa.objects.filter(configuracao=meta.objetivo_estrategico.configuracao).values_list('id', flat=True))
    ids_unidades = list(total_unidades)
    for unidades in unidades_cadastradas:
        if unidades == id_unidade:
            continue
        if unidades in ids_unidades:
            ids_unidades.remove(unidades)

    unidades = [['', '---------']]
    for unidade in UnidadeAdministrativa.objects.filter(id__in=ids_unidades).order_by('setor_equivalente__nome'):
        unidades.append([unidade.id, unidade])

    return unidades


# retorna um choice contendo as meta_unidades (é apresentado apenas o nome da unidade) que ainda nao estao associadas a acao proposta
def unidades_disponiveis_acao_proposta_as_choices(id_acao_proposta, id_unidade):
    acao_proposta = AcaoProposta.objects.get(pk=id_acao_proposta)
    unidades_cadastradas = list(MetaUnidadeAcaoProposta.objects.filter(acao_proposta=acao_proposta).values_list('meta_unidade_id', flat=True))
    total_unidades = list(MetaUnidade.objects.filter(meta=acao_proposta.meta).values_list('id', flat=True))
    ids_unidades = total_unidades
    for unidades in unidades_cadastradas:
        if unidades == id_unidade:
            continue
        if unidades in ids_unidades:
            ids_unidades.remove(unidades)

    meta_unidades = [['', '---------']]
    for meta_unidade in MetaUnidade.objects.filter(id__in=ids_unidades).order_by('unidade__setor_equivalente__nome'):
        meta_unidades.append([meta_unidade.id, meta_unidade.unidade])

    return meta_unidades


# retorna um choice contendo as unidades que ainda nao foram cadastradas
def unidades_origem_recurso_as_choices(id_origem_recurso, id_unidade=None):
    origem_recurso = OrigemRecurso.objects.get(pk=id_origem_recurso)
    unidades_cadastradas = list(OrigemRecursoUA.objects.filter(origem_recurso=id_origem_recurso).values_list('unidade_id', flat=True))
    total_unidades = list(UnidadeAdministrativa.objects.filter(configuracao=origem_recurso.configuracao).values_list('id', flat=True))
    ids_unidades = list(total_unidades)
    for unidades in unidades_cadastradas:
        if unidades == id_unidade:
            continue
        if unidades in ids_unidades:
            ids_unidades.remove(unidades)

    unidades = [['', '---------']]
    for unidade in UnidadeAdministrativa.objects.filter(id__in=ids_unidades).order_by('setor_equivalente__nome'):
        unidades.append([unidade.id, unidade])

    return unidades


# retorna um choice contendo as unidade associadas a uma meta
def unidades_associadas_as_choices(id_meta):
    unidades = []
    for meta_unidade in MetaUnidade.objects.filter(meta=id_meta):
        unidades.append([meta_unidade.unidade.id, meta_unidade.unidade])

    return unidades


# retorna um choice contendo as naturezas de despesas organizadas por grupos (custeio e investimento)
def naturezas_depesa_as_choices():
    naturezas = [['', '---------']]

    tipos = [{'nome': 'Pessoal', 'codigo': '31'}, {'nome': 'Custeio', 'codigo': '33'}, {'nome': 'Capital', 'codigo': '44'}]

    for tipo in tipos:
        naturezas_tipo = []
        for natureza in NaturezaDespesa.objects.filter(naturezadespesa__codigo__istartswith=tipo['codigo']):
            naturezas_tipo.append([natureza.id, natureza])

        naturezas.append([tipo['nome'], naturezas_tipo])

    return naturezas


# -------------------------------------------------------------------------------
class ConfiguracaoPlanejamentoForm(forms.ModelFormPlus):
    ano_base = forms.ModelChoiceField(label='Ano Base', help_text='Ano de realização das atividades', queryset=Ano.objects.all())
    data_geral_inicial = forms.DateFieldPlus(label='Vigência', help_text='Data de início')
    data_geral_final = forms.DateFieldPlus(help_text='Data limite', widget=BrDataWidget(show_label=False))
    data_metas_inicial = forms.DateFieldPlus(label='Cadastro de Sistêmico', help_text='Data de início')
    data_metas_final = forms.DateFieldPlus(help_text='Data limite', widget=BrDataWidget(show_label=False))
    data_acoes_inicial = forms.DateFieldPlus(label='Cadastro de Campus', help_text='Data de início')
    data_acoes_final = forms.DateFieldPlus(help_text='Data limite', widget=BrDataWidget(show_label=False))
    data_validacao_inicial = forms.DateFieldPlus(label='Validação', help_text='Data de início')
    data_validacao_final = forms.DateFieldPlus(help_text='Data limite', widget=BrDataWidget(show_label=False))
    data_planilhas_inicial = forms.DateFieldPlus(label='Envio de planilhas', help_text='Data de início')
    data_planilhas_final = forms.DateFieldPlus(help_text='Data limite', widget=BrDataWidget(show_label=False))

    class Meta:
        model = Configuracao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields['ano_base'] = forms.ModelChoiceField(
                label='Ano Base', help_text='Ano de realização das atividades', queryset=Ano.objects.all(), widget=AutocompleteWidget(readonly=True)
            )

    def clean_ano_base(self):
        if 'ano_base' in self.cleaned_data:
            data_menor = Configuracao.objects.filter(ano_base__gt=self.cleaned_data['ano_base'])
            if not self.instance.pk and len(data_menor) > 0:
                raise forms.ValidationError('Já existe planejamento cadastrado para um ano posterior ao informado.')
            return self.cleaned_data['ano_base']

    def clean_data_geral_final(self):
        if 'data_geral_final' in self.cleaned_data:
            if self.cleaned_data['data_geral_final'] < self.cleaned_data['data_geral_inicial']:
                raise forms.ValidationError('A data limite deve ser maior que a data inicial.')

            return self.cleaned_data['data_geral_final']

    def clean_data_metas_final(self):
        if ('data_geral_inicial' in self.cleaned_data) and ('data_metas_inicial' in self.cleaned_data) and ('data_metas_final' in self.cleaned_data):
            if self.cleaned_data['data_metas_final'] < self.cleaned_data['data_metas_inicial']:
                raise forms.ValidationError('A data limite deve ser maior que a data inicial.')

            if self.cleaned_data['data_metas_final'] > self.cleaned_data['data_geral_inicial']:
                raise forms.ValidationError('O período para o cadastro de metas deve ser anterior ao período de vigência do planejamento.')

            return self.cleaned_data['data_metas_final']

    def clean_data_acoes_final(self):
        if ('data_geral_inicial' in self.cleaned_data) and ('data_acoes_inicial' in self.cleaned_data) and ('data_acoes_final' in self.cleaned_data):
            if self.cleaned_data['data_acoes_final'] < self.cleaned_data['data_acoes_inicial']:
                raise forms.ValidationError('A data limite deve ser maior que a data inicial.')

            if self.cleaned_data['data_acoes_final'] > self.cleaned_data['data_geral_inicial']:
                raise forms.ValidationError('O período para o cadastro de acoes deve ser anterior ao período de vigência do planejamento.')

            return self.cleaned_data['data_acoes_final']

    def clean_data_validacao_final(self):
        if (
            ('data_geral_inicial' in self.cleaned_data)
            and ('data_validacao_inicial' in self.cleaned_data)
            and ('data_validacao_final' in self.cleaned_data)
        ):
            if self.cleaned_data['data_validacao_final'] < self.cleaned_data['data_validacao_inicial']:
                raise forms.ValidationError('A data limite deve ser maior que a data inicial.')

            if self.cleaned_data['data_validacao_final'] > self.cleaned_data['data_geral_inicial']:
                raise forms.ValidationError('O período para a validação do planejamento deve ser anterior ao período de vigência deste.')

            return self.cleaned_data['data_validacao_final']

    def clean_data_planilhas_final(self):
        if (
            ('data_geral_inicial' in self.cleaned_data)
            and ('data_planilhas_inicial' in self.cleaned_data)
            and ('data_planilhas_final' in self.cleaned_data)
        ):
            if self.cleaned_data['data_planilhas_final'] < self.cleaned_data['data_planilhas_inicial']:
                raise forms.ValidationError('A data limite deve ser maior que a data inicial.')

            if self.cleaned_data['data_planilhas_final'] > self.cleaned_data['data_geral_inicial']:
                raise forms.ValidationError('O período para o envio de planilhas do planejamento deve ser anterior ao período de vigência deste.')

            return self.cleaned_data['data_planilhas_final']


# -------------------------------------------------------------------------------
class DimensaoForm(forms.ModelFormPlus):
    descricao = forms.CapitalizeTextField(
        label='Descrição', help_text='Dimensão do Planejamento', max_length=80, widget=forms.TextInput(attrs={'size': '65'})
    )
    setor_sistemico = forms.ModelChoiceField(
        label='Setor',
        help_text='Responsável sistêmico',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    codigo = forms.IntegerFieldPlus(label='Código', max_length=2, required=False)

    class Meta:
        model = Dimensao
        exclude = ()

    def clean_codigo(self):
        if 'codigo' in self.cleaned_data:
            if self.cleaned_data['codigo']:
                dimensao = Dimensao.objects.filter(codigo=self.cleaned_data['codigo'])
                if self.instance.pk is None:  # indica que o fomulário está sendo utilizado para cadastro e não edição
                    if len(dimensao):
                        raise forms.ValidationError('O código escolhido já está sendo usado para outra dimensão.')
                else:  # edicao
                    if len(dimensao) and dimensao[0].pk != self.instance.pk:
                        raise forms.ValidationError('O código escolhido já está sendo usado para outra dimensão.')
        return self.cleaned_data['codigo']


# -------------------------------------------------------------------------------
class UnidadeMedidaForm(forms.ModelFormPlus):
    nome = forms.CapitalizeTextField(label='Nome', help_text='Ex.: Projeto, Processo', widget=forms.TextInput(attrs={'size': '88'}), max_length=30)

    class Meta:
        model = UnidadeMedida
        exclude = ()


# -------------------------------------------------------------------------------
class NaturezaDespesaForm(forms.ModelFormPlus):
    class Meta:
        model = NaturezaDespesa
        exclude = ()

    def clean(self):
        if 'naturezadespesa' in self.cleaned_data:
            if self.cleaned_data['naturezadespesa']:
                codigo = NaturezaDespesa.objects.filter(naturezadespesa=self.cleaned_data['naturezadespesa'])
                if len(codigo):
                    raise forms.ValidationError('A Natureza de despesa já está cadastrada!')
        return self.cleaned_data


# -------------------------------------------------------------------------------
class OrigemRecursoForm(forms.ModelFormPlus):
    configuracao = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all(), widget=AutocompleteWidget(readonly=True))
    dimensao = forms.ModelChoiceField(label='Dimensão', queryset=Dimensao.objects.all(), required=False)
    acao_ano = forms.ModelChoiceField(label='Ação', queryset=AcaoAno.objects.all())

    class Meta:
        model = OrigemRecurso
        exclude = ('valor_disponivel',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configs = Configuracao.objects.all().order_by('-ano_base__ano')
        if configs.exists():
            self.fields['configuracao'].initial = configs[0]
        self.fields['acao_ano'].queryset = AcaoAno.objects.filter(ano_base=configs[0].ano_base_id)

    def clean_valor_capital(self):
        if self.data['acao_ano']:
            configs = Configuracao.objects.all().order_by('-ano_base__ano')
            # Valor total de capital da Acao Ano
            total_capital_acao = (
                next(
                    iter(
                        AcaoAno.objects.filter(ano_base=configs[0].ano_base_id, pk=self.cleaned_data['acao_ano'].pk)
                        .aggregate(Sum('valor_capital'))
                        .values()
                    )
                )
                or 0
            )
            # Total do valor_capital das origens de recurso com a acao ano especificada
            total = next(iter(OrigemRecurso.objects.filter(acao_ano=self.cleaned_data['acao_ano']).aggregate(Sum('valor_capital')).values())) or 0
            # Valor disponivel para cadastrar
            if self.instance.pk:
                total_origemrecursoUA = (
                    next(iter(OrigemRecursoUA.objects.filter(origem_recurso=self.instance.pk).aggregate(Sum('valor_capital')).values())) or 0
                )
                if total_origemrecursoUA > self.cleaned_data['valor_capital']:
                    raise forms.ValidationError('Este valor é inferior ao planejado nas Origens de Recursos UA')
                capital_disponivel = (total_capital_acao + self.instance.valor_capital) - total
            else:
                capital_disponivel = total_capital_acao - total
            if capital_disponivel < 0 or self.cleaned_data['valor_capital'] > capital_disponivel:
                raise forms.ValidationError(
                    f'Este valor ultrapassou o valor disponível de capital da acão. Saldo Disponível: {format_money(capital_disponivel)}'
                )
            return self.cleaned_data['valor_capital']

    def clean_valor_custeio(self):
        if self.data['acao_ano']:
            configs = Configuracao.objects.all().order_by('-ano_base__ano')
            # Valor total de custeio da Acao Ano
            total_custeio_acao = (
                next(
                    iter(
                        AcaoAno.objects.filter(ano_base=configs[0].ano_base_id, pk=self.cleaned_data['acao_ano'].pk)
                        .aggregate(teste=Sum('valor_custeio'))
                        .values()
                    )
                )
                or 0
            )
            # Total de valor Custeio das origens de recurso com a ação ano especificada
            total = next(iter(OrigemRecurso.objects.filter(acao_ano=self.cleaned_data['acao_ano']).aggregate(Sum('valor_custeio')).values())) or 0
            # Valor disponivel para cadastrar
            if self.instance.pk:
                total_origemrecursoUA = (
                    next(iter(OrigemRecursoUA.objects.filter(origem_recurso=self.instance.pk).aggregate(Sum('valor_custeio')).values())) or 0
                )
                if total_origemrecursoUA > self.cleaned_data['valor_custeio']:
                    raise forms.ValidationError('Este valor é inferior ao planejado nas Origens de Recursos UA')
                custeio_disponivel = (total_custeio_acao + self.instance.valor_custeio) - total
            else:
                custeio_disponivel = total_custeio_acao - total
            if custeio_disponivel < 0 or self.cleaned_data['valor_custeio'] > custeio_disponivel:
                raise forms.ValidationError(
                    f'Este valor ultrapassou o valor disponível de custeio da ação. Saldo Disponível: {format_money(custeio_disponivel)}'
                )
            return self.cleaned_data['valor_custeio']


# -------------------------------------------------------------------------------
class UnidadeAdministrativaForm(forms.ModelFormPlus):
    configuracao = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all(), widget=AutocompleteWidget(readonly=True))
    codigo_simec = forms.CharField(required=False, label='Código SIMEC', max_length=6, widget=forms.TextInput(attrs={'size': '8'}))
    orcamento = forms.DecimalFieldPlus('Orçamento Próprio', help_text='Outros Custeios e Capital (OCC)', required=False)
    setor_equivalente = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor',
        help_text='Setor que responde pela unidade administrativa',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=forms.Select(attrs={'class': 'monospace'}),
    )

    class Meta:
        model = UnidadeAdministrativa
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configs = Configuracao.objects.all().order_by('-ano_base__ano')
        if configs.exists():
            self.fields['configuracao'].initial = configs[0]

    def clean(self):
        # impede que o usuário cadastre 000000 como código simec
        if 'codigo_simec' in self.cleaned_data and self.cleaned_data['codigo_simec'] == '000000':
            self.cleaned_data['codigo_simec'] = None
        return self.cleaned_data


# -------------------------------------------------------------------------------


class OrigemRecursoUAForm(forms.ModelFormPlus):
    origem_recurso = forms.ModelChoiceField(label='Origem Recurso', queryset=OrigemRecurso.objects.all(), widget=AutocompleteWidget(readonly=True))

    class Meta:
        model = OrigemRecursoUA
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'origem_recurso' in self.request.GET:
            self.fields['origem_recurso'].widget.readonly = True
            self.fields['unidade'].widget.choices = unidades_origem_recurso_as_choices(self.request.GET['origem_recurso'])

        if self.instance.pk:
            self.fields['origem_recurso'].widget.readonly = True
            self.fields['unidade'].widget.choices = unidades_origem_recurso_as_choices(self.instance.origem_recurso.id, self.instance.unidade.pk)

        configs = Configuracao.objects.all().order_by('-ano_base__ano')
        self.fields['origem_recurso'].queryset = OrigemRecurso.objects.filter(configuracao__ano_base=configs[0].ano_base_id)

    def clean_valor_capital(self):
        configs = Configuracao.objects.latest('ano_base__ano')
        total_capital = (
            next(iter(OrigemRecurso.objects.filter(id=self.cleaned_data['origem_recurso'].pk).aggregate(Sum('valor_capital')).values())) or 0
        )
        total = (
            next(
                iter(
                    OrigemRecursoUA.objects.filter(origem_recurso__id=self.cleaned_data['origem_recurso'].pk).aggregate(Sum('valor_capital')).values()
                )
            )
            or 0
        )
        capital_disponivel = total_capital - total

        if self.instance.pk:
            strConsulta = """
                SELECT COALESCE(SUM(at.quantidade * at.valor_unitario), 0) AS total
                  FROM planejamento_atividade at
                       INNER JOIN planejamento_acao a ON at.acao_id = a.id
                       INNER JOIN planejamento_metaunidade m ON a.meta_unidade_id = m.id
                       INNER JOIN planejamento_origemrecurso o ON at.tipo_recurso_id = o.id
                       INNER JOIN planejamento_naturezadespesa nat ON at.elemento_despesa_id = nat.id
                       INNER JOIN financeiro_naturezadespesa nat_desp ON nat.naturezadespesa_id = nat_desp.id
                 WHERE o.id = {}
                   AND nat_desp.tipo = '{}'
                   AND o.configuracao_id = {}
                   AND m.unidade_id = {}
            """.format(
                self.instance.origem_recurso.pk,
                'Capital',
                configs.pk,
                self.cleaned_data['unidade'].pk,
            )

            atividade_total = db.get_dict(strConsulta)
            total_atividade = atividade_total[0]['total'] or 0
            if total_atividade > self.cleaned_data['valor_capital']:
                raise forms.ValidationError('Este valor é inferior ao planejado nas atividades.')
            capital_disponivel = (total_capital + self.instance.valor_capital) - total
        else:
            capital_disponivel = total_capital - total
        if capital_disponivel < 0 or self.cleaned_data['valor_capital'] > capital_disponivel:
            raise forms.ValidationError(f'Este valor ultrapassou o valor de capital da acão. Saldo Disponível: {format_money(capital_disponivel)}')
        return self.cleaned_data['valor_capital']

    def clean_valor_custeio(self):
        configs = Configuracao.objects.latest('ano_base__ano')
        total_custeio = (
            next(iter(OrigemRecurso.objects.filter(id=self.cleaned_data['origem_recurso'].pk).aggregate(Sum('valor_custeio')).values())) or 0
        )
        total = (
            next(
                iter(
                    OrigemRecursoUA.objects.filter(origem_recurso__id=self.cleaned_data['origem_recurso'].pk).aggregate(Sum('valor_custeio')).values()
                )
            )
            or 0
        )
        custeio_disponivel = total_custeio - total

        if self.instance.pk:
            strConsulta = """
                SELECT COALESCE(SUM(at.quantidade * at.valor_unitario), 0) AS total
                  FROM planejamento_atividade at
                       INNER JOIN planejamento_acao a ON at.acao_id = a.id
                       INNER JOIN planejamento_metaunidade m ON a.meta_unidade_id = m.id
                       INNER JOIN planejamento_origemrecurso o ON at.tipo_recurso_id = o.id
                       INNER JOIN planejamento_naturezadespesa nat ON at.elemento_despesa_id = nat.id
                       INNER JOIN financeiro_naturezadespesa nat_desp ON nat.naturezadespesa_id = nat_desp.id
                 WHERE o.id = {}
                   AND nat_desp.tipo = '{}'
                   AND o.configuracao_id = {}
                   AND m.unidade_id = {}
            """.format(
                self.instance.origem_recurso.pk,
                'Custeio',
                configs.pk,
                self.cleaned_data['unidade'].pk,
            )

            atividade_total = db.get_dict(strConsulta)
            total_atividade = atividade_total[0]['total']
            if total_atividade > self.cleaned_data['valor_custeio']:
                raise forms.ValidationError('Este valor é inferior ao planejado nas atividades.')
            custeio_disponivel = (total_custeio + self.instance.valor_custeio) - total
        else:
            custeio_disponivel = total_custeio - total
        if custeio_disponivel < 0 or self.cleaned_data['valor_custeio'] > custeio_disponivel:
            raise forms.ValidationError(f'Este valor ultrapassou o valor de custeio da acão. Saldo Disponível: {format_money(custeio_disponivel)}')
        return self.cleaned_data['valor_custeio']


# -------------------------------------------------------------------------------
class ObjetivoEstrategicoForm(forms.ModelFormPlus):
    configuracao = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all(), widget=AutocompleteWidget(readonly=True))
    dimensao = forms.ModelChoiceField(
        label='Dimensão',
        help_text='Dimensão associada',
        queryset=Dimensao.objects.all(),
        widget=AutocompleteWidget(search_fields=Dimensao.SEARCH_FIELDS),
    )
    macro_projeto_institucional = forms.CharField(label='Macro Projeto Institucional', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}))
    descricao = forms.CharField(label='Objetivo Estratégico', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}))
    codigo = forms.IntegerFieldPlus(label='Código', max_length=4, required=False)

    class Meta:
        model = ObjetivoEstrategico
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configs = Configuracao.objects.all().order_by('-ano_base__ano')
        if configs.exists():
            self.fields['configuracao'].initial = configs[0]

        self.fields['configuracao'].widget.attrs['readonly'] = True
        user = self.request.user
        if not in_group(user, ['Administrador de Planejamento']):
            # verifica se existe uma dimensão cadastrada para o setor do usuário
            dimensao = Dimensao.objects.filter(setor_sistemico=get_setor_unidade_administrativa(user))
            if dimensao:
                if len(dimensao) == 1:
                    self.fields['dimensao'].initial = dimensao[0].id
                    self.fields['dimensao'].widget.readonly = True
                else:
                    self.fields['dimensao'] = forms.ModelChoiceField(label='Dimensão', help_text='Dimensão associada', queryset=dimensao)
            else:
                self.fields['dimensao'].widget.readonly = True

    def clean_codigo(self):
        if 'codigo' in self.cleaned_data:
            if self.cleaned_data['codigo'] and self.cleaned_data['configuracao'] and self.cleaned_data['dimensao']:
                codigo_objetivo = ObjetivoEstrategico.objects.filter(
                    configuracao=self.cleaned_data['configuracao'], codigo=self.cleaned_data['codigo'], dimensao=self.cleaned_data['dimensao']
                )
                if self.instance.pk is None:  # indica que o fomulário está sendo utilizado para cadastro e não edição
                    if len(codigo_objetivo):
                        raise forms.ValidationError('O código escolhido já está sendo usado para outro objetivo estratégico.')
                else:  # edicao
                    if len(codigo_objetivo) and codigo_objetivo[0].pk != self.instance.pk:
                        raise forms.ValidationError('O código escolhido já está sendo usado para outro objetivo estratégico.')
        return self.cleaned_data['codigo']

    def clean(self):
        super().clean()
        if 'configuracao' in self.cleaned_data and not self.cleaned_data['configuracao'].periodo_sistemico():
            raise forms.ValidationError('O período para o cadastro e edição de macro projeto institucional expirou.')
        return self.cleaned_data


# -------------------------------------------------------------------------------
class MetaForm(forms.ModelFormPlus):
    objetivo_estrategico = forms.ModelChoiceField(
        label='Macro Projeto Institucional',
        queryset=ObjetivoEstrategico.objects.all(),
        widget=AutocompleteWidget(search_fields=ObjetivoEstrategico.SEARCH_FIELDS),
    )
    titulo = forms.CharField(label='Título', widget=forms.TextInput(attrs={'size': '100'}))
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}))
    data_inicial = forms.DateFieldPlus(label='Data de início', help_text='Informe o início do período de execução.', required=True)
    data_final = forms.DateFieldPlus(
        label='Data de fim', help_text='Informe o fim do período de execução.', widget=BrDataWidget(show_label=False), required=True
    )
    codigo = forms.IntegerFieldPlus(label='Código', max_length=4, required=False)

    class Meta:
        model = Meta
        exclude = ('data_cadastro', 'unidade_medida')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # se tiver obj. estrategico na url, já preenche as datas
        if 'objetivo_estrategico' in self.request.GET:
            objetivo_estrategico = ObjetivoEstrategico.objects.get(pk=self.request.GET['objetivo_estrategico'])

            self.fields['objetivo_estrategico'].widget.readonly = True
            self.fields['data_inicial'].initial = objetivo_estrategico.configuracao.data_geral_inicial
            self.fields['data_final'].initial = objetivo_estrategico.configuracao.data_geral_final

        if self.instance.pk:
            self.fields['objetivo_estrategico'].widget.readonly = True

        # verifica se o usuário está cadastrando a partir da listagem de metas
        if 'objetivo_estrategico' not in self.request.GET and not self.instance.pk:
            config = Configuracao.objects.latest('ano_base__ano')

            self.fields['objetivo_estrategico'].queryset = ObjetivoEstrategico.objects.filter(configuracao=config)

    def clean_codigo(self):
        if 'codigo' in self.cleaned_data:
            if self.cleaned_data['codigo'] is not None:
                codigo_objetivo = Meta.objects.filter(
                    objetivo_estrategico=self.cleaned_data['objetivo_estrategico'], codigo=self.cleaned_data['codigo']
                )
                if self.instance.pk is None:  # indica que o fomulário está sendo utilizado para cadastro e não edição
                    if len(codigo_objetivo):
                        raise forms.ValidationError('O código escolhido já está sendo usado para outra Meta.')
                else:  # edicao
                    if len(codigo_objetivo) and codigo_objetivo[0].pk != self.instance.pk:
                        raise forms.ValidationError('O código escolhido já está sendo usado para outra Meta.')
        return self.cleaned_data['codigo']

    def clean(self):
        super().clean()
        if 'objetivo_estrategico' in self.cleaned_data and not self.cleaned_data['objetivo_estrategico'].configuracao.periodo_sistemico():
            raise forms.ValidationError('O período para o cadastro e edição de metas expirou.')

        if 'data_inicial' in self.cleaned_data and 'data_final' in self.cleaned_data:
            if self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
                self._errors['data_final'] = self.error_class(['A data limite deve ser maior que a data inicial.'])
                del self.cleaned_data['data_final']

        return self.cleaned_data


# -------------------------------------------------------------------------------
class MetaUnidadeForm(forms.ModelFormPlus):
    meta = forms.ModelChoiceField(label='Meta', queryset=Meta.objects.all(), widget=AutocompleteWidget(search_fields=Meta.SEARCH_FIELDS))
    unidade = forms.ModelChoiceField(label='Unidade', help_text='Unidade Administrativa', queryset=UnidadeAdministrativa.objects.all())
    quantidade = forms.IntegerFieldPlus(label='Quantidade', max_length=10, initial=1)
    valor_total = forms.DecimalFieldPlus(label='Valor Total', initial=Decimal('0.0'))

    class Meta:
        model = MetaUnidade
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # se a meta foi passada via url (get method) ou se trata de uma edição
        if 'meta' in self.request.GET:
            self.fields['unidade'].widget.choices = unidades_disponiveis_as_choices(self.request.GET['meta'])
            self.fields['meta'].widget.readonly = True

        if self.instance.pk:
            self.fields['unidade'].widget.choices = unidades_disponiveis_as_choices(self.instance.meta.id, self.instance.unidade.pk)
            self.fields['unidade'].initial = self.instance.unidade
            self.fields['meta'].widget.readonly = True

        # verifica se o usuário está cadastrando a partir da listagem de metas
        if 'meta' not in self.request.GET and not self.instance.pk:
            config = Configuracao.objects.latest('ano_base__ano')

            self.fields['meta'].queryset = Meta.objects.filter(objetivo_estrategico__configuracao=config)
            self.fields['unidade'].queryset = UnidadeAdministrativa.objects.filter(configuracao=config)

        """if 'id_meta' in kwargs:
            id_meta = kwargs.pop('id_meta')
            meta = Meta.objects.get(pk=id_meta)
            super(MetaUnidadeForm, self).__init__(*args, **kwargs)
            self.fields['meta'].initial = id_meta
            self.fields['unidade'].widget.choices = unidades_disponiveis_as_choices(id_meta)
        elif 'instance' in kwargs:
            metaunidade = kwargs['instance']
            super(MetaUnidadeForm, self).__init__(*args, **kwargs)
            opcoes = unidades_disponiveis_as_choices(metaunidade.meta.id, metaunidade.unidade.pk)
            if len(opcoes) == 1:
                self.fields['unidade'].widget = forms.HiddenInput()
                self.fields['unidade'].initial = metaunidade.unidade.id
            else:
                self.fields['unidade'].widget.choices = opcoes"""


class MetaUnidadeTodosCampiForm(forms.FormPlus):
    quantidade = forms.IntegerFieldPlus(label='Quantidade', max_length=10, required=False)
    valor_total = forms.DecimalFieldPlus(required=False)
    campi = forms.IntegerField(initial=1, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        id_meta = kwargs.pop('id_meta')
        Meta.objects.get(pk=id_meta)
        super().__init__(*args, **kwargs)


# -------------------------------------------------------------------------------
class AcaoPropostaForm(forms.ModelFormPlus):
    meta = forms.ModelChoiceField(label='Meta', queryset=Meta.objects.all(), widget=AutocompleteWidget(search_fields=Meta.SEARCH_FIELDS))
    titulo = forms.CharField(label='Título', max_length=250, widget=forms.TextInput(attrs={'size': '100'}))

    data_inicial = forms.DateFieldPlus(label='Período de Execução', help_text='Data de início', required=False)
    data_final = forms.DateFieldPlus(help_text='Data limite', widget=BrDataWidget(show_label=False), required=False)

    fonte_financiamento = forms.ModelChoiceField(
        label='Fonte', help_text='Fonte utilizada no financiamento da ação', queryset=FonteRecurso.objects.all()
    )
    codigo = forms.IntegerFieldPlus(
        label='Código',
        max_length=4,
        help_text='O código é gerado automaticamente.',
        required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),
    )

    class Meta:
        model = AcaoProposta
        exclude = ('data_cadastro', 'unidade_medida', 'acao_orcamento')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # se a meta foi passada via url (get method) ou se trata de uma edição
        if 'meta' in self.request.GET:
            meta = Meta.objects.get(pk=self.request.GET['meta'])
            # self.fields['unidade_medida'].initial = meta.unidade_medida.pk
            self.fields['data_inicial'].initial = meta.data_inicial
            self.fields['data_final'].initial = meta.data_final
            self.fields['meta'].widget.readonly = True
        if self.instance.pk:
            self.fields['meta'].widget.readonly = True

    def clean(self):
        super().clean()
        if 'meta' in self.cleaned_data and not self.cleaned_data['meta'].objetivo_estrategico.configuracao.periodo_sistemico():
            raise forms.ValidationError('O período para o cadastro e edição de ações propostas expirou.')
        return self.cleaned_data


# -------------------------------------------------------------------------------
class MetaUnidadeAcaoPropostaForm(forms.ModelFormPlus):
    meta_unidade = forms.ModelChoiceField(label='Unid. Administrativa', queryset=MetaUnidade.objects.all())
    acao_proposta = forms.ModelChoiceField(
        label='Ação Proposta', queryset=AcaoProposta.objects.all(), widget=AutocompleteWidget(search_fields=AcaoProposta.SEARCH_FIELDS)
    )
    quantidade = forms.IntegerFieldPlus(label='Quantidade', max_length=10, initial=1)
    valor_unitario = forms.DecimalFieldPlus(label='Valor Unitário')

    class Meta:
        model = MetaUnidadeAcaoProposta
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta_id = self.request.GET['meta']
        self.fields['meta_unidade'].queryset = MetaUnidade.objects.filter(meta__pk=meta_id)


# -------------------------------------------------------------------------------
class MetaUnidadeAcaoPropostaTodosCampiForm(forms.FormPlus):
    quantidade = forms.IntegerFieldPlus(label='Quantidade', max_length=10, required=False)
    valor_unitario = forms.DecimalFieldPlus(required=False)
    campi = forms.IntegerField(initial=1, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        id_acao_proposta = kwargs.pop('id_acao_proposta')
        AcaoProposta.objects.get(pk=id_acao_proposta)
        super().__init__(*args, **kwargs)


# -------------------------------------------------------------------------------
class AcaoBuscaForm(forms.FormPlus):
    titulo = forms.CharField(label='Título', required=True, widget=forms.TextInput(attrs={'size': '80'}))
    ano_base = forms.ModelChoiceField(
        label='Ano Base', empty_label='Todos', required=False, queryset=Configuracao.objects.all().order_by('-id'), widget=forms.Select()
    )


# -------------------------------------------------------------------------------
class AcaoForm(forms.ModelFormPlus):
    meta_unidade = forms.ModelChoiceField(
        label='Meta', queryset=MetaUnidade.objects.all(), widget=AutocompleteWidget(search_fields=MetaUnidade.SEARCH_FIELDS)
    )
    acao_indutora = forms.ModelChoiceField(
        label='Ação proposta', queryset=MetaUnidadeAcaoProposta.objects.all(), widget=AutocompleteWidget(readonly=True), required=False
    )
    titulo = forms.CharField(label='Título', widget=forms.TextInput(attrs={'size': '82'}))
    detalhamento = forms.CharField(label='Detalhamento', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}))

    setor_responsavel = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"10"}} - {{obj.nome}}',
        label='Setor',
        help_text='Setor Responsável',
        queryset=Setor.objects.suap_ativos().all(),
        widget=forms.Select(attrs={'class': 'monospace'}),
    )

    data_inicial = forms.DateFieldPlus(label='Período de Execução', help_text='Data de início', required=True)
    data_final = forms.DateFieldPlus(label='Período de Execução', help_text='Data limite', required=True)
    fonte_financiamento = forms.ModelChoiceField(
        label='Fonte', help_text='Fonte utilizada no financiamento da ação', queryset=FonteRecurso.objects.all()
    )

    valor_referencia = forms.DecimalFieldPlus(label='Valor de Referência', help_text='', required=False)
    codigo = forms.IntegerFieldPlus(
        label='Código',
        help_text='O código é gerado automaticamente.',
        max_length=4,
        required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),
    )

    class Meta:
        model = Acao
        exclude = ('status', 'data_cadastro', 'execucao', 'unidade_medida', 'quantidade', 'acao_orcamento')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # utilizado na importação de uma ação proposta
        if 'metaunidade_acaoproposta' in self.request.GET:
            mu_acaoproposta = MetaUnidadeAcaoProposta.objects.get(pk=self.request.GET['metaunidade_acaoproposta'])
            self.fields['acao_indutora'].initial = mu_acaoproposta
            self.fields['meta_unidade'].initial = mu_acaoproposta.meta_unidade
            self.fields['meta_unidade'].widget.readonly = True

            # bloqueia os campos que foram herdados de uma ação proposta e sugere os valores indicados na indução
            self.fields['titulo'].initial = mu_acaoproposta.acao_proposta.titulo
            self.fields['titulo'].widget.attrs['readonly'] = True
            self.fields['detalhamento'].widget.attrs['readonly'] = True
            self.fields['detalhamento'].required = False

            # será visualizado apenas o setores da unidade administrativa que cadastrou a ação
            setor_unidade_admin = mu_acaoproposta.meta_unidade.unidade.setor_equivalente
            self.fields['setor_responsavel'].queryset = (
                Setor.objects.suap_ativos().filter(id__in=setor_unidade_admin.ids_descendentes).order_by('sigla', 'nome')
            )

            self.fields['data_inicial'].initial = mu_acaoproposta.acao_proposta.data_inicial
            self.fields['data_final'].initial = mu_acaoproposta.acao_proposta.data_final

            #            self.fields['acao_orcamento'] = forms.ModelChoiceField(label=u'Ação do orçamento', queryset=financeiro.models.Acao.objects.all(), widget=AutocompleteWidget(readonly=True))
            #            self.fields['acao_orcamento'].initial = mu_acaoproposta.acao_proposta.acao_orcamento.pk
            self.fields['fonte_financiamento'] = forms.ModelChoiceField(
                label='Fonte de financiamento', queryset=financeiro.models.FonteRecurso.objects.all(), widget=AutocompleteWidget(readonly=True)
            )
            self.fields['fonte_financiamento'].initial = mu_acaoproposta.acao_proposta.fonte_financiamento.pk

            #            self.fields['unidade_medida'] = forms.ModelChoiceField(queryset=UnidadeMedida.objects.all(), widget=AutocompleteWidget(readonly=True))
            #            self.fields['unidade_medida'].initial = mu_acaoproposta.acao_proposta.unidade_medida
            #            self.fields['quantidade'].initial = mu_acaoproposta.quantidade
            # apresenta o campo valor de referência
            self.fields['valor_referencia'].initial = mu_acaoproposta.valor_unitario
            self.fields['valor_referencia'].widget.attrs['readonly'] = True
            self.fields['codigo'].initial = mu_acaoproposta.acao_proposta.codigo

        # cadastro de ações
        if 'meta_unidade' in self.request.GET:
            # utilizado em cadastro de ações
            # sugere os valores já cadastrados em uma meta
            meta_unidade = MetaUnidade.objects.get(id=self.request.GET['meta_unidade'])

            self.fields['meta_unidade'].widget.readonly = True
            self.fields['data_inicial'].initial = meta_unidade.meta.data_inicial
            self.fields['data_final'].initial = meta_unidade.meta.data_final
            #            self.fields['unidade_medida'].initial = meta_unidade.meta.unidade_medida

            # será visualizado apenas o setores da unidade administrativa que cadastrou a ação
            setor_unidade_admin = meta_unidade.unidade.setor_equivalente
            self.fields['setor_responsavel'].queryset = (
                Setor.objects.suap_ativos().filter(id__in=setor_unidade_admin.ids_descendentes).order_by('sigla', 'nome')
            )

        # edição da ação
        if self.instance.pk:
            self.fields['meta_unidade'].widget.readonly = True
            self.fields['setor_responsavel'].queryset = (
                Setor.objects.suap_ativos()
                .filter(id__in=self.instance.meta_unidade.unidade.setor_equivalente.ids_descendentes)
                .order_by('sigla', 'nome')
            )
            # impede que o usuário edite informações que foram importadas por uma ação proposta
            if self.instance.acao_indutora:
                self.fields['titulo'].widget.attrs['readonly'] = True
                self.fields['detalhamento'].widget.attrs['readonly'] = True
                self.fields['detalhamento'].required = False
                #                self.fields['acao_orcamento'] = forms.ModelChoiceField(queryset=financeiro.models.Acao.objects.all(), widget=AutocompleteWidget(readonly=True))
                self.fields['fonte_financiamento'] = forms.ModelChoiceField(
                    queryset=financeiro.models.FonteRecurso.objects.all(), widget=AutocompleteWidget(readonly=True)
                )

    #                self.fields['unidade_medida'] = forms.ModelChoiceField(queryset=UnidadeMedida.objects.all(), widget=AutocompleteWidget(readonly=True))

    def clean_data_inicial(self):
        if 'data_inicial' in self.cleaned_data and 'meta_unidade' in self.cleaned_data:
            if self.cleaned_data['data_inicial'] < self.cleaned_data['meta_unidade'].meta.data_inicial:
                raise forms.ValidationError('A data de início da execução deve coincidir com o período de execução da meta.')
            return self.cleaned_data['data_inicial']

    def clean_data_final(self):
        if 'data_final' in self.cleaned_data and 'data_inicial' in self.cleaned_data and 'meta_unidade' in self.cleaned_data:
            if self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
                raise forms.ValidationError('A data limite deve ser maior que a data inicial.')

            if self.cleaned_data['data_final'] > self.cleaned_data['meta_unidade'].meta.data_final:
                raise forms.ValidationError('A data final da execução deve coincidir com o período de execução da meta.')

            return self.cleaned_data['data_final']

    def clean(self):
        # o cadastro ou a edição só podem ser realizados se:
        # 1. está dentro do período de cadastro de ações
        # 2. está fora do período de cadastro de ações mas o status de parcialmente deferida indica a necessidade de mudança
        # 3. é a tentativa de importação de uma ação proposta
        if 'meta_unidade' in self.cleaned_data and (
            self.cleaned_data['meta_unidade'].meta.objetivo_estrategico.configuracao.periodo_campus
            or (
                not self.cleaned_data['meta_unidade'].meta.objetivo_estrategico.configuracao.periodo_campus
                and self.instance.status not in [Situacao.PENDENTE, Situacao.PARCIALMENTE_DEFERIDA]
            )
            or (
                not self.cleaned_data['meta_unidade'].meta.objetivo_estrategico.configuracao.periodo_campus
                and not self.instance.pk
                and 'acao_indutora' in self.cleaned_data
                and self.cleaned_data['acao_indutora']
            )
        ):
            return self.cleaned_data
        else:
            raise forms.ValidationError('O período para o cadastro e edição de ações expirou.')

    def save(self, commit=True):
        if in_group(self.request.user, ['Coordenador de Planejamento']):
            if self.instance.meta_unidade.meta.objetivo_estrategico.configuracao.periodo_validacao():
                self.instance.status = Situacao.PENDENTE
        return super().save(commit)


# -------------------------------------------------------------------------------
class AcaoExtraTetoForm(forms.ModelFormPlus):
    unidade = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeAdministrativa.objects.all(), widget=AutocompleteWidget(readonly=True)
    )
    titulo = forms.CapitalizeTextField(label='Título', widget=forms.TextInput(attrs={'size': '88'}), max_length=250)
    detalhamento = forms.CharField(label='Detalhamento', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}))
    quantidade = forms.IntegerFieldPlus(label='Quantidade', max_length=10)
    unidade_medida = forms.ModelChoiceField(label='Unidade de Medida', queryset=UnidadeMedida.objects.all().order_by('nome'))
    valor_previsto = forms.DecimalFieldPlus(label='Valor Previsto', help_text='')

    class Meta:
        model = AcaoExtraTeto
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configs = Configuracao.objects.all().order_by('-ano_base__ano')
        setor_unid_admin_usuario = get_setor_unidade_administrativa(self.request.user)

        strUnidadesAdm = f"""select u.setor_equivalente_id
                            from planejamento_unidadeadministrativa u, setor s
                            where s.id = u.setor_equivalente_id and
                                  u.setor_equivalente_id = {setor_unid_admin_usuario.id};"""

        unidades_admin = db.get_dict(strUnidadesAdm)
        if unidades_admin:
            unidade = UnidadeAdministrativa.objects.get(configuracao=configs[0], setor_equivalente=setor_unid_admin_usuario)
            self.fields['unidade'].initial = unidade.id

    def clean_unidade(self):
        if 'unidade' not in self.cleaned_data:
            raise forms.ValidationError('É necessário adicionar a Unidade Administrativa no planejamento atual.')
        return self.cleaned_data['unidade']


class AtividadeForm(forms.ModelFormPlus):
    acao = forms.ModelChoiceField(label='Ação', queryset=Acao.objects.all(), widget=AutocompleteWidget(readonly=True))
    descricao = forms.CapitalizeTextField(
        label='Descrição', help_text='Descrição da Atividade', max_length=300, widget=forms.TextInput(attrs={'size': '65'})
    )
    detalhamento = forms.CharField(label='Detalhamento', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}), required=False)
    unidade_medida = forms.ModelChoiceField(label='Unidade de Medida', queryset=UnidadeMedida.objects.all())
    quantidade = forms.IntegerFieldPlus(label='Quantidade', max_length=10)
    valor_total = forms.CharField(label='Total', widget=forms.TextInput(attrs={'disabled': 'disabled'}), required=False)
    elemento_despesa = forms.ModelChoiceField(label='Natureza de Despesa', queryset=NaturezaDespesa.objects.all())
    # O termo Origem de Recurso é utilizado a partir do planejamento 2014
    tipo_recurso = forms.ModelChoiceField(label='Origem de Recurso', queryset=OrigemRecurso.objects.filter(visivel_campus=True))

    class Meta:
        model = Atividade
        exclude = ('execucao',)

    class Media:
        js = ['/static/planejamento/js/AtividadeForm.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['quantidade'].widget.attrs['style'] = 'width: 60px;'

        # utilizado na importação de uma ação proposta
        if 'acao' in self.request.GET:
            acao = Acao.objects.get(id=self.request.GET['acao'])
            self.fields['unidade_medida'].initial = acao.unidade_medida
            self.fields['tipo_recurso'].queryset = self.fields['tipo_recurso'].queryset.filter(
                configuracao=acao.meta_unidade.meta.objetivo_estrategico.configuracao,
                origemrecursoua__unidade__setor_equivalente=acao.meta_unidade.unidade.setor_equivalente,
            )

        # edição
        if self.instance.pk:
            self.fields['tipo_recurso'].queryset = self.fields['tipo_recurso'].queryset.filter(
                configuracao=self.instance.acao.meta_unidade.meta.objetivo_estrategico.configuracao,
                origemrecursoua__unidade__setor_equivalente=self.instance.acao.meta_unidade.unidade.setor_equivalente,
            )

        self.fields['elemento_despesa'].widget.choices = naturezas_depesa_as_choices()

    def clean(self):
        if in_group(self.request.user, ['Coordenador de Planejamento']):
            if (
                'acao' in self.cleaned_data
                and not self.cleaned_data['acao'].meta_unidade.meta.objetivo_estrategico.configuracao.periodo_campus()
                and self.cleaned_data['acao'].status not in [Situacao.PARCIALMENTE_DEFERIDA, Situacao.PENDENTE]
            ):
                raise forms.ValidationError('O período de cadastro de atividades expirou.')

        # evita que o erro lançado pelo postgres seja disparado pelo template, já que a view não consegue reproduzir o erro formatado
        if 'acao' in self.cleaned_data and 'descricao' in self.cleaned_data and 'elemento_despesa' in self.cleaned_data:
            ats = Atividade.objects.filter(
                acao=self.cleaned_data['acao'], descricao=self.cleaned_data['descricao'], elemento_despesa=self.cleaned_data['elemento_despesa']
            )
            if len(ats) and ats[0].pk != self.instance.pk:
                self._errors['descricao'] = self.error_class(['Já existe atividade com essa descrição e natureza de despesa.'])

        if 'elemento_despesa' in self.cleaned_data:
            natureza = NaturezaDespesa.objects.get(naturezadespesa__naturezadespesa=self.cleaned_data['elemento_despesa'])
            tipo_recurso = self.cleaned_data['tipo_recurso']
            configs = Configuracao.objects.latest('ano_base__ano')
            ua = self.cleaned_data['acao'].meta_unidade.unidade

            strConsulta = f"""
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
                   AND o.configuracao_id = {configs.pk}
                   AND fn.tipo = '{natureza.naturezadespesa.tipo}'
                   AND mu.unidade_id = {ua.pk}
                   AND o.id = {tipo_recurso.pk}
            """

            atividade_total = db.get_dict(strConsulta)
            total_atividade = atividade_total[0]['total'] or 0
            total_atual = 0

            if 'quantidade' in self.cleaned_data and 'valor_unitario' in self.cleaned_data:
                total_atual = self.cleaned_data['quantidade'] * self.cleaned_data['valor_unitario']

            if natureza.naturezadespesa.tipo == 'Custeio':
                total = (
                    next(
                        iter(
                            OrigemRecursoUA.objects.filter(
                                unidade__setor_equivalente=self.cleaned_data['acao'].meta_unidade.unidade.setor_equivalente,
                                origem_recurso=self.cleaned_data['tipo_recurso'],
                            )
                            .aggregate(Sum('valor_custeio'))
                            .values()
                        )
                    )
                    or 0
                )
                custeio_disponivel = total - total_atividade
                if self.instance.pk and self.instance.elemento_despesa.naturezadespesa.tipo == natureza.naturezadespesa.tipo:
                    custeio_disponivel = total + (self.instance.valor_unitario * self.instance.quantidade) - total_atividade
                if custeio_disponivel < 0 or total_atual > custeio_disponivel:
                    self._errors['valor_unitario'] = self.error_class(
                        [f'Este valor ultrapassou o valor de custeio da atividade. Saldo Disponível: {format_money(custeio_disponivel)}']
                    )
                return self.cleaned_data

            elif natureza.naturezadespesa.tipo == 'Capital':
                total = (
                    next(
                        iter(
                            OrigemRecursoUA.objects.filter(
                                unidade__setor_equivalente=self.cleaned_data['acao'].meta_unidade.unidade.setor_equivalente,
                                origem_recurso=self.cleaned_data['tipo_recurso'],
                            )
                            .aggregate(Sum('valor_capital'))
                            .values()
                        )
                    )
                    or 0
                )
                capital_disponivel = total - total_atividade
                if self.instance.pk and self.instance.elemento_despesa.naturezadespesa.tipo == natureza.naturezadespesa.tipo:
                    capital_disponivel = total + (self.instance.valor_unitario * self.instance.quantidade) - total_atividade
                if capital_disponivel < 0 or total_atual > capital_disponivel:
                    self._errors['valor_unitario'] = self.error_class(
                        [f'Este valor ultrapassou o valor de capital da atividade. Saldo Disponível: {format_money(capital_disponivel)}']
                    )
                return self.cleaned_data
            else:
                self._errors['__all__'] = self.error_class(['A Natureza de Despesa escolhida não tem tipo de valor definido.'])
                return self.cleaned_data
        else:
            self._errors['elemento_despesa'] = self.error_class(['Este campo é obrigatório'])
            return self.cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        if in_group(self.request.user, ['Coordenador de Planejamento']):
            if self.instance.acao.meta_unidade.meta.objetivo_estrategico.configuracao.periodo_validacao():
                self.instance.acao.status = Situacao.PENDENTE
                self.instance.acao.save()
        return super().save(commit)


class AcaoExecucaoForm(forms.ModelFormPlus):
    acao = forms.ModelChoiceField(label='Ação', queryset=Acao.objects.all(), widget=forms.HiddenInput)
    texto = forms.CharField(label='Descrição', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}), required=True)
    percentual = forms.ChoiceField(
        label='Conclusão', help_text='Percentual de conclusão da ação', choices=PercentualExecucao.get_choices(), required=True
    )

    fieldsets = ((None, {'fields': ('acao', 'texto', 'percentual')}),)

    class Meta:
        model = AcaoExecucao
        exclude = ('data',)

    class Media:
        js = ['/static/planejamento/js/AcaoExecucaoForm.js']

    def __init__(self, *args, **kwargs):
        if 'id_acao' in kwargs:
            id_acao = kwargs.pop('id_acao')
            super().__init__(*args, **kwargs)

            acao = Acao.objects.get(id=id_acao)
            self.fields['acao'].initial = acao.id
            self.fields['percentual'].initial = acao.execucao


class AtividadeExecucaoForm(forms.ModelFormPlus):
    atividade = forms.ModelChoiceField(label='Atividade', queryset=Atividade.objects.all(), widget=forms.HiddenInput)
    texto = forms.CharField(label='Descrição', widget=forms.Textarea(attrs={'rows': '3', 'cols': '80'}), required=True)
    percentual = forms.ChoiceField(
        label='Conclusão', help_text='Percentual de conclusão da atividade', choices=PercentualExecucao.get_choices(), required=True
    )

    fieldsets = ((None, {'fields': ('atividade', 'texto', 'percentual')}),)

    class Meta:
        model = AtividadeExecucao
        exclude = ('data',)

    class Media:
        js = ['/static/planejamento/js/AtividadeExecucaoForm.js']

    def __init__(self, *args, **kwargs):
        if 'id_atividade' in kwargs:
            id_atividade = kwargs.pop('id_atividade')
            super().__init__(*args, **kwargs)

            atividade = Atividade.objects.get(id=id_atividade)
            self.fields['atividade'].initial = atividade.id
            self.fields['percentual'].initial = atividade.execucao


# apresenta um campo com a lista de todas as configuracoes - utilizado nos filtros dos relatórios
class ConfiguracaoFiltroForm(forms.FormPlus):
    configuracao = None

    def __init__(self, *args, **kwargs):
        if 'id_config' in kwargs:
            id_config = kwargs.pop('id_config')
            empty_label = kwargs.pop('empty_label') if 'empty_label' in kwargs else None

            super().__init__(*args, **kwargs)
            self.fields['configuracao'] = forms.ModelChoiceField(
                label='Ano Base',
                queryset=Configuracao.objects.all().order_by('-ano_base__ano'),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                empty_label=empty_label,
            )

            # filtra as origens de recurso pelo ano base da configuracao informada
            if id_config:
                configuracao = Configuracao.objects.get(id=id_config)
                self.fields['configuracao'].initial = configuracao.id
        else:
            super().__init__(*args, **kwargs)
            configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0].id
            self.fields['configuracao'] = forms.ModelChoiceField(
                label='Ano Base',
                queryset=Configuracao.objects.all().order_by('-ano_base__ano'),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                initial=configuracao,
            )


# apresenta um campo com a lista de todos os campi - utilizado nos filtros dos relatórios
class CampusFiltroForm(ConfiguracaoFiltroForm):
    campus = forms.ModelChoiceField(
        label='Unid. Administrativa',
        queryset=UnidadeAdministrativa.objects.filter(tipo=TipoUnidade.CAMPUS).order_by('setor_equivalente__nome'),
        widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
    )

    fieldsets = ((None, {'fields': ('configuracao', 'campus')}),)

    def __init__(self, *args, **kwargs):
        if 'id_configuracao' in kwargs:
            id_configuracao = kwargs.pop('id_configuracao')
        else:
            id_configuracao = Configuracao.objects.all().order_by('-ano_base')[0].id
        if 'id_campus' in kwargs:
            id_campus = kwargs.pop('id_campus')
            self.empty_label = kwargs.pop('empty_label') if 'empty_label' in kwargs else '---------'
            super().__init__(*args, **kwargs)

            # verifica se existe campus para o id informado
            if id_campus:
                campus = UnidadeAdministrativa.objects.get(setor_equivalente__id=id_campus, configuracao__id=id_configuracao)
                self.fields['campus'].initial = campus.id
        else:
            super().__init__(*args, **kwargs)

        super().__init__(*args, **kwargs)

        self.fields['campus'].queryset = self.fields['campus'].queryset.filter(configuracao__id=id_configuracao)


class RelatorioDetalhamentoForm(forms.FormPlus):
    configuracao = forms.ModelChoiceField(
        label='Ano Base', queryset=Configuracao.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )
    campus = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeAdministrativa.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    fieldsets = ((None, {'fields': ('configuracao', 'campus')}),)

    def __init__(self, *args, **kwargs):
        if 'id_configuracao' in kwargs:
            id_configuracao = kwargs.pop('id_configuracao')
            empty_label = kwargs.pop('empty_label', None)

            super().__init__(*args, **kwargs)
            self.fields['configuracao'].queryset = Configuracao.objects.all().order_by('-ano_base__ano')
            self.fields['configuracao'].empty_label = empty_label
            self.fields['campus'].queryset = UnidadeAdministrativa.objects.filter(configuracao__id=id_configuracao)
            # filtra as origens de recurso pelo ano base da configuracao informada
            if id_configuracao:
                configuracao = Configuracao.objects.get(id=id_configuracao)
                self.fields['configuracao'].initial = configuracao.id
        else:
            super().__init__(*args, **kwargs)
            configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0].id
            self.fields['configuracao'].queryset = Configuracao.objects.all().order_by('-ano_base__ano')
            self.fields['configuracao'].initial = configuracao
            self.fields['campus'].queryset = UnidadeAdministrativa.objects.filter(configuracao__id=configuracao)


class RelatorioOrigemRecursoForm(forms.FormPlus):
    configuracao = forms.ModelChoiceField(
        label='Ano Base', queryset=Configuracao.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )
    origemrecurso = forms.ModelChoiceField(
        label='Origem do Recurso', queryset=OrigemRecurso.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    fieldsets = ((None, {'fields': ('configuracao', 'origemrecurso')}),)

    def __init__(self, *args, **kwargs):
        if 'id_configuracao' in kwargs:
            id_configuracao = kwargs.pop('id_configuracao')
            origemrecurso = kwargs.pop('origemrecurso')
            empty_label = kwargs.pop('empty_label', None)

            super().__init__(*args, **kwargs)
            self.fields['configuracao'].queryset = Configuracao.objects.all().order_by('-ano_base__ano')
            self.fields['configuracao'].empty_label = empty_label
            self.fields['origemrecurso'] = forms.ModelChoiceField(
                label='Origem Recurso',
                queryset=OrigemRecurso.objects.filter(configuracao=id_configuracao),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                empty_label=empty_label,
            )

            if id_configuracao:
                configuracao = Configuracao.objects.get(id=id_configuracao)
                self.fields['configuracao'].initial = configuracao.id
            if origemrecurso:
                origemrecurso = OrigemRecurso.objects.get(id=origemrecurso)
                self.fields['origemrecurso'].initial = origemrecurso.id


class RelatorioCampusForm(forms.FormPlus):
    configuracao = forms.ModelChoiceField(
        label='Ano Base', queryset=Configuracao.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )
    campus = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeAdministrativa.objects.all(), widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    fieldsets = ((None, {'fields': ('configuracao', 'campus')}),)

    def __init__(self, *args, **kwargs):
        if 'id_config' in kwargs:
            id_configuracao = kwargs.pop('id_config')
            id_campus = kwargs.pop('id_campus')

            self.empty_label = kwargs.pop('empty_label') if 'empty_label' in kwargs else 'Todas'

            super().__init__(*args, **kwargs)
            self.fields['configuracao'].queryset = Configuracao.objects.all().order_by('-ano_base__ano')
            self.fields['campus'].queryset = UnidadeAdministrativa.objects.filter(configuracao__id=id_configuracao)

            if id_campus:
                campus = UnidadeAdministrativa.objects.get(setor_equivalente__id=id_campus, configuracao__id=id_configuracao)
                self.fields['campus'].initial = campus.id
            if id_configuracao:
                configuracao = Configuracao.objects.get(id=id_configuracao)
                self.fields['configuracao'].initial = configuracao.id

        else:
            super().__init__(*args, **kwargs)
            configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0].id
            self.fields['configuracao'].queryset = Configuracao.objects.all().order_by('-ano_base__ano')
            self.fields['configuracao'].initial = configuracao


# apresenta um campo com a lista de todas as dimensões - utilizado nos filtros dos relatórios
class DimensaoFiltroForm(forms.FormPlus):
    dimensao = None

    def __init__(self, *args, **kwargs):
        if 'id_dimensao' in kwargs:
            id_dimensao = kwargs.pop('id_dimensao')
            empty_label = kwargs.pop('empty_label') if 'empty_label' in kwargs else 'Todas'

            super().__init__(*args, **kwargs)
            self.fields['dimensao'] = forms.ModelChoiceField(
                label='Dimensão',
                queryset=Dimensao.objects.all().order_by('descricao'),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                empty_label=empty_label,
            )

            # verifica se existe campus para o id informado
            if id_dimensao:
                dimensao = Dimensao.objects.get(id=id_dimensao)
                self.fields['dimensao'].initial = dimensao.id


# apresenta um campo com a lista de todas as origens de recurso - utilizado nos filtros dos relatórios
class OrigemRecursoFiltroForm(forms.FormPlus):
    origem = None

    def __init__(self, *args, **kwargs):
        if 'id_origem' in kwargs:
            id_origem = kwargs.pop('id_origem')
            id_config = kwargs.pop('id_config') if 'id_config' in kwargs else None
            empty_label = kwargs.pop('empty_label') if 'empty_label' in kwargs else '---------'

            super().__init__(*args, **kwargs)

            # filtra as origens de recurso pelo ano base da configuracao informada
            if id_config:
                self.fields['origem'] = forms.ModelChoiceField(
                    label='Origem do Recurso',
                    queryset=OrigemRecurso.objects.filter(configuracao__id=id_config),
                    widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                    empty_label=empty_label,
                )
            else:
                self.fields['origem'] = forms.ModelChoiceField(
                    label='Origem do Recurso',
                    queryset=OrigemRecurso.objects.all(),
                    widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                    empty_label=empty_label,
                )

            # verifica se existe origem para o id informado
            if id_origem:
                origem = OrigemRecurso.objects.get(id=id_origem)
                self.fields['origem'].initial = origem.id


def get_situacoes_confirmacao():
    situacoes = []
    for key, value in Situacao.get_choices():
        if key != Situacao.PENDENTE:
            situacoes.append([key, value])
    return situacoes


class ConfirmacaoForm(forms.FormPlus):
    acao = forms.ModelChoiceField(label='Ação', queryset=Acao.objects.all(), widget=AutocompleteWidget(readonly=True))
    status_acao = forms.ChoiceField(label='Status', choices=get_situacoes_confirmacao(), required=True, widget=forms.RadioSelect)
    comentario_acao = forms.CharField(label='Comentário', max_length=500, widget=forms.Textarea, required=False)

    def __init__(self, *args, **kwargs):
        if 'id_acao' in kwargs:
            id_acao = kwargs.pop('id_acao')
            super().__init__(*args, **kwargs)

            acao = Acao.objects.get(id=id_acao)
            self.fields['acao'].initial = acao.id

    def clean(self):
        msg = {'motivo': 'Campo Motivo deve ser preenchido.', 'obrigatorio': 'Comentário Obrigatório'}
        if not self.errors:
            if not self.cleaned_data['status_acao']:
                self.errors['status_acao'] = [msg['motivo']]
            if self.cleaned_data['status_acao'] != 'Deferida' and self.cleaned_data['comentario_acao'] == '':
                self.errors['comentario_acao'] = [msg['obrigatorio']]
        return self.cleaned_data


# -------------------------------------------------------------------------------


class AcaoValidarFiltro(forms.FormPlus):
    ano = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all().order_by('-ano_base__ano'), empty_label=None)
    unidade = forms.ModelChoiceField(
        label='Unidade Administrativa', queryset=UnidadeAdministrativa.objects.all(), empty_label='TODAS AS UNIDADES ADMINISTRATIVAS', required=False
    )
    situacao = forms.ChoiceField(
        label='Situação',
        choices=(('todas', 'Todas as situações'), ('validadas', 'Ações avaliadas'), ('invalidadas', 'Ações não avaliadas')),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuracao = self.fields['ano'].queryset[0]
        self.fields['unidade'].queryset = UnidadeAdministrativa.objects.filter(configuracao=configuracao).order_by('setor_equivalente')


class AcaoAvaliacaoForm(forms.FormPlus):
    ano = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all().order_by('-ano_base__ano'), empty_label=None)
    unidade = forms.ModelChoiceField(
        label='Unidade Administrativa', queryset=UnidadeAdministrativa.objects.all(), empty_label='TODAS AS UNIDADES ADMINISTRATIVAS', required=False
    )
    situacao = forms.ChoiceField(label='Situação', choices=Situacao.get_choices(), required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuracao = self.fields['ano'].queryset[0]
        self.fields['unidade'].queryset = UnidadeAdministrativa.objects.filter(configuracao=configuracao).order_by('setor_equivalente')


class RelatorioOrigemRecursosForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Visualizar'
    ano = forms.ModelChoiceField(
        label='Ano Base', queryset=Configuracao.objects.filter(ano_base__ano__gte='2014').order_by('-ano_base__ano'), empty_label=None
    )
    origem = forms.ModelMultiplePopupChoiceField(OrigemRecurso.objects.all(), label='Origem de Recurso')
    unidade = forms.ModelMultiplePopupChoiceField(label='Unidade Administrativa', queryset=UnidadeAdministrativa.objects.all(), required=False)

    fieldsets = (('Filtros de Pesquisa', {'fields': ('ano', 'origem', 'unidade')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['origem'] = forms.MultipleModelChoiceField(
            label='Origem Recurso',
            queryset=OrigemRecurso.objects.all(),
            widget=AutocompleteWidget(
                search_fields=('nome',),
                multiple=True,
                form_filters=[('ano', 'configuracao__ano_base')],
            ),
        )
        self.fields['unidade'] = forms.MultipleModelChoiceField(
            label='Unidade Administrativa',
            queryset=UnidadeAdministrativa.objects.all(),
            required=False,
            widget=AutocompleteWidget(
                search_fields=UnidadeAdministrativa.SEARCH_FIELDS,
                multiple=True,
                form_filters=[('ano', 'configuracao__ano_base')],
            ),
        )


class PlanoAcaoForm(forms.FormPlus):
    ano_base = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all())

    METHOD = 'GET'
    fieldsets = ((None, {'fields': 'ano_base'}),)


class RenumeracaoAcaoForm(forms.FormPlus):
    ano_base = forms.ModelChoiceField(label='Ano Base', queryset=Configuracao.objects.all())

    METHOD = 'GET'
