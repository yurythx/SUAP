from django.contrib.admin.widgets import FilteredSelectMultiple

from djtools import forms
from rh.models import UnidadeOrganizacional
from temp_rh3.models import QuestionarioAcumuloCargos, TermoAcumuloCargos


class QuestionarioForm(forms.ModelFormPlus):
    campus = forms.ModelMultipleChoiceField(
        label='Campi', queryset=UnidadeOrganizacional.objects.suap().all(), widget=FilteredSelectMultiple('', True), required=False
    )

    class Meta:
        exclude = ()
        model = QuestionarioAcumuloCargos


class ResponderQuestionarioAcumuloCargosForm(forms.ModelFormPlus):
    fieldsets = (
        (
            'Declaração de Acumulação de Cargos',
            {
                'fields': (
                    ('nao_possui_outro_vinculo',),
                    ('tem_outro_cargo_acumulavel',),
                    ('tem_aposentadoria',),
                    ('tem_pensao',),
                    ('tem_atuacao_gerencial',),
                    ('exerco_atividade_remunerada_privada',),
                )
            },
        ),
        (
            'Anexo 1 - Informações de Cargo/Emprego/Função ocupado em outro órgão',
            {
                'fields': (
                    ('anexo1_pergunta1', 'anexo1_pergunta2'),
                    ('anexo1_pergunta3',),
                    ('anexo1_pergunta4',),
                    ('anexo1_pergunta5',),
                    ('anexo1_pergunta6',),
                    ('anexo1_pergunta7', 'anexo1_pergunta8'),
                    ('anexo1_pergunta9', 'anexo1_pergunta10'),
                    ('anexo1_pergunta11', 'anexo1_pergunta12'),
                )
            },
        ),
        (
            'Anexo 2 - Informações de Aposentadoria em outro órgão',
            {
                'fields': (
                    ('anexo2_pergunta1', 'anexo2_pergunta2'),
                    ('anexo2_pergunta3',),
                    ('anexo2_pergunta4',),
                    ('anexo2_pergunta5',),
                    ('anexo2_pergunta6', 'anexo2_pergunta7'),
                    ('anexo2_pergunta8', 'anexo2_pergunta9'),
                    ('anexo2_pergunta10', 'anexo2_pergunta11'),
                )
            },
        ),
        (
            'Anexo 3 - Informações sobre Pensão Civil em outro órgão',
            {'fields': (('anexo3_pergunta1',), ('anexo3_pergunta2',), ('anexo3_pergunta3',), ('anexo3_pergunta4',), ('anexo3_pergunta5',))},
        ),
        (
            'Anexo 4 - Informações sobre atuação gerencial em atividade mercantil',
            {
                'fields': (
                    ('anexo4_empresa_que_atua',),
                    ('anexo4_tipo_atuacao_gerencial',),
                    ('anexo4_tipo_sociedade_mercantil',),
                    ('anexo4_descricao_atividade_exercida',),
                    ('anexo4_qual_participacao_societaria',),
                    ('anexo4_data_inicio_atuacao',),
                    ('anexo4_nao_exerco_atuacao_gerencial',),
                    ('anexo4_nao_exerco_comercio',),
                )
            },
        ),
        (
            'Anexo 5 - Informações sobre atividade remunerada privada',
            {
                'fields': (
                    ('anexo5_nome_empresa_trabalha',),
                    ('anexo5_funcao_emprego_ocupado',),
                    ('anexo5_jornada_trabalho',),
                    ('anexo5_nivel_escolaridade_funcao',),
                    ('anexo5_data_inicio_atividade',),
                    ('anexo5_nao_exerco_atividade_remunerada',),
                )
            },
        ),
    )

    class Meta:
        model = TermoAcumuloCargos
        exclude = ('servidor', 'questionario_acumulo_cargos')


class QuestionarioFiltroForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), label='Campus', required=False)
    questionario_acumulo_cargos = forms.ModelChoiceField(
        QuestionarioAcumuloCargos.objects.all(), label='Questionário de Acúmulo de Cargos', required=False
    )

    CHOICES = [[0, 'Todos'], [1, 'Sim'], [2, 'Não']]
    nao_possui_outro_vinculo = forms.ChoiceField(required=False, choices=CHOICES, label='Não possui outro vínculo')
    tem_outro_cargo_acumulavel = forms.ChoiceField(required=False, choices=CHOICES, label='Tem outro cargo acumulável')
    tem_aposentadoria = forms.ChoiceField(required=False, choices=CHOICES, label='Percebe aposentadoria')
    tem_pensao = forms.ChoiceField(required=False, choices=CHOICES, label='É beneficiário de pensão')

    fieldsets = (
        (
            '',
            {
                'fields': (
                    ('campus', 'questionario_acumulo_cargos'),
                    ('nao_possui_outro_vinculo', 'tem_outro_cargo_acumulavel'),
                    ('tem_aposentadoria', 'tem_pensao'),
                )
            },
        ),
    )
