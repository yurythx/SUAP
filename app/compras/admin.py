import datetime

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.formats import localize
from django.utils.safestring import mark_safe

from compras.forms import CompraForm, EtapaCompraFormset, EventoForm, FaseForm, ProcessoCompraForm
from compras.models import (
    Calendario,
    CategoriaCompra,
    Compra,
    EtapaCompra,
    Evento,
    Fase,
    Nucleo,
    Processo,
    ProcessoCompra,
    ProcessoCompraCampus,
    SolicitacaoParticipacao,
    TipoEvento,
    TipoProcesso,
    EtapasProcessoCompra,
    TipoCalendario,
)
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import format_profile, status


class ProcessoCompraCampusInline(admin.StackedInline):
    model = ProcessoCompraCampus


class ProcessoCompraAdmin(ModelAdminPlus):
    form = ProcessoCompraForm
    exclude = ['status']
    inlines = [ProcessoCompraCampusInline]
    list_display = ['show_link', 'show_periodo_inclusao', 'show_tags']

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if form.cleaned_data['aplicar_todos']:
            form.instance.aplicar_todos_campus()

    def show_link(self, obj):
        return mark_safe(f'<a href="{obj.get_absolute_url()}">{obj!s}</a>')

    show_link.short_description = 'Processo de compra'

    def show_periodo_inclusao(self, obj):
        return mark_safe(f'<span class="{obj.is_em_periodo_de_inclusao()}">{localize(obj.data_inicio)} a {localize(obj.data_fim)}</span>')

    show_periodo_inclusao.admin_order_field = 'data_inicio'
    show_periodo_inclusao.short_description = 'Período para Inclusão/Validação'

    def show_tags(self, obj):
        return ', '.join([str(item) for item in obj.tags.all()])

    show_tags.short_description = 'Tags'


admin.site.register(ProcessoCompra, ProcessoCompraAdmin)


class CalendarioAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ('ativo',)
    ordering = ('descricao',)


admin.site.register(Calendario, CalendarioAdmin)


class TipoEventoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'calendario', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)


admin.site.register(TipoEvento, TipoEventoAdmin)


class EventoAdmin(ModelAdminPlus):
    form = EventoForm
    list_display = ('tipo_evento', 'get_calendario', 'data_inicio', 'data_fim', 'ativo')
    ordering = (
        'tipo_evento',
        'data_inicio',
    )
    list_filter = (
        'tipo_evento__calendario',
        'ativo',
    )
    list_display_icons = True

    def get_calendario(self, obj):
        return obj.tipo_evento.calendario.descricao

    get_calendario.short_description = 'Calendário'


admin.site.register(Evento, EventoAdmin)


class NucleoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'get_componentes', 'get_tipos_processo', 'ativo')
    ordering = (
        'descricao',
        'ativo',
    )
    list_filter = ('ativo',)
    list_display_icons = True

    def get_componentes(self, obj):
        return mark_safe(', '.join([format_profile(servidor) for servidor in obj.componentes.all()]))

    get_componentes.short_description = 'Servidores Relacionados'

    def get_tipos_processo(self, obj):
        return ', '.join([tipo.descricao for tipo in obj.tipoprocesso_set.all()])

    get_tipos_processo.short_description = 'Tipos de Processo'


admin.site.register(Nucleo, NucleoAdmin)


class TipoProcessoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'nucleo_responsavel', 'tipo_calendario', 'ativo')
    ordering = (
        'descricao',
        'ativo',
    )
    list_filter = (
        'nucleo_responsavel',
        'ativo',
    )
    list_display_icons = True


admin.site.register(TipoProcesso, TipoProcessoAdmin)


class ProcessoAdmin(ModelAdminPlus):
    list_display = ('tipo_processo', 'situacao', 'get_campi_solicitantes', 'get_opcoes')
    ordering = (
        'tipo_processo',
        'situacao',
    )
    list_filter = (
        'tipo_processo',
        'situacao',
    )
    list_display_icons = True

    def get_campi_solicitantes(self, obj):
        return obj.get_campi_solicitantes()

    get_campi_solicitantes.short_description = 'Campi que solicitaram participação'

    def get_opcoes(self, obj):
        texto = '<ul class="action-bar">'
        texto += f'<li><a href="/compras/adicionar_fase/{obj.pk}/" class="btn success">Adicionar Fase</a></li>'
        texto += f'<li><a href="/admin/compras/fase/?processo__id__exact={obj.pk}" class="btn default">Ver Fases</a></li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def has_add_permission(self, request):
        return request.user.has_perm('compras.add_processo') and (
            request.user.has_perm('compras.add_calendario') or Nucleo.objects.filter(componentes=request.user.get_relacionamento()).exists()
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('compras.add_calendario'):
            return qs
        else:
            return qs.filter(tipo_processo__nucleo_responsavel__componentes=request.user.get_relacionamento())


admin.site.register(Processo, ProcessoAdmin)


class FaseAdmin(ModelAdminPlus):
    form = FaseForm
    list_display = ('processo', 'data_inicio', 'data_fim', 'fase_inicial', 'ativo', 'get_opcoes')
    ordering = (
        'data_inicio',
        'ativo',
    )
    list_filter = (
        'processo',
        'ativo',
    )
    list_display_icons = True

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('compras.add_calendario'):
            return qs
        else:
            return qs.filter(processo__tipo_processo__nucleo_responsavel__componentes=request.user.get_relacionamento())

    def get_opcoes(self, obj):
        if obj.fase_inicial:
            texto = '<ul class="action-bar">'
            texto += f'<li><a href="/admin/compras/solicitacaoparticipacao/?fase__id__exact={obj.pk}" class="btn default">Ver Solicitações de Participação</a></li>'
            texto += '</ul>'
            return mark_safe(texto)

    get_opcoes.short_description = 'Opções'


admin.site.register(Fase, FaseAdmin)


class SolicitacaoParticipacaoAdmin(ModelAdminPlus):
    form = FaseForm
    list_display = (
        'fase',
        'campus_solicitante',
        'solicitada_em',
        'solicitada_por',
    )
    ordering = (
        'campus_solicitante',
        'solicitada_em',
    )
    list_filter = (
        'fase',
        'campus_solicitante',
    )
    list_display_icons = True

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('compras.add_calendario'):
            return qs
        else:
            return qs.filter(fase__processo__tipo_processo__nucleo_responsavel__componentes=request.user.get_relacionamento())


admin.site.register(SolicitacaoParticipacao, SolicitacaoParticipacaoAdmin)


# Novas classes para gestão do calendário de compras


class EtapaCompraEntregaInline(admin.TabularInline):
    formset = EtapaCompraFormset
    model = EtapaCompra
    extra = 0
    max_num = len(EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES)
    fields = ('compra', 'etapa', 'data_inicio', 'data_fim')
    show_change_link = False

    def get_extra(self, request, obj=None, **kwargs):
        """
        Sobrescreve o número de formulários extra dependendo se é uma nova instância.
        """
        if obj is None:
            return len(EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES)
        return 0

    def has_add_permission(self, request, obj=None):
        return (
            request.user.has_group_cached('Gerenciador de Compras')
            or Nucleo.objects.filter(componentes=request.user.get_vinculo().relacionamento).exists()
        )

    def has_change_permission(self, request, obj=None):
        if obj:
            return request.user.has_group_cached('Gerenciador de Compras') or (
                obj.nucleo_responsavel and obj.nucleo_responsavel in Nucleo.objects.filter(componentes=request.user.get_vinculo().relacionamento)
            )
        return False

    def has_delete_permission(self, request, obj=None):
        if obj:
            return request.user.has_group_cached('Gerenciador de Compras') or (
                obj.nucleo_responsavel and obj.nucleo_responsavel in Nucleo.objects.filter(componentes=request.user.get_vinculo().relacionamento)
            )
        return False


@admin.register(Compra)
class CompraAdmin(ModelAdminPlus):
    list_display = (
        'get_objeto',
        'tipo_compra',
        'etapa_atual',
        'get_responsavel',
        'get_campi_vinculados',
        'data_abertura',
        'data_prevista_fim',
        'get_cronograma',
        'get_opcoes',
    )
    list_display_icons = True
    search_fields = (
        'processo__search_fields_optimized',
        'objeto',
        'objeto',
    )
    list_filter = (
        'processo',
        'nucleo_responsavel',
        'campus_responsavel',
        'tipo_compra',
        'categoria',
        'tipo_calendario',
        'concluido',
    )
    inlines = [EtapaCompraEntregaInline]

    form = CompraForm

    def get_changeform_initial_data(self, request):
        return {
            'data_abertura': datetime.date.today(),
            'tipo_calendario': TipoCalendario.CAMPUS,
            'campus_responsavel': request.user.get_vinculo().setor.uo,
        }

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        items.append({'url': '/compras/calendarios_processos_compras/', 'label': 'Ver Calendários de Compras'})
        return items

    def get_campi_vinculados(self, obj):
        return ', '.join({campus.sigla for campus in obj.campi_vinculados.all()})

    get_campi_vinculados.short_description = 'Campi Vinculados'

    def get_cronograma(self, obj):
        cronograma = '-'
        if obj.concluido:
            cronograma = 'Concluído'
        elif obj.data_prevista_fim and (obj.data_prevista_fim >= datetime.date.today()):
            cronograma = 'No prazo'
        else:
            cronograma = 'Atrasado'

        return status(cronograma)

    get_cronograma.short_description = 'Situação'

    def get_responsavel(self, obj):
        responsavel = '<dl>'
        if obj.nucleo_responsavel:
            responsavel = f'<dt>Núcleo:</dt><dd>{obj.nucleo_responsavel}</dd>'
        if obj.campus_responsavel:
            responsavel = f'<dt>Campus:</dt><dd>{obj.campus_responsavel}</dd>'
        responsavel += '</dl>'
        return mark_safe(responsavel)

    get_responsavel.short_description = 'Responsável'

    def get_opcoes(self, obj):
        opcoes = '<ul class="action-bar">'
        opcoes += f'<li><a href="/compras/compra/{obj.id}/cronograma/" class="btn">Cronograma</a></li>'
        if (
            self.request.user.has_group_cached('Gerenciador de Compras')
            or Nucleo.objects.filter(componentes=self.request.user.get_vinculo().relacionamento).exists()
        ):
            opcoes += f'<li><a href="/compras/compra/{obj.id}/atualizar_etapa_atual/" class="btn">Atualizar Etapa Atual</a></li>'
        if obj.processo:
            opcoes += f'<li><a class="btn default popup" href="/processo_eletronico/processo/{obj.processo.id}/">Ver processo</a></li>'
        opcoes += '</ul>'
        return mark_safe(opcoes)

    get_opcoes.short_description = 'Opções'

    def get_objeto(self, obj):
        objeto = f"<p class='mb-2'>{obj.objeto}</p><dl><dt>Tem IRP:</dt>"
        tem_irp = EtapaCompra.objects.filter(compra=obj, etapa=EtapasProcessoCompra.INTENCAO_REGISTRO_PRECO).exists()
        if tem_irp:
            objeto += '<dd>Sim</dd>'
        else:
            objeto += '<dd>Não</dd>'
        objeto += '</dl>'
        return mark_safe(objeto)

    get_objeto.short_description = 'Objeto'

    def has_add_permission(self, request, obj=None):
        return (
            request.user.has_group_cached('Gerenciador de Compras')
            or Nucleo.objects.filter(componentes=request.user.get_vinculo().relacionamento).exists()
        )

    def has_change_permission(self, request, obj=None):
        if obj and not obj.concluido:
            return request.user.has_group_cached('Gerenciador de Compras') or (
                obj.nucleo_responsavel and obj.nucleo_responsavel in Nucleo.objects.filter(componentes=request.user.get_vinculo().relacionamento)
            )
        return False

    def response_add(self, request, obj, post_url_continue=None):
        if '_continue' not in request.POST:
            return HttpResponseRedirect(reverse('admin:compras_compra_changelist'))
        return super().response_add(request, obj, post_url_continue)

    def save_model(self, request, obj, form, change):
        # Define o campus responsável como o campus de criação, se não estiver definido
        if not obj.campus_responsavel:
            obj.campus_responsavel = obj.processo.setor_criacao.uo
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Inclui o campus responsável nos campi vinculados
        if obj.campus_responsavel and obj.campus_responsavel not in obj.campi_vinculados.all():
            obj.campi_vinculados.add(obj.campus_responsavel)


@admin.register(CategoriaCompra)
class CategoriaCompraAdmin(ModelAdminPlus):
    list_display = (
        'descricao',
        'cor',
        'ativo',
    )
    list_display_icons = True
