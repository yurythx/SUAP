import copy
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch
from django.db.models.aggregates import Max
from django.utils.safestring import mark_safe

from comum.models import Ano, Configuracao, Sala
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableRadioSelect,
    RenderableSelectMultiple,
)
from djtools.forms.widgets.radio import RadioInput
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import in_group
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    CalendarioAcademico,
    ComponenteCurricular,
    Diario,
    Diretoria,
    HorarioCampus,
    MatriculaDiario,
    MatriculaPeriodo,
    MatrizCurso,
    Polo,
    Turma,
    TurmaMinicurso,
    Turno,
)


class TurmaForm(forms.ModelFormPlus):
    codigo = forms.CharField(label='Código', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    descricao = forms.CharField(label='Descrição', widget=forms.Textarea(attrs={'readonly': 'readonly'}))
    sigla = forms.CharFieldPlus(label='Sigla', required=False)
    calendario_academico = forms.ModelChoiceField(queryset=CalendarioAcademico.locals, label='Calendário Acadêmico', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance.calendario_academico, 'uo'):
            self.fields['calendario_academico'].queryset = CalendarioAcademico.objects.filter(
                uo=self.instance.calendario_academico.uo, ano_letivo=self.instance.ano_letivo, periodo_letivo=self.instance.periodo_letivo
            )
            if self.instance.turno.pk != Turno.EAD:
                self.fields['polo'].widget = forms.Select(attrs={'readonly': 'readonly'})

    @transaction.atomic()
    def save(self, *args, **kwargs):
        turma = super().save(*args, **kwargs)
        for diario in turma.diario_set.all():
            if diario.quantidade_vagas != turma.quantidade_vagas:
                diario.quantidade_vagas = turma.quantidade_vagas
                diario.save()
        return turma

    class Meta:
        model = Turma
        exclude = ('ano_letivo', 'periodo_letivo', 'periodo_matriz', 'turno', 'curso_campus', 'matriz', 'sequencial', 'pertence_ao_plano_retomada')


class TransferirTurmaForm(FormWizardPlus):
    METHOD = 'POST'
    LAST_SUBMIT_LABEL = 'Transferir Alunos Selecionados'
    turma_destino = forms.ModelChoiceFieldPlus(None, label='Turma de Destino', widget=AutocompleteWidget(search_fields=Turma.SEARCH_FIELDS))
    confirmacao = forms.BooleanField(label='Confirmação', required=False, help_text='Marque a opção acima e clique no botão "Finalizar".')

    steps = ([('Turma de Destino', {'fields': ('turma_destino',)})], [('Confirmação dos Dados', {'fields': ('confirmacao',)})])

    def __init__(self, turma_origem, *args, **kwargs):
        self.turma_origem = turma_origem
        super().__init__(*args, **kwargs)

    def first_step(self):
        self.fields['turma_destino'].queryset = (
            Turma.locals.get_queryset()
            .filter(
                curso_campus=self.turma_origem.curso_campus,
                ano_letivo_id=self.turma_origem.ano_letivo_id,
                periodo_letivo=self.turma_origem.periodo_letivo,
                periodo_matriz=self.turma_origem.periodo_matriz,
            )
            .exclude(pk=self.turma_origem.pk)
        )


class DefinirLocalAulaTurmaForm(forms.FormPlus):
    sala = forms.ModelChoiceFieldPlus(Sala.ativas, required=False)
    todos_diarios = forms.BooleanField(
        label='Alterar já Definidos',
        help_text='Marque essa opção caso deseje que todos os diários dessa turma sejam alterados, incluse aqueles que já possuem sala definida.',
        required=False,
    )

    def __init__(self, turma, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turma = turma
        self.fields['sala'].queryset = Sala.ativas.filter(predio__uo_id=turma.calendario_academico.uo_id, laboratorio__isnull=True)

    def processar(self):
        qs_diarios = self.turma.diario_set.all()
        if not self.cleaned_data['todos_diarios']:
            qs_diarios = qs_diarios.filter(local_aula__isnull=True)
        qs_diarios.update(local_aula=self.cleaned_data['sala'])


class GerarTurmasFormMetaclass(type(FormWizardPlus)):
    def __new__(mcs, name, bases, attrs):
        cls = super().__new__(mcs, name, bases, attrs)
        for i in range(1, 13):
            field_qtd_periodo = f'qtd_periodo_{i}'
            cls.base_fields[field_qtd_periodo] = forms.ChoiceField(label='Nº de Turmas', required=False, choices=cls.QTD_TURMAS_CHOICES)
            field_turno_periodo = f'turno_periodo_{i}'
            cls.base_fields[field_turno_periodo] = forms.ModelChoiceField(
                label='Turno',
                queryset=Turno.objects.all(),
                required=False,
                empty_label=None,
                help_text='Formato: 20141.1.011004.1<strong>[M]</strong>',
            )
            field_vagas_periodo = f'vagas_periodo_{i}'
            cls.base_fields[field_vagas_periodo] = forms.IntegerField(label='Nº de Vagas', required=False, min_value=0)
        return cls


class GerarTurmasForm(FormWizardPlus, metaclass=GerarTurmasFormMetaclass):
    METHOD = 'GET'
    QTD_TURMAS_CHOICES = [[0, '0'], [1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5'], [6, '6'], [7, '7'], [8, '8'], [9, '9']]

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', help_text='Formato: <strong>[2014]</strong>1.1.011004.1.1M')
    periodo_letivo = forms.ChoiceField(
        label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES, help_text='Formato: 2014<strong>[1]</strong>.1.011004.1.1M'
    )
    tipo_componente = forms.ChoiceField(label='Tipo dos Componentes', choices=[[1, 'Obrigatório'], [0, 'Optativo']])
    matriz_curso = forms.ModelChoiceFieldPlus(
        MatrizCurso.objects,
        label='Matriz/Curso',
        help_text='Formato: 20141.1.<strong>[011004]</strong>.1.1M',
        widget=AutocompleteWidget(search_fields=MatrizCurso.SEARCH_FIELDS),
    )
    turno = forms.ModelChoiceField(Turno.objects)
    polos = forms.ModelMultiplePopupChoiceField(Polo.objects, label='Pólos', required=False, help_text='Apenas para cursos EAD')

    horario_campus = forms.ModelChoiceField(HorarioCampus.objects, label='Horário do Campus')
    calendario_academico = forms.ModelChoiceField(CalendarioAcademico.objects, label='Calendário Acadêmico')
    componentes = forms.MultipleModelChoiceField(
        ComponenteCurricular.objects, label='', widget=RenderableSelectMultiple('widgets/componentes_widget.html')
    )
    modulos = forms.MultipleChoiceField(
        label='Módulo', choices=ComponenteCurricular.TIPO_MODULO_CHOICES, widget=forms.CheckboxSelectMultiplePlus(), required=False
    )
    confirmacao = forms.BooleanField(
        label='Confirmação',
        required=True,
        help_text='Marque a opção acima e clique no botão "Finalizar" caso deseje que as turmas/diários identificados acima sejam criados.',
    )

    step_1 = [('Dados do Curso', {'fields': ('ano_letivo', 'periodo_letivo', 'tipo_componente', 'matriz_curso', 'polos')})]
    step_2 = [
        ('1º Período', {'fields': ('qtd_periodo_1', 'turno_periodo_1', 'vagas_periodo_1')}),
        ('2º Período', {'fields': ('qtd_periodo_2', 'turno_periodo_2', 'vagas_periodo_2')}),
        ('3º Período', {'fields': ('qtd_periodo_3', 'turno_periodo_3', 'vagas_periodo_3')}),
        ('4º Período', {'fields': ('qtd_periodo_4', 'turno_periodo_4', 'vagas_periodo_4')}),
        ('5º Período', {'fields': ('qtd_periodo_5', 'turno_periodo_5', 'vagas_periodo_5')}),
        ('6º Período', {'fields': ('qtd_periodo_6', 'turno_periodo_6', 'vagas_periodo_6')}),
        ('7º Período', {'fields': ('qtd_periodo_7', 'turno_periodo_7', 'vagas_periodo_7')}),
        ('8º Período', {'fields': ('qtd_periodo_8', 'turno_periodo_8', 'vagas_periodo_8')}),
        ('9º Período', {'fields': ('qtd_periodo_9', 'turno_periodo_9', 'vagas_periodo_9')}),
        ('10º Período', {'fields': ('qtd_periodo_10', 'turno_periodo_10', 'vagas_periodo_10')}),
        ('11º Período', {'fields': ('qtd_periodo_11', 'turno_periodo_11', 'vagas_periodo_11')}),
        ('12º Período', {'fields': ('qtd_periodo_12', 'turno_periodo_12', 'vagas_periodo_12')}),
    ]

    step_3 = [
        ('Horário/Calendário e Componentes', {'fields': ('horario_campus', 'calendario_academico')}),
        (
            'Seleção de Componentes',
            {
                'fields': (
                    'componentes',
                    'modulos',
                )
            },
        ),
    ]

    step_4 = [('Confirmação dos Dados', {'fields': ('confirmacao',)})]
    steps = (step_1, step_2, step_3, step_4)

    class Media:
        js = ('/static/edu/js/GerarTurmasForm.js',)

    def __init__(self, request, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        if not Configuracao.get_valor_por_chave('edu', 'permite_gerar_turma_polo'):
            self.fields['polos'].widget = forms.HiddenInput()

    def next_step(self):
        ano_letivo = self.get_entered_data('ano_letivo')
        periodo_letivo = self.get_entered_data('periodo_letivo')
        matriz_curso = self.get_entered_data('matriz_curso')

        if 'matriz_curso' in self.fields:
            self.fields['matriz_curso'].queryset = MatrizCurso.locals.filter(curso_campus__ativo=True, matriz__ativo=True)
        if 'horario_campus' in self.fields and matriz_curso:
            self.fields['horario_campus'].queryset = HorarioCampus.locals.filter(uo=matriz_curso.curso_campus.diretoria.setor.uo, ativo=True)
        if 'calendario_academico' in self.fields and matriz_curso and ano_letivo and periodo_letivo:
            qs_calendario_academico = CalendarioAcademico.locals.filter(
                uo=matriz_curso.curso_campus.diretoria.setor.uo,
                ano_letivo=ano_letivo,
                periodo_letivo=periodo_letivo,
                tipo=matriz_curso.curso_campus.periodicidade,
            )
            qs_calendario_academico = qs_calendario_academico.filter(diretoria__isnull=True) | qs_calendario_academico.filter(
                diretoria=matriz_curso.curso_campus.diretoria
            )
            self.fields['calendario_academico'].queryset = qs_calendario_academico
        if matriz_curso:
            if not matriz_curso.curso_campus.pode_ingressar_aluno():
                self.ALERT = 'Este curso encontra-se suspenso ou em processo de extinção. A oferta de turmas do primeiro período deve ocorrer apenas em casos de dependência.'

            for i in range(matriz_curso.matriz.qtd_periodos_letivos + 1, 13):
                if f'qtd_periodo_{i}' in self.fields:
                    self.fields[f'qtd_periodo_{i}'].required = False
                    self.fields[f'turno_periodo_{i}'].required = False
                    self.fields[f'vagas_periodo_{i}'].required = False
                    self.fields[f'qtd_periodo_{i}'].widget = forms.HiddenInput()
                    self.fields[f'turno_periodo_{i}'].widget = forms.HiddenInput()
                    self.fields[f'vagas_periodo_{i}'].widget = forms.HiddenInput()
        if 'componentes' in self.fields and matriz_curso:
            if matriz_curso.matriz.is_regime_modular():
                self.fields['componentes'].required = False
                self.fields['componentes'].widget = forms.HiddenInput()
                modulos_disponiveis = ComponenteCurricular.objects.filter(matriz=matriz_curso.matriz).values_list('tipo_modulo', flat=True).distinct()
                self.fields['modulos'].choices = [x for x in ComponenteCurricular.TIPO_MODULO_CHOICES if x[0] in modulos_disponiveis]

            else:
                self.fields['modulos'].required = False
                self.fields['modulos'].widget = forms.HiddenInput()

            periodos = []
            for i in range(1, matriz_curso.matriz.qtd_periodos_letivos + 1):
                if int(self.get_entered_data(f'qtd_periodo_{i}') or 0):
                    periodos.append(i)
            ids_componenentes_curriculares_associados = matriz_curso.matriz.componentecurricular_set.filter(
                componente_curricular_associado__isnull=False
            ).values_list('componente_curricular_associado', flat=True)
            qs = matriz_curso.matriz.componentecurricular_set.exclude(id__in=ids_componenentes_curriculares_associados)
            if int(self.get_entered_data('tipo_componente')) == 1:
                qs = qs.filter(periodo_letivo__in=periodos)
            else:
                qs = qs.filter(periodo_letivo__isnull=True)
            self.fields['componentes'].queryset = qs.order_by('periodo_letivo')

        if 'componentes' in self.cleaned_data:
            self.processar(False)

    def clean_matriz_curso(self):
        if not self.data.get('ano_letivo') or not self.data.get('periodo_letivo'):
            return forms.ValidationError(mark_safe('Matriz Curso inválida.'))
        matriz_curso = MatrizCurso.objects.get(id=self.data['matriz_curso'])
        is_secretario = in_group(self.request.user, 'Secretário Acadêmico, Administrador Acadêmico')
        if not is_secretario:
            if not matriz_curso.curso_campus.is_coordenador(self.request.user):
                raise forms.ValidationError('Coordenadores só podem gerar turmas para os cursos sob sua coordenação')
        if not (matriz_curso.curso_campus.diretoria.setor.uo.horariocampus_set.exists()):
            link = is_secretario and '<a href="/admin/edu/horariocampus/add/">Adicione um novo horário</a>' or ''
            raise forms.ValidationError(
                mark_safe(f'Não existe horário confirmado para o campus {matriz_curso.curso_campus.diretoria.setor.uo}. {link}')
            )
        if not (
            matriz_curso.curso_campus.diretoria.setor.uo.calendarioacademico_set.filter(
                ano_letivo__id=self.data['ano_letivo'], periodo_letivo=self.data['periodo_letivo']
            ).exists()
        ):
            link = is_secretario and '<a href="/admin/edu/calendarioacademico/add/">Adicione um novo calendário</a>' or ''
            raise forms.ValidationError(
                mark_safe(
                    f'Não existe calendário acadêmico para o campus {matriz_curso.curso_campus.diretoria.setor.uo} no período/ano informado. {link}'
                )
            )
        return matriz_curso

    def clean_calendario_academico(self):
        calendario_academico = self.cleaned_data['calendario_academico']
        matriz_curso = self.cleaned_data['matriz_curso']
        if calendario_academico:
            qtd_avaliacoes = matriz_curso.matriz.componentecurricular_set.all().aggregate(Max('qtd_avaliacoes')).get('qtd_avaliacoes__max') or 0
            if calendario_academico.qtd_etapas < qtd_avaliacoes:
                raise ValidationError(
                    f'A matriz possui componentes com {qtd_avaliacoes} etapas, mas o calendário selecionado possui apenas {calendario_academico.qtd_etapas}.'
                )
        return calendario_academico

    def processar(self, commit=True):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        matriz_curso = self.cleaned_data['matriz_curso']
        polos = self.cleaned_data.get('polos') or [None]
        numero_turmas_dict = {}
        turnos_dict = {}
        numero_vagas_dict = {}
        for i in range(1, matriz_curso.matriz.qtd_periodos_letivos + 1):
            numero_turmas_dict[i] = int(self.cleaned_data[f'qtd_periodo_{i}'] or 0)
            turnos_dict[i] = self.cleaned_data[f'turno_periodo_{i}'] or None
            numero_vagas_dict[i] = self.cleaned_data[f'vagas_periodo_{i}'] or 0
        horario_campus = self.cleaned_data['horario_campus']
        calendario_academico = self.cleaned_data['calendario_academico']
        pertence_ao_plano_retomada = False
        if matriz_curso.matriz.is_regime_modular():
            componentes = ComponenteCurricular.objects.filter(matriz=matriz_curso.matriz, tipo_modulo__in=self.cleaned_data['modulos']).order_by(
                'tipo_modulo'
            )
        else:
            componentes = self.cleaned_data['componentes']

        confirmacao = self.cleaned_data.get('confirmacao')
        commit = commit and confirmacao
        self.turmas = []
        for polo in polos:
            self.turmas.extend(
                Turma.gerar_turmas(
                    ano_letivo,
                    periodo_letivo,
                    turnos_dict,
                    numero_vagas_dict,
                    numero_turmas_dict,
                    matriz_curso.curso_campus,
                    matriz_curso.matriz,
                    horario_campus,
                    calendario_academico,
                    componentes,
                    pertence_ao_plano_retomada,
                    polo,
                    commit,
                )
            )


class TurmasRadioSelect(RenderableRadioSelect):
    def __init__(self, aluno: Aluno | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__('widgets/turmas_widget.html', *args, **kwargs)
        self.aluno = aluno

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = forms.RadioSelect.get_context(self, name, value, attrs)
        context['aluno'] = self.aluno
        objects = []
        base_attrs = attrs.copy() if attrs else {}
        for obj in self.choices.queryset.all():
            item_attrs = base_attrs.copy()
            item_attrs['id'] = f'{base_attrs.get("id", name)}_{obj.id}'
            if str(value) == str(obj.id):
                obj.checked_ = True
                item_attrs.update(checked='checked')
            widget = RadioInput(item_attrs)
            obj.input_id = item_attrs['id']
            obj.widget = widget.render(name, obj.id, item_attrs)
            objects.append(obj)
        context['objects'] = objects
        return context


class EfetuarMatriculaTurmaForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Matricular na turma'

    turma = forms.ModelChoiceField(Turma.objects, required=False, label='Turma', widget=TurmasRadioSelect())

    fieldsets = (
        (
            'Seleção da turma',
            {
                'fields': ('turma',),
            },
        ),
    )

    def __init__(self, aluno: Aluno, *args: Any, **kwargs: Any) -> None:
        self.aluno = aluno
        super().__init__(*args, **kwargs)
        self.fields['turma'].queryset = (
            Turma.locals.filter(
                ano_letivo=self.aluno.ano_letivo,
                periodo_letivo=self.aluno.periodo_letivo,
                turno=self.aluno.turno,
                curso_campus=self.aluno.curso_campus,
                matriz=self.aluno.matriz,
            )
            .select_related('turno', 'ano_letivo')
            .prefetch_related(
                Prefetch(
                    'diario_set',
                    queryset=Diario.objects.select_related('componente_curricular__componente').order_by(
                        'componente_curricular__componente__descricao'
                    ),
                )
            )
            .annotate(total_matriculados=Count('matriculaperiodo', distinct=True))
            .order_by('periodo_matriz', 'descricao', 'codigo')
        )
        if isinstance(self.fields['turma'].widget, TurmasRadioSelect):
            self.fields['turma'].widget.aluno = aluno

    def clean_turma(self) -> Turma:
        turma = self.cleaned_data.get('turma')
        if not turma:
            raise forms.ValidationError('Você deve selecionar uma turma.')
        return turma

    @transaction.atomic
    def processar(self, aluno: Aluno) -> MatriculaPeriodo:
        matricula_periodo = (
            MatriculaPeriodo.objects.filter(aluno=aluno, ano_letivo=self.aluno.ano_letivo, periodo_letivo=self.aluno.periodo_letivo).first()
            or MatriculaPeriodo.objects.filter(aluno=aluno).last()
        )
        if not matricula_periodo:
            raise forms.ValidationError('Matrícula no período não encontrada para o aluno.')

        matricula_periodo.turma = self.cleaned_data['turma']
        matricula_periodo.save()

        for diario in matricula_periodo.turma.diario_set.all():
            if not MatriculaDiario.objects.filter(diario=diario, matricula_periodo=matricula_periodo).exists():
                matricula_diario = MatriculaDiario()
                matricula_diario.matricula_periodo = matricula_periodo
                matricula_diario.diario = diario
                matricula_diario.save()

        return matricula_periodo


class AdicionarAlunosTurmaMinicursoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar alunos'
    turmas = forms.MultipleModelChoiceField(TurmaMinicurso.objects.none(), label='Turmas')

    def __init__(self, turma, *args, **kwargs):
        self.turma = turma
        super().__init__(*args, **kwargs)
        self.fields['turmas'].queryset = TurmaMinicurso.objects.filter(
            ano_letivo=turma.ano_letivo, periodo_letivo=turma.periodo_letivo, minicurso__diretoria=turma.curso_campus.diretoria
        )

    def processar(self):
        erros = []
        turmas_minicurso = self.cleaned_data['turmas']
        matriculas_periodo = self.turma.matriculaperiodo_set.filter(pk__in=self.request.GET['pks'].split('_'))
        for turma_minicurso in turmas_minicurso:
            for matricula_periodo in matriculas_periodo:
                try:
                    turma_minicurso.adicionar_novo_aluno(matricula_periodo.aluno.pessoa_fisica, matricula_periodo_origem=matricula_periodo)
                except ValidationError as e:
                    erros.append(e.message)
                    continue
        return erros


class EfetuarMatriculasTurmaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Matricular Selecionados'
    matricula_periodo = forms.MultipleModelChoiceField(
        MatriculaPeriodo.objects, label='', widget=RenderableSelectMultiple('widgets/matriculas_periodo_widget.html')
    )

    def __init__(self, turma, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turma = turma
        self.fields['matricula_periodo'].queryset = MatriculaPeriodo.objects.filter(
            aluno__curso_campus=turma.curso_campus, periodo_letivo=turma.periodo_letivo, ano_letivo=turma.ano_letivo
        )

    def processar(self, commit=True):
        for matricula_periodo in self.cleaned_data['matricula_periodo']:
            matricula_periodo.turma = self.turma
            matricula_periodo.save()
            for diario in self.turma.diario_set.all():
                if not MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=diario).exists():
                    matricula_diario = MatriculaDiario()
                    matricula_diario.matricula_periodo = matricula_periodo
                    matricula_diario.diario = diario
                    matricula_diario.save()


class GerarDiarioForm(forms.FormPlus):
    diarios = forms.MultipleModelChoiceField(Diario.objects, label='', widget=RenderableSelectMultiple('widgets/diarios_widget.html'))

    def __init__(self, *args, **kwargs):
        turma = kwargs.pop('turma')
        super().__init__(*args, **kwargs)
        self.fields['diarios'].queryset = turma.diario_set.filter(
            calendario_academico__qtd_etapas=4, componente_curricular__qtd_avaliacoes=2, segundo_semestre=False, possui_segunda_oferta=False
        )

    def processar(self):
        for diario in self.cleaned_data['diarios']:
            novo_diario = copy.copy(diario)
            novo_diario.id = None
            novo_diario.situacao = Diario.SITUACAO_ABERTO
            novo_diario.local_aula = None
            novo_diario.segundo_semestre = True
            novo_diario.integracao_com_moodle = False
            novo_diario.url_moodle = None
            novo_diario.url_ambiente_virtual = None
            novo_diario.posse_etapa_1 = Diario.POSSE_PROFESSOR
            novo_diario.posse_etapa_2 = Diario.POSSE_PROFESSOR
            novo_diario.posse_etapa_3 = Diario.POSSE_PROFESSOR
            novo_diario.posse_etapa_4 = Diario.POSSE_PROFESSOR
            novo_diario.posse_etapa_5 = Diario.POSSE_PROFESSOR
            novo_diario.entregue_fisicamente = None
            novo_diario.diario_primeira_oferta_id = diario.id
            novo_diario.save()
            novo_diario.locais_aula_secundarios.clear()
            diario.possui_segunda_oferta = True
            diario.save()


class ImprimirHorariosForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=True)
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, label='Período Letivo', required=True)

    diretoria = forms.ModelChoiceFieldPlus(
        Diretoria.objects.none(), required=True, label='Diretoria Acadêmica', widget=AutocompleteWidget(search_fields=Diretoria.SEARCH_FIELDS)
    )

    turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[('ano_letivo', 'ano_letivo'), ('periodo_letivo', 'periodo_letivo'), ('diretoria', 'curso_campus__diretoria')],
        ),
    )

    fieldsets = (
        (
            'Filtros',
            {
                'fields': (
                    ('ano_letivo', 'periodo_letivo'),
                    'diretoria',
                    'turma',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        diretoria = self.cleaned_data['diretoria']
        turma = self.cleaned_data['turma']
        qs = Turma.objects.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, curso_campus__diretoria=diretoria)
        if turma:
            qs = qs.filter(pk=turma.pk)
        return qs


class MapaTurmaForm(forms.Form):
    diarios = forms.MultipleModelChoiceField(Diario.objects, label='', widget=RenderableSelectMultiple('widgets/diarios_widget.html'))

    def __init__(self, diarios, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diarios'].queryset = diarios.order_by('componente_curricular__componente__sigla', 'id')


class EstatisticaTurmaForm(forms.Form):
    SUBMIT_LABEL = 'Exibir Estatística'

    etapas = forms.MultipleChoiceField(
        choices=[[1, '1ª Etapa'], [2, '2ª Etapa'], [3, '3ª Etapa'], [4, '4ª Etapa'], [5, 'Final']],
        label='',
        widget=forms.CheckboxSelectMultiplePlus(),
    )
    diarios = forms.MultipleModelChoiceField(Diario.objects.none(), label='', widget=forms.CheckboxSelectMultiplePlus())
    abreviar = forms.BooleanField(
        label='Abreviar', help_text='Exibir "sigla" do componente ao invés da descrição completa do diário.', required=False
    )

    fieldsets = (('Etapas', {'fields': ('etapas',)}), ('Diários', {'fields': ('diarios',)}), ('Exibição', {'fields': ('abreviar',)}))
