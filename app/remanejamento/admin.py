import datetime

from django.contrib import admin
from django.db import models
from django.template import defaultfilters
from django.urls import reverse
from django.utils.formats import localize
from django.utils.safestring import mark_safe

from djtools.contrib.admin import DateRangeListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_, in_group
from remanejamento.forms import DisciplinaAdminForm, EditalCriterioClassificacaoForm, EditalForm, AfastamentoRemocaoInternaForm
from remanejamento.models import (
    AcaoEditalHistorico,
    CriterioClassificacao,
    Disciplina,
    DisciplinaItem,
    Edital,
    EditalCriterioClassificacao,
    EditalRecurso,
    Inscricao,
    InscricaoContemplada,
    ServidorDataInicioExercicioRemocaoInterna,
    AfastamentoRemocaoInterna,
    ServidorTempoAdicionalRemocaoInterna,
)
from remanejamento.utils import obter_campos_alterados, tempo_servico_no_cargo_em_dias
from rh.models import CargoEmprego, Servidor


class EditalAdmin(ModelAdminPlus):
    form = EditalForm
    list_display = ('titulo', 'show_periodo_inscricoes', 'show_cargos', 'show_acoes')
    list_filter = ('cargos', 'categoria', 'campus')
    search_fields = ('titulo',)
    list_display_icons = True

    def has_change_permission(self, request, obj=None):
        has_change_permission = super().has_change_permission(request, obj)
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador'])
        if obj:
            has_change_permission = has_change_permission and (
                request.user in obj.coordenadores.all() or request.user.is_superuser or eh_administrador_remanejamento
            )

        return has_change_permission

    def show_cargos(self, obj):
        out = ['<ul>']
        for cargo in obj.cargos.all():
            out.append(f'<li>{cargo!s}</li>')
        out.append('</ul>')
        return mark_safe(''.join(out))

    show_cargos.short_description = 'Cargos'

    def show_periodo_inscricoes(self, obj):
        return mark_safe(
            f'<span class="{obj.is_em_periodo_de_inscricao()}">{localize(obj.inicio_inscricoes)} a {localize(obj.fim_inscricoes)}</span>'
        )

    show_periodo_inscricoes.admin_order_field = 'inicio_inscricoes'
    show_periodo_inscricoes.short_description = 'Período de Inscrições'

    def show_acoes(self, obj):
        html_acoes = ''
        if self.has_change_permission(self.request, obj):
            usuario_logado = self.request.user
            html_acoes = '<ul class="action-bar">'
            if obj.coordenadores.filter(pk=usuario_logado.pk):
                html_acoes += f'<li><a href="{reverse("gerenciar_edital", args=[obj.id])}" class="btn default">Gerenciar</a></li>'
            html_acoes += f'<li><a class="btn" href="/remanejamento/inscricoes_csv/{obj.pk}/">Gerar CSV</a></li></ul>'
        return mark_safe(html_acoes)

    show_acoes.short_description = 'Ações'

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'categoria',
                    'titulo',
                    'descricao',
                    'edital_documentotexto',
                    'url',
                    'campus',
                    'cargos',
                    'coordenadores',
                    'tem_anexo',
                    'chave_hash',
                )
            },
        ),
        ('Recurso ao Edital', {'fields': (('inicio_recursos_edital', 'fim_recursos_edital'), 'resultado_recursos_edital')}),
        ('Inscrições', {'fields': ('inicio_inscricoes', 'fim_inscricoes')}),
        # ('Avaliações', {'fields': ('inicio_avaliacoes', 'fim_avaliacoes')}), #deprecated
        ('Desistência do Edital', {'fields': (('inicio_desistencias', 'fim_desistencias'),)}),
        ('Recursos ao Resultado', {'fields': (('inicio_recursos', 'fim_recursos'), 'resultado_recursos')}),
        ('Resultado Parcial', {'fields': ('data_resultado_parcial',)}),
        ('Resultado Final', {'fields': ('inicio_resultados',)}),
        ('Homologação do Resultado Final', {'fields': ('data_homologacao_resultado',)}),
        ('Permitir Múltiplas Inscrições', {'fields': ('servidores_permitidos_multiplas_inscricoes',)}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            acao_realizada = f'Cadastrou {obj.titulo}'
        else:
            objeto_anterior = Edital.objects.get(pk=obj.pk)
            obj.save()
            campos_modificados = obter_campos_alterados(objeto_anterior, obj)
            acao_realizada = f'Atualizou {campos_modificados}'
        super().save_model(request, obj, form, change)
        AcaoEditalHistorico.cadastrar_acao(obj, obj.get_etapa_atual(), acao_realizada, request.user.get_vinculo())


admin.site.register(Edital, EditalAdmin)


class EditalRecursoAdmin(ModelAdminPlus):
    list_display_comum = ('edital', 'servidor', 'dh_recurso')
    list_display_coordenador = ('edital', 'servidor', 'dh_recurso', 'recurso_respondido')
    list_filter_comum = ('edital',)
    list_filter_coordenador = ('edital', 'recurso_respondido', 'edital__cargos', ('edital__inicio_resultados', DateRangeListFilter))
    search_fields = [f'servidor__{servidor}' for servidor in Servidor.SEARCH_FIELDS]
    export_to_xls = True
    list_display_icons = True

    # não exibe o botão "Adicionar"
    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        has_view_permission = super().has_view_permission(request, obj)
        if obj:
            eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador'])
            sou_coordenador = obj.edital.coordenadores.filter(pk=request.user.pk).exists()
            sou_dono_recurso = obj.servidor == request.user.get_relacionamento()
            has_view_permission = (
                has_view_permission and (sou_coordenador or sou_dono_recurso) or request.user.is_superuser or eh_administrador_remanejamento
            )
        return has_view_permission

    def changelist_view(self, request, extra_context=None):
        if in_group(request.user, ['Coordenador de Remanejamento', 'Avaliador de Remanejamento', 'Coordenador de Gestão de Pessoas Sistêmico']):
            self.list_display = self.list_display_coordenador
            self.list_filter = self.list_filter_coordenador
        else:
            self.list_display = self.list_display_comum
            self.list_filter = self.list_filter_comum

        return super().changelist_view(request, extra_context)

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Edital',
            'Servidor',
            'Horário de Cadastro do Recurso',
            'Texto do Recurso',
            'Horário de Cadastro da Resposta ao Recurso',
            'Resposta ao Recurso',
        ]
        rows = [header]
        superusuario = request.user.is_superuser
        relacionamento = request.user.get_relacionamento()
        eh_servidor = request.user.eh_servidor()
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [idx + 1, obj.edital, obj.servidor, obj.dh_recurso, obj.recurso_texto, obj.dh_resposta, obj.recurso_resposta]
            if superusuario or request.user in obj.edital.coordenadores.all() or (eh_servidor and relacionamento == obj.servidor):
                rows.append(row)
        return rows


admin.site.register(EditalRecurso, EditalRecursoAdmin)


class DisciplinaItemInline(admin.StackedInline):
    model = DisciplinaItem


class DisciplinaAdmin(ModelAdminPlus):
    list_display = ['descricao', 'edital', 'show_avaliadores']
    search_fields = ['descricao']
    inlines = [DisciplinaItemInline]
    form = DisciplinaAdminForm
    list_filter = ['edital']

    def show_avaliadores(self, obj):
        out = ['<ul>']
        for avaliador in obj.avaliadores.all():
            out.append(f'<li class="text-nowrap">{avaliador!s} ({avaliador.get_profile().nome})</li>')
        out.append('<ul>')
        return mark_safe(''.join(out))

    show_avaliadores.short_description = 'Avaliadores'


admin.site.register(Disciplina, DisciplinaAdmin)


class DisciplinaItemAdmin(ModelAdminPlus):
    list_display = ['disciplina', 'descricao', 'sequencia', 'nao_avaliar']


admin.site.register(DisciplinaItem, DisciplinaItemAdmin)


def restringir_inscricoes(self, request):
    eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador'])
    if request.user.is_superuser or eh_administrador_remanejamento:
        return admin.ModelAdmin.get_queryset(self, request)
    else:
        return (
            admin.ModelAdmin.get_queryset(self, request)
            .filter(
                models.Q(edital__coordenadores=request.user)
                | models.Q(avaliacao_avaliador=request.user)
                | models.Q(disciplina__avaliadores=request.user)
                | models.Q(servidor=request.user.get_relacionamento())
            )
            .distinct()
        )


class InscricaoDisciplinaFilter(admin.SimpleListFilter):
    title = 'Disciplina'
    parameter_name = 'disciplina'

    def lookups(self, request, model_admin):
        edital = request.GET.get('edital')
        disciplinas = Disciplina.objects.filter(edital__pk=edital)
        if edital and disciplinas.exists():
            return [(d.id, d.descricao) for d in Disciplina.objects.filter(edital__pk=edital)]
        return None

    def queryset(self, request, queryset):
        if self.value():
            edital = request.GET.get('edital', False)
            if edital and queryset.filter(edital=edital, disciplina__id__exact=self.value()).exists():
                return queryset.filter(disciplina__id__exact=self.value())
            else:
                self.used_parameters.pop(self.parameter_name)
        return queryset


class InscricaoCargoFilter(admin.SimpleListFilter):
    title = 'Cargo'
    parameter_name = 'cargo'

    def lookups(self, request, model_admin):
        cargos = model_admin.get_queryset(request).distinct().values_list('edital__cargos', flat=True)
        if cargos.exists():
            return [(d.id, d.nome) for d in CargoEmprego.objects.filter(pk__in=cargos)]
        return None

    def queryset(self, request, queryset):
        if self.value():
            edital = request.GET.get('edital', False)
            if edital:
                return queryset.filter(edital__pk=edital, servidor__cargo_emprego__id=self.value())
            else:
                return queryset.filter(servidor__cargo_emprego__id=self.value())
        return queryset


class RecursoFilter(admin.SimpleListFilter):
    title = 'Tem Recurso?'
    parameter_name = 'recurso'

    def lookups(self, request, model_admin):
        return (('s', 'Sim'), ('n', 'Não'))

    def queryset(self, request, queryset):
        if self.value() == 's':
            return queryset.exclude(recurso_texto='')
        elif self.value() == 'n':
            return queryset.filter(recurso_texto='')
        return queryset


class RecursoRespondidoFilter(admin.SimpleListFilter):
    title = 'Recurso Respondido?'
    parameter_name = 'recurso_respondido'

    def lookups(self, request, model_admin):
        return (('s', 'Sim'), ('n', 'Não'))

    def queryset(self, request, queryset):
        if self.value() == 'n':
            return queryset.filter(avaliacao_recurso='').exclude(recurso_texto='')
        elif self.value() == 's':
            return queryset.exclude(avaliacao_recurso='')
        return queryset


class DesistenciaFilter(admin.SimpleListFilter):
    title = 'Desistência?'
    parameter_name = 'desistencia'

    def lookups(self, request, model_admin):
        return (('s', 'Sim'), ('n', 'Não'))

    def queryset(self, request, queryset):
        if self.value() == 's':
            return queryset.filter(data_desistencia__isnull=False)
        elif self.value() == 'n':
            return queryset.filter(data_desistencia__isnull=True)
        return queryset


class InabilitadaFilter(admin.SimpleListFilter):
    title = 'Inabilitada?'
    parameter_name = 'inabilitada'

    def lookups(self, request, model_admin):
        return (('s', 'Sim'), ('n', 'Não'))

    def queryset(self, request, queryset):
        if self.value() == 's':
            return queryset.filter(data_inapta__isnull=False)
        elif self.value() == 'n':
            return queryset.filter(data_inapta__isnull=True)
        return queryset


class InscricaoAdmin(ModelAdminPlus):
    list_display = [
        'show_informacoes',
        'horario',
        'servidor',
        'show_disciplina',
        'show_data_inicio_exercicio_no_cargo',
        'show_recurso',
        'confirmada',
        'show_cancelar',
    ]
    get_queryset = restringir_inscricoes
    search_fields = ['id'] + [f'servidor__{servidor}' for servidor in Servidor.SEARCH_FIELDS]
    list_display_icons = True
    export_to_xls = True

    def get_list_filter(self, request):
        if request.user.is_superuser or in_group(request.user, ['Coordenador de Remanejamento', 'Avaliador de Remanejamento']):
            return (
                'edital',
                'confirmada',
                InscricaoCargoFilter,
                InscricaoDisciplinaFilter,
                RecursoFilter,
                RecursoRespondidoFilter,
                DesistenciaFilter,
                InabilitadaFilter,
            )
        else:
            return ('edital', 'confirmada', InscricaoDisciplinaFilter)

    def show_informacoes(self, obj):
        out = [f'<dl><dt>Edital:</dt><dd>{obj.edital!s}</dd>']
        if obj.disciplina:
            out.append(f'<dt>Disciplina:</dt><dd>{obj.disciplina.descricao!s}</dd>')
        if obj.avaliacao_avaliador:
            out.append(f'<dt>Avaliador:</dt><dd>{obj.avaliacao_avaliador!s} ({obj.avaliacao_avaliador.get_profile().nome!s})</dd>')
        out.append('</dl>')
        if obj.data_desistencia:
            out.append(f'<span class="status status-error">Desistência em {format_(obj.data_desistencia)}</span>')

        return mark_safe(''.join(out))

    show_informacoes.short_description = 'Informações'

    def show_recurso(self, obj):
        html = '<dl><dt>Tem Recurso:</dt>'
        if obj.recurso_texto:
            html += '<dd><span class="status status-success">Sim</span></dd>'
            html += '<dt>Recurso Respondido:</dt>'
            if obj.avaliacao_recurso:
                html += '<dd><span class="status status-success">Sim</span></dd>'
            else:
                html += '<dd><span class="status status-error">Não</span></dd>'
        else:
            html += '<dd><span class="status status-error">Não</span></dd>'
        html += '</dt>'

        return mark_safe(html)

    show_recurso.short_description = 'Recurso'

    def show_cancelar(self, obj):
        if obj.confirmada and obj.is_pode_desistir(self.request.user):
            return mark_safe(
                f'<a title="Cancelar Inscrição (Desistência)" class="btn danger text-center" href="/remanejamento/inscricao/{obj.pk}/desistir/">Cancelar Inscrição </br>(Desistência)</a>'
            )
        return '-'

    show_cancelar.short_description = 'Ações'

    def show_data_inicio_exercicio_no_cargo(self, obj):
        return obj.servidor.data_inicio_exercicio_no_cargo

    show_data_inicio_exercicio_no_cargo.short_description = 'Data de Início do Exercício no Cargo'
    show_data_inicio_exercicio_no_cargo.admin_order_field = 'servidor__data_inicio_exercicio_no_cargo'

    def show_disciplina(self, obj):
        retorno = ''
        servidor = obj.servidor
        if servidor.eh_docente:
            retorno += '<dl>'
            retorno += '<dt>Disciplina de Ingresso:</dt><dd>{}</dd>'.format(obj.servidor.disciplina_ingresso or 'Não definido')
            if obj.disciplina:
                retorno += '<dt>Disciplina Inscrita:</dt><dd>{}</dd>'.format(obj.disciplina.descricao or 'Não definido')
            retorno += '</dl>'
        return mark_safe(retorno)

    show_disciplina.short_description = 'Disciplina'
    show_disciplina.admin_order_field = 'disciplina'

    def show_score(self, obj):
        if obj.avaliacao_score is not None:
            return defaultfilters.floatformat(obj.avaliacao_score, 2)
        else:
            return '-'

    show_score.admin_order_field = 'avaliacao_score'
    show_score.short_description = 'Score'

    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Edital',
            'Candidato',
            'Disciplina de Ingresso',
            'Disciplina',
            'Data de Início do Exercício no Cargo',
            'Data Usada para Cálculo do Tempo de Serviço',
            'Tempo de Serviço no Cargo',
            'Tempo de Serviço no Cargo(Retirando Afastamentos)',
            'Texto do Recurso',
            'Confirmada',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            data_referencia_edital = datetime.date.today()
            if obj.edital.inicio_resultados:
                data_referencia_edital = obj.edital.inicio_inscricoes.date()
            tempo_servico_no_cargo = obj.servidor.tempo_servico_no_cargo(data_referencia=data_referencia_edital)
            tempo_servico_no_cargo_via_pca = obj.servidor.tempo_servico_no_cargo_via_pca(data_referencia=data_referencia_edital)
            row = [
                idx + 1,
                obj.edital,
                obj.servidor,
                obj.servidor.disciplina_ingresso,
                obj.disciplina,
                obj.servidor.data_inicio_exercicio_no_cargo,
                data_referencia_edital,
                f'{format_(tempo_servico_no_cargo)} - {tempo_servico_no_cargo.days} dias',
                f'{format_(tempo_servico_no_cargo_via_pca)} - {tempo_servico_no_cargo_via_pca.days} dias',
                obj.recurso_texto,
                obj.confirmada,
            ]
            rows.append(row)
        return rows


admin.site.register(Inscricao, InscricaoAdmin)


class CriterioClassificacaoAdmin(ModelAdminPlus):
    list_display = ['nome', 'descricao', 'ativo']
    search_fields = ['nomedescricao']
    list_filter = ['nome', 'ativo']
    exclude = ['atualizado_por', 'atualizado_em']

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(CriterioClassificacao, CriterioClassificacaoAdmin)


class ServidorDataInicioExercicioRemocaoInternaAdmin(ModelAdminPlus):
    list_display = ['servidor', 'data_inicio_exercicio', 'get_qtd_dias', 'atualizado_por', 'atualizado_em']
    search_fields = ['servidor__matricula', 'servidor__pessoa_fisica__nome', 'data_inicio_exercicio']
    exclude = ['atualizado_por', 'atualizado_em']

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def get_qtd_dias(self, obj):
        ultima_inscricao_validada = Inscricao.objects.filter(servidor=obj.servidor, validado_por__isnull=False).last()
        if ultima_inscricao_validada:
            return tempo_servico_no_cargo_em_dias(ultima_inscricao_validada, ultima_inscricao_validada.edital.inicio_inscricoes.date())
        return '-'

    get_qtd_dias.short_description = 'Tempo Serviço (Dias)'


admin.site.register(ServidorDataInicioExercicioRemocaoInterna, ServidorDataInicioExercicioRemocaoInternaAdmin)


class EditalCriterioClassificacaoAdmin(ModelAdminPlus):
    list_display = ['edital', 'criterio_classificacao']
    search_fields = ['criterio_classificacao__nomeedital__titulo']
    exclude = ['edital', 'atualizado_por', 'atualizado_em']
    form = EditalCriterioClassificacaoForm

    def save_model(self, request, obj, form, change):
        edital_id = request.GET.get('edital')
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.edital_id = edital_id
        obj.save()

    def has_add_permission(self, request, obj=None):
        # TODO REVISAR
        has_add_permission = super().has_add_permission(request)
        edital = None
        edital_id = request.GET.get('edital')
        if edital_id:
            edital = Edital.objects.filter(pk=edital_id).first()

        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador'])
        # has_add_permission = has_add_permission and (request.user in obj.coordenadores.all() or request.user.is_superuser or eh_administrador_remanejamento)
        eh_coordenador = False
        if obj:
            eh_coordenador = request.user in obj.edital.coordenadores.all()
        elif edital:
            eh_coordenador = request.user in edital.coordenadores.all()
        has_add_permission = eh_coordenador or request.user.is_superuser or eh_administrador_remanejamento

        return has_add_permission

    def has_delete_permission(self, request, obj=None):
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador'])
        if obj:
            return request.user in obj.edital.coordenadores.all() or request.user.is_superuser or eh_administrador_remanejamento


admin.site.register(EditalCriterioClassificacao, EditalCriterioClassificacaoAdmin)


class InscricaoContempladaAdmin(ModelAdminPlus):
    list_display = ['inscricao', 'get_edital', 'get_campus_origem_sigla_ajustado', 'get_campus_destino_sigla_ajustado', 'situacao', 'justificativa']
    search_fields = ['inscricao__servidor__pessoa_fisica__nome', 'inscricao__servidor__matricula']
    list_filter = [
        'campus_origem',
        'campus_destino',
        'situacao',
        'inscricao__edital',
    ]
    exclude = ['processamento_resultado', 'atualizado_por', 'atualizado_em']
    form = EditalCriterioClassificacaoForm

    def get_edital(self, obj):
        return obj.inscricao.edital

    get_edital.short_description = 'Edital'

    def get_campus_origem_sigla_ajustado(self, obj):
        return obj.campus_origem_sigla_ajustado

    get_campus_origem_sigla_ajustado.short_description = 'Campus de Origem'

    def get_campus_destino_sigla_ajustado(self, obj):
        return obj.campus_destino_sigla_ajustado

    get_campus_destino_sigla_ajustado.short_description = 'Campus de Destino'

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador'])
        if obj:
            return request.user.is_superuser or eh_administrador_remanejamento


admin.site.register(InscricaoContemplada, InscricaoContempladaAdmin)


class AfastamentoRemocaoInternaAdmin(ModelAdminPlus):
    list_display = ['afastamento', 'impeditivo', 'desconta_exercicio']
    search_fields = ['afastamento']
    exclude = ['atualizado_por', 'atualizado_em']
    form = AfastamentoRemocaoInternaForm

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def has_add_permission(self, request, obj=None):
        has_add_permission = super().has_add_permission(request)
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador', 'Coordenador de Remanejamento'])
        has_add_permission = request.user.is_superuser or eh_administrador_remanejamento
        return has_add_permission

    def has_delete_permission(self, request, obj=None):
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador', 'Coordenador de Remanejamento'])
        return request.user.is_superuser or eh_administrador_remanejamento


admin.site.register(AfastamentoRemocaoInterna, AfastamentoRemocaoInternaAdmin)


class ServidorTempoAdicionalRemocaoInternaAdmin(ModelAdminPlus):
    list_display = ['servidor', 'data_inicio', 'data_fim', 'quantidade_dias', 'atualizado_por', 'atualizado_em']
    search_fields = ['servidor__matricula', 'servidor__pessoa_fisica__nome']
    exclude = ['atualizado_por', 'atualizado_em']

    def has_add_permission(self, request, obj=None):
        has_add_permission = super().has_add_permission(request)
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador', 'Coordenador de Remanejamento'])
        has_add_permission = request.user.is_superuser or eh_administrador_remanejamento
        return has_add_permission

    def has_delete_permission(self, request, obj=None):
        eh_administrador_remanejamento = in_group(request.user, ['remanejamento Administrador', 'Coordenador de Remanejamento'])
        return request.user.is_superuser or eh_administrador_remanejamento


admin.site.register(ServidorTempoAdicionalRemocaoInterna, ServidorTempoAdicionalRemocaoInternaAdmin)
