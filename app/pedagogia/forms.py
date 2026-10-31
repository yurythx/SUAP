from comum.utils import tl
from djtools import forms
from edu.models import CursoCampus, Modalidade
from pedagogia.models import AvaliacaoDisciplina, AvaliacaoProcessualCurso, QuestionarioMatriz
from rh.models import UnidadeOrganizacional


class ResultadoAvaliacaoCursosForm(forms.FormPlus):
    MODALIDADE = 1
    CURSO = 2
    EXIBIR_CHOICES = [[MODALIDADE, 'Modalidade'], [CURSO, 'Curso']]
    filtrar_por = forms.ChoiceField(choices=EXIBIR_CHOICES, widget=forms.RadioSelect(), initial=1)
    modalidade = forms.ModelChoiceField(Modalidade.objects.all(), required=False)
    curso = forms.MultipleModelChoiceFieldPlus(QuestionarioMatriz.objects.all(), required=False, label='Cursos')
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), required=False, label='Campus')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modalidade'].queryset = Modalidade.objects.filter(cursocampus__questionariomatriz__isnull=False).distinct()

    def clean_curso(self):
        if self.cleaned_data.get('filtrar_por') == '2' and not self.cleaned_data.get('curso'):
            raise forms.ValidationError('Este campo é obrigatório.')
        return self.cleaned_data['curso']

    def clean_modalidade(self):
        if self.cleaned_data.get('filtrar_por') == '1' and not self.cleaned_data.get('modalidade'):
            raise forms.ValidationError('Este campo é obrigatório.')
        return self.cleaned_data['modalidade']

    def clean_filtrar_por(self):
        if not self.cleaned_data.get('filtrar_por'):
            raise forms.ValidationError('Este campo é obrigatório.')
        return self.cleaned_data['filtrar_por']

    class Media:
        js = ('/static/pedagogia/js/ResultadoAvaliacaoCursosForm.js',)


class QuestionarioMatrizForm(forms.ModelFormPlus):
    cursos = forms.MultipleModelChoiceFieldPlus(required=True, queryset=CursoCampus.objects.all(), label='Cursos')


class AvaliacaoProcessualCursoForm(forms.ModelFormPlus):
    class Meta:
        model = AvaliacaoProcessualCurso
        exclude = ('questionario_matriz',)

    def clean(self):
        for letra in 'hij':
            valores = []
            valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_1'))
            valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_2'))
            valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_3'))
            valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_4'))
            valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_5'))
            valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_6'))

            if letra != 'i':
                valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_7i'))
            else:
                valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_7'))
                valores.append(self.cleaned_data.get(f'parte_2_II_{letra}_8i'))

            lista_filtrada = [_f for _f in valores if _f]

            if lista_filtrada:
                set_valores = set(lista_filtrada)
                dicionario_qtd = {}
                for x in set_valores:
                    qtd = valores.count(x)
                    dicionario_qtd.update({x: qtd})

                for k, v in list(dicionario_qtd.items()):
                    if v > 1:
                        raise forms.ValidationError(f'O item {k} está repetido no item {letra.upper()}).')

        return self.cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        aluno = tl.get_user().get_relacionamento()
        self.questionario_matriz = QuestionarioMatriz.objects.get(cursos=aluno.curso_campus)
        nucleos = self.questionario_matriz.itemquestionariomatriz_set.order_by('nucleo').values_list('nucleo', flat=True).distinct()
        self.dados = []
        for nucleo in nucleos:
            itens = self.questionario_matriz.itemquestionariomatriz_set.filter(nucleo=nucleo).order_by('periodo', 'disciplina')
            for item in itens:
                fields = []
                areas = []
                for i in range(6):
                    initial = None
                    name = f'{item.pk}-{i}'

                    qs_avaliacao_disciplina = AvaliacaoDisciplina.objects.filter(
                        avaliacao_processual_curso=self.instance, item_questionario_matriz=item
                    )
                    if i <= 2:
                        if qs_avaliacao_disciplina.exists():
                            if i == 0:
                                initial = qs_avaliacao_disciplina[0].avaliacao_carga_horaria
                            elif i == 1:
                                initial = qs_avaliacao_disciplina[0].avaliacao_sequencia_didatica
                            elif i == 2:
                                initial = qs_avaliacao_disciplina[0].avaliacao_ementa_disciplina
                        field = forms.ChoiceField(choices=[['', ''], *AvaliacaoProcessualCurso.OPNIAO_CHOICES], required=False, initial=initial)
                        fields.append(name)
                    else:
                        if qs_avaliacao_disciplina.exists():
                            if i == 3:
                                initial = qs_avaliacao_disciplina[0].avaliacao_carga_horaria_justificativa
                            elif i == 4:
                                initial = qs_avaliacao_disciplina[0].avaliacao_sequencia_didatica_justificativa
                            elif i == 5:
                                initial = qs_avaliacao_disciplina[0].avaliacao_ementa_disciplina_justificativa
                        field = forms.CharField(widget=forms.HiddenInput(), required=False, initial=initial)
                        areas.append(name)
                    self.fields[name] = field

                item.fields = fields
                item.areas = areas
            self.dados.append({'nucleo': nucleo, 'itens': itens})

    def processar(self):
        aluno = tl.get_user().get_relacionamento()
        self.instance.aluno = aluno
        self.instance.questionario_matriz = self.questionario_matriz
        self.save()
        for item in self.questionario_matriz.itemquestionariomatriz_set.all():
            params = {
                'avaliacao_processual_curso': self.instance,
                'item_questionario_matriz': item,
                'avaliacao_carga_horaria': self.cleaned_data[f'{item.pk}-{0}'],
                'avaliacao_sequencia_didatica': self.cleaned_data[f'{item.pk}-{1}'],
                'avaliacao_ementa_disciplina': self.cleaned_data[f'{item.pk}-{2}'],
                'avaliacao_carga_horaria_justificativa': self.cleaned_data[f'{item.pk}-{3}'],
                'avaliacao_sequencia_didatica_justificativa': self.cleaned_data[f'{item.pk}-{4}'],
                'avaliacao_ementa_disciplina_justificativa': self.cleaned_data[f'{item.pk}-{5}'],
            }
            qs_avaliacao_disciplina = AvaliacaoDisciplina.objects.filter(avaliacao_processual_curso=self.instance, item_questionario_matriz=item)
            if qs_avaliacao_disciplina.exists():
                qs_avaliacao_disciplina.update(**params)
            else:
                AvaliacaoDisciplina.objects.create(**params)
