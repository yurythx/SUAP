from datetime import date

from django.forms.utils import ErrorList

from comum.models import Configuracao
from comum.utils import get_uo
from djtools import forms
from djtools.forms import AutocompleteWidget, TextareaCounterWidget
from pdp_ifrn.models import (
    PDP,
    AreaTematica,
    CompetenciaAssociada,
    EnfoqueDesenvolvimento,
    EspecificacaoTipoAprendizagem,
    HistoricoStatusResposta,
    Necessidade,
    PublicoAlvo,
    Resposta,
    TipoAprendizagem,
)
from rh.models import Setor, UnidadeOrganizacional


class RespostaForm(forms.ModelFormPlus):
    pdp = forms.ModelChoiceFieldPlus(queryset=PDP.objects.all(), required=True, label='PDP')
    enfoque_desenvolvimento = forms.ModelChoiceField(
        EnfoqueDesenvolvimento.objects,
        label='Qual a área que melhor identifica a temática relacionada a essa necessidade de desenvolvimento? (Macros)',
    )
    enfoque_outros = forms.CharField(
        required=False,
        label='Descreva quais são as outras necessidades de desenvolvimento não especificadas',
        widget=TextareaCounterWidget(max_length=20, attrs={'style': 'height:40px'}),
    )
    area_tematica = forms.ModelChoiceField(
        AreaTematica.objects,
        required=True,
        label='A ação de desenvolvimento para essa necessidade está relacionada a qual área temática dos Sistemas Estruturadores do Poder Executivo Federal?',
    )
    necessidade = forms.ChainedModelChoiceField(
        Necessidade.objects,
        label='Que necessidade de desenvolvimento o Campus/Reitoria possui?',
        required=True,
        obj_label='descricao',
        form_filters=[('area_tematica', 'area_tematica_id')],
    )
    justificativa_necessidade = forms.CharField(
        label='Que resultado essa ação de desenvolvimento trará?',
        help_text='<strong>OBS 1: </strong> indique os resultados organizacionais a serem alcançados; '
        '<strong>OBS 2: </strong> indique comportamento e/ou resultados pessoais que os servidores conseguirão apresentar com a realização da ação de desenvolvimento;',
        widget=TextareaCounterWidget(max_length=200, attrs={'style': 'height:80px'}),
    )
    acao_transversal = forms.ChoiceField(
        widget=forms.RadioSelect(),
        choices=Resposta.TIPO_SIM_NAO,
        label='Essa necessidade de desenvolvimento é transversal, ou seja, comum a múltiplas unidades do IFRN?',
    )
    publico_alvo = forms.ModelChoiceFieldPlus(
        PublicoAlvo.objects, required=True, label='Qual o público-alvo da ação de desenvolvimento para essa necessidade?'
    )

    # setor_beneficiado = forms.ModelChoiceFieldPlus(
    #    Setor.objects,
    #    required=True,
    #    label='Qual unidade funcional do IFRN será beneficiada pela ação de desenvolvimento para essa necessidade?'
    # )
    #
    setor_beneficiado = forms.MultipleModelChoiceFieldPlus(
        Setor.objects, required=True, label='Qual unidade funcional do IFRN será beneficiada pela ação de desenvolvimento para essa necessidade?'
    )

    qtd_pessoas_beneficiadas = forms.IntegerFieldPlus(
        label='Quantos servidores serão beneficiados pela ação de desenvolvimento para essa necessidade?', required=True
    )
    competencia_associada = forms.ModelMultipleChoiceField(
        label='Essa necessidade está associada a quais competências?',
        help_text='Permitido marcar até 3 competências.',
        required=True,
        queryset=CompetenciaAssociada.objects.filter(ativa=True),
        widget=forms.CheckboxSelectMultiplePlus(),
    )
    tipo_aprendizagem = forms.ModelChoiceField(
        TipoAprendizagem.objects,
        required=True,
        label='A ação de desenvolvimento para essa necessidade deve preferencialmente ser ofertada em qual tipo de aprendizagem?',
    )
    especificacao_tipo_aprendizagem = forms.ChainedModelChoiceField(
        EspecificacaoTipoAprendizagem.objects,
        label='De acordo com a resposta anterior, qual opção melhor caracteriza o subtipo de aprendizagem?',
        required=True,
        obj_label='descricao',
        form_filters=[('tipo_aprendizagem', 'tipo_aprendizagem_id')],
    )

    modalidade = forms.ChoiceField(widget=forms.RadioSelect(), choices=Resposta.TIPO_MODALIDADE, label='Modalidade')
    #
    titulo_necessidade = forms.CharField(
        label='Título previsto da ação de desenvolvimento',
        help_text='Em caso de já possuir uma opção em consideração qual seria o título previsto da ação de desenvolvimento para essa necessidade?',
        required=False,
    )

    ano_termino_acao = forms.IntegerFieldPlus(
        label='Em caso de já possuir uma opção em consideração, qual o término previsto da ação de desenvolvimento para essa necessidade?',
        help_text='Informe o ano de término da ação de desenvolvimento',
        required=False,
    )
    onus_inscricao = forms.ChoiceField(
        widget=forms.RadioSelect(), choices=Resposta.TIPO_SIM_NAO, label='A ação de desenvolvimento pode ser ofertada de modo gratuito?'
    )
    valor_onus_inscricao = forms.DecimalFieldPlus(
        label='Se não gratuita, qual o custo total previsto da ação de desenvolvimento para essa necessidade? (R$)',
        required=False,
        # help_text='Caso de tenha respondido SIM na pergunta anterior, informe o Se não gratuita, qual o custo total previsto da ação de desenvolvimento para essa necessidade?.'
    )

    # atendida_pelo_cfs = forms.ChoiceField(
    #    widget=forms.RadioSelect(),
    #    choices=Resposta.TIPO_SIM_NAO,
    #    label='A ação de desenvolvimento para essa necessidade pode ser ofertada pelo Centro de Formação de Servidores?'
    # )

    class Meta:
        model = Resposta
        exclude = ['servidor', 'campus', 'data_cadastro']

    class Media:
        js = ('/static/pdp_ifrn/js/respostas.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'acao_transversal'
        ].label = f'Essa necessidade de desenvolvimento é transversal, ou seja, comum a múltiplas unidades do {Configuracao.get_valor_por_chave("comum", "instituicao")}?'
        self.fields[
            'setor_beneficiado'
        ].label = f'Qual unidade funcional do {Configuracao.get_valor_por_chave("comum", "instituicao")} será beneficiada pela ação de desenvolvimento para essa necessidade?'

        pdp_id = None

        if self.request:
            pdp_id = self.request.GET.get('pdp_id')

        if pdp_id:
            try:
                pdp = PDP.objects.get(id=pdp_id, preenchimento_habilitado=True, data_inicial__lte=date.today(), data_final__gte=date.today())
                if pdp.manual:
                    self.fields['pdp'] = forms.ModelChoiceField(
                        label='PDP',
                        queryset=PDP.objects.filter(
                            preenchimento_habilitado=True, data_inicial__lte=date.today(), data_final__gte=date.today()
                        ).order_by('ano__ano'),
                        widget=AutocompleteWidget(readonly=True),
                        initial=pdp,
                        help_text=f'<strong>Clique <a href="{pdp.manual.url}" target="_blank">AQUI</a> para acessar o manual com instruções de preenchimento.</strong>',
                    )
                else:
                    self.fields['pdp'] = forms.ModelChoiceField(
                        label='PDP',
                        queryset=PDP.objects.filter(
                            preenchimento_habilitado=True, data_inicial__lte=date.today(), data_final__gte=date.today()
                        ).order_by('ano__ano'),
                        widget=AutocompleteWidget(readonly=True),
                        initial=pdp,
                    )
            except PDP.DoesNotExist, ValueError:
                self.fields['pdp'].queryset = PDP.objects.filter(
                    preenchimento_habilitado=True, data_inicial__lte=date.today(), data_final__gte=date.today()
                ).order_by('ano__ano')
        else:
            if self.request.user.is_superuser or self.request.user.groups.filter(name='Coordenador de PDP Sistêmico').exists():
                self.fields['pdp'].queryset = PDP.objects.all()
            else:
                self.fields['pdp'].queryset = PDP.objects.filter(
                    preenchimento_habilitado=True, data_inicial__lte=date.today(), data_final__gte=date.today()
                ).order_by('ano__ano')

    def clean_pdp(self):
        if 'pdp' in self.cleaned_data:
            hoje = date.today()
            pdp = self.cleaned_data['pdp']
            if hoje < pdp.data_inicial or hoje > pdp.data_final or not pdp.preenchimento_habilitado:
                user = self.request.user
                if not (user.is_superuser or user.groups.filter(name='Coordenador de PDP Sistêmico').exists()):
                    self._errors['pdp'] = ErrorList(['Período de lançamento não está aberto para o PDP selecionado.'])
        return self.cleaned_data['pdp']

    def clean_competencia_associada(self):
        if 'competencia_associada' in self.cleaned_data:
            competencias = self.cleaned_data['competencia_associada']
            if len(competencias) > 3:
                self._errors['competencia_associada'] = ErrorList(['Permitida a seleção de no máximo 3 competências associadas.'])
        return self.cleaned_data['competencia_associada']

    def clean_valor_onus_inscricao(self):
        if 'onus_inscricao' in self.cleaned_data and 'valor_onus_inscricao' in self.cleaned_data:
            if self.cleaned_data['onus_inscricao'] == 'nao':
                if not self.cleaned_data['valor_onus_inscricao']:
                    self._errors['valor_onus_inscricao'] = ErrorList(['Preenchimento obrigatório pois a opção "Sim" foi marcada acima.'])
        return self.cleaned_data['valor_onus_inscricao']

    def clean_ano_termino_acao(self):
        if 'pdp' in self.cleaned_data and 'ano_termino_acao' in self.cleaned_data:
            pdp = self.cleaned_data['pdp']
            ano_inicial = pdp.ano.ano
            ano_final = pdp.ano.ano + 5
            if self.cleaned_data['ano_termino_acao']:
                if not ano_inicial <= self.cleaned_data['ano_termino_acao'] <= ano_final:
                    self._errors['ano_termino_acao'] = ErrorList(
                        [f'O ano de término previsto da ação de desenvolvimento deve ser entre {ano_inicial} e {ano_final}.']
                    )
        return self.cleaned_data['ano_termino_acao']

    def clean_enfoque_outros(self):
        if 'enfoque_desenvolvimento' in self.cleaned_data:
            enfoque = self.cleaned_data['enfoque_desenvolvimento']
            if enfoque.descricao == 'Outras não especificadas':
                if 'enfoque_outros' in self.cleaned_data and not self.cleaned_data['enfoque_outros']:
                    self._errors['enfoque_outros'] = ErrorList(
                        ['Preenchimento obrigatório pois a opção "Outras não especificadas" foi marcada acima.']
                    )
        return self.cleaned_data['enfoque_outros']


class RespostasPDPForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'
    pdp = forms.ModelChoiceField(PDP.objects, label='PDP', required=True, empty_label=None)

    status = forms.ChoiceField(required=True, choices=HistoricoStatusResposta.STATUS_RESPOSTA, widget=forms.Select, label='Situação')

    campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects, required=False)
    setor = forms.ChainedModelChoiceField(
        Setor.objects.suap_ativos().filter(id__in=Resposta.objects.order_by().values_list('servidor__setor__id', flat=True).distinct()),
        label='Setor do Servidor',
        required=False,
        obj_label='sigla',
        form_filters=[('campus', 'uo')],
    )
    necessidade = forms.ModelChoiceField(Necessidade.objects, label='Necessidade', required=False)
    tipo_aprendizagem = forms.ModelChoiceField(TipoAprendizagem.objects, label='Tipo de Aprendizagem', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.request.user
        if not user.is_superuser and not user.groups.filter(name__in=['Coordenador de PDP Sistêmico', 'Homologador de PDP']).exists():
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
            self.fields['setor'].queryset = self.fields['setor'].queryset.filter(uo=get_uo(self.request.user))

        self.fields['status'].choices = [[0, '---------'], ['TODOS', 'Todos']] + [[st[0], st[1]] for st in HistoricoStatusResposta.STATUS_RESPOSTA]


class HistoricoStatusRespostaForm(forms.FormPlus):
    justificativa = forms.CharField(label='Justificativa', widget=TextareaCounterWidget(max_length=255, attrs={'style': 'height:80px'}))


# class ConsultaPDPForm(forms.FormPlus):
#     METHOD = 'GET'
#     SUBMIT_LABEL = 'Buscar'
#     anos = tuple(Resposta.objects.values_list('ano', flat=True).order_by('-ano').distinct())
#     ANOS_CHOICES = tuple(zip(('',) + anos, ('---------',) + anos))
#
#     campus = forms.ModelChoiceField(
#         label='Campus',
#         queryset=UnidadeOrganizacional.objects,
#         required=False,
#     )
#     ano = forms.ChoiceField(
#         label='Ano',
#         choices=ANOS_CHOICES,
#         required=False
#     )
#
#     def __init__(self, *args, **kwargs):
#         super(ConsultaPDPForm, self).__init__(*args, **kwargs)
#
#     def processar(self):
#         respostas = Resposta.objects.all()
#
#         # Exibe apenas as homologadas
#         respostas = [x for x in respostas if x.get_ultimo_status == 'homologada']
#
#         # Aplica filtros escolhidos
#         campus = self.cleaned_data['campus']
#         ano = self.cleaned_data['ano']
#
#         if campus:
#             respostas = [x for x in respostas if x.campus == campus]
#         if ano:
#             respostas = [x for x in respostas if x.ano == int(ano)]
#
#         return respostas
