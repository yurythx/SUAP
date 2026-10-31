from datetime import datetime

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import (
    ComponenteForm,
    ConteudoMinicursoFormset,
    CursoCampusForm,
    EquivalenciaComponenteQAcademicoForm,
    EstruturaCursoForm,
    MatrizForm,
    MinicursoForm,
    RotuloModuloForm,
)
from edu.models import (
    AtoRegulatorioCurso,
    Componente,
    ConteudoMinicurso,
    CursoCampus,
    Diretoria,
    EquivalenciaComponenteQAcademico,
    EstruturaCurso,
    Habilitacao,
    Matriz,
    Minicurso,
    Modalidade,
    NivelEnsino,
    RepresentacaoConceitual,
    RotuloModulo,
    SituacaoMatricula,
)


class ComponenteAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'sigla',
        'descricao',
        'nivel_ensino',
        'grupo_atuacao',
        'get_ch_hora_relogio',
        'get_ch_hora_aula',
        'ch_qtd_creditos',
        'ativo',
        'sigla_qacademico',
        'observacao',
    )
    list_filter = (CustomTabListFilter, 'ativo', 'tipo', 'nivel_ensino', 'matriz', 'grupo_atuacao')
    list_filter_multiple_choices = ('tipo',)
    search_fields = ('id', 'sigla', 'descricao', 'observacao', 'sigla_qacademico')
    list_display_icons = True
    export_to_xls = True
    list_per_page = 15
    form = ComponenteForm

    def get_fieldsets(self, request, obj=None):
        fieldsets = []
        if obj and obj.get_planodisciplina():
            fieldsets.append(('Dados gerais', {'fields': ('abreviatura', 'ativo')}))
            fieldsets.append(('Dados Extras', {'fields': ('grupo_atuacao',)}))
        else:
            fieldsets.append(
                ('Dados gerais', {'fields': ('descricao', 'descricao_historico', 'abreviatura', 'tipo', 'diretoria', 'nivel_ensino', 'ativo')})
            )
            if settings.COMPONENTE_CH_DECIMAL:
                fieldsets.append(('Carga Horária', {'fields': ('ch_hora_relogio_decimal', 'ch_hora_aula', 'ch_qtd_creditos')}))
            else:
                fieldsets.append(('Carga Horária', {'fields': ('ch_hora_relogio', 'ch_hora_aula', 'ch_qtd_creditos')}))
            fieldsets.append(
                (
                    'Dados Extras',
                    {
                        'fields': (
                            'grupo_atuacao',
                            'observacao',
                        )
                    },
                ),
            )
        return fieldsets

    def get_ch_hora_relogio(self, obj):
        return obj.get_ch_hora_relogio()

    get_ch_hora_relogio.short_description = 'Hora/relógio'

    def get_ch_hora_aula(self, obj):
        return obj.get_ch_hora_aula()

    get_ch_hora_aula.short_description = 'Hora/aula'

    def get_tabs(self, request):
        return ['utilizados', 'nao_utilizados']

    def utilizados(self, request, queryset):
        qs_componente_curricular = queryset.filter(componentecurricular__id__isnull=False)
        qs_equivalente = queryset.filter(equivalenciacomponenteqacademico__id__isnull=False)
        qs_registro = queryset.filter(registrohistorico__id__isnull=False)
        return (qs_componente_curricular | qs_equivalente | qs_registro).distinct()

    utilizados.short_description = 'Utilizados'

    def nao_utilizados(self, request, queryset):
        qs_componente_curricular = queryset.filter(componentecurricular__id__isnull=False)
        qs_equivalente = queryset.filter(equivalenciacomponenteqacademico__id__isnull=False)
        qs_registro = queryset.filter(registrohistorico__id__isnull=False)
        qs_vinculados = (qs_componente_curricular | qs_equivalente | qs_registro).distinct()
        return queryset.exclude(id__in=qs_vinculados.values_list('id', flat=True))

    nao_utilizados.short_description = 'Não Utilizados'


admin.site.register(Componente, ComponenteAdmin)


class RepresentacaoConceitualInline(admin.TabularInline):
    model = RepresentacaoConceitual
    extra = 3


class EstruturaCursoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao', 'ativo')
    list_filter = (
        'tipo_avaliacao',
        'ativo',
    )
    list_display_icons = True
    search_fields = ('descricao',)
    form = EstruturaCursoForm
    inlines = [RepresentacaoConceitualInline]
    export_to_xls = True

    fieldsets = (
        ('Dados gerais', {'fields': ('descricao', 'ativo')}),
        (
            'Critérios de apuração de resultados por período',
            {
                'fields': (
                    'tipo_avaliacao',
                    'qtd_minima_disciplinas',
                    'numero_disciplinas_superior_periodo',
                    'limite_reprovacao',
                    'componente_sem_periodo',
                    'reprova_todas_disciplinas',
                    'qtd_max_periodos_subsequentes',
                    'numero_max_cancelamento_disciplina',
                    'ch_minima_disciplinas',
                    'ch_maxima_disciplinas',
                    'proitec',
                )
            },
        ),
        (
            'Critérios de avaliação por disciplinas',
            {
                'fields': (
                    'criterio_avaliacao',
                    'media_aprovacao_sem_prova_final',
                    'media_evitar_reprovacao_direta',
                    'media_aprovacao_avaliacao_final',
                    'conceito_minimo_aprovacao',
                )
            },
        ),
        (
            'Critérios de apuração de frequência ',
            {
                'fields': (
                    ('percentual_frequencia', 'reprovacao_por_falta_disciplina'),
                    ('exibe_frequencia_global', 'limitar_ch_por_tipo_aula'),
                )
            },
        ),
        (
            'Critérios de jubilamento',
            {'fields': ('qtd_periodos_conclusao', 'qtd_max_reprovacoes_periodo', 'qtd_max_reprovacoes_disciplina', 'fator_acrescimo_periodo_letivo')},
        ),
        (
            'Critérios de trancamento',
            {
                'fields': (
                    'qtd_trancamento_voluntario',
                    'exige_periodo_ingresso_integralizado',
                )
            },
        ),
        ('Critérios de cancelamento', {'fields': ('requer_declaracao_para_cancelamento_matricula',)}),
        ('Critérios de matrícula', {'fields': (('numero_min_alunos_diario', 'numero_max_alunos_especiais'))}),
        ('Índice de rendimento acadêmico (IRA)', {'fields': ('ira',)}),
        ('Fechamento de período', {'fields': ('permite_fechamento_com_pendencia',)}),
        (
            'Configurações de diário',
            {
                'fields': (
                    'pode_entregar_etapa_sem_aula',
                    'pode_lancar_nota_fora_do_prazo',
                    'pode_lancar_aula_fora_do_prazo',
                    'permite_recuperacao_etapa',
                    'calculo_media_final',
                )
            },
        ),
        (
            'Aproveitamento de disciplinas',
            {
                'fields': (
                    ('quantidade_max_creditos_aproveitamento', 'percentual_max_aproveitamento'),
                    ('numero_max_certificacoes', 'media_certificacao_conhecimento'),
                    'formas_ingresso_ignoradas_aproveitamento',
                    'permite_registro_mobilidade_academica',
                )
            },
        ),
        ('Plano de estudo', {'fields': ('plano_estudo',)}),
        ('Plano de ensino', {'fields': ('exige_plano_ensino_submetido',)}),
    )


admin.site.register(EstruturaCurso, EstruturaCursoAdmin)


class HabilitacaoAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    list_display_icons = True
    search_fields = ('descricao',)
    ordering = ('descricao',)

    fieldsets = (('Dados gerais', {'fields': ('descricao',)}),)


admin.site.register(Habilitacao, HabilitacaoAdmin)


class CursoCampusAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao', 'ativo', 'modalidade', 'get_diretoria', 'get_matrizes', 'get_coordenadores')
    list_filter = (
        CustomTabListFilter,
        'ativo',
        'ano_letivo',
        'modalidade',
        'diretoria__setor__uo',
        'diretoria',
        'assinatura_eletronica',
        'assinatura_digital',
        'suspenso',
        'em_extincao',
        'extinto',
    )
    list_display_icons = True
    exclude = ('codigo_academico',)
    search_fields = ('descricao', 'codigo', 'codigo_academico', 'diretoria__setor__uo__sigla')
    list_per_page = 15
    export_to_xls = True
    list_xls_display = (
        'id',
        'descricao',
        'descricao_historico',
        'codigo_censup',
        'codigo_emec',
        'codigo_sistec',
        'codigo_educacenso',
        'ano_letivo',
        'periodo_letivo',
        'data_inicio',
        'data_funcionamento',
        'data_fim',
        'ativo',
        'quantidade_vagas',
        'possui_aluno_cursando',
        'codigo',
        'modalidade',
        'are_curso_formacao_superior',
        'area',
        'eixo',
        'curso_tecnico',
        'area_capes',
        'periodicidade',
        'exige_enade',
        'exige_colacao_grau',
        'emite_diploma',
        'area_concentracao',
        'programa',
        'diretoria',
        'extensao',
        'coordenador',
        'numero_portaria_coordenador',
        'coordenador_2',
        'numero_portaria_coordenador_2',
        'titulo_certificado_masculino',
        'titulo_certificado_feminino',
        'get_matrizes',
    )
    show_count_on_tabs = True

    form = CursoCampusForm

    fieldsets = (
        (
            'Identificação',
            {
                'fields': (
                    ('descricao',),
                    ('descricao_historico',),
                    ('mesmo_curso',),
                    ('codigo_censup', 'codigo_emec'),
                    ('codigo_sistec', 'codigo_educacenso'),
                    ('ciencia_sem_fronteira', 'formacao_de_professores'),
                )
            },
        ),
        (
            'Dados de funcionamento',
            {'fields': (('data_inicio', 'data_funcionamento'), ('ano_letivo', 'periodo_letivo'), ('quantidade_vagas', 'ativo'))},
        ),
        ('Coordenação', {'fields': ('coordenador', 'numero_portaria_coordenador', 'coordenador_2', 'numero_portaria_coordenador_2')}),
        (
            'Dados gerais',
            {
                'fields': (
                    'codigo',
                    'modalidade',
                    'area_curso_formacao_superior',
                    'area',
                    'eixo',
                    'curso_tecnico',
                    'area_capes',
                    'periodicidade',
                    'diretoria',
                    (
                        'exige_colacao_grau',
                        'plano_ensino',
                    ),
                    ('emite_diploma', 'assinatura_eletronica', 'assinatura_digital'),
                    'area_concentracao',
                    'programa',
                    'fator_esforco_curso',
                )
            },
        ),
        (
            'ENADE',
            {
                'fields': (
                    'exige_enade',
                    'justificativa_dispensa_ingressante',
                )
            },
        ),
        ('Título do certificado de conclusão', {'fields': ('titulo_certificado_masculino', 'titulo_certificado_feminino')}),
    )

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.GET.get('tab') in ['tab_migrados', 'tab_integralizados']:
            list_display = [*list(list_display), 'codigo_academico']
        return list_display

    def get_matrizes(self, obj):
        if hasattr(obj, 'export_to_xls'):
            return ', '.join([str(f'{matriz} - {matriz.get_ch_total()} horas') for matriz in obj.matrizes.all()])
        lista = ['<ul>']
        for matriz in obj.matrizes.all():
            lista.append('<li> ')
            lista.append(f'<a href="/edu/matriz/{matriz.pk}/">{matriz.descricao!s}</a>')
            lista.append('</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_matrizes.short_description = 'Matrizes'

    def get_diretoria(self, obj):
        if not obj.diretoria:
            if self.request.user.has_perm('edu.add_matriz'):
                return mark_safe(f'<a href="/edu/inserir_diretoria_curso/{obj.pk}/" class="btn popup">Definir Diretoria</a>')
            else:
                return '(Nenhum)'
        return mark_safe(str(obj.diretoria))

    get_diretoria.short_description = 'Diretoria'

    def get_coordenadores(self, obj):
        return obj.get_coordenadores_html(detalhado=False) if obj else '-'

    get_coordenadores.short_description = 'Coordenadores'

    def get_queryset(self, request):
        return CursoCampus.locals.exclude(modalidade_id=Modalidade.FIC_MENOS)

    def get_tabs(self, request):
        return [
            'tab_com_coordenadores',
            'com_matriz',
            'tab_sem_coordenadores',
            'nao_vinculados_diretoria',
            'tab_sob_minha_coordenacao',
            'sem_censup',
            'sem_emec',
            'sem_sistec',
            'sem_educacenso',
            'sem_alunos',
            'sem_autorizacao',
            'sem_criacao',
            'sem_processo_emec',
            'sem_reconhecimento',
            'sem_data_funcionamento',
            'vagas_pendentes',
            'tab_migrados',
            'tab_integralizados',
        ]

    def tab_com_coordenadores(self, request, queryset):
        return queryset.com_coordenadores()

    tab_com_coordenadores.short_description = 'Com coordenadores'

    def tab_sem_coordenadores(self, request, queryset):
        return queryset.sem_coordenadores()

    tab_sem_coordenadores.short_description = 'Sem coordenadores'

    def nao_vinculados_diretoria(self, request, queryset):
        return queryset.nao_vinculados_diretoria()

    nao_vinculados_diretoria.short_description = 'Não vinculados à diretoria'

    def tab_sob_minha_coordenacao(self, request, queryset):
        return queryset.sob_coordenacao_de(request.user.get_vinculo())

    tab_sob_minha_coordenacao.short_description = 'Sob minha coordenação'

    def tab_integralizados(self, request, queryset):
        return queryset.integralizados()

    tab_integralizados.short_description = 'Com alunos integralizados'

    def tab_migrados(self, request, queryset):
        return queryset.migrados()

    tab_migrados.short_description = 'Migrados'

    def sem_censup(self, request, queryset):
        return queryset.filter(modalidade__nivel_ensino_id=NivelEnsino.GRADUACAO, codigo_censup='', ativo=True).exclude(
            diretoria__tipo=Diretoria.TIPO_PRONATEC
        )

    sem_censup.short_description = 'Sem CENSUP'

    def sem_emec(self, request, queryset):
        return queryset.filter(modalidade_id__in=[Modalidade.ESPECIALIZACAO], codigo_emec='', ativo=True).exclude(
            diretoria__tipo=Diretoria.TIPO_PRONATEC
        )

    sem_emec.short_description = 'Sem e-MEC'

    def sem_sistec(self, request, queryset):
        return queryset.filter(codigo_sistec='', ativo=True).exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC).exclude(aluno__isnull=True)

    sem_sistec.short_description = 'Sem SISTEC'

    def sem_educacenso(self, request, queryset):
        qs = queryset.filter(codigo_educacenso__isnull=True, ativo=True).exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
        qs = qs.filter(modalidade__nivel_ensino_id=NivelEnsino.MEDIO) | qs.filter(modalidade_id=Modalidade.PROEJA_FIC_FUNDAMENTAL)
        return qs.distinct()

    sem_educacenso.short_description = 'Sem EDUCACENSO'

    def com_matriz(self, request, queryset):
        return queryset.filter(mesmo_curso__isnull=True, matrizes__isnull=False).distinct()

    com_matriz.short_description = 'Com matriz'

    def sem_alunos(self, request, queryset):
        return queryset.exclude(mesmo_curso__isnull=True, aluno__situacao__in=SituacaoMatricula.SITUACOES_CURSANDO).distinct()

    sem_alunos.short_description = 'Sem alunos cursando'

    def sem_autorizacao(self, request, queryset):
        return (
            queryset.filter(mesmo_curso__isnull=True, matrizes__isnull=False)
            .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO)
            .exclude(modalidade_id__in=[Modalidade.MESTRADO, Modalidade.DOUTORADO])
            .distinct()
        )

    sem_autorizacao.short_description = 'Sem autorização'

    def sem_criacao(self, request, queryset):
        return (
            queryset.filter(mesmo_curso__isnull=True, matrizes__isnull=False, modalidade_id__in=[Modalidade.MESTRADO, Modalidade.DOUTORADO])
            .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_CRIACAO_CURSO)
            .distinct()
        )

    sem_criacao.short_description = 'Sem criação'

    def sem_processo_emec(self, request, queryset):
        hoje = datetime.today()
        return (
            queryset.filter(
                mesmo_curso__isnull=True,
                tramitacaoprocessoemec__isnull=True,
                data_solicitacao_reconhecimento__lt=hoje,
                modalidade__in=AtoRegulatorioCurso.MODALIDADE_EXIGE_RECONHECIMENTO,
                matrizes__isnull=False,
            )
            .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO)
            .distinct()
        )

    sem_processo_emec.short_description = 'Sem processo e-MEC'

    def sem_reconhecimento(self, request, queryset):
        return (
            queryset.filter(mesmo_curso__isnull=True, tramitacaoprocessoemec__isnull=False, matrizes__isnull=False)
            .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO)
            .distinct()
        )

    sem_reconhecimento.short_description = 'Sem reconhecimento'

    def sem_data_funcionamento(self, request, queryset):
        return queryset.filter(data_funcionamento__isnull=True, matrizes__isnull=False).distinct()

    sem_data_funcionamento.short_description = 'Sem data de funcionamento'

    def vagas_pendentes(self, request, queryset):
        return queryset.filter(quantidade_vagas__isnull=True, matrizes__isnull=False).distinct()

    vagas_pendentes.short_description = 'Vagas autorizadas pendente'

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def correntes(self, request):
        q = '?ativo__exact=1'
        return HttpResponseRedirect('/admin/edu/cursocampus/' + q)

    def response_add(self, request, obj):
        self.message_user(request, 'Curso cadastrado com sucesso. Por favor, vincule a(s) matriz(es) ao curso.')
        return HttpResponseRedirect(f'/edu/cursocampus/{obj.pk}/')


admin.site.register(CursoCampus, CursoCampusAdmin)


class EquivalenciaComponenteQAcademicoAdmin(ModelAdminPlus):
    list_display = ('sigla', 'descricao', 'carga_horaria', 'componente')
    list_filter = (CustomTabListFilter,)
    search_fields = ('descricao', 'componente__sigla', 'sigla')
    form = EquivalenciaComponenteQAcademicoForm
    list_per_page = 15
    export_to_xls = True
    list_display_icons = True

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        return items

    def get_tabs(self, request):
        return ['tab_vinculados', 'tab_nao_vinculados']

    def tab_vinculados(self, request, queryset):
        return queryset.exclude(componente__isnull=True)

    tab_vinculados.short_description = 'Vinculados'

    def tab_nao_vinculados(self, request, queryset):
        return queryset.filter(componente__isnull=True)

    tab_nao_vinculados.short_description = 'Não-Vinculados'


admin.site.register(EquivalenciaComponenteQAcademico, EquivalenciaComponenteQAcademicoAdmin)


class MatrizAdmin(ModelAdminPlus):
    list_display = ('id', 'get_descricao', 'ano_criacao', 'nivel_ensino', 'natureza_participacao', 'ativo', 'get_diretorias')
    list_filter = (
        CustomTabListFilter,
        'ano_criacao',
        'ativo',
        'nivel_ensino',
        'estrutura',
        'estrutura__tipo_avaliacao',
        'requer_vinculacao_extensao_diarios',
        'cursocampus__diretoria__setor__uo',
        'cursocampus__diretoria',
    )
    search_fields = ('id', 'descricao')
    list_display_icons = True
    list_per_page = 15
    export_to_xls = True
    form = MatrizForm
    show_count_on_tabs = True

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'descricao',
                    ('ano_criacao', 'periodo_criacao'),
                    ('nivel_ensino', 'natureza_participacao'),
                    'ativo',
                    ('data_inicio', 'data_fim'),
                    'ppp',
                    'ppc',
                    'qtd_periodos_letivos',
                    'estrutura',
                )
            },
        ),
        (
            'Carga horária de componentes curriculares',
            {
                'fields': (
                    ('ch_componentes_obrigatorios', 'ch_componentes_optativos'),
                    (
                        'ch_componentes_extensao',
                        'ch_componentes_eletivos',
                    ),
                    ('ch_pratica_profissional', 'ch_componentes_tcc'),
                    ('ch_seminarios', 'ch_pratica_como_componente'),
                )
            },
        ),
        (
            'Integração curricular da extensão',
            {'fields': (('ch_atividades_extensao', 'ch_componentes_com_extensao'),)},
        ),
        (
            'Projeto Integrador',
            {'fields': ('ch_projeto_integrador',)},
        ),
        (
            'Carga horária de outras atividades',
            {'fields': (('ch_atividades_complementares', 'ch_atividades_aprofundamento'), ('ch_visita_tecnica',))},
        ),
        (
            'Configurações adicionais',
            {'fields': ('configuracao_atividade_academica', 'configuracao_atividade_aprofundamento', 'configuracao_creditos_especiais')},
        ),
        ('Curricularização da extensão', {'fields': ('requer_vinculacao_extensao_diarios',)}),
        (
            'Trabalho de conclusão de curso',
            {
                'fields': (
                    'exige_tcc',
                    'permite_etapas_componente_tcc',
                )
            },
        ),
        (
            'Estágio',
            {
                'fields': ('exige_estagio', 'ch_minima_estagio', 'periodo_minimo_estagio_obrigatorio', 'periodo_minimo_estagio_nao_obrigatorio'),
            },
        ),
        (
            'Certificação parcial',
            {
                'fields': (
                    'emite_certificacao_parcial',
                    'certificado_parcial_acumulavel',
                ),
            },
        ),
        (
            'Observações',
            {
                'fields': ('observacao',),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        if obj and obj.get_matrizppc():
            fieldsets = []
            fieldsets.append(('Dados gerais', {'fields': (('ano_criacao', 'periodo_criacao'), 'ativo', ('data_inicio', 'data_fim'), 'ppp', 'ppc')}))
            fieldsets.append(('Projeto Integrador', {'fields': ('ch_projeto_integrador',)}))
            fieldsets.append(
                (
                    'Certificação parcial',
                    {
                        'fields': (
                            'emite_certificacao_parcial',
                            'certificado_parcial_acumulavel',
                        )
                    },
                )
            )
        else:
            fieldsets = super().get_fieldsets(request, obj)

        return fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('ano_criacao')

    def get_tabs(self, request):
        return ['tab_vazias', 'tab_incompletas']

    def tab_vazias(self, request, queryset):
        return queryset.vazias()

    tab_vazias.short_description = 'Vazias'

    def tab_incompletas(self, request, queryset):
        return queryset.incompletas()

    tab_incompletas.short_description = 'Inconsistentes'

    def response_add(self, request, obj):
        self.message_user(request, 'Matriz cadastrada com sucesso. Por favor, vincule os componentes à matriz.')
        return HttpResponseRedirect(f'/edu/matriz/{obj.pk}/')

    def get_descricao(self, obj):
        html = [f'<p>{obj.descricao}</p>']
        if obj.observacao:
            html.append(f'<br><dl><dt>Observação:</dt><dd>{obj.observacao}</dd></dl>')
        return mark_safe(''.join(html))

    get_descricao.short_description = 'Descrição'

    def get_diretorias(self, obj):
        diretorias = obj.get_diretorias()
        if diretorias:
            lista = ['<ul>']
            for diretoria in diretorias:
                lista.append('<li>')
                lista.append(str(diretoria))
                lista.append('</li>')
            lista.append('</ul>')
            return mark_safe(''.join(lista))
        else:
            return mark_safe('-')

    get_diretorias.short_description = 'Diretorias'

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls

    def correntes(self, request):
        url = '/admin/edu/matriz/?&ativo__exact=1'
        return HttpResponseRedirect(url)


admin.site.register(Matriz, MatrizAdmin)


class RotuloModuloAdmin(ModelAdminPlus):
    list_display = ('matriz', 'descricao', 'tipo_modulo')
    ordering = ('matriz', 'tipo_modulo')
    search_fields = ('descricao',)
    form = RotuloModuloForm


admin.site.register(RotuloModulo, RotuloModuloAdmin)


class ConteudoMiniCursoInline(admin.TabularInline):
    formset = ConteudoMinicursoFormset
    model = ConteudoMinicurso
    extra = 0


class MinicursoAdmin(ModelAdminPlus):
    list_display = (
        'get_codigo',
        'descricao',
        'ativo',
        'ano_letivo',
        'periodo_letivo',
        'ch_total',
        'ch_aula',
        'diretoria',
        'autoinstrucional',
        'tipo_curso_autoinstrucional',
    )
    list_filter = (
        CustomTabListFilter,
        'ativo',
        'ano_letivo',
        'modalidade',
        'diretoria__setor__uo',
        'diretoria',
        'extensao',
        'autoinstrucional',
        'tipo_curso_autoinstrucional',
    )
    search_fields = ('descricao', 'codigo')
    ordering = ('descricao',)
    export_to_xls = True
    list_per_page = 15
    list_display_icons = True

    form = MinicursoForm
    inlines = [ConteudoMiniCursoInline]
    fieldsets = MinicursoForm.fieldsets

    def get_queryset(self, request):
        if request.user.has_perm('comum.is_operador_de_censo'):
            return self.model.objects.all()
        return self.model.locals.all()

    def get_tabs(self, request):
        return [
            'tab_any_data',
            'sem_sistec',
        ]

    def sem_sistec(self, request, queryset):
        return (
            queryset.filter(ch_total__gte=CursoCampus.CARGA_HORARIA_BASE_MINICURSO, codigo_sistec='', ativo=True)
            .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
            .exclude(aluno__isnull=True)
        )

    sem_sistec.short_description = 'Sem SISTEC'


admin.site.register(Minicurso, MinicursoAdmin)
