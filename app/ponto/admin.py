import datetime
import zipfile
from io import BytesIO

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.utils.safestring import mark_safe

from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, DateRangeListFilter, ModelAdminPlus
from djtools.templatetags.tags import icon
from djtools.utils import httprr
from ponto.forms import (
    AfastamentoForm,
    LiberacaoForm,
    MaquinaForm,
    ObservacaoAdminForm,
    RecessoOpcaoForm,
    RecessoOpcaoOutroForm,
    SolicitacaoAbonoParcialGravidezForm,
)
from ponto.models import (
    AbonoChefia,
    Afastamento,
    DebitoExternoCadastro,
    Frequencia,
    HorarioCompensacao,
    Liberacao,
    Maquina,
    MaquinaLog,
    Observacao,
    RecessoOpcao,
    RecessoOpcaoEscolhida,
    SaldoExterno,
    SolicitacaoAbonoParcial,
    SolicitacaoAbonoParcialGravidez,
    TipoAfastamento,
    SolicitacaoRevisaoAbonoChefia,
)


class MaquinaAdmin(ModelAdminPlus):
    form = MaquinaForm
    ordering = ['-id']
    search_fields = ['descricao', 'ip']
    list_display = ['ip', 'descricao', 'ativo', 'get_terminais', 'versao_terminal', 'observacao', 'ultimo_log', 'testar_apis_button']
    list_filter = ['ativo', 'cliente_ponto', 'cliente_chaves', 'cliente_cadastro_impressao_digital', 'cliente_refeitorio', 'uo']
    filter_horizontal = ('predios',)

    def _build_machine_request(self, maquina: Maquina) -> HttpRequest:
        request = HttpRequest()
        request.method = 'GET'
        request.path = '/'
        request.path_info = '/'
        request.META['REMOTE_ADDR'] = maquina.ip
        request.user = AnonymousUser()
        return request

    @staticmethod
    def _campos_esperados_get_pessoas(versao: str | None) -> int:
        return 12 if versao and versao >= '1.2.0' else 10

    @staticmethod
    def _conteudo_http_response(resp: HttpResponse) -> bytes | None:
        try:
            return resp.content
        except Exception:
            arquivo = getattr(resp, 'file_to_stream', None)
            if not arquivo:
                return None

            posicao = arquivo.tell()
            try:
                arquivo.seek(0)
                return arquivo.read()
            finally:
                arquivo.seek(posicao)

    @staticmethod
    def _resumir_http_response(resp: HttpResponse) -> tuple[bool, str]:
        status = getattr(resp, 'status_code', 200)
        content = MaquinaAdmin._conteudo_http_response(resp)
        if content is None:
            return status < 400, f'HTTP {status}'

        resumo = f'HTTP {status} len={len(content)}'
        content_type = resp.get('Content-Type', '')
        if content_type != 'application/zip':
            return status < 400, resumo

        try:
            with zipfile.ZipFile(BytesIO(content)) as zip_file:
                nomes = zip_file.namelist()
                if not nomes:
                    return status < 400, f'{resumo} zip=vazio'

                primeira_linha = zip_file.read(nomes[0]).splitlines()[0]
                return status < 400, f'{resumo} zip={nomes[0]} campos={len(primeira_linha.split(b"\t"))}'
        except Exception as e:
            return False, f'{resumo} zip=erro:{type(e).__name__}'

    def _call_view_with_remote_addr(self, view_func: object, maquina: Maquina, *args: object, **kwargs: object) -> tuple[bool, str]:
        """Helper: cria um request com REMOTE_ADDR = maquina.ip e chama a view_func.
        Retorna uma tupla (ok: bool, resumo: str).
        """
        from djtools.middleware import threadlocals as tl

        request = self._build_machine_request(maquina)
        # colocar na threadlocal para as funções que usam tl.get_request()
        try:
            tl.context.request = request
        except Exception:
            try:
                # fallback: atributo direto
                tl.context.request = request
            except Exception:
                pass

        import inspect

        try:
            # detect if view_func expects positional args (e.g., request)
            sig = inspect.signature(view_func)
            params = [p for p in sig.parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            if len(params) == 0:
                # function expects no args (uses threadlocal internally)
                resp = view_func()
            else:
                resp = view_func(request, *args, **kwargs)
            # Se a view retornar um HttpResponse
            if isinstance(resp, HttpResponse):
                return self._resumir_http_response(resp)

            # Se a view retornar um dicionário (webservice functions)
            if isinstance(resp, dict):
                return True, f'OK: {resp}'

            # Qualquer outro retorno
            return True, f'OK: {type(resp)}'

        except Exception as e:
            return False, f'Erro: {type(e).__name__}: {e}'
        finally:
            # limpar threadlocal
            try:
                tl.context.request = None
            except Exception:
                pass

    def _call_func_with_remote_addr(self, func, maquina, *args, **kwargs):
        """Set a request with REMOTE_ADDR in threadlocal and call func(*args, **kwargs).
        Use this for functions that read tl.get_request() but do not accept a request parameter.
        Returns (ok: bool, resumo: str)
        """
        from djtools.middleware import threadlocals as tl

        request = self._build_machine_request(maquina)
        try:
            tl.context.request = request
        except Exception:
            try:
                tl.context.request = request
            except Exception:
                pass

        try:
            resp = func(*args, **kwargs)

            from django.http import HttpResponse

            if isinstance(resp, HttpResponse):
                status = getattr(resp, 'status_code', 200)
                content_desc = ''
                try:
                    content_desc = f'len={len(resp.content)}'
                except Exception:
                    content_desc = ''
                return True, f'HTTP {status} {content_desc}'

            if isinstance(resp, dict):
                return True, f'OK: {resp}'

            return True, f'OK: {type(resp)}'
        except Exception as e:
            return False, f'Erro: {type(e).__name__}: {e}'
        finally:
            try:
                tl.context.request = None
            except Exception:
                pass

    def get_terminais(self, obj):
        out = '<ul>'
        if obj.cliente_cadastro_impressao_digital:
            out += '<li>Cadastro</li>'
        if obj.cliente_chaves:
            out += '<li>Chaves</li>'
        if obj.cliente_ponto:
            out += '<li>Ponto</li>'
        if obj.cliente_refeitorio:
            out += '<li>Refeitório</li>'
        out += '</ul>'
        return mark_safe(out)

    get_terminais.short_description = 'Terminais'

    def testar_apis_button(self, obj):
        """Render a per-row button linking to the per-machine test view."""
        try:
            from django.urls import reverse

            url = reverse('admin:ponto_maquina_testar_apis', args=(obj.pk,))
        except Exception:
            # Fallback to a relative URL if reverse fails for any reason
            url = f'./{obj.pk}/testar_apis/'
        return mark_safe(f'<a class="btn success" href="{url}">Testar</a>')

    testar_apis_button.short_description = 'Testar APIs'
    testar_apis_button.allow_tags = True

    def get_list_display(self, request):
        """Show the testar_apis_button column only to superusers."""
        base = super().get_list_display(request)
        if request.user.is_superuser:
            return base
        # filter out the testing button for non-superusers
        return [col for col in base if col != 'testar_apis_button']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.has_group_cached('Coordenador de TI sistêmico'):
            return qs

        qs = qs.filter(uo=get_uo(request.user))
        return qs

    # --- admin extra view for single-machine testing -------------------------------------------------
    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        my_urls = [
            path('<int:pk>/testar_apis/', self.admin_site.admin_view(self.testar_apis_view), name='ponto_maquina_testar_apis'),
        ]
        return my_urls + urls

    def testar_apis_view(self, request, pk):
        """Admin view: testa APIs para uma única máquina e redireciona à página de alteração com mensagem."""
        # acesso restrito a superusers
        if not request.user.is_superuser:
            raise PermissionDenied
        from django.shortcuts import get_object_or_404, render
        from django.contrib import messages
        from django.urls import reverse
        from ponto.models import MaquinaLog

        maquina = get_object_or_404(Maquina, pk=pk)

        # Allow optional login param (to test cadastro flow)
        login = request.GET.get('login') or request.POST.get('login')
        run = request.GET.get('run') or request.POST.get('run')
        incluir_pesadas = request.GET.get('incluir_pesadas') == '1' or request.POST.get('incluir_pesadas') == '1'

        results = []
        results.append(('ping', f'ip={maquina.ip}', f'ip={maquina.ip}'))

        from ponto import views as ponto_views
        from chaves import views as chaves_views
        from comum import views as comum_views
        from comum import webservice as comum_webservice
        from ae import views as ae_views

        if run:
            # Execute the checks
            status_overall = MaquinaLog.SUCESSO

            if maquina.cliente_ponto:
                versao_terminal = maquina.versao_terminal.numero if maquina.versao_terminal else '1.3.1'
                campos_esperados = self._campos_esperados_get_pessoas(versao_terminal)
                if incluir_pesadas:
                    ok, resumo = self._call_view_with_remote_addr(ponto_views.get_dump_terminal_ponto, maquina)
                    results.append(('ponto.get_dump_terminal_ponto', 'HTTP 200 zip=tabela_terminal.copy campos=5', resumo))
                    if not ok:
                        status_overall = MaquinaLog.ERRO
                    ok, resumo = self._call_view_with_remote_addr(ponto_views.get_fotos_terminal_ponto, maquina)
                    results.append(('ponto.get_fotos_terminal_ponto', 'HTTP 200 zip válido', resumo))
                    if not ok:
                        status_overall = MaquinaLog.ERRO
                    ok, resumo = self._call_view_with_remote_addr(comum_views.get_pessoas, maquina, versao_terminal)
                    results.append(
                        (
                            'comum.get_pessoas',
                            f'HTTP 200 zip=tabela_terminal.copy campos={campos_esperados} (versão {versao_terminal})',
                            resumo,
                        )
                    )
                    if not ok:
                        status_overall = MaquinaLog.ERRO
                else:
                    results.append(('ponto.get_dump_terminal_ponto', 'HTTP 200 zip=tabela_terminal.copy campos=5', 'Não executado: API pesada'))
                    results.append(('ponto.get_fotos_terminal_ponto', 'HTTP 200 zip válido', 'Não executado: API pesada'))
                    results.append(
                        (
                            'comum.get_pessoas',
                            f'HTTP 200 zip=tabela_terminal.copy campos={campos_esperados} (versão {versao_terminal})',
                            'Não executado: API pesada',
                        )
                    )

            if maquina.cliente_refeitorio:
                ok, resumo = self._call_view_with_remote_addr(ae_views.get_pessoas, maquina)
                results.append(('ae.get_pessoas', 'HTTP 200 zip válido', resumo))
                if not ok:
                    status_overall = MaquinaLog.ERRO

            if maquina.cliente_chaves:
                ok, resumo = self._call_view_with_remote_addr(chaves_views.get_tabela_chaves, maquina)
                results.append(('chaves.get_tabela_chaves', 'HTTP 200 zip válido', resumo))
                if not ok:
                    status_overall = MaquinaLog.ERRO
                ok, resumo = self._call_view_with_remote_addr(chaves_views.get_tabela_permissoes, maquina)
                results.append(('chaves.get_tabela_permissoes', 'HTTP 200 zip válido', resumo))
                if not ok:
                    status_overall = MaquinaLog.ERRO

            if maquina.cliente_cadastro_impressao_digital:
                ok, resumo = self._call_view_with_remote_addr(comum_webservice.meu_ip, maquina)
                results.append(('comum.webservice.meu_ip', 'OK com flags da máquina', resumo))
                if not ok:
                    status_overall = MaquinaLog.ERRO
                ok, resumo = self._call_view_with_remote_addr(comum_webservice.is_terminal_cadastro, maquina)
                results.append(('comum.webservice.is_terminal_cadastro', 'OK is_terminal_cadastro=True', resumo))
                if not ok:
                    status_overall = MaquinaLog.ERRO

                # If login provided, call get_dados_pessoa to reproduce cadastro lookup
                if login:
                    ok, resumo = self._call_func_with_remote_addr(comum_webservice.get_dados_pessoa, maquina, login)
                    results.append((f'comum.webservice.get_dados_pessoa({login})', 'OK para matrícula existente/autorizada', resumo))
                    if not ok:
                        status_overall = MaquinaLog.ERRO

            # Persist a machine log
            try:
                mensagem = '\n'.join([f'{k}: esperado={esperado}; resultado={resultado}' for k, esperado, resultado in results])
                MaquinaLog.objects.create(maquina=maquina, status=status_overall, operacao='diagnostico_testar_apis', mensagem=mensagem)
            except Exception:
                pass

            messages.info(request, f'Diagnóstico executado para {maquina.ip}.')

        # Render a simple template with optional form to run
        context = {
            'maquina': maquina,
            'results': results,
            'login': login or '',
            'run': bool(run),
            'incluir_pesadas': incluir_pesadas,
            'admin_site': self.admin_site,
            'opts': self.model._meta,
            'change_url': reverse('admin:ponto_maquina_change', args=(maquina.pk,)),
        }
        return render(request, 'ponto/admin/testar_apis.html', context)

    def get_action_bar(self, request, remove_add_button=False):
        # Add a Test button to the object change page action bar when obj present
        itens = super().get_action_bar(request, remove_add_button=remove_add_button)
        obj_id = request.resolver_match.kwargs.get('object_id') if request.resolver_match else None
        if obj_id:
            from django.urls import reverse

            # Only superusers may see/run the per-machine API test
            if request.user.is_superuser:
                testar_url = reverse('admin:ponto_maquina_testar_apis', args=(int(obj_id),))
                itens = [{'url': testar_url, 'label': 'Testar APIs do Terminal', 'css_class': 'warning'}, *itens]
        return itens


admin.site.register(Maquina, MaquinaAdmin)


class LiberacaoAdmin(ModelAdminPlus):
    form = LiberacaoForm
    date_hierarchy = 'data_inicio'
    list_filter = ['uo']
    search_fields = ['descricao']
    list_display = ['data_inicio', 'data_fim', 'uo', 'descricao', 'tipo']
    list_display_icons = True

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or request.user.has_perm('rh.eh_rh_sistemico'):
            return queryset
        else:
            user_logado = request.user
            if user_logado:
                uo_logado = get_uo(user_logado)
                queryset = queryset.filter(uo=uo_logado)
            else:
                queryset = Liberacao.objects.none()
        return queryset


admin.site.register(Liberacao, LiberacaoAdmin)


def restringir_observacoes(self, request):
    return admin.ModelAdmin.get_queryset(self, request).filter(vinculo=request.user.get_vinculo())


class ObservacaoAdmin(ModelAdminPlus):
    date_hierarchy = 'data'
    search_fields = ['descricao']
    list_display = ['vinculo', 'data', 'descricao']
    get_queryset = restringir_observacoes
    form = ObservacaoAdminForm
    list_display_icons = True

    def has_delete_permission(self, request, obj=None):
        is_superuser = request.user.is_superuser
        if obj:
            tem_abono = AbonoChefia.objects.filter(data=obj.data, vinculo_pessoa=obj.vinculo).exists()
            if tem_abono:
                return is_superuser  # se tem abono, permissao para excluir apenas super usuarios
        return super().has_delete_permission(request, obj)  # se nao tem abono, retorno padrao


admin.site.register(Observacao, ObservacaoAdmin)


class AfastamentoAdmin(ModelAdminPlus):
    form = AfastamentoForm
    list_display = ['vinculo', 'tipo', 'descricao', 'data_ini', 'data_fim']
    list_filter = ['tipo']
    search_fields = ['descricao', 'vinculo__pessoa__nome']
    list_display_icons = True
    date_hierarchy = 'data_ini'


admin.site.register(Afastamento, AfastamentoAdmin)


class TipoAfastamentoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display_icons = True


admin.site.register(TipoAfastamento, TipoAfastamentoAdmin)


class FrequenciaAdmin(ModelAdminPlus):
    list_display = ['id', 'maquina', 'vinculo', 'acao', 'horario', 'online']
    list_filter = ['horario', 'acao', 'online', 'maquina']
    search_fields = ['vinculo__pessoa__nome']
    ordering = ['-horario']
    date_hierarchy = 'horario'


admin.site.register(Frequencia, FrequenciaAdmin)


class AbonoChefiaTipoFilter(admin.SimpleListFilter):
    title = 'Tipo de abono'
    parameter_name = 'tipo_abono'

    def lookups(self, request, model_admin):
        return [
            ['abono_parcial', 'Apenas abonos parciais'],
            ['abono_integral', 'Apenas abonos integrais (Padrão)'],
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            if value == 'abono_parcial':
                try:
                    return queryset.filter(solicitacao_abono_parcial__isnull=False)
                except Exception:
                    return queryset.none()
            elif value == 'abono_integral':
                try:
                    return queryset.filter(solicitacao_abono_parcial__isnull=True)
                except Exception:
                    return queryset.none()
        return queryset


class AbonoChefiaAdmin(ModelAdminPlus):
    list_display = [
        'data',
        'vinculo_pessoa',
        'vinculo_chefe_imediato',
        'descricao',
        'data_cadastro',
        'ultima_atualizacao',
    ]
    list_filter = ['vinculo_pessoa', AbonoChefiaTipoFilter]
    ordering = ['-data']
    date_hierarchy = 'data'
    list_display_icons = True
    list_per_page = 25

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        pode_ver = super().has_view_permission(request, obj)
        if obj:
            return bool(obj.vinculo_pessoa.user == request.user or obj.vinculo_chefe_imediato.user == request.user)
        return pode_ver

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        queryset = queryset.filter(Q(vinculo_pessoa__user=request.user) | Q(vinculo_chefe_imediato__user=request.user))
        return queryset


admin.site.register(AbonoChefia, AbonoChefiaAdmin)


##########################################################################################
# COMPENSAÇÃO DE HORÁRIO
##########################################################################################
class HorarioCompensacaoAdmin(ModelAdminPlus):
    change_form_template = 'ponto/templates/admin/ponto/horariocompensacao/change_form.html'
    list_display = ['_opcoes', '_ch_compensada', 'data_aplicacao', 'data_compensacao', 'saldo_externo_compensacao', '_situacao']
    list_filter = (('data_aplicacao', DateRangeListFilter), ('data_compensacao', DateRangeListFilter), 'saldo_externo_compensacao', 'situacao')
    list_per_page = 50

    def _opcoes(self, obj):
        return icon('view', obj.get_absolute_url())

    _opcoes.short_description = 'Ações'

    def _ch_compensada(self, obj):
        return obj.ch_compensada.strftime('%H:%M:%S')

    _ch_compensada.short_description = 'Carga Horária Compensada'
    _ch_compensada.admin_order_field = 'ch_compensada'

    def _situacao(self, obj):
        status_css = 'status-finalizado'
        if obj.situacao == HorarioCompensacao.SITUACAO_INVALIDO:
            status_css = 'status-rejeitado'
        return mark_safe(f"<span class='status {status_css} text-nowrap-normal'>{obj.get_situacao_display()}</span>")

    _situacao.short_description = 'Situação'
    _situacao.admin_order_field = 'situacao'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs).order_by('data_aplicacao', '-data_compensacao')
        eu = request.user.get_relacionamento()
        meus_informes = qs.filter(funcionario=eu)
        return meus_informes

    def get_form(self, request, obj=None, **kwargs):
        raise PermissionDenied

    def get_action_bar(self, request, remove_add_button=False):
        eu = request.user.get_relacionamento()
        itens = [
            {'url': '/ponto/adicionar_compensacao_v2/', 'label': 'Informar Compensação de Horário', 'css_class': 'success'},  # redefine o add
            {
                'label': 'Remover Compensações',
                'css_class': 'danger no-confirm',
                'subitems': [
                    {'label': 'Localizar Por Data do Débito', 'url': f'/ponto/remover_compensacoes/{eu.matricula}/?localizar_opcao=1'},
                    {'label': 'Localizar Por Data do Saldo', 'url': f'/ponto/remover_compensacoes/{eu.matricula}/?localizar_opcao=2'},
                    {'label': 'Localizar Por Saldo Externo Utilizado', 'url': f'/ponto/remover_compensacoes/{eu.matricula}/?localizar_opcao=4'},
                    {'label': 'Localizar Compensações em Duplicidade', 'url': f'/ponto/remover_compensacoes/{eu.matricula}/?localizar_opcao=3'},
                ],
            },
        ]
        return itens + super().get_action_bar(request, remove_add_button=True)


admin.site.register(HorarioCompensacao, HorarioCompensacaoAdmin)


class RecessoOpcaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao', 'tipo', '_situacao')
    list_filter = ('tipo', 'situacao')
    search_fields = RecessoOpcao.SEARCH_FIELDS

    def _situacao(self, obj):
        if obj.situacao == RecessoOpcao.SITUACAO_FECHADO:
            situacao = f'<span class="status status-finalizado">{obj.get_situacao_display()}</span>'
        else:
            situacao = f'<span class="status status-em-tramite">{obj.get_situacao_display()}</span>'
            #
            if obj.is_aberto_para_escolhas_de_datas and not obj.is_no_periodo_para_escolhas_de_datas:
                situacao = f'<span class="status status-error">{obj.get_situacao_display()} (o período de escolhas expirou)</span>'
        return mark_safe(situacao)

    _situacao.short_description = 'Situação'
    _situacao.admin_order_field = 'situacao'

    def get_action_bar(self, request, remove_add_button=False):
        subitems = [
            {
                'label': str(tipo[1]),
                'url': f'/admin/ponto/recessoopcao/add/?tipo={tipo[0]}',
            }
            for tipo in RecessoOpcao.TIPO_CHOICES
            if tipo[0] != RecessoOpcao.TIPO_CADASTRO_EXTERNO
        ]
        item = [{'label': 'Adicionar', 'css_class': 'success', 'subitems': subitems}]
        return item + super().get_action_bar(request, remove_add_button=True)

    def get_form(self, request, obj=None, **kwargs):
        tipo = obj.tipo if obj else self._get_tipo(request)
        self.form = RecessoOpcaoOutroForm
        if tipo == RecessoOpcao.TIPO_PERMITE_ESCOLHA_LIVRE:
            self.form = RecessoOpcaoForm
        return super().get_form(request, obj, **kwargs)

    def _get_tipo(self, request):
        tipo = int(request.GET.get('tipo')) if request.GET.get('tipo') else None
        tipos_validos = [tipo_[0] for tipo_ in RecessoOpcao.TIPO_CHOICES if tipo_[0] != RecessoOpcao.TIPO_CADASTRO_EXTERNO]
        if tipo not in tipos_validos:
            raise PermissionDenied
        return tipo

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        if obj and not obj.is_em_fase_de_cadastro:
            return httprr(
                f'/ponto/abrir_opcao_recesso/{obj.id}/',
                message='A opção de compensação não está em fase de cadastro. Por favor, faça as edições desejadas por esta página.',
                tag='warning',
            )
        return super().render_change_form(request, context, form_url=form_url, add=add, change=change, obj=obj)

    def has_delete_permission(self, request, obj=None):
        return False  # apenas via /ponto/excluir_opcao_recesso


admin.site.register(RecessoOpcao, RecessoOpcaoAdmin)


class RecessoOpcaoEscolhidaAdmin(ModelAdminPlus):
    show_tab_any_data = False
    list_filter = [CustomTabListFilter, 'validacao', 'recesso_opcao']
    actions = ['avaliar_em_lote']
    empty_queryset_message = 'Nenhuma compensação específica encontrada.'

    def get_actions(self, request):
        actions = super().get_actions(request)
        tab = request.GET.get('tab')
        if tab != 'recessos_pendentes_do_setor':
            if 'avaliar_em_lote' in actions:
                actions.pop('avaliar_em_lote')
        return actions

    def avaliar_em_lote(self, request, queryset):
        ids = [f'ids={obj.id}' for obj in queryset]
        return httprr(f'/ponto/validar_recesso_escolhido_lote/?{"&".join(ids)}')

    def get_list_display(self, request):
        list_display = [
            'opcoes',
            'recesso_opcao',
            'data_escolha_display',
            'dias_efetivos_a_compensar_display',
            'total_carga_horaria_pendente_display',
            'periodo_compensacao_display',
            'validacao_display',
        ]

        # por questões de desempenho já que uma das colunas mostra a
        # carga horária pendente, que exige diversos cálculos
        self.list_per_page = 4

        if request.GET.get('tab') in ['recessos_pendentes_do_setor', 'recessos_do_setor']:
            list_display.insert(1, 'funcionario')
            # nesse caso, a maioria das compensações exibidas não pertencem
            # ao usuário visualizador (chefe) e portanto a CH pendente não será
            # calculada (não será exibida)
            self.list_per_page = 20

        return list_display

    def get_list_filter(self, request):
        list_filter = self.list_filter

        if 'funcionario' in list_filter:
            list_filter.remove('funcionario')

        if request.GET.get('tab') in ['recessos_pendentes_do_setor', 'recessos_do_setor'] and 'funcionario' not in list_filter:
            list_filter.insert(0, 'funcionario')

        return list_filter

    def data_escolha_display(self, obj):
        return obj.data_escolha_display

    data_escolha_display.short_description = 'Data da Escolha'
    data_escolha_display.admin_order_field = 'data_escolha'

    def dias_efetivos_a_compensar_display(self, obj):
        return obj.dias_efetivos_a_compensar_display_html()

    dias_efetivos_a_compensar_display.short_description = 'Dias Efetivos a Compensar'

    def total_carga_horaria_pendente_display(self, obj):
        return obj.total_carga_horaria_pendente_display_html(user_visualizador=self.request.user)

    total_carga_horaria_pendente_display.short_description = 'CH Pendente'

    def opcoes(self, obj):
        return icon('view', obj.get_absolute_url())

    opcoes.short_description = 'Ações'

    def periodo_compensacao_display(self, obj):
        return obj.periodo_compensacao()

    periodo_compensacao_display.short_description = 'Período de Compensação'

    def validacao_display(self, obj):
        status_css = 'status-alert'  # aguardando
        if obj.validacao == RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO:
            status_css = 'status-success'
        elif obj.validacao in [RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO, RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR]:
            status_css = 'status-error'
        return mark_safe(f"<span class='status {status_css} text-nowrap-normal'>{obj.get_validacao_display()}</span>")

    validacao_display.short_description = 'Validação'
    validacao_display.admin_order_field = 'validacao'

    def get_action_bar(self, request, remove_add_button=False):
        itens = [
            {
                'url': '/ponto/escolher_dia_ou_periodo_de_recesso/',
                'label': 'Verificar se há Dias ou Períodos a Escolher ou Modificar',
                'css_class': 'success',
            }
        ]  # redefine o add
        pode_editar_opcoes_escolhidas, _ = RecessoOpcaoEscolhida.pode_editar_opcoes_escolhidas(request.user)
        if pode_editar_opcoes_escolhidas:
            itens += [{'url': '/ponto/localizar_acompanhamentos/', 'label': 'Edição de Compensações Específicas'}]
        return itens + super().get_action_bar(request, remove_add_button=True)

    def get_form(self, request, obj=None, **kwargs):
        # não é permitido adicionar/alterar pelo admin
        # há um "add" específico '/ponto/escolher_dia_ou_periodo_de_recesso/'
        raise PermissionDenied

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # não é permitido excluir pelo admin
        return False

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        return (
            qs.only(
                'funcionario',
                'recesso_opcao',
                'data_escolha',
                'dias_efetivos_a_compensar_cache',
                'validacao',
            )
            .select_related(
                'funcionario',
                'recesso_opcao',
            )
            .prefetch_related(
                'recesso_opcao__periodos_de_compensacao',
            )
        )

    def get_tabs(self, request):
        queryset_padrao = super().get_queryset(request)
        if self.eh_validador_ou_chefe(request, queryset_padrao):
            return ['meus_recessos', 'recessos_pendentes_do_setor', 'recessos_do_setor']
        return ['meus_recessos']

    def meus_recessos(self, request, queryset):
        eu = request.user.get_relacionamento()
        return queryset.filter(funcionario=eu)

    meus_recessos.short_description = 'Minhas Compensações'

    def recessos_pendentes_do_setor(self, request, queryset):
        recessos_pendentes_do_setor = self.recessos_do_setor(request, queryset).filter(validacao=RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO)
        return recessos_pendentes_do_setor

    recessos_pendentes_do_setor.short_description = 'Compensações Pendentes do Setor'

    def eh_validador_ou_chefe(self, request, queryset):
        eu = request.user.get_relacionamento()
        hoje = datetime.date.today()
        return (
            # Direto via validador da compensação (rápido).
            queryset.filter(
                validador=eu,
            ).exists()
            or
            # Indireto via solicitante da compensação (lento).
            queryset.filter(
                funcionario__setor_id__in=eu.historico_funcao(hoje, hoje).only('setor_suap_id').values_list('setor_suap_id', flat=True)
            ).exists()
        )

    def recessos_do_setor(self, request, queryset):
        eu = request.user.get_relacionamento()
        hoje = datetime.date.today()
        queryset = queryset.filter(
            # já validei ou vou validar
            validador=eu
        ) | queryset.filter(
            # meus subordinados hoje
            funcionario__setor_id__in=eu.historico_funcao(hoje, hoje).only('setor_suap_id').values_list('setor_suap_id', flat=True)
        )
        queryset = queryset.exclude(
            # omite os meus recessos (já tem uma tab só pra isso)
            funcionario=eu
        ).distinct()
        return queryset

    recessos_do_setor.short_description = 'Compensações do Setor'


admin.site.register(RecessoOpcaoEscolhida, RecessoOpcaoEscolhidaAdmin)


class MaquinaLogAdmin(ModelAdminPlus):
    search_fields = ['operacao', 'mensagem']
    list_filter = ('maquina__uo', 'horario', 'status', 'maquina')
    ordering = ['-horario']
    list_display_icons = True
    list_display = ('maquina', 'operacao', 'horario', 'status')


admin.site.register(MaquinaLog, MaquinaLogAdmin)


class SaldoExternoValorFilter(admin.SimpleListFilter):
    title = 'Valor do Saldo'
    parameter_name = 'valor_saldo'

    def lookups(self, request, model_admin):
        return [
            ['apenas_com_valor_restante', 'Valor Disponível'],
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            if value == 'apenas_com_valor_restante':
                try:
                    # lento
                    saldo_externo_ids = [_.id for _ in queryset if _.valor_saldo_restante > 0]
                    return queryset.filter(id__in=saldo_externo_ids)
                except Exception:
                    return queryset.none()
        return queryset


class SaldoExternoAdmin(ModelAdminPlus):
    list_display = (
        'servidor',
        'data_inicio',
        'data_fim',
        'valor_saldo_display',
        'validador',
        'get_situacao_display_html',
        'data_cadastro',
        'get_origem',
    )
    list_display_icons = True
    list_filter = (CustomTabListFilter, 'situacao', SaldoExternoValorFilter)
    show_tab_any_data = True
    show_count_on_tabs = True
    add_form = None
    change_form = None
    list_per_page = 20
    date_hierarchy = 'data_inicio'

    def get_origem(self, obj):
        return obj.get_origem_display()

    get_origem.short_description = 'Origem da Informação'

    def get_situacao_display_html(self, obj):
        return obj.get_situacao_display_html()

    get_situacao_display_html.short_description = 'Situação'
    get_situacao_display_html.admin_order_field = 'situacao'

    def valor_saldo_display(self, obj):
        saldo_externo: SaldoExterno = obj
        return saldo_externo.get_valor_saldo_display()

    valor_saldo_display.short_description = 'Valor do Saldo'
    valor_saldo_display.admin_order_field = 'valor_saldo'

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        if obj:
            saldo_externo: SaldoExterno = obj
            return saldo_externo.pode_visualizar(request.user)
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj:
            saldo_externo: SaldoExterno = obj
            return saldo_externo.pode_excluir(request.user)
        return super().has_delete_permission(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        return httprr('/admin/ponto/saldoexterno', f'{obj_display} foi removido.')

    def get_action_bar(self, request, remove_add_button=False):
        itens = [{'label': 'Adicionar Saldo Externo de Carga Horária', 'css_class': 'success', 'subitems': []}]

        if SaldoExterno.pode_adicionar(request.user):
            itens[0]['subitems'].append({'url': '/ponto/adicionar_saldo_externo_ch/', 'label': 'Como Destinatário do Saldo'})

        if SaldoExterno.pode_adicionar_como_chefe(request.user):
            itens[0]['subitems'].append({'url': '/ponto/adicionar_saldo_externo_ch_como_chefe/', 'label': 'Como Validador do Saldo'})

        if not itens[0]['subitems']:
            itens = []

        if itens and len(itens[0]['subitems']) == 1:
            itens[0].update({'url': itens[0]['subitems'][0]['url']})
            del itens[0]['subitems']  # não precisa

        return itens + super().get_action_bar(request, remove_add_button=True)

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = SaldoExterno.get_saldos_externos_meus(request.user) | SaldoExterno.get_saldos_externos_minhas_validacoes(request.user)
        return qs

    def get_tabs(self, request):
        return ['meus', 'minhas_validacoes']

    def meus(self, request, queryset):
        return SaldoExterno.get_saldos_externos_meus(request.user, queryset)

    meus.short_description = 'Como Destinatário'

    def minhas_validacoes(self, request, queryset):
        return SaldoExterno.get_saldos_externos_minhas_validacoes(request.user, queryset)

    minhas_validacoes.short_description = 'Como Validador'


admin.site.register(SaldoExterno, SaldoExternoAdmin)


class DebitoExternoCadastroAdmin(ModelAdminPlus):
    list_display = ('servidor', 'total_debito_display', 'validador', 'get_situacao_display_html', 'data_cadastro', 'get_origem')
    list_display_icons = True
    list_filter = (CustomTabListFilter, 'situacao')
    show_tab_any_data = True
    show_count_on_tabs = True
    add_form = None
    change_form = None
    list_per_page = 20

    def get_origem(self, obj):
        return obj.get_origem_display()

    get_origem.short_description = 'Origem da Informação'

    def get_situacao_display_html(self, obj):
        return obj.get_situacao_display_html()

    get_situacao_display_html.short_description = 'Situação'
    get_situacao_display_html.admin_order_field = 'situacao'

    def total_debito_display(self, obj):
        debito_externo_cadastro: DebitoExternoCadastro = obj
        return debito_externo_cadastro.get_total_debito_display()

    total_debito_display.short_description = 'Total do Débito'
    total_debito_display.admin_order_field = 'total_debito'

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        if obj:
            debito_externo_cadastro: DebitoExternoCadastro = obj
            return debito_externo_cadastro.pode_visualizar(request.user)
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj:
            debito_externo_cadastro: DebitoExternoCadastro = obj
            return debito_externo_cadastro.pode_excluir(request.user)
        return super().has_delete_permission(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        return httprr('/admin/ponto/debitoexternocadastro', f'{obj_display} foi removido.')

    def get_action_bar(self, request, remove_add_button=False):
        itens = [{'label': 'Adicionar Débito Externo de Carga Horária', 'css_class': 'success', 'subitems': []}]

        if DebitoExternoCadastro.pode_adicionar(request.user):
            itens[0]['subitems'].append({'url': '/ponto/adicionar_debito_externo_ch_cadastro/', 'label': 'Como Destinatário do Débito'})

        if DebitoExternoCadastro.pode_adicionar_como_chefe(request.user):
            itens[0]['subitems'].append({'url': '/ponto/adicionar_debito_externo_ch_cadastro_como_chefe/', 'label': 'Como Validador do Débito'})

        if not itens[0]['subitems']:
            itens = []

        if itens and len(itens[0]['subitems']) == 1:
            itens[0].update({'url': itens[0]['subitems'][0]['url']})
            del itens[0]['subitems']  # não precisa

        return itens + super().get_action_bar(request, remove_add_button=True)

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = DebitoExternoCadastro.get_debitos_externos_cadastros_meus(
            request.user
        ) | DebitoExternoCadastro.get_debitos_externos_cadastros_minhas_validacoes(request.user)
        return qs

    def get_tabs(self, request):
        return ['meus', 'minhas_validacoes']

    def meus(self, request, queryset):
        return DebitoExternoCadastro.get_debitos_externos_cadastros_meus(request.user, queryset)

    meus.short_description = 'Como Destinatário'

    def minhas_validacoes(self, request, queryset):
        return DebitoExternoCadastro.get_debitos_externos_cadastros_minhas_validacoes(request.user, queryset)

    minhas_validacoes.short_description = 'Como Validador'


admin.site.register(DebitoExternoCadastro, DebitoExternoCadastroAdmin)


class SolicitacaoAbonoParcialAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display_links = None
    show_tab_any_data = False
    show_count_on_tabs = True
    date_hierarchy = 'data_aplicacao'
    actions = ['avaliar_em_lote']

    def get_actions(self, request):
        actions = super().get_actions(request)
        tab = request.GET.get('tab')
        if tab != 'solicitacoes_terceiros_pendentes':
            if 'avaliar_em_lote' in actions:
                actions.pop('avaliar_em_lote')
        return actions

    def avaliar_em_lote(self, request, queryset):
        ids = [f'ids={obj.id}' for obj in queryset]
        return httprr(f'/ponto/avaliar_abono_parcial_lote/?{"&".join(ids)}')

    def get_list_display(self, request):
        tem_solicitacoes_terceiros = SolicitacaoAbonoParcial.query_solicitacoes_terceiros(request.user).exists()
        if tem_solicitacoes_terceiros:
            list_display = ['admin_opcoes', 'vinculo_pessoa', 'data_aplicacao', 'motivo', 'admin_ch_solicitada', 'abono_solicitado', 'admin_situacao']
        else:
            list_display = ['admin_opcoes', 'data_aplicacao', 'motivo', 'admin_ch_solicitada', 'abono_solicitado', 'admin_situacao']
        return list_display

    def get_list_filter(self, request):
        tab = request.GET.get('tab')
        tab_eh_minhas_solicitacoes = tab == 'minhas_solicitacoes' or not tab
        if tab_eh_minhas_solicitacoes:
            list_filter = [CustomTabListFilter, 'situacao']
        else:
            tem_solicitacoes_terceiros = SolicitacaoAbonoParcial.query_solicitacoes_terceiros(request.user).exists()
            if tem_solicitacoes_terceiros:
                list_filter = [CustomTabListFilter, 'vinculo_pessoa', 'situacao']
            else:
                list_filter = [CustomTabListFilter, 'situacao']
        return list_filter

    def has_view_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_view_permission(request, obj)

    def has_action_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_action_permission(request, obj=obj)

    def has_add_permission(self, request):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return False

    def has_change_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return False

    def has_delete_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        if obj:
            return obj.pode_remover(request.user)
        return False

    def admin_opcoes(self, obj):
        return icon('view', obj.get_absolute_url())

    admin_opcoes.short_description = 'Ações'

    def admin_ch_solicitada(self, obj):
        return obj.ch_solicitada_display

    admin_ch_solicitada.short_description = 'Carga horária a abonar'
    admin_ch_solicitada.admin_order_field = 'ch_solicitada'

    def admin_situacao(self, obj):
        return obj.get_situacao_display_html

    admin_situacao.short_description = 'Situação'
    admin_situacao.admin_order_field = 'situacao'

    def get_tabs(self, request):
        tem_solicitacoes_terceiros = SolicitacaoAbonoParcial.query_solicitacoes_terceiros(request.user).exists()
        if tem_solicitacoes_terceiros:
            tabs = ['minhas_solicitacoes', 'solicitacoes_terceiros_pendentes', 'solicitacoes_terceiros_avaliadas']
        else:
            tabs = ['minhas_solicitacoes']
        return tabs

    def minhas_solicitacoes(self, request, queryset):
        return SolicitacaoAbonoParcial.query_minhas_solicitacoes(request.user).order_by('-data_aplicacao')

    minhas_solicitacoes.short_description = 'Minhas solicitações'

    def solicitacoes_terceiros_pendentes(self, request, queryset):
        return SolicitacaoAbonoParcial.query_solicitacoes_terceiros_pendentes(request.user).order_by('-data_aplicacao')

    solicitacoes_terceiros_pendentes.short_description = 'Solicitações de terceiros (Pendentes)'

    def solicitacoes_terceiros_avaliadas(self, request, queryset):
        return SolicitacaoAbonoParcial.query_solicitacoes_terceiros_avaliadas(request.user).order_by('-data_aplicacao')

    solicitacoes_terceiros_avaliadas.short_description = 'Solicitações de terceiros (Avaliadas)'


admin.site.register(SolicitacaoAbonoParcial, SolicitacaoAbonoParcialAdmin)


class SolicitacaoAbonoParcialGravidezAdmin(ModelAdminPlus):
    list_display = ['nome_gravida', 'descricao']
    list_display_icons = True
    list_display_links = None
    form = SolicitacaoAbonoParcialGravidezForm

    def get_queryset(self, request):
        meu_vinculo = request.user.get_vinculo()
        qs = super().get_queryset(request).filter(vinculo_pessoa=meu_vinculo)
        return qs

    def has_view_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_view_permission(request, obj)

    def has_action_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_action_permission(request, obj=obj)

    def has_add_permission(self, request):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_delete_permission(request, obj)


admin.site.register(SolicitacaoAbonoParcialGravidez, SolicitacaoAbonoParcialGravidezAdmin)


class SolicitacaoRevisaoAbonoChefiaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display_links = None
    show_tab_any_data = False
    show_count_on_tabs = True
    date_hierarchy = 'abono_chefia_data'

    def get_list_display(self, request):
        tem_solicitacoes_terceiros = AbonoChefia.get_solicitacoes_revisao_abono_chefia(vinculo_avaliador=request.user.get_vinculo()).exists()
        if tem_solicitacoes_terceiros:
            list_display = ['admin_opcoes', 'vinculo_solicitante', 'abono_chefia_display', 'justificativa', 'admin_situacao']
        else:
            list_display = ['admin_opcoes', 'abono_chefia_display', 'justificativa', 'admin_situacao']
        return list_display

    def get_list_filter(self, request):
        tab = request.GET.get('tab')
        tab_eh_minhas_solicitacoes = tab == 'minhas_solicitacoes' or not tab
        if tab_eh_minhas_solicitacoes:
            list_filter = [CustomTabListFilter, 'situacao']
        else:
            tem_solicitacoes_terceiros = AbonoChefia.get_solicitacoes_revisao_abono_chefia(vinculo_avaliador=request.user.get_vinculo()).exists()
            if tem_solicitacoes_terceiros:
                list_filter = [CustomTabListFilter, 'vinculo_solicitante', 'situacao']
            else:
                list_filter = [CustomTabListFilter, 'situacao']
        return list_filter

    def has_view_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_view_permission(request, obj)

    def has_action_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return super().has_action_permission(request, obj=obj)

    def has_add_permission(self, request):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return False

    def has_change_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        return False

    def has_delete_permission(self, request, obj=None):
        if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            return False
        if obj:
            return AbonoChefia.get_permissoes_solicitacao_revisao_abono_chefia(request.user.get_vinculo(), obj).get('pode_remover')
        return False

    def admin_opcoes(self, obj):
        return icon('view', obj.get_absolute_url())

    admin_opcoes.short_description = 'Ações'

    def admin_situacao(self, obj):
        return obj.get_situacao_display_html()

    admin_situacao.short_description = 'Situação'
    admin_situacao.admin_order_field = 'situacao'

    def get_tabs(self, request):
        tem_solicitacoes_terceiros = AbonoChefia.get_solicitacoes_revisao_abono_chefia(vinculo_avaliador=request.user.get_vinculo()).exists()
        if tem_solicitacoes_terceiros:
            tabs = ['minhas_solicitacoes', 'solicitacoes_terceiros_pendentes', 'solicitacoes_terceiros_avaliadas']
        else:
            tabs = ['minhas_solicitacoes']
        return tabs

    def minhas_solicitacoes(self, request, queryset):
        return AbonoChefia.get_solicitacoes_revisao_abono_chefia(vinculo_solicitante=request.user.get_vinculo()).order_by('-abono_chefia_data')

    minhas_solicitacoes.short_description = 'Minhas solicitações'

    def solicitacoes_terceiros_pendentes(self, request, queryset):
        return AbonoChefia.get_solicitacoes_revisao_abono_chefia(
            vinculo_avaliador=request.user.get_vinculo(), situacao=SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE
        ).order_by('-abono_chefia_data')

    solicitacoes_terceiros_pendentes.short_description = 'Solicitações de terceiros (Pendentes)'

    def solicitacoes_terceiros_avaliadas(self, request, queryset):
        return AbonoChefia.get_solicitacoes_revisao_abono_chefia(
            vinculo_avaliador=request.user.get_vinculo(), situacao=SolicitacaoRevisaoAbonoChefia.SITUACAO_AVALIADO
        ).order_by('-abono_chefia_data')

    solicitacoes_terceiros_avaliadas.short_description = 'Solicitações de terceiros (Avaliadas)'


admin.site.register(SolicitacaoRevisaoAbonoChefia, SolicitacaoRevisaoAbonoChefiaAdmin)
