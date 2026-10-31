from django.conf import settings

from comum.models import Ano
from djtools import forms
from djtools.templatetags.filters import in_group
from edu.models import (
    Aluno,
    AproveitamentoEstudo,
    CertificacaoConhecimento,
    Componente,
    ComponenteCurricular,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
    PedidoMatriculaDiario,
    Professor,
    RegistroHistorico,
)


class CertificarConhecimentoForm(forms.ModelFormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', help_text='Ano letivo da certificação.')
    periodo_letivo = forms.ChoiceField(
        label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES, help_text='Período letivo no qual a disciplina está sendo/foi certificada.'
    )

    class Meta:
        model = CertificacaoConhecimento
        fields = ('ano_letivo', 'periodo_letivo', 'data', 'nota', 'professores', 'servidores', 'ausente')

    fieldsets = (
        ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), ('data', 'ausente', 'nota'))}),
        ('Comissão', {'fields': ('professores', 'servidores')}),
    )

    def __init__(self, aluno, componente_curricular, *args, **kwargs):
        self.aluno = aluno
        self.componente_curricular = componente_curricular
        super().__init__(*args, **kwargs)
        if componente_curricular.qtd_avaliacoes == 0:
            del self.fields['nota']
            self.fieldsets = (
                ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), ('data',))}),
                ('Comissão', {'fields': ('professores', 'servidores')}),
            )
        elif self.aluno.matriz.estrutura.is_lancamento_conceito():
            choices = [['', '---']]
            for choice in settings.REPRESENTACAO_CONCEITUAL:
                choices.append([settings.REPRESENTACAO_CONCEITUAL[choice], choice])
            self.fields['nota'] = forms.ChoiceField(choices=choices, label='Conceito', required=True)
        self.fields['ano_letivo'].queryset = Ano.objects.filter(id__in=self.aluno.matriculaperiodo_set.values_list('ano_letivo_id', flat=True))
        if self.instance.pk:
            self.fields['ano_letivo'].initial = self.instance.matricula_periodo.ano_letivo.pk
            self.fields['periodo_letivo'].initial = self.instance.matricula_periodo.periodo_letivo

    def get_matricula_periodo_queryset(self):
        return self.aluno.matriculaperiodo_set.filter(ano_letivo=self.cleaned_data['ano_letivo'], periodo_letivo=self.cleaned_data['periodo_letivo'])

    def clean(self):
        if 'ano_letivo' not in self.cleaned_data:
            raise forms.ValidationError('O campo "Ano Letivo" é de preenchimento obrigatório.')

        if 'data' not in self.cleaned_data:
            raise forms.ValidationError('O campo "Data" é de preenchimento obrigatório.')

        nota = self.cleaned_data.get('nota')
        ausente = self.cleaned_data.get('ausente')
        if ausente and nota:
            raise forms.ValidationError('O campo "Nota" não pode ser preenchido se o campo "Ausente" estiver marcado.')
        if not ausente and nota is None:
            raise forms.ValidationError('O campo "Nota" é de preenchimento obrigatório se o campo "Ausente" não estiver marcado.')

        qs = self.get_matricula_periodo_queryset()
        if not qs.exists():
            raise forms.ValidationError('O aluno não está matriculado no ano/período informado.')

        matricula_periodo = qs[0]

        if PedidoMatriculaDiario.objects.filter(
            pedido_matricula__matricula_periodo__aluno=self.aluno,
            data_processamento__isnull=True,
            diario__componente_curricular=self.componente_curricular,
        ).exists():
            raise forms.ValidationError(
                'O aluno solicitou matrícula nessa disciplina. Aguarde o processamento do pedido de matrícula para realizar esse procedimeto.'
            )

        if (
            self.aluno.matriz.estrutura.numero_max_certificacoes > 0
            and matricula_periodo.get_numero_certificacoes() >= self.aluno.matriz.estrutura.numero_max_certificacoes
        ):
            raise forms.ValidationError(
                f'O aluno já atingiu o número de certificações no período que são de {self.aluno.matriz.estrutura.numero_max_certificacoes} certificações.'
            )

        if self.aluno.matriz.estrutura.percentual_max_aproveitamento:
            ch_componentes_aproveitaveis = self.aluno.matriz.get_ch_certificavel_aproveitavel()
            pode_aproveitar = (
                self.aluno.get_ch_certificada_ou_aproveitada() + self.componente_curricular.get_carga_horaria_total()
                <= self.aluno.matriz.estrutura.percentual_max_aproveitamento * ch_componentes_aproveitaveis / 100
            )
            if not pode_aproveitar:
                raise forms.ValidationError(
                    f'Ao certificar essa disciplina, o aluno extrapola o percentual máximo de carga horária aproveitada/certificada que é de {self.aluno.matriz.estrutura.percentual_max_aproveitamento}%.'
                )
        pode_cursar, msg = self.aluno.pode_cursar_componente_curricular(self.componente_curricular)
        if not pode_cursar:
            raise forms.ValidationError(
                f'Essa disciplina não pode ser certificada, pois não atende a todos os critérios de co/pré-requisitos: {msg}.'
            )

        if self.aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento:
            pode_aproveitar = (
                self.aluno.get_creditos_certificados_ou_aproveitados() + self.componente_curricular.componente.ch_qtd_creditos
                <= self.aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento
            )
            if not pode_aproveitar:
                raise forms.ValidationError(
                    f'Ao certificar essa disciplina, o aluno extrapola a quantidade máxima de créditos aproveitados/certificados que é de {self.aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento}.'
                )

        if self.aluno.curso_campus.modalidade.descricao == 'Integrado':
            if self.componente_curricular.nucleo.descricao in ['Fundamental', 'Estruturante', 'Tecnológico']:
                raise forms.ValidationError(
                    'Para os cursos técnicos na forma integrada, é vedada a certificação de conhecimentos de disciplinas referentes aos núcleos fundamental e estruturante.'
                )

        if self.componente_curricular.tipo in [
            ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
            ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
            ComponenteCurricular.TIPO_SEMINARIO,
        ]:
            if not in_group(self.request.user, 'edu Administrador'):
                raise forms.ValidationError(
                    'Não é possível fazer certificação do conhecimento para componentes curriculares de prática profissional ou de trabalho de conclusão de curso ou de seminário.'
                )

        matriculas_periodo = MatriculaPeriodo.objects.filter(
            aluno=self.aluno, ano_letivo=self.cleaned_data.get('ano_letivo'), periodo_letivo=self.cleaned_data.get('periodo_letivo')
        )
        qs1 = MatriculaDiario.objects.filter(
            situacao__in=[MatriculaDiario.SITUACAO_TRANCADO],
            diario__componente_curricular=self.componente_curricular,
            matricula_periodo__in=matriculas_periodo,
        )
        qs2 = MatriculaDiarioResumida.objects.filter(
            situacao__in=[MatriculaDiario.SITUACAO_TRANCADO],
            equivalencia_componente__componente=self.componente_curricular.componente,
            matricula_periodo__in=matriculas_periodo,
        )
        if qs1.exists() or qs2.exists():
            raise forms.ValidationError(
                'Não é possível realizar certificação de conhecimento no período letivo informado, pois o aluno trancou a disciplina nesse período. Informe um período letivo diferente.'
            )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        self.instance.matricula_periodo = self.get_matricula_periodo_queryset()[0]
        self.instance.componente_curricular = self.componente_curricular
        certificacao = super().save(*args, **kwargs)
        self.aluno.atualizar_situacao('Registro de Certificação de Conhecimento')
        return certificacao


class AproveitamentoEstudoForm(forms.ModelFormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', help_text='Ano letivo do aproveitamento.')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES, help_text='Período letivo do aproveitamento.')

    quebrar_requisitos = forms.BooleanField(
        label='Forçar quebra de requisitos',
        required=False,
        help_text='Marque esta opção para forçar a quebra de pré-requisitos e co-requisitos do componente curricular.',
    )

    class Meta:
        model = AproveitamentoEstudo
        fields = ('ano_letivo', 'periodo_letivo', 'data', 'escola_origem', 'frequencia', 'nota', 'professores', 'servidores')

    fieldsets = (
        ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), ('data', 'escola_origem'), ('frequencia', 'nota'), 'quebrar_requisitos')}),
        ('Comissão', {'fields': ('professores', 'servidores')}),
    )

    def __init__(self, aluno, componente_curricular, *args, **kwargs):
        self.aluno = aluno
        self.componente_curricular = componente_curricular

        super().__init__(*args, **kwargs)
        if componente_curricular.qtd_avaliacoes == 0:
            del self.fields['nota']
            self.fieldsets = (
                ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), ('data', 'escola_origem'), ('frequencia',))}),
                ('Comissão', {'fields': ('professores', 'servidores')}),
            )
        elif self.aluno.matriz.estrutura.is_lancamento_conceito():
            choices = [['', '---']]
            for choice in settings.REPRESENTACAO_CONCEITUAL:
                choices.append([settings.REPRESENTACAO_CONCEITUAL[choice], choice])
            self.fields['nota'] = forms.ChoiceField(choices=choices, label='Conceito', required=True)

        self.fields['ano_letivo'].queryset = Ano.objects.filter(id__in=self.aluno.matriculaperiodo_set.values_list('ano_letivo_id', flat=True))
        if self.instance and self.instance.pk:
            self.fields['ano_letivo'].initial = self.instance.matricula_periodo.ano_letivo.pk
            self.fields['periodo_letivo'].initial = self.instance.matricula_periodo.periodo_letivo

    def get_matricula_periodo_queryset(self):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        if ano_letivo and periodo_letivo:
            return self.aluno.matriculaperiodo_set.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)

    def clean(self):
        is_administrador = in_group(self.request.user, 'edu Administrador')
        quebrar_requisitos = self.cleaned_data.get('quebrar_requisitos')
        if 'ano_letivo' not in self.cleaned_data or 'periodo_letivo' not in self.cleaned_data:
            return self.cleaned_data
        mp = self.get_matricula_periodo_queryset().first()
        if mp is None:
            raise forms.ValidationError('O aluno não está matriculado no ano/período informado.')

        AproveitamentoEstudo.validar(
            mp,
            self.componente_curricular,
            ignorar_prerequisito=quebrar_requisitos,
            ignorar_corequisito=quebrar_requisitos,
            is_administrador=is_administrador,
        )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        self.instance.matricula_periodo = self.get_matricula_periodo_queryset()[0]
        self.instance.componente_curricular = self.componente_curricular
        aproveitamento = super().save(*args, **kwargs)
        self.aluno.atualizar_situacao('Registro de Aproveitamento de Estudo')
        return aproveitamento


def GetRegistroHistoricoFormClass(mobilidade_academica=True):
    class RegistroHistoricoForm(forms.ModelFormPlus):
        nome_professor = forms.CharField(label='Nome', required=False)
        titularidade_professor = forms.ChoiceField(label='Titulação', choices=Professor.TITULACAO_CHOICES)
        nome_professor2 = forms.CharField(label='Nome', required=False)
        titularidade_professor2 = forms.ChoiceField(label='Titulação', choices=[['', ''], *Professor.TITULACAO_CHOICES], required=False)
        conceito = forms.ChoiceField(label='Conceito', choices=[])
        outros_professores = forms.CharField(
            label='Outros professores',
            required=False,
            widget=forms.Textarea,
            help_text='Se houver mais de dois professores, informe os adicionais utilizando o seguinte formato: "Nome|Titulação;" — por exemplo: João Maria|Mestre; Maria Silva|Doutora;',
        )

        if mobilidade_academica:
            ALERT = 'Este cadastro deve ser utilizado apenas para registro de Mobilidade Acadêmica Nacional/Internacional.'

        def __init__(self, *args, **kwargs):
            aluno = kwargs.pop('aluno', None)
            super().__init__(*args, **kwargs)
            self.fields['matricula_periodo'].queryset = MatriculaPeriodo.objects.filter(aluno=aluno)
            self.fields['componente'].queryset = Componente.objects.filter(nivel_ensino_id=aluno.curso_campus.modalidade.nivel_ensino_id)
            if mobilidade_academica:
                id_componentes_matriz = ComponenteCurricular.objects.filter(matriz_id=aluno.matriz_id).values_list('componente_id', flat=True)
                self.fields['componente'].queryset = Componente.objects.filter(nivel_ensino_id=aluno.curso_campus.modalidade.nivel_ensino_id).exclude(
                    id__in=id_componentes_matriz
                )
            if aluno.matriz.estrutura.is_lancamento_conceito():
                del self.fields['media_final_disciplina']
                choices = [['', '---']]
                for choice in settings.REPRESENTACAO_CONCEITUAL:
                    choices.append([choice, choice])
                self.fields['conceito'].choices = choices
            else:
                del self.fields['conceito']

            self.fieldsets = (
                (
                    'Dados gerais',
                    {
                        'fields': (
                            'matricula_periodo',
                            'componente',
                            ('conceito' if aluno.matriz.estrutura.is_lancamento_conceito() else 'media_final_disciplina', 'frequencia', 'situacao'),
                        )
                    },
                ),
                ('Dados do professor principal', {'fields': (('nome_professor', 'titularidade_professor'),)}),
                ('Dados do professor auxiliar', {'fields': (('nome_professor2', 'titularidade_professor2'),)}),
                ('Dados de outros professores', {'fields': (('outros_professores'),)}),
            )

        class Meta:
            model = RegistroHistorico
            fields = (
                'matricula_periodo',
                'componente',
                'media_final_disciplina',
                'conceito',
                'frequencia',
                'situacao',
                'nome_professor',
                'titularidade_professor',
                'nome_professor2',
                'titularidade_professor2',
                'outros_professores',
            )

        def save(self, *args, **kwargs):
            self.instance.mobilidade_academica = mobilidade_academica
            return super().save(*args, **kwargs)

    return RegistroHistoricoForm
