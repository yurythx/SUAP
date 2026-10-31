import unicodedata

from django.core.exceptions import ValidationError
from django.db import transaction

from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from djtools.templatetags.filters import format_
from edu.models import (
    Escola,
    EstagioDocente,
    Professor,
    VisitaEstagioDocente,
)


class EstagioDocenteForm(forms.ModelFormPlus):
    professor_coordenador = forms.ModelChoiceField(queryset=Professor.objects.none(), label='Professor Coordenador')
    professor_orientador = forms.ModelChoiceField(
        queryset=Professor.objects, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS), label='Professor Orientador'
    )

    class Meta:
        model = EstagioDocente
        exclude = ('matricula_diario',)

    fieldsets = (
        ('Dados gerais', {'fields': ('turno', 'convenio', 'local', 'nivel', 'professor_coordenador', 'professor_orientador')}),
        ('Período', {'fields': (('data_inicio', 'data_fim'), 'data_final_envio_portfolio')}),
        ('Documentação', {'fields': (('plano_estagio', 'termo_compromisso'), 'documentacao_comprobatoria')}),
        ('Seguro', {'fields': ('nome_seguradora', 'numero_seguro')}),
        (
            'Supervisor de estágio',
            {
                'fields': (
                    ('cpf_professor_colaborador', 'nome_professor_colaborador'),
                    ('cargo_professor_colaborador', 'formacao_professor_colaborador'),
                    ('telefone_professor_colaborador', 'email_professor_colaborador'),
                )
            },
        ),
        ('Observações', {'fields': ('observacoes',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['professor_coordenador'].queryset = Professor.servidores_docentes
        if self.instance.matricula_diario_id:
            self.fields[
                'professor_coordenador'
            ].queryset = self.instance.matricula_diario.matricula_periodo.aluno.curso_campus.coordenadores_estagio_docente

    def clean(self, *args, **kwargs):
        cleaned_data = self.cleaned_data
        plano_estagio = cleaned_data.get('plano_estagio')
        termo_compromisso = cleaned_data.get('termo_compromisso')
        documentacao_comprobatoria = cleaned_data.get('documentacao_comprobatoria')
        if not (plano_estagio and termo_compromisso) and not documentacao_comprobatoria:
            raise ValidationError(
                'Obrigatório preencher Plano de Atividades e Termo de Compromisso conjuntamente ou Documentação Comprobatória de Prática Efetiva em substituição a estes documentos.'
            )
        return cleaned_data

    def save(self, *args, **kwargs):
        self.instance.professor_coordenador = self.cleaned_data.get('professor_coordenador')
        self.instance.professor_orientador = self.cleaned_data.get('professor_orientador')
        return super().save(*args, **kwargs)


class AssociarEscolasForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        c1 = 'escola'
        c2 = 'matricula_diario__matricula_periodo__aluno__curso_campus__diretoria__setor__uo__sigla'
        self.pendencias = (
            EstagioDocente.objects.filter(escola__isnull=False, local__isnull=True)
            .order_by(c1, c2)
            .exclude(escola__contains='------')
            .values_list(c1, c2)
            .distinct()
        )
        for i, (nome, campus) in enumerate(self.pendencias[0:50]):
            nome_sem_acento = ''.join(char for char in unicodedata.normalize('NFD', nome) if not unicodedata.combining(char)).upper()
            qs = Escola.objects.none()
            ignorar = (
                'ESCOLA ESTADUAL UNIDADE MUNICIPAL SILVA MARIA CEEF PROFESSOR PROFESSORA CENTRO EDUCACAO INTEGRADO EDUCACIONAL JOSE INTEGRADA'.split()
            )
            for token in nome_sem_acento.split():
                if len(token) > 4 and token not in ignorar:
                    qs = qs | Escola.objects.filter(nome__contains=token)
            self.fields[f'field{i}'] = forms.ModelChoiceFieldPlus(qs, label=f'{nome} | {campus}', required=False)

    def processar(self):
        for k, local in self.cleaned_data.items():
            if local:
                EstagioDocente.objects.filter(escola=self.fields[k].label.split(' | ')[0]).update(local=local)


class VisitaEstagioDocenteForm(forms.ModelFormPlus):
    class Meta:
        model = VisitaEstagioDocente
        exclude = ('estagio_docente',)

    fieldsets = (
        ('Dados gerais', {'fields': ('data_visita', 'relatorio')}),
        ('Atividades', {'fields': ('desenvolvendo_atividades_previstas', 'informacoes_complementares')}),
    )

    def __init__(self, estagio_docente, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.estagio_docente = estagio_docente


class EnviarPortfolioEstagioDocenteForm(forms.ModelFormPlus):
    class Meta:
        model = EstagioDocente
        fields = ('portfolio',)


class CadastrarEstagioDocenteConcomitanteForm(forms.ModelFormPlus):
    professor_coordenador = forms.ModelChoiceField(queryset=Professor.objects.none(), label='Professor Coordenador')
    professor_orientador = forms.ModelChoiceField(
        queryset=Professor.objects, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS), label='Professor Orientador'
    )

    class Meta:
        model = EstagioDocente
        exclude = ('matricula_diario', 'justificativa', 'escola')

    fieldsets = (
        ('Dados gerais', {'fields': ('turno', 'convenio', 'local', 'nivel', 'professor_coordenador', 'professor_orientador')}),
        ('Período', {'fields': (('data_inicio', 'data_fim'), 'data_final_envio_portfolio')}),
        ('Documentação', {'fields': (('plano_estagio', 'termo_compromisso'), 'documentacao_comprobatoria')}),
        ('Seguro', {'fields': ('nome_seguradora', 'numero_seguro')}),
        (
            'Supervisor de estágio',
            {
                'fields': (
                    'nome_professor_colaborador',
                    'cpf_professor_colaborador',
                    'telefone_professor_colaborador',
                    'cargo_professor_colaborador',
                    'formacao_professor_colaborador',
                    'email_professor_colaborador',
                )
            },
        ),
        ('Observações', {'fields': ('observacoes',)}),
    )

    def __init__(self, estagio_docente, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'professor_coordenador'
        ].queryset = estagio_docente.matricula_diario.matricula_periodo.aluno.curso_campus.coordenadores_estagio_docente
        self.estagio_docente = estagio_docente

    def clean(self, *args, **kwargs):
        cleaned_data = self.cleaned_data
        plano_estagio = cleaned_data.get('plano_estagio')
        termo_compromisso = cleaned_data.get('termo_compromisso')
        documentacao_comprobatoria = cleaned_data.get('documentacao_comprobatoria')
        if not (plano_estagio and termo_compromisso) and not documentacao_comprobatoria:
            raise ValidationError(
                {
                    'plano_estagio': 'Obrigatório preencher Plano de Estágio e Termo de Compromisso conjuntamente ou Documentação Comprobatória de Prática Anterior em substituição a estes documentos.'
                }
            )
        return cleaned_data

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.instance.matricula_diario = self.estagio_docente.matricula_diario
        self.instance.professor_coordenador = self.cleaned_data.get('professor_coordenador')
        self.instance.professor_orientador = self.cleaned_data.get('professor_orientador')
        return super().save(*args, **kwargs)


class EncerrarEstagioDocenteForm(forms.ModelFormPlus):
    class Meta:
        model = EstagioDocente
        fields = ('avaliacao_do_orientador', 'avaliacao_do_professor_colaborador', 'portfolio', 'ch_final')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliacao_do_orientador'].required = True
        self.fields['avaliacao_do_professor_colaborador'].required = True
        self.fields['ch_final'].required = True
        self.fields['portfolio'].required = True
        if self.instance.matricula_diario.estagiodocente_set.exclude(pk=self.instance.pk).exists():
            carga_horaria_total_componente = (
                self.instance.matricula_diario.diario.componente_curricular.componente_curricular_associado
                and self.instance.matricula_diario.diario.componente_curricular.componente_curricular_associado.get_carga_horaria_total()
                or self.instance.matricula_diario.diario.componente_curricular.get_carga_horaria_total()
            )
            mensagem = (
                f'Atenção para a situação dos outros estágios (a soma das cargas horárias deve ser igual a {carga_horaria_total_componente}h):\n'
            )
            mensagem = mensagem + '<table><thead><tr><th>Escola</th><th>Carga Horária Já Registrada</th><th>Situação</th></thead><tbody>'
            for estagio_docente in self.instance.matricula_diario.estagiodocente_set.exclude(pk=self.instance.pk):
                mensagem = (
                    mensagem
                    + f'<tr> <td>{estagio_docente.get_escola()}</td> <td>{format_(estagio_docente.ch_final)}</td> <td>{estagio_docente.get_situacao_display()}</td> </tr>'
                )
            mensagem = mensagem + '</tbody></table>'
            self.fields['ch_final'].help_text = mensagem

    fieldsets = (
        ('Documentação', {'fields': ('avaliacao_do_orientador', 'avaliacao_do_professor_colaborador', 'portfolio')}),
        ('Documentação', {'fields': ('ch_final',)}),
    )

    def clean(self):
        if not self.instance.visitaestagiodocente_set.exists():
            raise forms.ValidationError(
                'Para encerrar estágio docente é necessário que o professor orientador tenha feito o cadastro de pelo menos uma visita.'
            )


class EncerrarEstagioDocenteNaoConcluidoForm(forms.ModelFormPlus):
    estagio_nao_concluido = forms.BooleanField(label='Estágio não concluído', help_text='O estágio não foi concluído pelo aluno.', required=False)

    class Meta:
        model = EstagioDocente
        fields = ('estagio_nao_concluido',)

    fieldsets = (('Encerrar sem conclusão', {'fields': ('estagio_nao_concluido',)}),)

    def clean(self):
        if not self.cleaned_data.get('estagio_nao_concluido'):
            raise ValidationError('Para encerrar o estágio por não conclusão marque a opção estágio não concluído.')

    def save(self, *args, **kwargs):
        if self.cleaned_data.get('estagio_nao_concluido'):
            self.instance.encerrar_sem_conclusao()


class RegistrarMundancaEscolaEstagioDocenteForm(forms.ModelFormPlus):
    class Meta:
        model = EstagioDocente
        fields = ('data_inicio', 'data_fim', 'justificativa', 'ch_final')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa'].required = True
        self.fields['ch_final'].required = True

    fieldsets = (
        ('Registrar Período Cursado na Escola Anterior', {'fields': (('data_inicio', 'data_fim'),)}),
        ('Justificativa', {'fields': ('justificativa',)}),
        ('Registrar Carga Horária Cursada na Escola Anterior', {'fields': ('ch_final',)}),
    )

    def save(self, *args, **kwargs):
        self.instance.situacao = EstagioDocente.SITUACAO_MUDANCA
        self.instance.save()
        return super().save(*args, **kwargs)


class EnviarAvaliacaoEstagioDocenteForm(forms.ModelFormPlus):
    class Meta:
        model = EstagioDocente
        fields = ('avaliacao_do_orientador',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    fieldsets = (('Documentação', {'fields': ('avaliacao_do_orientador',)}),)

    def clean(self):
        if self.instance.situacao == EstagioDocente.SITUACAO_ENCERRADO:
            raise forms.ValidationError('Estágio já encerrado.')
