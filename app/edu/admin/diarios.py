from datetime import datetime

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import path, reverse_lazy
from django.utils.safestring import mark_safe

from comum.utils import get_sigla_reitoria
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, TabularInlinePlus, unquote
from djtools.templatetags.filters import in_group
from djtools.utils import httprr
from edu import perms
from edu.forms import ConfiguracaoAvaliacaoForm, DiarioForm, ItemConfiguracaoAvaliacaoFormset, MaterialAulaForm
from edu.models import Aula, ConfiguracaoAvaliacao, Diario, ItemConfiguracaoAvaliacao, MaterialAula, MatriculaDiario, Professor
from edu.models.diarios import JustificativaSuspensaoDiario, Trabalho


class DiarioAdmin(ModelAdminPlus):
    list_display = ('id', 'turma', 'componente_curricular', 'ano_letivo', 'periodo_letivo', 'get_outras_informacoes', 'get_datas_etapas')
    list_filter = (
        CustomTabListFilter,
        'ano_letivo',
        'periodo_letivo',
        'turma__curso_campus__modalidade',
        'turma__curso_campus__modalidade__nivel_ensino',
        'turma__curso_campus__diretoria__setor__uo',
        'turma__curso_campus__diretoria',
        'turno',
        'turma',
        'turma__curso_campus',
        'turma__polo',
        'segundo_semestre',
        'entregue_fisicamente',
        'turma__pertence_ao_plano_retomada',
        'professordiario__professor',
    )
    list_display_icons = True
    list_per_page = 15
    export_to_xls = True
    list_xls_display = (
        'id',
        'turma',
        'componente_curricular',
        'ano_letivo',
        'periodo_letivo',
        'get_nomes_professores',
        'local_aula',
        'local_laboratorio',
        'get_horario_aulas',
        'get_qtd_alunos_matriculados',
        'get_qtd_alunos_cursando',
    )
    search_fields = Diario.SEARCH_FIELDS
    form = DiarioForm
    actions = (
        'alternar_primeiro_semestre',
        'alternar_segundo_semestre',
        'registrar_entrega_fisica',
        'cancelar_entrega_fisica',
        'habilitar_integracao_com_moodle',
        'desabilitar_integracao_com_moodle',
        'suspender_diarios',
        'encerrar_suspensao_diarios',
    )

    show_count_on_tabs = True
    max_terms_search = 5

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab') and request.GET.get('tab') == 'tab_semestrais_em_cursos_anuais':
            return {}
        if request.GET.get('tab') and request.GET.get('tab') == 'tab_suspensos':
            del actions['suspender_diarios']
        if request.GET.get('tab') and request.GET.get('tab') != 'tab_suspensos':
            del actions['encerrar_suspensao_diarios']
        return actions

    def habilitar_integracao_com_moodle(self, request, queryset):
        queryset.update(integracao_com_moodle=True)
        messages.success(request, 'Habilitação realizada com sucesso.')

    habilitar_integracao_com_moodle.short_description = 'Habilitar Integração com Moodle'

    def desabilitar_integracao_com_moodle(self, request, queryset):
        queryset.update(integracao_com_moodle=False)
        messages.success(request, 'Desabilitação realizada com sucesso.')

    desabilitar_integracao_com_moodle.short_description = 'Desabilitar Integração com Moodle'

    def encerrar_suspensao_diarios(self, request, queryset):
        selected_ids = list(queryset.values_list('id', flat=True))
        pks = '_'.join(map(str, selected_ids))
        return httprr(reverse_lazy('encerrar_suspensao_diarios_lote', kwargs={'pks': pks}))

    encerrar_suspensao_diarios.short_description = 'Encerrar Suspensão'

    def suspender_diarios(self, request, queryset):
        selected_ids = list(queryset.values_list('id', flat=True))
        pks = '_'.join(map(str, selected_ids))
        return httprr(reverse_lazy('suspender_diarios_lote', kwargs={'pks': pks}))

    suspender_diarios.short_description = 'Suspender Diários'

    def alternar_primeiro_semestre(self, request, queryset):
        for diario in queryset.filter(componente_curricular__segundo_semestre=True):
            diario.segundo_semestre = False
            diario.save()
        messages.success(request, 'Diário alterado com sucesso.')

    alternar_primeiro_semestre.short_description = 'Alternar para Primeiro Semestre Letivo'

    def alternar_segundo_semestre(self, request, queryset):
        for diario in queryset.filter(componente_curricular__segundo_semestre=False):
            diario.segundo_semestre = True
            diario.save()
        messages.success(request, 'Diário alterado com sucesso.')

    alternar_segundo_semestre.short_description = 'Alternar para Segundo Semestre Letivo'

    def registrar_entrega_fisica(self, request, queryset):
        queryset.update(entregue_fisicamente=True)
        messages.success(request, 'Entrega física registrada com sucesso.')

    registrar_entrega_fisica.short_description = 'Registrar Entrega Física'

    def cancelar_entrega_fisica(self, request, queryset):
        queryset.update(entregue_fisicamente=False)
        messages.success(request, 'Entrega física cancelada com sucesso.')

    cancelar_entrega_fisica.short_description = 'Cancelar Entrega Física'

    def get_datas_etapas(self, obj):
        html = []

        if obj.componente_curricular.qtd_avaliacoes > 0:
            etapa1 = []
            if obj.get_inicio_etapa_1() is not None:
                etapa1.append(obj.get_inicio_etapa_1().strftime('%d/%m/%Y'))
            else:
                etapa1.append(' - ')
            etapa1.append(' a ')
            if obj.get_fim_etapa_1() is not None:
                etapa1.append(str(obj.get_fim_etapa_1().strftime('%d/%m/%Y')))
            else:
                etapa1.append(' - ')
            html.append("<strong title='")
            html.append(' '.join(etapa1))
            html.append("'>Etapa ")
            if obj.segundo_semestre:
                html.append('3</strong><br/>')
            else:
                html.append('1</strong><br/>')

            if obj.componente_curricular.qtd_avaliacoes > 1:
                etapa2 = []
                if obj.get_inicio_etapa_2() is not None:
                    etapa2.append(obj.get_inicio_etapa_2().strftime('%d/%m/%Y'))
                else:
                    etapa2.append(' - ')
                etapa2.append(' a ')
                if obj.get_fim_etapa_2() is not None:
                    etapa2.append(str(obj.get_fim_etapa_2().strftime('%d/%m/%Y')))
                else:
                    etapa2.append(' - ')
                html.append("<strong title='")
                html.append(' '.join(etapa2))
                html.append("'>Etapa </span>")
                if obj.segundo_semestre:
                    html.append('4</strong><br/>')
                else:
                    html.append('2</strong><br/>')

                is_semestral_em_calendario_anual = obj.is_semestral_em_calendario_anual()
                if not is_semestral_em_calendario_anual and obj.componente_curricular.qtd_avaliacoes > 2:
                    etapa3 = []
                    if obj.get_inicio_etapa_3() is not None:
                        etapa3.append(obj.get_inicio_etapa_3().strftime('%d/%m/%Y'))
                    else:
                        etapa3.append(' - ')
                    etapa3.append(' a ')
                    if obj.get_fim_etapa_3() is not None:
                        etapa3.append(str(obj.get_fim_etapa_3().strftime('%d/%m/%Y')))
                    else:
                        etapa3.append(' - ')
                    html.append("<strong title='")
                    html.append(' '.join(etapa3))
                    html.append("'>Etapa 3</strong><br/>")

                if not is_semestral_em_calendario_anual and obj.componente_curricular.qtd_avaliacoes > 3:
                    etapa4 = []
                    if obj.get_inicio_etapa_4() is not None:
                        etapa4.append(obj.get_inicio_etapa_4().strftime('%d/%m/%Y'))
                    else:
                        etapa4.append(' - ')
                    etapa4.append(' a ')
                    if obj.get_fim_etapa_4() is not None:
                        etapa4.append(str(obj.get_fim_etapa_4().strftime('%d/%m/%Y')))
                    else:
                        etapa4.append(' - ')
                    html.append("<strong title='")
                    html.append(' '.join(etapa4))
                    html.append("'>Etapa 4</strong><br/>")

        etapa5 = []
        if obj.get_inicio_etapa_final() is not None:
            etapa5.append(obj.get_inicio_etapa_final().strftime('%d/%m/%Y'))
        else:
            etapa5.append(' - ')
        etapa5.append(' a ')
        if obj.get_fim_etapa_final() is not None:
            etapa5.append(str(obj.get_fim_etapa_final().strftime('%d/%m/%Y')))
        else:
            etapa5.append(' - ')
        html.append("<strong style='display:ruby; ' title='")
        html.append(' '.join(etapa5))
        html.append("'>Etapa Final</strong><br />")

        return mark_safe(' '.join(html))

    get_datas_etapas.short_description = 'Etapas'

    def get_outras_informacoes(self, obj):
        if not obj.local_aula and not obj.local_laboratorio and not obj.get_horario_aulas() and not obj.professordiario_set.exists():
            return '-'

        html = []

        # Local de Aula
        if obj.local_aula:
            html.append('<strong>Sala de aula:</strong> ')
            html.append(str(obj.local_aula))
            html.append('<br/>')
            html.append('<br/>')

        if obj.local_laboratorio:
            html.append('<strong>Laboratório:</strong> ')
            html.append(str(obj.local_laboratorio))
            html.append('<br/>')
            html.append('<br/>')

        # Horário de Aula
        if obj.get_horario_aulas():
            html.append('<strong>Horário de Aula:</strong> ')
            html.append(str(obj.get_horario_aulas()))
            html.append('<br/>')

        # Professores
        professores = obj.professordiario_set.all().select_related('tipo')
        if professores:
            lista_professores = []
            for professor_diario in professores:
                nome = f'{professor_diario.professor.vinculo.pessoa.nome} ({professor_diario.tipo})'
                lista_professores.append(nome)
            html.append('<br/>')
            html.append('<strong>Professores:</strong> ')
            if len(lista_professores) > 1:
                html.append('<ul>')
                for professor in lista_professores:
                    html.append(f'<li>{professor}</li>')
                html.append('<ul>')
            else:
                html.append(', '.join(lista_professores))
            html.append('<br/>')

        # Alunos
        if obj.local_aula or obj.local_laboratorio:
            html.append('<br/>')
            html.append('<strong>Alunos:</strong> ')
            html.append(str(obj.get_quantidade_alunos_ativos()))

        return mark_safe(' '.join(html))

    get_outras_informacoes.short_description = 'Outras Informações'

    def get_queryset(self, request):
        if request.user.has_group_cached('Diretor Acadêmico'):
            manager = Diario.objects
        else:
            manager = Diario.locals
        qs = (
            super()
            .get_queryset(request, manager)
            .select_related(
                'componente_curricular',
                'componente_curricular__componente',
                'componente_curricular__componente__nivel_ensino',
                'componente_curricular__matriz',
                'calendario_academico',
                'turma',
                'local_aula',
                'local_aula__predio',
                'local_aula__predio__uo',
                'local_laboratorio',
                'local_laboratorio__predio',
                'local_laboratorio__predio__uo',
                'turma__curso_campus',
                'ano_letivo',
            )
            .prefetch_related('professordiario_set')
        )
        return qs

    def get_tabs(self, request):
        return [
            'tab_sem_professores',
            'tab_sem_local_aula',
            'tab_sem_horario_aula',
            'tab_sem_aluno',
            'tab_em_curso',
            'tab_notas_pendentes',
            'tab_ch_pendente',
            'tab_semestrais_em_cursos_anuais',
            'tab_entregues',
            'tab_nao_entregues',
            'tab_frequencias_pendentes',
            'tab_suspensos',
            'tab_sem_aulas_registradas',
        ]

    def tab_sem_professores(self, request, queryset):
        return queryset.sem_professores()

    tab_sem_professores.short_description = 'Sem Professores'

    def tab_sem_local_aula(self, request, queryset):
        return queryset.sem_local_aula()

    tab_sem_local_aula.short_description = 'Sem Local de Aula'

    def tab_sem_horario_aula(self, request, queryset):
        return queryset.sem_horario_aula()

    tab_sem_horario_aula.short_description = 'Sem Horário de Aula'

    def tab_sem_aluno(self, request, queryset):
        return queryset.sem_aluno()

    tab_sem_aluno.short_description = 'Sem Aluno'

    def tab_em_curso(self, request, queryset):
        return queryset.em_curso()

    tab_em_curso.short_description = 'Em Andamento'

    def tab_notas_pendentes(self, request, queryset):
        return queryset.pendentes()

    tab_notas_pendentes.short_description = 'Notas Pendentes'

    def tab_ch_pendente(self, request, queryset):
        return queryset.com_ch_pendente()

    tab_ch_pendente.short_description = 'C.H. Pendente'

    def tab_semestrais_em_cursos_anuais(self, request, queryset):
        return queryset.semestrais_em_cursos_anuais()

    tab_semestrais_em_cursos_anuais.short_description = 'Semestrais em Cursos Anuais'

    def tab_entregues(self, request, queryset):
        return queryset.entregues()

    tab_entregues.short_description = 'Entregues'

    def tab_nao_entregues(self, request, queryset):
        return queryset.nao_entregues()

    tab_nao_entregues.short_description = 'Não Entregues'

    def tab_frequencias_pendentes(self, request, queryset):
        return queryset.frequencias_pendentes()

    tab_frequencias_pendentes.short_description = 'Frequências Pendentes'

    def tab_suspensos(self, request, queryset):
        return queryset.suspensos()

    tab_suspensos.short_description = 'Suspensos'

    def tab_sem_aulas_registradas(self, request, queryset):
        return queryset.sem_aulas_registradas()

    tab_sem_aulas_registradas.short_description = 'Sem Aulas Registradas'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_group_cached(['Administrador Acadêmico', 'Diretor Acadêmico', 'Coordenador de Curso', 'Secretário Acadêmico']):
            items.append(
                {
                    'label': 'Ações para o TimeTables',
                    'subitems': [
                        {'url': '/static/edu/timetables/suap_edu.xml', 'label': 'Gerar o Arquivo de configuração do TimeTables'},
                        {'url': '/edu/exportar_xml_time_tables/', 'label': 'Exportar XML para o TimeTables'},
                        {'url': '/edu/importar_xml_time_tables/', 'label': 'Importar XML do TimeTables'},
                    ],
                }
            )
        return items

    def has_delete_permission(self, request, obj=None):
        return bool(obj and obj.pode_ser_excluido() and perms.realizar_procedimentos_academicos(request.user, obj.turma.curso_campus))

    def correntes(self, request):
        url = '/admin/edu/diario/'
        if in_group(request.user, 'Diretor Acadêmico') and (request.user.eh_servidor or request.user.eh_prestador):
            sigla_reitoria = get_sigla_reitoria()
            if request.user.get_relacionamento().setor.uo.sigla != sigla_reitoria:
                url = f'{url}?turma__curso_campus__diretoria__setor__uo__id__exact={request.user.get_vinculo().setor.uo_id}'
        return HttpResponseRedirect(url)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('correntes/', self.admin_site.admin_view(self.correntes))]
        return my_urls + urls


admin.site.register(Diario, DiarioAdmin)


class AulaAdmin(ModelAdminPlus):
    list_display = ('professor_diario', 'registro_frequencia_confirmado', 'quantidade', 'data', 'get_qtd_faltas')
    list_filter = (
        'registro_frequencia_confirmado',
        'professor_diario__diario__ano_letivo',
        'professor_diario__diario__periodo_letivo',
        'professor_diario__diario__turma__curso_campus__modalidade',
        'professor_diario__diario__matriculadiario__matricula_periodo__aluno',
    )
    list_display_icons = True
    export_to_xls = True
    list_per_page = 100
    date_hierarchy = 'data'
    ordering = ('-id',)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_qtd_faltas(self, obj):
        qtd = ''
        pk = self.request.GET.get('professor_diario__diario__matriculadiario__matricula_periodo__aluno', None)
        if pk:
            qtd = sum(obj.falta_set.filter(matricula_diario__matricula_periodo__aluno=pk).values_list('quantidade', flat=True))
        return qtd

    get_qtd_faltas.short_description = 'Faltas'


admin.site.register(Aula, AulaAdmin)


class MaterialAulaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'data_cadastro', 'professor')
    search_fields = ('descricao', 'professor__vinculo__user__username', 'professor__vinculo__pessoa__nome')
    date_hierarchy = 'data_cadastro'
    list_display_icons = True
    form = MaterialAulaForm
    # fieldsets = MaterialAulaForm.fieldsets
    list_filter = (CustomTabListFilter,)
    actions = ['remover_selecionadas', 'clonar_selecionadas']

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab') != 'tab_meus_materiais' and 'remover_selecionadas' in actions:
            del actions['remover_selecionadas']
        if request.GET.get('tab') != 'tab_compartilhados' and 'clonar_selecionadas' in actions:
            del actions['clonar_selecionadas']
        return actions

    def remover_selecionadas(self, request, queryset):
        for element in queryset:
            element.delete()
        messages.success(request, 'Ação realizada com sucesso.')

    remover_selecionadas.short_description = 'Remover Materiais Selecionados'

    def clonar_selecionadas(self, request, queryset):
        for element in queryset:
            element.clone(request.user)
        messages.success(request, 'Ação realizada com sucesso.')

    clonar_selecionadas.short_description = 'Clonar Materiais Selecionados'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(professor__vinculo__user=request.user) | qs.exclude(professor__vinculo__user=request.user).filter(publico=True)

    def get_tabs(self, request):
        return ['tab_meus_materiais', 'tab_compartilhados']

    def tab_meus_materiais(self, request, queryset):
        return queryset.filter(professor__vinculo__user=request.user)

    tab_meus_materiais.short_description = 'Meus Materiais'

    def tab_compartilhados(self, request, queryset):
        return queryset.exclude(professor__vinculo__user=request.user).filter(publico=True)

    tab_compartilhados.short_description = 'Materiais Públicos'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.add_materialaula'):
            items.append({'url': '/edu/adicionar_materiais_aula/', 'label': 'Adicionar Material de Aula', 'css_class': 'success'})

        professor = Professor.objects.filter(vinculo=request.user.get_vinculo()).first()
        if professor and professor.get_materiais_aula_outros_vinculos().exists():
            items.append({'url': '/edu/importar_materiais_aula/', 'label': 'Importar Materiais de outros Vínculos'})
        return items


admin.site.register(MaterialAula, MaterialAulaAdmin)


class ItemConfiguracaoAvaliacaoInline(TabularInlinePlus):
    formset = ItemConfiguracaoAvaliacaoFormset
    model = ItemConfiguracaoAvaliacao
    extra = 0

    def get_exclude(self, request, obj=None):
        if obj and obj.diario.is_lancamento_conceito():
            return 'nota_maxima', 'peso'
        return super().get_exclude(request, obj)

    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj=obj)
        return has_permission


class ItemConfiguracaoAvaliacaoInlineSemRecuperacao(ItemConfiguracaoAvaliacaoInline):
    def get_queryset(self, request):
        return super().get_queryset(request).exclude(tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)


class ItemConfiguracaoAvaliacaoInlineSomenteRecuperacao(ItemConfiguracaoAvaliacaoInline):
    readonly_fields = ['tipo_avaliacao']
    verbose_name = 'Item de Configuração de Recuperação'
    verbose_name_plural = 'Itens de Configuração de Recuperação'
    can_delete = False
    max_num = 1

    def get_fields(self, request, obj=None):
        if obj and obj.diario.is_lancamento_conceito():
            return ['tipo_avaliacao', 'sigla', 'descricao', 'data']
        else:
            return ['tipo_avaliacao', 'sigla', 'descricao', 'data', 'nota_maxima']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def tipo_avaliacao(self, obj):
        return 'Recuperação'

    tipo_avaliacao.short_description = 'Tipo da avaliação'

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        formfield.disabled = True

        return formfield

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)


class ConfiguracaoAvaliacaoAdmin(ModelAdminPlus):
    list_display = ('forma_calculo', 'maior_nota', 'menor_nota', 'get_avaliacoes')
    list_display_icons = True
    export_to_xls = True
    form = ConfiguracaoAvaliacaoForm

    inlines = [ItemConfiguracaoAvaliacaoInlineSemRecuperacao]

    fieldsets = (('', {'fields': (('forma_calculo', 'divisor'), ('menor_nota', 'maior_nota'), 'autopublicar', 'observacao')}),)

    def get_inline_instances(self, request, obj=None):
        inline_instances = super().get_inline_instances(request, obj)

        # inclui o inline de recuperação apenas se a etapa curso permitir
        if obj.etapa != 5 and obj.diario.estrutura_curso.permite_recuperacao_etapa:
            inline_instances.append(ItemConfiguracaoAvaliacaoInlineSomenteRecuperacao(self.model, self.admin_site))

        return inline_instances

    def has_delete_permission(self, request, obj=None):
        return bool(
            obj
            and obj.diario
            and obj.diario.pode_ser_excluido()
            and perms.realizar_procedimentos_academicos(request.user, obj.diario.turma.curso_campus)
        )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        result = super().change_view(request, object_id, form_url, extra_context)
        if not in_group(request.user, 'Administrador Acadêmico,Secretário Acadêmico'):
            obj = self.get_object(request, unquote(object_id))
            prof = request.user.get_vinculo().professor_set.all()
            if not prof or (obj and prof[0].pk not in obj.diario.professordiario_set.values_list('professor__id', flat=True).distinct()):
                raise PermissionDenied
        return result

    @transaction.atomic
    def after_saving_model_and_related_inlines(self, obj):
        for matricula_diario in obj.diario.matriculadiario_set.all():
            matricula_diario.criar_registros_notas_etapa(obj.etapa, ItemConfiguracaoAvaliacao.objects.filter(configuracao_avaliacao=obj))

        from edu.models import AbonoFaltas

        # Checar se há abono de faltas no período das avaliações que justifiquem a criação de reposição de faltas
        itens = ItemConfiguracaoAvaliacao.objects.filter(configuracao_avaliacao=obj, data__isnull=False)
        for item in itens:
            abonos = AbonoFaltas.objects.filter(
                aluno__matriculaperiodo__matriculadiario__diario=obj.diario, data_inicio__lte=item.data, data_fim__gte=item.data, deferido=True
            ).distinct()

            for abono in abonos:
                abono.checar_solicitacoes_reposicao_atividade()

        return obj

    def response_change(self, request, obj):
        obj = self.after_saving_model_and_related_inlines(obj)
        return super().response_change(request, obj)

    def get_avaliacoes(self, obj):
        if obj.itemconfiguracaoavaliacao_set.exists():
            lista = ['<ul>']
            for item in obj.itemconfiguracaoavaliacao_set.all():
                lista.append(f'<li>{item.get_tipo_display()}({item.sigla}): {item.nota_maxima}</li>')
            lista.append('</ul>')
        else:
            return mark_safe('-')

        return mark_safe(''.join(lista))

    get_avaliacoes.short_description = 'Avaliações'


admin.site.register(ConfiguracaoAvaliacao, ConfiguracaoAvaliacaoAdmin)


class TrabalhoAdmin(ModelAdminPlus):
    list_display = ('diario', 'titulo', 'descricao', 'get_opcoes')
    search_fields = ('diario__componente_curricular__componente__sigla', 'titulo', 'descricao')

    def get_queryset(self, request):
        return (
            Trabalho.objects.filter(
                diario__matriculadiario__matricula_periodo__aluno__matricula=request.user.username,
                diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
            )
            .exclude(entregatrabalho__isnull=False)
            .exclude(data_limite_entrega__lt=datetime.today())
            .distinct()
        )

    def get_opcoes(self, obj):
        entregar_trabalho = f'<li><a href="/edu/entregar_trabalho/{obj.pk}/" class="btn success popup">Entregar trabalho</a></li>'
        acessar_disciplina = f'<li><a href="/edu/disciplina/{obj.diario.pk}/" class="btn">Acessar disciplina</a></li>'
        arquivo = f'<li><a href="{obj.arquivo.url}" class="btn">Visualizar especificação</a></li>' if obj.arquivo else ''
        return mark_safe(f'<ul class="action-bar">{entregar_trabalho} {acessar_disciplina} {arquivo} </ul>')

    get_opcoes.short_description = 'Opções'


admin.site.register(Trabalho, TrabalhoAdmin)


class JustificativaSuspensaoDiarioAdmin(ModelAdminPlus):
    list_display = 'descricao', 'codigo_pedemeia', 'ativo'
    list_filter = ('ativo',)
    list_display_icons = True
    export_to_xls = True
    list_per_page = 100
    ordering = ('id',)


admin.site.register(JustificativaSuspensaoDiario, JustificativaSuspensaoDiarioAdmin)
