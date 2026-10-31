from django.contrib import admin
from django.db.models import Exists, OuterRef, QuerySet
from django.http import HttpRequest
from django.utils.safestring import mark_safe

from comum.models import Vinculo
from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group
from djtools.templatetags.tags import icon
from djtools.utils import httprr
from eventos.enums import SituacaoSubmissao
from eventos.forms import AtendimentoPublicoForm, AtividadeEventoForm, BannerForm, EventoForm, InternacionalizacaoForm, TipoParticipanteForm
from eventos.models import (
    AvaliacaoSubmissao,
    AreaTematica,
    AssuntoAtendimento,
    AtendimentoPublico,
    AtividadeEvento,
    Banner,
    ClassificacaoEvento,
    Dimensao,
    Espacialidade,
    Evento,
    Internacionalizacao,
    MotivoAtendimento,
    Natureza,
    Participante,
    PorteEvento,
    PublicoAlvoEvento,
    PublicoAtendimento,
    SituacaoAtendimento,
    Submissao,
    SubtipoEvento,
    TipoAtendimento,
    TipoAtividade,
    TipoEvento,
    TipoModalidade,
    TipoParticipacao,
    TipoParticipante,
    VersaoSubmissao,
)


class NaturezaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)


admin.site.register(Natureza, NaturezaAdmin)


class AreaTematicaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('titulo', 'ativa', 'evento')
    list_filter = ('ativa',)
    search_fields = ('titulo', 'evento__nome')


admin.site.register(AreaTematica, AreaTematicaAdmin)


class TipoModalidadeAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('titulo', 'ativa', 'evento')
    list_filter = ('ativa',)
    search_fields = ('titulo',)


admin.site.register(TipoModalidade, TipoModalidadeAdmin)


class DimensaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'get_avaliadores_locais', 'get_avaliadores_sistemicos')

    def get_avaliadores_locais(self, obj):
        lista = ['<ul>']
        for grupo in obj.grupos_avaliadores_locais.all():
            lista.append(f'<li>{grupo}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_avaliadores_locais.short_description = 'Avaliadores Locais'

    def get_avaliadores_sistemicos(self, obj):
        lista = ['<ul>']
        for grupo in obj.grupos_avaliadores_sistemicos.all():
            lista.append(f'<li>{grupo}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_avaliadores_sistemicos.short_description = 'Avaliadores Sistêmicos'


admin.site.register(Dimensao, DimensaoAdmin)


class TipoEventoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)


admin.site.register(TipoEvento, TipoEventoAdmin)


class SubtipoEventoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = 'nome', 'tipo', 'detalhamento', 'multiplas_atividades'
    list_filter = 'tipo', 'multiplas_atividades'


admin.site.register(SubtipoEvento, SubtipoEventoAdmin)


class EspacialidadeAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'ambiente_virtual')


admin.site.register(Espacialidade, EspacialidadeAdmin)


class ClassificacaoEventoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'detalhamento')


admin.site.register(ClassificacaoEvento, ClassificacaoEventoAdmin)


class PorteEventoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'detalhamento')


admin.site.register(PorteEvento, PorteEventoAdmin)


class PublicoAlvoEventoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'ativo')


admin.site.register(PublicoAlvoEvento, PublicoAlvoEventoAdmin)


class TipoParticipacaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'ch_organizacao', 'permite_inscricao_direta')


admin.site.register(TipoParticipacao, TipoParticipacaoAdmin)


class TipoAtividadeAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)


admin.site.register(TipoAtividade, TipoAtividadeAdmin)


class TipoParticipanteInline(admin.StackedInline):
    model = TipoParticipante
    form = TipoParticipanteForm
    extra = 1
    readonly_fields = ()  # 'preview',
    verbose_name = 'Tipo de Participação'
    verbose_name_plural = 'Tipo de Participações'
    fieldsets = (
        (
            '',
            {
                'fields': (
                    'evento',
                    ('tipo_participacao', 'limite_inscricoes'),
                    'modelo_certificado',
                    'permite_inscricao_direta',
                    ('data_inicio_inscricoes', 'hora_inicio_inscricoes'),
                    ('data_fim_inscricoes', 'hora_fim_inscricoes'),
                )
            },
        ),
    )

    def preview(self, obj):
        return mark_safe('<button class="btn preview-certificado">Testar Certificado</button>')

    preview.short_description = ''


class AtividadeEventoInline(admin.StackedInline):
    model = AtividadeEvento
    extra = 1
    exclude = ('participantes',)
    form = AtividadeEventoForm
    fieldsets = (('', {'fields': ('evento', 'tipo', 'descricao', ('data', 'hora', 'data_fim', 'hora_fim'), ('ch', 'limite_inscricoes'))}),)


class InternacionalizacaoInline(admin.StackedInline):
    model = Internacionalizacao
    extra = 1
    form = InternacionalizacaoForm


class AvaliacaoTrabalhosFilter(admin.SimpleListFilter):
    title = 'Avaliação de trabalhos'
    parameter_name = 'avaliacao_trabalhos'

    def lookups(self, request: HttpRequest, model_admin: ModelAdminPlus) -> tuple[tuple[str, str], ...]:
        return (('pendente', 'Com avaliações pendentes'),)

    def queryset(self, request: HttpRequest, queryset: QuerySet[Evento]) -> QuerySet[Evento]:
        if self.value() != 'pendente':
            return queryset

        avaliacoes_pendentes = AvaliacaoSubmissao.objects.filter(
            versao__submissao__modalidade__evento=OuterRef('pk'),
            nota__isnull=True,
        ).exclude(versao__submissao__situacao=SituacaoSubmissao.REMOVIDO_DUPLICIDADE)
        return queryset.filter(Exists(avaliacoes_pendentes))


class EventoAdmin(ModelAdminPlus):
    list_display_icons = False
    list_display_links = None
    list_display = ('get_acoes', 'nome', 'campus', 'local', 'get_dimensoes', 'data_inicio', 'submetido', 'deferido', 'ativo', 'finalizado')
    search_fields = ('nome', 'apresentacao')
    list_filter = (
        CustomTabListFilter,
        AvaliacaoTrabalhosFilter,
        'dimensoes',
        'classificacao',
        'espacialidades',
        'tipo',
        'subtipo',
        'campus',
        'capacitacao',
        'possui_cunho_social',
        'deferido',
        'finalizado',
        'ativo',
    )
    date_hierarchy = 'data_inicio'
    form = EventoForm
    show_count_on_tabs = True
    list_per_page = 25
    show_tab_any_data = False

    fieldsets = (
        (
            'Dados gerais',
            {'fields': ('nome', 'dimensoes', 'apresentacao', 'imagem', 'site', 'campus', 'recursos', 'capacitacao', 'possui_cunho_social')},
        ),
        ('Coordenação e Organização', {'fields': ('coordenador', 'setor', 'organizadores')}),
        ('Realização', {'fields': ('local', ('hora_inicio', 'hora_fim'), ('data_inicio', 'data_fim'))}),
        (
            'Inscrição',
            {'fields': ('termo_aceite_condicoes',)},
        ),
        (
            'Configurações',
            {
                'fields': (
                    ('inscricao_publica', 'confirmacao_automatica_inscricao'),
                    ('gera_certificado', 'exigir_avaliacao_para_certificado'),
                    ('registrar_presenca_online', 'utilizar_qr_code'),
                    'gerencia_pagina_institucional',
                )
            },
        ),
        ('Carga Horária', {'fields': (('carga_horaria',))}),
        ('Classificação', {'fields': ('classificacao', 'espacialidades', 'porte', 'tipo', 'subtipo', 'publico_alvo')}),
    )

    def get_dimensoes(self, obj):
        dimensoes = ['<ul>']
        for dimensao in obj.dimensoes.all():
            dimensoes.append(f'<li>{dimensao}</li>')
        dimensoes.append('</ul>')
        return mark_safe(' '.join(dimensoes))

    get_dimensoes.short_description = 'Dimensões'

    def get_opcoes(self, obj):
        opcoes = []
        if self.get_tab_corrente() == 'tab_participante':
            opcoes.append('<ul class="action-bar">')
            minhas_participacoes = obj.participantes.filter(cpf=self.request.user.get_profile().cpf).order_by('nome')
            for participante in minhas_participacoes:
                if participante.codigo_geracao_certificado:
                    if participante.tipo and participante.tipo.tipo_participacao:
                        tipo_participacao = participante.tipo.tipo_participacao
                        opcoes.append(
                            f'<li><a href="{participante.get_url_download_certificado()}" class="btn default">Imprimir certificado {tipo_participacao.descricao}</a></li>'
                        )
                    else:
                        opcoes.append(
                            f'<li><a href="{participante.get_url_download_certificado()}" class="btn default">Imprimir certificado</a></li>'
                        )
            opcoes.append('</ul>')
        return mark_safe(' '.join(opcoes))

    get_opcoes.short_description = 'Opções'

    def get_action_bar(self, request, remove_add_button=False):
        action_bar = super().get_action_bar(request, remove_add_button=remove_add_button)
        action_bar.append({'url': '/static/eventos/Modelo_de_projeto_de_eventos.docx', 'label': 'Baixar Arquivo de Projeto', 'css_class': 'default'})
        return action_bar

    def get_list_display(self, request):
        default_list_display = super().get_list_display(request)
        if self.get_tab_corrente() == 'tab_participante':
            return ('get_acoes', 'nome', 'campus', 'local', 'data_inicio', 'get_opcoes')
        if in_group(request.user, 'Coordenador de Comunicação Sistêmico'):
            return (*default_list_display, 'cancelado')

        return default_list_display

    def get_acoes(self, obj):
        out = [icon('view', obj.get_absolute_url())]
        if obj.pode_gerenciar(self.request.user):
            out.append(icon('edit', f'/admin/eventos/evento/{obj.id}/'))
        return mark_safe(''.join(out))

    get_acoes.short_description = 'Ações'

    def response_add(self, request, obj):
        return httprr(f'/eventos/evento/{obj.pk}/', 'Ação realizada com sucesso.')

    def response_change(self, request, obj):
        return self.response_add(request, obj)

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        return retorno and (not obj or obj.pode_gerenciar(request.user))

    def tab_ativos(self, request, queryset):
        return queryset.filter(ativo=True, deferido=True).exclude(cancelado=True)

    tab_ativos.short_description = 'Ativos'

    def tab_aguardando_minha_aprovacao(self, request, queryset):
        dimensoes = Dimensao.objects.filter(grupos_avaliadores_locais__in=request.user.groups.values_list('pk', flat=True))
        return (
            queryset.filter(submetido=True, deferido__isnull=True, dimensoes__in=dimensoes, campus=request.user.get_vinculo().setor.uo)
            .exclude(cancelado=True)
            .distinct()
        )

    tab_aguardando_minha_aprovacao.short_description = 'Aguardando minha aprovação'

    def tab_aguardando_aprovacao(self, request, queryset):
        dimensoes = Dimensao.objects.filter(grupos_avaliadores_sistemicos__in=request.user.groups.values_list('pk', flat=True))
        return queryset.filter(deferido__isnull=True, dimensoes__in=dimensoes).exclude(cancelado=True).distinct()

    tab_aguardando_aprovacao.short_description = 'Aguardando aprovação'

    def tab_sob_minha_organizacao(self, request, queryset):
        pks = Participante.objects.filter(tipo__tipo_participacao__descricao='Organizador', cpf=request.user.get_profile().cpf).values_list(
            'evento_id', flat=True
        )
        return queryset.filter(pk__in=pks)

    tab_sob_minha_organizacao.short_description = 'Sob minha organização'

    def tab_sob_minha_coordenacao(self, request, queryset):
        return queryset.filter(coordenador__pessoa_fisica=request.user.get_profile())

    tab_sob_minha_coordenacao.short_description = 'Sob minha coordenação'

    def tab_todos(self, request, queryset):
        return queryset.all()

    tab_todos.short_description = 'Todos'

    def tab_participante(self, request, queryset):
        return queryset.filter(participantes__cpf=self.request.user.get_profile().cpf)

    tab_participante.short_description = 'Participante'

    def tab_campus(self, request, queryset):
        return queryset.filter(campus=get_uo(self.request.user))

    tab_campus.short_description = 'Do campus'

    def get_tabs(self, request):
        grupos_avaliadores_sistemicos = Dimensao.objects.values_list('grupos_avaliadores_sistemicos', flat=True)
        is_avaliador_sistemico = request.user.groups.filter(pk__in=grupos_avaliadores_sistemicos)
        grupos_avaliadores_locais = Dimensao.objects.values_list('grupos_avaliadores_locais', flat=True)
        is_avaliador_local = request.user.groups.filter(pk__in=grupos_avaliadores_locais)
        is_organizador = Participante.objects.filter(tipo__tipo_participacao__descricao='Organizador', cpf=request.user.get_profile().cpf).exists()
        is_coordenador = Evento.objects.filter(coordenador__pessoa_fisica_id=request.user.get_vinculo().pessoa_id).exists()
        tabs = ['tab_ativos', 'tab_participante']
        if is_avaliador_local:
            tabs.append('tab_aguardando_minha_aprovacao')
        if is_avaliador_sistemico:
            tabs.append('tab_aguardando_aprovacao')
        if is_organizador:
            tabs.append('tab_sob_minha_organizacao')
        if is_coordenador:
            tabs.append('tab_sob_minha_coordenacao')
        if in_group(request.user, 'Coordenador de Comunicação'):
            tabs.append('tab_campus')
        if in_group(request.user, 'Coordenador de Comunicação Sistêmico'):
            tabs.append('tab_todos')
        return tabs

    def render_change_form(self, request, context, **kwargs):
        context['show_save_and_continue'] = False
        return super().render_change_form(request, context, **kwargs)

    @staticmethod
    def _obter_ou_criar_tipo_participacao(descricao: str) -> TipoParticipacao:
        tipo_participacao = TipoParticipacao.objects.filter(descricao=descricao).order_by('pk').first()
        if tipo_participacao:
            return tipo_participacao
        return TipoParticipacao.objects.create(descricao=descricao)

    @staticmethod
    def _obter_ou_criar_tipo_participante(evento: Evento, tipo_participacao: TipoParticipacao) -> TipoParticipante:
        tipo_participante = TipoParticipante.objects.filter(evento=evento, tipo_participacao=tipo_participacao).order_by('pk').first()
        if tipo_participante:
            return tipo_participante
        return TipoParticipante.objects.create(evento=evento, tipo_participacao=tipo_participacao)

    @staticmethod
    def _obter_ou_criar_participante(evento: Evento, vinculo: Vinculo, tipo: TipoParticipante) -> Participante:
        participante = Participante.objects.filter(evento=evento, vinculo=vinculo, tipo=tipo).order_by('pk').first()
        if participante:
            return participante
        return Participante.objects.create(
            evento=evento,
            vinculo=vinculo,
            tipo=tipo,
            nome=vinculo.pessoa.nome,
            cpf=vinculo.pessoa.pessoafisica.cpf,
            email=vinculo.email_notificacao,
            inscricao_validada=True,
        )

    def save_related(self, request: HttpRequest, form: EventoForm, formsets: object, change: bool) -> None:
        super().save_related(request, form, formsets, change)
        evento = form.instance

        tipo_participacao_participante = self._obter_ou_criar_tipo_participacao('Participante')
        # Tipo Participação 'Participante' é obrigatório, irá criar caso não exista.
        self._obter_ou_criar_tipo_participante(evento, tipo_participacao_participante)

        tipo_participacao_organizador = self._obter_ou_criar_tipo_participacao('Organizador')
        # Tipo Participação 'Organizador' é obrigatório, irá criar caso não exista.
        tipo_participante_organizador = self._obter_ou_criar_tipo_participante(evento, tipo_participacao_organizador)

        tipo_participacao_coordenador = self._obter_ou_criar_tipo_participacao('Coordenador')
        # Tipo Participação 'Coordenador' é obrigatório, irá criar caso não exista.
        tipo_participante_coordenador = self._obter_ou_criar_tipo_participante(evento, tipo_participacao_coordenador)

        for vinculo in form.cleaned_data['organizadores']:
            participante = self._obter_ou_criar_participante(evento, vinculo, tipo_participante_organizador)
            participante.checar_publico_alvo()
            participante.save()

        coordenador_obj = form.cleaned_data.get('coordenador')
        if coordenador_obj and hasattr(coordenador_obj, 'pessoa_fisica') and coordenador_obj.pessoa_fisica:
            vinculo = coordenador_obj.get_vinculo()
            if vinculo:  # Garante que o vínculo foi encontrado
                coordenador = self._obter_ou_criar_participante(evento, vinculo, tipo_participante_coordenador)
                coordenador.checar_publico_alvo()
                coordenador.save()


admin.site.register(Evento, EventoAdmin)


class ParticipanteAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('nome', 'email', 'evento', 'data_cadastro')
    search_fields = ('nome', 'email')
    list_filter = ('evento',)
    date_hierarchy = 'data_cadastro'


admin.site.register(Participante, ParticipanteAdmin)


class BannerAdmin(ModelAdminPlus):
    form = BannerForm
    list_display_icons = True
    list_display = ('titulo', 'data_inicio', 'data_termino')
    search_fields = ('titulo',)
    date_hierarchy = 'data_inicio'


admin.site.register(Banner, BannerAdmin)


class TipoAtendimentoAdmin(ModelAdminPlus):
    list_display = ('descricao',)


admin.site.register(TipoAtendimento, TipoAtendimentoAdmin)


class MotivoAtendimentoAdmin(ModelAdminPlus):
    list_display = ('descricao',)


admin.site.register(MotivoAtendimento, MotivoAtendimentoAdmin)


class AssuntoAtendimentoAdmin(ModelAdminPlus):
    list_display = ('descricao',)


admin.site.register(AssuntoAtendimento, AssuntoAtendimentoAdmin)


class PublicoAtendimentoAdmin(ModelAdminPlus):
    list_display = ('descricao',)


admin.site.register(PublicoAtendimento, PublicoAtendimentoAdmin)


class SituacaoAtendimentoAdmin(ModelAdminPlus):
    list_display = ('descricao',)


admin.site.register(SituacaoAtendimento, SituacaoAtendimentoAdmin)


class AtendimentoPublicoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('data_cadastro', 'campus', 'tipo', 'motivo', 'assunto', 'publico', 'situacao')
    list_filter = ('tipo', 'motivo', 'assunto', 'publico', 'situacao')
    date_hierarchy = 'data_cadastro'
    form = AtendimentoPublicoForm

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('ae.add_tipoatendimento'):
            list_filter = ('campus', *self.list_filter)
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.add_tipoatendimento'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs


admin.site.register(AtendimentoPublico, AtendimentoPublicoAdmin)


class SubmissaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('id', 'titulo', 'modalidade', 'area_tematica')
    search_fields = ('titulo', 'id')


admin.site.register(Submissao, SubmissaoAdmin)


class VersaoSubmissaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('id', 'submissao__titulo', 'numero', 'arquivo', 'comentario', 'enviado_em')
    search_fields = ('submissao__titulo', 'submissao__id')


admin.site.register(VersaoSubmissao, VersaoSubmissaoAdmin)
