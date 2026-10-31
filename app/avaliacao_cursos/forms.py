from avaliacao_cursos.models import GrupoPergunta, OpcaoRespostaPergunta, Pergunta, Questionario, Respondente, Segmento
from comum.models import Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from edu.models.cadastros_gerais import Modalidade
from edu.models.cursos import Matriz
from rh.models import UnidadeOrganizacional


class ResultadoForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    segmento = forms.ModelMultiplePopupChoiceField(queryset=Segmento.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def processar(self):
        qs = Respondente.objects.all()

        segmento = self.cleaned_data['segmento']

        if segmento:
            qs = qs.filter(segmento__in=segmento)

        return qs


class QuestionarioForm(forms.ModelFormPlus):
    segmentos = forms.ModelMultiplePopupChoiceField(queryset=Segmento.objects.all(), label='Segmentos')
    modalidades = forms.ModelMultiplePopupChoiceField(queryset=Modalidade.objects.all(), label='Modalidades')

    class Meta:
        model = Questionario
        exclude = ()


class AdicionarQuestionarioForm(forms.ModelFormPlus):
    segmentos = forms.MultipleModelChoiceFieldPlus(queryset=Segmento.objects.all(), label='Segmentos')
    modalidades = forms.MultipleModelChoiceFieldPlus(queryset=Modalidade.objects.all(), label='Modalidades')

    class Meta:
        model = Questionario
        exclude = ('avaliacao',)


class GrupoPerguntaForm(forms.ModelFormPlus):
    class Meta:
        model = GrupoPergunta
        exclude = ('questionario',)


class PerguntaForm(forms.ModelFormPlus):
    class Meta:
        model = Pergunta
        exclude = ('grupo_pergunta',)

    def clean(self):
        multipla_escolha = self.cleaned_data.get('multipla_escolha')
        tipo_resposta = self.cleaned_data.get('tipo_resposta')
        if multipla_escolha and not tipo_resposta == Pergunta.RESPOSTA_OBJETIVA:
            raise forms.ValidationError('Apenas a resposta do tipo OBJETIVA pode ser de múltipla escolha.')
        return self.cleaned_data


class OpcaoRespostaPerguntaForm(forms.ModelFormPlus):
    class Meta:
        model = OpcaoRespostaPergunta
        exclude = ('pergunta',)


class OpcoesRespostaPerguntaForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in range(10):
            self.fields[f'opcao{i}'] = forms.CharFieldPlus(label=f'Opção {i}', required=False)

    def save(self, pergunta):
        for i in range(10):
            opcao = self.cleaned_data.get(f'opcao{i}')
            if opcao:
                OpcaoRespostaPergunta.objects.create(pergunta=pergunta, valor=opcao)


class RespondentesForm(forms.FormPlus):
    segmentos = forms.ModelMultiplePopupChoiceField(queryset=Segmento.objects.all(), required=False, label='Segmentos')
    vinculo = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.filter(tipo_relacionamento__model__in=['aluno', 'servidor']),
        required=False,
        label='Respondente',
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    def __init__(self, questionario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.questionario = questionario

    def processar(self):
        qs = self.questionario.respondente_set.all()

        segmentos = self.cleaned_data['segmentos']
        vinculo = self.cleaned_data['vinculo']

        if segmentos:
            qs = qs.filter(segmento__in=segmentos)

        if vinculo:
            qs = qs.filter(vinculo=vinculo)

        return qs


class RelatorioForm(forms.FormPlus):
    uos = forms.ModelMultiplePopupChoiceField(queryset=UnidadeOrganizacional.objects.suap().all(), label='Campi', required=False)
    segmento = forms.ModelChoiceField(
        queryset=Segmento.objects.filter(pk__in=(Segmento.ALUNO, Segmento.PROFESSOR)), label='Segmento', widget=forms.RadioSelect(), empty_label=None
    )
    matriz = forms.ModelChoiceFieldPlus(queryset=Matriz.objects.filter(ativo=True), label='Matriz', required=False)
    modalidades = forms.ModelMultiplePopupChoiceField(
        queryset=Modalidade.objects.all(), label='Modalidades', widget=forms.CheckboxSelectMultiplePlus()
    )

    def __init__(self, avaliacao, *args, **kwargs):
        self.avaliacao = avaliacao
        super().__init__(*args, **kwargs)
        self.fields['modalidades'].queryset = Modalidade.objects.filter(pk__in=self.avaliacao.questionario_set.values_list('modalidades', flat=True))
