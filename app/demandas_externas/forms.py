from django.conf import settings

from comum.models import Vinculo
from demandas_externas.models import Demanda, Equipe, Periodo, PublicoAlvo, TipoAcao
from djtools import forms
from djtools.forms import ReCaptchaField
from djtools.forms.widgets import FilteredSelectMultiplePlus
from djtools.utils import running_tests
from edu.models import Cidade, Estado
from projetos.models import ColaboradorVoluntario
from rh.models import UnidadeOrganizacional


class PeriodoForm(forms.ModelFormPlus):
    campi = forms.MultipleModelChoiceFieldPlus(
        label='Campi', queryset=UnidadeOrganizacional.objects.uo().all(), widget=FilteredSelectMultiplePlus('', True), required=True
    )
    data_inicio = forms.DateFieldPlus(label='Início do Período')
    data_termino = forms.DateFieldPlus(label='Término do Período')

    class Meta:
        model = Periodo
        fields = ('titulo', 'data_inicio', 'data_termino', 'descricao', 'campi')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class DemandaForm(forms.ModelFormPlus):
    publico_alvo = forms.ModelMultipleChoiceField(
        queryset=PublicoAlvo.objects, widget=forms.CheckboxSelectMultiplePlus(), required=True, label='Público-Alvo'
    )
    campus_indicado = forms.ModelChoiceFieldPlus2(
        queryset=UnidadeOrganizacional.objects.uo().all().order_by('sigla'),
        label_template='{{ obj.nome }} ({{ obj.municipio.nome|format }})',
        label='Qual campus fica mais próximo da demanda?',
    )
    recaptcha = ReCaptchaField(label='')

    fieldsets = (
        (
            'Dados da Demanda',
            {'fields': ('tipo_demanda', 'nome_comunidade', 'campus_indicado', 'descricao', 'publico_alvo', 'qtd_prevista_beneficiados')},
        ),
        (
            'Dados do Responsável',
            {
                'fields': (
                    'nome',
                    'identificador',
                    'email',
                    'email_alternativo',
                    'telefones',
                    'whatsapp',
                    'municipio',
                    'recaptcha',
                )
            },
        ),
    )

    class Meta:
        model = Demanda
        fields = (
            'tipo_demanda',
            'nome',
            'identificador',
            'email',
            'email_alternativo',
            'telefones',
            'whatsapp',
            'municipio',
            'nome_comunidade',
            'campus_indicado',
            'descricao',
            'publico_alvo',
            'qtd_prevista_beneficiados',
            'recaptcha',
        )

    def __init__(self, *args, **kwargs):
        self.periodo = kwargs.pop('periodo', None)
        self.sigla_instituicao = kwargs.pop('sigla_instituicao', None)
        super().__init__(*args, **kwargs)
        self.fields['municipio'].queryset = Cidade.objects.filter(estado__id=Estado.ESTADOS.get('RN'))
        self.fields['campus_indicado'].queryset = UnidadeOrganizacional.objects.uo().filter(
            id__in=self.periodo.campi.all().values_list('id', flat=True)
        )
        if self.sigla_instituicao:
            self.fields['campus_indicado'].label = f'Campus do {self.sigla_instituicao} que fica mais próximo da demanda'
        self.fields['descricao'].widget = forms.Textarea()
        self.fields['publico_alvo'].queryset = PublicoAlvo.objects.filter(ativo=True)
        self.fields['email'].help_text = 'Informe um email válido. Todo aviso sobre o andamento da demanda será enviado para o email informado.'
        self.fields['descricao'].help_text = 'Espaço máximo de 5.000 caracteres'
        if running_tests() or settings.DEBUG:
            del self.fields['recaptcha']


class RecusarDemandaForm(forms.ModelFormPlus):
    class Meta:
        model = Demanda
        fields = ('observacoes',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['observacoes'].widget = forms.Textarea()
        self.fields['observacoes'].required = True
        self.fields['observacoes'].label = 'Justificativa'
        self.fields['observacoes'].help_text = 'Atenção! A justificativa do não aceite desta demanda será enviada por email para o demandante.'


class AtribuirDemandaForm(forms.ModelFormPlus):
    class Meta:
        model = Demanda
        fields = ('responsavel', 'data_prevista')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('demandas_externas.view_publicoalvo'):
            id_vinculo = self.request.user.get_vinculo().id
            self.fields['responsavel'] = forms.ModelChoiceFieldPlus(label='Responsável', queryset=Vinculo.objects, required=True)
            self.fields['responsavel'].queryset = Vinculo.objects.filter(id=id_vinculo)
            self.fields['responsavel'].initial = id_vinculo
        else:
            self.fields['responsavel'] = forms.ModelChoiceFieldPlus(
                label='Responsável',
                queryset=Vinculo.objects.filter(setor__uo=self.instance.campus_atendimento, tipo_relacionamento__model='servidor'),
                required=True,
            )


class IndicarCampusForm(forms.ModelFormPlus):
    class Meta:
        model = Demanda
        fields = ('campus_atendimento',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus_atendimento'].queryset = UnidadeOrganizacional.objects.uo().all()


class MembroEquipeForm(forms.FormPlus):
    participantes = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Participantes', required=False)

    def __init__(self, *args, **kwargs):
        self.demanda = kwargs.pop('demanda', None)
        super().__init__(*args, **kwargs)
        self.fields['participantes'].queryset = Vinculo.objects.filter(tipo_relacionamento__model__in=['aluno', 'servidor']) | Vinculo.objects.filter(
            id__in=ColaboradorVoluntario.objects.values_list('prestador__vinculo', flat=True)
        )
        if Equipe.objects.filter(demanda=self.demanda).exists():
            self.fields['participantes'].initial = self.demanda.equipe_set.all().values_list('participante', flat=True)


class RegistrarAtendimentoForm(forms.ModelFormPlus):
    class Meta:
        model = Demanda
        fields = ('tipo_acao', 'area_tematica', 'qtd_beneficiados_atendidos', 'descricao_atendimento')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao_atendimento'].widget = forms.Textarea()
        self.fields['descricao_atendimento'].max_length = 5000
        self.fields['descricao_atendimento'].help_text = 'Espaço máximo de 5.000 caracteres'
        self.fields['descricao_atendimento'].required = True
        self.fields['tipo_acao'].queryset = TipoAcao.objects.filter(ativo=True)


class AtribuirPrioridadeForm(forms.ModelFormPlus):
    class Meta:
        model = Demanda
        fields = ('prioridade',)
