import datetime
from itertools import groupby
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.widgets import Select

from comum.models import Ano, Configuracao, User
from djtools import forms
from djtools.forms.widgets import (
    AjaxSelectMultiplePopup,
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import in_group
from djtools.utils import httprr, somar_dias
from edu import tasks
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    AbonoFaltas,
    Aluno,
    AproveitamentoComponente,
    AproveitamentoEstudo,
    ComponenteCurricular,
    CursoCampus,
    Diario,
    Diretoria,
    EstruturaCurso,
    FormaIngresso,
    ItemConfiguracaoAvaliacao,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
    Matriz,
    MatrizCurso,
    MedidaDisciplinar,
    Mensagem,
    Modalidade,
    MotivoAusenciaEscolar,
    ParecerAvaliacaoAproveitamentoEstudo,
    PedidoMatriculaDiario,
    Premiacao,
    ProcedimentoMatricula,
    Professor,
    RegistroEmissaoDiploma,
    RegistroHistorico,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    RequerimentoCancelamentoDisciplina,
    RequerimentoMatriculaComAumentoDeCH,
    RequerimentoMatriculaDisciplina,
    RequerimentoMatriculaQuebraRequisito,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    SolicitacaoAproveitamentoEstudo,
    SolicitacaoAproveitamentoEstudoExterno,
    SolicitacaoAproveitamentoEstudoInterno,
    SolicitacaoReposicaoAtividade,
    Turma,
    Turno,
)
from rh.models import UnidadeOrganizacional


class ProcessarPeriodoLetivoForm(FormWizardPlus):
    FECHAMENTO_POR_MATRICULA = 'MATRICULA'
    FECHAMENTO_POR_TURMA = 'TURMA'
    FECHAMENTO_POR_CURSO = 'CURSO'
    FECHAMENTO_POR_DIARIO = 'DIARIO'
    TIPO_FECHAMENTO_CHOICES = [
        [FECHAMENTO_POR_MATRICULA, 'Por Matrícula'],
        [FECHAMENTO_POR_TURMA, 'Por Turma'],
        [FECHAMENTO_POR_CURSO, 'Por Curso'],
        [FECHAMENTO_POR_DIARIO, 'Por Diário'],
    ]

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    tipo = forms.ChoiceField(choices=TIPO_FECHAMENTO_CHOICES, widget=forms.RadioSelect())
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects.none(), label='Matrícula', required=False)
    turma = forms.ModelChoiceFieldPlus(Turma.objects.none(), label='Turma', required=False)
    curso = forms.ModelChoiceFieldPlus(CursoCampus.objects.none(), label='Curso', required=False)
    diario = forms.ModelChoiceFieldPlus(Diario.objects.none(), label='Diário', required=False)
    modulo = forms.ChoiceField(choices=ComponenteCurricular.TIPO_MODULO_CHOICES, widget=forms.HiddenInput(), required=False)
    forcar_fechamento = forms.BooleanField(
        label='Forçar fechamento?',
        help_text='Marque essa opção caso deseje que o diário seja fechado ainda que ele se encontre na posse do professor. Nesse caso, as notas pedentes serão computadas como zero e a posse do diário será transferida para o registro escolar.',
        required=False,
    )
    confirmado = forms.BooleanField(
        help_text='Marque a opção acima e em seguida clique no botão "Finalizar" para realizar o processamento do período para os diários listados.'
    )

    class Media:
        js = ('/static/edu/js/FecharPeriodoLetivoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.matriculas_periodo = []
        self.processado = False
        self.exibir_forcar_fechamento = False

    def first_step(self):
        if 'aluno' in self.fields:
            self.fields['aluno'].queryset = Aluno.locals.filter(matriz__isnull=False)
        if 'turma' in self.fields:
            self.fields['turma'].queryset = Turma.locals.filter(curso_campus__ativo=True)
        if 'curso' in self.fields:
            self.fields['curso'].queryset = CursoCampus.locals.filter(ativo=True)
        if 'diario' in self.fields:
            self.fields['diario'].queryset = Diario.locals.all()

    steps = (
        [('Fechar Período', {'fields': ('ano_letivo', 'periodo_letivo', 'tipo', 'aluno', 'turma', 'curso', 'diario', 'modulo')})],
        [('Confirmação dos Dados', {'fields': ('forcar_fechamento', 'confirmado')})],
    )

    def next_step(self):
        if self.get_entered_data('ano_letivo'):
            tipo = self.get_entered_data('tipo')
            matriculas_periodo = self.get_matriculas_periodo()
            if tipo == ProcessarPeriodoLetivoForm.FECHAMENTO_POR_MATRICULA and self.get_entered_data('aluno'):
                matriculas_periodo = matriculas_periodo.filter(aluno_id=self.get_entered_data('aluno').id)
                self.exibir_forcar_fechamento = self.get_entered_data('aluno').matriz.estrutura.permite_fechamento_com_pendencia
            elif tipo == ProcessarPeriodoLetivoForm.FECHAMENTO_POR_TURMA and self.get_entered_data('turma'):
                matriculas_periodo = matriculas_periodo.filter(matriculadiario__diario__turma_id=self.get_entered_data('turma').id)
                self.exibir_forcar_fechamento = self.get_entered_data('turma').matriz.estrutura.permite_fechamento_com_pendencia
            elif tipo == ProcessarPeriodoLetivoForm.FECHAMENTO_POR_CURSO and self.get_entered_data('curso'):
                matriculas_periodo = matriculas_periodo.filter(aluno__curso_campus_id=self.get_entered_data('curso').id)
                self.exibir_forcar_fechamento = False
            elif tipo == ProcessarPeriodoLetivoForm.FECHAMENTO_POR_DIARIO and self.get_entered_data('diario'):
                matriculas_periodo = matriculas_periodo.filter(matriculadiario__diario_id=self.get_entered_data('diario').id)
                self.exibir_forcar_fechamento = self.get_entered_data('diario').estrutura_curso.permite_fechamento_com_pendencia
            else:
                matriculas_periodo = MatriculaPeriodo.objects.none()
                self.exibir_forcar_fechamento = False
            self.matriculas_periodo = matriculas_periodo.distinct().order_by('id')

    def get_matriculas_periodo(self):
        qs = MatriculaPeriodo.objects.filter(
            ano_letivo_id=self.get_entered_data('ano_letivo').id, periodo_letivo=self.get_entered_data('periodo_letivo'), aluno__matriz__isnull=False
        ).order_by('id')
        qs = qs.exclude(aluno__matriz__estrutura__proitec=True).exclude(matriculadiarioresumida__isnull=False)
        return qs

    def get_diarios(self):
        diarios_ids = (
            MatriculaDiario.objects.filter(matricula_periodo__in=self.matriculas_periodo)
            .exclude(situacao__in=[6, 7, 8])
            .values_list('diario', flat=True)
        )
        return Diario.locals.filter(id__in=diarios_ids).distinct()


class FecharPeriodoLetivoForm(ProcessarPeriodoLetivoForm):
    METHOD = 'GET'

    @transaction.atomic
    def processar(self, request):
        if not self.matriculas_periodo.distinct() and not self.get_diarios():
            return httprr('/edu/fechar_periodo_letivo/', 'É necessário selecionar pelo menos uma matrícula período.', 'error')
        return tasks.fechar_periodo(
            self.cleaned_data['forcar_fechamento'],
            self.matriculas_periodo.distinct(),
            self.get_diarios(),
            request.META.get('QUERY_STRING', ''),
            self.cleaned_data['modulo'],
        )

    def get_matriculas_periodo(self):
        qs = super().get_matriculas_periodo().filter(situacao=SituacaoMatriculaPeriodo.MATRICULADO)
        if self.get_entered_data('modulo'):
            ids_mp = (
                MatriculaDiario.objects.filter(
                    situacao=MatriculaDiario.SITUACAO_CURSANDO,
                    matricula_periodo_id__in=qs.values_list('id', flat=True),
                    diario__componente_curricular__tipo_modulo=self.get_entered_data('modulo'),
                )
                .values_list('matricula_periodo_id', flat=True)
                .distinct()
            )
            qs = qs.filter(id__in=ids_mp)
        return qs


class AbrirPeriodoLetivoForm(ProcessarPeriodoLetivoForm):
    METHOD = 'GET'
    steps = (
        [('Abrir Período', {'fields': ('ano_letivo', 'periodo_letivo', 'tipo', 'aluno', 'turma', 'curso', 'diario', 'modulo')})],
        [('Confirmação dos Dados', {'fields': ('confirmado',)})],
    )

    def get_matriculas_periodo(self):
        modulo = self.get_entered_data('modulo')
        situacoes_periodo = []
        situacoes_periodo.append(SituacaoMatriculaPeriodo.EM_ABERTO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.CANCELADA)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.TRANCADA)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.EVASAO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.JUBILADO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.INTERCAMBIO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.TRANSF_EXTERNA)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.TRANSF_CURSO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.TRANSF_TURNO)
        situacoes_periodo.append(SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL)
        if not modulo:
            situacoes_periodo.append(SituacaoMatriculaPeriodo.MATRICULADO)

        situacoes_curso = []
        situacoes_curso.append(SituacaoMatricula.MATRICULADO)
        situacoes_curso.append(SituacaoMatricula.CONCLUIDO)
        situacoes_curso.append(SituacaoMatricula.NAO_CONCLUIDO)
        situacoes_curso.append(SituacaoMatricula.FORMADO)
        qs = (
            super()
            .get_matriculas_periodo()
            .filter(aluno__situacao__in=situacoes_curso)
            .exclude(situacao__in=situacoes_periodo)
            .exclude(periodo_integralizado_ensino_medio=True)
            .exclude(
                aluno__registroemissaodiploma__tipo__in=[
                    RegistroEmissaoDiploma.TIPO_CONCLUSAO_CURSO,
                    RegistroEmissaoDiploma.TIPO_CERTIFICACAO_PARCIAL,
                ],
                aluno__registroemissaodiploma__cancelado=False,
            )
        )
        qs_pedido = PedidoMatriculaDiario.objects.filter(data_processamento__isnull=True)
        if self.get_entered_data('aluno'):
            qs_pedido = qs_pedido.filter(pedido_matricula__matricula_periodo__aluno_id=self.get_entered_data('aluno').id)
        elif self.get_entered_data('turma'):
            qs_pedido = qs_pedido.filter(pedido_matricula__matricula_periodo__matriculadiario__diario__turma_id=self.get_entered_data('turma').id)
        elif self.get_entered_data('curso'):
            qs_pedido = qs_pedido.filter(pedido_matricula__matricula_periodo__aluno__curso_campus_id=self.get_entered_data('curso').id)
        elif self.get_entered_data('diario'):
            qs_pedido = qs_pedido.filter(pedido_matricula__matricula_periodo__matriculadiario__diario_id=self.get_entered_data('diario').id)
        qs_pedido = qs_pedido.values_list('pedido_matricula__matricula_periodo', flat=True).order_by('pedido_matricula__matricula_periodo').distinct()
        if qs_pedido.exists():
            return qs.exclude(pk__in=qs_pedido)

        if modulo:
            ids_mp = (
                MatriculaDiario.objects.filter(
                    matricula_periodo_id__in=qs.values_list('id', flat=True), diario__componente_curricular__tipo_modulo=modulo
                )
                .exclude(situacao=MatriculaDiario.SITUACAO_CURSANDO)
                .values_list('matricula_periodo_id', flat=True)
                .distinct()
            )
            qs = qs.filter(id__in=ids_mp)

        return qs

    @transaction.atomic
    def processar(self, request):
        matriculas_periodo = self.matriculas_periodo.distinct()
        diarios = self.get_diarios()
        querystring = request.META.get('QUERY_STRING', '')

        if not matriculas_periodo and not diarios:
            return httprr('/edu/abrir_periodo_letivo/', 'É necessário selecionar pelo menos uma matrícula período.', 'error')
        # self.processado = True
        return tasks.abrir_periodo(diarios, matriculas_periodo, querystring, self.cleaned_data['modulo'])


class AbonoFaltasForm(forms.ModelFormPlus):
    aluno = forms.ModelChoiceFieldPlus(
        Aluno.objects,
        help_text='Somente alunos com situação no período "Matriculado" serão listados.',
        label='Aluno',
        required=True,
        widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS),
    )

    diarios = forms.MultipleModelChoiceFieldPlus(
        Diario.objects,
        label='Diário',
        help_text='Para abonar todos os diários deixe este campo vazio',
        required=False,
        widget=AjaxSelectMultiplePopup(
            required_form_filters=True,
            form_filters=[
                ('data_inicio', 'calendario_academico__data_inicio__lte'),
                ('data_fim', 'calendario_academico__data_fim__gte'),
                ('aluno', 'matriculadiario__matricula_periodo__aluno'),
            ],
        ),
    )

    responsavel_abono = forms.ModelChoiceFieldPlus(
        User.objects, label='Responsável', required=True, widget=AutocompleteWidget(search_fields=User.SEARCH_FIELDS, readonly='readonly')
    )

    class Meta:
        model = AbonoFaltas
        fields = ('data_inicio', 'quantidade_dias', 'data_fim', 'motivo_ausencia_escolar', 'justificativa', 'anexo', 'diarios', 'responsavel_abono')

    class Media:
        js = ('/static/edu/js/AbonoFaltasForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motivo_ausencia_escolar'].queryset = MotivoAusenciaEscolar.objects.filter(ativo=True)
        if self.instance.pk:
            del self.fields['diarios']
            del self.fields['responsavel_abono']
            self.fields['aluno'].widget = forms.HiddenInput()
        else:
            self.initial['responsavel_abono'] = self.request.user.id
            # O secretário só pode criar, alterar ou excluir os abonos de alunos de seus campus.
            # Apenas alunos cujo período letivo encontra-se aberto (matriculado) podem ter faltas abonadas ou rejeitadas.
            self.fields['aluno'].queryset = (
                Aluno.locals_uo.filter(matriculaperiodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO, matriz__isnull=False)
                .order_by('pk')
                .distinct()
            )

    def clean(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        quantidade_dias = self.cleaned_data.get('quantidade_dias')
        if quantidade_dias is None or quantidade_dias < 1:
            raise ValidationError('A quantidade de dias do atestado deve ser maior ou igual a 1.')
        if data_inicio:
            data_fim = somar_dias(data_inicio, quantidade_dias - 1)
            data_fim_form = self.cleaned_data.get('data_fim')
            if data_fim_form is None or data_fim_form != data_fim:
                self.cleaned_data['data_fim'] = data_fim
        else:
            raise ValidationError('É obrigatório informar uma Data de Início válida do atestado.')
        return self.cleaned_data

    def save(self, *args, **kwargs):
        # deferimento automatico se na criação do abono for informado o responsável.
        deferido = True if self.instance.pk is None and self.cleaned_data.get('responsavel_abono') else None
        obj = super().save(False)
        obj.deferido = deferido
        return obj


class CadastrarJustificativaFaltaForm(forms.ModelFormPlus):
    EXTRA_INFO = 'Caso sua ausência ultrapasse 15 dias, você pode ter direito (dependendo do motivo) a atendimento domiciliar. Contacte sua diretoria acadêmica se for o caso.'

    fieldsets = (
        (
            'Dados Gerais',
            {
                'fields': (
                    'aluno',
                    ('data_inicio', 'quantidade_dias'),
                )
            },
        ),
        (
            'Detalhamento',
            {
                'fields': (
                    'motivo_ausencia_escolar',
                    'justificativa',
                    'anexo',
                )
            },
        ),
    )

    class Meta:
        model = AbonoFaltas
        fields = 'data_inicio', 'quantidade_dias', 'motivo_ausencia_escolar', 'justificativa', 'anexo'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motivo_ausencia_escolar'].queryset = MotivoAusenciaEscolar.objects.filter(ativo=True)

    def clean(self):
        aluno = Aluno.objects.get(matricula=self.request.user.username)
        self.instance.aluno = aluno
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        quantidade_dias = cleaned_data.get('quantidade_dias')
        if quantidade_dias is None or quantidade_dias < 1:
            raise ValidationError('A quantidade de dias do atestado deve ser maior ou igual a 1.')
        if data_inicio:
            data_fim = somar_dias(data_inicio, quantidade_dias - 1)
            data_fim_form = cleaned_data.get('data_fim')
            if data_fim_form is None or data_fim_form != data_fim:
                cleaned_data['data_fim'] = data_fim
        else:
            raise ValidationError('É obrigatório informar uma Data de Início válida do atestado.')
        return cleaned_data


class AvaliarAbonoFaltasForm(forms.ModelFormPlus):
    diarios = forms.MultipleModelChoiceFieldPlus(
        Diario.objects,
        label='Diário',
        help_text='Para abonar todos os diários, deixe este campo vazio.',
        required=False,
    )

    class Meta:
        model = AbonoFaltas
        fields = ('deferido', 'observacao_avaliacao', 'diarios')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diarios'].queryset = Diario.objects.filter(
            calendario_academico__data_inicio__lte=self.instance.data_inicio,
            calendario_academico__data_fim__gte=self.instance.data_fim,
            matriculadiario__matricula_periodo__aluno_id=self.instance.aluno_id,
        )

        self.fields['deferido'].required = True
        self.fields['deferido'].widget.choices = (
            ('', '-----'),
            (True, 'Sim'),
            (False, 'Não'),
        )

    def processar(self, user):
        self.instance.responsavel_abono = user
        self.instance.data_avaliacao = datetime.date.today()
        diarios = self.cleaned_data['diarios']
        self.instance.save()
        if diarios:
            self.instance.diarios.set(diarios)
        self.instance.processar()
        return self.instance


class AbonoFaltasLoteForm(forms.ModelFormPlus):
    METHOD = 'POST'

    diario = forms.ModelChoiceFieldPlus(
        Diario.objects,
        help_text='Selecione um diário caso deseje abonar somente as faltas deste diário. Em seguida selecione os alunos no campo abaixo.',
        label='Diário',
        required=False,
        widget=AutocompleteWidget(search_fields=Diario.SEARCH_FIELDS),
    )

    alunos = forms.MultipleModelChoiceField(
        Aluno.objects,
        label='Alunos',
        help_text='Somente alunos com situação no período "Matriculado" serão listados.',
        required=True,
        widget=AutocompleteWidget(
            search_fields=Aluno.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('diario', 'matriculaperiodo__matriculadiario__diario'),
            ],
        ),
    )

    responsavel_abono = forms.ModelChoiceFieldPlus(
        User.objects, label='Responsável por Abono', required=True, widget=AutocompleteWidget(search_fields=User.SEARCH_FIELDS, readonly='readonly')
    )

    fieldsets = (
        (
            '',
            {
                'fields': (
                    'diario',
                    'alunos',
                    'motivo_ausencia_escolar',
                    'data_inicio',
                    'quantidade_dias',
                    'data_fim',
                    'justificativa',
                    'anexo',
                    'responsavel_abono',
                )
            },
        ),
    )

    class Meta:
        model = AbonoFaltas
        exclude = ('aluno',)

    class Media:
        js = ('/static/edu/js/AbonoFaltasForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motivo_ausencia_escolar'].queryset = MotivoAusenciaEscolar.objects.filter(ativo=True)
        self.fields['responsavel_abono'].initial = self.request.user
        # O secretário só pode criar, alterar ou excluir os abonos de alunos de seus campus.
        # Apenas alunos cujo período letivo encontra-se aberto (matriculado) podem ter faltas abonadas ou rejeitadas.
        self.fields['alunos'].queryset = (
            Aluno.locals.filter(matriculaperiodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO, matriz__isnull=False).order_by('pk').distinct()
        )

    def clean(self):
        alunos = self.cleaned_data.get('alunos')
        data_inicio = self.cleaned_data.get('data_inicio')
        quantidade_dias = self.cleaned_data.get('quantidade_dias')
        if quantidade_dias is None or quantidade_dias < 1:
            raise ValidationError('A quantidade de dias do atestado deve ser maior ou igual a 1.')
        if data_inicio:
            data_fim = somar_dias(data_inicio, quantidade_dias - 1)
            data_fim_form = self.cleaned_data.get('data_fim')
            if data_fim_form is None or data_fim_form != data_fim:
                self.cleaned_data['data_fim'] = data_fim
        else:
            raise ValidationError('É obrigatório informar uma Data de Início válida do atestado.')

        if alunos and data_inicio and data_fim:
            for aluno in alunos:
                abono = AbonoFaltas(aluno=aluno, data_inicio=data_inicio, data_fim=data_fim, deferido=True)
                abono.pk = self.instance.pk
                try:
                    abono.clean()
                except ValidationError as e:
                    raise ValidationError(f'Erro para o aluno {aluno}: {e.messages[0]}')

        return self.cleaned_data

    def processar(self, *args, **kwargs):
        alunos = self.cleaned_data.get('alunos')
        diario = self.cleaned_data.get('diario')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        justificativa = self.cleaned_data.get('justificativa')
        anexo = self.cleaned_data.get('anexo')
        responsavel_abono = self.cleaned_data.get('responsavel_abono')
        motivo_ausencia_escolar = self.cleaned_data.get('motivo_ausencia_escolar')
        for aluno in alunos:
            abono = AbonoFaltas()
            abono.aluno = aluno
            abono.data_inicio = data_inicio
            abono.data_fim = data_fim
            abono.justificativa = justificativa
            abono.deferido = True
            abono.anexo = anexo
            abono.responsavel_abono = responsavel_abono
            abono.motivo_ausencia_escolar = motivo_ausencia_escolar
            if diario:
                abono.diarios.add(diario)
            abono.save()
            abono.processar()


class ProcedimentoMatriculaForm(forms.ModelFormPlus):
    ano_letivo = forms.ModelChoiceField(
        Ano.objects.ultimos(), label='Ano Letivo', initial=1, required=False, widget=Select(attrs={'readonly': 'readonly'})
    )
    periodo_letivo = forms.ChoiceField(
        label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES, required=False, widget=Select(attrs={'readonly': 'readonly'})
    )
    opcoes = forms.ChoiceField(label='Tipo')

    def __init__(self, matricula_periodo_pk, *args, **kwargs):
        self.matricula_periodo = MatriculaPeriodo.objects.get(pk=matricula_periodo_pk)
        super().__init__(*args, **kwargs)
        self.fields['ano_letivo'].initial = self.matricula_periodo.ano_letivo.pk
        self.fields['periodo_letivo'].initial = self.matricula_periodo.periodo_letivo
        self.fields['opcoes'].choices = [['', '-------------'], *self.get_choices()]
        if self.instance.pk:
            self.fields['ano_letivo'].initial = self.instance.matricula_periodo.ano_letivo.pk
            self.fields['periodo_letivo'].initial = self.instance.matricula_periodo.periodo_letivo

    def get_choices(self):
        return []

    class Meta:
        model = ProcedimentoMatricula
        fields = ('processo', 'data', 'motivo')

    fieldsets = (
        ('Procedimento de Matrícula', {'fields': ('ano_letivo', 'periodo_letivo', 'processo', 'data', 'opcoes', 'motivo', 'matricula_periodo')}),
    )

    def save(self, *args, **kwargs):
        situacao_matricula_pk, situacao_matricula_periodo_pk, situacao_matricula_diario_pk = self.cleaned_data['opcoes'].split(';')
        situacao_matricula = SituacaoMatricula.objects.get(pk=situacao_matricula_pk)
        situacao_matricula_periodo = SituacaoMatriculaPeriodo.objects.get(pk=situacao_matricula_periodo_pk)
        situacao_matricula_anterior = self.matricula_periodo.aluno.situacao

        procedimento = super().save(commit=False)
        for choice in self.get_choices():
            if choice[0] == self.cleaned_data['opcoes']:
                procedimento.tipo = choice[1]
        procedimento.matricula_periodo = self.matricula_periodo
        procedimento.situacao_matricula_anterior = situacao_matricula_anterior

        self.matricula_periodo.realizar_procedimento_matricula(
            procedimento, situacao_matricula, situacao_matricula_periodo, situacao_matricula_diario_pk
        )

        if self.cleaned_data.get('excluir_pedido_matricula'):
            qs_pedido = PedidoMatriculaDiario.objects.filter(
                pedido_matricula__matricula_periodo_id=self.matricula_periodo.id, data_processamento__isnull=True
            )
            if qs_pedido.exists():
                qs_pedido.delete()

        return procedimento

    def clean(self):
        mps = MatriculaPeriodo.objects.filter(
            aluno=self.matricula_periodo.aluno, situacao__id__in=[SituacaoMatriculaPeriodo.EM_ABERTO, SituacaoMatriculaPeriodo.MATRICULADO]
        ).exclude(pk=self.matricula_periodo.pk)
        if mps.exists():
            raise forms.ValidationError('É necessário fechar os períodos anteriores antes de realizar o procedimento.')

        if 'opcoes' in self.cleaned_data:
            for choice in self.get_choices():
                if choice[0] == self.cleaned_data['opcoes']:
                    tipo = choice[1]
                    if self.matricula_periodo.aluno.possui_pendencia_nada_consta(tipo):
                        self.matricula_periodo.aluno.solicitar_quitacao_nada_consta(procedimento=tipo)
                        raise forms.ValidationError('Há solicitações de Nada Consta não atendidas que são exigidas para este procedimento.')

        if self.matricula_periodo.aluno.matriz_id and self.matricula_periodo.aluno.matriz.estrutura.requer_declaracao_para_cancelamento_matricula:
            if not self.matricula_periodo.aluno.alunoarquivo_set.filter(tipo=15).exists():
                raise forms.ValidationError(
                    'Para realizar o cancelamento da matrícula, é necessário realizar previamente o upload da "Declaração de Pedido de Cancelamento de Matrícula" na pasta documental do aluno.'
                )

        return self.cleaned_data


class CancelarMatriculaForm(ProcedimentoMatriculaForm):
    def get_choices(self):
        return [
            [
                f'{SituacaoMatricula.CANCELAMENTO_COMPULSORIO};{SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO,
            ],
            [
                f'{SituacaoMatricula.CANCELADO};{SituacaoMatriculaPeriodo.CANCELADA};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
            ],
            [
                f'{SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE};{SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            ],
            [
                f'{SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO};{SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            ],
            [f'{SituacaoMatricula.EVASAO};{SituacaoMatriculaPeriodo.EVASAO};{MatriculaDiario.SITUACAO_CANCELADO}', ProcedimentoMatricula.EVASAO],
            [
                f'{SituacaoMatricula.JUBILADO};{SituacaoMatriculaPeriodo.JUBILADO};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.JUBILAMENTO,
            ],
        ]


class IntegralizarFaseEscolarForm(ProcedimentoMatriculaForm):
    manter_aluno_matriculado = forms.BooleanField(
        label='Manter Aluno Matriculado',
        help_text='Marque essa opção caso o aluno manifestou interesse em continuar o curso.',
        initial=True,
        required=False,
    )
    obs_integralizacao_ensino_medio = forms.CharField(
        label='Observação da Integralização Ensino Médio',
        help_text='Observação que constará no histórico e no diploma.',
        widget=forms.Textarea(),
        initial='Curso técnico não finalizado. Certificado de conclusão do ensino médio emitido em obediência a decisão judicial RECURSO ESPECIAL Nº 1.783.577 - RN (2018/0312877-6).',
    )

    fieldsets = (
        *ProcedimentoMatriculaForm.fieldsets,
        ('Situação da Matrícula', {'fields': ('manter_aluno_matriculado', 'obs_integralizacao_ensino_medio')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['opcoes'].initial = self.get_choices()[0][0]
        self.fields['opcoes'].widget = forms.HiddenInput()
        self.fields['motivo'].widget = forms.HiddenInput()
        self.fields['motivo'].required = False
        # se for aluno do q-Acadêmico, pode informar uma período não existente no SUAP
        if self.matricula_periodo.aluno.matriz_id is None:
            self.fields['ano_letivo'].widget.attrs.pop('readonly')
            self.fields['periodo_letivo'].widget.attrs.pop('readonly')

    def get_choices(self):
        return [
            [
                f'{SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO};{SituacaoMatriculaPeriodo.INTEGRALIZADO_ENSINO_MEDIO};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.INTEGRALIZAR_ENSINO_MEDIO,
            ],
        ]

    def save(self, *args, **kwargs):
        alterar_situacao = not self.cleaned_data['manter_aluno_matriculado']
        obs_integralizacao_ensino_medio = self.cleaned_data['obs_integralizacao_ensino_medio']
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        aluno = self.matricula_periodo.aluno
        # criar a matrícula período caso ela ainda não exista
        with transaction.atomic():
            if self.matricula_periodo.ano_letivo != ano_letivo or self.matricula_periodo.periodo_letivo != int(periodo_letivo):
                self.matricula_periodo = MatriculaPeriodo.objects.update_or_create(
                    ano_letivo=ano_letivo,
                    periodo_letivo=periodo_letivo,
                    aluno=aluno,
                    defaults={
                        'situacao_id': SituacaoMatriculaPeriodo.EM_ABERTO,
                    },
                )
            aluno.integralizou_ensino_medio = True
            aluno.obs_integralizacao_ensino_medio = obs_integralizacao_ensino_medio
            aluno.save()

            MatriculaPeriodo.objects.filter(aluno_id=aluno.id, ano_letivo__ano__lt=ano_letivo.ano).update(periodo_integralizado_ensino_medio=True)
            if int(periodo_letivo) == 2:
                MatriculaPeriodo.objects.filter(aluno_id=aluno.id, ano_letivo__ano=ano_letivo.ano, periodo_letivo=1).update(
                    periodo_integralizado_ensino_medio=True
                )

            if alterar_situacao:
                super().save(*args, **kwargs)
                MatriculaPeriodo.objects.filter(aluno_id=aluno.id, ano_letivo__ano=ano_letivo.ano).update(periodo_integralizado_ensino_medio=True)

            if aluno.matriz_id is None:
                from edu.q_academico import DAO

                DAO().atualizar_situacao_aluno_integralizado_fase_escolar(self.matricula_periodo)


class EditarObsIntegralizacaoEnsinoMedioForm(forms.ModelFormPlus):
    class Meta:
        model = Aluno
        fields = ('obs_integralizacao_ensino_medio',)


class TrancarMatriculaForm(ProcedimentoMatriculaForm):
    excluir_pedido_matricula = forms.BooleanField(
        label='Excluir Pedido de Renovação de Matrícula',
        required=False,
        help_text='Marque esta opção caso o aluno tenha realizado um pedido de renovação de matrícula que não foi processado.',
    )

    fieldsets = (
        (
            'Procedimento de Matrícula',
            {'fields': ('ano_letivo', 'periodo_letivo', 'processo', 'data', 'opcoes', 'motivo', 'excluir_pedido_matricula', 'matricula_periodo')},
        ),
    )

    def clean(self):
        aluno = self.matricula_periodo.aluno
        is_trancamento_voluntario = False
        if 'opcoes' in self.cleaned_data:
            is_trancamento_voluntario = int(self.cleaned_data['opcoes'].split(';')[1]) == SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE

        if is_trancamento_voluntario:
            if aluno.is_atingido_limite_trancamento_voluntario(self.matricula_periodo):
                raise forms.ValidationError('Não é possível realizar outro trancamento voluntário. O limite do curso já foi atingido.')
            if not aluno.is_periodo_ingresso_integralizado():
                raise forms.ValidationError(
                    'Não é possível realizar o trancamento voluntário pois o aluno não integralizou todos os componentes curriculares de seu período de ingresso.'
                )
            if (
                not self.cleaned_data.get('excluir_pedido_matricula')
                and PedidoMatriculaDiario.objects.filter(
                    pedido_matricula__matricula_periodo_id=self.matricula_periodo.id, data_processamento__isnull=True
                ).exists()
            ):
                raise forms.ValidationError('Não é possível realizar o trancamento pois o aluno possui pedido de matrícula em andamento.')

        return super().clean()

    def clean_excluir_pedido_matricula(self):
        excluir = self.cleaned_data.get('excluir_pedido_matricula')
        if (
            not excluir
            and PedidoMatriculaDiario.objects.filter(
                pedido_matricula__matricula_periodo_id=self.matricula_periodo.id, data_processamento__isnull=True
            ).exists()
        ):
            raise forms.ValidationError(
                'Não é possível realizar o trancamento pois o aluno possui pedido de renovação de matrícula não processada no período letivo.'
            )
        return excluir

    def get_choices(self):
        return [
            [
                f'{SituacaoMatricula.INTERCAMBIO};{SituacaoMatriculaPeriodo.INTERCAMBIO};{MatriculaDiario.SITUACAO_TRANCADO}',
                ProcedimentoMatricula.INTERCAMBIO,
            ],
            [
                f'{SituacaoMatricula.TRANCADO};{SituacaoMatriculaPeriodo.TRANCADA};{MatriculaDiario.SITUACAO_TRANCADO}',
                ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
            ],
            [
                f'{SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE};{SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE};{MatriculaDiario.SITUACAO_TRANCADO}',
                ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
            ],
        ]


class TransferenciaCursoForm(ProcedimentoMatriculaForm):
    matriz_curso = forms.ModelChoiceFieldPlus(MatrizCurso.objects, label='Matriz/Curso de Destino')
    forma_ingresso = forms.ModelChoiceField(FormaIngresso.objects, label='Forma de Ingresso')
    turno = forms.ModelChoiceFieldPlus(Turno.objects, label='Turno')
    importar_pasta_documental = forms.BooleanField(
        label='Importar Pasta Documental',
        required=False,
        help_text='Marque esta opção caso deseje migrar a pasta documental do aluno para a nova matrícula.',
        initial=True,
    )

    fieldsets = (
        (
            'Procedimento de Matrícula',
            {
                'fields': (
                    'ano_letivo',
                    'periodo_letivo',
                    'processo',
                    'data',
                    'opcoes',
                    'matriz_curso',
                    'forma_ingresso',
                    'turno',
                    'motivo',
                    'importar_pasta_documental',
                    'matricula_periodo',
                )
            },
        ),
    )

    def __init__(self, matricula_periodo_pk, tipo, *args, **kwargs):
        self.tipo = tipo
        super().__init__(matricula_periodo_pk, *args, **kwargs)

        matricula_periodo = MatriculaPeriodo.objects.get(pk=matricula_periodo_pk)
        curso_campus = matricula_periodo.aluno.curso_campus

        if tipo == 'Intercampus':
            qs_matriz_curso = MatrizCurso.objects.exclude(curso_campus__diretoria__setor__uo=curso_campus.diretoria.setor.uo)
        else:
            qs_matriz_curso = MatrizCurso.objects.filter(curso_campus__diretoria__setor__uo=curso_campus.diretoria.setor.uo)

        if self.instance.user and in_group(self.instance.user, 'Administrador Acadêmico'):
            qs_matriz_curso = qs_matriz_curso.filter(
                curso_campus__modalidade__nivel_ensino=matricula_periodo.aluno.curso_campus.modalidade.nivel_ensino
            )
        else:
            qs_matriz_curso = qs_matriz_curso.filter(curso_campus__modalidade=matricula_periodo.aluno.curso_campus.modalidade)

        self.fields['matriz_curso'].queryset = qs_matriz_curso.exclude(curso_campus=curso_campus)
        self.fields['forma_ingresso'].queryset = self.fields['forma_ingresso'].queryset.filter(ativo=True, descricao__contains='Transf')
        self.initial['turno'] = matricula_periodo.aluno.turno_id

    def get_choices(self):
        tipo_procedimento = (
            self.tipo == 'Intercampus' and ProcedimentoMatricula.TRANSFERENCIA_INTERCAMPUS or ProcedimentoMatricula.TRANSFERENCIA_CURSO
        )
        return [
            [
                f'{SituacaoMatricula.TRANSFERIDO_INTERNO};{SituacaoMatriculaPeriodo.TRANSF_CURSO};{MatriculaDiario.SITUACAO_CANCELADO}',
                tipo_procedimento,
            ]
        ]


class TransferenciaExternaForm(ProcedimentoMatriculaForm):
    def get_choices(self):
        return [
            [
                f'{SituacaoMatricula.TRANSFERIDO_EXTERNO};{SituacaoMatriculaPeriodo.TRANSF_EXTERNA};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.TRANSFERENCIA_EXTERNA,
            ]
        ]


class ReintegrarAlunoForm(forms.ModelFormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)

    class Meta:
        model = ProcedimentoMatricula
        fields = ('processo', 'data', 'motivo')

    def __init__(self, matricula_periodo, *args, **kwargs):
        self.matricula_periodo = matricula_periodo
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.cleaned_data.get('ano_letivo'):
            return self.cleaned_data
        elif (self.cleaned_data['ano_letivo'].ano < self.matricula_periodo.ano_letivo.ano) or (
            self.cleaned_data['ano_letivo'].ano == self.matricula_periodo.ano_letivo.ano
            and int(self.cleaned_data['periodo_letivo']) <= self.matricula_periodo.periodo_letivo
        ):
            raise forms.ValidationError('Período de reintegração inválido.')
        else:
            return self.cleaned_data


class EvasaoEmLoteForm(forms.FormPlus):
    SUBMIT_LABEL = 'Pesquisar'
    METHOD = 'GET'

    ano_letivo = forms.ModelChoiceField(Ano.objects, label='Ano letivo')
    periodo_letivo = forms.ChoiceField(label='Período letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)

    ano_ingresso_inicio = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de ingresso a partir de', required=False)
    ano_ingresso_fim = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de ingresso até', required=False)
    periodo_ingresso_inicio = forms.ChoiceField(
        choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de ingresso a partir de', required=False
    )
    periodo_ingresso_fim = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de ingresso até', required=False)

    periodo_referencia = forms.ChoiceField(
        label='Período de referência atual', required=False, choices=[[0, '----']] + [[x, x] for x in range(1, 11)]
    )

    disciplina_obrigatoria_pendente = forms.BooleanField(
        label='Possui disciplina obrigatória pendente',
        required=False,
    )

    uo = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.locals, label='Campus', required=False)
    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
    )
    modalidade = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidade', required=False)

    fieldsets = (
        ('Período letivo', {'fields': (('ano_letivo', 'periodo_letivo'),)}),
        (
            'Período de ingresso',
            {
                'fields': (
                    ('ano_ingresso_inicio', 'periodo_ingresso_inicio'),
                    ('ano_ingresso_fim', 'periodo_ingresso_fim'),
                )
            },
        ),
        (
            'Outros filtros',
            {
                'fields': (
                    'periodo_referencia',
                    'disciplina_obrigatoria_pendente',
                    'uo',
                    'curso_campus',
                    'modalidade',
                )
            },
        ),
    )

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        uo = self.cleaned_data['uo']
        curso_campus = self.cleaned_data['curso_campus']
        modalidade = self.cleaned_data['modalidade']

        ano_ingresso_inicio = self.cleaned_data['ano_ingresso_inicio']
        ano_ingresso_fim = self.cleaned_data['ano_ingresso_fim']
        periodo_ingresso_inicio = self.cleaned_data['periodo_ingresso_inicio'] or 0
        periodo_ingresso_fim = self.cleaned_data['periodo_ingresso_fim'] or 0
        periodo_referencia = self.cleaned_data['periodo_referencia'] or 0
        disciplina_obrigatoria_pendente = self.cleaned_data['disciplina_obrigatoria_pendente']

        qs = Aluno.locals_uo.filter(
            matriculaperiodo__ano_letivo=ano_letivo,
            matriculaperiodo__periodo_letivo=periodo_letivo,
            matriculaperiodo__situacao_id=SituacaoMatriculaPeriodo.EM_ABERTO,
            matriz__isnull=False,
        )

        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo__in=uo)
        if curso_campus:
            qs = qs.filter(curso_campus=curso_campus)
        if modalidade:
            qs = qs.filter(curso_campus__modalidade__in=modalidade)

        if int(periodo_referencia):
            qs = qs.filter(periodo_atual=periodo_referencia)

        if ano_ingresso_inicio:
            qs = qs.filter(ano_letivo__gte=ano_ingresso_inicio)
            if int(periodo_ingresso_inicio) == 2:
                qs = qs.exclude(ano_letivo=ano_ingresso_inicio, periodo_letivo=1)
        if ano_ingresso_fim:
            qs = qs.filter(ano_letivo__lte=ano_ingresso_fim)
            if int(periodo_ingresso_fim) == 1:
                qs = qs.exclude(ano_letivo=ano_ingresso_fim, periodo_letivo=2)

        if disciplina_obrigatoria_pendente:
            qs = qs.filter(pendencia_ch_obrigatoria=True)

        return qs.order_by('curso_campus__codigo')


class MatriculaVinculoForm(ProcedimentoMatriculaForm):
    def get_choices(self):
        return [
            [
                f'{SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL};{SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL};{MatriculaDiario.SITUACAO_CANCELADO}',
                ProcedimentoMatricula.MATRICULA_VINCULO,
            ]
        ]

    def clean(self):
        if not in_group(self.request.user, 'Administrador Acadêmico'):
            motivo = self.matricula_periodo.aluno.deve_impedir_matricula_vinculo()
            if motivo:
                raise forms.ValidationError(motivo)
        return super().clean()


class MatriculaIngressosTurmaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Pesquisar'
    METHOD = 'GET'

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, label='Período Letivo')
    diretoria = forms.ModelChoiceField(Diretoria.objects.none())
    curso = forms.ModelChoiceFieldPlus(CursoCampus.objects, label='Curso', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals
        self.fields['curso'].queryset = CursoCampus.objects.filter(ativo=True, diretoria__in=Diretoria.locals.all())

    def processar(self):
        qs_turmas = Turma.locals.filter(
            ano_letivo=self.cleaned_data.get('ano_letivo'),
            periodo_letivo=self.cleaned_data.get('periodo_letivo'),
            curso_campus__diretoria=self.cleaned_data.get('diretoria'),
        )

        if self.cleaned_data.get('curso'):
            qs_turmas = qs_turmas.filter(curso_campus=self.cleaned_data.get('curso'))

        turmas = []
        alunos_aptos_matricular = []
        for turma in qs_turmas:
            alunos_nao_matriculados = turma.get_alunos_apto_matricula(apenas_ingressantes=True)
            turma.total_nao_matriculados = alunos_nao_matriculados.count()
            if turma.total_nao_matriculados:
                alunos_aptos_matricular = alunos_aptos_matricular + list(alunos_nao_matriculados.values_list('aluno__id', flat=True))
                turma.total_matriculados = turma.get_alunos_matriculados().count()
                turma.total_aptos_matricula = turma.get_alunos_apto_matricula(ignorar_matriculados=False, apenas_ingressantes=True).count()
                turmas.append(turma)

        return turmas, list(set(alunos_aptos_matricular))


class AproveitamentoComponenteForm(forms.ModelFormPlus):
    ano_letivo = forms.ModelChoiceField(
        Ano.objects.ultimos(), label='Ano Letivo', help_text='Ano letivo no qual a equivalência da disciplina está sendo registrada'
    )
    periodo_letivo = forms.ChoiceField(
        label='Período Letivo',
        choices=Aluno.PERIODO_LETIVO_CHOICES,
        help_text='Período letivo no qual a equivalência da disciplina está sendo registrada',
    )
    matriculas_diario_resumidas = forms.MultipleModelChoiceField(
        MatriculaDiarioResumida.objects.all(),
        required=False,
        label='',
        widget=RenderableSelectMultiple('widgets/matricula_diario_resumida_widget.html'),
    )
    matriculas_diario = forms.MultipleModelChoiceField(
        MatriculaDiario.objects.all(), required=False, label='', widget=RenderableSelectMultiple('widgets/matricula_diario_widget.html')
    )
    registros_historico = forms.MultipleModelChoiceField(
        RegistroHistorico.objects.all(), required=False, label='', widget=RenderableSelectMultiple('widgets/registro_historico_widget.html')
    )

    class Meta:
        model = AproveitamentoComponente
        fields = ['matriculas_diario_resumidas', 'matriculas_diario', 'registros_historico']

    def __init__(self, aluno, componente_curricular, *args, **kwargs):
        self.aluno = aluno
        self.componente_curricular = componente_curricular
        super().__init__(*args, **kwargs)
        self.fields['ano_letivo'].queryset = Ano.objects.filter(id__in=self.aluno.matriculaperiodo_set.values_list('ano_letivo_id', flat=True))
        qs_componentes = aluno.matriz.componentecurricular_set.select_related('componente').all()
        self.fields['matriculas_diario_resumidas'].queryset = MatriculaDiarioResumida.objects.filter(
            matricula_periodo__aluno=aluno,
            situacao__in=[
                MatriculaDiario.SITUACAO_APROVADO,
                MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
            ],
        ).exclude(equivalencia_componente__componente_id__in=qs_componentes.values_list('componente_id', flat=True))
        self.fields['matriculas_diario'].queryset = MatriculaDiario.objects.filter(
            matricula_periodo__aluno=aluno, situacao__in=[MatriculaDiario.SITUACAO_APROVADO]
        ).exclude(diario__componente_curricular__componente_id__in=qs_componentes.values_list('componente_id', flat=True))
        self.fields['registros_historico'].queryset = RegistroHistorico.objects.filter(
            matricula_periodo__aluno=aluno,
            situacao__in=[
                MatriculaDiario.SITUACAO_APROVADO,
                MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
                MatriculaDiario.SITUACAO_DISPENSADO,
            ],
        ).exclude(componente_id__in=qs_componentes.values_list('componente_id', flat=True))
        if self.instance.pk:
            self.fields['ano_letivo'].initial = self.instance.matricula_periodo.ano_letivo.pk
            self.fields['periodo_letivo'].initial = self.instance.matricula_periodo.periodo_letivo

        academico_nome_sistema = Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema') or 'Q-Acadêmico'
        self.fieldsets = (
            ('Período Letivo', {'fields': ('ano_letivo', 'periodo_letivo')}),
            (f'Componentes Cursados no {academico_nome_sistema}', {'fields': (('matriculas_diario_resumidas'),)}),
            ('Componentes Cursados no Suap', {'fields': (('matriculas_diario'),)}),
            ('Outros Componentes', {'fields': (('registros_historico'),)}),
        )

    def clean(self):
        if 'ano_letivo' not in self.cleaned_data or 'periodo_letivo' not in self.cleaned_data:
            return self.cleaned_data

        if PedidoMatriculaDiario.objects.filter(
            pedido_matricula__matricula_periodo__aluno=self.aluno,
            data_processamento__isnull=True,
            diario__componente_curricular=self.componente_curricular,
        ).exists():
            raise forms.ValidationError(
                'O aluno solicitou matrícula nessa disciplina. Aguarde o processamento do pedido de matrícula para realizar esse procedimeto.'
            )

        if not self.get_matricula_periodo_queryset().exists():
            raise forms.ValidationError('O aluno não está matriculado no ano/período informado.')

        if (
            not self.cleaned_data['matriculas_diario_resumidas']
            and not self.cleaned_data['matriculas_diario']
            and not self.cleaned_data['registros_historico']
        ):
            raise forms.ValidationError('Selecione ao menos um componente')
        return self.cleaned_data

    def get_matricula_periodo_queryset(self):
        return self.aluno.matriculaperiodo_set.filter(ano_letivo=self.cleaned_data['ano_letivo'], periodo_letivo=self.cleaned_data['periodo_letivo'])

    def save(self, *args, **kwargs):
        self.instance.matricula_periodo = self.get_matricula_periodo_queryset()[0]
        self.instance.componente_curricular = self.componente_curricular
        super().save(*args, **kwargs)


class EditarMatriculaDiarioResumidaForm(forms.ModelForm):
    frequencia = forms.IntegerField(label='Frequência')
    titularidade_professor = forms.ChoiceField(label='Titulação', choices=[['', '-----'], *Professor.TITULACAO_CHOICES], required=True)

    class Meta:
        model = MatriculaDiarioResumida
        fields = ('frequencia', 'media_final_disciplina', 'nome_professor', 'titularidade_professor', 'ch_extensao_cumprida')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.matricula_periodo.aluno.situacao.ativo:
            del self.fields['media_final_disciplina']
            del self.fields['frequencia']

    def save(self, *args, **kwargs):
        if self.instance.matricula_periodo.aluno.situacao.ativo:
            MULTIPLICADOR_DECIMAL = 1
            if settings.NOTA_DECIMAL:
                MULTIPLICADOR_DECIMAL = settings.CASA_DECIMAL == 1 and 10 or 100

            media_final_disciplina = self.cleaned_data.get('media_final_disciplina') * MULTIPLICADOR_DECIMAL
            frequencia = self.cleaned_data.get('frequencia')
            estrutura_curso = self.instance.matricula_periodo.aluno.matriz.estrutura

            if estrutura_curso.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_NOTA:
                # Avaliação por Nota
                if media_final_disciplina < estrutura_curso.media_aprovacao_sem_prova_final:
                    self.instance.situacao = MatriculaDiario.SITUACAO_REPROVADO
                else:
                    self.instance.situacao = MatriculaDiario.SITUACAO_APROVADO
            elif estrutura_curso.is_lancamento_conceito():
                # Avaliação por Conceito
                if media_final_disciplina < estrutura_curso.get_nota_minima_aprovacao_conceito():
                    self.instance.situacao = MatriculaDiario.SITUACAO_REPROVADO
                else:
                    self.instance.situacao = MatriculaDiario.SITUACAO_APROVADO
            else:
                # Avaliação por Frequência
                if frequencia < estrutura_curso.percentual_frequencia:
                    self.instance.situacao = MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA
                else:
                    self.instance.situacao = MatriculaDiario.SITUACAO_APROVADO

        if self.instance.codigo_professor and self.instance.codigo_diario_pauta:
            MatriculaDiarioResumida.objects.filter(
                codigo_professor=self.instance.codigo_professor, codigo_diario_pauta=self.instance.codigo_diario_pauta
            ).update(titularidade_professor=self.instance.titularidade_professor, nome_professor=self.instance.nome_professor)

        super().save(*args, **kwargs)


class AlunosConflitosHorariosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Pesquisar'
    METHOD = 'GET'

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, label='Período Letivo')
    diretoria = forms.ModelChoiceField(Diretoria.objects.none())
    curso = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('diretoria', 'diretoria__in')]),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals
        self.fields['curso'].queryset = CursoCampus.objects.filter(ativo=True, diretoria__in=Diretoria.locals.all())

    def processar(self):
        qs_matriculas_periodos = MatriculaPeriodo.objects.filter(
            aluno__matriz__isnull=False,
            aluno__curso_campus__diretoria=self.cleaned_data['diretoria'],
            ano_letivo=self.cleaned_data['ano_letivo'],
            periodo_letivo=self.cleaned_data['periodo_letivo'],
            matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        ).distinct()

        if self.cleaned_data['curso']:
            qs_matriculas_periodos = qs_matriculas_periodos.filter(aluno__curso_campus=self.cleaned_data['curso'])

        alunos_conflitos_horarios = {}
        for matricula_periodo in qs_matriculas_periodos:
            horarios_conflitos = matricula_periodo.get_horarios_com_choque()
            if horarios_conflitos:
                alunos_conflitos_horarios.update({matricula_periodo.aluno: horarios_conflitos})
        return alunos_conflitos_horarios


class RequerimentoForm(forms.ModelFormPlus):
    class Meta:
        model = Requerimento
        exclude = ('situacao', 'deferido', 'observacao')

    class Media:
        js = ('/static/edu/js/RequerimentoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        automatizados = [choice[0] for choice in Requerimento.TIPO_AUTOMATIZADO_CHOICES]
        choices = []
        for choice in Requerimento.TIPO_CHOICES:
            if choice[0] not in automatizados:
                choices.append(choice)
        self.fields['tipo'].choices = choices
        if self.instance.pk:
            self.fields['atendente'].queryset = self.instance.get_atendentes_possiveis()

    def save(self, *args, **kwargs):
        conteudo = f"""
Caro(a) aluno(a),

Foi realizado o cadastro do seu requerimento para {self.instance.get_tipo_display()}. Para mais informações procure a secretaria acadêmica.

"""
        mensagem = Mensagem()
        mensagem.remetente = self.request.user
        mensagem.assunto = f'Novo Requerimento - {self.instance.get_tipo_display()}'
        mensagem.conteudo = conteudo
        mensagem.via_suap = True
        mensagem.via_email = False
        mensagem.save()
        mensagem.destinatarios.add(self.instance.aluno.get_user())
        mensagem.save()
        return super().save(*args, **kwargs)


class RequerimentoTrancamentoMatriculaForm(forms.ModelFormPlus):
    class Meta:
        model = Requerimento
        fields = ('descricao',)

    def save(self, *args, **kwargs):
        self.instance.aluno.solicitar_quitacao_nada_consta(procedimento=ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO)
        return super().save(*args, **kwargs)


class RequerimentoRealizacaoProvaForm(forms.ModelFormPlus):
    diario = forms.ModelChoiceFieldPlus(Diario.objects.none(), label='Diário')

    class Meta:
        model = Requerimento
        fields = ('diario', 'descricao', 'anexo')


class RequerimentoAproveitamentoEstudoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Continuar'

    class Meta:
        model = RequerimentoAproveitamentoEstudo
        fields = (
            'interno',
            'instituicao',
            'historico_escolar',
            'comprovante_reconhecimento_curso',
        )
        widgets = {
            'interno': forms.RadioSelect(choices=[[True, 'Nesta instituição'], [False, 'Outra instituição']]),
        }

    class Media:
        js = ('/static/edu/js/RequerimentoAproveitamentoEstudoForm.js',)

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'interno',
                    'instituicao',
                    ('historico_escolar', 'comprovante_reconhecimento_curso'),
                )
            },
        ),
    )

    def clean_interno(self):
        interno = self.cleaned_data.get('interno')
        if interno is None:
            return None
        if not interno:
            for name in ['instituicao']:
                if not self.data.get(name):
                    raise forms.ValidationError('Informe a instituição.')
            for name in ['historico_escolar']:
                if name not in self.request.FILES:
                    raise forms.ValidationError('Informe o histórico escolar.')
            return False
        if interno:
            hoje = datetime.date.today()
            qs = (
                Diario.objects.filter(
                    matriculadiario__situacao=MatriculaDiario.SITUACAO_APROVADO,
                    matriculadiario__matricula_periodo__aluno__pessoa_fisica__cpf=self.instance.matricula_periodo.aluno.pessoa_fisica.cpf,
                )
                .exclude(matriculadiario__matricula_periodo__aluno=self.instance.matricula_periodo.aluno)
                .exclude(turma__curso_campus__modalidade=Modalidade.FIC)
                .filter(ano_letivo__ano__gte=(hoje.year - RequerimentoAproveitamentoEstudo.QTD_ANOS_APROVEITAMENTO), ano_letivo__ano__lte=hoje.year)
            )
            if not qs.exists():
                raise forms.ValidationError('Você não possui diários aprovados em cursos regulares nessa instituição nos últimos anos.')
        return True


class SolicitacaoAproveitamentoEstudoInternoFom(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoAproveitamentoEstudoInterno
        fields = (
            'componente_curricular',
            'ementa',
            'diario_1',
            'ementa_1',
            'diario_2',
            'ementa_2',
        )

    fieldsets = (
        ('Componente a Aproveitar', {'fields': ('componente_curricular', 'ementa')}),
        ('Componente Cursado (Principal)', {'fields': (('diario_1', 'ementa_1'),)}),
        ('Componente Adicional (Opcional)', {'fields': (('diario_2', 'ementa_2'),)}),
    )

    def __init__(self, *args, **kwargs):
        hoje = datetime.date.today()
        self.requerimento = kwargs.pop('requerimento')
        super().__init__(*args, **kwargs)
        self.fields['componente_curricular'].queryset = self.requerimento.aluno.matriz.componentecurricular_set.exclude(
            componente__in=self.requerimento.aluno.get_ids_componentes_cumpridos()
        ).exclude(componente__in=self.requerimento.aluno.get_ids_componentes_nao_certificaveis())
        self.fields['componente_curricular'].help_text = 'Só serão listados os compontentes aptos para o aproveitamento.'
        diarios = (
            Diario.objects.filter(
                matriculadiario__situacao=MatriculaDiario.SITUACAO_APROVADO,
                matriculadiario__matricula_periodo__aluno__pessoa_fisica__cpf=self.requerimento.aluno.pessoa_fisica.cpf,
            )
            .exclude(matriculadiario__matricula_periodo__aluno=self.requerimento.aluno)
            .exclude(turma__curso_campus__modalidade=Modalidade.FIC)
            .filter(ano_letivo__ano__gte=(hoje.year - 12), ano_letivo__ano__lte=hoje.year)
            .distinct()
        )
        self.fields['diario_1'].queryset = diarios.distinct()
        self.fields['diario_2'].queryset = diarios.distinct()

    def clean(self) -> dict[str, object]:
        dados = []
        for name in ['diario_2', 'ementa_2']:
            dados.append(self.cleaned_data.get(name))
        if any(dados) and not all(dados):
            raise forms.ValidationError('Ou informe todos os dados referente ao segundo componente cursado ou não informe nenhum.')
        qs = (
            SolicitacaoAproveitamentoEstudo.objects.filter(
                requerimento__aluno=self.requerimento.aluno,
                componente_curricular=self.cleaned_data.get('componente_curricular'),
                parecer__isnull=True,
            )
            .exclude(requerimento__situacao=Requerimento.SITUACAO_ARQUIVADO)
            .exclude(pk=self.instance.pk)
        )
        if qs.exists():
            raise forms.ValidationError('Já existe uma solicitação de aproveitamento para a disciplina informada.')
        return self.cleaned_data


class SolicitacaoAproveitamentoEstudoExternoFom(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoAproveitamentoEstudoExterno
        fields = (
            'componente_curricular',
            'ementa',
            'ano_letivo_1',
            'periodo_letivo_1',
            'nome_1',
            'nota_1',
            'frequencia_1',
            'ementa_1',
            'ano_letivo_2',
            'periodo_letivo_2',
            'nome_2',
            'nota_2',
            'frequencia_2',
            'ementa_2',
        )

    fieldsets = (
        ('Componente a Aproveitar', {'fields': ('componente_curricular', 'ementa')}),
        ('Componente Cursado (Principal)', {'fields': (('ano_letivo_1', 'periodo_letivo_1'), 'nome_1', ('nota_1', 'frequencia_1'), 'ementa_1')}),
        ('Componente Adicional (Opcional)', {'fields': (('ano_letivo_2', 'periodo_letivo_2'), 'nome_2', ('nota_2', 'frequencia_2'), 'ementa_2')}),
    )

    def __init__(self, *args, **kwargs):
        self.requerimento = kwargs.pop('requerimento')
        super().__init__(*args, **kwargs)
        hoje = datetime.date.today()
        for name in ['ano_letivo_1', 'ano_letivo_2']:
            self.fields[name].queryset = self.fields[name].queryset.filter(ano__gte=(hoje.year - 12), ano__lte=hoje.year)
        self.fields['componente_curricular'].queryset = self.requerimento.aluno.matriz.componentecurricular_set.exclude(
            componente__in=self.requerimento.aluno.get_ids_componentes_cumpridos()
        ).exclude(componente__in=self.requerimento.aluno.get_ids_componentes_nao_certificaveis())
        self.fields['componente_curricular'].help_text = 'Só serão listados os compontentes aptos para o aproveitamento.'
        for name in ['nota_1', 'nota_2', 'frequencia_1', 'frequencia_2']:
            self.fields[name].help_text = 'Valor de 0 a 100'
        self.fields['ano_letivo_1'].required = True
        self.fields['periodo_letivo_1'].required = True

    def clean(self) -> dict[str, object]:
        dados = []
        for name in ['ano_letivo_2', 'periodo_letivo_2', 'nome_2', 'nota_2', 'frequencia_2', 'ementa_2']:
            dados.append(self.cleaned_data.get(name))
        if any(dados) and not all(dados):
            raise forms.ValidationError('Ou informe todos os dados referente ao segundo componente cursado ou não informe nenhum.')
        qs = (
            SolicitacaoAproveitamentoEstudo.objects.filter(
                requerimento__aluno=self.requerimento.aluno,
                componente_curricular=self.cleaned_data.get('componente_curricular'),
                parecer__isnull=True,
            )
            .exclude(requerimento__situacao=Requerimento.SITUACAO_ARQUIVADO)
            .exclude(pk=self.instance.pk)
        )
        if qs.exists():
            raise forms.ValidationError('Já existe uma solicitação de aproveitamento para a disciplina informada.')
        return self.cleaned_data

    def clean_nota_1(self):
        nota = self.cleaned_data.get('nota_1')
        if nota:
            if nota < 0 or nota > 100:
                raise forms.ValidationError('A nota deve ser um valor de 0 a 100')
        return nota

    def clean_nota_2(self):
        nota = self.cleaned_data.get('nota_2')
        if nota:
            if nota < 0 or nota > 100:
                raise forms.ValidationError('A nota deve ser um valor de 0 a 100')
        return nota

    def clean_frequencia_1(self):
        nota = self.cleaned_data.get('frequencia_1')
        if nota:
            if nota < 0 or nota > 100:
                raise forms.ValidationError('A nota deve ser um valor de 0 a 100')
        return nota

    def clean_frequencia_2(self):
        nota = self.cleaned_data.get('frequencia_2')
        if nota:
            if nota < 0 or nota > 100:
                raise forms.ValidationError('A nota deve ser um valor de 0 a 100')
        return nota


class EncaminharSolicitacaoAproveitamentoEstudoForm(forms.FormPlus):
    INFO = 'Informe o professor responsável pela análise dessa solicitação ou desmarque o professor selecionado caso queira cancelar a atribuição.'
    avaliador = forms.ModelChoiceFieldPlus(Professor.objects, label='Avaliador', required=False)


class AvaliarSolicitacaoAproveitamentoEstudoForm(forms.FormPlus):
    INFO = 'Informe o parecer da análise dessa solicitação ou desmarque o parecer selecionado caso queira desfazer a avaliação.'
    parecer = forms.ModelChoiceFieldPlus(
        ParecerAvaliacaoAproveitamentoEstudo.objects, label='Parecer', required=False, widget=forms.widgets.RadioSelect()
    )
    observacao = forms.CharField(label='Observação', widget=forms.Textarea(), required=False, help_text='Obrigatório em caso de indeferimento')

    def __init__(self, *args, **kwargs):
        self.solicitacao = kwargs.pop('solicitacao')
        super().__init__(*args, **kwargs)

    def clean(self):
        parecer = self.cleaned_data.get('parecer')
        observacao = self.cleaned_data.get('observacao')
        if parecer and not parecer.deferido and not observacao:
            raise forms.ValidationError('Informe uma observação')
        if parecer and parecer.deferido:
            mp = self.solicitacao.requerimento.aluno.get_ultima_matricula_periodo()
            AproveitamentoEstudo.validar(mp, self.solicitacao.componente_curricular, ignorar_corequisito=True)
        return super().clean()


class RequerimentoAlunoForm(forms.ModelFormPlus):
    class Meta:
        model = Requerimento
        fields = ('tipo', 'descricao', 'anexo')


class RequerimentoMatriculaDiarioForm(forms.ModelFormPlus):
    class Meta:
        model = RequerimentoMatriculaDisciplina
        fields = ('descricao', 'diario')

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.aluno = aluno
        self.instance.data = datetime.date.today()
        mp = aluno.get_ultima_matricula_periodo()
        qs_diario = Diario.objects.filter(
            ano_letivo=mp.ano_letivo,
            periodo_letivo=mp.periodo_letivo,
            turma__curso_campus__modalidade=aluno.curso_campus.modalidade,
            turma__curso_campus__diretoria__setor__uo_id=aluno.curso_campus.diretoria.setor.uo_id,
        )
        qs_diario = qs_diario.exclude(componente_curricular__componente_id__in=aluno.get_ids_componentes_cumpridos()).exclude(
            componente_curricular__componente_id__in=aluno.get_ids_componentes_cursando()
        )
        self.fields['diario'].queryset = qs_diario
        self.fields['diario'].required = True

    def clean_diario(self):
        diario = self.cleaned_data.get('diario')
        if diario:
            pode_solicitar_matricula, msg = self.instance.aluno.pode_ser_matriculado_no_diario(diario)
            if not pode_solicitar_matricula:
                raise ValidationError(msg)
        return diario


class RequerimentoQuebraRequisitoForm(forms.ModelFormPlus):
    class Meta:
        model = RequerimentoMatriculaQuebraRequisito
        fields = ('descricao', 'anexo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].required = True


class RequerimentoMatriculaComAumentoCHForm(forms.ModelFormPlus):
    class Meta:
        model = RequerimentoMatriculaComAumentoDeCH
        fields = ('descricao', 'anexo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].required = True


class RequerimentoCancelamentoDisciplinaForm(forms.ModelFormPlus):
    matriculas_diario = forms.MultipleChoiceField(label='Disciplinas', widget=forms.CheckboxSelectMultiplePlus())

    class Meta:
        model = RequerimentoCancelamentoDisciplina
        fields = ('descricao', 'matriculas_diario')

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.aluno = aluno
        self.instance.data = datetime.date.today()
        qs = (
            aluno.get_ultima_matricula_periodo()
            .matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
            .select_related('diario__componente_curricular__componente')
        )
        choices = []
        for md in qs:
            choices.append(
                (md.pk, f'{md.diario.componente_curricular.componente.descricao_historico} - {md.diario.componente_curricular.get_periodo_oferta()}')
            )
        self.fields['matriculas_diario'].choices = choices

    def clean_matriculas_diario(self):
        pks = self.cleaned_data['matriculas_diario']
        matriculas_diario = MatriculaDiario.objects.filter(pk__in=pks)
        for matricula_diario in matriculas_diario:
            matricula_diario.cancelar(False, [md.diario for md in matriculas_diario if md.id != matricula_diario.id])
        return matriculas_diario


class AvaliacaoRequerimentoForm(forms.ModelFormPlus):
    TITLE = 'Alterar Situação'

    deferido = forms.ChoiceField(label='Deferido', choices=(('None', '-----'), (True, 'Sim'), (False, 'Não')), required=False)

    class Meta:
        model = Requerimento
        fields = ('deferido', 'situacao', 'observacao')

    def clean_situacao(self):
        if self.cleaned_data.get('deferido') is not None:
            if self.cleaned_data.get('situacao') != 'Arquivado':
                raise forms.ValidationError('A situação do requerimento deve ser "Arquivado"')
        if self.cleaned_data.get('situacao') == 'Arquivado' and self.cleaned_data.get('deferido') == 'None':
            raise forms.ValidationError('É necessário deferir ou indeferir o requerimento antes de arquivá-lo.')
        return self.cleaned_data.get('situacao')

    def save(self, user, *args, **kwargs):
        self.instance.atendente = user
        instance = super().save(*args, **kwargs)
        self.instance.enviar_email()
        return instance


class PremiacaoForm(forms.ModelForm):
    class Meta:
        model = Premiacao
        exclude = ('aluno',)

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno

    def save(self, *args, **kwargs):
        self.instance.aluno = self.aluno
        self.instance.save()


class MedidaDisciplinarForm(forms.ModelForm):
    class Meta:
        model = MedidaDisciplinar
        exclude = ('aluno',)

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno

    def save(self, *args, **kwargs):
        self.instance.aluno = self.aluno
        self.instance.save()


class IndeferirRequerimentoForm(forms.ModelFormPlus):
    class Meta:
        model = Requerimento
        fields = ('observacao',)


class IndeferirRequerimentoEmLoteForm(forms.Form):
    observacao = forms.CharField(
        label='Justificativa do indeferimento', widget=forms.Textarea(), help_text='Informe o motivo do indeferimento dos requerimentos listados.'
    )


class ImportarMatrizCSVForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )
    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_matrizes_csv(file_contents, apenas_validar, False)


class ImportarComponenteCSVForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )
    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_componentes_csv(file_contents, apenas_validar, False)


class ImportarCursoCSVForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )

    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_cursos_csv(file_contents, apenas_validar, False)


class ImportarAlunoCSVFormV2(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )

    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    ignorar_obrigatorios = forms.BooleanField(
        label='Ignorar campos obrigatórios',
        required=False,
        help_text='Marque esta opção se desejar ignorar os campos obrigatórios.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        ignorar_obrigatorios = self.cleaned_data.get('ignorar_obrigatorios')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_alunos_csv_v2(file_contents, apenas_validar, ignorar_obrigatorios)


class ImportarHistoricoAlunoCSVForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )

    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    ignorar_obrigatorios = forms.BooleanField(
        label='Ignorar campos obrigatórios',
        required=False,
        help_text='Marque esta opção se desejar ignorar a obrigatoriedade de nota, conceito, frequência e período da matriz.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        ignorar_obrigatorios = self.cleaned_data.get('ignorar_obrigatorios')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_historico_aluno_csv(file_contents, apenas_validar, ignorar_obrigatorios)


class ImportarProcedimentoMatriculaCSVForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )

    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_procedimento_matricula_csv(file_contents, apenas_validar, False)


class ImportarEquivalenciaCSVForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )
    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar o arquivo de migração. Os dados não serão salvos no SUAP.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.importar_equivalencia_csv(file_contents, apenas_validar, False)


class InicializarPeriodoLetivoForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        filetypes=[
            'csv',
        ],
    )
    apenas_validar = forms.BooleanField(
        label='Apenas validar',
        required=False,
        help_text='Marque esta opção para validar as matrículas a serem inicializadas. Os dados não serão salvos no SUAP.',
    )

    def processar(self):
        arquivo_csv = self.cleaned_data.get('arquivo')
        apenas_validar = self.cleaned_data.get('apenas_validar')
        file_contents = arquivo_csv.read().decode('utf-8')
        return tasks.inicializar_periodo_letivo(file_contents, apenas_validar, False)


class InconsistenciasForm(forms.FormPlus):
    tipo = forms.ChoiceField(
        label='Tipo de inconsistência',
        choices=[
            ['', '---'],
            ['1', 'Situação de matrícula em período'],
            ['2', 'Período de referência do aluno'],
            ['2b', 'Período de referência no período letivo'],
            ['3', 'Alunos sem matrícula período no ano corrente'],
            ['4', 'Situação de matrícula do aluno'],
        ],
        required=True,
    )
    somente_integralizado = forms.BooleanField(
        label='Somente alunos integralizados', initial=True, help_text='Alunos que foram migrados do sistema legado para o SUAP.', required=False
    )
    amostra = forms.BooleanField(
        label='Exibir amostragem', initial=True, help_text='Exibe uma amostragem de pelo menos 10 inconsistências encontradas.', required=False
    )
    situacoes = forms.MultipleModelChoiceFieldPlus(
        SituacaoMatricula.objects, label='Situação', required=False, help_text='Situação atual de matrícula do aluno.'
    )
    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects, label='Campus', required=False)
    curso = forms.ModelChoiceFieldPlus(CursoCampus.objects, label='Curso', required=False)
    matriz = forms.ModelChoiceFieldPlus(Matriz.objects, label='Matriz', required=False)
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects, label='Aluno', required=False)

    fieldsets = (('', {'fields': ('tipo', ('somente_integralizado', 'amostra'), ('situacoes', 'campus'), ('curso', 'matriz'), 'aluno')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uos = UnidadeOrganizacional.locals.all()
        self.fields['campus'].queryset = uos
        if uos.count() == 1:
            self.fields['curso'].queryset = CursoCampus.objects.filter(diretoria__setor__uo__in=uos)
            self.fields['matriz'].queryset = Matriz.objects.filter(matrizcurso__curso_campus__diretoria__setor__uo__in=uos).distinct()
            self.fields['aluno'].queryset = Aluno.objects.filter(curso_campus__diretoria__setor__uo__in=uos)

    def processar(self):
        inconsistencias = []
        amostra = self.cleaned_data.get('amostra')

        aluno = self.cleaned_data.get('aluno')
        if aluno:
            qs_aluno = Aluno.objects.filter(id=aluno.id)
        else:
            qs_aluno = Aluno.objects.filter(matriz__isnull=False).exclude(matriz__estrutura__proitec=True)

            somente_integralizado = self.cleaned_data.get('somente_integralizado')
            if somente_integralizado:
                qs_aluno = qs_aluno.filter(data_integralizacao__isnull=False)

            situacoes = self.cleaned_data.get('situacoes')
            if situacoes:
                qs_aluno = qs_aluno.filter(situacao__in=situacoes)

            campus = self.cleaned_data.get('campus')
            if campus:
                qs_aluno = qs_aluno.filter(curso_campus__diretoria__setor__uo=campus)

            curso = self.cleaned_data.get('curso')
            if curso:
                qs_aluno = qs_aluno.filter(curso_campus=curso)

            matriz = self.cleaned_data.get('matriz')
            if matriz:
                qs_aluno = qs_aluno.filter(matriz=matriz)

        tipo = self.cleaned_data.get('tipo')

        if tipo == '2b':
            qs_aluno = qs_aluno.filter(
                matriz__estrutura__tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
                situacao__in=(SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL),
            )

        for aluno in qs_aluno:
            # Situação de matrícula em período
            if tipo == '1':
                estrutura = aluno.matriz.estrutura
                for mp in aluno.matriculaperiodo_set.order_by('ano_letivo__ano', 'periodo_letivo').values('id', 'situacao_id'):
                    mp_id = mp['id']
                    mp_situacao_id = mp['situacao_id']

                    # verifica se é último período do aluno com procedimento de matrícula
                    ultimo = aluno.matriculaperiodo_set.order_by('ano_letivo__ano', 'periodo_letivo').last()
                    if ultimo.id == mp_id:
                        if aluno.situacao_id == SituacaoMatricula.EVASAO and mp_situacao_id == SituacaoMatriculaPeriodo.EVASAO:
                            continue
                        if aluno.situacao_id == SituacaoMatricula.JUBILADO and mp_situacao_id == SituacaoMatriculaPeriodo.JUBILADO:
                            continue
                        if aluno.situacao_id == SituacaoMatricula.CANCELADO and mp_situacao_id == SituacaoMatriculaPeriodo.CANCELADA:
                            continue
                        if (
                            aluno.situacao_id == SituacaoMatricula.CANCELAMENTO_COMPULSORIO
                            and mp_situacao_id == SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO
                        ):
                            continue
                        if (
                            aluno.situacao_id == SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO
                            and mp_situacao_id == SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO
                        ):
                            continue
                        if (
                            aluno.situacao_id == SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE
                            and mp_situacao_id == SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE
                        ):
                            continue
                        if aluno.situacao_id == SituacaoMatricula.TRANSFERIDO_INTERNO and mp_situacao_id == SituacaoMatriculaPeriodo.TRANSF_CURSO:
                            continue
                        if aluno.situacao_id == SituacaoMatricula.TRANSFERIDO_EXTERNO and mp_situacao_id == SituacaoMatriculaPeriodo.TRANSF_EXTERNA:
                            continue
                        if aluno.situacao_id == SituacaoMatricula.MATRICULADO and mp_situacao_id in [
                            SituacaoMatriculaPeriodo.MATRICULADO,
                            SituacaoMatriculaPeriodo.EM_ABERTO,
                        ]:
                            continue

                    situacao = SituacaoMatriculaPeriodo.APROVADO
                    tem_rh = RegistroHistorico.objects.filter(matricula_periodo_id=mp_id).exists()
                    tem_mdr = MatriculaDiarioResumida.objects.filter(matricula_periodo_id=mp_id).exists()
                    tem_md = MatriculaDiario.objects.filter(matricula_periodo_id=mp_id).exists()

                    # verifica se aluno trancado está sem diários ou com todos os diários trancados
                    if mp_situacao_id in [
                        SituacaoMatriculaPeriodo.TRANCADA,
                        SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
                        SituacaoMatriculaPeriodo.INTERCAMBIO,
                    ]:
                        if not tem_rh and not tem_mdr and not tem_md:
                            continue
                        diarios_trancados = True
                        if (
                            tem_rh
                            and RegistroHistorico.objects.filter(matricula_periodo_id=mp_id)
                            .exclude(situacao=MatriculaDiario.SITUACAO_TRANCADO)
                            .exists()
                            or tem_mdr
                            and MatriculaDiarioResumida.objects.filter(matricula_periodo_id=mp_id)
                            .exclude(situacao=MatriculaDiario.SITUACAO_TRANCADO)
                            .exists()
                            or tem_md
                            and MatriculaDiario.objects.filter(matricula_periodo_id=mp_id)
                            .exclude(situacao=MatriculaDiario.SITUACAO_TRANCADO)
                            .exists()
                        ):
                            diarios_trancados = False
                        if diarios_trancados:
                            continue
                        else:
                            situacao = None

                    # verifica se aluno cancelado está sem diários ou com todos os diários cancelados
                    elif mp_situacao_id in [SituacaoMatriculaPeriodo.CANCELADA, SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO]:
                        if not tem_rh and not tem_mdr and not tem_md:
                            continue
                        diarios_cancelados = True
                        if (
                            tem_rh
                            and RegistroHistorico.objects.filter(matricula_periodo_id=mp_id)
                            .exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO)
                            .exists()
                            or tem_mdr
                            and MatriculaDiarioResumida.objects.filter(matricula_periodo_id=mp_id)
                            .exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO)
                            .exists()
                            or tem_md
                            and MatriculaDiario.objects.filter(matricula_periodo_id=mp_id)
                            .exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO)
                            .exists()
                        ):
                            diarios_cancelados = False
                        if diarios_cancelados:
                            continue
                        else:
                            situacao = None

                    # verifica se aluno com matícula vinculo ou em aberto tem algum diário
                    elif mp_situacao_id in [
                        SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                        SituacaoMatriculaPeriodo.EM_ABERTO,
                        SituacaoMatriculaPeriodo.EVASAO,
                    ]:
                        if not tem_rh and not tem_mdr and not tem_md:
                            continue
                        else:
                            situacao = None

                    # verifica cursos de avaliação FIC
                    if estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_FIC:
                        if tem_rh:
                            if RegistroHistorico.objects.filter(matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
                                situacao = SituacaoMatriculaPeriodo.MATRICULADO
                            elif RegistroHistorico.objects.filter(
                                matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA
                            ).exists():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA
                            elif RegistroHistorico.objects.filter(matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_REPROVADO).exists():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO
                            elif (
                                RegistroHistorico.objects.filter(matricula_periodo_id=mp_id)
                                .exclude(situacao=MatriculaDiario.SITUACAO_APROVADO)
                                .exists()
                            ):
                                situacao = SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA

                        if situacao == SituacaoMatriculaPeriodo.APROVADO and tem_mdr:
                            if MatriculaDiarioResumida.objects.filter(
                                matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_CURSANDO
                            ).exists():
                                situacao = SituacaoMatriculaPeriodo.MATRICULADO
                            elif MatriculaDiarioResumida.objects.filter(
                                matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA
                            ).exists():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA
                            elif MatriculaDiarioResumida.objects.filter(
                                matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_REPROVADO
                            ).exists():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO
                            elif (
                                MatriculaDiarioResumida.objects.filter(matricula_periodo_id=mp_id)
                                .exclude(situacao=MatriculaDiario.SITUACAO_APROVADO)
                                .exists()
                            ):
                                situacao = SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA

                        if situacao == SituacaoMatriculaPeriodo.APROVADO and tem_md:
                            if MatriculaDiario.objects.filter(matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
                                situacao = SituacaoMatriculaPeriodo.MATRICULADO
                            elif MatriculaDiario.objects.filter(
                                matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA
                            ).exists():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA
                            elif MatriculaDiario.objects.filter(matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_REPROVADO).exists():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO
                            elif (
                                MatriculaDiario.objects.filter(matricula_periodo_id=mp_id)
                                .exclude(situacao=MatriculaDiario.SITUACAO_APROVADO)
                                .exists()
                            ):
                                situacao = SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA

                    # verifica cursos de avaliação SERIADO e MODULAR (situações verificadas: APROVADO, REPROVADO e DEPENDENCIA)
                    elif estrutura.tipo_avaliacao in [EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR]:
                        # verifica se aluno com reprovação ficou em dependencia ou reprovado
                        reprovacoes_rh = RegistroHistorico.objects.filter(
                            matricula_periodo_id=mp_id,
                            situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
                        ).count()
                        reprovacoes_mdr = MatriculaDiarioResumida.objects.filter(
                            matricula_periodo_id=mp_id,
                            situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
                        ).count()
                        reprovacoes_md = MatriculaDiario.objects.filter(
                            matricula_periodo_id=mp_id,
                            situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
                        ).count()
                        qtd_reprovacoes = reprovacoes_rh + reprovacoes_mdr + reprovacoes_md
                        if qtd_reprovacoes > estrutura.limite_reprovacao:
                            situacao = SituacaoMatriculaPeriodo.REPROVADO
                        elif 0 < qtd_reprovacoes <= estrutura.limite_reprovacao:
                            situacao = SituacaoMatriculaPeriodo.DEPENDENCIA

                    # verifica cursos de avaliação CREDITO (situações verificadas: PERIODO FECHADO e FECHADO COM PENDENCIA)
                    elif estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
                        situacao = SituacaoMatriculaPeriodo.PERIODO_FECHADO
                        if tem_rh:
                            if RegistroHistorico.objects.filter(matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_PENDENTE).exists():
                                situacao = SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA
                        if situacao == SituacaoMatriculaPeriodo.PERIODO_FECHADO and tem_mdr:
                            if MatriculaDiarioResumida.objects.filter(
                                matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_PENDENTE
                            ).exists():
                                situacao = SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA
                        if situacao == SituacaoMatriculaPeriodo.PERIODO_FECHADO and tem_md:
                            if MatriculaDiario.objects.filter(matricula_periodo_id=mp_id, situacao=MatriculaDiario.SITUACAO_PENDENTE).exists():
                                situacao = SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA

                    # verifica reprovação por falta
                    mp1 = None
                    if not estrutura.reprovacao_por_falta_disciplina:
                        situacoes_inativas = [
                            MatriculaDiario.SITUACAO_CANCELADO,
                            MatriculaDiario.SITUACAO_DISPENSADO,
                            MatriculaDiario.SITUACAO_TRANCADO,
                            MatriculaDiario.SITUACAO_TRANSFERIDO,
                        ]
                        percentual_exigido = estrutura.percentual_frequencia
                        if tem_rh:
                            ch_total = 0
                            ch_frequencia = 0
                            for rh in (
                                RegistroHistorico.objects.filter(matricula_periodo_id=mp_id)
                                .exclude(situacao__in=situacoes_inativas)
                                .values('frequencia', 'componente__ch_hora_relogio')
                            ):
                                frequencia_aluno = rh['frequencia'] or 0
                                ch_disciplina = rh['componente__ch_hora_relogio'] or 0
                                ch_frequencia += frequencia_aluno * ch_disciplina / 100
                                ch_total += ch_disciplina

                            if ch_total and ch_frequencia / ch_total * 100 < percentual_exigido:
                                situacao = SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA

                        if tem_mdr:
                            ch_total = 0
                            ch_frequencia = 0
                            for rh in (
                                MatriculaDiarioResumida.objects.filter(matricula_periodo_id=mp_id)
                                .exclude(situacao__in=situacoes_inativas)
                                .values('frequencia', 'equivalencia_componente__carga_horaria')
                            ):
                                frequencia_aluno = rh['frequencia'] or 0
                                ch_disciplina = rh['equivalencia_componente__carga_horaria'] or 0
                                ch_frequencia += rh['frequencia'] * ch_disciplina / 100
                                ch_total += ch_disciplina

                            if ch_total and ch_frequencia / ch_total * 100 < percentual_exigido:
                                situacao = SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA

                        if tem_md:
                            mp1 = MatriculaPeriodo.objects.get(id=mp_id)
                            if mp1.get_percentual_carga_horaria_frequentada() < mp1.get_percentual_frequencia_minimo():
                                situacao = SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA

                    if situacao != mp_situacao_id:
                        # [matrícula período inconsistente, situação calculada, aplica correção automatica]
                        mp2 = mp1 or MatriculaPeriodo.objects.get(id=mp_id)
                        if situacao is None:
                            inconsistencias.append([mp2, 'Situação não calculada', False])
                        else:
                            inconsistencias.append([mp2, SituacaoMatriculaPeriodo.objects.get(id=situacao), True])

            elif tipo == '2':
                menor_periodo_pendente = aluno.calcular_periodo_referencia()

                if menor_periodo_pendente is None:
                    inconsistencias.append([aluno, 'Período não calculado', False])
                if aluno.periodo_atual != menor_periodo_pendente:
                    inconsistencias.append([aluno, menor_periodo_pendente, True])

            elif tipo == '2b':
                for periodo_letivo, periodo_atual, periodo_esperado, id_periodo_letivo in aluno.verificar_periodo_referencia_em_periodos_letivos():
                    inconsistencias.append([aluno, periodo_letivo, periodo_atual, periodo_esperado, id_periodo_letivo, True])

            elif tipo == '3':
                if aluno.situacao_id not in (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO):
                    ano = datetime.date.today().year
                    if not aluno.matriculaperiodo_set.filter(ano_letivo__ano=ano).exists():
                        inconsistencias.append([aluno, 'Matrícula em período inexistente no ano {ano}', True])

            elif tipo == '4':
                ultima_mp = aluno.matriculaperiodo_set.order_by('ano_letivo__ano', 'periodo_letivo').last()
                if ultima_mp:
                    mp_situacao_id = ultima_mp.situacao_id
                    if mp_situacao_id == SituacaoMatriculaPeriodo.EVASAO and aluno.situacao_id != SituacaoMatricula.EVASAO:
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.EVASAO), True])
                    elif mp_situacao_id == SituacaoMatriculaPeriodo.JUBILADO and aluno.situacao_id != SituacaoMatricula.JUBILADO:
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.JUBILADO), True])
                    elif mp_situacao_id == SituacaoMatriculaPeriodo.CANCELADA and aluno.situacao_id != SituacaoMatricula.CANCELADO:
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.CANCELADO), True])
                    elif (
                        mp_situacao_id == SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO
                        and aluno.situacao_id != SituacaoMatricula.CANCELAMENTO_COMPULSORIO
                    ):
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.CANCELAMENTO_COMPULSORIO), True])
                    elif (
                        mp_situacao_id == SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO
                        and aluno.situacao_id != SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO
                    ):
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO), True])
                    elif (
                        mp_situacao_id == SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE
                        and aluno.situacao_id != SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE
                    ):
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE), True])
                    elif mp_situacao_id == SituacaoMatriculaPeriodo.TRANSF_CURSO and aluno.situacao_id != SituacaoMatricula.TRANSFERIDO_INTERNO:
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.TRANSFERIDO_INTERNO), True])
                    elif mp_situacao_id == SituacaoMatriculaPeriodo.TRANSF_EXTERNA and aluno.situacao_id != SituacaoMatricula.TRANSFERIDO_EXTERNO:
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.TRANSFERIDO_EXTERNO), True])
                    elif mp_situacao_id in [SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.EM_ABERTO] and aluno.situacao_id not in [
                        SituacaoMatricula.MATRICULADO,
                        SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                    ]:
                        inconsistencias.append([aluno, SituacaoMatricula.objects.get(id=SituacaoMatricula.MATRICULADO), False])
                    else:
                        continue
            if amostra and len(inconsistencias) > 9:
                break
        return inconsistencias


class ProcedimentoMatriculaManualForm(forms.ModelFormPlus):
    class Meta:
        model = ProcedimentoMatricula
        fields = 'tipo', 'situacao_matricula_anterior', 'matricula_periodo', 'motivo', 'processo', 'data'


class RelatorioRequerimentoForm(forms.FormPlus):
    diretoria = forms.ModelChoiceField(Diretoria.objects.none())
    tipo_relatorio = forms.ChoiceField(
        label='Tipo de Relatório', choices=[['aproveitamento_disciplina', 'Aproveitamento de Disciplinas Pendentes de Avaliação']]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals

    def processar(self):
        rows = [['ID', 'ALUNO', 'DISCIPLINA', 'AVALIADOR', 'CURSO', 'DIRETORIA']]
        diretoria = self.cleaned_data['diretoria']
        tipo_relatorio = self.cleaned_data['tipo_relatorio']
        if tipo_relatorio == 'aproveitamento_disciplina':
            qs = SolicitacaoAproveitamentoEstudo.objects.filter(
                requerimento__aluno__curso_campus__diretoria=diretoria, requerimento__situacao__isnull=False
            )
            qs = qs.filter(parecer__isnull=True) | qs.filter(parecer__apto=False)
            for s in qs.order_by('requerimento__aluno__curso_campus__diretoria'):
                rows.append(
                    [
                        s.requerimento.id,
                        s.requerimento.aluno,
                        s.componente_curricular,
                        s.avaliador,
                        s.requerimento.aluno.curso_campus,
                        s.requerimento.aluno.curso_campus.diretoria,
                    ]
                )
        return rows


class SolicitarReposicaoAtividadeForm(forms.FormPlus):
    item_configuracao_avaliacao = forms.ChoiceField(label='Atividade')

    def __init__(self, *args, **kwargs):
        self.abono = kwargs.pop('abono')
        super().__init__(*args, **kwargs)
        pks = (
            MatriculaDiario.objects.filter(matricula_periodo=self.abono.aluno.get_ultima_matricula_periodo())
            .filter(diario__configuracaoavaliacao__itemconfiguracaoavaliacao__data__isnull=True, notaavaliacao__nota__isnull=True)
            .values_list('diario__configuracaoavaliacao__itemconfiguracaoavaliacao', flat=True)
        )
        pks_ja_solicitados = SolicitacaoReposicaoAtividade.objects.filter(abono_faltas__aluno=self.abono.aluno).values_list(
            'item_configuracao_avaliacao_id', flat=True
        )
        itens = (
            ItemConfiguracaoAvaliacao.objects.filter(pk__in=pks)
            .exclude(pk__in=pks_ja_solicitados)
            .select_related('configuracao_avaliacao__diario__componente_curricular__componente')
            .order_by(
                'configuracao_avaliacao__diario__componente_curricular__componente__descricao_historico', 'configuracao_avaliacao__etapa', 'sigla'
            )
        )

        grouped_choices = [('', '--- Selecione uma atividade ---')]

        def key_func(i):
            return i.configuracao_avaliacao.diario.componente_curricular.componente.descricao_historico

        for disciplina, grupo in groupby(itens, key=key_func):
            opcoes_disciplina = [
                (
                    item.id,
                    f'{item.sigla} - {item.get_tipo_display()} ({item.configuracao_avaliacao.etapa}ª Etapa)',
                )
                for item in grupo
            ]
            grouped_choices.append((disciplina, opcoes_disciplina))

        self.fields['item_configuracao_avaliacao'].choices = grouped_choices

    def processar(self):
        item_configuracao_avaliacao_id = self.cleaned_data['item_configuracao_avaliacao']
        SolicitacaoReposicaoAtividade.objects.get_or_create(abono_faltas=self.abono, item_configuracao_avaliacao_id=item_configuracao_avaliacao_id)


class AvaliarSolicitacaoReposicaoAtividadeForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoReposicaoAtividade
        fields = 'deferida', 'data_reposicao', 'observacao'

    def clean_observacao(self):
        deferida = self.cleaned_data.get('deferida') if 'deferida' in self.fields else True
        observacao = self.cleaned_data.get('observacao')
        if not deferida and not observacao:
            raise forms.ValidationError('Informe o motivo do indeferimento.')
        return observacao

    def clean_data_reposicao(self):
        deferida = self.cleaned_data.get('deferida')
        data_reposicao = self.cleaned_data.get('data_reposicao')
        if deferida and not data_reposicao:
            raise forms.ValidationError('Informe a data da reposição.')
        return data_reposicao
