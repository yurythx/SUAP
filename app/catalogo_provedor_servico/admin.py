import datetime
import json
import textwrap

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import mark_safe

from catalogo_provedor_servico.forms import ServicoGerenteEquipeLocalForm, ServicoGerenteFormFactory
from catalogo_provedor_servico.models import ServicoGerenteEquipeLocal, TemplateNotificaGovBR
from comum.models import Vinculo
from djtools.contrib.admin import ModelAdminPlus, TabularInlinePlus
from djtools.templatetags.filters import in_group, status
from rh.models import UnidadeOrganizacional

from .forms import AtribuirAvaliadorForm
from .models import (
    RegistroAcompanhamentoGovBR,
    RegistroAvaliacaoGovBR,
    RegistroNotificacaoGovBR,
    Servico,
    ServicoEquipe,
    Solicitacao,
    SolicitacaoEtapa,
)


class ServicoGerenteEquipeLocalInline(TabularInlinePlus):
    form = ServicoGerenteEquipeLocalForm
    model = ServicoGerenteEquipeLocal
    extra = 0


class ServicoAdmin(ModelAdminPlus):
    search_fields = ('id_servico_portal_govbr', 'titulo')
    list_display = (
        'id_servico_portal_govbr',
        'titulo',
        'descricao',
        'ativo',
        'icone',
    )
    list_filter = ('ativo',)
    list_display_icons = True
    inlines = [ServicoGerenteEquipeLocalInline]

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        eh_gerente_local = self.request.user.has_perm('catalogo_provedor_servico.eh_gerente_local_catalogo')
        eh_gerente_sistemico = self.request.user.has_perm('catalogo_provedor_servico.eh_gerente_sistemico_catalogo')
        if eh_gerente_local or eh_gerente_sistemico:
            list_display += ('get_acoes',)
        return list_display

    def get_acoes(self, obj):
        txt = ''
        eh_gerente_local = self.request.user.has_perm('catalogo_provedor_servico.eh_gerente_local_catalogo')
        eh_gerente_sistemico = self.request.user.has_perm('catalogo_provedor_servico.eh_gerente_sistemico_catalogo')
        if eh_gerente_sistemico or (eh_gerente_local and obj.servicogerenteequipelocal_set.filter(vinculo=self.request.user.get_vinculo()).exists()):
            obj.servicogerenteequipelocal_set.filter(vinculo=self.request.user.get_vinculo()).exists()
            url = reverse('gerenciar_equipe_servico_catalogo', args=(obj.pk,))
            txt += f'<a class="btn" href="{url}">Gerenciar Equipe</a>'
        if eh_gerente_sistemico:
            url = reverse('gerenciar_gerente_equipe_servico_catalogo', args=(obj.pk,))
            txt += f'<a class="btn" href="{url}">Gerenciar Gerentes Equipe Local</a>'
        return mark_safe(txt)

    get_acoes.short_description = 'Opções'

    def get_form(self, request, obj=None, **kwargs):
        formulario = super().get_form(request, obj, **kwargs)
        vinculo = request.user.get_vinculo()
        if request.user.has_perm('catalogo_provedor_servico.eh_gerente_sistemico_catalogo'):
            return formulario
        if obj and not obj.servicogerenteequipelocal_set.filter(vinculo=vinculo).values_list('campus', flat=True):
            return formulario
        return ServicoGerenteFormFactory(obj)


admin.site.register(Servico, ServicoAdmin)


class SolicitacaoEtapaInline(admin.StackedInline):
    model = SolicitacaoEtapa
    readonly_fields = ('get_resumo_dados_formulario', 'get_links_arquivos_formulario')
    exclude = ['dados']

    def get_resumo_dados_formulario(self, obj):
        """
        Este método retorna um resumo dos dados inseridos pelo cidadão em cada etapa da solicitação. Neste resumo não
        estão inclusos os arquivos por questão de desempenho, pois exibir a string base 64 que representa o arquivo é
        muito custoso pros navegadores.

        :param obj: SolicitacaoEtapa
        :return: html contendo um resumodo dos dados inseridos.
        """
        dados = json.loads(obj.dados)
        resumo_dados_formulario = []
        for item in dados['formulario']:
            if item['type'] != 'file':
                resumo_dados_formulario.append('<strong>{} ({})</strong>: {}'.format(item['label'], item['name'], item['value']))
        return mark_safe('<br/>'.join(resumo_dados_formulario))

    get_resumo_dados_formulario.short_description = 'Resumo dos Dados'
    get_resumo_dados_formulario.allow_tags = True

    def get_links_arquivos_formulario(self, obj):
        dados = json.loads(obj.dados)
        formulario = dados['formulario']
        arquivos_links = []
        link_base = (
            '<a href="data:{arquivo_tipo};base64,{arquivo_str_b64}" download="{arquivo_nome}" target="_blank">{arquivo_nome} ({arquivo_tamanho})</a>'
        )
        for item in formulario:
            if item['type'] == 'file':
                arquivo_nome = '{}.{}'.format(item['label'], item['value_content_type'].split('/')[-1])

                arquivo_tamanho = round(item['value_size_in_bytes'] / 1024.0, 2)
                if arquivo_tamanho <= 1024:
                    arquivo_tamanho = f'{arquivo_tamanho} KB'
                else:
                    arquivo_tamanho = f'{round(arquivo_tamanho / 1024.0, 2)} MB'

                arquivos_links.append(
                    link_base.format(
                        arquivo_str_b64=item['value'],
                        arquivo_nome=arquivo_nome,
                        arquivo_tipo=item['value_content_type'],
                        arquivo_tamanho=arquivo_tamanho,
                    )
                )
        if arquivos_links:
            return mark_safe('<br/>'.join(arquivos_links))
        return '(Nenhum)'

    get_links_arquivos_formulario.short_description = 'Arquivos Anexados'
    get_links_arquivos_formulario.allow_tags = True


class CampusFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'uo'

    def lookups(self, request, model_admin):
        user = request.user
        vinculo = user.get_vinculo()
        usuario_pode_ver_solicitacoes_de_todas_uos = in_group(request.user, 'Gerente Sistemico do Catalogo Digital') or user.is_superuser
        queryset = UnidadeOrganizacional.objects.suap().filter(solicitacoes__isnull=False)
        if not usuario_pode_ver_solicitacoes_de_todas_uos:
            queryset = queryset.filter(pk__in=vinculo.servicoequipe_set.all().values_list('campus_id', flat=True))

        return queryset.order_by('nome').distinct().values_list('id', 'nome')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(uo__id=self.value())
        return queryset


class ServicoFilter(admin.SimpleListFilter):
    title = 'Serviço'
    parameter_name = 'servico'

    def lookups(self, request, model_admin):
        vinculo = request.user.get_vinculo()
        servicos = Servico.objects.filter(ativo=True, servicoequipe__vinculo=vinculo).distinct()
        return servicos.order_by('titulo').values_list('id', 'titulo')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(servico__id=self.value())
        return queryset


class ServicoResponsavelFilter(admin.SimpleListFilter):
    title = 'Responsável'
    parameter_name = 'vinculo_responsavel'

    def lookups(self, request, model_admin):
        servicos = Servico.objects.filter(ativo=True)
        equipes = ServicoEquipe.objects.filter(servico__in=servicos)

        responsaveis = Vinculo.objects.filter(Q(pk__in=equipes.values_list('vinculo__id', flat=True)) | Q(pk=request.user.get_vinculo().pk))
        responsaveis = responsaveis.distinct()
        retorno = [('nenhum', 'Nenhum')]
        [retorno.append(responsavel) for responsavel in responsaveis.values_list('id', 'pessoa__nome')]
        return retorno

    def queryset(self, request, queryset):
        if self.value():
            if str(self.value()) == 'nenhum':
                queryset = queryset.filter(vinculo_responsavel__isnull=True)
            else:
                try:
                    queryset = queryset.filter(vinculo_responsavel_id=self.value())
                except Exception:
                    pass
        return queryset


class SolicitacaoAdmin(ModelAdminPlus):
    inlines = [SolicitacaoEtapaInline]

    search_fields = ['servico__titulo', 'cpf', 'extra_dados', 'nome']
    list_display = (
        'servico',
        'cpf',
        'nome',
        'get_informacoes_extras',
        'data_criacao',
        'data_ultima_atualizacao',
        'get_status',
        'get_responsavel',
        'uo',
    )
    list_filter = ('status', ServicoFilter, ServicoResponsavelFilter, CampusFilter)
    date_hierarchy = 'data_ultima_atualizacao'
    list_filter_multiple_choices = ('status',)
    list_display_icons = True

    actions = [
        'atribuicao_avaliador',
    ]
    ordering = ('-data_ultima_atualizacao',)
    actions_on_top = True
    actions_on_bottom = True
    export_to_xls = True

    def get_responsavel(self, obj):
        if obj.vinculo_responsavel:
            return obj.vinculo_responsavel.relacionamento

    get_responsavel.short_description = 'Responsável'
    get_responsavel.admin_order_field = 'vinculo_responsavel'

    def get_status(self, obj):
        return status(obj.get_status_display())

    get_status.short_description = 'Situação'
    get_status.admin_order_field = 'status'

    def get_informacoes_extras(self, obj):
        return mark_safe(obj.get_extra_dados_html())

    get_informacoes_extras.short_description = 'Informações Extras'

    # TODO: Rever esta action, pois ela não deixa claro ao usuário qual registro foi atribuído ou não com sucesso.
    @transaction.atomic()
    def atribuicao_avaliador(self, request, queryset):
        if not in_group(request.user, 'Gerente Local do Catalogo Digital'):
            return PermissionDenied

        if queryset.count() > 1:
            if queryset.order_by().values('servico').distinct().count() > 1:
                self.message_user(request, 'Não é possível realizar a atribuição de avaliador. A seleção contem mais de um serviço. ')
                return

        form = AtribuirAvaliadorForm(
            queryset=queryset,
            request=request,
            initial={'action': request.POST.getlist('action'), '_selected_action': request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)},
        )

        if request.POST.get('avaliador'):
            form = AtribuirAvaliadorForm(request.POST, queryset=queryset, request=request)

            if form.is_valid():
                processados = 0
                nao_processados = 0
                for solicitacao in queryset:
                    if solicitacao.status in [*Solicitacao.STATUS_DEFINITIVOS, Solicitacao.STATUS_INCOMPLETO]:
                        nao_processados += 1
                        continue

                    try:
                        solicitacao.atribuir_responsavel(
                            vinculo_atribuinte=request.user.get_vinculo(),
                            vinculo_responsavel=form.cleaned_data.get('avaliador'),
                            data_associacao_responsavel=datetime.datetime.now(),
                            instrucao=form.cleaned_data.get('instrucao'),
                        )
                        solicitacao.save()
                        processados += 1
                    except Exception:
                        nao_processados += 1
                        continue

                mensagem = f'Foram processados {processados} solicitação(ões).'
                if nao_processados > 0:
                    mensagem = f'{mensagem} E não foram processados {nao_processados}.'

                self.message_user(request, mensagem)
                return
        else:
            context = {'title': 'Atribuição de Avaliador a Solicitação', 'form': form, 'solicitacoes': queryset}

            return render(request=request, template_name='atribuicao_avaliador.html', context=context)

    atribuicao_avaliador.short_description = 'Atribuir Avaliador'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not in_group(request.user, 'Gerente Local do Catalogo Digital'):
            actions.pop('atribuicao_avaliador', None)
        return actions

    def get_queryset(self, request):
        user = request.user
        vinculo = user.get_vinculo()
        queryset = super().get_queryset(request)
        usuario_pode_ver_solicitacoes_de_todas_uos = in_group(request.user, 'Gerente Sistemico do Catalogo Digital') or user.is_superuser
        if not usuario_pode_ver_solicitacoes_de_todas_uos:
            queryset = queryset.filter(servico__servicoequipe__vinculo=vinculo, uo=F('servico__servicoequipe__campus')).distinct()
        return queryset

    def get_action_bar(self, request, remove_add_button=False):
        items = super().get_action_bar(request, remove_add_button)
        if settings.DEBUG:
            items.append(
                {
                    'url': '/catalogo_provedor_servico/apagar_atendimento/',
                    'label': 'Apagar Atendimentos (Ambiente de Desenvolvimento)',
                    'css_class': 'popup danger no-confirm',
                }
            )
        return items

    def has_change_permission(self, request, obj=None):
        return bool(obj and obj.status != Solicitacao.STATUS_ATENDIDO)


admin.site.register(Solicitacao, SolicitacaoAdmin)


class RegistroAcompanhamentoGovBRAdmin(ModelAdminPlus):
    list_display = ('payload', 'status', 'tipo', 'data_criacao')
    list_filter = ('status', 'data_criacao')


admin.site.register(RegistroAcompanhamentoGovBR, RegistroAcompanhamentoGovBRAdmin)


class RegistroNotificacaoGovBRAdmin(ModelAdminPlus):
    list_display = ('get_resposta', 'tipo', 'enviada')
    ordering = ('-id',)
    search_fields = ('response_content',)
    list_filter = ('tipo', 'enviada')
    list_display_icons = True

    def get_resposta(self, obj):
        lista = textwrap.wrap(str(obj.response_content), width=100)

        return ' '.join(lista)


admin.site.register(RegistroNotificacaoGovBR, RegistroNotificacaoGovBRAdmin)


class RegistroAvaliacaoGovBRAdmin(ModelAdminPlus):
    list_display = ('solicitacao', 'avaliado', 'notificado_por_email')
    ordering = ('-id',)
    search_fields = ('solicitacao',)
    list_filter = ('avaliado', 'notificado_por_email')
    list_display_icons = True


admin.site.register(RegistroAvaliacaoGovBR, RegistroAvaliacaoGovBRAdmin)


class TemplateNotificaGovBRAdmin(ModelAdminPlus):
    list_display = ('id_template', 'tipo_notificacao')
    ordering = ('-id',)
    search_fields = ('id_template',)
    list_filter = ('canal_notificacao',)
    list_display_icons = True


admin.site.register(TemplateNotificaGovBR, TemplateNotificaGovBRAdmin)
