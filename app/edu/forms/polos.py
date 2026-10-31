from django.core.exceptions import ValidationError
from django.db.models.aggregates import Count

from comum.models import Sala, UsuarioGrupo, UsuarioGrupoSetor, Vinculo
from djtools import forms
from djtools.db import transaction
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import format_iterable
from edu.models import (
    Aluno,
    AtividadePolo,
    CoordenadorPolo,
    CursoCampus,
    Polo,
    Turma,
    TutorPolo,
)

from .utils import grupos


class CoordenadorPoloForm(forms.ModelFormPlus):
    vinculo = forms.ModelChoiceField(
        Vinculo.objects.none(), required=True, label='Usuário', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )

    class Meta:
        model = CoordenadorPolo
        fields = 'vinculo', 'portaria_designacao'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.funcionarios().filter(ativo=True)

    @transaction.atomic
    def processar(self, polo):
        self.instance.polo_id = polo.id
        self.instance.save()
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR_POLO'], user=self.instance.vinculo.user)[0]
        UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=polo.diretoria.setor)


class TutorPoloForm(forms.FormPlus):
    vinculo = forms.ModelChoiceField(Vinculo.objects, required=True, label='Usuário', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS))
    cursos = forms.MultipleModelChoiceFieldPlus(CursoCampus.objects, required=True, label='Cursos')

    def __init__(self, polo, tutor_polo, *args, **kwargs):
        self.polo = polo
        self.tutor_polo = tutor_polo
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.funcionarios().filter(ativo=True)

    def processar(self):
        vinculo = self.cleaned_data['vinculo']
        cursos = self.cleaned_data['cursos']
        if self.tutor_polo:
            tutor_polo = self.tutor_polo
            tutor_polo.vinculo = vinculo
            tutor_polo.save()
        else:
            tutor_polo = TutorPolo.objects.get_or_create(vinculo=vinculo, polo=self.polo)[0]
        for curso_campus in cursos.all():
            tutor_polo.cursos.add(curso_campus)
        user = vinculo.user
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['TUTOR_POLO'], user=user)[0]
        UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.polo.diretoria.setor)
        return tutor_polo


class AtividadePoloForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs_polos = Polo.locals.all()
        self.fields['polo'].queryset = qs_polos.order_by('descricao')
        self.fields['sala'].queryset = Sala.ativas.filter(predio__uo__id__in=qs_polos.values_list('diretoria__setor__uo__id', flat=True))

    class Meta:
        model = AtividadePolo
        exclude = ('confirmada',)


class HorarioAtendimentoPoloForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    polos = forms.ModelMultiplePopupChoiceField(Polo.objects, label='Polo', required=False)
    tutor_polo = forms.ModelChoiceFieldPlus(
        TutorPolo.objects, label='Tutor', widget=AutocompleteWidget(search_fields=TutorPolo.SEARCH_FIELDS), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['polos'].queryset = Polo.objects.all().order_by('descricao')

    def clean(self):
        qs = Polo.objects.all()
        polos = self.cleaned_data['polos']
        tutor_polo = self.cleaned_data['tutor_polo']

        filtros = []

        if polos:
            qs = polos
            filtros.append({'chave': 'Polos', 'valor': format_iterable(polos)})
        if tutor_polo:
            qs = qs.filter(tutorpolo__polo=tutor_polo.polo)
            filtros.append({'chave': 'Tutor Polo', 'valor': str(tutor_polo)})

        qs = qs.annotate(null_position=Count('horariopolo')).order_by('-null_position').distinct()
        qs.filtros = filtros

        self.qs = qs
        return self.cleaned_data

    def processar(self):
        return self.qs


class TransferirPoloAlunoForm(FormWizardPlus):
    TRANSFERIR_POR_TURMA = 'TURMA'
    TRANSFERIR_POR_CURSO = 'CURSO'
    TIPO_TRANSFERENCIA_CHOICES = [[TRANSFERIR_POR_TURMA, 'Por Turma'], [TRANSFERIR_POR_CURSO, 'Por Curso']]

    tipo = forms.ChoiceField(label='Filtrar Alunos', choices=TIPO_TRANSFERENCIA_CHOICES, widget=forms.RadioSelect())
    turma = forms.ModelChoiceFieldPlus(Turma.objects, label='Turma', required=False)
    curso = forms.ModelChoiceFieldPlus(
        CursoCampus.objects, label='Curso', required=False, widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS)
    )
    polo = forms.ModelChoiceFieldPlus(Polo.objects, label='Polo')
    alunos = forms.MultipleModelChoiceField(Aluno.objects, label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html'))

    steps = (
        [('Filtro', {'fields': ('tipo', 'turma', 'curso')})],
        [('Polo de Destino', {'fields': ('polo',)}), ('Seleção dos Alunos', {'fields': ('alunos',)})],
    )

    class Media:
        js = ('/static/edu/js/ImprimirHistoricoFinalEmLoteForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def first_step(self):
        self.fields['turma'].queryset = Turma.objects.filter(matriculaperiodo__aluno__curso_campus__diretoria__ead=True).distinct()
        self.fields['curso'].queryset = CursoCampus.objects.filter(diretoria__ead=True)

    def next_step(self):
        curso = self.get_entered_data('curso')
        turma = self.get_entered_data('turma')

        if 'alunos' in self.fields:
            qs = self.fields['alunos'].queryset

            if curso:
                qs = qs.filter(curso_campus=curso)
            if turma:
                qs = qs.filter(matriculaperiodo__turma=turma)

            self.fields['alunos'].queryset = qs

    def clean_turma(self):
        if self.cleaned_data.get('tipo') == self.TRANSFERIR_POR_TURMA and not self.cleaned_data.get('turma'):
            raise ValidationError('Informe a turma dos alunos.')
        return self.cleaned_data['turma']

    def clean_curso(self):
        if self.cleaned_data.get('tipo') == self.TRANSFERIR_POR_CURSO and not self.cleaned_data.get('curso'):
            raise ValidationError('Informe o curso dos alunos.')
        return self.cleaned_data['curso']

    def processar(self):
        polo = self.cleaned_data['polo']
        alunos = self.cleaned_data['alunos']

        for aluno in alunos:
            aluno.polo = polo
            aluno.save()
