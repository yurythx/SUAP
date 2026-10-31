import io
import logging
import os
import tempfile
from datetime import datetime
from functools import update_wrapper
from zipfile import ZipFile

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter, StackedInline, helpers
from django.contrib.auth.admin import GroupAdmin as AuthGroupAdmin
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

import comum.views
from comum import utils
from comum.forms import (
    APIExternaForm,
    AreaAtuacaoForm,
    CadastrarAtalhoForm,
    CategoriaNotificacaoForm,
    CertificadoDigitalForm,
    ConfiguracaoImpressaoDocumentoForm,
    ContatoEmergenciaForm,
    DocumentoControleAdminFormFactory,
    DocumentoControleTipoForm,
    GrupoGerenciamentoForm,
    ManutencaoProgramadaForm,
    ObraForm,
    PensionistaForm,
    PredioForm,
    PrestadorServicoForm,
    PublicoAdminForm,
    ReuniaoOrgaoColegiadoForm,
    SalaForm,
    VinculoForm,
)
from comum.html import ReuniaoOrgaoColegiadoView
from comum.models import (
    AcabamentoExternoPredio,
    AcabamentoParedeSala,
    Ano,
    APIExterna,
    AreaAtuacao,
    Atalho,
    Beneficio,
    BeneficioDependente,
    CategoriaNotificacao,
    CertificadoDigital,
    ClassificacaoSala,
    ClimatizacaoSala,
    CoberturaPredio,
    CombateIncendioPanico,
    Configuracao,
    ConfiguracaoCarteiraFuncional,
    ConfiguracaoImpressaoDocumento,
    ContatoEmergencia,
    Dependente,
    Device,
    DocumentoControle,
    DocumentoControleTipo,
    EmailBlockList,
    EsquadriasSala,
    EstadoCivil,
    EstruturaPredio,
    ForroSala,
    FuncaoCodigo,
    GerenciamentoGrupo,
    GrauParentesco,
    GroupDetail,
    InstalacaoEletricaSala,
    InstalacaoGasesSala,
    InstalacaoHidraulicaSala,
    InstalacaoLogicaSala,
    JustificativaUsuarioExterno,
    Log,
    ManutencaoProgramada,
    Municipio,
    Notificacao,
    NotificacaoSistema,
    OauthLogin,
    Obra,
    Ocupacao,
    OcupacaoPrestador,
    Pais,
    Pensionista,
    PessoaTelefone,
    PisoSala,
    Predio,
    Preferencia,
    PreferenciaNotificacao,
    PrestadorServico,
    Publico,
    Raca,
    RegistroEmissaoDocumento,
    RegistroNotificacao,
    ReservaSala,
    ReuniaoOrgaoColegiado,
    Sala,
    SenhaExposta,
    SessionInfo,
    SistemaAbastecimentoPredio,
    SistemaAlimentacaoEletricaPredio,
    SistemaProtecaoDescargaAtmosfericaPredio,
    SistemaSanitarioPredio,
    SolicitacaoReservaSala,
    TipoArquivo,
    TipoCarteiraFuncional,
    User,
    UsoSala,
    UsuarioGrupo,
    UsuarioGrupoSetor,
    VedacaoPredio,
    Vinculo,
)
from comum.types import PessoaFisicaCadastro, PrestadorServicoCadastro
from djtools.choices import SituacaoSolicitacaoDocumento
from djtools.contrib.admin import CustomTabListFilter, DateRangeListFilter, HttpResponseRedirect, ModelAdminPlus, get_uo_setor_listfilter
from djtools.storages import cache_file
from djtools.templatetags.filters import format_user, in_group, status
from djtools.templatetags.filters.utils import format_
from djtools.templatetags.tags import icon
from djtools.utils import get_ldap_conf, httprr, is_ldap_enabled, render
from rh.models import UnidadeOrganizacional
from rh.pdf import imprime_carteira_funcional, imprime_cracha
from suap import nomenclatura


class SomenteDescricaoModelAdmin(ModelAdminPlus):
    list_filter = ('ativo',)
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True


for cls in (
    EstruturaPredio,
    CoberturaPredio,
    VedacaoPredio,
    SistemaSanitarioPredio,
    SistemaAbastecimentoPredio,
    SistemaAlimentacaoEletricaPredio,
    SistemaProtecaoDescargaAtmosfericaPredio,
    AcabamentoExternoPredio,
    InstalacaoEletricaSala,
    InstalacaoLogicaSala,
    InstalacaoHidraulicaSala,
    InstalacaoGasesSala,
    ClimatizacaoSala,
    AcabamentoParedeSala,
    PisoSala,
    ForroSala,
    EsquadriasSala,
    UsoSala,
    ClassificacaoSala,
):
    admin.site.register(cls, SomenteDescricaoModelAdmin)


class AtalhoAdmin(ModelAdminPlus):
    list_display = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True
    form = CadastrarAtalhoForm

    actions = ('excluir',)

    def excluir(self, request, queryset):
        queryset.delete()
        messages.success(request, 'Atalhos excluídos com sucesso.')

    excluir.short_description = 'Excluir atalhos selecionados'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        return super().get_queryset(request, manager, *args, **kwargs).filter(usuario=request.user)

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated


admin.site.register(Atalho, AtalhoAdmin)


class PublicoAdmin(ModelAdminPlus):
    list_display = ('nome', 'modelo_base', 'manager_base', 'qs_filter', 'get_acoes')
    list_filter = ('modelo_base',)
    search_fields = ('nome',)
    list_display_icons = True
    form = PublicoAdminForm

    def get_acoes(self, obj):
        html = f"""<ul class="action-bar">
                <li><a href="/comum/publico/{obj.pk}/visualizar/"> Ver Público </a></li>
            </ul>"""
        return mark_safe(html)

    get_acoes.short_description = 'Ações'


admin.site.register(Publico, PublicoAdmin)


class CertificadoDigitalAdmin(ModelAdminPlus):
    list_display_icons = True
    form = CertificadoDigitalForm
    list_display = ('user', 'nome', 'organizacao', 'unidade', 'validade')
    search_fields = ('user__username', 'nome')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(user=request.user)
        return qs

    def has_view_permission(self, request, obj=None):
        has_permission = super().has_view_permission(request, obj=obj)
        if has_permission:
            return obj is None or obj.user == request.user or request.user.is_superuser
        return False


admin.site.register(CertificadoDigital, CertificadoDigitalAdmin)


class AreaAtuacaoAdmin(ModelAdminPlus):
    form = AreaAtuacaoForm
    export_to_xls = True
    list_display = ('nome', 'slug', 'icone', 'ativo')
    list_display_icons = True

    def to_xls(self, request, queryset, processo):
        header = ['Código', 'Área', 'Slug', 'Ativo']
        rows = [header]
        for obj in processo.iterate(queryset):
            row = [obj.pk, obj.nome, obj.slug, obj.ativo]
            rows.append(row)
        return rows


admin.site.register(AreaAtuacao, AreaAtuacaoAdmin)


class EstadoCivilAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo_siape', 'ativo')
    ordering = ('ativo', 'nome', 'codigo_siape')
    search_fields = ('nome', 'codigo_siape')


admin.site.register(EstadoCivil, EstadoCivilAdmin)


class PaisAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'codigo_censup', 'codigo_educacenso', 'iso_alfa3', 'excluido')
    ordering = ('excluido', 'nome', 'codigo', 'codigo_censup')
    list_filter = [CustomTabListFilter, 'excluido', 'codigo_censup']
    list_editable = ['codigo_censup', 'codigo_educacenso', 'iso_alfa3']
    search_fields = ('nome', 'codigo', 'iso_alfa3')
    show_count_on_tabs = True

    def get_tabs(self, request):
        return ['tab_usados']

    def tab_usados(self, request, queryset):
        from rh.models import Servidor

        return queryset.filter(pk__in=Servidor.objects.values_list('pessoa_fisica__pais_origem', flat=True).order_by().distinct())

    tab_usados.short_description = 'Usados'


admin.site.register(Pais, PaisAdmin)


class MunicipioAdmin(ModelAdminPlus):
    list_display = ('nome', 'uf')
    list_filter = ('uf',)
    search_fields = ('identificacao',)


admin.site.register(Municipio, MunicipioAdmin)


class RacaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'codigo_siape', 'inativo_siape')
    search_fields = ('descricao',)
    list_display_icons = True


admin.site.register(Raca, RacaAdmin)


#########################
# DocumentoControleTipo #
#########################


class DocumentoControleTipoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'get_abrangencia')
    search_fields = ('descricao',)
    list_display_icons = True
    form = DocumentoControleTipoForm

    def get_abrangencia(self, obj):
        return mark_safe('<br />'.join(ab.nome_siape for ab in obj.abrangencia.all()))

    get_abrangencia.short_description = 'Abrangência'


admin.site.register(DocumentoControleTipo, DocumentoControleTipoAdmin)


class DocumentoControleUoFilter(SimpleListFilter):
    title = nomenclatura.campus
    parameter_name = 'uo'

    def lookups(self, request, model_admin):
        return [(c.id, c.sigla) for c in UnidadeOrganizacional.objects.suap().all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(solicitante_vinculo__setor__uo_id__exact=self.value())
        else:
            return queryset


class DocumentoControleTipoFilter(SimpleListFilter):
    title = 'Tipo de Documento'
    parameter_name = 'tipo_documento'

    def lookups(self, request, model_admin):
        return [(tipo.id, tipo.descricao) for tipo in DocumentoControleTipo.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(documento_tipo__id=self.value())
        else:
            return queryset


class DocumentoControleAdmin(ModelAdminPlus):
    list_display = ('get_foto', 'get_solicitante', 'documento_tipo', 'get_campus_suap', 'get_status_solicitacao', 'ativo')
    list_display_icons = True
    list_filter = (DocumentoControleTipoFilter, DocumentoControleUoFilter, 'status_solicitacao')
    search_fields = ('documento_id', 'solicitante_vinculo__pessoa__nome', 'solicitante_vinculo__user__username')

    actions = ('atender', 'exportar_xls', 'imprimir_carteira_funcional', 'imprimir_cracha')

    def atender(self, request, queryset):
        if self._pertence_grupo_com_permissao(request):
            ids = request.POST.getlist('_selected_action')
            if ids:
                ids = list(map(int, ids))
            qs_solicitacoes = queryset.filter(id__in=ids, status_solicitacao=SituacaoSolicitacaoDocumento.NAO_ATENDIDA)
            if qs_solicitacoes.exists():
                for solicitacao in qs_solicitacoes:
                    solicitacao.atender_solicitacao(request)
                messages.success(request, 'Solicitações atendidas com sucesso.')

    atender.short_description = 'Atender'

    def imprimir_carteira_funcional(self, request, queryset):
        if self._pertence_grupo_com_permissao(request):
            # servidor_ids = []
            servidores = []
            if request.POST and request.POST.getlist('_selected_action'):
                qs_solicitacoes = DocumentoControle.objects.filter(
                    id__in=request.POST.getlist('_selected_action'), documento_tipo__identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL
                )
                for solicitacao in qs_solicitacoes:
                    servidores.append(solicitacao.solicitante_vinculo.relacionamento)

                qs_config = ConfiguracaoCarteiraFuncional.objects.all()
                config = None
                if qs_config.exists():
                    config = qs_config.order_by('-id')[0]
                return imprime_carteira_funcional(servidores, config)
                #    servidor_ids.append(solicitacao.solicitante_vinculo.relacionamento.id)

                # request.session['_servidores_ids'] = servidor_ids
                # return httprr('/rh/carteira_funcional/')

    imprimir_carteira_funcional.short_description = 'Imprimir Carteira Funcional'

    def imprimir_cracha(self, request, queryset):
        if self._pertence_grupo_com_permissao(request):
            servidores = []
            if request.POST and request.POST.getlist('_selected_action'):
                qs_solicitacoes = DocumentoControle.objects.filter(
                    id__in=request.POST.getlist('_selected_action'), documento_tipo__identificador=DocumentoControleTipo.CRACHA
                )
                for solicitacao in qs_solicitacoes:
                    servidor = solicitacao.solicitante_vinculo.relacionamento
                    servidor.pessoa_fisica.nome_sugerido_cracha = solicitacao.nome_sugerido or ''
                    servidor.pessoa_fisica.nome_social_cracha = solicitacao.nome_social or ''
                    servidores.append(servidor)
                if not servidores:
                    return httprr('/admin/comum/documentocontrole/', 'Você precisa solicitar pelo menos uma solicitação de crachá.', 'error')
                return imprime_cracha(servidores)

    imprimir_cracha.short_description = 'Imprimir Crachá'

    def exportar_xls(self, request, queryset):
        temps = []
        if request.POST and request.POST.getlist('_selected_action'):
            qs_solicitacoes = DocumentoControle.objects.filter(
                id__in=request.POST.getlist('_selected_action'),
                documento_tipo__identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL,
                status_solicitacao=SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
            )

            import pandas as pd

            # Prepare data
            data = []
            columns = [
                'Matrícula',
                'Nome',
                'CPF',
                'RG/Orgão Expedidor',
                'Cargo',
                'Tipo Sanguíneo/Fator RH',
                'Naturalidade',
                'Data de Nascimento',
                'Filiação',
                'Local e Data de Expedição',
            ]

            #
            # tratando data
            dia = datetime.now().day
            if dia < 10:
                dia = f'0{dia}'
            mes = datetime.now().month
            if mes < 10:
                mes = f'0{mes}'
            ano = datetime.now().year

            #
            # instanciando StringIO para tratar arquivo zip em memória
            in_memory = io.BytesIO()
            zip = ZipFile(in_memory, 'a')

            for solicitacao in qs_solicitacoes:
                rg = solicitacao.solicitante_vinculo.pessoa.pessoafisica.rg or ''
                rg_orgao = solicitacao.solicitante_vinculo.pessoa.pessoafisica.rg_orgao or ''
                cargo = solicitacao.solicitante_vinculo.relacionamento.cargo_emprego.nome or ''
                grupo_sanguineo = solicitacao.solicitante_vinculo.pessoa.pessoafisica.grupo_sanguineo or ''
                fator_rh = solicitacao.solicitante_vinculo.pessoa.pessoafisica.fator_rh or ''

                municipio = ''
                uf = ''
                if solicitacao.solicitante_vinculo.pessoa.pessoafisica.nascimento_municipio:
                    municipio = solicitacao.solicitante_vinculo.pessoa.pessoafisica.nascimento_municipio.nome or ''
                    uf = solicitacao.solicitante_vinculo.pessoa.pessoafisica.nascimento_municipio.uf or ''

                data_nascimento = ''
                if solicitacao.solicitante_vinculo.pessoa.pessoafisica.nascimento_data:
                    data_nascimento = solicitacao.solicitante_vinculo.pessoa.pessoafisica.nascimento_data.strftime('%d/%m/%Y')

                row = [
                    solicitacao.solicitante_vinculo.relacionamento.matricula,
                    solicitacao.solicitante_vinculo.pessoa.nome,
                    solicitacao.solicitante_vinculo.pessoa.pessoafisica.cpf,
                    f'{rg}/{rg_orgao}',
                    cargo,
                    f'{grupo_sanguineo}{fator_rh}',
                    f'{municipio}/{uf}',
                    data_nascimento,
                    solicitacao.solicitante_vinculo.pessoa.pessoafisica.nome_mae,
                    f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}/{Configuracao.get_valor_por_chave("comum", "instituicao_estado")}, {dia}/{mes}/{ano}',
                ]
                data.append(row)

                foto = solicitacao.solicitante_vinculo.foto
                tmp = cache_file(foto.name)
                temps.append(tmp)
                zip.write(tmp, f'{solicitacao.solicitante_vinculo.relacionamento.matricula}.png')

            #
            # é necessário salvar a planilha gerada para que seja possível adicioná-la ao arquivo zip
            df = pd.DataFrame(data, columns=columns)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                temps.append(tmp.name)
                df.to_excel(tmp.name, index=False, sheet_name='Dados Servidores')

            zip.write(tmp.name, 'planilha_servidores.xlsx')
            zip.close()
            in_memory.seek(0)
            content = in_memory.read()

            for tmp in temps:
                os.unlink(tmp)

            response = HttpResponse(content_type='application/force-download')
            response['Content-Disposition'] = 'attachment; filename=dados_carteira_funcional.zip'
            response.write(content)

            return response

    exportar_xls.short_description = 'Exportar Carteira Funcional para Excel'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self._pertence_grupo_com_permissao(request):
            return actions
        else:
            for key in list(actions.keys()):
                del actions[key]
            return actions

    def response_change(self, request, obj):
        return httprr(
            '/admin/comum/documentocontrole/', 'Solicitação de documento alterada com sucesso. Em breve você receberá o documento solicitado.'
        )

    def response_add(self, request, obj):
        return httprr(
            '/admin/comum/documentocontrole/', 'Solicitação de documento cadastrada com sucesso. Em breve você receberá o documento solicitado.'
        )

    def get_list_display(self, request):
        default_list_display = super().get_list_display(request)
        if self._pertence_grupo_com_permissao(request):
            coluna_pagamento = ('get_acoes',)
            nova_list_display = default_list_display + coluna_pagamento
            return nova_list_display
        return default_list_display

    def get_campus_suap(self, obj):
        if obj.solicitante_vinculo.setor:
            return mark_safe(obj.solicitante_vinculo.setor.uo)
        return None

    get_campus_suap.admin_order_field = 'solicitante_vinculo__setor__uo'
    get_campus_suap.short_description = nomenclatura.campus

    def get_status_solicitacao(self, obj):
        return mark_safe(f'<span class="status status-{obj.get_classe_css()}">{obj.get_status_solicitacao_display()}</span>')

    get_status_solicitacao.admin_order_field = 'status_solicitacao'
    get_status_solicitacao.short_description = 'Situação da Solicitação'

    def get_solicitante(self, obj):
        show_email = ''
        if obj.solicitante_vinculo.email_notificacao:
            show_email = f'<a href="mailto:{obj.solicitante_vinculo.email_notificacao}">{obj.solicitante_vinculo.email_notificacao}</a>'
        out = f"""
        <dl>
            <dt class="hidden">Nome:</dt><dd class="negrito">{obj.solicitante_vinculo.pessoa.nome}</dd>
            <dt class="hidden">E-mail:</dt><dd>{show_email} </dd>
            <dt>Matrícula:</dt><dd>{obj.solicitante_vinculo.relacionamento.matricula}</dd>
            <dt>Tipo Sanguíneo:</dt><dd>{obj.solicitante_vinculo.pessoa.pessoafisica.tipo_sanguineo}</dd>
            <dt>Situação:</dt><dd>{obj.solicitante_vinculo.relacionamento.situacao.nome}</dd>
        </dl>
        """
        return mark_safe(out)

    get_solicitante.admin_order_field = 'solicitante_vinculo__pessoa__nome'
    get_solicitante.short_description = 'Solicitante'

    def get_foto(self, obj):
        img_src = obj.solicitante_vinculo.get_foto_75x100_url()
        return mark_safe(f'<img class="img-inside-container" src="{img_src}"/>')

    get_foto.short_description = 'Foto'

    def get_acoes(self, obj):
        html = """<ul class="action-bar">"""

        if obj.status_solicitacao == SituacaoSolicitacaoDocumento.NAO_ATENDIDA:
            html += f"""<li><a class="btn success confirm" href="/comum/marcar_solicitacao_atendida/{obj.pk}/">Marcar como Atendida</a></li>
                        <li><a class="btn danger popup" href="/comum/rejeitar_solicitacao/{obj.pk}/"> Rejeitar Solicitação </a></li>
                     """

        if obj.status_solicitacao not in [SituacaoSolicitacaoDocumento.REJEITADA, SituacaoSolicitacaoDocumento.DEVOLVIDA]:
            if obj.documento_tipo and obj.documento_tipo.identificador == DocumentoControleTipo.CRACHA:
                html += f"""<li><a class="btn" href="/rh/cracha_pessoa/{obj.solicitante_vinculo.pessoa.id}/"> Imprimir </a></li>"""

            if obj.documento_tipo and obj.documento_tipo.identificador == DocumentoControleTipo.CARTEIRA_FUNCIONAL:
                html += f"""<li><a class="btn" href="/rh/carteira_funcional/{obj.solicitante_vinculo.relacionamento.id}/"> Imprimir </a></li>"""

        html += """</ul>"""

        return mark_safe(html)

    get_acoes.short_description = 'Ações'

    def get_fields(self, request, obj=None):
        super().get_fields(request, obj)
        form = self.get_form(request, obj)
        return form.get_fields()

    def get_form(self, request, obj=None, **kwargs):
        form = DocumentoControleAdminFormFactory(request, obj)
        form.request = request
        return form

    # Só pode solicitar um documento se existir uma configuração de impressão para o campus;
    def has_add_permission(self, request):
        uo_usuario = utils.get_uo(request.user)
        return ConfiguracaoImpressaoDocumento.objects.filter(relacao_impressao=uo_usuario).exists()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.regras_filtro_queryset(request, qs)

    # Regras de acesso para o IFRN
    def regras_filtro_queryset(self, request, qs):
        # Se for rh sistemico, pode ver tudo
        eh_rh_sistemico = request.user.has_perm('rh.eh_rh_sistemico')
        if eh_rh_sistemico:
            return qs

        # mostrar apenas solicitações ativas
        qs = qs.filter(solicitante_vinculo__ativo=True)
        pode_gerar_cracha = request.user.has_perm('rh.pode_gerar_cracha')
        pode_gerar_carteira = request.user.has_perm('rh.pode_gerar_carteira')
        if pode_gerar_cracha or pode_gerar_carteira:
            # verificando qual a uo do usuário logado
            uo_usuario_logado = utils.get_uo(request.user)

            # selecionando apenas os tipos de documentos suportados pelo campus do gestor de pessoas
            ids = []
            for conf in ConfiguracaoImpressaoDocumento.objects.filter(uo=uo_usuario_logado):
                ids += [
                    dc.pk
                    for dc in qs.filter(
                        documento_tipo__in=conf.tipos_documento.all(), solicitante_vinculo__setor__uo__equivalente__in=conf.relacao_impressao.all()
                    ).exclude(solicitante_vinculo__user=request.user)
                ]

                ids += [
                    dc.pk
                    for dc in qs.filter(
                        documento_tipo__in=conf.tipos_documento.all(), solicitante_vinculo__setor__uo__in=conf.relacao_impressao.all()
                    ).exclude(solicitante_vinculo__user=request.user, id__in=ids)
                ]
            return qs.filter(id__in=ids) | qs.filter(solicitante_vinculo__user=request.user)

        # se não exisitir configuração e não for do grupo de gestão de pessoas, mostra apenas a própria solicitação
        return qs.filter(solicitante_vinculo__user=request.user)

    def _pertence_grupo_com_permissao(self, request):
        grupos = ['Coordenador de Gestão de Pessoas Sistêmico', 'Coordenador de Gestão de Pessoas', 'Confeccionador de Documentos']
        return bool(request.user.has_group(grupos))


admin.site.register(DocumentoControle, DocumentoControleAdmin)


class ConfiguracaoImpressaoDocumentoAdmin(ModelAdminPlus):
    list_display = ('get_uo', 'get_relacao_impressao', 'get_tipos_documento', 'local_impressao')
    search_fields = ('uo__nome',)
    form = ConfiguracaoImpressaoDocumentoForm
    list_display_icons = True

    def get_uo(self, obj):
        return obj.uo.nome

    get_uo.admin_order_field = 'uo__nome'
    get_uo.short_description = nomenclatura.campus

    def get_relacao_impressao(self, obj):
        return mark_safe('<br />'.join([o.nome for o in obj.relacao_impressao.all()]))

    get_relacao_impressao.short_description = 'Relação de Impressão'

    def get_tipos_documento(self, obj):
        return mark_safe('<br />'.join([o.descricao for o in obj.tipos_documento.all()]))

    get_tipos_documento.short_description = 'Tipos de Documentos'


admin.site.register(ConfiguracaoImpressaoDocumento, ConfiguracaoImpressaoDocumentoAdmin)


admin.site.register(ConfiguracaoCarteiraFuncional)


#######
# Ano #
#######


class AnoAdmin(ModelAdminPlus):
    pass


admin.site.register(Ano, AnoAdmin)


class OcupacaoPrestadorInline(admin.StackedInline):
    model = OcupacaoPrestador
    extra = 1
    can_delete = False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return False


class OcupacaoPrestadorReadOnlyInLine(admin.StackedInline):
    model = OcupacaoPrestador
    extra = 0
    can_delete = False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        result = list(set([field.name for field in self.opts.local_fields] + [field.name for field in self.opts.local_many_to_many]))
        result.remove('id')
        result.remove('data_fim')
        return result


class PrestadorServicoAdmin(ModelAdminPlus):
    list_display = (
        'get_documento_identificador',
        'get_nome',
        'get_email_secundario',
        'get_foto',
        'get_papeis',
        'get_tipo_login',
        'get_ocupacao',
        'ativo',
        'get_opcoes',
    )
    list_filter = (*get_uo_setor_listfilter(), 'pessoa_fisica__eh_estrangeiro', 'usuario_externo', 'ativo')
    list_display_icons = True
    list_per_page = 20
    search_fields = ('pessoa_fisica__nome', 'pessoa_fisica__cpf', 'matricula')
    ordering = ['-id', 'pessoa_fisica__nome']
    form = PrestadorServicoForm

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': [
                    'nome_registro',
                    'nome_social',
                    'nome_usual',
                    ('cpf', 'sexo'),
                    ('nacionalidade', 'passaporte', 'pais_origem'),
                    ('justificativa_cadastro'),
                    'ativo',
                ]
            },
        ),
    )

    def get_readonly_fields(self, request: HttpRequest, obj: PrestadorServico | None = None) -> tuple[str, ...]:
        campos_somente_leitura = tuple(super().get_readonly_fields(request, obj))
        if obj is None or request.user.has_group_cached(['Coordenador de TI sistêmico']):
            return campos_somente_leitura
        return (*campos_somente_leitura, 'ativo')

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fields = []
        if not obj:
            fields.append(('email_secundario', 'confirma_email'))
        else:
            fields.append('email_secundario')

        # se for admin mostra o campo "tem_digital_fraca"
        if request.user.is_superuser:
            fields.append('tem_digital_fraca')

        dados_extras = (('Dados extras', {'fields': fields}),)
        if fields:
            fieldsets = fieldsets + dados_extras
        return fieldsets

    def get_foto(self, obj):
        return mark_safe(f'<div class="photo-circle sm"><img src="{obj.get_foto_75x100_url()}"></div>')

    get_foto.short_description = 'Foto'

    def get_ocupacao(self, obj):
        if obj.tem_ocupacao_ativa():
            return mark_safe('<span class="status status-success">Sim</span>')
        return mark_safe('<span class="status status-error">Não</span>')

    get_ocupacao.short_description = 'Ocupação ativa como Prestador de Serviço?'

    def get_documento_identificador(self, obj):
        return obj.pessoa_fisica.documento_identificador

    get_documento_identificador.short_description = 'Documento Identificador'
    get_documento_identificador.admin_order_field = 'pessoa_fisica__documento_identificador'

    def get_nome(self, obj):
        return obj.pessoa_fisica.nome

    get_nome.short_description = 'Nome'
    get_nome.admin_order_field = 'pessoa_fisica__nome'

    def get_email_secundario(self, obj):
        return obj.email_pessoal

    get_email_secundario.short_description = 'Email Pessoal'
    get_email_secundario.admin_order_field = 'vinculos__email_pessoal'

    def get_papeis(self, obj):
        texto = '<ul>'
        for papel in obj.papeis_ativos:
            texto += f'<li>{papel}</li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_papeis.short_description = 'Papéis'

    def get_tipo_login(self, obj):
        texto = '<ul>'
        if obj.tem_ocupacao_ativa():
            texto += '<li>Login Via SUAP</li>'
        if obj.pessoa_fisica.cpf and obj.tem_papel_ativo_usuario_externo:
            texto += '<li>Login Via Gov.BR</li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_tipo_login.short_description = 'Tipos de Login'

    def get_opcoes(self, obj):
        texto = '<ul class="action-bar">'
        if self.request.user.has_group_cached(['Coordenador de TI sistêmico']):
            if obj.ativo:
                texto += f'<li><a href="/comum/usuario_externo/inativar/{obj.pk:d}/" class="btn danger"><span class="fas fa-toggle-off" aria-hidden="true"></span> Inativar usuário</a></li>'
            else:
                texto += f'<li><a href="/comum/usuario_externo/ativar/{obj.pk:d}/" class="btn success"><span class="fas fa-toggle-on" aria-hidden="true"></span> Ativar usuário</a></li>'

        if self.request.user.has_perm('comum.change_prestadorservico'):
            if not obj.tem_ocupacao_ativa():
                texto += f'<li><a href="/comum/ocupacao_prestador/{obj.pk:d}/" class="btn success"><span class="fas fa-plus" aria-hidden="true"></span> Vincular ocupação</a></li>'
            texto += f'<li><a href="/comum/alterar_foto_prestador/{obj.pk:d}/" class="btn primary"><span class="fas fa-edit" aria-hidden="true"></span> Alterar foto</a></li>'

        if (
            self.request.user.has_group_cached(['Gerente de Usuário Externo', 'Coordenador de TI sistêmico'])
            and not obj.tem_papel_ativo_usuario_externo()
        ):
            texto += f'<li><a href="/comum/criar_papel_usuario_externo/{obj.pk:d}/" class="btn"><span class="fas fa-edit" aria-hidden="true"></span>Criar papel de Usuário Externo</a></li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def response_add(self, request, obj, post_url_continue=None):
        obj = PrestadorServico.objects.filter(pk=obj.pk).first()
        return httprr(
            '/admin/comum/prestadorservico/',
            f'Usuário Externo cadastrado com sucesso. Foi enviado um e-mail para {obj.email_notificacao} com instruções para acessar o SUAP.',
        )

    def save_model(self, request: HttpRequest, obj: PrestadorServico, form: PrestadorServicoForm, change: bool) -> None:
        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': form.cleaned_data['cpf'],
            'nome_registro': form.cleaned_data['nome_registro'],
            'nome_social': form.cleaned_data['nome_social'],
            'nome_usual': form.cleaned_data['nome_usual'],
            'nacionalidade': int(form.cleaned_data['nacionalidade'] or 1),
            'passaporte': form.cleaned_data['passaporte'] or '',
            'pais_origem': form.cleaned_data.get('pais_origem'),
            'sexo': form.cleaned_data['sexo'],
            'email_secundario': form.cleaned_data['email_secundario'],
            'email': form.cleaned_data['email_secundario'],
            'tem_digital_fraca': form.cleaned_data.get('tem_digital_fraca', False),
        }
        dados: PrestadorServicoCadastro = {
            'pessoa_fisica': pessoa_fisica,
            'justificativa_cadastro': form.cleaned_data['justificativa_cadastro'],
            'ativo': form.cleaned_data.get('ativo', obj.ativo),
        }

        prestador = PrestadorServico.update_or_create(dados, existente=obj if change else None)['prestador']
        obj.pk = prestador.pk


admin.site.register(PrestadorServico, PrestadorServicoAdmin)


class PredioAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('nome', 'uo', 'ativo')
    list_filter = ('nome', 'uo', 'ativo')
    fieldsets = (
        ('Dados gerais', {'fields': ('nome', 'uo', 'ativo')}),
        (
            'Sistemas Construtivos',
            {
                'fields': (
                    'estrutura',
                    'vedacao',
                    'cobertura',
                    'sistema_sanitario',
                    'sistema_abastecimento',
                    'sistema_alimentacao_eletrica',
                    'potencia_transformador',
                    'informacao_sistema_alimentacao_eletrica',
                    'sistema_protecao_descarga_atmosferica',
                    'acabamento_externo',
                )
            },
        ),
    )
    form = PredioForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(uo=utils.get_uo(request.user))


admin.site.register(Predio, PredioAdmin)


class ObraAdmin(ModelAdminPlus):
    form = ObraForm


admin.site.register(Obra, ObraAdmin)


class CombateIncendioPanicoAdmin(ModelAdminPlus):
    pass


admin.site.register(CombateIncendioPanico, CombateIncendioPanicoAdmin)


def get_uo_predio_listfilter(parametro_predio='predio', title_predio='Prédio', title_uo=nomenclatura.campus):
    parametro_uo = f'{parametro_predio}__uo'

    qs_filter_predio = f'{parametro_predio}__id__exact'
    qs_filter_uo = f'{parametro_predio}__uo__id__exact'

    class PredioFilter(admin.SimpleListFilter):
        title = str(title_predio.capitalize())
        parameter_name = str(parametro_predio)

        def lookups(self, request, model_admin):
            if parametro_uo in request.GET:
                return Predio.objects.filter(uo__id__exact=request.GET.get(parametro_uo)).values_list('id', 'nome')
            return Predio.objects.all().values_list('id', 'nome')

        def queryset(self, request, queryset):
            if self.value():
                predio = Predio.objects.all().filter(pk=request.GET.get(parametro_predio))
                if parametro_uo in request.GET:
                    predio = predio.filter(uo__pk=request.GET.get(parametro_uo))
                if predio.exists():
                    return queryset.filter(**{qs_filter_predio: self.value()})
                else:
                    self.used_parameters.pop(self.parameter_name)
            return queryset

    class UoFilter(admin.SimpleListFilter):
        title = str(title_uo.capitalize())
        parameter_name = str(parametro_uo)

        def lookups(self, request, model_admin):
            return UnidadeOrganizacional.objects.uo().values_list('id', 'sigla')

        def queryset(self, request, queryset):
            if self.value():
                uo = UnidadeOrganizacional.objects.uo().filter(pk=request.GET.get(parametro_uo))
                if uo.exists():
                    return queryset.filter(**{qs_filter_uo: self.value()})
                else:
                    self.used_parameters.pop(self.parameter_name)
            return queryset

    return (UoFilter, PredioFilter)


class SalaAdmin(ModelAdminPlus):
    form = SalaForm
    list_display = ('nome', 'show_campus_e_predio', 'ativa', 'agendavel', 'get_avaliadores', 'get_opcoes')
    list_display_icons = True
    list_filter = (CustomTabListFilter, *get_uo_predio_listfilter(), 'agendavel', 'ativa')
    list_per_page = 20
    actions = ['sala_agendavel', 'sala_naoagendavel']
    search_fields = ('nome', 'predio__nome')
    show_count_on_tabs = True
    fieldsets = (
        ('Dados gerais', {'fields': ('nome', 'predio', 'capacidade', 'setores', 'ativa')}),
        ('Agendamento', {'fields': ('agendavel', 'avaliadores_de_agendamentos', 'restringir_agendamentos_no_campus', 'informacoes_complementares')}),
        ('Dados complementares', {'fields': ('area_util', 'area_parede', 'uso', 'classificacao')}),
        (
            'Acabamento e Sistemas Prediais',
            {
                'fields': (
                    'instalacao_eletrica',
                    'instalacao_logica',
                    'instalacao_hidraulica',
                    'instalacao_gases',
                    'climatizacao',
                    'acabamento_parede',
                    'piso',
                    'forro',
                    'esquadrias',
                )
            },
        ),
    )

    def get_tabs(self, request):
        return ['tab_minhas_salas']

    def tab_minhas_salas(self, request, queryset):
        return queryset.filter(avaliadores_de_agendamentos=request.user)

    tab_minhas_salas.short_description = 'Salas que Avalio'

    def show_campus_e_predio(self, obj):
        return mark_safe(f'{obj.predio.uo.sigla} / {obj.predio.nome}')

    show_campus_e_predio.short_description = f'{nomenclatura.campus}/Prédio'

    def get_avaliadores(self, obj):
        if obj.avaliadores_de_agendamentos.exists():
            retorno = []
            for avaliador in obj.avaliadores_de_agendamentos.all():
                retorno.append(format_user(avaliador))
            return mark_safe(', '.join(retorno))
        elif obj.agendavel:
            return mark_safe('<span class="status status-error">Não possui avaliador</span>')
        else:
            return mark_safe('-')

    get_avaliadores.short_description = 'Avaliadores de Agendamentos'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('comum.change_sala'):
            if 'sala_agendavel' in actions:
                del actions['sala_agendavel']
            if 'sala_naoagendavel' in actions:
                del actions['sala_naoagendavel']
        return actions

    def sala_agendavel(self, request, queryset):
        try:
            ids = request.POST.getlist('_selected_action')
            if ids:
                ids = list(map(int, ids))
                queryset.filter(id__in=ids).update(agendavel=True)
                messages.success(request, 'Alterações de sala realizadas com sucesso.')
        except Exception:
            messages.error(request, 'Não foi possível realizar a ação.')

    sala_agendavel.short_description = 'Permitir agendamentos'

    def sala_naoagendavel(self, request, queryset):
        try:
            ids = request.POST.getlist('_selected_action')
            if ids:
                ids = list(map(int, ids))
                queryset.filter(id__in=ids).update(agendavel=False)
                messages.success(request, 'Alterações de sala realizadas com sucesso.')
        except Exception:
            messages.error(request, 'Não foi possível realizar a ação.')

    sala_naoagendavel.short_description = 'Indisponibilizar agendamentos'

    def get_opcoes(self, obj):
        retorno = ''
        if obj.pode_agendar(self.request.user):
            if obj.is_agendavel():
                retorno = f'<a class="btn success" href="/comum/sala/solicitar_reserva/{obj.pk}/">Solicitar/Ver Reservas</a>'
            elif not obj.ativa:
                retorno = '<span class="status status-error">Inativa</span>'
            elif not obj.agendavel:
                retorno = '<span class="status status-error">Não é agendável</span>'
            elif not obj.avaliadores_de_agendamentos.exists():
                retorno = '<span class="status status-error">Não possui avaliador</span>'
        elif obj.is_agendavel():
            retorno = '<span class="status status-error">Esta sala só pode ser agendada por usuários do mesmo campus</span>'
        else:
            retorno = '<span class="status status-error">Não é agendável</span>'

        return mark_safe(retorno)

    get_opcoes.short_description = 'Opções'

    def save_related(self, request, form, formsets, change):
        avaliadores_antigos = list(form.instance.avaliadores_de_agendamentos.all())
        super().save_related(request, form, formsets, change)
        avaliadores_atuais = list(form.instance.avaliadores_de_agendamentos.all())
        grupo_avaliador_sala = Group.objects.get(name='Avaliador de Sala')
        for avaliador in avaliadores_antigos:
            if not avaliador.salas_avaliadas.exists():
                usuario_grupo = UsuarioGrupo.objects.filter(user=avaliador, group=grupo_avaliador_sala)
                if usuario_grupo.exists() and UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_grupo[0]).exists():
                    UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_grupo[0]).delete()
                avaliador.groups.remove(grupo_avaliador_sala)

        for avaliador in avaliadores_atuais:
            avaliador.groups.add(grupo_avaliador_sala)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        pode_editar = super().has_change_permission(request, obj)
        if obj:
            pode_editar = pode_editar and obj.predio.uo == utils.get_uo(request.user)

        return pode_editar

    def get_action_bar_view(self, request, obj):
        items = []
        if obj.eh_avaliador(request.user):
            items.append({'url': f'/comum/sala/cancelar_reservas_periodo/{obj.id}/', 'label': 'Cancelar Reservas por Período'})
        return items


admin.site.register(Sala, SalaAdmin)


class SolicitacaoReservaSalaAdmin(ModelAdminPlus):
    list_display = ('sala', 'solicitante', 'get_periodo', 'get_status', 'data_solicitacao')
    list_filter = (
        CustomTabListFilter,
        'status',
        'sala',
        'solicitante',
        ('data_inicio', DateRangeListFilter),
        ('data_fim', DateRangeListFilter),
    )
    search_fields = ('sala__nome', 'solicitante__vinculo__pessoa__search_fields_optimized')
    date_hierarchy = 'data_inicio'
    ordering = ('-data_inicio', '-hora_inicio')
    list_display_icons = True
    export_to_xls = True
    show_count_on_tabs = True

    def show_list_display_icons(self, obj: SolicitacaoReservaSala) -> str:
        out = []
        if obj.pode_ver(self.request.user):
            out.append(icon('view', obj.get_absolute_url()))

        if obj.pode_excluir(self.request.user):
            # A exclusão exige POST. A linha já está dentro do `#changelist-form` (POST com CSRF), e
            # form aninhado é descartado pelo navegador: o botão reaproveita esse form via `formaction`.
            # Sem type="submit" para o main.js pedir a confirmação.
            out.append(
                format_html(
                    '<button formaction="/comum/sala/excluir_solicitacao/{}/" formmethod="post" class="icon icon-delete" title="Remover" '
                    'data-confirm="{}"><span class="visually-hidden">Remover</span></button>',
                    obj.id,
                    f'Tem certeza que deseja excluir a solicitação de reserva da sala {obj.sala} de {obj.get_periodo()}?',
                )
            )
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = 'Ações'

    def add_view(self, request):
        uo = utils.get_uo(request.user)
        if uo:
            return httprr(f'/admin/comum/sala/?agendavel__exact=1&predio__uo={uo.id:d}')
        else:
            return httprr('/', 'Você não possui permissão para realizar isto.', 'error')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if Sala.eh_avaliador_salas(request.user):
            return qs.filter(solicitante=request.user) | qs.filter(sala__id__in=request.user.salas_avaliadas.all())

        return qs.filter(solicitante=request.user)

    def get_tabs(self, request):
        tabs = []
        if Sala.eh_avaliador_salas(request.user):
            tabs = ['tab_minhas_solicitacoes', 'tab_solicitacoes_a_avaliar', 'tab_excluidas']
        tabs.append('tab_minhas_solicitacoes_futuras')
        tabs.append('tab_meu_interesse')
        tabs.append('tab_excluidas')
        return tabs

    def get_periodo(self, obj):
        return mark_safe(obj.get_periodo())

    get_periodo.admin_order_field = 'data_inicio'
    get_periodo.short_description = 'Período Solicitado'

    def tab_minhas_solicitacoes_futuras(self, request, queryset):
        agora = datetime.now()
        reservas_derefidas = queryset.filter(solicitante=request.user)
        reservas_derefidas_hoje = reservas_derefidas.filter(data_inicio=agora.date(), hora_inicio__gt=agora.time())
        reservas_derefidas_futuras = reservas_derefidas.filter(data_inicio__gt=agora.date())
        return reservas_derefidas_hoje | reservas_derefidas_futuras

    tab_minhas_solicitacoes_futuras.short_description = 'Minhas Solicitações Futuras'

    def tab_minhas_solicitacoes(self, request, queryset):
        return queryset.filter(solicitante=request.user)

    tab_minhas_solicitacoes.short_description = 'Minhas Solicitações'

    def tab_meu_interesse(self, request, queryset):
        return SolicitacaoReservaSala.objects.filter(interessados_vinculos__user=request.user)

    tab_meu_interesse.short_description = 'Meu Interesse'

    def tab_solicitacoes_a_avaliar(self, request, queryset):
        salas_avaliadas = request.user.salas_avaliadas.values_list('id', flat=True)
        return queryset.filter(sala_id__in=salas_avaliadas, status=SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO)

    tab_solicitacoes_a_avaliar.short_description = 'Solicitações a Avaliar'

    def tab_excluidas(self, request, queryset):
        return SolicitacaoReservaSala.objects.filter(status=SolicitacaoReservaSala.STATUS_EXCLUIDA)

    tab_excluidas.short_description = 'Excluídas'

    def get_status(self, obj):
        return mark_safe(status(obj.get_status_display()))

    get_status.short_description = 'Situação'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Sala',
            'Solicitante',
            'Período Solicitado',
            'Data início',
            'Data Final',
            'Hora início',
            'Hora Fim',
            'CH total agendada',
            'Situação',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.sala,
                obj.solicitante,
                obj.get_periodo(),
                obj.data_inicio,
                obj.data_fim,
                obj.data_hora_inicio.strftime('%H:%M'),
                obj.data_hora_fim.strftime('%H:%M'),
                obj.get_ch_solicitacao(),
                obj.get_status_display(),
            ]
            rows.append(row)
        return rows

    def delete_view(self, request, object_id, extra_context=None):
        solicitacao = get_object_or_404(SolicitacaoReservaSala, pk=object_id)
        if not solicitacao.pode_excluir(request.user):
            raise PermissionDenied

        return super().delete_view(request, object_id, extra_context)


admin.site.register(SolicitacaoReservaSala, SolicitacaoReservaSalaAdmin)


###############
# Pensionista
###############


class NullDataFimPgtoFilter(SimpleListFilter):
    title = _('data fim de pagamento')
    parameter_name = ''

    def lookups(self, request, model_admin):
        return (('nenhum', _('Nenhum')),)

    def queryset(self, request, queryset):
        if self.value() == 'nenhum':
            return queryset.filter(data_fim_pagto_beneficio__isnull=True)
        return queryset.all()


class PensionistaAdmin(ModelAdminPlus):
    list_display = (
        'matricula',
        'get_nome',
        'get_cpf',
        'representante_legal',
        'data_inicio_pagto_beneficio',
        'data_fim_pagto_beneficio',
        'get_instituidor',
    )
    ordering = ('matricula', 'usuario_externo__pessoa_fisica__nome')
    search_fields = (
        'usuario_externo__pessoa_fisica__nome',
        'matricula',
        'usuario_externo__pessoa_fisica__cpf',
        'contracheque__servidor__pessoa_fisica__nome',
        'contracheque__servidor__matricula',
    )
    form = PensionistaForm
    list_per_page = 50
    list_display_icons = True

    def get_instituidor(self, obj):
        return obj.instituidor

    def get_nome(self, obj):
        return obj.usuario_externo.pessoa_fisica.nome

    get_nome.short_description = 'Nome'
    get_nome.admin_order_field = 'usuario_externo__nome'

    def get_cpf(self, obj):
        return obj.usuario_externo.pessoa_fisica.cpf

    get_cpf.short_description = 'CPF'
    get_cpf.admin_order_field = 'usuario_externo__cpf'

    get_instituidor.short_description = 'Instituidor'


admin.site.register(Pensionista, PensionistaAdmin)


###############
# Grau de Parentesco
###############


class GrauParentescoAdmin(ModelAdminPlus):
    list_display = ('codigo', 'nome', 'get_situacao')
    ordering = ('excluido', 'codigo')
    search_fields = ('codigo', 'nome')
    list_filter = ('excluido',)
    list_per_page = 50
    list_display_icons = True

    def get_situacao(self, obj):
        return status(not obj.excluido, ['Excluído', 'Ativo'])

    get_situacao.short_description = 'Situação'


admin.site.register(GrauParentesco, GrauParentescoAdmin)


###############
# Benefício
###############


class BeneficioAdmin(ModelAdminPlus):
    list_display = ('codigo', 'nome', 'get_situacao')
    ordering = ('excluido', 'codigo')
    search_fields = ('codigo', 'nome')
    list_filter = ('excluido',)
    list_per_page = 50
    list_display_icons = True

    def get_situacao(self, obj):
        return status(not obj.excluido, ['Excluído', 'Ativo'])

    get_situacao.short_description = 'Situação'


admin.site.register(Beneficio, BeneficioAdmin)


###############
# Dependente
###############


class BeneficioDependenteInline(admin.TabularInline):
    model = BeneficioDependente
    fields = ('beneficio', 'data_inicio', 'data_termino')
    extra = 0
    readonly_fields = ('beneficio', 'data_inicio', 'data_termino')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DependenteAdmin(ModelAdminPlus):
    list_display = ('get_nome', 'get_cpf', 'matricula', 'servidor', 'grau_parentesco', 'codigo_condicao')
    ordering = ('usuario_externo__pessoa_fisica__nome',)
    search_fields = (
        'usuario_externo__pessoa_fisica__nome',
        'usuario_externo__pessoa_fisica__cpf',
        'matricula',
        'servidor__matricula',
        'servidor__pessoa_fisica__nome',
    )
    list_filter = ('grau_parentesco',)
    list_per_page = 50
    list_display_icons = True
    inlines = [BeneficioDependenteInline]
    readonly_fields = (
        'usuario_externo',
        'matricula',
        'servidor',
        'representante_legal',
        'grau_parentesco',
        'codigo_condicao',
    )

    def get_nome(self, obj):
        return obj.usuario_externo.pessoa_fisica.nome

    get_nome.short_description = 'Nome'
    get_nome.admin_order_field = 'usuario_externo__pessoa_fisica__nome'

    def get_cpf(self, obj):
        return obj.usuario_externo.pessoa_fisica.cpf

    get_cpf.short_description = 'CPF'
    get_cpf.admin_order_field = 'usuario_externo__pessoa_fisica__cpf'


admin.site.register(Dependente, DependenteAdmin)


###############
# Benefício-Dependente
###############


class BeneficioDependenteAdmin(ModelAdminPlus):
    list_display = ('get_dependente_nome', 'get_dependente_cpf', 'beneficio', 'data_inicio', 'get_data_termino')
    ordering = ('dependente__usuario_externo__pessoa_fisica__nome', 'beneficio__nome', 'data_inicio')
    search_fields = (
        'dependente__usuario_externo__pessoa_fisica__nome',
        'dependente__usuario_externo__pessoa_fisica__cpf',
        'dependente__matricula',
        'beneficio__codigo',
        'beneficio__nome',
    )
    list_filter = ('beneficio',)
    list_per_page = 50
    list_display_icons = True

    def get_dependente_nome(self, obj):
        return obj.dependente.usuario_externo.pessoa_fisica.nome

    get_dependente_nome.short_description = 'Dependente'
    get_dependente_nome.admin_order_field = 'dependente__usuario_externo__pessoa_fisica__nome'

    def get_dependente_cpf(self, obj):
        return obj.dependente.usuario_externo.pessoa_fisica.cpf

    get_dependente_cpf.short_description = 'CPF'
    get_dependente_cpf.admin_order_field = 'dependente__usuario_externo__pessoa_fisica__cpf'

    def get_data_termino(self, obj):
        return obj.data_termino or '—'

    get_data_termino.short_description = 'Data Término'
    get_data_termino.admin_order_field = 'data_termino'


admin.site.register(BeneficioDependente, BeneficioDependenteAdmin)


###############
# Tipo Prestador
###############


class OcupacaoAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao', 'representante')
    list_filter = ('representante',)
    list_display_icons = True
    ordering = ('descricao',)
    search_fields = ('descricao', 'codigo')
    list_per_page = 50


admin.site.register(Ocupacao, OcupacaoAdmin)


class NotificacaoAdmin(ModelAdminPlus):
    pass


admin.site.register(Notificacao, NotificacaoAdmin)


class GerenciamentoGrupoAdmin(ModelAdminPlus):
    list_display = ('grupo_gerenciador', 'get_grupos_gerenciados', 'eh_local')
    search_fields = ('grupo_gerenciador__name', 'grupos_gerenciados__name')
    list_filter = ('eh_local', 'grupo_gerenciador')
    form = GrupoGerenciamentoForm
    list_display_icons = True

    def get_grupos_gerenciados(self, obj):
        strOut = '<ul>'
        for grupo in obj.grupos_gerenciados.all():
            strOut += f'<li>{grupo.name}</li>'
        strOut += '</ul>'
        return mark_safe(strOut)

    get_grupos_gerenciados.short_description = 'Grupos'


admin.site.register(GerenciamentoGrupo, GerenciamentoGrupoAdmin)


class RegistroEmissaoDocumentoAdmin(ModelAdminPlus):
    list_display = ('id', 'tipo', 'data_emissao', 'codigo_verificador', 'tipo_objeto', 'modelo_pk', 'cancelado')
    ordering = ('id',)
    list_filter = (CustomTabListFilter, 'tipo', 'tipo_objeto')
    search_fields = ('modelo_pk', 'codigo_verificador')
    list_per_page = 50
    actions = ['cancelar']
    show_count_on_tabs = True

    def cancelar(self, request, queryset):
        queryset.update(cancelado=True)

    cancelar.short_description = 'Cancelar'

    def get_tabs(self, request):
        return ['tab_vencidos', 'tab_a_vencer', 'tab_permanentes']

    def tab_vencidos(self, request, queryset):
        return queryset.filter(data_validade__lt=datetime.now())

    tab_vencidos.short_description = 'Vencidos'

    def tab_a_vencer(self, request, queryset):
        return queryset.filter(data_validade__gte=datetime.now())

    tab_a_vencer.short_description = 'À vencer'

    def tab_permanentes(self, request, queryset):
        return queryset.filter(data_validade__isnull=True)

    tab_permanentes.short_description = 'Permanentes'


admin.site.register(RegistroEmissaoDocumento, RegistroEmissaoDocumentoAdmin)


########################
# django.contrib.admin #
########################


class HasVinculoListFilter(admin.SimpleListFilter):
    title = 'Vínculo'
    parameter_name = 'has_vinculo'

    def lookups(self, request, model_admin):
        return (
            ('eh_servidor', 'Servidor'),
            ('eh_aluno', 'Aluno'),
            ('eh_prestador', 'Prestador de Serviços'),
            ('eh_docente', 'Docente'),
            ('eh_tecnico_administrativo', 'Técnico Administrativo'),
        )

    """
    eh_servidor = models.BooleanField(default=False)
    eh_aluno = models.BooleanField(default=False)
    eh_prestador = models.BooleanField(default=False)
    eh_docente = models.BooleanField(default=False)
    eh_tecnico_administrativo = models.BooleanField(default=False)
    """

    def queryset(self, request, queryset):
        if self.value() == 'eh_servidor':
            return queryset.filter(eh_servidor=True)
        elif self.value() == 'eh_aluno':
            return queryset.filter(eh_aluno=True)
        elif self.value() == 'eh_prestador':
            return queryset.filter(eh_prestador=True)
        elif self.value() == 'eh_docente':
            return queryset.filter(eh_docente=True)
        elif self.value() == 'eh_tecnico_administrativo':
            return queryset.filter(eh_tecnico_administrativo=True)
        else:
            return queryset


class HasProfileListFilter(admin.SimpleListFilter):
    title = 'pessoa fisica'
    parameter_name = 'has_profile'

    def lookups(self, request, model_admin):
        return ((True, 'Sim'), (False, 'Não'))

    def queryset(self, request, queryset):
        if self.value() == 'True':
            return queryset.filter(vinculo__pessoa__pessoafisica__isnull=False)
        elif self.value() == 'False':
            return queryset.filter(vinculo__pessoa__pessoafisica__isnull=True)
        else:
            return queryset


class NotificationTypesFilter(SimpleListFilter):
    title = 'Tipos de Notificação'
    parameter_name = 'tipos_notificacao'

    def lookups(self, request, model_admin):
        return [
            ('both', 'SUAP e E-mail'),
            ('suap', 'Somente SUAP'),
            ('email', 'Somente E-mail'),
        ]

    def queryset(self, request, queryset):
        val = self.value()
        if val == 'both':
            return queryset.filter(preferencia__via_suap=True, preferencia__via_email=True)
        if val == 'suap':
            return queryset.filter(preferencia__via_suap=True, preferencia__via_email=False)
        if val == 'email':
            return queryset.filter(preferencia__via_suap=False, preferencia__via_email=True)
        return queryset


class TwoFactorActiveFilter(SimpleListFilter):
    title = '2FA'
    parameter_name = 'two_factor'

    def lookups(self, request, model_admin):
        return [('yes', 'Ativo'), ('no', 'Inativo')]

    def queryset(self, request, queryset):
        val = self.value()
        if val == 'yes':
            return queryset.filter(autenticacaodoisfatores__ativo=True)
        if val == 'no':
            return queryset.filter(Q(autenticacaodoisfatores__ativo=False) | Q(autenticacaodoisfatores__isnull=True))
        return queryset


class UserAdmin(AuthUserAdmin, ModelAdminPlus):
    list_display = (
        'username',
        'get_full_name',
        'email',
        'vinculo',
        'is_active',
        'forcar_troca_senha',
        'tema_preferido',
        'tipos_notificacao',
        'autenticacao_2fa',
        'last_login',
        'data_ultima_alteracao_senha',
        'get_opcoes',
    )
    search_fields = ('username', 'email', 'first_name', 'last_name', 'email')
    filter_horizontal = ('user_permissions',)
    list_filter = (
        *get_uo_setor_listfilter('vinculo__setor', 'Setor SUAP', f'{nomenclatura.campus} SUAP'),
        'is_active',
        'is_superuser',
        'preferencia__tema',
        'groups',
        HasProfileListFilter,
        HasVinculoListFilter,
    )
    list_display_icons = True

    actions = [
        'forcar_troca_senha_proximo_login',
        'desfazer_troca_senha_proximo_login',
        'habilitar_usuario',
        'desabilitar_usuario',
        'sincronizar_usuario_no_ad',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def get_fieldsets(self, *args, **kwargs):
        return (
            (None, {'fields': ('username', 'password')}),
            (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
            (
                _('Permissions'),
                {
                    'fields': (
                        'is_active',
                        'is_staff',
                        'is_superuser',
                        'groups',
                        'user_permissions',
                    ),
                },
            ),
            (_('Important dates'), {'fields': ('last_login', 'date_joined', 'data_ultima_alteracao_senha')}),
        )

    def get_opcoes(self, obj):
        opcoes = '<ul class="action-bar">'
        if is_ldap_enabled():
            opcoes += f'<li><a href="/ldap_backend/show_object/{obj.username}/" class="btn">LDAP Actions</a></li>'
        # mostrar ação de desabilitar 2FA para superuser quando o alvo tiver 2FA ativo
        try:
            request_user = getattr(self, 'request', None) or None
            if request_user and request_user.user.is_superuser:
                if getattr(obj, 'autenticacaodoisfatores_habilitada', lambda: False)():
                    des_url = reverse('desabilitar_2fa_usuario', args=[obj.pk])
                    opcoes += f'<li><a href="{des_url}" class="btn danger">Desabilitar 2FA</a></li>'
        except Exception:
            # não bloquear exibição caso algo falhe
            pass
        opcoes += '</ul>'
        return mark_safe(opcoes)

    get_opcoes.short_description = 'Opções'

    def get_list_filter(self, request):
        # include our custom filters plus forcar_troca_senha
        base = super().get_list_filter(request)
        extra = ('forcar_troca_senha', NotificationTypesFilter, TwoFactorActiveFilter)
        # if non-superuser campus coordinator we keep their reduced set
        if not request.user.is_superuser and in_group(request.user, 'Coordenador de TI de campus'):
            return base
        return (*base, *extra)

    def get_list_display(self, request):
        return self.list_display

    def changelist_view(self, request, extra_context=None):
        # expor request para métodos que precisam saber quem é o usuário atual
        self.request = request
        return super().changelist_view(request, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        self.request = request
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def tipos_notificacao(self, obj):
        parts = []
        try:
            if getattr(obj, 'preferencia', None) and obj.preferencia.via_suap:
                parts.append('SUAP')
            if getattr(obj, 'preferencia', None) and obj.preferencia.via_email:
                parts.append('E-mail')
        except Exception:
            pass
        return ', '.join(parts) if parts else 'Nenhuma'

    tipos_notificacao.short_description = 'Notificações'
    tipos_notificacao.admin_order_field = 'preferencia__via_suap'

    def autenticacao_2fa(self, obj):
        try:
            return format_(obj.autenticacaodoisfatores_habilitada())
        except Exception:
            return format_(False)

    autenticacao_2fa.short_description = '2FA ativo?'
    autenticacao_2fa.admin_order_field = 'autenticacaodoisfatores__ativo'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and in_group(request.user, 'Coordenador de TI de campus'):
            qs = qs.filter(vinculo__setor__uo=request.user.get_vinculo().setor.uo)
        return qs

    def desabilitar_usuario(self, request, queryset):
        if not in_group(request.user, 'Coordenador de TI de campus, Coordenador de TI sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return
        queryset.update(is_active=False)
        self.message_user(request, 'Procedimento realizado com sucesso.')

    desabilitar_usuario.short_description = 'Desabilitar usuário'

    def habilitar_usuario(self, request, queryset):
        if not in_group(request.user, 'Coordenador de TI de campus, Coordenador de TI sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return
        queryset.update(is_active=True)
        self.message_user(request, 'Procedimento realizado com sucesso.')

    habilitar_usuario.short_description = 'Habilitar usuário'

    def sincronizar_usuario_no_ad(self, request, queryset):
        if not in_group(request.user, 'Coordenador de TI de campus, Coordenador de TI sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        conf = get_ldap_conf()
        if conf:
            for obj in queryset:
                conf.sync_user(obj.username)

        self.message_user(request, 'Procedimento realizado com sucesso.')

    sincronizar_usuario_no_ad.short_description = 'Sincronizar usuário no AD'

    def forcar_troca_senha_proximo_login(self, request, queryset):
        if not in_group(request.user, 'Coordenador de TI de campus, Coordenador de TI sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        conf = get_ldap_conf()
        for obj in queryset:
            if conf:
                conf.force_user_reset_password(obj.username)
            """ force_user_reset_password """
            obj.forcar_troca_senha = True
            obj.data_solicitacao_forcar_troca_senha = datetime.now()
            obj.save()

        self.message_user(request, 'Procedimento realizado com sucesso.')

    forcar_troca_senha_proximo_login.short_description = 'Forçar troca de senha no próximo login'

    def desfazer_troca_senha_proximo_login(self, request, queryset):
        if not in_group(request.user, 'Coordenador de TI de campus, Coordenador de TI sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        conf = get_ldap_conf()
        for obj in queryset:
            if conf:
                conf.force_user_not_reset_password(obj.username)
            """ force_user_reset_password """
            obj.forcar_troca_senha = False
            obj.data_solicitacao_forcar_troca_senha = None
            obj.save()

        self.message_user(request, 'Procedimento realizado com sucesso.')

    desfazer_troca_senha_proximo_login.short_description = 'Desfazer a troca de senha no próximo login'

    def get_actions(self, request):
        if request.user.is_superuser or in_group(request.user, 'Coordenador de TI de campus, Coordenador de TI sistêmico'):
            return super().get_actions(request)
        return []

    def get_groups(self, obj):
        out = ['<ol>']
        for g in obj.groups.order_by('name'):
            out.append(f'<li>{g.name}</li>')
        out.append('</ol>')
        return mark_safe(''.join(out))

    get_groups.short_description = _('groups')

    def get_full_name(self, obj):
        return obj.get_full_name()

    get_full_name.short_description = _('name')
    get_full_name.admin_order_field = 'first_name'

    def tema_preferido(self, obj):
        return obj.tema_preferido()

    tema_preferido.short_description = 'Tema Preferido'
    tema_preferido.admin_order_field = 'preferencia__tema'

    def eh_notificado_suap(self, obj):
        return format_(obj.eh_notificado_suap)

    eh_notificado_suap.short_description = 'É notificado via SUAP?'
    eh_notificado_suap.admin_order_field = 'preferencia__via_suap'

    def eh_notificado_email(self, obj):
        return format_(obj.eh_notificado_email)

    eh_notificado_email.short_description = 'É notificado via Email?'
    eh_notificado_email.admin_order_field = 'preferencia__via_suap'

    def get_urls(self):
        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        urls = super().get_urls()
        custom_urls = []
        return custom_urls + urls


# admin.site.unregister(User)
admin.site.register(User, UserAdmin)


class OauthLoginAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = 'user', 'data_hora'
    date_hierarchy = 'data_hora'
    list_filter = ('user',)


admin.site.register(OauthLogin, OauthLoginAdmin)


def _pode_consultar_contas_na_seguranca(user: User) -> bool:
    return user.is_superuser or user.has_group_cached('Coordenador de Segurança da Informação')


def _pode_gerenciar_contas_na_seguranca(user: User) -> bool:
    return _pode_consultar_contas_na_seguranca(user)


def _pode_consultar_senhas_expostas(user: User) -> bool:
    return _pode_consultar_contas_na_seguranca(user) or user.has_group_cached('Coordenador de TI sistêmico')


class SessionInfoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_filter = ('expired',)
    ordering = ('-date_time',)
    fieldsets = (('Dados gerais', {'fields': ('get_user', 'get_device', 'ip_address', 'date_time', 'expired')}),)

    def get_action_bar(self, request, *args, **kwargs):
        items = super().get_action_bar(request, *args, **kwargs)
        url_base = '/comum/remote_logout_all/'
        items.append({'url': url_base, 'label': 'Deslogar todas as outras sessões'})
        return items

    def get_list_display(self, request: HttpRequest) -> tuple[str, ...]:
        if _pode_consultar_contas_na_seguranca(request.user):
            return ('show_list_display_icons', 'get_user', 'get_device', 'get_ip_location', 'date_time', 'expired', 'acoes')
        return ('show_list_display_icons', 'get_device', 'get_ip_location', 'date_time', 'expired', 'acoes')

    def get_search_fields(self, request: HttpRequest) -> tuple[str, ...]:
        if _pode_consultar_contas_na_seguranca(request.user):
            return (
                'device__user_agent',
                'device__nickname',
                'ip_address',
                'device__user__username',
                'device__user__vinculo__pessoa__pessoafisica__cpf',
                'device__user__vinculo__pessoa__nome',
            )
        return ()

    def get_list_filter(self, request: HttpRequest) -> tuple[str, ...]:
        if _pode_consultar_contas_na_seguranca(request.user):
            return (*self.list_filter, 'device__user')
        return self.list_filter

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return True

    def get_user(self, obj):
        return obj.device.user

    get_user.short_description = 'Usuário'
    get_user.admin_order_field = 'device__user'

    def get_device(self, obj):
        return obj.device.get_name()

    get_device.short_description = 'Dispositivo'
    get_device.admin_order_field = 'device__friendly_name'

    def get_ip_location(self, obj):
        if obj.ip_address:
            return mark_safe(f'<a href="https://ipinfo.io/{obj.ip_address}">{obj.ip_address}</a>')
        return '-'

    get_ip_location.short_description = 'Endereço IP'
    get_ip_location.admin_order_field = 'ip_address'

    def acoes(self, obj: SessionInfo) -> str:
        if obj.session_id == self.request.session.session_key:
            return 'Sessão atual'
        if obj.expired or not (_pode_gerenciar_contas_na_seguranca(self.request.user) or obj.device.user_id == self.request.user.id):
            return ''
        return mark_safe(f'<a href="/comum/remote_logout/{obj.pk}/" class="btn danger">Deslogar</a>')

    acoes.short_description = 'Ações'

    def get_queryset(self, request: HttpRequest, *args: object, **kwargs: object) -> QuerySet[SessionInfo]:
        qs = super().get_queryset(request, *args, **kwargs)
        if not _pode_consultar_contas_na_seguranca(request.user):
            qs = qs.filter(device__user=request.user)
        return qs.select_related('device__user__vinculo__pessoa__pessoafisica')


admin.site.register(SessionInfo, SessionInfoAdmin)


class DeviceAdmin(ModelAdminPlus):
    list_display_icons = True
    list_filter = ('activated',)
    fieldsets = (('Dados gerais', {'fields': ('user', 'user_agent', 'activated')}),)

    def get_list_display(self, request: HttpRequest) -> tuple[str, ...]:
        if _pode_consultar_contas_na_seguranca(request.user):
            return ('show_list_display_icons', 'user', 'user_agent', 'nickname', 'friendly_name', 'activated', 'get_status', 'acoes')
        return ('show_list_display_icons', 'nickname', 'friendly_name', 'activated', 'get_status', 'acoes')

    def get_search_fields(self, request: HttpRequest) -> tuple[str, ...]:
        if _pode_consultar_contas_na_seguranca(request.user):
            return (
                'user_agent',
                'nickname',
                'friendly_name',
                'sessioninfo__ip_address',
                'user__username',
                'user__vinculo__pessoa__pessoafisica__cpf',
                'user__vinculo__pessoa__nome',
            )
        return ()

    def get_list_filter(self, request: HttpRequest) -> tuple[str, ...]:
        if _pode_consultar_contas_na_seguranca(request.user):
            return (*self.list_filter, 'user')
        return self.list_filter

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def get_status(self, obj):
        if obj.activated:
            status = 'Ativado'
        else:
            status = 'Desativado'
        if obj.user_agent == self.request.META.get('HTTP_USER_AGENT', '-') and obj.user == self.request.user:
            status += ' - Dispositivo Atual'
        return status

    get_status.short_description = 'Situação'

    def get_queryset(self, request: HttpRequest, *args: object, **kwargs: object) -> QuerySet[Device]:
        qs = super().get_queryset(request, *args, **kwargs)
        if not _pode_consultar_contas_na_seguranca(request.user):
            qs = qs.filter(user=request.user)
        return qs.select_related('user__vinculo__pessoa__pessoafisica')

    def acoes(self, obj: Device) -> str:
        pode_gerenciar = _pode_gerenciar_contas_na_seguranca(self.request.user)
        if not (pode_gerenciar or obj.user_id == self.request.user.id):
            return ''
        pode_editar_proprio = self.request.user.is_superuser or obj.user_id == self.request.user.id
        botoes = []
        if pode_editar_proprio:
            botoes.append(f'<li><a href="/comum/give_nickname_to_device/{obj.pk}/" class="btn popup">Apelidar</a></li>')
        atual = obj.user_agent == self.request.META.get('HTTP_USER_AGENT', '-') and obj.user == self.request.user

        if obj.activated:
            if not atual:
                botoes.append(f'<li><a href="/comum/deactivate_device/{obj.pk}/" class="btn danger">Desativar</a></li>')
        elif pode_editar_proprio:
            botoes.append(f'<li><a href="/comum/reactivate_device/{obj.pk}/" class="btn success">Reativar</a></li>')
        return mark_safe(f'<ul class="action-bar">{"".join(botoes)}</ul>') if botoes else ''

    acoes.short_description = 'Opções'


admin.site.register(Device, DeviceAdmin)

# remove "grupos" do gerenciamento de usuário do Django (/admin/comum/user/<id>/)
# O widget por padrão REMOVE todos os grupos do usuário e inclui novamente. Esse comportamento
# está gerando erros de integridade referencial na relação com "setores" (ver classe UsuarioGrupo em /comum/models.py)
UserAdmin.fieldsets = (
    (None, {'fields': ('username', 'password')}),
    (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
    (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'user_permissions')}),
    (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
)


class GroupAdmin(AuthGroupAdmin, ModelAdminPlus):
    list_display = ['id', 'name']


admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)


class GroupDetailAdmin(ModelAdminPlus):
    list_display = ['id', 'descricao', 'group']


admin.site.register(GroupDetail, GroupDetailAdmin)


class PermissionAdmin(ModelAdminPlus):
    search_fields = ['name', 'codename']
    list_display = ['name', 'content_type', 'codename']
    list_filter = ['content_type']


admin.site.register(Permission, PermissionAdmin)


class LogAdmin(ModelAdminPlus):
    search_fields = ('app', 'titulo', 'texto')
    list_display = ('horario', 'app', 'titulo', 'texto')
    list_filter = ('app', 'titulo')


admin.site.register(Log, LogAdmin)


class ReservaSalaAdmin(ModelAdminPlus):
    list_display = ('sala', 'get_descricao', 'get_solicitante', 'data_inicio', 'data_fim')
    list_filter = (
        CustomTabListFilter,
        'sala',
    )
    search_fields = ('solicitacao__justificativa',)
    ordering = ('data_inicio',)
    date_hierarchy = 'data_inicio'
    show_count_on_tabs = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_display_links = None

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        return qs.filter(cancelada=False, sala__predio__uo=utils.get_uo(request.user))

    def get_descricao(self, obj):
        if obj.solicitacao:
            return mark_safe(obj.solicitacao.justificativa)
        else:
            return mark_safe('-')

    get_descricao.short_description = 'Justificativa'

    def get_solicitante(self, obj):
        if obj.solicitacao:
            return mark_safe(obj.solicitacao.solicitante)
        else:
            return mark_safe('-')

    get_solicitante.short_description = 'Solicitante'

    def has_add_permission(self, request):
        return False

    def tab_meu_interesse(self, request, queryset):
        return ReservaSala.objects.filter(solicitacao__interessados_vinculos__user=request.user)

    tab_meu_interesse.short_description = 'Meu Interesse'

    def get_tabs(self, request):
        return ['tab_meu_interesse']


admin.site.register(ReservaSala, ReservaSalaAdmin)


class TipoCarteiraFuncionalAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_display = ('nome', 'get_modelo', 'template', 'data_cadastro', 'ativo')
    list_display_icons = True

    def get_modelo(self, obj):
        return mark_safe(f'<img src="{obj.modelo.url}" height="150" />')

    get_modelo.short_description = 'Modelo'


admin.site.register(TipoCarteiraFuncional, TipoCarteiraFuncionalAdmin)


class VinculoAdmin(ModelAdminPlus):
    form = VinculoForm
    search_fields = ('pessoa__nome',)
    list_filter = ('tipo_relacionamento',)
    list_display = ('pessoa', 'get_relacionamento')
    list_display_icons = True

    def get_relacionamento(self, obj):
        return f'{obj.relacionamento._meta.verbose_name} - {obj.relacionamento}'

    get_relacionamento.short_description = 'Relacionamento'


admin.site.register(Vinculo, VinculoAdmin)


class ContatoEmergenciaAdmin(ModelAdminPlus):
    list_display = ('pessoa_fisica', 'nome_contato', 'telefone')
    list_display_links = ('nome_contato',)
    search_fields = ('pessoa_fisica__nome', 'nome_contato', 'telefone')
    ordering = ('pessoa_fisica__nome', 'nome_contato', 'telefone')
    fields = ('nome_contato', 'telefone')
    form = ContatoEmergenciaForm
    pessoa_fisica_pk = None

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = ContatoEmergencia.objects
        if not request.user.has_perm('comum.view_contatoemergencia'):
            qs = qs.filter(pessoa_fisica=request.user.get_profile())
        return qs

    def has_add_permission(self, request):
        # adições não serão feitas via tela do admin
        return False

    def has_change_permission(self, request, obj=None):
        if obj and obj.pessoa_fisica == request.user.get_profile():
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.pessoa_fisica == request.user.get_profile():
            return True
        return super().has_delete_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        # get_queryset já prevê a listagem de apenas contatos que o usuário pode ver
        return True

    def delete_view(self, request, object_id, extra_context=None):
        self.pessoa_fisica_pk = get_object_or_404(ContatoEmergencia, pk=object_id).pessoa_fisica.pk
        return super().delete_view(request, object_id, extra_context)

    def response_add(self, request, obj, post_url_continue=None):
        self.pessoa_fisica_pk = obj.pessoa_fisica.pk
        return httprr(self.list_view_contatos(), 'Contato adicionado com sucesso.')

    def response_change(self, request, obj):
        if '_save' in request.POST:
            self.pessoa_fisica_pk = obj.pessoa_fisica.pk
            return httprr(self.list_view_contatos(), 'Contato editado com sucesso.')
        return super().response_change(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        return httprr(self.list_view_contatos(), 'Contato removido com sucesso.')

    def list_view_contatos(self):
        if self.pessoa_fisica_pk:
            return reverse(comum.views.listar_contatos_de_emergencia, kwargs={'pessoa_fisica_pk': self.pessoa_fisica_pk})
        return '/admin/comum/contatoemergencia'


admin.site.register(ContatoEmergencia, ContatoEmergenciaAdmin)


class ManutencaoProgramadaAdmin(ModelAdminPlus):
    form = ManutencaoProgramadaForm
    list_filter = ('tipo',)
    list_display = ('tipo', 'data_hora_atualizacao', 'previsao_minutos_inatividade')
    list_display_icons = True
    ordering = ('-data_hora_atualizacao',)
    fieldsets = (
        ('Dados gerais', {'fields': ('tipo', 'motivo', 'sistema_ou_servico', 'data_hora_atualizacao', 'previsao_minutos_inatividade')}),
        (
            'Público da Manutenção Programada ',
            {
                'fields': (
                    'publico',
                    'campi',
                )
            },
        ),
    )

    def get_equipe_manutencao(self, obj):
        equipe = '</li><li>'.join([str(k.relacionamento) for k in obj.equipe_manutencao.all()])
        return mark_safe(f'<ul><li>{equipe}</li></ul>')

    get_equipe_manutencao.short_description = 'Equipe da Manutenção'

    def get_search_fields(self, request):
        if request.user.has_perm('comum.add_manutencaoprogramada'):
            return ('motivo',)
        return None

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('comum.add_manutencaoprogramada'):
            list_filter = (*list_filter, 'equipe_manutencao', 'data_hora_atualizacao')
        return list_filter

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.user.has_perm('comum.add_manutencaoprogramada'):
            list_display = (
                *list_display,
                'motivo',
                'data_hora_inicio_notificacao',
                'efetivos_minutos_inatividade',
                'get_equipe_manutencao',
                'usuario',
                'data_cadastro',
            )
        return list_display

    def get_queryset(self, request, manager=None, *args, **kwargs):
        if request.user.has_perm('comum.add_manutencaoprogramada'):
            return super().get_queryset(request, manager, *args, **kwargs)
        else:
            return ManutencaoProgramada.proximas_atualizacoes()

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        dados_extras = (('Dados Extras', {'fields': ('data_hora_inicio_notificacao', 'equipe_manutencao', 'efetivos_minutos_inatividade')}),)
        if request.user.has_perm('comum.add_manutencaoprogramada'):
            return fieldsets + dados_extras
        return fieldsets


admin.site.register(ManutencaoProgramada, ManutencaoProgramadaAdmin)


class InlineSemAddButton(StackedInline):
    @property
    def media(self):
        _media = super().media
        if 'admin/js/inlines.js' in _media._js:
            _media._js.remove('admin/js/inlines.js')
        if 'admin/js/inlines.min.js' in _media._js:
            _media._js.remove('admin/js/inlines.min.js')
        _media._js.append('/static/comum/js/inlines_sem_add_button.js')
        return _media


class FuncaoCodigoAdmin(ModelAdminPlus):
    list_display = ('id', 'nome')
    ordering = ('id',)


admin.site.register(FuncaoCodigo, FuncaoCodigoAdmin)


class CategoriaNotificacaoAdmin(ModelAdminPlus):
    form = CategoriaNotificacaoForm
    list_display = ('assunto', 'get_notificacoes', 'ativa', 'get_opcoes')
    list_display_icons = True
    list_filter = ('ativa',)
    search_fields = ('assunto',)
    ordering = ('assunto',)

    def get_notificacoes(self, obj):
        return NotificacaoSistema.objects.filter(categoria=obj).count()

    get_notificacoes.short_description = 'Notificações'

    def get_opcoes(self, obj):
        opcoes = '<ul class="action-bar">'
        if obj.ativa:
            opcoes += f'<li><a href="/comum/desativar_categoria_notificacao/{obj.pk}/" class="btn danger">Desativar</a></li>'
        else:
            opcoes += f'<li><a href="/comum/ativar_categoria_notificacao/{obj.pk}/" class="btn success">Ativar</a></li>'
        opcoes += '</ul>'
        return mark_safe(opcoes)

    get_opcoes.short_description = 'Opções'


admin.site.register(CategoriaNotificacao, CategoriaNotificacaoAdmin)


class RegistroNotificacaoAdmin(ModelAdminPlus):
    list_display = ('get_assunto_display', 'lida', 'data', 'get_opcoes')
    list_display_icons = True
    list_filter = ('lida', 'notificacao__categoria__assunto')
    search_fields = ('notificacao__categoria__assunto',)
    date_hierarchy = 'data'

    actions = ['marcar_como_lida', 'marcar_como_nao_lida', 'remover_em_lote']
    actions_on_top = True
    actions_on_bottom = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(vinculo=request.user.get_vinculo())

    def has_change_permission(self, request, obj=None):
        return False

    def has_action_permission(self, request, obj=None):
        return obj.pode_ler() and obj.pode_excluir()

    def get_assunto_display(self, obj):
        return obj.notificacao.categoria.assunto

    get_assunto_display.allow_tags = True
    get_assunto_display.short_description = 'Opções'

    def get_opcoes(self, obj):
        opcoes = '<ul class="action-bar">'
        if obj.lida:
            opcoes += f'<li><a href="#" class="btn" data-notificacao-leitura="{obj.pk}" data-admin="true" data-lida="{obj.lida}">Marcar como não lida</a></li>'
        elif obj.pode_ler():
            opcoes += (
                f'<li><a href="#" class="btn" data-notificacao-leitura="{obj.pk}" data-admin="true" data-lida="{obj.lida}">Marcar como lida</a></li>'
            )
        if obj.pode_excluir():
            opcoes += f'<li><a href="/comum/remover_notificacao/{obj.pk}/" class="btn danger">Remover</a></li>'
        opcoes += '</ul>'
        return mark_safe(opcoes)

    get_opcoes.short_description = 'Opções'

    def marcar_como_lida(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/marcar_como_lida_em_lote/?ids={}'.format(','.join(selected)))

    marcar_como_lida.short_description = 'Marcar como lida'

    def marcar_como_nao_lida(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/marcar_como_nao_lida_em_lote/?ids={}'.format(','.join(selected)))

    marcar_como_nao_lida.short_description = 'Marcar como não lida'

    def remover_em_lote(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/remover_notificacoes_em_lote/?ids={}'.format(','.join(selected)))

    remover_em_lote.short_description = 'Remover'


admin.site.register(RegistroNotificacao, RegistroNotificacaoAdmin)


class PreferenciaNotificacaoAdmin(ModelAdminPlus):
    list_display = ('get_categoria', 'data', 'via_suap', 'via_email', 'get_opcoes')
    list_filter = ('via_suap', 'via_email')
    search_fields = ('categoria__assunto',)
    date_hierarchy = 'data'
    list_display_icons = True

    actions = ['ativar_via_suap', 'desativar_via_suap', 'ativar_via_email', 'desativar_via_email']
    actions_on_top = True
    actions_on_bottom = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_categoria(self, obj):
        if self.request.user.has_perm('comum.change_categorianotificacao'):
            return mark_safe(f'<a href="/admin/comum/categorianotificacao/{obj.categoria.id}/">{obj.categoria}</a>')
        else:
            return obj.categoria

    get_categoria.short_description = 'Categoria'
    get_categoria.admin_order_field = 'categoria__assunto'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(vinculo=request.user.get_vinculo(), categoria__ativa=True)

    def get_action_bar(self, request: HttpRequest) -> list[dict]:
        items = super().get_action_bar(request)
        # Sem linha gravada vale o default do model (os dois canais ligados), e é desse estado que
        # `atualizar_preferencia_padrao` alterna: a barra anuncia a mesma ação que o clique faz (#17390).
        preferencia = Preferencia.objects.filter(usuario=request.user).first() or Preferencia(usuario=request.user)
        if preferencia.via_suap:
            items.append(
                {
                    'url': '/comum/atualizar_preferencia_padrao/?envio=suap',
                    'label': mark_safe('<span class="fa fa-bell-slash"></span> Desativar Envio Padrão via SUAP'),
                    'css_class': 'danger no-confirm',
                }
            )
        else:
            items.append(
                {
                    'url': '/comum/atualizar_preferencia_padrao/?envio=suap',
                    'label': mark_safe('<span class="fa fa-bell"></span> Ativar Envio Padrão via SUAP'),
                    'css_class': 'success',
                }
            )
        if preferencia.via_email:
            items.append(
                {
                    'url': '/comum/atualizar_preferencia_padrao/?envio=email',
                    'label': mark_safe('<span class="fa fa-bell-slash"></span> Desativar Envio Padrão via E-mail'),
                    'css_class': 'danger no-confirm',
                }
            )
        else:
            items.append(
                {
                    'url': '/comum/atualizar_preferencia_padrao/?envio=email',
                    'label': mark_safe('<span class="fa fa-bell"></span> Ativar Envio Padrão via E-mail'),
                    'css_class': 'success',
                }
            )

        return items

    def get_opcoes(self, obj):
        opcoes = '<ul class="action-bar">'
        if obj.pode_desabilitar():
            if obj.via_suap:
                opcoes += f'<li><a href="/comum/atualizar_via_suap/{obj.pk}/" class="btn danger"><span class="fa fa-bell-slash" aria-hidden="true"></span> Desativar Envio via SUAP</a></li>'
            else:
                opcoes += f'<li><a href="/comum/atualizar_via_suap/{obj.pk}/" class="btn success"><span class="fa fa-bell" aria-hidden="true"></span> Ativar Envio via SUAP</a></li>'
            if obj.via_email:
                opcoes += f'<li><a href="/comum/atualizar_via_email/{obj.pk}/" class="btn danger"><span class="fa fa-bell-slash" aria-hidden="true"></span> Desativar Envio via E-mail</a></li>'
            else:
                opcoes += f'<li><a href="/comum/atualizar_via_email/{obj.pk}/" class="btn success"><span class="fa fa-bell" aria-hidden="true"></span> Ativar Envio via E-mail</a></li>'
        opcoes += '</ul>'
        return mark_safe(opcoes)

    get_opcoes.short_description = 'Opções'

    def ativar_via_suap(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/ativar_via_suap_em_lote/?ids={}'.format(','.join(selected)))

    ativar_via_suap.short_description = 'Ativar Envio via SUAP'

    def desativar_via_suap(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/desativar_via_suap_em_lote/?ids={}'.format(','.join(selected)))

    desativar_via_suap.short_description = 'Desativar Envio via SUAP'

    def ativar_via_email(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/ativar_via_email_em_lote/?ids={}'.format(','.join(selected)))

    ativar_via_email.short_description = 'Ativar Envio via E-mail'

    def desativar_via_email(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/comum/desativar_via_email_em_lote/?ids={}'.format(','.join(selected)))

    desativar_via_email.short_description = 'Desativar Envio via E-mail'


admin.site.register(PreferenciaNotificacao, PreferenciaNotificacaoAdmin)


class EmailBlocklistAdmin(ModelAdminPlus):
    list_display = ('email',)
    search_fields = ('email',)


admin.site.register(EmailBlockList, EmailBlocklistAdmin)


class JustificativaUsuarioExternoAdmin(ModelAdminPlus):
    list_display = (
        'justificativa',
        'ativo',
    )
    search_fields = ('justificativa',)


admin.site.register(JustificativaUsuarioExterno, JustificativaUsuarioExternoAdmin)


class APIExternaAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo', 'get_opcoes')
    search_fields = (
        'nome',
        'endpoint',
    )
    list_display_icons = True
    form = APIExternaForm

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        new_urls = [
            path('<str:obj_pk>/testar-conectividade/', self.testar_conectividade, name='comum_apiexterna_testar_conectividade'),
            path('<str:obj_pk>/alternar-atividade/', self.alternar_atividade, name='comum_apiexterna_alternar_atividade'),
            path('<str:obj_pk>/testar-consulta-cpf/', self.testar_consulta_cpf, name='comum_apiexterna_testar_consulta_cpf'),
        ]
        return new_urls + super().get_urls()

    @staticmethod
    def _suporta_consulta_por_cpf(obj):
        # Convenção: qualquer serviço (de qualquer API externa) que queira aparecer na
        # ferramenta de teste por CPF do admin deve implementar `consultar_por_cpf(cpf, verbosity=)`.
        try:
            return hasattr(obj.get_service(), 'consultar_por_cpf')
        except Exception:
            return False

    def get_opcoes(self, obj):
        botoes = (
            f'<li><a href="/admin/comum/apiexterna/{obj.pk:d}/testar-conectividade/" class="popup btn success">'
            f'<span class="fas fa-spinner" aria-hidden="true"></span>Testar Conectividade</a></li>'
            f'<li><a href="/admin/comum/apiexterna/{obj.pk:d}/alternar-atividade/" class="btn">'
            f'<span class="fas fa-toggle-on" aria-hidden="true"></span>Alternar Atividade</a></li>'
        )
        if self._suporta_consulta_por_cpf(obj):
            botoes += (
                f'<li><a href="/admin/comum/apiexterna/{obj.pk:d}/testar-consulta-cpf/" class="popup btn primary">'
                f'<span class="fas fa-search" aria-hidden="true"></span>Testar Consulta por CPF</a></li>'
            )
        return mark_safe(f'<ul class="action-bar">{botoes}</ul>')

    get_opcoes.short_description = 'Opções'

    def alternar_atividade(self, request, obj_pk):
        if not request.user.has_group_cached('Coordenador de Sistemas'):
            return httprr('/admin/comum/apiexterna/', 'Operação não autorizada.', 'error')

        api = APIExterna.objects.get(pk=obj_pk)
        api.ativo = not api.ativo
        api.save()

        return httprr('/admin/comum/apiexterna/', 'Procedimento realizado com sucesso.', 'success')

    def testar_conectividade(self, request, obj_pk):
        if not request.user.has_group_cached('Coordenador de Sistemas'):
            return httprr('/admin/comum/apiexterna/', 'Operação não autorizada.', 'error')

        api_externa = APIExterna.objects.get(pk=obj_pk)

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        logger_alvo = logging.getLogger()
        logger_alvo.addHandler(handler)
        try:
            token = api_externa.get_service().estah_acessivel(verbosity=True)
            if token:
                self.message_user(request, 'Conexão com a API realizada com sucesso.', level=messages.SUCCESS)
            else:
                self.message_user(request, 'Conexão com a API não foi estabelecida.', level=messages.ERROR)
        except Exception:
            if settings.DEBUG:
                raise
            self.message_user(request, 'Error na conexão/autenticação com a API.', level=messages.ERROR)
        finally:
            # 5. Removemos o handler para não vazar logs para chamadas futuras
            logger_alvo.removeHandler(handler)
        logs_capturados = log_stream.getvalue()
        log_stream.close()
        return render('testar_conectividade.html', {'api_externa': api_externa, 'logs': logs_capturados}, request=request)

    testar_conectividade.short_description = 'Testar conectividade'

    def testar_consulta_cpf(self, request, obj_pk):
        if not request.user.has_group_cached('Coordenador de Sistemas'):
            return httprr('/admin/comum/apiexterna/', 'Operação não autorizada.', 'error')

        api_externa = APIExterna.objects.get(pk=obj_pk)
        cpf = request.GET.get('cpf')
        resultado = None
        erro = None
        resposta_bruta = None

        if cpf:
            try:
                servico = api_externa.get_service()
                if not hasattr(servico, 'consultar_por_cpf'):
                    erro = 'Este serviço não implementa consulta por CPF.'
                else:
                    resultado = servico.consultar_por_cpf(cpf)
            except Exception as e:
                # Ferramenta de diagnóstico: sempre mostra o erro bruto na própria página, nunca
                # estoura para a página de erro do Django mesmo com DEBUG=True. `response_status`/
                # `response_body`, quando presentes, são anexados pelo próprio serviço (ver
                # saude.services.rnvacina.ApiRNMaisVacinaService.consultar_imunizacoes).
                erro = str(e)
                if hasattr(e, 'response_body'):
                    resposta_bruta = f'HTTP {getattr(e, "response_status", "?")}\n{e.response_body}'

        return render(
            'testar_consulta_cpf.html',
            {
                'api_externa': api_externa,
                'cpf': cpf,
                'resultado': resultado,
                'erro': erro,
                'resposta_bruta': resposta_bruta,
            },
            request=request,
        )

    testar_consulta_cpf.short_description = 'Testar consulta por CPF'


admin.site.register(APIExterna, APIExternaAdmin)


class TipoArquivoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('nome', 'extensoes', 'eh_video')
    search_fields = ('nome', 'extensoes')


admin.site.register(TipoArquivo, TipoArquivoAdmin)


@admin.register(PessoaTelefone)
class PessoaTelefoneAdmin(ModelAdminPlus):
    list_display = ('pessoa', 'numero', 'ramal', 'observacao')
    search_fields = ('pessoa__nome', 'numero')
    list_display_icons = True
    actions = ('deletar',)

    def deletar(self, request, queryset):
        try:
            if request.user.is_superuser:
                queryset.delete()
                messages.success(request, 'Ação realizada com sucesso.')
            else:
                raise PermissionError('Você não pode executar essa operação.')
        except Exception as ex:
            messages.error(request, ex)

    deletar.short_description = 'Apagar Registros'


@admin.register(ReuniaoOrgaoColegiado)
class ReuniaoOrgaoColegiadoAdmin(ModelAdminPlus):
    list_display = ('colegiado_display_html', 'titulo', 'data_inicio', 'data_fim', 'hora_inicio', 'hora_fim')
    search_fields = ('titulo', 'descricao', 'local')
    list_display_icons = True
    form = ReuniaoOrgaoColegiadoForm
    date_hierarchy = 'data_inicio'

    def colegiado_display_html(self, reuniao):
        reuniao_view = ReuniaoOrgaoColegiadoView(reuniao)
        return reuniao_view.get_colegiado_display_html()

    colegiado_display_html.short_description = 'Colegiado'


@admin.register(SenhaExposta)
class SenhaExpostaAdmin(ModelAdminPlus):
    search_fields = ('senha',)
    list_display_icons = True
    date_hierarchy = 'data_exposicao'

    def get_list_display(self, request: HttpRequest) -> list[str]:
        list_display = ['show_list_display_icons', 'email', 'senha', 'formato_senha', 'data_exposicao']
        if _pode_consultar_senhas_expostas(request.user):
            list_display.insert(1, 'usuario')
        return list_display

    def get_list_filter(self, request: HttpRequest) -> list[str]:
        list_filter = ['formato_senha']
        if _pode_consultar_senhas_expostas(request.user):
            list_filter.append('usuario')
        return list_filter

    def get_queryset(self, request: HttpRequest) -> QuerySet[SenhaExposta]:
        qs = super().get_queryset(request)
        if not _pode_consultar_senhas_expostas(request.user):
            qs = qs.filter(usuario=request.user)
        return qs

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
