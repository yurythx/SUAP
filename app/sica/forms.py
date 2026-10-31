from djtools import forms
from edu.forms import AlunoCRAForm
from sica.models import ComponenteCurricular, RegistroHistorico


class RegistroHistoricoForm(forms.ModelFormPlus):
    fieldsets = (
        ('Dados gerais', {'fields': (('ano', 'periodo'), 'turma')}),
        ('Dados da Disciplina', {'fields': ('componente', ('periodo_matriz', 'carga_horaria'), 'opcional')}),
        ('Nota/Frequência', {'fields': (('nota', 'qtd_faltas'),)}),
        ('Situação', {'fields': ('situacao',)}),
    )

    class Meta:
        model = RegistroHistorico
        fields = 'componente', 'ano', 'periodo', 'turma', 'nota', 'qtd_faltas', 'carga_horaria', 'situacao', 'periodo_matriz', 'opcional'


class ComponenteCurricularForm(forms.ModelFormPlus):
    equivalencias = forms.MultipleModelChoiceField(
        ComponenteCurricular.objects.all(),
        required=False,
        label='Equivalências',
        widget=forms.CheckboxSelectMultiplePlus(),
        help_text='Marque a(s) disciplin(a)s que, quando paga(s), torna(m) esse componente curricular opcional.',
    )

    fieldsets = (
        ('Dados gerais', {'fields': (('periodo', 'qtd_creditos'), ('opcional', 'tipo'))}),
        ('Período de Vigência', {'fields': (('desde', 'ate'),)}),
        ('Equivalências', {'fields': (('equivalencias',),)}),
    )

    class Meta:
        model = ComponenteCurricular
        fields = 'periodo', 'qtd_creditos', 'tipo', 'opcional', 'desde', 'ate', 'equivalencias'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['equivalencias'].queryset = self.fields['equivalencias'].queryset.filter(
            matriz=self.instance.matriz, periodo=self.instance.periodo
        )


class EditarAlunoForm(AlunoCRAForm):
    comprovou_experiencia_proficional = forms.BooleanField(
        label='Comprovou Experiência Profisional',
        required=False,
        help_text='Marque essa opção caso o aluno tenha recorrido à portal 426/94 - DG/ETFRN',
    )
    carga_horaria_estagio = forms.IntegerField(label='C.H. de Estágio', required=False)
    dt_conclusao_curso = forms.DateFieldPlus(label='Data de Conclusão', required=False)

    fieldsets = (
        *AlunoCRAForm.fieldsets,
        ('Dados do Estágio', {'fields': ('comprovou_experiencia_proficional', 'carga_horaria_estagio')}),
        ('Dados da Conclusão', {'fields': ('dt_conclusao_curso',)}),
    )

    def __init__(self, *args, **kwargs):
        self.historico = kwargs.pop('historico')
        super().__init__(*args, **kwargs)
        self.fields['dt_conclusao_curso'].initial = self.instance.dt_conclusao_curso
        self.fields['carga_horaria_estagio'].initial = self.historico.carga_horaria_estagio
        self.fields['comprovou_experiencia_proficional'].initial = self.historico.comprovou_experiencia_proficional

    def save(self, *args, **kwargs):
        self.instance.dt_conclusao_curso = self.cleaned_data['dt_conclusao_curso']
        super().save(*args, **kwargs)
        self.historico.carga_horaria_estagio = self.cleaned_data['carga_horaria_estagio']
        self.historico.comprovou_experiencia_proficional = self.cleaned_data['comprovou_experiencia_proficional']
        self.historico.save()
