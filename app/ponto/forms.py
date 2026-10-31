import datetime
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from django.contrib.contenttypes.models import ContentType
from django.db.models.query import QuerySet
from django.db.transaction import atomic
from django.utils.safestring import mark_safe

from comum.models import Configuracao, Ocupacao, PrestadorServico, User, Vinculo
from comum.utils import get_setor, get_uo
from djtools import forms
from djtools.forms.fields import DateFieldPlus, SelectDaysField
from djtools.forms.utils import render_field
from djtools.forms.widgets import AutocompleteWidget, TreeWidget
from djtools.html.calendarios import CalendarioPlus
from djtools.storages.utils import generate_filename
from djtools.utils import datas_entre, formata_segundos, get_session_cache
from ponto.compensacao import (
    CompensacaoHorarioAddFormUtils,
    Contexto,
    PeriodoInfo,
    PeriodoProcessamentoInfo,
    get_periodo_info,
    get_periodo_processamento_info,
)
from ponto.enums import TipoFormFrequenciaTerceirizados, TipoLiberacao
from ponto.exceptions import (
    PontoException,
)
from ponto.models import (
    AbonoChefia,
    DebitoExterno,
    DebitoExternoCadastro,
    DocumentoAnexo,
    Frequencia,
    HorarioCompensacao,
    Maquina,
    Observacao,
    RecessoDia,
    RecessoDiaEscolhido,
    RecessoOpcao,
    RecessoOpcaoEscolhida,
    RecessoPeriodo,
    RecessoPeriodoCompensacao,
    RecessoPeriodoEscolhido,
    RecessoPeriodoEscolhidoDiaIndividual,
    SaldoExterno,
    SolicitacaoAbonoParcial,
    SolicitacaoAbonoParcialGravidez,
    SolicitacaoRevisaoAbonoChefia,
    TipoAfastamento,
)
from ponto.utils import (
    get_data_ultimo_dia_mes_corrente,
    get_datas_dia_um_e_ultimo_dia_mes_passado,
    get_datas_segunda_feira_e_sexta_feira_semana_passada,
    get_total_tempo_debito_pendente_mes_anterior,
    get_total_tempo_debito_pendente_mes_corrente,
    get_total_tempo_debito_pendente_semana_anterior,
    get_total_tempo_saldo_restante_mes_corrente,
)
from rh.models import CargoEmprego, Servidor, Setor, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    tolerancia_15_min = forms.BooleanField(
        initial=False,
        label='Tolerância de 15 min para abono?',
        help_text='Marque essa opção para o suap considerar a tolerância de 15 minutos para abono de frequência.',
        required=False,
    )
    subnets_ponto_online = forms.CharFieldPlus(
        label='Subredes do Ponto Online',
        help_text='Informe as subredes (separadas por ";") através das quais será possível registrar o ponto online pelo SUAP. Utilize "0.0.0.0/0" para não restringir pelo IP do usuário.',
        required=False,
    )


class FrequenciaFormFactoryBase(forms.FormPlus):
    hoje = date.today()

    class Media:
        js = ('/static/js/frequencia-consulta-form.js',)

    faixa_0 = DateFieldPlus(initial=hoje, label='Início', required=True)
    faixa_1 = DateFieldPlus(initial=hoje, label='Término', required=True)
    so_inconsistentes = forms.BooleanField(initial=False, label='Apenas frequências inconsistentes', required=False)
    so_inconsistentes_apenas_esta_inconsistencia = forms.ChoiceField(
        choices=[],  # definido no __init__
        initial=None,
        label='Tipo de Inconsistência',
        required=False,
    )
    so_inconsistentes_situacao_abono = forms.ChoiceField(
        choices=[
            [Frequencia.SITUACAO_INCONSISTENCIA_DESCONSIDERAR_ABONO, 'Desconsiderar abono'],
            [Frequencia.SITUACAO_INCONSISTENCIA_COM_ABONO, 'Com abono'],
            [Frequencia.SITUACAO_INCONSISTENCIA_SEM_ABONO, 'Sem abono'],
            [Frequencia.SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO, 'Com ou sem abono'],
        ],
        initial=Frequencia.SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO,
        label='Situação das Inconsistências/Abono',
        required=False,
    )
    so_inconsistentes_situacao_debito = forms.ChoiceField(
        choices=[
            [Frequencia.SITUACAO_INCONSISTENCIA_DESCONSIDERAR_DEBITO, 'Desconsiderar débito'],
            [Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_TODO_COMPENSADO, 'Com débito totalmente compensado'],
            [Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_PARTE_COMPENSADO, 'Com débito parcialmente compensado'],
            [Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_NADA_COMPENSADO, 'Com débito sem nenhuma compensação'],
            [Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE, 'Com débito compensado ou não'],
        ],
        initial=Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE,
        label='Situação das Inconsistências/Débito de CH',
        required=False,
    )

    METHOD = 'GET'

    # calcula os dias que serão usados pelos EXTRA_BUTTONS a seguir
    seg_feira_semana_passada, sex_feira_semana_passada = get_datas_segunda_feira_e_sexta_feira_semana_passada()
    dia_um_mes_passado, ultimo_dia_mes_passado = get_datas_dia_um_e_ultimo_dia_mes_passado()
    dia_um_mes_atual = datetime.date(hoje.year, hoje.month, 1)
    ultimo_dia_mes_atual = get_data_ultimo_dia_mes_corrente()
    seg_feira_semana_atual = (seg_feira_semana_passada + timedelta(7)).date()
    sex_feira_semana_atual = (sex_feira_semana_passada + timedelta(7)).date()
    um_ano_atras = hoje - relativedelta(years=1)

    EXTRA_BUTTONS = [
        {
            'type': 'button',
            'value': 'Mês Passado',
            'name': '_continue',
            'class': 'btn sm btn-frequencias',
            'extra_attrs': {
                'id': 'btn-frequencias-mes-passado',
                'data-dia-inicial': dia_um_mes_passado.strftime('%Y-%m-%d'),
                'data-dia-final': ultimo_dia_mes_passado.strftime('%Y-%m-%d'),
            },
        },
        {
            'type': 'button',
            'value': 'Semana Passada',
            'name': '_continue',
            'class': 'btn sm btn-frequencias',
            'extra_attrs': {
                'id': 'btn-frequencias-semana-passada',
                'data-dia-inicial': seg_feira_semana_passada.strftime('%Y-%m-%d'),
                'data-dia-final': (sex_feira_semana_passada + timedelta(2)).strftime('%Y-%m-%d'),
            },
        },
        {
            'type': 'button',
            'value': 'Mês Atual',
            'name': '_continue',
            'class': 'btn sm btn-frequencias',
            'extra_attrs': {
                'id': 'btn-frequencias-mes-atual',
                'data-dia-inicial': dia_um_mes_atual.strftime('%Y-%m-%d'),
                'data-dia-final': ultimo_dia_mes_atual.strftime('%Y-%m-%d'),
            },
        },
        {
            'type': 'button',
            'value': 'Semana Atual',
            'name': '_continue',
            'class': 'btn sm btn-frequencias',
            'extra_attrs': {
                'id': 'btn-frequencias-semana-atual',
                'data-dia-inicial': seg_feira_semana_atual.strftime('%Y-%m-%d'),
                'data-dia-final': (sex_feira_semana_atual + timedelta(2)).strftime('%Y-%m-%d'),
            },
        },
        {
            'type': 'button',
            'value': 'Últimos 12 Meses ({} à {})'.format(um_ano_atras.strftime('%d/%m/%Y'), hoje.strftime('%d/%m/%Y')),
            'name': '_continue',
            'class': 'btn sm btn-frequencias',
            'extra_attrs': {
                'id': 'btn-frequencias-ultimo-ano',
                'data-dia-inicial': um_ano_atras.strftime('%Y-%m-%d'),
                'data-dia-final': hoje.strftime('%Y-%m-%d'),
            },
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # define as choices para o field so_inconsistentes_apenas_esta_inconsistencia
        so_inconsistentes_apenas_esta_inconsistencia_choices = [
            [None, 'Qualquer'],
            [Frequencia.INCONSISTENCIA_MENOR_JORNADA, Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_MENOR_JORNADA)],
            [Frequencia.INCONSISTENCIA_MAIOR_JORNADA, Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_MAIOR_JORNADA)],
            [Frequencia.INCONSISTENCIA_FALTA, Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_FALTA)],
            [
                Frequencia.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS,
                Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS),
            ],
            [Frequencia.INCONSISTENCIA_TRABALHO_FDS, Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_TRABALHO_FDS)],
            [
                Frequencia.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS,
                Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS),
            ],
        ]
        if Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_intervalo_inferior_1h_data_inicio'):
            so_inconsistentes_apenas_esta_inconsistencia_choices.append(
                [
                    Frequencia.INCONSISTENCIA_INTERVALO_INFERIOR_1H,
                    Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_INTERVALO_INFERIOR_1H),
                ]
            )
        if Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_intervalo_superior_3h_data_inicio'):
            so_inconsistentes_apenas_esta_inconsistencia_choices.append(
                [
                    Frequencia.INCONSISTENCIA_INTERVALO_SUPERIOR_3H,
                    Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_INTERVALO_SUPERIOR_3H),
                ]
            )
        if Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_nenhum_intervalo_data_inicio'):
            so_inconsistentes_apenas_esta_inconsistencia_choices.append(
                [
                    Frequencia.INCONSISTENCIA_NENHUM_INTERVALO,
                    Frequencia.DESCRICAO_INCONSISTENCIA.get(Frequencia.INCONSISTENCIA_NENHUM_INTERVALO),
                ]
            )
        self.fields['so_inconsistentes_apenas_esta_inconsistencia'].choices = so_inconsistentes_apenas_esta_inconsistencia_choices


def FrequenciaFuncionarioFormFactory(request):
    """
    Cria uma classe de formulário com base na permissão do usuário autenticado.
    """
    usuario = request.user
    funcionario_logado = usuario.get_relacionamento()
    vinculo = usuario.get_vinculo()
    initial_servidor = funcionario_logado if vinculo.eh_servidor else None
    queryset = Servidor.objects.all()
    if usuario.has_perm('ponto.pode_ver_frequencia_todos'):
        help_text = 'Pode ver frequência de todos os servidores do instituto.'
    else:
        help_text = []
        if usuario.has_perm('ponto.pode_ver_frequencia_campus'):
            help_text.append(
                'Pode ver frequência dos servidores do seu campus, ou que já foram do seu campus e de todos os setores em que teve função.'
            )

        elif vinculo.eh_servidor:
            help_text.append('Pode ver frequência dos servidores de todos os setores em que teve função.')

        elif usuario.has_perm('ponto.pode_ver_frequencia_propria') and funcionario_logado.eh_servidor:
            queryset = Servidor.objects.filter(pk=funcionario_logado.pk)
            help_text.append('Pode ver frequência própria.')

        help_text = ' '.join(help_text)

    class FrequenciaFuncionarioForm(FrequenciaFormFactoryBase):
        funcionario = forms.ModelChoiceField(
            queryset=queryset,
            widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
            help_text=help_text,
            initial=initial_servidor,
            label='Servidor',
        )

        mostrar_texto_observacoes = forms.BooleanField(label='Mostrar texto das observações', required=False)

        fieldsets = (
            (
                None,
                {
                    'fields': (
                        'funcionario',
                        ('faixa_0', 'faixa_1'),
                        ('mostrar_texto_observacoes',),
                        ('so_inconsistentes',),
                        ('so_inconsistentes_apenas_esta_inconsistencia', 'so_inconsistentes_situacao_abono', 'so_inconsistentes_situacao_debito'),
                    )
                },
            ),
        )

        def clean(self):
            if not self.cleaned_data.get('faixa_1') or not self.cleaned_data.get('faixa_0'):
                raise forms.ValidationError('Corrija os erros abaixo.')
            if self.cleaned_data['faixa_1'] < self.cleaned_data['faixa_0']:
                raise forms.ValidationError('Data Término não pode ser menor do que a Data Início.')
            if self.cleaned_data['faixa_1'] - self.cleaned_data['faixa_0'] > timedelta(days=366):
                raise forms.ValidationError('A diferença entre as datas não pode ser maior que 365 dias.')
            return self.cleaned_data

    return FrequenciaFuncionarioForm


def FrequenciaDocenteFormFactory(request):
    form_class = FrequenciaFuncionarioFormFactory(request)
    form_class.fieldsets = ((None, {'fields': ('funcionario', ('faixa_0', 'faixa_1'), ('so_inconsistentes',))}),)
    return form_class


def FrequenciasPorSetorFormFactory(request):
    hoje = date.today()

    class FormFrequenciaSetor(forms.FormPlus):
        METHOD = 'GET'
        setor = forms.ModelChoiceField(
            queryset=Setor.objects.suap_ativos(), widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS), initial=get_setor().id
        )
        recursivo = forms.BooleanField(required=False, label='Incluir Sub-setores?')
        faixa_0 = DateFieldPlus(initial=hoje, label='Início', required=True)
        faixa_1 = DateFieldPlus(initial=hoje, label='Término', required=True)

        def clean(self):
            super().clean()
            faixa_0 = self.cleaned_data.get('faixa_0')
            faixa_1 = self.cleaned_data.get('faixa_1')
            if faixa_0 and faixa_1 and (faixa_1 - faixa_0).days > 30:
                self.add_error('faixa_1', 'Faixa não deve exceder 30 dias!')
            return self.cleaned_data

        fieldsets = (('', {'fields': ('setor', 'recursivo', 'faixa_0', 'faixa_1')}),)

    return FormFrequenciaSetor


##############################
# Frequências de Estagiários #
##############################
def FrequenciaEstagiariosFormFactory(data=None):
    fields = {}
    fields['faixa_0'] = DateFieldPlus(initial=date.today(), label='Início')
    fields['faixa_1'] = DateFieldPlus(initial=date.today(), label='Término')
    fieldsets = ((None, {'fields': ('faixa_0', 'faixa_1')}),)

    return type(
        'FrequenciaEstagiariosForm',
        (forms.BaseForm,),
        {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'GET', 'TITLE': 'Frequências de Estagiários'},
    )


##############################
#     Frequência Noturna     #
##############################
def FrequenciaNoturnaFormFactory(user):
    CARGO_EMPREGO_CHOICES = [
        ['docente', 'Docente'],
        ['tecnico_administrativo', 'Técnico-Administrativo'],
        ['professor_substituto_temporario', 'Professor Substituto/Temporário'],
    ]
    hoje = date.today()

    class FormFrequenciaNoturnaSetor(forms.FormPlus):
        cargo_emprego = forms.ChoiceField(widget=forms.RadioSelect(), choices=CARGO_EMPREGO_CHOICES)
        uo = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.suap().all(), widget=forms.Select, label='Campus')
        faixa_0 = DateFieldPlus(initial=hoje, label='Início')
        faixa_1 = DateFieldPlus(initial=hoje, label='Término')

        METHOD = 'GET'

    return FormFrequenciaNoturnaSetor


############################
# Frequências de Bolsistas #
############################
def FrequenciaBolsistasFormFactory(data=None):
    fields = {}
    hoje = date.today()
    fields['faixa_0'] = DateFieldPlus(initial=hoje, label='Início')
    fields['faixa_1'] = DateFieldPlus(initial=hoje, label='Término')

    fieldsets = ((None, {'fields': ('faixa_0', 'faixa_1')}),)

    return type(
        'FrequenciaBolsistasForm',
        (forms.BaseForm,),
        {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'GET', 'TITLE': 'Frequências de Bolsistas'},
    )


################################
# Frequências de Terceirizados #
################################
def FrequenciaTerceirizadosFormFactory(request, tipo_form):
    """
    Retorna uma classe que serve para construção do formulário para listar
    frequências de todos os terceirizados da Instituição.
    """
    prestador = request.user.get_relacionamento()
    cpf = prestador.pessoa_fisica.cpf
    qs_prestador = PrestadorServico.objects.none()
    raiz = Setor.objects.suap_ativos().none()

    if request.user.has_perm('ponto.pode_ver_frequencia_terceirizados_todos'):
        raiz = Setor.raiz_suap()
        qs_prestador = PrestadorServico.objects.all()
    elif request.user.has_perm('ponto.pode_ver_frequencia_terceirizados_campus'):
        qs_prestador = PrestadorServico.objects.filter(setor__uo=prestador.setor.uo)
        raiz = prestador.setor.uo.setor
    elif request.user.has_perm('ponto.pode_ver_frequencia_terceirizados_setor'):
        qs_prestador = PrestadorServico.objects.filter(setor=prestador.setor)
        raiz = prestador.setor

    if request.user.has_perm('ponto.pode_ver_frequencia_terceirizados_propria'):
        qs_prestador = (qs_prestador | PrestadorServico.objects.filter(pessoa_fisica__cpf=cpf)).distinct()

    hoje = date.today()
    fields = {}
    fields['faixa_0'] = DateFieldPlus(initial=hoje, label='Início')
    fields['faixa_1'] = DateFieldPlus(initial=hoje, label='Término')

    fieldsets = ()

    if tipo_form == TipoFormFrequenciaTerceirizados.POR_SETOR:
        fieldsets = ((None, {'fields': ('setor', 'recursivo', ('faixa_0', 'faixa_1'), 'ocupacao')}),)
        fields['ocupacao'] = forms.ModelChoiceField(
            queryset=Ocupacao.objects.all(), widget=forms.Select, empty_label='Todos', label='Tipo prestador', required=False
        )
        fields['setor'] = forms.ModelChoiceField(
            queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(root_nodes=[raiz]), initial=get_setor().id
        )
        fields['recursivo'] = forms.BooleanField(required=False, label='Incluir Sub-setores?')

    if tipo_form == TipoFormFrequenciaTerceirizados.POR_TERCEIRIZADO:
        fields['terceirizado'] = forms.ModelChoiceFieldPlus(
            queryset=qs_prestador,
            widget=AutocompleteWidget(search_fields=PrestadorServico.SEARCH_FIELDS),
            initial=qs_prestador.filter(pessoa_fisica__cpf=cpf)[0] if qs_prestador.filter(pessoa_fisica__cpf=cpf).exists() else None,
        )
        fieldsets = ((None, {'fields': ('terceirizado', ('faixa_0', 'faixa_1'))}),)

    return type('FrequenciaTerceirizadosForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'GET'})


# Frequência de Setor
def setor_raiz_por_permissao_ponto(request):
    if request.user.has_perm('ponto.pode_ver_frequencia_todos') or request.user.has_perm('ponto.pode_ver_frequencias_enquanto_foi_chefe'):
        return Setor.raiz_suap()
    elif request.user.has_perm('ponto.pode_ver_frequencia_campus'):
        return request.user.get_vinculo().setor.uo.setor
    else:
        return Setor.objects.suap_ativos().none()


def FrequenciaCargoEmpregoFormFactory(data=None):
    hoje = date.today()

    class FormFrequenciaCargoEmprego(forms.FormPlus):
        cargo_emprego = forms.ModelChoiceField(queryset=CargoEmprego.utilizados.filter(excluido=False), widget=forms.Select)
        faixa_0 = DateFieldPlus(initial=hoje, label='Início')
        faixa_1 = DateFieldPlus(initial=hoje, label='Término')
        METHOD = 'GET'

        def clean(self):
            super().clean()
            faixa_0 = self.cleaned_data.get('faixa_0')
            faixa_1 = self.cleaned_data.get('faixa_1')
            if faixa_0 and faixa_1 and (faixa_1 - faixa_0).days > 30:
                self.add_error('faixa_1', 'Faixa não deve exceder 30 dias!')
            return self.cleaned_data

    return FormFrequenciaCargoEmprego


class MaquinaForm(forms.ModelFormPlus):
    usuarios = forms.MultipleModelChoiceFieldPlus(label='Usuários', required=False, queryset=User.objects.all())

    class Meta:
        model = Maquina
        exclude = ('versao_terminal',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap()


class ObservacaoForm(forms.ModelFormPlus):
    class Meta:
        model = Observacao
        exclude = ('pessoa', 'data')


class ObservacaoAdminForm(forms.ModelFormPlus):
    data = DateFieldPlus()

    class Meta:
        model = Observacao
        fields = ('data', 'descricao')

    def save(self, *args, **kwargs):
        self.instance.vinculo = self.request.user.get_vinculo()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.is_valid():
            is_superuser = self.request.user.is_superuser
            tem_abono = AbonoChefia.objects.filter(data=self.cleaned_data['data'], vinculo_pessoa=self.request.user.get_vinculo()).exists()
            if not is_superuser and tem_abono:
                raise forms.ValidationError('Existe uma ação da chefia imediata com relação à frequência inconsistente na data informada.')
        return self.cleaned_data


class LiberacaoForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap(), label='Unidade Organizacional', empty_label='Todas', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.is_superuser or self.request.user.has_perm('ponto.eh_gerente_sistemico_ponto'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().all()
        else:
            uo_logado = get_uo(self.request.user)
            if uo_logado:
                self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(id=uo_logado.pk)
            else:
                self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().none()

    """
    Assegura que a UO escolhida seja a da pessoa logada, a não ser que seja
    gerente_sistemico_ponto.
    """

    def clean_uo(self):
        if self.request.user.has_perm('ponto.eh_gerente_sistemico_ponto'):
            return self.cleaned_data['uo']
        else:
            if get_uo(self.request.user) != self.cleaned_data['uo']:
                raise forms.ValidationError('Sua Unidade Organizacional deve ser escolhida.')
            else:
                return self.cleaned_data['uo']

    def clean(self):
        clean = super().clean()
        if clean.get('tipo') == TipoLiberacao.get_numero(TipoLiberacao.LIBERACAO_PARCIAL):
            if not clean.get('ch_maxima_exigida') > 0:
                self.add_error(
                    'ch_maxima_exigida',
                    f"Para o tipo '{TipoLiberacao.LIBERACAO_PARCIAL}', a carga horária máxima exigida deve ser informada.",
                )
        else:
            clean['ch_maxima_exigida'] = 0  # força ZERO
        return clean


# FIXME: o ideal seria utilizar o daterange widget para tratar as duas datas do afastamento.
class AfastamentoForm(forms.ModelFormPlus):
    data_ini = DateFieldPlus()
    data_fim = DateFieldPlus()
    vinculo = forms.ModelChoiceField(queryset=Vinculo.objects.none(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS))
    tipo = forms.ModelChoiceField(queryset=TipoAfastamento.objects.all(), widget=AutocompleteWidget(search_fields=TipoAfastamento.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.filter(tipo_relacionamento=ContentType.objects.get(Vinculo.SERVIDOR))

    def clean(self):
        self.validate_unique()
        if not self.errors:
            if self.cleaned_data['data_ini'] > self.cleaned_data['data_fim']:
                raise forms.ValidationError('A data inicial é maior que a final')
        return self.cleaned_data


##########################################################################################
# COMPENSAÇÃO DE HORÁRIOS
##########################################################################################


def get_compensacao_horario_add_form_v2(
    request,
    periodo_data_inicial,
    periodo_data_final,
    periodo_objetivo: str,  # ver constantes PeriodoInfo.PERIODO_OBJETIVO_SALDO e PeriodoInfo.PERIODO_OBJETIVO_DEBITO
    omite_debitos_de_compensacoes_especificas: bool = False,
    abrange_apenas_debitos_dessas_compensacoes_especificas_ids: list[int] | None = None,
    omite_saldos_externos: bool = False,
    abrange_apenas_saldos_externos: bool = False,
    abrange_apenas_esses_saldos_externos_ids: list[int] | None = None,
) -> type:
    if abrange_apenas_esses_saldos_externos_ids is None:
        abrange_apenas_esses_saldos_externos_ids = []

    if abrange_apenas_debitos_dessas_compensacoes_especificas_ids is None:
        abrange_apenas_debitos_dessas_compensacoes_especificas_ids = []

    periodo = get_periodo_info(
        user=request.user,
        periodo_data_inicio=periodo_data_inicial,
        periodo_data_fim=periodo_data_final,
        periodo_objetivo=periodo_objetivo,
        omite_debitos_de_compensacoes_especificas=omite_debitos_de_compensacoes_especificas,
        abrange_apenas_debitos_dessas_compensacoes_especificas_ids=abrange_apenas_debitos_dessas_compensacoes_especificas_ids,
        omite_saldos_externos=omite_saldos_externos,
        abrange_apenas_saldos_externos=abrange_apenas_saldos_externos,
        abrange_apenas_esses_saldos_externos_ids=abrange_apenas_esses_saldos_externos_ids,
    )

    processamento = get_periodo_processamento_info(periodo_info=periodo, values=request.POST or None)

    form_fields: dict[str, Any] = {}  # {'fieldname': field}

    for field_name, field_value in processamento.fields.items():
        field_debito_compensacao = forms.TimeFieldPlus(widget=forms.HiddenInput, required=False, initial=field_value)
        form_fields[field_name] = field_debito_compensacao

    # prepara o calendário
    calendario = CalendarioPlus()
    calendario.mostrar_mes_e_ano = True
    calendario.envolve_mes_em_um_box = True
    calendario.destacar_hoje = False

    # para cada saldo (ponto batido), cria-se um evento no calendário no dia do saldo
    for data_saldo, saldo in list(periodo.saldos_disponiveis.items()):
        saldo_utilizado = processamento.saldos_utilizacao.get(data_saldo, 0)
        saldo_a_utilizar = saldo - saldo_utilizado

        link_frequencia = '/ponto/ver_frequencia/{}/?datas={}'.format(periodo.servidor.matricula, data_saldo.strftime('%d%m%Y'))

        info_saldo = (
            '<li class="calendario-item warning saldo">'
            ''
            '<span class="data" hidden="hidden">{data}</span>'
            '<span class="valor-em-segundos" hidden="hidden">{saldo_em_segundos}</span>'
            '<span class="valor-distribuido-em-segundos" hidden="hidden">{distribuindo_em_segundos}</span>'
            '<span class="valor-a-distribuir-em-segundos" hidden="hidden">{distribuir_em_segundos}</span>'
            ''
            '<h4>Saldo: <strong><span class="valor-a-distribuir-view">{saldo}</span></strong></h4>'
            ''
            '<dl>'
            '<dt>Distribuído</dt>'
            '<dd><span class="valor-distribuido-view">{saldo_distruibuido}</span></dd>'
            '</dl>'
            ''
            '<div class="clear"></div>'
            ''
            '<p>'
            '<a href="{link}" class="popup btn default">'
            '<i class="fas fa-clock" aria-hidden="true"></i> Frequência do Dia'
            '</a>'
            '</p>'
            '</li>'.format(
                data=data_saldo.strftime('%Y%m%d'),
                saldo_em_segundos=saldo,
                distribuindo_em_segundos=saldo_utilizado,
                distribuir_em_segundos=saldo_a_utilizar,
                saldo_distruibuido=formata_segundos(saldo_utilizado, '{h}h ', '{m}min ', '{s}seg ', True),
                saldo=formata_segundos(saldo_a_utilizar, '{h}h ', '{m}min ', '{s}seg ', True),
                link=link_frequencia,
            )
        )

        saldo_totalmente_utilizado_info = ''
        if saldo_a_utilizar > 0:
            saldo_totalmente_utilizado_info = 'hidden="hidden"'

        info_saldo += (
            f'<li class="calendario-item info saldo-totalmente-utilizado" {saldo_totalmente_utilizado_info}>'
            '<p><strong>Este saldo está sendo totalmente utilizado/distribuído.</strong></p>'
            '</li>'
        )

        #
        # adiciona no calendário
        calendario.adicionar_evento_calendario(data_inicio=data_saldo, data_fim=data_saldo, descricao=info_saldo, css_class='info', title='')

    ####
    # informações sobre os saldos externos

    infos_saldos_externos: OrderedDict[SaldoExterno, str] = OrderedDict()

    # para cada saldo externo, cria-se uma informação exclusiva
    for saldo_externo, saldo in periodo.saldos_externos_disponiveis.items():
        saldo_utilizado = processamento.saldos_externos_utilizacao.get(saldo_externo, 0)
        saldo_a_utilizar = saldo - saldo_utilizado

        link_detalhes = f'{saldo_externo.get_absolute_url()}'

        infos_saldos_externos[saldo_externo] = (
            '<div class="saldo saldo-externo">'
            ''
            '<span class="saldo-externo-id" hidden="hidden">{saldo_externo_id}</span>'
            '<span class="valor-em-segundos" hidden="hidden">{saldo_em_segundos}</span>'
            '<span class="valor-distribuido-em-segundos" hidden="hidden">{distribuindo_em_segundos}</span>'
            '<span class="valor-a-distribuir-em-segundos" hidden="hidden">{distribuir_em_segundos}</span>'
            ''
            '<h4>Saldo Externo #{saldo_id_display}</h4>'
            ''
            '<dl>'
            '<dt>Detalhamento</dt> '
            '<dd>{saldo_externo_detalhamento}</dd>'
            ''
            '<dt>Período dos Débitos</dt> '
            '<dd>{periodo_dos_debitos}</dd>'
            ''
            '<dt>Disponível</dt> '
            '<dd class="valor-a-distribuir-view">{saldo_display}</dd>'
            ''
            '<dt>Distribuído</dt> '
            '<dd class="valor-distribuido-view">{saldo_distruibuido_display}</dd>'
            '</dl>'
            ''
            '<div class="clear"></div>'
            ''
            '<p>'
            '<a href="{link}" class="popup btn default">'
            '<i class="fas fa-search" aria-hidden="true"></i> Detalhes'
            '</a>'
            '</p>'
            '</div>'.format(
                saldo_externo_id=saldo_externo.id,
                saldo_em_segundos=saldo,
                distribuindo_em_segundos=saldo_utilizado,
                distribuir_em_segundos=saldo_a_utilizar,
                saldo_id_display=saldo_externo.id,
                saldo_display=formata_segundos(saldo_a_utilizar, '{h}h ', '{m}min ', '{s}seg ', True),
                saldo_distruibuido_display=formata_segundos(saldo_utilizado, '{h}h ', '{m}min ', '{s}seg ', True),
                saldo_externo_detalhamento=saldo_externo.detalhamento,
                link=link_detalhes,
                periodo_dos_debitos=saldo_externo.get_periodo_saldo_display(),
            )
        )

    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        # adiciona os débitos ao calendário
        self.add_debitos_no_calendario()

    def add_debitos_no_calendario(self):
        datas_debito: list[date] = []

        datas_debito += list(self.debitos_saldos_utilizacao.keys())
        datas_debito += list(self.debitos_saldos_externos_utilizacao.keys())

        saldos_utilizados_total = 0

        for data_debito in sorted(set(datas_debito)):
            info_saldos_utilizados: list[str] = []

            # saldos utilizados (ponto batido)
            for data_saldo, saldo_utilizado in self.debitos_saldos_utilizacao.get(data_debito, {}).items():
                saldos_utilizados_total += saldo_utilizado

                field_name = CompensacaoHorarioAddFormUtils.get_field_name(data_debito, data_saldo)
                field_debito_compensacao_render = render_field(self, field_name)

                info_saldos_utilizados.append(
                    ''
                    '<span class="valor-em-segundos" hidden="hidden">{}</span>'
                    '<p>Saldo utilizado: <strong><span class="valor-view">{}</span></strong> ({}).</p>'
                    '{}'
                    ''.format(
                        saldo_utilizado,
                        formata_segundos(saldo_utilizado, '{h}h ', '{m}min ', '{s}seg ', True),
                        data_saldo.strftime('%d/%m/%Y'),
                        field_debito_compensacao_render,
                    )
                )

            # saldos externos utilizados
            for saldo_externo, saldo_utilizado in self.debitos_saldos_externos_utilizacao.get(data_debito, {}).items():
                saldos_utilizados_total += saldo_utilizado

                field_name = CompensacaoHorarioAddFormUtils.get_field_name_saldo_externo(data_debito, saldo_externo)
                field_debito_compensacao_render = render_field(self, field_name)

                info_saldos_utilizados.append(
                    ''
                    '<span class="valor-em-segundos" hidden="hidden">{}</span>'
                    '<p>Saldo utilizado: <strong><span class="valor-view">{}</span></strong> (Saldo Externo #{}).</p>'
                    '{}'
                    ''.format(
                        saldo_utilizado,
                        formata_segundos(saldo_utilizado, '{h}h ', '{m}min ', '{s}seg ', True),
                        saldo_externo.id,
                        field_debito_compensacao_render,
                    )
                )

            debito = self.debitos.get(data_debito, 0)
            debito_restante = debito - saldos_utilizados_total
            if debito_restante < 0:
                debito_restante = 0

            link_frequencia = '/ponto/ver_frequencia/{}/?datas={}'.format(periodo.servidor.matricula, data_debito.strftime('%d%m%Y'))

            info_debito = (
                '<li class="calendario-item danger debito">'
                ''
                '<span class="data" hidden="hidden">{data}</span>'
                '<span class="valor-em-segundos" hidden="hidden">{debito_em_segundos}</span>'
                '<span class="valor-compensado-em-segundos" hidden="hidden">{compensado_em_segundos}</span>'
                ''
                '<h4>Débito: <strong><span class="valor-restante-view">{debito_restante_display}</span></strong></h4>'
                ''
                '<dl>'
                '<dt>Compensando</dt>'
                '<dd><span class="valor-compensado-view">{saldo_utilizado_total_display}</span></dd>'
                '</dl>'
                ''
                '<div class="clear"></div>'
                ''
                '<p>'
                '<a href="{link}" class="popup btn default">'
                '<i class="fas fa-clock" aria-hidden="true"></i> Frequência do Dia'
                '</a>'
                '</p>'
                '</li>'.format(
                    data=data_debito.strftime('%Y%m%d'),
                    debito_em_segundos=debito,
                    compensado_em_segundos=saldos_utilizados_total,
                    saldo_utilizado_total_display=formata_segundos(saldos_utilizados_total, '{h}h ', '{m}min ', '{s}seg ', True),
                    debito_restante_display=formata_segundos(debito_restante, '{h}h ', '{m}min ', '{s}seg ', True),
                    link=link_frequencia,
                )
            )

            debito_totalmente_compensado_info = ''
            if debito > saldos_utilizados_total:
                debito_totalmente_compensado_info = 'hidden="hidden"'

            info_debito += (
                f'<li class="calendario-item info debito-totalmente-compensado" {debito_totalmente_compensado_info}>'
                '<p><strong>Este débito está sendo totalmente compensado.</strong></p>'
                '</li>'
            )

            # débito abaixo do mínimo?
            if debito < HorarioCompensacao.DEBITO_MINIMO_EM_SEGUNDOS:
                info_debito += '<li class="calendario-item info info-extra"><p>Débito abaixo de {}.</p></li>'.format(
                    formata_segundos(HorarioCompensacao.DEBITO_MINIMO_EM_SEGUNDOS, '{h}h ', '{m}min ', '{s}seg ', True)
                )

            # débito refere-se a um dia de compensação específica ?
            if data_debito in self.datas_debitos_especificos:
                compensacoes_especificas = self.compensacao_contexto.get_dia(data_debito).acompanhamentos_envolvidos_contendo_o_dia_como_debito

                for compensacao_especifica in compensacoes_especificas:
                    if abrange_apenas_debitos_dessas_compensacoes_especificas_ids:
                        if compensacao_especifica.id not in abrange_apenas_debitos_dessas_compensacoes_especificas_ids:
                            continue  # omite a informação
                    info_debito += f'<li class="calendario-item info info-extra"><p>Compensação Específica: <strong>{compensacao_especifica.recesso_opcao}</strong></p></li>'

                # houve carga horária trabalhada no dia em questão?
                if self.frequencias_no_periodo.filter(horario__date=data_debito).exists():
                    info_debito += '<li class="calendario-item info info-extra"><p>Carga Horária trabalhada não esperada.</p></li>'

            # exibe os saldos utilizados pelo débito
            for info_saldo_utilizado in info_saldos_utilizados:
                info_debito += f'<li class="calendario-item extra saldo-utilizado">{info_saldo_utilizado}</li>'

            # adiciona o débito no calendário, criando um evento no calendário no dia do débito
            self.calendario.adicionar_evento_calendario(
                data_inicio=data_debito, data_fim=data_debito, descricao=info_debito, css_class='danger', title=''
            )

    @property
    def media(self):
        return forms.Media(css={}, js=('/static/js/ponto-util-v2.js', '/static/js/informar-compensacao-v2.js'))

    def form_rendered(self):
        # A renderização deste form não segue o padrão label: field.
        #
        # Os fields serão renderizados em um calendário de eventos via método djtools.forms.utils.render_field.
        #
        # Esse código foi baseado no templatetag djtools.forms.utils.render_form, o qual cria o conteúdo HTML
        # para um form com as seguintes seções:
        #   1) erros do formulário
        #   2) fields do formulário
        #
        # No caso deste form, este método substituírá (não chamará) a implementação de djtools.forms.utils.render_form.
        #
        # Para isso, foi refatorada a tag djtools.templatetags.tags.RenderFormNode:
        #   - se o form já possui o atributo 'rendered', não precisa criá-lo (via djtools.forms.utils.render_form)

        periodo_renderizado_data_inicial = self.periodo_total_data_inicial
        periodo_renderizado_data_final = self.periodo_total_data_final

        out = [
            '<div>',
            #########################################
            # seção 1) erros do formulário
            #          copiado de "djtools.forms.utils.render_form"
            f'<ul class="errorlist">{"".join([f"<li>{error}</li>" for error in self.non_field_errors()])}</ul>' if self.non_field_errors() else '',
            #########################################
            # seção 2) fields do formulário via conteúdo HTML específico (no conteúdo do evento do calendário) no qual
            #          os fields são inseridos em locais que não seguem o padrão "label: field", MAS são renderizados
            #          via "djtools.forms.utils.render_field" (aproveitamento o código de renderizção de um formfield)
            self.calendario.formato_periodo(
                mes_inicio=periodo_renderizado_data_inicial.month,
                ano_inicio=periodo_renderizado_data_inicial.year,
                mes_fim=periodo_renderizado_data_final.month,
                ano_fim=periodo_renderizado_data_final.year,
                omite_mes_sem_eventos=True,
            )
            if self.calendario.eventos
            else '',
            '</div>',
        ]
        return mark_safe(''.join(out))

    def clean(self):
        clean = super(self.__class__, self).clean()

        ####
        # validações

        ####
        # 1) o total de saldo utilizado deve existir e ser menor ou igual ao total de saldo disponível
        total_saldo = self.saldo_total_em_segundos
        total_saldo_utilizado = 0  # em segundos (soma novamente, confirmando o valor)

        saldos_utilizados: dict[date, int] = OrderedDict()
        debitos_saldos_utilizados: dict[date, dict[date, int]] = OrderedDict()
        saldos_externos_utilizados: dict[SaldoExterno, int] = OrderedDict()
        debitos_saldos_externos_utilizados: dict[date, dict[SaldoExterno, int]] = OrderedDict()

        for field_info in CompensacaoHorarioAddFormUtils.get_fields_infos(self.fields.keys(), self.cleaned_data):
            saldo_utilizado = Frequencia.time_para_segundos(field_info.field_value)

            if saldo_utilizado:
                total_saldo_utilizado += saldo_utilizado

                data_debito = field_info.data_debito
                data_saldo = field_info.data_saldo
                saldo_externo_id = field_info.saldo_externo_id

                if data_saldo:
                    if data_saldo not in saldos_utilizados:
                        saldos_utilizados[data_saldo] = 0

                    saldos_utilizados[data_saldo] += saldo_utilizado

                    if data_debito not in debitos_saldos_utilizados:
                        debitos_saldos_utilizados[data_debito] = OrderedDict()

                    if data_saldo not in debitos_saldos_utilizados[data_debito]:
                        debitos_saldos_utilizados[data_debito][data_saldo] = 0

                    debitos_saldos_utilizados[data_debito][data_saldo] += saldo_utilizado

                if saldo_externo_id:
                    saldo_externo = SaldoExterno.objects.filter(id=saldo_externo_id).first()

                    if saldo_externo:
                        if saldo_externo not in saldos_externos_utilizados:
                            saldos_externos_utilizados[saldo_externo] = 0

                        saldos_externos_utilizados[saldo_externo] += saldo_utilizado

                        if data_debito not in debitos_saldos_externos_utilizados:
                            debitos_saldos_externos_utilizados[data_debito] = OrderedDict()

                        if saldo_externo not in debitos_saldos_externos_utilizados[data_debito]:
                            debitos_saldos_externos_utilizados[data_debito][saldo_externo] = 0

                        debitos_saldos_externos_utilizados[data_debito][saldo_externo] += saldo_utilizado

        if not total_saldo_utilizado > 0:
            self.add_error(None, 'Nenhuma compensação de horário foi informada.')

        if total_saldo_utilizado > total_saldo:
            self.add_error(None, 'A carga horária total utilizada/distribuída é maior que o saldo total a utilizar.')

        ####
        # 2) os saldos utilizados por cada débito devem ser possíveis de utilização pelo débito em questão
        # 3) o total dos saldos utilizados por cada débito deve ser menor ou igual ao débito em questão

        debitos_saldos_utilizados_totais: dict[date, int] = OrderedDict()

        # saldos (ponto batido)
        for data_debito, saldos in list(debitos_saldos_utilizados.items()):
            total_saldo_utilizado_pelo_debito = 0

            for data_saldo, saldo_utilizado in list(saldos.items()):
                pode_compensar = data_saldo in self.compensacao_contexto.get_dia(data_debito).debito_dias_dos_saldos

                if not pode_compensar:
                    self.add_error(
                        None,
                        'O Saldo em {} não pode ser utilizado para compensar o Débito em {}. Saldo fora do período de compensação do Débito.'.format(
                            data_saldo.strftime('%d/%m/%Y'), data_debito.strftime('%d/%m/%Y')
                        ),
                    )

                total_saldo_utilizado_pelo_debito += saldo_utilizado

            if data_debito not in debitos_saldos_utilizados_totais:
                debitos_saldos_utilizados_totais[data_debito] = 0

            debitos_saldos_utilizados_totais[data_debito] += total_saldo_utilizado_pelo_debito

        # saldos externos
        for data_debito, saldos in list(debitos_saldos_externos_utilizados.items()):
            total_saldo_utilizado_pelo_debito = 0

            for saldo_externo, saldo_utilizado in list(saldos.items()):
                # o saldo externo pode ser utilizado pelo débito?
                # pode_compensar = saldo_externo.data_inicio <= data_debito <= saldo_externo.data_fim
                pode_compensar = saldo_externo.pode_ser_utilizado_neste_debito(data_debito)

                if not pode_compensar:
                    self.add_error(
                        None,
                        'O Saldo Externo "{}" não pode ser '
                        'utilizado para compensar o Débito em {}. '
                        'Débito fora do período de utilização do Saldo.'.format(saldo_externo, data_debito.strftime('%d/%m/%Y')),
                    )

                total_saldo_utilizado_pelo_debito += saldo_utilizado

            if data_debito not in debitos_saldos_utilizados_totais:
                debitos_saldos_utilizados_totais[data_debito] = 0

            debitos_saldos_utilizados_totais[data_debito] += total_saldo_utilizado_pelo_debito

        # saldos utilizados somados
        for data_debito, total_saldo_utilizado in list(debitos_saldos_utilizados_totais.items()):
            if data_debito in self.debitos:
                if total_saldo_utilizado > self.debitos[data_debito]:
                    self.add_error(
                        None,
                        'O total de Saldo Utilizado para compensar o Débito em {} ({}) é maior que o próprio Débito ({}).'.format(
                            data_debito.strftime('%d/%m/%Y'), total_saldo_utilizado, self.debitos[data_debito]
                        ),
                    )
            else:
                self.add_error(None, 'O Débito em {} não foi encontrado.'.format(data_debito.strftime('%d/%m/%Y')))

        ####
        # 4) os saldos utilizados por data do saldo deve ser menor ou igual ao saldo restante no dia em questão
        # 5) os saldos utilizados por saldo externo deve ser menor ou igual ao saldo externo restante em questão

        # saldos utilizados (ponto batido)
        for data_saldo, saldo_utilizado in list(saldos_utilizados.items()):
            if data_saldo in self.saldos:
                if saldo_utilizado > self.saldos[data_saldo]:
                    self.add_error(
                        None,
                        'O total de utilização ({}) do Saldo Produzido em {} é maior que o próprio Saldo Restante ({}).'.format(
                            formata_segundos(saldo_utilizado, '{h}h ', '{m}min ', '{s}seg ', True),
                            data_saldo.strftime('%Y/%m/%d'),
                            formata_segundos(self.saldos[data_saldo], '{h}h ', '{m}min ', '{s}seg ', True),
                        ),
                    )
            else:
                self.add_error(None, 'O Saldo em {} não foi encontrado.'.format(data_saldo.strftime('%d/%m/%Y')))

        # saldos externos utilizados
        for saldo_externo, saldo_utilizado in list(saldos_externos_utilizados.items()):
            if saldo_externo in self.saldos_externos:
                valor_saldo_restante = saldo_externo.valor_saldo_restante
                if saldo_utilizado > valor_saldo_restante:
                    self.add_error(
                        None,
                        'O total de utilização ({}) do Saldo Externo "{}" é maior que o próprio Saldo Restante ({}).'.format(
                            formata_segundos(saldo_utilizado, '{h}h ', '{m}min ', '{s}seg ', True),
                            saldo_externo,
                            formata_segundos(valor_saldo_restante, '{h}h ', '{m}min ', '{s}seg ', True),
                        ),
                    )
            else:
                self.add_error(None, f'O Saldo Externo "{saldo_externo}" não foi encontrado.')

        return clean

    def save(self):
        # retorna uma lista com os informes de compensação salvos
        processamento: PeriodoProcessamentoInfo = self.processamento
        compensacoes_salvas: list[HorarioCompensacao] = processamento.salva_compensacoes(fields_values=self.cleaned_data)
        if compensacoes_salvas:
            get_session_cache(self.request, 'total_tempo_debito_pendente_semana_anterior', get_total_tempo_debito_pendente_semana_anterior, 5 * 60)
            get_session_cache(self.request, 'total_tempo_debito_pendente_mes_anterior', get_total_tempo_debito_pendente_mes_anterior, 5 * 60)
            get_session_cache(self.request, 'total_tempo_debito_pendente_mes_corrente', get_total_tempo_debito_pendente_mes_corrente, 5 * 60)
            get_session_cache(self.request, 'total_tempo_saldo_restante_mes_corrente', get_total_tempo_saldo_restante_mes_corrente, 5 * 60)

        return compensacoes_salvas

    return type(
        'CompensacaoHorarioAddFormV2',
        (forms.BaseForm,),
        {
            'processamento': processamento,
            'base_fields': form_fields,
            'compensacao_contexto': periodo.compensacao_contexto,
            'saldos': periodo.saldos_disponiveis,
            'saldo_total_em_segundos': periodo.saldo_total_em_segundos,
            'saldo_total_view': formata_segundos(periodo.saldo_total_em_segundos, '{h:2d}h ', '{m:2d}min ', '{s:02d}seg ', True),
            'saldo_total_distribuido_em_segundos': processamento.saldo_total_distribuido_em_segundos,
            'saldo_total_distribuido_view': formata_segundos(
                processamento.saldo_total_distribuido_em_segundos, '{h:2d}h ', '{m:2d}min ', '{s:2d}seg ', True
            ),
            'saldo_total_a_distribuir_em_segundos': processamento.saldo_total_a_distribuir_em_segundos,
            'saldo_total_a_distribuir_view': formata_segundos(
                processamento.saldo_total_a_distribuir_em_segundos, '{h:2d}h ', '{m:2d}min ', '{s:2d}seg ', True
            ),
            'saldos_utilizacao': processamento.saldos_utilizacao,
            'saldos_externos': list(periodo.saldos_externos_disponiveis.keys()),
            'saldos_externos_utilizacao': processamento.saldos_externos_utilizacao,
            'infos_saldos_externos': infos_saldos_externos,
            'tem_saldos': bool(periodo.saldos_disponiveis or periodo.saldos_externos_disponiveis),
            'tem_saldos_utilizados': bool(processamento.saldos_utilizacao or processamento.saldos_externos_utilizacao),
            'debitos': periodo.debitos_pendentes,
            'debitos_saldos_utilizacao': processamento.debitos_saldos_utilizacao,
            'debitos_saldos_externos_utilizacao': processamento.debitos_saldos_externos_utilizacao,
            'debito_total_em_segundos': periodo.debito_total_em_segundos,
            'debito_total_view': formata_segundos(periodo.debito_total_em_segundos, '{h:2d}h ', '{m:2d}min ', '{s:2d}seg ', True),
            'debito_total_compensado_em_segundos': processamento.debito_total_compensado_em_segundos,
            'debito_total_compensado_view': formata_segundos(
                processamento.debito_total_compensado_em_segundos, '{h:2d}h ', '{m:2d}min ', '{s:2d}seg ', True
            ),
            'debito_total_restante_em_segundos': processamento.debito_total_restante_em_segundos,
            'debito_total_restante_view': formata_segundos(
                processamento.debito_total_restante_em_segundos, '{h:2d}h ', '{m:2d}min ', '{s:2d}seg ', True
            ),
            'compensacoes_especificas': periodo.compensacoes_especificas,
            'datas_debitos_especificos': periodo.datas_debitos_especificos,
            'periodo_objetivo_display': periodo.get_periodo_objetivo_display(),
            'periodo_data_inicial': periodo.periodo_data_inicio,
            'periodo_data_final': periodo.periodo_data_fim,
            'periodo_envolvido_data_inicial': periodo.periodo_envolvido_data_inicio,
            'periodo_envolvido_data_final': periodo.periodo_envolvido_data_fim,
            'periodo_envolvido_eh_valido': periodo.periodo_envolvido_eh_valido,
            'periodo_envolvido_eh_dos_saldos': periodo.periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_DEBITO,
            'periodo_envolvido_eh_dos_debitos': periodo.periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_SALDO,
            'periodo_total_data_inicial': periodo.periodo_total_data_inicio,
            'periodo_total_data_final': periodo.periodo_total_data_fim,
            'frequencias_no_periodo': periodo.frequencias_no_periodo,
            'calendario': calendario,
            'add_debitos_no_calendario': add_debitos_no_calendario,
            'rendered': form_rendered,
            'METHOD': 'POST',
            '__init__': __init__,
            'media': media,
            'clean': clean,
            'save': save,
            'SUBMIT_LABEL': 'Salvar',
            'request': request,
        },
    )


class HorarioCompensacaoEditarObservacoesPontoForm(forms.ModelFormPlus):
    class Meta:
        model = HorarioCompensacao
        fields = ('observacoes',)


class RecessoOpcaoForm(forms.ModelFormPlus):
    tipo_display = forms.CharField(
        label='Tipo',
        initial='Livre Escolha de Dias/Períodos',
        help_text='Dias/Períodos podem ser escolhidos pelos servidores. Ex: Recesso de Fim de Ano.',
    )

    class Meta:
        model = RecessoOpcao
        fields = (
            'tipo_display',
            'descricao',
            'publico_alvo_servidores',
            'publico_alvo_campi',
            'qtde_max_dias_escolhidos',
            'qtde_max_periodos_escolhidos',
            'periodo_de_escolha_data_inicial',
            'periodo_de_escolha_data_final',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['publico_alvo_campi'].queryset = UnidadeOrganizacional.objects.suap().all()
        self.fields['tipo_display'].widget.attrs['readonly'] = 'readonly'

    def save(self, commit=True):
        if not self.instance.id:
            self.instance.tipo = RecessoOpcao.TIPO_PERMITE_ESCOLHA_LIVRE
            self.instance.responsavel = self.request.user.get_relacionamento()
        return super().save(commit)


class RecessoOpcaoOutroForm(forms.ModelFormPlus):
    tipo_display = forms.CharField(
        label='Tipo', initial='Escolha Impositiva de Dias/Períodos', help_text='Dias/Períodos são atribuídos aos servidores.'
    )

    class Meta:
        model = RecessoOpcao
        fields = ('tipo_display', 'descricao', 'publico_alvo_servidores', 'publico_alvo_campi')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_display'].widget.attrs['readonly'] = 'readonly'

    def save(self, commit=True):
        if not self.instance.id:
            self.instance.tipo = RecessoOpcao.TIPO_OUTRO
            self.instance.responsavel = self.request.user.get_relacionamento()
        return super().save(commit)


class RecessoDiaAddForm(forms.ModelFormPlus):
    data_inicial = forms.DateFieldPlus(label='Data Inicial', required=False)
    data_final = forms.DateFieldPlus(label='Data Final', required=False)

    def __init__(self, *args, **kwargs):
        self.recesso_opcao = kwargs.pop('recesso_opcao', None)
        self.is_data_unica = kwargs.pop('is_data_unica', False)
        assert self.recesso_opcao is not None
        super().__init__(*args, **kwargs)

    def clean(self):
        clean = super().clean()

        data_inicial, data_final = self._clean_get_datas()

        if data_inicial and data_final:
            for data in datas_entre(data_inicial, data_final):
                if RecessoDia.objects.filter(data=data, recesso_opcao__id=self.recesso_opcao.id).exists():
                    self.add_error(None, f'Dia {data.strftime("%d/%m/%Y")} já adicionado.')

        return clean

    def _clean_get_datas(self):
        clean = self.cleaned_data

        data_inicial = clean.get('data_inicial')
        data_final = clean.get('data_final')

        if self.is_data_unica:
            if not data_inicial:
                self.add_error('data_inicial', 'Data não informada.')
            data_final = data_inicial
        else:
            if data_inicial and data_final:
                if data_inicial > data_final:
                    self.add_error('data_inicial', 'Data inicial deve ser menor ou igual à data final.')
            else:
                self.add_error(None, 'Informe a data inicial e a data final.')

        clean['data_inicial'] = data_inicial
        clean['data_final'] = data_final

        return data_inicial, data_final

    def save(self, commit=True):
        data_inicial, data_final = self._clean_get_datas()
        recesso_dia = None
        if data_inicial and data_final:
            for data in datas_entre(data_inicial, data_final):
                recesso_dia = RecessoDia()
                recesso_dia.recesso_opcao = self.recesso_opcao
                recesso_dia.data = data
                recesso_dia.save()
        return recesso_dia  # retorna o último dia salvo do período informado

    class Meta:
        model = RecessoDia
        fields = ('data_inicial', 'data_final')


class RecessoPeriodoAddForm(forms.ModelFormPlus):
    class Meta:
        model = RecessoPeriodo
        fields = ('data_inicio', 'data_fim', 'descricao', 'qtde_max_dias_a_escolher', 'dias_excluidos')
        help_texts = {'descricao': 'Ex: Semana do natal, Semana do ano novo, etc.'}

    def __init__(self, *args, **kwargs):
        self.recesso_opcao = kwargs.pop('recesso_opcao', None)
        assert self.recesso_opcao is not None
        super().__init__(*args, **kwargs)

    def clean(self):
        clean = super().clean()

        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        qtde_max_dias_a_escolher = self.cleaned_data.get('qtde_max_dias_a_escolher')

        if data_inicio and data_fim:
            if RecessoPeriodo.objects.filter(data_inicio=data_inicio, data_fim=data_fim, recesso_opcao__id=self.recesso_opcao.id).exists():
                self.add_error(None, 'Período já adicionado.')

            if data_inicio > data_fim:
                self.add_error('data_inicio', 'Data Início deve ser menor ou igual à Data Fim.')

            if qtde_max_dias_a_escolher:
                total_dias_no_periodo = (data_fim - data_inicio).days + 1
                if qtde_max_dias_a_escolher > total_dias_no_periodo:
                    self.add_error(
                        'qtde_max_dias_a_escolher',
                        f'Quantidade máxima de dias a escolher ({qtde_max_dias_a_escolher}) não pode ser maior que o total de dias no período ({total_dias_no_periodo}).',
                    )

        return clean

    def save(self, commit=True):
        self.instance.recesso_opcao = self.recesso_opcao
        return super().save(commit)


class RecessoPeriodoCompensacaoAddForm(forms.ModelFormPlus):
    data_inicial = forms.DateFieldPlus(label='Data Inicial', required=False)
    data_final = forms.DateFieldPlus(label='Data Final', required=False)

    def __init__(self, *args, **kwargs):
        self.recesso_opcao = kwargs.pop('recesso_opcao', None)
        self.is_data_unica = kwargs.pop('is_data_unica', False)
        assert self.recesso_opcao is not None
        super().__init__(*args, **kwargs)

    def clean(self):
        clean = super().clean()

        data_inicial, data_final = self._clean_get_datas()

        if data_inicial and data_final:
            # período conflita com outro já cadastrado?
            pass

        return clean

    def _clean_get_datas(self):
        clean = self.cleaned_data

        data_inicial = clean.get('data_inicial')
        data_final = clean.get('data_final')

        if self.is_data_unica:
            if not data_inicial:
                self.add_error('data_inicial', 'Data não informada.')

            data_final = data_inicial
        else:
            if data_inicial and data_final:
                if data_inicial > data_final:
                    self.add_error('data_inicial', 'Data inicial deve ser menor ou igual à data final.')
            else:
                self.add_error(None, 'Informe a data inicial e a data final.')

        clean['data_inicial'] = data_inicial
        clean['data_final'] = data_final

        return data_inicial, data_final

    def save(self, commit=True):
        self.instance.recesso_opcao = self.recesso_opcao
        return super().save(commit)

    class Meta:
        model = RecessoPeriodoCompensacao
        exclude = ()


class RecessoPeriodoEscolhaForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert self.instance is not None

    def clean(self):
        clean = super().clean()
        data_inicial = clean.get('periodo_de_escolha_data_inicial')
        data_final = clean.get('periodo_de_escolha_data_final')
        apenas_uma_data_foi_informada = (data_inicial and not data_final) or (not data_inicial and data_final)
        if apenas_uma_data_foi_informada:
            self.add_error(None, 'Defina as duas datas do período ou deixe-as em branco.')
        if data_inicial and data_final and data_inicial > data_final:
            self.add_error(None, 'A data inicial deve ser menor ou igual a data final.')
        return clean

    class Meta:
        model = RecessoOpcao
        fields = ('periodo_de_escolha_data_inicial', 'periodo_de_escolha_data_final')


def get_type_form_dias_ou_periodos_escolhidos(request, recesso_opcao=None):
    """
    Etapa de escolha dos dias ou períodos por parte dos funcionários/servidores.

    Form
        Fieldset (para cada ponto.RecessoOpcao)
            Field (BooleanField para cada Dia de ponto.RecessoDia)
            Field (SelectDaysField para cada Período de ponto.RecessoPeriodo)
        ...
    """

    _funcionario = request.user.get_relacionamento()

    # escolhe/modifica dias ou períodos
    modo_add = bool(not recesso_opcao)

    recessos_opcoes = RecessoOpcao.get_recessos_opcoes_com_dias_ou_periodos_a_escolher_hoje(_funcionario)

    # determina o escopo dos dias/períodos de recesso que podem ser escolhidos
    if modo_add:
        dias_recesso = RecessoDia.objects.filter(
            recesso_opcao__in=(
                recessos_opcoes.get('com_dias_ou_periodos_a_escolher')
                | recessos_opcoes.get('com_dias_ou_periodos_a_editar')
                | recessos_opcoes.get('com_dias_ou_periodos_a_remarcar')
            )
        )
        periodos_recesso = RecessoPeriodo.objects.filter(
            recesso_opcao__in=(
                recessos_opcoes.get('com_dias_ou_periodos_a_escolher')
                | recessos_opcoes.get('com_dias_ou_periodos_a_editar')
                | recessos_opcoes.get('com_dias_ou_periodos_a_remarcar')
            )
        )
    else:
        dias_recesso = RecessoDia.objects.filter(
            recesso_opcao=recesso_opcao,
            recesso_opcao__in=(
                recessos_opcoes.get('com_dias_ou_periodos_a_editar')
                | recessos_opcoes.get('com_dias_ou_periodos_a_remarcar')
                | recessos_opcoes.get('com_dias_ou_periodos_que_ainda_pode_editar')
            ),
        )
        periodos_recesso = RecessoPeriodo.objects.filter(
            recesso_opcao=recesso_opcao,
            recesso_opcao__in=(
                recessos_opcoes.get('com_dias_ou_periodos_a_editar')
                | recessos_opcoes.get('com_dias_ou_periodos_a_remarcar')
                | recessos_opcoes.get('com_dias_ou_periodos_que_ainda_pode_editar')
            ),
        )

    # {'fieldname': field}
    fields = {}

    # {'opcao_recesso.id': [{'opcao_recesso': ..., 'periodos_recesso': [...]}, {'fields': ['fieldname', ...],}), ...]
    fieldsets = {}

    # dias a escolher
    # fieldname = 'dia_recesso_ID'

    qs_base_dia_escolhido = RecessoDiaEscolhido.objects.select_related(
        'recesso_opcao_escolhida__funcionario', 'recesso_opcao_escolhida__recesso_opcao'
    ).filter(recesso_opcao_escolhida__funcionario=_funcionario)

    for dia_recesso in dias_recesso:
        dia_recesso_ja_escolhido = qs_base_dia_escolhido.filter(
            recesso_opcao_escolhida__recesso_opcao=dia_recesso.recesso_opcao, dia=dia_recesso
        ).first()

        fieldname = f'dia_recesso_{dia_recesso.id}'
        fields[fieldname] = forms.BooleanField(
            label=f'Dia {dia_recesso.data.strftime("%d/%m/%Y")}', required=False, initial=bool(dia_recesso_ja_escolhido)
        )

        fieldset_key = f'{dia_recesso.recesso_opcao.id}'
        if fieldset_key not in fieldsets:
            fieldsets[fieldset_key] = [{'opcao_recesso': dia_recesso.recesso_opcao, 'periodos_recesso': []}, {'fields': []}]

        fieldsets[fieldset_key][1]['fields'].append(fieldname)

    # períodos a escolher
    # fieldname = 'periodo_recesso_ID'

    qs_base_periodo_escolhido = RecessoPeriodoEscolhido.objects.select_related(
        'recesso_opcao_escolhida__funcionario', 'recesso_opcao_escolhida__recesso_opcao'
    ).filter(recesso_opcao_escolhida__funcionario=_funcionario)

    for periodo_recesso in periodos_recesso:
        periodo_dias_definidos = periodo_recesso.get_dias_definidos()
        periodo_dias_escolhidos = []
        for dia in periodo_dias_definidos:
            dia_ja_escolhido = qs_base_periodo_escolhido.filter(
                recesso_opcao_escolhida__recesso_opcao=periodo_recesso.recesso_opcao,
                periodo=periodo_recesso,
                periodos_escolhidos_dias_individuais__dia=dia,
            ).first()
            if dia_ja_escolhido:
                periodo_dias_escolhidos.append(dia)

        periodo_recesso_ja_escolhido = qs_base_periodo_escolhido.filter(
            recesso_opcao_escolhida__recesso_opcao=periodo_recesso.recesso_opcao, periodo=periodo_recesso
        ).first()

        fieldname = f'periodo_recesso_{periodo_recesso.id}'
        fields[fieldname] = SelectDaysField(
            label=f'Período {periodo_recesso}',
            required=False,
            initial={
                'all_selected': (bool(periodo_recesso_ja_escolhido)) and not periodo_dias_escolhidos,
                'days_selected': periodo_dias_escolhidos,
            },
            days_choices=periodo_dias_definidos,
            can_select_all=not periodo_recesso.qtde_max_dias_a_escolher,
            label_all_select='Todo o período',
            label_custom_select='Dias específicos',
        )

        fieldset_key = f'{periodo_recesso.recesso_opcao.id}'
        if fieldset_key not in fieldsets:
            fieldsets[fieldset_key] = [{'opcao_recesso': periodo_recesso.recesso_opcao, 'periodos_recesso': []}, {'fields': []}]

        fieldsets[fieldset_key][0]['periodos_recesso'].append(periodo_recesso)
        fieldsets[fieldset_key][1]['fields'].append(fieldname)

    # acrescenta title, description e field do chefe imediato/validador para cada fieldset que representa uma opção de recesso

    for recesso_opcao_id, info in fieldsets.items():
        recesso_opcao = info[0]['opcao_recesso']
        periodos_recesso = info[0]['periodos_recesso']

        fieldset_title = f'{recesso_opcao}'

        fieldset_description_info = []
        fieldset_description_warning = []
        fieldset_description_danger = []

        if recesso_opcao.qtde_max_dias_escolhidos or recesso_opcao.qtde_max_periodos_escolhidos:
            if recesso_opcao.qtde_max_dias_escolhidos:
                if recesso_opcao.qtde_max_dias_escolhidos == 1:
                    fieldset_description_info.append('Você pode escolher até <strong>1 dia</strong>.')
                else:
                    fieldset_description_info.append(f'Você pode escolher até <strong>{recesso_opcao.qtde_max_dias_escolhidos} dias</strong>.')

            if recesso_opcao.qtde_max_periodos_escolhidos:
                if recesso_opcao.qtde_max_periodos_escolhidos == 1:
                    fieldset_description_info.append('Você pode fazer escolhas em até <strong>1 período</strong>.')
                else:
                    fieldset_description_info.append(
                        f'Você pode fazer escolhas em até <strong>{recesso_opcao.qtde_max_periodos_escolhidos} períodos</strong>.'
                    )

        for periodo_recesso in periodos_recesso:
            if periodo_recesso.qtde_max_dias_a_escolher:
                if periodo_recesso.qtde_max_dias_a_escolher == 1:
                    fieldset_description_info.append(f'Período <strong>{periodo_recesso}</strong>: você pode escolher até <strong>1 dia</strong>.')
                else:
                    fieldset_description_info.append(
                        f'Período <strong>{periodo_recesso}</strong>: você pode escolher até <strong>{periodo_recesso.qtde_max_dias_a_escolher} dias</strong>.'
                    )

        fieldset_description_info.append(f'Prazo final até <strong>{recesso_opcao.periodo_de_escolha_data_final.strftime("%d/%m/%Y")}</strong>.')

        minha_escolha = RecessoOpcaoEscolhida.objects.filter(funcionario=_funcionario, recesso_opcao__id=recesso_opcao_id).first()

        if minha_escolha:
            chefes = minha_escolha.chefes

            if minha_escolha.validador:
                # pode ser um validador que tenha sido escolhido manualmente pelo superusuario
                chefe_escolhido_manual = Servidor.objects.filter(id=minha_escolha.validador.id).first()
                if chefe_escolhido_manual:
                    chefes = [*chefes, chefe_escolhido_manual]

            if minha_escolha.validacao == RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR:
                fieldset_description_danger.append(f'<strong>Validação</strong>: {minha_escolha.get_validacao_display()}')
                fieldset_description_danger.append(f'(Motivo: {minha_escolha.motivo_nao_autorizacao}).')
            elif minha_escolha.validacao != RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO:
                fieldset_description_warning.append(f'<strong>Validação</strong>: {minha_escolha.get_validacao_display()}')
        else:
            # inicia uma escolha
            minha_escolha = RecessoOpcaoEscolhida(funcionario=_funcionario)
            chefes = minha_escolha.chefes
            if chefes:
                # sugere o primeiro chefe da lista
                minha_escolha.validador = chefes[0]

        fieldsets[recesso_opcao_id][0] = fieldset_title
        fieldsets[recesso_opcao_id][1]['description'] = ''

        if fieldset_description_info:
            fieldsets[recesso_opcao_id][1]['description'] += f"""
                <div class="alert alert-info">
                    <p><strong>Atenção</strong>:</p>
                    <ul>
                        {''.join([f'<li>{msg_info}</li>' for msg_info in fieldset_description_info])}
                    </ul>
                </div>
            """
        fieldsets[recesso_opcao_id][1]['description'] += (
            f'<p class="alert alert-danger mt-1 mb-1">{" ".join(fieldset_description_danger)}</p>' if fieldset_description_danger else ''
        )
        fieldsets[recesso_opcao_id][1]['description'] += (
            f'<p class="alert alert-warning mt-1 mb-1">{" ".join(fieldset_description_warning)}</p>' if fieldset_description_warning else ''
        )

        chefe_queryset = Servidor.objects.filter(id__in=[chefe.id for chefe in chefes])
        chefe_initial = minha_escolha.validador
        fieldname = f'validador_chefe_imediato_{recesso_opcao_id}'
        fields[fieldname] = forms.ModelChoiceField(
            label='Chefe Imediato/Validador', required=False, queryset=chefe_queryset, initial=chefe_initial.id if chefe_initial else None
        )

        fieldsets[recesso_opcao_id][1]['fields'].insert(0, fieldname)

    if not fields:
        raise Exception('Não há dias ou períodos disponíveis para escolher ou modificar.')

    fieldsets = list(fieldsets.values())

    def clean(self):
        funcionario = self.request.user.get_relacionamento()

        # validação para a qtd escolhida por opção de recesso
        recesso_dias_escolhidos = {}  # {recesso_opcao_id: [recesso_opcao, qtd_dias_escolhidos]}
        recesso_periodos_escolhidos = {}  # {recesso_opcao_id: [recesso_opcao, qtd_periodos_escolhidos]}

        # validação para a qtd de dias escolhidos por período
        periodo_dias_escolhidos = {}  # {periodo_id: [periodo, qtd_dias_escolhidos]}

        for field_name in self.fields:
            # dias escolhidos

            # True/False
            dia_foi_escolhido = 'dia_recesso_' in field_name and self.cleaned_data.get(field_name, False)

            if dia_foi_escolhido:
                dia_recesso_id = field_name.replace('dia_recesso_', '')
                dia_recesso = RecessoDia.objects.filter(id=dia_recesso_id).first()

                if dia_recesso:
                    # o funcionário pode escolher esse dia? Se for útil para ele, sim.
                    is_dia_util = HorarioCompensacao.is_dia_util(funcionario.get_vinculo(), dia_recesso.data)
                    if not is_dia_util[0]:
                        self.add_error(field_name, 'Não é um dia útil para você: {}'.format('. '.join(is_dia_util[1])))

                    recesso_opcao = dia_recesso.recesso_opcao
                    if recesso_opcao.id not in recesso_dias_escolhidos:
                        recesso_dias_escolhidos[recesso_opcao.id] = [recesso_opcao, 0]

                    # incrementa qtde de dias escolhidos
                    recesso_dias_escolhidos[recesso_opcao.id][1] += 1

            # períodos escolhidos

            eh_field_periodo_recesso = 'periodo_recesso_' in field_name

            if eh_field_periodo_recesso:
                periodo_recesso_fieldvalue = self.cleaned_data.get(field_name, {})
                periodo_foi_escolhido = periodo_recesso_fieldvalue.get('all_selected', False) or periodo_recesso_fieldvalue.get(
                    'days_selected', False
                )

                if periodo_foi_escolhido:
                    periodo_recesso_id = field_name.replace('periodo_recesso_', '')
                    periodo_recesso = RecessoPeriodo.objects.filter(id=periodo_recesso_id).first()

                    if periodo_recesso:
                        for periodo_dia_escolhido in periodo_recesso_fieldvalue.get('days_selected', []):
                            # o funcionário pode escolher esse dia? Se for útil para ele, sim.
                            is_dia_util = HorarioCompensacao.is_dia_util(funcionario.get_vinculo(), periodo_dia_escolhido)
                            if not is_dia_util[0]:
                                self.add_error(
                                    field_name,
                                    f'{periodo_dia_escolhido.strftime("%d/%m/%Y")} não é um dia útil para você: {". ".join(is_dia_util[1])}',
                                )

                        # incrementa qtde de períodos escolhidos do recesso relacionado
                        recesso_opcao = periodo_recesso.recesso_opcao
                        if recesso_opcao.id not in recesso_periodos_escolhidos:
                            recesso_periodos_escolhidos[recesso_opcao.id] = [recesso_opcao, 0]
                        recesso_periodos_escolhidos[recesso_opcao.id][1] += 1

                        # incrementa qtde de dias escolhidos do período em questão
                        if periodo_recesso.id not in periodo_dias_escolhidos:
                            periodo_dias_escolhidos[periodo_recesso.id] = [periodo_recesso, 0]
                        periodo_dias_escolhidos[periodo_recesso.id][1] += len(periodo_recesso_fieldvalue.get('days_selected', []))

        # valida a quantidade de dias escolhidos por opção de recesso
        for recesso_opcao, qtd_dias_escolhidos in recesso_dias_escolhidos.values():
            qtd_max_dias_a_escolher = recesso_opcao.qtde_max_dias_escolhidos
            if qtd_max_dias_a_escolher and qtd_dias_escolhidos > qtd_max_dias_a_escolher:
                self.add_error(None, f"Recesso '{recesso_opcao}': você pode escolher, no máximo, {qtd_max_dias_a_escolher} dia(s).")

        # valida a quantidade de períodos escolhidos por opção de recesso
        for recesso_opcao, qtd_periodos_escolhidos in recesso_periodos_escolhidos.values():
            qtd_max_periodos_a_escolher = recesso_opcao.qtde_max_periodos_escolhidos
            if qtd_max_periodos_a_escolher and qtd_periodos_escolhidos > qtd_max_periodos_a_escolher:
                self.add_error(None, f"Recesso '{recesso_opcao}': você pode fazer escolhas em, no máximo, {qtd_max_periodos_a_escolher} período(s).")

        # valida a quantidade de dias escolhidos por período de recesso
        for periodo_recesso, qtd_dias_escolhidos in periodo_dias_escolhidos.values():
            qtd_max_dias_a_escolher = periodo_recesso.qtde_max_dias_a_escolher
            if qtd_max_dias_a_escolher and qtd_dias_escolhidos > qtd_max_dias_a_escolher:
                self.add_error(
                    f'periodo_recesso_{periodo_recesso.id}', f'Você pode escolher, no máximo, {qtd_max_dias_a_escolher} dia(s) neste período.'
                )

        return self.cleaned_data

    @atomic
    def save(self):
        funcionario = self.request.user.get_relacionamento()
        recesso_opcoes_escolhidas = []

        for field_name in self.fields:
            dia_escolha = 'dia_recesso_' in field_name
            periodo_escolha = 'periodo_recesso_' in field_name

            dia_recesso = None
            periodo_recesso = None
            recesso_opcao = None

            if dia_escolha:
                dia_recesso_id = field_name.replace('dia_recesso_', '')
                dia_recesso = RecessoDia.objects.filter(id=dia_recesso_id).first()
                recesso_opcao = dia_recesso.recesso_opcao if dia_recesso else None

            elif periodo_escolha:
                periodo_recesso_id = field_name.replace('periodo_recesso_', '')
                periodo_recesso = RecessoPeriodo.objects.filter(id=periodo_recesso_id).first()
                recesso_opcao = periodo_recesso.recesso_opcao if periodo_recesso else None

            if recesso_opcao and (dia_recesso or periodo_recesso):
                # opção de recesso escolhida
                recesso_opcao_escolhida = RecessoOpcaoEscolhida.objects.filter(funcionario=funcionario, recesso_opcao=recesso_opcao).first()

                if not recesso_opcao_escolhida:
                    recesso_opcao_escolhida = RecessoOpcaoEscolhida()
                    recesso_opcao_escolhida.funcionario = funcionario
                    recesso_opcao_escolhida.recesso_opcao = recesso_opcao

                recesso_opcao_escolhida.data_escolha = datetime.datetime.now()

                # validação
                chefe_imediato_fieldname = f'validador_chefe_imediato_{recesso_opcao.id}'
                recesso_opcao_escolhida.validador = self.cleaned_data.get(chefe_imediato_fieldname, None)
                recesso_opcao_escolhida.validacao = RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO
                recesso_opcao_escolhida.motivo_nao_autorizacao = ''

                recesso_opcao_escolhida.save()

                recesso_opcoes_escolhidas.append(recesso_opcao_escolhida)

                if dia_recesso:
                    # True/False
                    dia_escolhido = self.cleaned_data.get(field_name, False)

                    dia_escolhido_salvo = RecessoDiaEscolhido.objects.filter(
                        recesso_opcao_escolhida__funcionario=funcionario, recesso_opcao_escolhida__recesso_opcao=recesso_opcao, dia=dia_recesso
                    ).first()

                    if dia_escolhido:
                        # ainda não foi salvo?
                        if not dia_escolhido_salvo:
                            # salva o dia escolhido
                            dia_recesso_escolhido = RecessoDiaEscolhido()
                            dia_recesso_escolhido.recesso_opcao_escolhida = recesso_opcao_escolhida
                            dia_recesso_escolhido.dia = dia_recesso
                            dia_recesso_escolhido.save()
                    else:
                        # mas já foi salvo anteriormente?
                        if dia_escolhido_salvo:
                            # remove o dia escolhido
                            dia_escolhido_salvo.delete()

                elif periodo_recesso:
                    periodo_recesso_fieldvalue = self.cleaned_data.get(field_name, {})
                    periodo_escolhido = periodo_recesso_fieldvalue.get('all_selected', False) or periodo_recesso_fieldvalue.get(
                        'days_selected', False
                    )

                    periodo_escolhido_salvo = RecessoPeriodoEscolhido.objects.filter(
                        recesso_opcao_escolhida__funcionario=funcionario,
                        recesso_opcao_escolhida__recesso_opcao=recesso_opcao,
                        periodo=periodo_recesso,
                    ).first()

                    if periodo_escolhido:
                        # ainda não foi salvo?
                        if not periodo_escolhido_salvo:
                            # salva o período escolhido
                            periodo_recesso_escolhido = RecessoPeriodoEscolhido()
                            periodo_recesso_escolhido.recesso_opcao_escolhida = recesso_opcao_escolhida
                            periodo_recesso_escolhido.periodo = periodo_recesso
                            periodo_recesso_escolhido.save()
                            periodo_escolhido_salvo = periodo_recesso_escolhido

                        # trata dias selecionados dentro do período
                        # remove os existentes e adiciona os atualmente selecionados
                        RecessoPeriodoEscolhidoDiaIndividual.objects.filter(
                            recesso_periodo_escolhido=periodo_escolhido_salvo,
                        ).delete()
                        dias_selecionados = periodo_recesso_fieldvalue.get('days_selected', [])
                        for dia_selecionado in dias_selecionados:
                            RecessoPeriodoEscolhidoDiaIndividual(recesso_periodo_escolhido=periodo_escolhido_salvo, dia=dia_selecionado).save()
                    else:
                        # mas já foi salvo anteriormente?
                        if periodo_escolhido_salvo:
                            # remove o período escolhido (os dias selecionados serão removidos em cascata)
                            periodo_escolhido_salvo.delete()

        # não escolher nenhum dia e período equivale a excluir a opção
        for recesso_opcoes_escolhida in recesso_opcoes_escolhidas:
            # não marcou nenhum dia e período na opção de recesso
            if not recesso_opcoes_escolhida.dias_escolhidos.all().exists() and not recesso_opcoes_escolhida.periodos_escolhidos.all().exists():
                recesso_opcoes_escolhida.delete()

    return type(
        'RecessoDiaEscolhidoForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'fieldsets': fieldsets,
            'METHOD': 'POST',
            'SUBMIT_LABEL': 'Salvar',
            'save': save,
            'clean': clean,
            'request': request,
            'ha_dias_disponiveis_para_escolha': bool(fields),
        },
    )


class RecessoOpcaoEscolhidaValidarForm(forms.ModelFormPlus):
    """Validação do chefe imediato de uma opção de recesso escolhida por um funcionário/servidor.
    Um e-mail de notificação será enviado ao funcionário/servidor.
    """

    class Meta:
        model = RecessoOpcaoEscolhida
        fields = ('validacao', 'motivo_nao_autorizacao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # redefine as opções de validação, removendo a opção 'Aguardando'
        self.fields['validacao'].choices = RecessoOpcaoEscolhida.VALIDACAO_CHOICES[1:]

    def clean(self):
        clean = super().clean()
        validacao = self.cleaned_data.get('validacao')
        if validacao:
            if int(validacao) in [RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO, RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR]:
                motivo_nao_autorizacao = self.cleaned_data.get('motivo_nao_autorizacao')
                if not motivo_nao_autorizacao:
                    self.add_error('motivo_nao_autorizacao', 'Informe o motivo da não autorização.')
        else:
            self.add_error('validacao', 'Informe a validação.')
        return clean

    def save(self, commit=True):
        validacao = int(self.cleaned_data.get('validacao'))

        if validacao in [
            RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
            RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
            RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
        ]:
            self.instance.validador = self.request.user.get_relacionamento()
            self.instance.data_validacao = datetime.datetime.now()
        else:
            self.instance.data_validacao = None

        if validacao not in [
            RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
            RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
        ]:
            self.cleaned_data['motivo_nao_autorizacao'] = ''

        # força a atualização de dias efetivos a compensar
        self.instance.dias_efetivos_a_compensar_cache = ''

        save = super().save(commit)
        if save:
            # envia o email
            self.instance.notifica_validacao()
        return save


class RecessoOpcaoEscolhidaValidarLoteForm(RecessoOpcaoEscolhidaValidarForm):
    """Validação em lote de opções de compensações específicas escolhidas por servidores."""

    class Meta:
        model = RecessoOpcaoEscolhida
        fields = ('validacao', 'motivo_nao_autorizacao')

    def __init__(self, recesso_opcoes_escolhidas: list[RecessoOpcaoEscolhida], *args, **kwargs):
        self.recesso_opcoes_escolhidas = recesso_opcoes_escolhidas
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        for recesso_opcao_escolhida in self.recesso_opcoes_escolhidas:
            recesso_opcao_escolhida_validacao_form = RecessoOpcaoEscolhidaValidarForm(
                data=self.data, instance=recesso_opcao_escolhida, request=self.request
            )
            recesso_opcao_escolhida_validacao_form.is_valid() and recesso_opcao_escolhida_validacao_form.save(commit)


class RecessoPeriodoCompensacaoAdminForm(forms.ModelFormPlus):
    class Meta:
        model = RecessoPeriodoCompensacao
        fields = ('data_inicial', 'data_final')


class RecessoDiaAdminForm(forms.ModelFormPlus):
    class Meta:
        model = RecessoDia
        fields = ('data',)


class HorarioCompensacaoPeriodoForm(forms.FormPlus):
    class Media:
        js = ('/static/js/ponto-util-v2.js',)

    METHOD = 'GET'

    data_inicio = DateFieldPlus(label='Data Início', initial=datetime.date.today())
    data_fim = DateFieldPlus(label='Data Fim', initial=datetime.date.today())

    def clean(self):
        clean = super().clean()

        if 'data_fim' in clean and 'data_inicio' in clean:
            if clean['data_fim'] < clean['data_inicio']:
                self.add_error('data_fim', 'Data Fim deve ser maior ou igual à Data Início.')

        return clean


class InformarCompensacaoPeriodoForm(HorarioCompensacaoPeriodoForm):
    periodo_objetivo = forms.ChoiceField(
        label='Objetivo',
        choices=[
            [PeriodoInfo.PERIODO_OBJETIVO_SALDO, 'Utilizar o saldo do período'],
            [PeriodoInfo.PERIODO_OBJETIVO_DEBITO, 'Compensar o débito do período'],
        ],
        initial=PeriodoInfo.PERIODO_OBJETIVO_SALDO,
    )


class RecessoOpcaoEscolhidaEditarChefeForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['validador'].label = 'Chefe Imediato/Validador'
        self.fields['validador'].queryset = Servidor.objects.filter(id__in=[chefe.id for chefe in self.instance.chefes])

    class Meta:
        model = RecessoOpcaoEscolhida
        fields = ('validador',)
        widgets = {'validador': forms.Select}


class LocalizarServidorForm(forms.FormPlus):
    servidor = forms.ModelChoiceFieldPlus(label='Servidor', queryset=Servidor.objects)

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        escopo_opcoes_escolhidas: QuerySet[RecessoOpcaoEscolhida] = kwargs.pop('escopo_opcoes_escolhidas')
        super().__init__(*args, **kwargs)
        self.fields['servidor'].queryset = Servidor.objects.filter(id__in=escopo_opcoes_escolhidas.values_list('funcionario_id', flat=True))


class RecessoOpcaoEscolhidaEditarForm(forms.ModelFormPlus):
    pode_validar_apos_prazo = forms.BooleanField(
        label='Liberado para validação após término do prazo', help_text='Marque essa opção caso seja um terceiro a validar.', required=False
    )

    class Meta:
        model = RecessoOpcaoEscolhida
        exclude = ('data_validacao',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance_initial = self.instance
        self.servidor_logado = self.request.user.get_relacionamento()

    def clean(self):
        clean = super().clean()

        if clean.get('validacao') in [RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO, RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO]:
            if not self.instance.recesso_opcao.is_permite_escolha_pelos_servidores:
                self.add_error('validacao', 'Não se aplica, pois não houve um período de escolhas.')

        if clean.get('validacao') == RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR:
            if not self.instance.recesso_opcao.is_no_periodo_para_escolhas_de_datas:
                self.add_error('validacao', 'O período de escolhas já expirou ou a remarcação não se aplica.')

        if clean.get('validacao') in [RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO, RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO]:
            if self.instance_initial.validacao != clean.get('validacao'):
                if clean.get('validador') != self.servidor_logado:
                    self.add_error('validador', 'No caso de autorização (ou não) como nova validação, o validador deve ser obrigatoriamente você.')

        return clean

    def save(self, commit=True):
        if self.cleaned_data.get('validacao') in [
            RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
            RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
            RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
        ]:
            self.instance.data_validacao = datetime.datetime.now()
        else:
            self.instance.data_validacao = None
        self.instance.responsavel_ultima_pos_edicao = self.servidor_logado
        return super().save(commit)


class DocumentoAnexoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAnexo
        fields = ('descricao', 'anexo')

    def __init__(self, *args, **kwargs):
        vinculo = kwargs.pop('vinculo')
        data = kwargs.pop('data')
        super().__init__(*args, **kwargs)

        self.instance.vinculo = vinculo
        self.instance.data = data

    def clean_anexo(self):
        arquivo = self.cleaned_data['anexo']
        filename = generate_filename(
            [self.instance.vinculo.id, self.instance.data, datetime.datetime.now()],
            arquivo,
        )

        arquivo.name = filename

        return self.cleaned_data['anexo']


class DocumentoAnexoChangeForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAnexo
        fields = ('descricao',)


#################
# Compensação de Horários: Saldo Externo


class SaldoExternoDestinatarioAdd(forms.ModelFormPlus):
    valor_saldo_hms = forms.TimeDeltaFieldPlus(label='Valor do Saldo', help_text='Formato: HHH:MM:SS.')

    class Meta:
        model = SaldoExterno
        fields = ('data_inicio', 'data_fim', 'valor_saldo_hms', 'detalhamento')

    def destinatario(self) -> Servidor:
        return self.request.user.get_relacionamento()

    def validador(self) -> Servidor:
        hoje = datetime.date.today()
        chefes = self.destinatario().get_chefes_no_periodo(hoje, hoje).get(hoje)
        return chefes[0] if chefes else None

    def clean(self):
        clean = super().clean()
        validador = self.validador()
        if validador == self.destinatario():
            hoje = datetime.date.today()
            if not validador.eh_reitor(hoje):
                self.add_error(None, 'A auto-validação não é permitida. Servidor (destinatário) e Validador devem ser diferentes.')
        return clean

    def save(self, commit=True):
        saldo_externo: SaldoExterno = self.instance
        servidor = self.destinatario()
        saldo_externo.servidor = servidor
        saldo_externo.servidor_cadastro = servidor
        valor_saldo_hms: timedelta = self.cleaned_data.get('valor_saldo_hms')
        saldo_externo.valor_saldo = valor_saldo_hms.total_seconds()
        saldo_externo.validador = self.validador()
        saldo_externo.situacao = SaldoExterno.SITUACAO_EM_FASE_DEFINICAO  # continua na fase de cadastro
        return super().save(commit)


class SaldoExternoValidadorAdd(SaldoExternoDestinatarioAdd):
    class Meta:
        model = SaldoExterno
        fields = ('servidor', 'data_inicio', 'data_fim', 'valor_saldo_hms', 'detalhamento')

    def destinatario(self) -> Servidor:
        return self.cleaned_data.get('servidor')

    def validador(self) -> Servidor:
        return self.request.user.get_relacionamento()

    def save(self, commit=True):
        saldo_externo: SaldoExterno = self.instance
        validador = self.validador()
        saldo_externo.servidor_cadastro = validador
        valor_saldo_hms: timedelta = self.cleaned_data.get('valor_saldo_hms')
        saldo_externo.valor_saldo = valor_saldo_hms.total_seconds()
        saldo_externo.validador = validador
        saldo_externo.situacao = SaldoExterno.SITUACAO_EM_FASE_DEFINICAO  # continua na fase de cadastro
        return super(forms.ModelFormPlus, self).save(commit)


class SaldoExternoDestinatarioChange(SaldoExternoDestinatarioAdd):
    class Meta:
        model = SaldoExterno
        fields = ('data_inicio', 'data_fim', 'valor_saldo_hms', 'detalhamento', 'validador')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        saldo_externo: SaldoExterno = self.instance
        valor_saldo_hms: timedelta = timedelta(seconds=saldo_externo.valor_saldo)
        self.fields['valor_saldo_hms'].initial = valor_saldo_hms

        # lista restrita de validadores (apenas os chefes hoje do destinatário + validador atual)
        hoje = datetime.date.today()
        self.fields['validador'].queryset = Servidor.objects.filter(
            id__in=[
                servidor.id for servidor in [*self.destinatario().get_chefes_no_periodo(hoje, hoje).get(hoje), self.instance.validador] if servidor
            ]
        )

    def clean(self):
        clean = super().clean()
        saldo_externo: SaldoExterno = self.instance
        if saldo_externo.compensacoes_informadas.exists():
            valor_saldo_hms: timedelta = self.cleaned_data.get('valor_saldo_hms')
            saldo_externo_old = SaldoExterno.objects.filter(id=saldo_externo.id).first()
            if valor_saldo_hms.total_seconds() != saldo_externo_old.valor_saldo:
                self.add_error('valor_saldo_hms', 'Não é possível alterar o valor do saldo. Parte ou todo o saldo já foi utilizado pelo servidor.')
                self.add_error('valor_saldo_hms', 'Para alterar o valor do saldo, é preciso que o servidor cancele/exclua o que foi utilizado.')
        return clean

    def destinatario(self) -> Servidor:
        return self.instance.servidor

    def validador(self) -> Servidor:
        return self.cleaned_data.get('validador')

    def save(self, commit=True):
        saldo_externo: SaldoExterno = self.instance
        valor_saldo_hms: timedelta = self.cleaned_data.get('valor_saldo_hms')
        saldo_externo.valor_saldo = valor_saldo_hms.total_seconds()
        return super(forms.ModelFormPlus, self).save(commit)


class SaldoExternoValidadorChange(SaldoExternoDestinatarioChange):
    servidor_display = forms.CharField(label='Servidor', help_text='Destinatário do Saldo.')

    class Meta:
        model = SaldoExterno
        fields = ('servidor_display', 'data_inicio', 'data_fim', 'valor_saldo_hms', 'detalhamento', 'validador')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        saldo_externo: SaldoExterno = self.instance
        valor_saldo_hms: timedelta = timedelta(seconds=saldo_externo.valor_saldo)
        self.fields['valor_saldo_hms'].initial = valor_saldo_hms

        self.fields['servidor_display'].initial = self.instance.servidor
        self.fields['servidor_display'].widget.attrs['readonly'] = 'readonly'

        if self.instance.validador == self.destinatario():
            # lista restrita de validadores (apenas os chefes hoje do destinatário + validador atual)
            hoje = datetime.date.today()
            self.fields['validador'].queryset = Servidor.objects.filter(
                id__in=[
                    servidor.id
                    for servidor in [*self.destinatario().get_chefes_no_periodo(hoje, hoje).get(hoje), self.instance.validador]
                    if servidor
                ]
            )
        else:
            # lista não restrita de validadores (todos os servidores)
            self.fields['validador'].queryset = Servidor.objects

    def destinatario(self) -> Servidor:
        return self.instance.servidor

    def validador(self) -> Servidor:
        return self.cleaned_data.get('validador')


class SaldoExternoValidar(forms.ModelFormPlus):
    situacao_acao = forms.ChoiceField(
        label='Ação',
        choices=[
            [None, 'Selecione uma ação'],
            [SaldoExterno.SITUACAO_EM_FASE_DEFINICAO, 'Voltar para a Fase de Cadastro'],
            [SaldoExterno.SITUACAO_VALIDADO, 'Autorizar'],
        ],
    )

    class Meta:
        model = SaldoExterno
        fields = ('situacao_acao', 'validador_observacoes')

    def destinatario(self) -> Servidor:
        return self.instance.servidor

    def validador(self) -> Servidor:
        return self.instance.validador

    def clean(self):
        clean = super().clean()
        validador = self.validador()
        if validador == self.destinatario():
            hoje = datetime.date.today()
            if not validador.eh_reitor(hoje):
                self.add_error(
                    None,
                    'A auto-validação não é permitida. Servidor (destinatário) e Validador devem ser diferentes. Será necessário escolher um Validador diferente através da opção "Editar".',
                )
        return clean

    def save(self, commit=True):
        saldo_externo: SaldoExterno = self.instance
        saldo_externo.situacao = self.cleaned_data.get('situacao_acao')
        return super(forms.ModelFormPlus, self).save(commit)


class SelecionarSaldosExternosForm(forms.FormPlus):
    saldos_externos = forms.MultipleModelChoiceFieldPlus(label='Saldos Externos', queryset=SaldoExterno.objects)

    class Meta:
        fields = ('saldos_externos',)

    def __init__(self, *args, **kwargs):
        self.escopo_user_como_destinatario = kwargs.pop('escopo_user_como_destinatario', False)
        self.escopo_user_como_validador = kwargs.pop('escopo_user_como_validador', False)
        self.escopo_user_qualquer = kwargs.pop('escopo_user_qualquer', False)

        super().__init__(*args, **kwargs)

        servidor_user: Servidor = self.request.user.get_relacionamento()

        self.fields['saldos_externos'].help_text = ''

        if self.escopo_user_como_destinatario:
            self.fields['saldos_externos'].queryset = SaldoExterno.objects.filter(servidor=servidor_user)
            self.fields['saldos_externos'].help_text += 'Seus Saldos Externos como Destinatário. '
        if self.escopo_user_como_validador:
            self.fields['saldos_externos'].queryset = SaldoExterno.objects.filter(validador=servidor_user)
            self.fields['saldos_externos'].help_text += 'Seus Saldos Externos como Validador. '
        if self.escopo_user_qualquer:
            self.fields['saldos_externos'].queryset = SaldoExterno.objects.all()
            self.fields['saldos_externos'].help_text += 'Quaisquer Saldos Externos. '


#################
# Compensação de Horários: Débito Externo


class DebitoExternoCadastroDestinatarioAdd(forms.ModelFormPlus):
    total_debito_hms = forms.TimeDeltaFieldPlus(label='Valor Total do Débito', help_text='Formato: HHH:MM:SS.')

    class Meta:
        model = DebitoExternoCadastro
        fields = ('total_debito_hms', 'detalhamento')

    def destinatario(self) -> Servidor:
        return self.request.user.get_relacionamento()

    def validador(self) -> Servidor:
        hoje = datetime.date.today()
        chefes = self.destinatario().get_chefes_no_periodo(hoje, hoje).get(hoje)
        return chefes[0] if chefes else None

    def clean(self):
        clean = super().clean()
        validador = self.validador()
        if validador == self.destinatario():
            hoje = datetime.date.today()
            if not validador.eh_reitor(hoje):
                self.add_error(None, 'A auto-validação não é permitida. Servidor (destinatário) e Validador devem ser diferentes.')
        return clean

    def save(self, commit=True):
        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        servidor = self.destinatario()
        debito_externo_cadastro.servidor = servidor
        debito_externo_cadastro.servidor_cadastro = servidor
        total_debito_hms: timedelta = self.cleaned_data.get('total_debito_hms')
        debito_externo_cadastro.total_debito = total_debito_hms.total_seconds()
        debito_externo_cadastro.validador = self.validador()
        debito_externo_cadastro.situacao = DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO  # continua na fase de cadastro
        return super().save(commit)


class DebitoExternoCadastroValidadorAdd(DebitoExternoCadastroDestinatarioAdd):
    class Meta:
        model = DebitoExternoCadastro
        fields = ('servidor', 'total_debito_hms', 'detalhamento')

    def destinatario(self) -> Servidor:
        return self.cleaned_data.get('servidor')

    def validador(self) -> Servidor:
        return self.request.user.get_relacionamento()

    def save(self, commit=True):
        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        validador = self.validador()
        debito_externo_cadastro.servidor_cadastro = validador
        total_debito_hms: timedelta = self.cleaned_data.get('total_debito_hms')
        debito_externo_cadastro.total_debito = total_debito_hms.total_seconds()
        debito_externo_cadastro.validador = validador
        debito_externo_cadastro.situacao = DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO  # continua na fase de cadastro
        return super(forms.ModelFormPlus, self).save(commit)


class DebitoExternoCadastroDestinatarioChange(DebitoExternoCadastroDestinatarioAdd):
    class Meta:
        model = DebitoExternoCadastro
        fields = ('total_debito_hms', 'detalhamento', 'validador')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        total_debito_hms: timedelta = timedelta(seconds=debito_externo_cadastro.total_debito)
        self.fields['total_debito_hms'].initial = total_debito_hms

        # lista restrita de validadores (apenas os chefes hoje do destinatário + validador atual)
        hoje = datetime.date.today()
        self.fields['validador'].queryset = Servidor.objects.filter(
            id__in=[
                servidor.id for servidor in [*self.destinatario().get_chefes_no_periodo(hoje, hoje).get(hoje), self.instance.validador] if servidor
            ]
        )

    def clean(self):
        clean = super().clean()
        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        if debito_externo_cadastro.compensacoes_informadas.exists():
            total_debito_hms: timedelta = self.cleaned_data.get('total_debito_hms')
            debito_externo_cadastro_old = DebitoExternoCadastro.objects.filter(id=debito_externo_cadastro.id).first()
            if total_debito_hms.total_seconds() != debito_externo_cadastro_old.total_debito:
                self.add_error(
                    'total_debito_hms', 'Não é possível alterar o valor do débito. Parte ou todo o débito já foi compensado pelo servidor.'
                )
                self.add_error('total_debito_hms', 'Para alterar o valor do débito, é preciso que o servidor cancele/exclua o que foi compensado.')
        return clean

    def destinatario(self) -> Servidor:
        return self.instance.servidor

    def validador(self) -> Servidor:
        return self.cleaned_data.get('validador')

    def save(self, commit=True):
        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        total_debito_hms: timedelta = self.cleaned_data.get('total_debito_hms')
        debito_externo_cadastro.total_debito = total_debito_hms.total_seconds()
        return super(forms.ModelFormPlus, self).save(commit)


class DebitoExternoCadastroValidadorChange(DebitoExternoCadastroDestinatarioChange):
    servidor_display = forms.CharField(label='Servidor', help_text='Destinatário do Débito.')

    class Meta:
        model = DebitoExternoCadastro
        fields = ('servidor_display', 'total_debito_hms', 'detalhamento', 'validador')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        total_debito_hms: timedelta = timedelta(seconds=debito_externo_cadastro.total_debito)
        self.fields['total_debito_hms'].initial = total_debito_hms

        self.fields['servidor_display'].initial = self.instance.servidor
        self.fields['servidor_display'].widget.attrs['readonly'] = 'readonly'

        if self.instance.validador == self.destinatario():
            # lista restrita de validadores (apenas os chefes hoje do destinatário + validador atual)
            hoje = datetime.date.today()
            self.fields['validador'].queryset = Servidor.objects.filter(
                id__in=[
                    servidor.id
                    for servidor in [*self.destinatario().get_chefes_no_periodo(hoje, hoje).get(hoje), self.instance.validador]
                    if servidor
                ]
            )
        else:
            # lista não restrita de validadores (todos os servidores)
            self.fields['validador'].queryset = Servidor.objects

    def destinatario(self) -> Servidor:
        return self.instance.servidor

    def validador(self) -> Servidor:
        return self.cleaned_data.get('validador')


class DebitoExternoAdd(forms.ModelFormPlus):
    valor_debito_hms = forms.TimeDeltaFieldPlus(label='Valor do Débito', help_text='Formato: HHH:MM:SS.')

    def __init__(self, *args, **kwargs):
        self.debito_externo_cadastro = kwargs.pop('debito_externo_cadastro')
        assert self.debito_externo_cadastro is not None
        super().__init__(*args, **kwargs)

    class Meta:
        model = DebitoExterno
        fields = ('data_debito', 'valor_debito_hms', 'observacoes')

    def save(self, commit=True):
        debito_externo: DebitoExterno = self.instance
        debito_externo.cadastro = self.debito_externo_cadastro
        valor_debito_hms: timedelta = self.cleaned_data.get('valor_debito_hms')
        debito_externo.valor_debito = valor_debito_hms.total_seconds()
        return super().save(commit)


class DebitoExternoChange(forms.ModelFormPlus):
    valor_debito_hms = forms.TimeDeltaFieldPlus(label='Valor do Débito', help_text='Formato: HHH:MM:SS.')

    class Meta:
        model = DebitoExterno
        fields = ('data_debito', 'valor_debito_hms', 'observacoes')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        debito_externo: DebitoExterno = self.instance
        valor_debito_hms: timedelta = timedelta(seconds=debito_externo.valor_debito)
        self.fields['valor_debito_hms'].initial = valor_debito_hms

    def save(self, commit=True):
        debito_externo: DebitoExterno = self.instance
        valor_debito_hms: timedelta = self.cleaned_data.get('valor_debito_hms')
        debito_externo.valor_debito = valor_debito_hms.total_seconds()
        return super().save(commit)


class DebitoExternoCadastroValidar(forms.ModelFormPlus):
    situacao_acao = forms.ChoiceField(
        label='Ação',
        choices=[
            [None, 'Selecione uma ação'],
            [DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO, 'Voltar para a Fase de Cadastro'],
            [DebitoExternoCadastro.SITUACAO_VALIDADO, 'Autorizar'],
        ],
    )

    class Meta:
        model = DebitoExternoCadastro
        fields = ('situacao_acao', 'validador_observacoes')

    def destinatario(self) -> Servidor:
        return self.instance.servidor

    def validador(self) -> Servidor:
        return self.instance.validador

    def clean(self):
        clean = super().clean()

        validador = self.validador()
        if validador == self.destinatario():
            hoje = datetime.date.today()
            if not validador.eh_reitor(hoje):
                self.add_error(
                    None,
                    'A auto-validação não é permitida. Servidor (destinatário) e Validador devem ser diferentes. Será necessário escolher um Validador diferente através da opção "Editar".',
                )

        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        debito_externo_cadastro_erros = debito_externo_cadastro.get_erros()
        if debito_externo_cadastro_erros:
            self.add_error(None, ' '.join(debito_externo_cadastro_erros))

        return clean

    def save(self, commit=True):
        debito_externo_cadastro: DebitoExternoCadastro = self.instance
        debito_externo_cadastro.situacao = self.cleaned_data.get('situacao_acao')
        return super(forms.ModelFormPlus, self).save(commit)


###
# SOLICITAÇÃO DE ABONO PARCIAL / ABONO DE CHEFIA / REVISÃO DE ABONO DE CHEFIA


# SOLICITAÇÃO DE ABONO PARCIAL


class SolicitacaoAbonoParcialEtapa1Form(forms.ModelFormPlus):
    motivo_solicitacao = forms.ChoiceField(
        label='Motivo da Solicitação',
        choices=[
            [None, '--- Selecione ---'],
        ]
        + SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_CHOICES
        + [choice for choice in SolicitacaoAbonoParcial.MOTIVO_CHOICES if choice[0] != SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE],
        required=True,
        initial=None,
    )

    SUBMIT_LABEL = 'Continuar'

    class Meta:
        model = SolicitacaoAbonoParcial
        fields = (
            'data_aplicacao',
            'motivo_solicitacao',
        )


def SolicitacaoAbonoParcialEtapa2FormFactory(motivo_solicitacao: int, data_aplicacao: datetime.date):
    motivo_solicitacao_acompanhamento_gravidez = False

    # O motivo SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE (valor 1)
    # não deve ser tratado como um motivo válido dentro do escopo deste
    # formulário. Tal motivo é desmembrando em outros sub-motivos (11, 12, ...),
    # e esses sim fazem parte do escopo deste formulário.

    if motivo_solicitacao == SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_COMO_PACIENTE:
        motivo_solicitacao_display_value = SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_CHOICES[0][1]
    elif motivo_solicitacao == SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_ACOMPANHAR_GRAVIDEZ:
        motivo_solicitacao_display_value = SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_CHOICES[1][1]
        motivo_solicitacao_acompanhamento_gravidez = True
    elif motivo_solicitacao in [
        SolicitacaoAbonoParcial.MOTIVO_ESQUECIMENTO_FREQUENCIA,
        SolicitacaoAbonoParcial.MOTIVO_HORARIO_INTERVALO,
        SolicitacaoAbonoParcial.MOTIVO_SIASS,
        SolicitacaoAbonoParcial.MOTIVO_OUTROS,
    ]:
        motivo_solicitacao_display_value = SolicitacaoAbonoParcial(motivo=motivo_solicitacao).get_motivo_display()
    else:
        raise PontoException('Motivo da Solicitação inválido.')

    class SolicitacaoAbonoParcialEtapa2BaseForm(forms.ModelFormPlus):
        motivo_solicitacao_display = forms.CharField(label='Motivo da Solicitação', initial=motivo_solicitacao_display_value)
        ch_solicitada_hms = forms.TimeDeltaFieldPlus(
            label='Carga Horária a Abonar',
            help_text='Formato: HH:MM:SS.',
            mask_hours='00',
            min_value=timedelta(seconds=1),
        )
        abono_solicitado = forms.ChoiceField(
            label='Abono Solicitado',
            choices=[[None, '--- Selecione ---'], *SolicitacaoAbonoParcial.ABONO_CHOICES],
            required=True,
            initial=None,
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['motivo_solicitacao_display'].widget.attrs['readonly'] = 'readonly'
            servidor = self.get_vinculo_pessoa().relacionamento
            ctx_ponto = Contexto(servidor, data_aplicacao, data_aplicacao)
            self.fields['ch_solicitada_hms'].initial = timedelta(seconds=ctx_ponto.get_dia(data_aplicacao, True).debito_qtd_restante)

        def get_vinculo_pessoa(self):
            return self.request.user.get_vinculo()

        def get_motivo(self):
            if motivo_solicitacao in [
                SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_COMO_PACIENTE,
                SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE_ACOMPANHAR_GRAVIDEZ,
            ]:
                motivo = SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE
            else:
                motivo = motivo_solicitacao

            return int(motivo)

        def get_ch_solicitada_em_segundos(self):
            ch_solicitada_hms: timedelta = self.cleaned_data.get('ch_solicitada_hms', timedelta(0))
            return ch_solicitada_hms.total_seconds()

        def clean(self):
            clean = super().clean()

            if self.is_valid():
                validacao_errors = SolicitacaoAbonoParcial.validar(
                    SolicitacaoAbonoParcial(
                        id=self.instance.id,
                        vinculo_pessoa=self.get_vinculo_pessoa(),
                        data_aplicacao=clean.get('data_aplicacao'),
                        motivo=self.get_motivo(),
                        acompanhamento_gravidez=clean.get('acompanhamento_gravidez'),
                        acompanhamento_gravidez_qtd_consultas=int(clean.get('acompanhamento_gravidez_qtd_consultas'))
                        if clean.get('acompanhamento_gravidez_qtd_consultas')
                        else None,
                        descricao=clean.get('descricao'),
                        arquivo=clean.get('arquivo'),
                        ch_solicitada=self.get_ch_solicitada_em_segundos(),
                        abono_solicitado=int(clean.get('abono_solicitado')) if clean.get('abono_solicitado') else None,
                        situacao=SolicitacaoAbonoParcial.SITUACAO_PENDENTE,
                    ),
                    revalidar=self.instance.id is not None,
                )

                for error in validacao_errors:
                    self.add_error(None, error)

            return clean

        def save(self, commit=True):
            abono_parcial: SolicitacaoAbonoParcial = self.instance
            abono_parcial.vinculo_pessoa = self.get_vinculo_pessoa()
            abono_parcial.motivo = self.get_motivo()
            abono_parcial.ch_solicitada = self.get_ch_solicitada_em_segundos()
            abono_parcial.situacao = SolicitacaoAbonoParcial.SITUACAO_PENDENTE
            return super().save(commit)

    if motivo_solicitacao_acompanhamento_gravidez:

        class SolicitacaoAbonoParcialEtapa2Form(SolicitacaoAbonoParcialEtapa2BaseForm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['acompanhamento_gravidez'].required = True
                self.fields['acompanhamento_gravidez_qtd_consultas'].required = True
                self.fields['acompanhamento_gravidez'].queryset = SolicitacaoAbonoParcialGravidez.objects.filter(
                    vinculo_pessoa=self.request.user.get_vinculo()
                )
                self.fields[
                    'acompanhamento_gravidez'
                ].help_text += ' Para cadastrar períodos de gravidez, acesse o menu "Gravidez de Esposa ou Companheira".'

            class Meta:
                model = SolicitacaoAbonoParcial
                fields = (
                    'data_aplicacao',
                    'motivo_solicitacao_display',
                    'acompanhamento_gravidez',
                    'acompanhamento_gravidez_qtd_consultas',
                    'descricao',
                    'arquivo',
                    'ch_solicitada_hms',
                    'abono_solicitado',
                )
    else:

        class SolicitacaoAbonoParcialEtapa2Form(SolicitacaoAbonoParcialEtapa2BaseForm):
            class Meta:
                model = SolicitacaoAbonoParcial
                fields = (
                    'data_aplicacao',
                    'motivo_solicitacao_display',
                    'descricao',
                    'arquivo',
                    'ch_solicitada_hms',
                    'abono_solicitado',
                )

    return SolicitacaoAbonoParcialEtapa2Form


class SolicitacaoAbonoParcialGravidezForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoAbonoParcialGravidez
        exclude = ('vinculo_pessoa',)
        labels = {
            'descricao': 'Descrição da Gravidez (opcional):',
            'arquivo': 'Arquivo Comprobatório (opcional):',
        }

    def save(self, commit=True):
        if not self.instance.id:
            self.instance.vinculo_pessoa = self.request.user.get_vinculo()
        return super().save(commit)


def DireitosHistoricoAbonoParcialFilterFormFactory(queryset_servidor_choices):
    class FilterForm(forms.FormPlus):
        servidor = forms.ModelChoiceFieldPlus(
            label='Servidor',
            queryset=queryset_servidor_choices,
            help_text='Você ou qualquer outro Servidor que já avaliou ou que está com avaliação pendente.',
        )

        METHOD = 'GET'

    return FilterForm


# EDIÇÃO DE SOLICITAÇÃO DE ABONO PARCIAL


class SolicitacaoAbonoParcialForm(forms.ModelFormPlus):
    ch_solicitada_hms = forms.TimeDeltaFieldPlus(
        label='Carga Horária a Abonar',
        help_text='Formato: HH:MM:SS.',
        mask_hours='00',
        min_value=timedelta(seconds=1),
    )
    motivo = forms.ChoiceField(
        label='Motivo da Solicitação',
        choices=[[None, '--- Selecione ---'], *SolicitacaoAbonoParcial.MOTIVO_CHOICES],
        required=True,
        initial=None,
    )
    abono_solicitado = forms.ChoiceField(
        label='Abono Solicitado',
        choices=[[None, '--- Selecione ---'], *SolicitacaoAbonoParcial.ABONO_CHOICES],
        required=True,
        initial=None,
    )

    class Meta:
        model = SolicitacaoAbonoParcial
        fields = (
            'data_aplicacao',
            'motivo',
            'acompanhamento_gravidez',
            'acompanhamento_gravidez_qtd_consultas',
            'descricao',
            'arquivo',
            'ch_solicitada_hms',
            'abono_solicitado',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        abono_parcial = self.instance
        assert abono_parcial.id is not None
        self.fields['acompanhamento_gravidez'].queryset = SolicitacaoAbonoParcialGravidez.objects.filter(
            vinculo_pessoa=self.request.user.get_vinculo()
        )
        self.fields['acompanhamento_gravidez'].help_text += ' Para cadastrar períodos de gravidez, acesse o menu "Gravidez de Esposa ou Companheira".'
        self.fields['ch_solicitada_hms'].initial = timedelta(seconds=abono_parcial.ch_solicitada)

    def get_vinculo_pessoa(self):
        return self.request.user.get_vinculo()

    def get_ch_solicitada_em_segundos(self):
        ch_solicitada_hms: timedelta = self.cleaned_data.get('ch_solicitada_hms', timedelta(0))
        return ch_solicitada_hms.total_seconds()

    def clean(self):
        clean = super().clean()

        if self.is_valid():
            validacao_errors = SolicitacaoAbonoParcial.validar(
                SolicitacaoAbonoParcial(
                    id=self.instance.id,
                    vinculo_pessoa=self.get_vinculo_pessoa(),
                    data_aplicacao=clean.get('data_aplicacao'),
                    motivo=int(clean.get('motivo')) if clean.get('motivo') else None,
                    acompanhamento_gravidez=clean.get('acompanhamento_gravidez'),
                    acompanhamento_gravidez_qtd_consultas=int(clean.get('acompanhamento_gravidez_qtd_consultas'))
                    if clean.get('acompanhamento_gravidez_qtd_consultas')
                    else None,
                    descricao=clean.get('descricao'),
                    arquivo=clean.get('arquivo'),
                    ch_solicitada=self.get_ch_solicitada_em_segundos(),
                    abono_solicitado=int(clean.get('abono_solicitado')) if clean.get('abono_solicitado') else None,
                    situacao=SolicitacaoAbonoParcial.SITUACAO_PENDENTE,
                ),
                revalidar=True,
            )

            for error in validacao_errors:
                self.add_error(None, error)

        return clean

    def save(self, commit=True):
        abono_parcial: SolicitacaoAbonoParcial = self.instance
        abono_parcial.vinculo_pessoa = self.get_vinculo_pessoa()
        abono_parcial.ch_solicitada = self.get_ch_solicitada_em_segundos()
        abono_parcial.situacao = SolicitacaoAbonoParcial.SITUACAO_PENDENTE
        return super().save(commit)


# ABONO (AVALIAÇÃO) DE CHEFIA COM OU SEM SOLICITAÇÃO DE ABONO PARCIAL


class AbonoChefiaFormUtils:
    def __init__(self, inconsistencias: list[str], com_solicitacao_abono_parcial: bool):
        self.inconsistencias = inconsistencias
        self.com_solicitacao_abono_parcial = com_solicitacao_abono_parcial

    def get_choices(self):
        if self.com_solicitacao_abono_parcial:
            return [[None, 'Selecione uma opção'], *SolicitacaoAbonoParcial.ABONO_CHOICES, [AbonoChefia.NAO_ABONADO, 'Não abonar']]
        choices_por_inconsistencias = []
        for inconsistencia in self.inconsistencias:
            choices_por_inconsistencias += AbonoChefia.CHOICES_POR_INCONSISTENCIAS[inconsistencia]
        return [[None, 'Selecione uma opção'], *choices_por_inconsistencias]

    def get_descricao_abonos(self) -> dict:
        # Aqui usamos as constantes para gerar uma lista de tuplas (value, descrição)
        return {key: AbonoChefia.DESCRICOES_ABONO.get(key, '') for key, _ in self.get_choices()}

    def get_fields(self) -> dict:
        fields = {}

        if self.com_solicitacao_abono_parcial:
            fields.update(
                {
                    'ch_solicitada_a_abonar_confirmacao_hms': forms.TimeDeltaFieldPlus(
                        label='Carga Horária a Abonar',
                        help_text='Formato: HH:MM:SS.',
                        mask_hours='00',
                        min_value=timedelta(seconds=1),
                    ),
                }
            )

        fields.update(
            {
                'descricao': forms.CharField(label='Descrição/Observação', required=False, widget=forms.Textarea()),
                'acao_abono': forms.ChoiceField(
                    label='Abono',
                    choices=self.get_choices(),
                    required=True,
                    initial=None,
                ),
            }
        )

        if Configuracao.get_valor_por_chave(app='rh', chave='permite_desconto_de_carga_horaria'):
            fields.update(
                {
                    'ch_descontada_hms': forms.TimeDeltaFieldPlus(
                        label='Carga Horária a Descontar',
                        required=False,
                        help_text='Atenção: o desconto de carga horária possui um valor punitivo. Formato: HH:MM:SS.',
                        mask_hours='00',
                        min_value=timedelta(seconds=1),
                    ),
                }
            )

        return fields


# ABONO (AVALIAÇÃO) DE CHEFIA SEM SOLICITAÇÃO DE ABONO PARCIAL (= DINÂMICA PADRÃO)


def AbonoChefiaFormFactory(inconsistencias):
    form_utils = AbonoChefiaFormUtils(inconsistencias, False)
    form_fields = form_utils.get_fields()

    class AbonoChefiaForm(forms.ModelFormPlus):
        descricao = form_fields.get('descricao')
        acao_abono = form_fields.get('acao_abono')
        ch_descontada_hms = form_fields.get('ch_descontada_hms')

        class Meta:
            model = AbonoChefia
            fields = (
                'descricao',
                'acao_abono',
            )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.descricao_abonos = form_utils.get_descricao_abonos()

        def save(self, commit=True):
            ch_descontada_hms: timedelta = self.cleaned_data.get('ch_descontada_hms', timedelta(0))
            self.instance.ch_descontada = ch_descontada_hms.total_seconds() if ch_descontada_hms else None
            return super().save(commit)

    return AbonoChefiaForm


def AbonoChefiaLoteFormFactory(inconsistencias, frequencias_dias):
    form_utils = AbonoChefiaFormUtils(inconsistencias, False)
    form_fields = form_utils.get_fields()
    frequencias_dias_choices = [[dias, dias] for dias in frequencias_dias]

    class AbonoChefiaLoteForm(forms.FormPlus):
        descricao = form_fields.get('descricao')
        acao_abono = form_fields.get('acao_abono')
        frequencias_dias = forms.MultipleChoiceField(
            label='frequencias_dias', widget=forms.CheckboxSelectMultiplePlus(attrs={'checked': ''}), choices=frequencias_dias_choices, required=True
        )

        METHOD = 'POST'
        SUBMIT_LABEL = 'Salvar'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.descricao_abonos = form_utils.get_descricao_abonos()

    return AbonoChefiaLoteForm


# ABONO (AVALIAÇÃO) DE CHEFIA COM SOLICITAÇÃO DE ABONO PARCIAL


def SolicitacaoAbonoParcialAvaliarFormFactory():
    form_utils = AbonoChefiaFormUtils([], True)
    form_fields = form_utils.get_fields()

    class SolicitacaoAbonoParcialAvaliarForm(forms.FormPlus):
        ch_solicitada_a_abonar_confirmacao_hms = form_fields.get('ch_solicitada_a_abonar_confirmacao_hms')
        descricao = form_fields.get('descricao')
        acao_abono = form_fields.get('acao_abono')
        ch_descontada_hms = form_fields.get('ch_descontada_hms')

        SUBMIT_LABEL = 'Salvar'

        def __init__(self, data, solicitacoes: list[SolicitacaoAbonoParcial] | None = None, *args, **kwargs):
            if solicitacoes is None:
                solicitacoes = []

            super().__init__(data, *args, **kwargs)

            self.descricao_abonos = form_utils.get_descricao_abonos()

            # suporte a avaliação em lote de solicitações
            self.solicitacoes = solicitacoes or []
            solicitacoes_vinculos: list[Vinculo] = []
            solicitacoes_abonos: list[int] = []
            for solicitacao in self.solicitacoes:
                if solicitacao.vinculo_pessoa not in solicitacoes_vinculos:
                    solicitacoes_vinculos.append(solicitacao.vinculo_pessoa)
                if solicitacao.abono_solicitado not in solicitacoes_abonos:
                    solicitacoes_abonos.append(solicitacao.abono_solicitado)

            # as solicitações devem ser do mesmo vinculo
            assert not len(solicitacoes_vinculos) > 1

            # seta valor inicial para "ch_solicitada_a_abonar_confirmacao_hms"
            if len(self.solicitacoes) == 1:
                self.fields['ch_solicitada_a_abonar_confirmacao_hms'].initial = timedelta(seconds=self.solicitacoes[0].ch_solicitada)
            else:
                del self.fields['ch_solicitada_a_abonar_confirmacao_hms']
                if 'ch_descontada_hms' in self.fields:
                    del self.fields['ch_descontada_hms']

            # seta valor inicial para "acao_abono"
            if len(solicitacoes_abonos) == 1:
                self.fields['acao_abono'].initial = solicitacoes_abonos[0]
            elif len(solicitacoes_abonos) > 1:
                self.fields['acao_abono'].choices += [[99, 'Abonar conforme o tipo de abono pedido em cada solicitação']]
                self.fields['acao_abono'].initial = 99

        def clean(self):
            clean = super().clean()

            acao_abono_nao_abonado = clean.get('acao_abono') == f'{AbonoChefia.NAO_ABONADO}'

            if acao_abono_nao_abonado and not clean.get('descricao'):
                self.add_error('descricao', 'Nesse caso, informe uma descrição/observação sobre os motivos que o levaram a não abonar.')

            if self.is_valid():
                # revalida cada solicitação

                for solicitacao in self.solicitacoes:
                    erro = self.clean_solicitacao(solicitacao)
                    if erro:
                        self.add_error(None, erro)

            return clean

        def clean_solicitacao(self, solicitacao: SolicitacaoAbonoParcial) -> str:
            solicitacao_abono_solicitado = solicitacao.abono_solicitado
            solicitacao_ch_solicitada = solicitacao.ch_solicitada

            if self.cleaned_data.get('acao_abono') != '99' and self.cleaned_data.get('acao_abono') != f'{solicitacao_abono_solicitado}':
                # Nesse caso, o chefe imediato alterou a ação do abono em comparação ao que foi solicitado.
                # Então, a revalidação da solicitação deve considerar, temporariamente, a ação do abono que
                # foi escolhida pelo chefe imediato.
                solicitacao.abono_solicitado = int(self.cleaned_data.get('acao_abono'))

            # No caso de avaliação de uma única solicitação de abono parcial, a carga horária solicitada
            # a abonar também pode ter sido alterada pelo chefe imediato e que a revalidação da solicitação
            # deve considerar, temporariamente, esse novo valor de carga horária solicitada a abonar.
            if len(self.solicitacoes) == 1:
                solicitacao.ch_solicitada = self.get_ch_solicitada_a_abonar_confirmacao_em_segundos()

            msg_erro = ''

            erros = SolicitacaoAbonoParcial.validar(solicitacao, revalidar=True)

            if erros:
                msg_erro = f'A solicitação "{solicitacao}" não pode ser avaliada: {" ".join(erros)}'

            # restaura/reafirma o valor original do abono solicitado
            solicitacao.abono_solicitado = solicitacao_abono_solicitado

            # restaura/reafirma o valor original da carga horária solicitada
            solicitacao.ch_solicitada = solicitacao_ch_solicitada

            return msg_erro

        def get_ch_solicitada_a_abonar_confirmacao_em_segundos(self):
            ch_solicitada_a_abonar_confirmacao_hms: timedelta = self.cleaned_data.get('ch_solicitada_a_abonar_confirmacao_hms', timedelta(0))
            return ch_solicitada_a_abonar_confirmacao_hms.total_seconds()

        def get_ch_descontada_em_segundos(self):
            ch_descontada_hms: timedelta = self.cleaned_data.get('ch_descontada_hms', timedelta(0))
            return ch_descontada_hms.total_seconds() if ch_descontada_hms else None

        @atomic
        def save(self) -> list[str]:
            """
            Para uma ou mais solicitações (avaliação em lote):
                - Há casos em que não há erros de validação no escopo individual, mas pode
                haver erros de validação considerando solicitações que já foram salvas.

                - Então, antes de salvar a próxima solicitação, o seu 'clean' individual será
                chamado novamente.

            Este 'save' retornará uma lista de erros (se for o caso).
            """

            result_erros = []

            vinculo_chefe_imediato = self.request.user.get_vinculo()

            for solicitacao in self.solicitacoes:
                # apenas solicitações não avaliadas serão processadas
                if solicitacao.situacao_is_avaliado:
                    continue

                erros = []

                # confirma se o usuário pode avaliar
                solicitacao_pode_avaliar = solicitacao.pode_avaliar(self.request.user)
                if not solicitacao_pode_avaliar:
                    erros.append(f'Você não tem permissão para avaliar a solicitação "{solicitacao}".')

                # revalida a solicitação
                solicitacao_erro = self.clean_solicitacao(solicitacao)
                if solicitacao_erro:
                    erros.append(solicitacao_erro)

                tem_erros = len(erros) > 0

                if not tem_erros:
                    acao_abono = int(self.cleaned_data.get('acao_abono'))
                    if acao_abono == 99:
                        acao_abono = solicitacao.abono_solicitado

                    # novo abono
                    abono = AbonoChefia()
                    abono.vinculo_pessoa = solicitacao.vinculo_pessoa
                    abono.vinculo_chefe_imediato = vinculo_chefe_imediato
                    abono.data = solicitacao.data_aplicacao
                    abono.descricao = self.cleaned_data.get('descricao')
                    abono.acao_abono = acao_abono
                    abono.solicitacao_abono_parcial = solicitacao
                    abono.ch_descontada = self.get_ch_descontada_em_segundos()
                    abono.save()

                    # carga horária solicitada a abonar final para o caso de
                    # avaliação de uma única solicitação de abono parcial
                    if len(self.solicitacoes) == 1:
                        solicitacao.set_ch_abonada_chefe_imediato(self.get_ch_solicitada_a_abonar_confirmacao_em_segundos(), vinculo_chefe_imediato)

                    # solicitação avaliada
                    solicitacao.situacao = SolicitacaoAbonoParcial.SITUACAO_AVALIADO
                    solicitacao.vinculo_chefe_imediato = vinculo_chefe_imediato
                    solicitacao.save()

                if tem_erros:
                    result_erros.append(' '.join(erros))

            return result_erros

    return SolicitacaoAbonoParcialAvaliarForm


# EDIÇÃO DE ABONO DE CHEFIA COM OU SEM SOLICITAÇÃO DE ABONO PARCIAL


def AbonoChefiaChangeFormFactory(inconsistencias, abono_chefia):
    form_utils = AbonoChefiaFormUtils(inconsistencias, abono_chefia.solicitacao_abono_parcial is not None)
    form_fields = form_utils.get_fields()

    class AbonoChefiaChangeForm(forms.FormPlus):
        ch_solicitada_a_abonar_confirmacao_hms = form_fields.get('ch_solicitada_a_abonar_confirmacao_hms')
        descricao = form_fields.get('descricao')
        acao_abono = form_fields.get('acao_abono')
        ch_descontada_hms = form_fields.get('ch_descontada_hms')

        def __init__(self, *args, **kwargs):
            self.instance = kwargs.pop('instance')
            super().__init__(*args, **kwargs)
            if 'ch_solicitada_a_abonar_confirmacao_hms' in self.fields and abono_chefia.solicitacao_abono_parcial:
                self.fields['ch_solicitada_a_abonar_confirmacao_hms'].initial = timedelta(
                    seconds=abono_chefia.solicitacao_abono_parcial.ch_solicitada
                )
            if 'ch_descontada_hms' in self.fields and self.instance.ch_descontada:
                self.fields['ch_descontada_hms'].initial = timedelta(seconds=self.instance.ch_descontada)
            self.descricao_abonos = form_utils.get_descricao_abonos()
            self.fields['acao_abono'].initial = self.instance.acao_abono

        def clean(self):
            clean = super().clean()

            acao_abono_nao_abonado = clean.get('acao_abono') == f'{AbonoChefia.NAO_ABONADO}'
            if acao_abono_nao_abonado and not clean.get('descricao'):
                self.add_error('descricao', 'Nesse caso, informe uma descrição/observação sobre os motivos que o levaram a não abonar.')

            abono = self.instance
            if abono.solicitacao_abono_parcial:
                if self.is_valid():  # and not clean.get('acao_abono') == f'{AbonoChefia.NAO_ABONADO}':
                    # revalida a solicitação
                    solicitacao = abono.solicitacao_abono_parcial

                    solicitacao_abono_solicitado = solicitacao.abono_solicitado

                    if clean.get('acao_abono') != f'{solicitacao_abono_solicitado}':
                        # nesse caso, o chefe imediato mudou a ação do abono em comparação ao que foi solicitado
                        # então, a revalidação da solicitação deve considerar, temporariamente, a ação do abono que
                        # foi escolhida pelo chefe imediato
                        solicitacao.abono_solicitado = int(clean.get('acao_abono'))

                    errors = SolicitacaoAbonoParcial.validar(solicitacao, revalidar=True)

                    if errors:
                        self.add_error(None, f'A solicitação "{solicitacao}" não pode ser avaliada: {" ".join(errors)}')
                        self.add_error(
                            None,
                            f'Você deverá remover esta avaliação para que o servidor "{solicitacao.vinculo_pessoa.relacionamento}" possa revisar/verificar sua solicitação.',
                        )

                    # restaura/reafirma o valor original do abono solicitado
                    solicitacao.abono_solicitado = solicitacao_abono_solicitado

            return clean

        def get_ch_solicitada_a_abonar_confirmacao_em_segundos(self):
            ch_solicitada_a_abonar_confirmacao_hms: timedelta = self.cleaned_data.get('ch_solicitada_a_abonar_confirmacao_hms', timedelta(0))
            return ch_solicitada_a_abonar_confirmacao_hms.total_seconds()

        def get_ch_descontada_em_segundos(self):
            ch_descontada_hms: timedelta = self.cleaned_data.get('ch_descontada_hms', timedelta(0))
            return ch_descontada_hms.total_seconds() if ch_descontada_hms else None

        def save(self, commit=True):
            vinculo_chefe_imediato = self.request.user.get_vinculo()
            # atualiza o abono
            abono = self.instance
            abono.vinculo_chefe_imediato = vinculo_chefe_imediato
            abono.descricao = self.cleaned_data.get('descricao')
            abono.acao_abono = int(self.cleaned_data.get('acao_abono'))
            abono.ch_descontada = self.get_ch_descontada_em_segundos()
            abono.save()
            # atualiza a solicitação de abono parcial relacionada (se for o caso)
            if abono.solicitacao_abono_parcial:
                solicitacao = abono.solicitacao_abono_parcial
                solicitacao.situacao = SolicitacaoAbonoParcial.SITUACAO_AVALIADO
                solicitacao.vinculo_chefe_imediato = vinculo_chefe_imediato
                solicitacao.set_ch_abonada_chefe_imediato(self.get_ch_solicitada_a_abonar_confirmacao_em_segundos(), vinculo_chefe_imediato)
                solicitacao.save()

    return AbonoChefiaChangeForm


# REVISÃO DE ABONO DE CHEFIA


def SolicitacaoRevisaoAbonoChefiaFormFactory(
    vinculo: Vinculo,
    data_inicio: datetime.date,
    data_fim: datetime.date,
):
    if not (vinculo and data_inicio and data_fim):
        raise ValueError

    def get_abonos():
        return AbonoChefia.get_abonos_chefia(vinculo, data_inicio, data_fim)

    def get_abonos_choices():
        abonos = get_abonos()
        choices = []
        for data in datas_entre(data_inicio, data_fim):
            choices.extend([[abono.id, f'{abono.display}'] for abono in abonos.get(data, [])])
        return choices

    class SolicitacaoRevisaoAbonoChefiaForm(forms.FormPlus):
        abono_chefia = forms.ChoiceField(
            label='Abono de Chefia a Revisar',
            choices=[[None, 'Selecione'], *get_abonos_choices()],
            required=True,
        )
        justificativa = forms.CharField(
            label='Justificativa',
            required=True,
            widget=forms.Textarea(),
        )

        def clean_abono_chefia(self):
            return AbonoChefia.objects.filter(id=self.cleaned_data.get('abono_chefia')).first()

        def clean(self):
            clean = super().clean()
            if not self.errors:
                try:
                    AbonoChefia.adiciona_solicitacao_revisao_abono_chefia(
                        vinculo,
                        clean.get('abono_chefia'),
                        clean.get('justificativa'),
                        commit=False,
                    )
                except PontoException as error:
                    self.add_error(None, f'{error}')
                except Exception:
                    self.add_error(None, 'Ocorre um erro. Tente novamente.')
            return clean

        def save(self, commit=True):
            return AbonoChefia.adiciona_solicitacao_revisao_abono_chefia(
                vinculo,
                self.cleaned_data.get('abono_chefia'),
                self.cleaned_data.get('justificativa'),
                commit=commit,
            )

    return SolicitacaoRevisaoAbonoChefiaForm


class SolicitacaoRevisaoAbonoChefiaChangeForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoRevisaoAbonoChefia
        fields = ('justificativa',)

    def save(self, commit=True):
        return AbonoChefia.altera_solicitacao_revisao_abono_chefia(
            self.instance,
            self.cleaned_data.get('justificativa'),
            commit=commit,
        )


class AvaliacaoRevisaoAbonoChefiaChangeForm(forms.ModelFormPlus):
    acao_abono_chefia = forms.ChoiceField(
        label='Ação sobre o abono revisado',
        choices=[
            [None, 'Selecione'],
            ['manter', 'Manter o abono'],
            ['editar', 'Editar o abono'],
            ['remover', 'Remover o abono'],
        ],
        required=True,
    )

    class Meta:
        model = SolicitacaoRevisaoAbonoChefia
        fields = (
            'acao_abono_chefia',
            'chefe_imediato_observacoes',
        )

    def __init__(self, *args, **kwargs):
        self.vinculo_chefe_imediato: Vinculo = kwargs.pop('vinculo_chefe_imediato')
        super().__init__(*args, **kwargs)

    def editar_abono(self):
        return self.cleaned_data.get('acao_abono_chefia') == 'editar'

    def remover_abono(self):
        return self.cleaned_data.get('acao_abono_chefia') == 'remover'

    def save(self, commit=True):
        return AbonoChefia.avalia_solicitacao_revisao_abono_chefia(
            self.instance,
            self.vinculo_chefe_imediato,
            self.cleaned_data.get('chefe_imediato_observacoes'),
            commit=commit,
        )


# FIM SOLICITAÇÃO DE ABONO PARCIAL / ABONO DE CHEFIA / REVISÃO DE ABONO DE CHEFIA


class DataRelatorioOcupacaoForm(forms.FormPlus):
    CHOICES_TIPO_RELACIONAMENTO = (
        ('', 'Todos'),
        ('servidor', 'Servidor'),
        ('prestador', 'Prestador de Serviço'),
        ('docente', 'Docente'),
        ('tecnico', 'Técnico Administrativo'),
        ('estagiario', 'Estagiário'),
    )
    data = DateFieldPlus(label='Data', required=True)
    tipo_relacionamento = forms.ChoiceField(choices=CHOICES_TIPO_RELACIONAMENTO, label='Tipo Relacionamento', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = date.today()
        self.fields['data'].initial = hoje
