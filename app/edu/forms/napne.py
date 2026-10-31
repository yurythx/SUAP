import datetime

from django.conf import settings

from comum.models import PrestadorServico, Raca
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)

if 'documento_eletronico' in settings.INSTALLED_APPS:
    from documento_eletronico.models import DocumentoTexto, NivelPermissao
from edu.models import (
    Aluno,
    CursoCampus,
    Deficiencia,
    TipoNEE,
)
from edu.models.napne import (
    Acolhimento,
    AcolhimentoAnexo,
    Acompanhamento,
    Entrevista,
    ProfissionalApoioEspecializado,
)
from rh.models import PessoaFisica, UnidadeOrganizacional


class AcolhimentoForm(forms.ModelFormPlus):
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects, label='Matrícula/Nome', widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS))

    class Meta:
        model = Acolhimento
        fields = ('aluno', 'data_acolhimento', 'relatorio')

    def __init__(self, *args, **kwargs):
        aluno = kwargs.pop('aluno', None)
        uo = kwargs.pop('uo', None)
        super().__init__(*args, **kwargs)
        self.fields['data_acolhimento'].initial = datetime.date.today()
        if self.instance and self.instance.pk:
            # Edição: aluno não pode ser alterado
            del self.fields['aluno']
        else:
            # Criação: aluno pode ser selecionado normalmente
            if aluno:
                self.fields['aluno'].initial = aluno
            alunos_qs = Aluno.ativos.exclude(id__in=Acolhimento.objects.values_list('aluno_id', flat=True))
            if uo:
                alunos_qs = alunos_qs.filter(curso_campus__diretoria__setor__uo=uo)

            self.fields['aluno'].queryset = alunos_qs


class AnexoAcolhimentoForm(forms.ModelFormPlus):
    if 'documento_eletronico' in settings.INSTALLED_APPS:
        documento_digital = forms.ModelChoiceField(
            label='Documento Digital',
            queryset=DocumentoTexto.objects.none(),
            widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
            required=False,
        )

    class Meta:
        model = AcolhimentoAnexo
        fields = ('descricao', 'arquivo', 'documento_digital')

    def __init__(self, *args, **kwargs):
        self.acolhimento = kwargs.pop('acolhimento')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            qs_documentos = DocumentoTexto.objects.compartilhados(self.user, NivelPermissao.LER) | DocumentoTexto.objects.proprios(self.user)
            self.fields['documento_digital'].queryset = qs_documentos
        else:
            del self.fields['documento_digital']

    def save(self, commit=True):
        if not self.instance.pk:
            self.instance.acolhimento = self.acolhimento
        return super().save(commit=commit)

    def clean(self):
        cleaned_data = super().clean()
        arquivo = cleaned_data.get('arquivo')
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            documento_digital = cleaned_data.get('documento_digital')
            if not arquivo and not documento_digital:
                raise forms.ValidationError('Informe o arquivo ou o documento digital.')
        else:
            if not arquivo:
                raise forms.ValidationError('Informe um arquivo.')
        return cleaned_data


class FiltroCampusForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.campi().all())


class FiltroAcolhimentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    texto = forms.CharField(label='Nome/Matrícula', required=False, widget=forms.TextInput(attrs={'placeholder': 'Nome ou Matrícula'}))
    sexo = forms.ChoiceField(required=False, choices=[('', '---------'), ['M', 'Masculino'], ['F', 'Feminino']])
    genero = forms.ChoiceField(required=False, label='Gênero', choices=[('', '---------'), *list(PessoaFisica.GENERO_CHOICES.items())])
    raca = forms.ModelChoiceField(Raca.objects.all(), required=False, label='Raça')

    deficiencias = forms.MultipleModelChoiceField(
        Deficiencia.objects,
        label='Deficiências',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Deficiencia.SEARCH_FIELDS,
            multiple=True,
        ),
    )
    outras_nees = forms.MultipleModelChoiceField(
        TipoNEE.objects,
        label='Outras NEEs',
        required=False,
        widget=AutocompleteWidget(
            search_fields=TipoNEE.SEARCH_FIELDS,
            multiple=True,
        ),
    )

    curso = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
    )
    campus = forms.ModelChoiceField(required=False, label='Campus', queryset=UnidadeOrganizacional.objects.campi().all())

    def __init__(self, *args, **kwargs):
        uo = kwargs.pop('uo', None)
        super().__init__(*args, **kwargs)
        if uo:
            self.fields['curso'].queryset = self.fields['curso'].queryset.filter(diretoria__setor__uo=uo)
            self.fields['campus'].queryset = self.fields['campus'].queryset.filter(pk=uo.id)


class EntrevistaForm(forms.ModelFormPlus):
    aluno_nome = forms.CharField(label='Aluno', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False)

    class Meta:
        model = Entrevista
        fields = ('aluno_nome', 'data_entrevista', 'anamnese', 'parecer', 'sugestoes_recursos')

    def __init__(self, *args, **kwargs):
        self.acolhimento = kwargs.pop('acolhimento', None)
        super().__init__(*args, **kwargs)
        self.fields['data_entrevista'].initial = datetime.date.today()
        if self.acolhimento:
            self.fields['aluno_nome'].initial = self.acolhimento.aluno

    def save(self, commit=True):
        if not self.instance.pk:
            self.instance.acolhimento = self.acolhimento
        return super().save(commit=commit)


class ProfissionalApoioEspecializadoForm(forms.ModelFormPlus):
    aluno_nome = forms.CharField(label='Aluno', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False)
    aluno_nees = forms.CharField(
        label='Necessidades Educacionais Específicas', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False
    )
    # aluno_campus e codigo_acolhimento estão sendo utilizados no javaScript para filtrar os profissionais por UO
    aluno_campus = forms.CharField(label='Campus', widget=forms.HiddenInput(), required=False)
    codigo_acolhimento = forms.CharField(label='Código do acolhimento', widget=forms.HiddenInput(), required=False)
    profissional = forms.ModelChoiceFieldPlus(
        queryset=PrestadorServico.objects.none(),
        widget=forms.Select(),
        label='Profissional',
    )

    class Meta:
        model = ProfissionalApoioEspecializado
        fields = ('aluno_nome', 'aluno_campus', 'codigo_acolhimento', 'aluno_nees', 'apoio_especializado', 'profissional', 'situacao')

    class Media:
        js = ('/static/edu/js/ProfissionalApoioEspecializadoForm.js',)

    def __init__(self, *args, **kwargs):
        self.acolhimento = kwargs.pop('acolhimento', None)
        self.profissional_id = kwargs.pop('profissional_id', None)
        super().__init__(*args, **kwargs)
        self.fields['aluno_nome'].initial = self.acolhimento.aluno
        self.fields['aluno_nees'].initial = ', '.join(self.acolhimento.aluno.get_nee())
        self.fields['aluno_campus'].initial = self.acolhimento.aluno.curso_campus.diretoria.setor.uo.id
        self.fields['codigo_acolhimento'].initial = self.acolhimento.id

        if self.profissional_id:
            self.fields['profissional'].queryset = PrestadorServico.objects.filter(pk=self.profissional_id)

    def save(self, commit=True):
        if not self.instance.pk:
            self.instance.acolhimento = self.acolhimento
        return super().save(commit=commit)


class AcompanhamentoForm(forms.ModelFormPlus):
    aluno_nome = forms.CharField(label='Aluno', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False)
    aluno_nees = forms.CharField(
        label='Necessidades Educacionais Específicas', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False
    )

    class Meta:
        model = Acompanhamento
        fields = ('aluno_nome', 'aluno_nees', 'descricao')

    def __init__(self, *args, **kwargs):
        self.profissional_apoio_especializado = kwargs.pop('profissional_apoio_especializado', None)
        self.acolhimento = kwargs.pop('acolhimento', None)
        super().__init__(*args, **kwargs)
        self.fields['aluno_nome'].initial = self.acolhimento.aluno
        self.fields['aluno_nees'].initial = ', '.join(self.acolhimento.aluno.get_nee())

    def save(self, commit=True):
        if not self.instance.pk:
            self.instance.acolhimento = self.acolhimento
            self.instance.profissional_apoio_especializado = self.profissional_apoio_especializado
        return super().save(commit=commit)


class AtualizarNeesAlunoForm(forms.ModelFormPlus):
    aluno_nome = forms.CharField(label='Aluno', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False)

    deficiencias = forms.MultipleModelChoiceField(
        Deficiencia.objects.filter(ativo=True),
        label='Deficiências',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Deficiencia.SEARCH_FIELDS,
            multiple=True,
        ),
    )
    outras_nees = forms.MultipleModelChoiceField(
        TipoNEE.objects.filter(ativo=True),
        label='Outros tipos de Necessidades Educacionais Específicas',
        required=False,
        widget=AutocompleteWidget(
            search_fields=TipoNEE.SEARCH_FIELDS,
            multiple=True,
        ),
    )

    class Meta:
        model = Aluno
        fields = ('aluno_nome', 'deficiencias', 'outras_nees')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['aluno_nome'].initial = self.instance
            self.fields['deficiencias'].initial = self.instance.deficiencias.all()
            self.fields['outras_nees'].initial = self.instance.outras_nees.all()
