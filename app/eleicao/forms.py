import operator
from functools import reduce

from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models.functions import Lower
from django.db.models.query_utils import Q

from comum.models import Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, TextareaCounterWidget
from edu.models import Aluno
from eleicao.models import Candidato, Chapa, Edital, Eleicao, Voto
from rh.models import Servidor, UnidadeOrganizacional


class EditalForm(forms.ModelFormPlus):
    vinculos_coordenadores = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects, label='Coordenadores do Edital', required=True)

    class Meta:
        model = Edital
        fields = (
            'descricao',
            'data_inscricao_inicio',
            'data_inscricao_fim',
            'data_validacao_inicio',
            'data_validacao_fim',
            'data_campanha_inicio',
            'data_campanha_fim',
            'data_votacao_inicio',
            'data_votacao_fim',
            'data_pre_resultado_inicio',
            'data_pre_resultado_fim',
            'data_homologacao_inicio',
            'data_homologacao_fim',
            'data_resultado_final',
            'vinculos_coordenadores',
        )


class EleicaoForm(forms.ModelFormPlus):
    pessoas_relacionadas_eleicao = forms.MultipleModelChoiceFieldPlus(
        label='Servidores',
        help_text='Selecione servidores para se inscreverem e votarem nesta eleição',
        required=False,
        queryset=Servidor.objects.all(),
    )
    campi = forms.MultipleModelChoiceFieldPlus(
        label='Campi', required=False, queryset=UnidadeOrganizacional.objects.suap().all(), widget=FilteredSelectMultiple('', True)
    )
    alunos_relacionados_eleicao = forms.MultipleModelChoiceFieldPlus(
        label='Alunos', help_text='Selecione alunos para se inscreverem e votarem nesta eleição', required=False, queryset=Aluno.objects.all()
    )

    descricao = forms.CharFieldPlus(label='Descrição', width=500)

    class Meta:
        model = Eleicao
        fields = (
            'edital',
            'descricao',
            'pessoas_relacionadas_eleicao',
            'alunos_relacionados_eleicao',
            'publico',
            'campi',
            'votacao_global',
            'resultado_global',
            'caracteres_campanha',
            'caracteres_recurso',
            'obs_voto',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edital_queryset = Edital.objects.all()
        if not self.request.user.is_superuser:
            edital_queryset = edital_queryset.filter(vinculos_coordenadores__in=[self.request.user.get_vinculo()])
        self.fields['edital'].queryset = edital_queryset
        self.instance.tipo = Eleicao.TIPO_INDIVIDUAL

    def clean(self):
        cleaned_data = super().clean()
        # pessoas_relacionadas_eleicao = cleaned_data.get('pessoas_relacionadas_eleicao', None)
        # publico = cleaned_data.get('publico', None)
        # campi = cleaned_data.get('campi', None)
        # if pessoas_relacionadas_eleicao or publico or campi:
        #     if (publico and pessoas_relacionadas_eleicao) or (campi and pessoas_relacionadas_eleicao):
        #         self.add_error('pessoas_relacionadas_eleicao',
        #                        u'Apenas um tipo de público pode ser selecionado.')
        #         self.add_error('publico',
        #                        u'Apenas um tipo de público pode ser selecionado.')
        #         self.add_error('campi',
        #                        u'Apenas um tipo de público pode ser selecionado.')
        #     if not pessoas_relacionadas_eleicao and (campi or publico):
        #         self.add_error(None,
        #                        u'Um público deve ser informado.')

        return cleaned_data


class ChapaAdminForm(forms.ModelFormPlus):
    descricao = forms.CharField(label='Descrição', widget=TextareaCounterWidget(max_length=1000))

    class Meta:
        model = Chapa
        exclude = ()


class CandidatoAdminForm(forms.ModelFormPlus):
    candidato_vinculo = forms.ModelChoiceField(
        queryset=Vinculo.objects.all(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Candidato', required=True
    )
    descricao = forms.CharField(label='Descrição', widget=TextareaCounterWidget(max_length=1000))

    class Meta:
        model = Candidato
        fields = ('eleicao', 'candidato_vinculo', 'descricao', 'status', 'justificativa_parecer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        eleicao_queryset = Eleicao.objects.all()
        if not self.request.user.is_superuser:
            eleicao_queryset = eleicao_queryset.filter(edital__vinculos_coordenadores=self.request.user.get_vinculo())
        self.fields['eleicao'].queryset = eleicao_queryset
        if self.instance.pk:
            self.fields['descricao'].widget.max_length = self.instance.eleicao.caracteres_campanha

    def clean_justificativa_parecer(self):
        cleaned_data = self.cleaned_data
        status = cleaned_data.get('status')
        justificativa_parecer = cleaned_data.get('justificativa_parecer')
        if status == Candidato.STATUS_INDEFERIDO and not justificativa_parecer:
            raise forms.ValidationError('A justificativa é obrigatória.')
        return justificativa_parecer


class ChapaInscricaoForm(forms.ModelFormPlus):
    title = 'Inscrição de Chapa para a Eleição'
    descricao = forms.CharField(label='Descrição', widget=TextareaCounterWidget(max_length=1000))

    class Meta:
        model = Chapa
        fields = ('nome', 'descricao')

    def __init__(self, *args, **kwargs):
        eleicao = kwargs.pop('eleicao')
        super().__init__(*args, **kwargs)
        self.fields['descricao'].widget.max_length = eleicao.caracteres_campanha
        self.instance.eleicao = eleicao

        self.title = f'Inscrição para: {eleicao.descricao}'


class CandidatoInscricaoForm(forms.ModelFormPlus):
    title = 'Inscrição de Chapa para a Eleição'
    descricao = forms.CharField(
        label='Texto de Apresentação',
        widget=TextareaCounterWidget(max_length=1000),
        help_text='Este texto irá aparecer para o eleitor no momento da divulgação da candidatura e na votação',
    )

    class Meta:
        model = Candidato
        fields = ('descricao',)

    def __init__(self, *args, **kwargs):
        eleicao = kwargs.pop('eleicao', None)
        super().__init__(*args, **kwargs)
        self.fields['descricao'].widget.max_length = eleicao.caracteres_campanha

        self.title = f'Inscrição para: {eleicao.descricao}'


class EditarInscricaoForm(forms.ModelFormPlus):
    descricao = forms.CharField(label='Texto de Apresentação', required=True, widget=forms.Textarea())

    class Meta:
        model = Candidato
        fields = ('descricao',)


class CandidatoValidarForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'

    eleicao = forms.CharField(label='Eleição', required=False)
    candidato = forms.CharField(label='Candidato', required=False)
    descricao = forms.CharField(label='Texto de Apresentação', required=False, widget=forms.Textarea())
    status = forms.ChoiceField(label='Parecer', choices=Candidato.STATUS_CHOICES, initial=Candidato.STATUS_PENDENTE)
    justificativa_parecer = forms.CharField(label='Justificativa', required=False, widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        self.candidato = kwargs.pop('candidato', None)
        super().__init__(*args, **kwargs)
        self.fields['eleicao'].initial = self.candidato.eleicao
        self.fields['eleicao'].widget.attrs['readonly'] = 'readonly'

        self.fields['candidato'].initial = self.candidato.candidato_vinculo.pessoa.nome
        self.fields['candidato'].widget.attrs['readonly'] = 'readonly'

        self.fields['descricao'].initial = self.candidato.descricao
        self.fields['descricao'].widget.attrs['readonly'] = 'readonly'

    def clean(self):
        cleaned_data = super().clean()
        if 'status' in self.cleaned_data:
            if self.cleaned_data['status'] in [Candidato.STATUS_PENDENTE, Candidato.STATUS_NAO_APLICADO]:
                self._errors['status'] = self.error_class(['O parecer não pode ser {}'.format(self.cleaned_data['status'].lower())])
                del cleaned_data['status']
            else:
                if self.cleaned_data['status'] == Candidato.STATUS_INDEFERIDO:
                    if 'justificativa_parecer' in cleaned_data and len(cleaned_data['justificativa_parecer'].strip()) == 0:
                        self._errors['justificativa_parecer'] = self.error_class(['A justificativa é obrigatória para o parecer indeferido.'])
                        del cleaned_data['justificativa_parecer']

        return cleaned_data

    def validar(self):
        self.candidato.status = self.cleaned_data.get('status', None)
        self.candidato.justificativa_parecer = self.cleaned_data['justificativa_parecer']
        self.candidato.save()


class ChapaValidarForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'

    eleicao = forms.CharField(label='Eleição', required=False)
    nome = forms.CharField(label='Nome', required=False)
    descricao = forms.CharField(label='Texto de Apresentação', required=False, widget=forms.Textarea())
    status = forms.ChoiceField(label='Parecer', choices=Chapa.STATUS_CHOICES, initial=Chapa.STATUS_PENDENTE)
    justificativa_parecer = forms.CharField(label='Justificativa', required=False, widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        self.chapa = kwargs.pop('chapa', None)
        super().__init__(*args, **kwargs)
        self.fields['eleicao'].initial = self.chapa.eleicao
        self.fields['eleicao'].widget.attrs['readonly'] = 'readonly'

        self.fields['nome'].initial = self.chapa.nome
        self.fields['nome'].widget.attrs['readonly'] = 'readonly'

        self.fields['descricao'].initial = self.chapa.descricao
        self.fields['descricao'].widget.attrs['readonly'] = 'readonly'

    def clean(self):
        cleaned_data = super().clean()
        if 'status' in self.cleaned_data:
            if self.cleaned_data['status'] == Chapa.STATUS_PENDENTE:
                self._errors['status'] = self.error_class(['O parecer não pode ser {}'.format(self.cleaned_data['status'].lower())])
                del cleaned_data['status']
            else:
                if self.cleaned_data['status'] == Chapa.STATUS_INDEFERIDO:
                    if 'justificativa_parecer' in cleaned_data and len(cleaned_data['justificativa_parecer'].strip()) == 0:
                        self._errors['justificativa_parecer'] = self.error_class(['A justificativa é obrigatória para o parecer indeferido.'])
                        del cleaned_data['justificativa_parecer']

        return cleaned_data

    def validar(self):
        self.chapa.status = self.cleaned_data.get('status', None)
        self.chapa.justificativa_parecer = self.cleaned_data['justificativa_parecer']
        self.chapa.save()


class ValidarVotoForm(forms.ModelFormPlus):
    class Meta:
        model = Voto
        fields = ('justificativa_avaliacao',)


class ValidarVotoBuscarForm(forms.FormPlus):
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), label='Campus', required=False)
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    def processar(self, votos):
        campus = self.cleaned_data.get('campus', None)
        if campus:
            votos = votos.filter(campus=campus)

        return votos


class ResultadoForm(forms.FormPlus):
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), label='Campus', required=False)
    METHOD = 'GET'


class BuscarPublicoForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'
    texto_busca = forms.CharField(label='Por Nome ou Matrícula', required=False)

    def __init__(self, *args, **kwargs):
        eleicao = kwargs.pop('eleicao')
        super().__init__(*args, **kwargs)
        self.eleicao = eleicao

    def processar(self):
        vinculos = self.eleicao.vinculo_publico_eleicao.all()
        if self.cleaned_data['texto_busca']:
            texto_busca = self.cleaned_data['texto_busca']
            vinculos = vinculos.filter(
                reduce(
                    operator.or_,
                    [
                        Q(pessoa__pessoafisica__cpf__icontains=texto_busca),
                        Q(user__username__icontains=texto_busca),
                        Q(pessoa__nome__icontains=texto_busca),
                    ],
                )
            )

        return vinculos.order_by(Lower('pessoa__nome'))
