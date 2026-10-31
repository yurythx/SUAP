import datetime
from typing import Any

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from comum.forms import SetorTelefoneForm
from comum.models import Configuracao, PessoaEndereco, PessoaTelefone, SetorTelefone, Vinculo
from comum.types import PessoaFisicaCadastro, ServidorCadastro
from djtools import forms
from djtools.choices import DiaSemanaChoices, Meses
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, get_uo_setor_listfilter
from djtools.forms.widgets import AutocompleteWidget
from djtools.templatetags.filters import format_user, in_group
from djtools.templatetags.filters.utils import status
from djtools.templatetags.tags import icon
from djtools.utils import get_datetime_now, httprr, sync_ldap_user
from djtools.utils.response import solicitar_autenticacao_2fa
from rh.enums import Nacionalidade
from rh.forms import (
    AcaoSaudeForm,
    AgendaAtendimentoHorarioForm,
    AgendarAtendimentoForm,
    AreaVinculacaoForm,
    AvaliadorExternoForm,
    BancoForm,
    CargoEmpregoForm,
    CronogramaFolhaForm,
    DataConsultaBloqueadaForm,
    ExcecaoDadoForm,
    FuncaoForm,
    GetServidorFuncaoHistoricoForm,
    GetServidorFuncaoSiapeHistoricoForm,
    InstituicaoForm,
    JornadaTrabalhoPCAForm,
    PCAForm,
    PessoaEnderecoForm,
    PessoaExternaForm,
    PessoaFisicaForm,
    PessoaJuridicaContatoForm,
    PessoaJuridicaForm,
    PosicionamentoPCAForm,
    ProcessoCargaHorariaReduzidaRHForm,
    QuantitativoCargoClassePorCampusForm,
    RegimeJuridicoPCAForm,
    ServidorAfastamentoSiapeForm,
    ServidorForm,
    ServidorReativacaoPermanenteForm,
    ServidorReativacaoTemporariaForm,
    ServidorSetorHistoricoForm,
    SetorAddForm,
    SetorForm,
    SetorJornadaHistoricoFormFactory,
    SolicitacaoAlteracaoFotoForm,
)
from rh.importador_ws import ImportadorWs
from rh.models import (
    PCA,
    AcaoSaude,
    AfastamentoSiape,
    AfastamentoSiapeEfetivoExercicio,
    AgendaAtendimentoHorario,
    AlertaGestaoPessoa,
    AlertaGestaoPessoaVisualizacao,
    AreaConhecimento,
    AreaVinculacao,
    Atividade,
    Avaliador,
    Banco,
    CampoExcecao,
    CargaHorariaReduzida,
    CargoClasse,
    CargoEmprego,
    CargoEmpregoArea,
    CargoEmpregoPendente,
    cargo_cadastrado_para_pendencia,
    CronogramaFolha,
    DataConsultaBloqueada,
    DiplomaLegal,
    ExcecaoDado,
    FormaProvimentoVacancia,
    Funcao,
    GrupoCargoEmprego,
    GrupoOcorrencia,
    HorarioAgendado,
    IndicadoresPublicos,
    Instituicao,
    JornadaTrabalho,
    JornadaTrabalhoPCA,
    ModalidadePGD,
    NivelEscolaridade,
    Ocorrencia,
    PadraoVencimento,
    Papel,
    Pessoa,
    PessoaExterna,
    PessoaFisica,
    PessoaInfoComplementar,
    PessoaJuridica,
    PessoaJuridicaContato,
    PosicionamentoPCA,
    QuantitativoCargoClassePorCampus,
    RegimeJuridico,
    RegimeJuridicoPCA,
    Servidor,
    ServidorAfastamento,
    ServidorFuncaoHistorico,
    ServidorOcorrencia,
    ServidorReativacaoPermanente,
    ServidorReativacaoTemporaria,
    ServidorSetorHistorico,
    ServidorSetorLotacaoHistorico,
    Setor,
    SetorJornadaHistorico,
    Situacao,
    SolicitacaoAlteracaoFoto,
    TipoUnidadeOrganizacional,
    Titulacao,
    UnidadeOrganizacional,
)
from rh.utils import estah_no_pgd_hoje_pgd1_pgd2
from suap import nomenclatura


###############
# Atividade
###############


class AtividadeAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo')


admin.site.register(Atividade, AtividadeAdmin)


###############
# Bancos
###############


class BancoAdmin(ModelAdminPlus):
    form = BancoForm
    list_display = ('codigo', 'nome', 'sigla', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo', 'sigla')


admin.site.register(Banco, BancoAdmin)


###############
# Cargo Emprego
###############


class CargoEmpregoUtilizadosFilter(admin.SimpleListFilter):
    title = 'Cargo emprego usado no sistema'
    parameter_name = 'usado_no_sistema'

    SIM = 'SIM'
    NAO = 'NAO'

    def lookups(self, request, model_admin):
        return ((self.SIM, 'Sim'), (self.NAO, 'Não'))

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == self.SIM:
                return queryset.filter(servidor__isnull=False).distinct()
            elif self.value() == self.NAO:
                return queryset.filter(servidor__isnull=True).distinct()


class CargoEmpregoAreaInline(admin.StackedInline):
    model = CargoEmpregoArea
    fields = ('descricao',)
    extra = 1


class CargoEmpregoAdmin(ModelAdminPlus):
    list_display = ('nome', 'nome_amigavel', 'codigo', 'grupo_cargo_emprego', 'cargo_suap', 'cargo_siape', 'excluido')
    list_display_icons = True
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['cargo_suap', 'cargo_siape', 'excluido', CargoEmpregoUtilizadosFilter]
    search_fields = ('nome', 'codigo')
    inlines = [CargoEmpregoAreaInline]
    form = CargoEmpregoForm

    def get_readonly_fields(self, request, obj=None):
        """Protege os campos que a extração do SIAPE sobrescreve.

        Em um cargo que pertence ao SIAPE, só os campos exclusivos do SUAP são editáveis: os
        demais seriam desfeitos na importação seguinte. Cargos cadastrados no SUAP ficam
        totalmente editáveis, inclusive o código, que é a chave de reconciliação.
        """
        if obj and not obj.cargo_suap:
            # grupo_cargo_emprego entra aqui porque o importador o deriva dos 3 primeiros
            # dígitos do código: editá-lo num cargo do SIAPE não teria efeito nenhum.
            return ('codigo', 'nome', 'sigla_escolaridade', 'grupo_cargo_emprego', 'excluido')
        return ()


admin.site.register(CargoEmprego, CargoEmpregoAdmin)


##############################
# Cargo Emprego Pendente
##############################


class CargoEmpregoPendenteResolvidaFilter(admin.SimpleListFilter):
    title = 'Situação'
    parameter_name = 'resolvida'

    SIM = 'SIM'
    NAO = 'NAO'

    def lookups(self, request, model_admin):
        return ((self.NAO, 'Pendente de cadastro'), (self.SIM, 'Cargo já cadastrado'))

    def queryset(self, request, queryset):
        if self.value() == self.SIM:
            return queryset.resolvidas()
        if self.value() == self.NAO:
            return queryset.nao_resolvidas()
        return queryset


class CargoEmpregoPendenteAdmin(ModelAdminPlus):
    """Códigos de cargo que vieram no arquivo de servidores sem cargo correspondente no SUAP.

    Lista somente leitura: as linhas são produzidas pelo importador. Cadastrando o cargo com o
    mesmo código, a extração seguinte religa os servidores automaticamente.
    """

    list_display = (
        'codigo',
        'grupo_codigo',
        'get_grupo_cargo_emprego',
        'qtd_servidores',
        'get_resolvida',
        'primeira_ocorrencia',
        'ultima_ocorrencia',
    )
    list_display_icons = True
    list_filter = [CargoEmpregoPendenteResolvidaFilter]
    search_fields = ('codigo', 'grupo_codigo')
    ordering = ('-ultima_ocorrencia', 'codigo')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        """Anota resolução e nome do grupo para a listagem não consultar por linha."""
        return (
            super()
            .get_queryset(request)
            .annotate(
                _resolvida=cargo_cadastrado_para_pendencia(),
                _grupo_nome=Subquery(GrupoCargoEmprego.objects.filter(codigo=OuterRef('grupo_codigo')).values('nome')[:1]),
            )
        )

    def get_grupo_cargo_emprego(self, obj):
        return obj._grupo_nome or 'Grupo não cadastrado'

    get_grupo_cargo_emprego.short_description = 'Grupo de Cargo Emprego'
    get_grupo_cargo_emprego.admin_order_field = '_grupo_nome'

    def get_resolvida(self, obj):
        return obj._resolvida

    get_resolvida.short_description = 'Cargo cadastrado'
    get_resolvida.boolean = True
    get_resolvida.admin_order_field = '_resolvida'


admin.site.register(CargoEmpregoPendente, CargoEmpregoPendenteAdmin)


###############
# Cargo Classe
###############


class CargoClasseAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo')


admin.site.register(CargoClasse, CargoClasseAdmin)

###############
# Cargo Classe por campus - Quadro de referência
###############


class QuantitativoCargoClassePorCampusAdmin(ModelAdminPlus):
    list_display = ('cargo_classe', 'uo', 'quantidade')
    list_filter = ['cargo_classe', 'uo']

    form = QuantitativoCargoClassePorCampusForm


admin.site.register(QuantitativoCargoClassePorCampus, QuantitativoCargoClassePorCampusAdmin)


###############
# Diploma Legal
###############


class DiplomaLegalAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'sigla', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo', 'sigla')


admin.site.register(DiplomaLegal, DiplomaLegalAdmin)


###############
# Titulacao
###############


class TitulacaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'titulo_masculino', 'titulo_feminino')
    ordering = ('nome', 'codigo')
    search_fields = ('nome', 'codigo')


admin.site.register(Titulacao, TitulacaoAdmin)


###############
# Funcao
###############


class FuncaoCHSemanalFilter(admin.SimpleListFilter):
    title = 'Carga Horária Semanal'
    parameter_name = 'ch_semanal'

    def lookups(self, request, model_admin):
        return [
            ['40_horas', '40 Horas'],
            ['30_horas', '30 Horas'],
            ['20_horas', '20 Horas'],
            ['definida', 'Definida'],
            ['nao_definida', 'Não Definida'],
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            if value == 'definida':
                try:
                    funcao_ids = [_.id for _ in queryset if _.ch_semanal is not None]
                    return queryset.filter(id__in=funcao_ids)
                except Exception:
                    return queryset.none()
            elif value == 'nao_definida':
                try:
                    funcao_ids = [_.id for _ in queryset if _.ch_semanal is None]
                    return queryset.filter(id__in=funcao_ids)
                except Exception:
                    return queryset.none()
            else:
                try:
                    ch = int(value.split('_')[0])
                    funcao_ids = [_.id for _ in queryset if _.ch_semanal and _.ch_semanal == ch]
                    return queryset.filter(id__in=funcao_ids)
                except Exception:
                    return queryset.none()
        return queryset


class FuncaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'funcao_suap', 'eh_funcao_chefia', 'ch_semanal', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['funcao_siape', 'funcao_suap', 'eh_funcao_chefia', FuncaoCHSemanalFilter, 'excluido']
    search_fields = ('nome', 'codigo')
    form = FuncaoForm


admin.site.register(Funcao, FuncaoAdmin)


###############
# Servidor Funcao
###############
class DataFimFuncaoFilter(admin.SimpleListFilter):
    title = 'Data Fim de Função'
    parameter_name = 'com_data_fim'

    def lookups(self, request, model_admin):
        return [[True, 'Com data final'], [False, 'Sem data final']]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(data_fim_funcao__isnull=self.value() == 'False')
        return queryset


class ServidorFuncaoHistoricoAdmin(ModelAdminPlus):
    list_display = (
        'servidor',
        'data_inicio_funcao',
        'data_fim_funcao',
        'funcao',
        'nivel',
        'atividade',
        'setor',
        'setor_suap',
        'atualiza_pelo_extrator',
    )
    ordering = ('-data_inicio_funcao',)
    list_filter = (
        *get_uo_setor_listfilter('setor_suap', 'Setor SUAP', f'{nomenclatura.campus} SUAP'),
        'funcao',
        'atividade',
        *get_uo_setor_listfilter('setor', 'Setor SIAPE', f'{nomenclatura.campus} SIAPE', setor_suap=False),
        DataFimFuncaoFilter,
    )
    search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula', 'funcao__codigo', 'funcao__nome')
    list_display_icons = True
    date_hierarchy = 'data_inicio_funcao'

    def get_queryset(self, request):
        if request.user.is_superuser:
            queryset = super().get_queryset(request)
        elif request.user.has_perm('rh.eh_rh_sistemico') or in_group(request.user, 'Auditor'):
            queryset = super().get_queryset(request).exclude(funcao__codigo=Funcao.CODIGO_ESTAGIARIO)
        else:
            vinculo = request.user.get_vinculo()
            if vinculo.eh_funcionario():
                uo_siape = UnidadeOrganizacional.objects.filter(equivalente=vinculo.setor.uo, setor__excluido=False)
                queryset = super().get_queryset(request).exclude(funcao__codigo=Funcao.CODIGO_ESTAGIARIO)
                queryset = (queryset.filter(setor_suap__uo=vinculo.setor.uo) | queryset.filter(setor__uo__in=uo_siape)).distinct()
            else:
                queryset = ServidorFuncaoHistorico.objects.none()
        return queryset

    def get_form(self, request, obj=None, **kwargs):
        if obj and not obj.funcao.funcao_suap:
            return GetServidorFuncaoSiapeHistoricoForm(request)
        return GetServidorFuncaoHistoricoForm(request)


admin.site.register(ServidorFuncaoHistorico, ServidorFuncaoHistoricoAdmin)


###############
# Grupo de Cargo Emprego
###############


class GrupoCargoEmpregoAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla', 'codigo', 'categoria', 'excluido')
    ordering = ('excluido', 'nome', 'sigla', 'codigo')
    list_filter = ['categoria', 'excluido']
    search_fields = ('nome', 'codigo', 'sigla')

    def get_readonly_fields(self, request, obj=None):
        """Impede a alteração do código de um grupo já existente.

        O importador deriva o grupo de um cargo pelos 3 primeiros dígitos do código do cargo
        (rh/importador.py) por indexação direta no cache. Um código de grupo alterado ou removido
        levanta KeyError e aborta a importação inteira da tabela de cargos.
        """
        if obj:
            return ('codigo',)
        return ()


admin.site.register(GrupoCargoEmprego, GrupoCargoEmpregoAdmin)


###############
# Grupo de Ocorrencia
###############


class GrupoOcorrenciaAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo')


admin.site.register(GrupoOcorrencia, GrupoOcorrenciaAdmin)


###############
# Jornada de Trabalho
###############


class JornadaTrabalhoAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo')


admin.site.register(JornadaTrabalho, JornadaTrabalhoAdmin)


class SetorJornadaHistoricoAdmin(ModelAdminPlus):
    list_display = ('setor_link_historico_jornadas', 'jornada_trabalho', 'data_inicio_da_jornada', 'data_fim_da_jornada_formatada')
    search_fields = (
        'setor__nome',
        'setor__sigla',
        'jornada_trabalho__codigo',
        'jornada_trabalho__nome',
        'data_inicio_da_jornada',
        'data_fim_da_jornada',
    )
    list_filter = ('jornada_trabalho',)
    list_display_icons = True

    def setor_link_historico_jornadas(self, obj):
        return mark_safe(
            '<a href="/rh/setor_jornada_historico/{}/" title="{}">{}</a>'.format(
                obj.setor.id, f'Detalhar Jornada de Trabalho de {obj.setor}', obj.setor
            )
        )

    setor_link_historico_jornadas.short_description = 'Setor'
    setor_link_historico_jornadas.admin_order_field = 'setor'

    def data_fim_da_jornada_formatada(self, obj):
        if obj.data_fim_da_jornada:
            return obj.data_fim_da_jornada
        else:
            return '-'

    data_fim_da_jornada_formatada.short_description = 'Data Final da Jornada'
    data_fim_da_jornada_formatada.admin_order_field = 'data_fim_da_jornada'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        url_base = '/rh/setor_jornada_historico_pendencias/'
        items.append({'url': url_base, 'label': 'Setores com pendências'})
        return items

    def get_queryset(self, request):
        if request.user.has_perm('rh.eh_rh_sistemico'):
            return SetorJornadaHistorico.objects.all()
        else:
            #
            # exibe apenas os históricos dos setores pertencentes ao mesmo campus do usuário logado
            #
            vinculo = request.user.get_vinculo()
            if vinculo.eh_funcionario():
                return SetorJornadaHistorico.objects.filter(setor__uo__sigla=vinculo.setor.uo.sigla)
            else:
                return []  # usuário logado tem permissão para gerenciar jornadas de trabalho de setores mas não é funcionário!!!!!

    def get_form(self, request, obj=None, **kwargs):
        return SetorJornadaHistoricoFormFactory(request)


admin.site.register(SetorJornadaHistorico, SetorJornadaHistoricoAdmin)


###############
# Nivel Escolaridade
###############


class NivelEscolaridadeAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo')


admin.site.register(NivelEscolaridade, NivelEscolaridadeAdmin)


###############
# Ocorrencia
###############


class OcorrenciaAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'grupo_ocorrencia', 'excluido')
    ordering = ('excluido', 'nome', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'codigo')


admin.site.register(Ocorrencia, OcorrenciaAdmin)


class PessoaAdmin(ModelAdminPlus):
    list_display_icons = True

    def has_add_permission(self, request):
        return request.user == request.user.is_superuser

    def cpf_ou_cnpj(self, obj):
        try:
            return obj.pessoafisica.cpf
        except Exception:
            return obj.pessoajuridica.cnpj

    cpf_ou_cnpj.short_description = 'CPF ou CNPJ'

    list_display = ['nome', 'cpf_ou_cnpj']
    search_fields = ['nome']


admin.site.register(Pessoa, PessoaAdmin)


class TelefoneInline(admin.StackedInline):
    model = PessoaTelefone
    fields = ('numero',)
    extra = 1


class ContatoInline(admin.StackedInline):
    form = PessoaJuridicaContatoForm
    model = PessoaJuridicaContato
    fields = ('descricao', 'telefone', 'email', 'via_form_suap')
    extra = 1


class PessoaEnderecoInline(admin.StackedInline):
    form = PessoaEnderecoForm
    model = PessoaEndereco
    fields = ('municipio', 'logradouro', 'numero', 'complemento', 'bairro', 'cep', 'via_form_suap')
    extra = 1


class PessoaFisicaAdmin(ModelAdminPlus):
    form = PessoaFisicaForm
    search_fields = ('nome', 'cpf')
    list_display = ('nome', 'documento_identificador', 'telefones')
    list_display_icons = True
    inlines = [TelefoneInline]

    def has_add_permission(self, request):
        return request.user.is_superuser

    def get_form(self, request, obj=None, **kwargs):
        if request.user.is_superuser:
            kwargs['fields'] = ('nome', 'sexo', 'cpf', 'passaporte', 'nascimento_data', 'nacionalidade', 'tem_digital_fraca')
        else:
            kwargs['fields'] = ('nome', 'sexo', 'cpf', 'passaporte', 'nascimento_data')
        return super().get_form(request, obj=obj, **kwargs)


admin.site.register(PessoaFisica, PessoaFisicaAdmin)


class PessoaJuridicaAdmin(ModelAdminPlus):
    fields = ('nome', 'nome_fantasia', 'cnpj', 'ramo_atividade', 'nome_representante_legal', 'email', 'inscricao_estadual', 'website')
    form = PessoaJuridicaForm
    inlines = [ContatoInline, PessoaEnderecoInline]
    list_display_icons = True
    list_display = (
        'cnpj',
        'get_nome',
        'nome_fantasia',
        'get_telefones',
        'natureza_juridica',
        'ramo_atividade',
        'possui_prestador_servico',
        'get_sistema_origem',
    )
    search_fields = ('nome', 'nome_fantasia', 'cnpj')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # email migrou p/ Vinculo.email_pessoal; grava no vínculo da PJ (criado no PessoaJuridica.save()).
        vinculo = obj.get_vinculo()
        if vinculo:
            vinculo.email_pessoal = form.cleaned_data.get('email') or ''
            vinculo.save(update_fields=['email_pessoal'])

    def get_nome(self, obj):
        return obj.nome

    get_nome.short_description = 'Razão Social'
    get_nome.admin_order_field = 'nome'

    def get_sistema_origem(self, obj: PessoaJuridica) -> str:
        v = obj.get_vinculo()
        return v.sistema_origem if v else ''

    get_sistema_origem.short_description = 'Sistema de Origem'

    def get_view_inlines(self, request):
        return ['get_telefones', 'get_enderecos']

    def get_telefones(self, obj):
        return ', '.join([str(contato) for contato in obj.pessoajuridicacontato_set.all()])

    get_telefones.short_description = 'Telefones'
    get_telefones.columns = ['descricao', 'telefone', 'email']

    def get_enderecos(self, obj):
        return obj.pessoaendereco_set.all()

    get_enderecos.short_description = 'Endereços'

    def possui_prestador_servico(self, obj):
        if obj.ocupacaoprestador_set.exists():
            return mark_safe('<span class="status status-success">Sim</span>')
        return mark_safe('<span class="status status-error">Não</span>')

    possui_prestador_servico.short_description = 'Possui Prestador de Serviço'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        if request.user.has_perm('rh.add_pessoajuridica'):
            items.append({'url': '/rh/importar_pessoajuridica/', 'label': 'Importar Pessoa Jurídica', 'css_class': 'primary'})
        return items


admin.site.register(PessoaJuridica, PessoaJuridicaAdmin)


###############
# Regime Juridico
###############


class RegimeJuridicoAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla', 'codigo_regime', 'excluido')
    ordering = ('excluido', 'nome', 'sigla', 'codigo_regime')
    list_filter = ['excluido']
    search_fields = ('nome', 'sigla', 'codigo_regime')


admin.site.register(RegimeJuridico, RegimeJuridicoAdmin)


###############
# Representante Legal
###############

# class RepresentanteLegalAdmin(admin.ModelAdmin):
# pass
# admin.site.register(RepresentanteLegal, RepresentanteLegalAdmin)

############
# Servidor #
############


class CategoriaListFilter(admin.SimpleListFilter):
    title = 'Categoria'
    parameter_name = 'categoria'
    DOCENTE = 'docente'
    TECNICO = 'tecnico_administrativo'
    ESTAGIARIO = 'estagiario'

    def lookups(self, request, model_admin):
        return [[self.DOCENTE, 'Docente'], [self.TECNICO, 'Técnico Administrativo'], [self.ESTAGIARIO, 'Estagiário']]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == self.DOCENTE:
                return queryset.filter(eh_docente=True)
            elif self.value() == self.TECNICO:
                return queryset.filter(eh_tecnico_administrativo=True)
            elif self.value() == self.ESTAGIARIO:
                return queryset.filter(situacao__codigo__in=Situacao.situacoes_siape_estagiarios())
        return queryset


class FuncaoListFilter(admin.SimpleListFilter):
    title = 'Função'
    parameter_name = 'funcao'

    def lookups(self, request, model_admin):
        return [[funcao.pk, str(funcao)] for funcao in Funcao.objects.usadas()]

    def queryset(self, request, queryset):
        hoje = datetime.date.today()
        if self.value():
            funcoes_hoje = ServidorFuncaoHistorico.objects.filter(
                servidor=OuterRef('pk'), funcao_id=self.value(), data_inicio_funcao__lte=hoje
            ).filter(Q(data_fim_funcao__gte=hoje) | Q(data_fim_funcao__isnull=True))
            queryset = queryset.filter(pk__in=Subquery(funcoes_hoje.values('servidor__pk')))
        return queryset.distinct()


class EstrangeiroListFilter(admin.SimpleListFilter):
    """Estrangeiro pela nacionalidade da pessoa física (a do servidor vem do SIAPE); ``filtro`` muda por modelo."""

    title = 'Estrangeiro'
    parameter_name = 'estrangeiro'
    filtro = Q(pessoa_fisica__nacionalidade=Nacionalidade.ESTRANGEIRO)

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> list[tuple[str, str]]:
        return [('sim', 'Sim'), ('nao', 'Não')]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == 'sim':
            return queryset.filter(self.filtro)
        if self.value() == 'nao':
            return queryset.exclude(self.filtro)
        return queryset


class ServidorAdmin(ModelAdminPlus):
    ordering = ['pessoa_fisica__nome']
    form = ServidorForm
    list_display_icons = True
    list_per_page = 20
    list_filter = (
        'setor__uo',
        'setor',
        'ativo',
        CategoriaListFilter,
        'cargo_emprego',
        'cargo_emprego_area',
        FuncaoListFilter,
        'situacao',
        EstrangeiroListFilter,
    )
    if 'edu' in settings.INSTALLED_APPS:
        list_filter += ('vinculos__professor__disciplina',)
    list_display = ('get_foto', 'get_info_principal', 'get_contatos', 'get_info_cargo', 'get_info_funcional')
    search_fields = (*tuple(Servidor.SEARCH_FIELDS), 'setor__sigla')
    export_to_xls = True

    dados_funcionais = (
        (
            'Dados funcionais',
            {
                'fields': (
                    'cargo_emprego',
                    'setor',
                    'setores_adicionais',
                    'data_inicio_servico_publico',
                    'data_posse_no_cargo',
                    'data_inicio_exercicio_no_cargo',
                    'data_inicio_exercicio_na_instituicao',
                ),
            },
        ),
    )
    dados_sistemicos = (('Para Terminal de Ponto', {'fields': ('tem_digital_fraca', 'senha_ponto')}),)
    fieldsets = (
        ('Dados pessoais', {'fields': ('nome_usual', 'nome_pai', 'nascimento_municipio', 'orcid', ('grupo_sanguineo', 'fator_rh'), 'foto')}),
        *dados_funcionais,
    )

    extra_fieldsets = (
        (
            'Dados pessoais',
            {
                'fields': (
                    'nome_usual',
                    'nome_social',
                    'nome_registro',
                    'nome_pai',
                    'nascimento_municipio',
                    'orcid',
                    ('grupo_sanguineo', 'fator_rh'),
                    'povo_indigena',
                    'foto',
                )
            },
        ),
        *dados_funcionais,
    )

    super_extra_fieldsets = (('SÓ SUPERUSUÁRIO', {'fields': ('setor_exercicio', 'ativo')}),)

    def get_fieldsets(self, request, obj=None):
        meus_fieldsets = self.fieldsets
        if request.user.has_perm('rh.add_servidor'):
            meus_fieldsets = (
                self.extra_fieldsets
                + self.dados_sistemicos
                + (('Para Gestão de Pessoas', {'fields': ('cpf', 'matricula', 'situacao', 'data_base_progressao')}),)
            )
        elif request.user.has_perm('rh.eh_rh_sistemico'):
            meus_fieldsets = self.extra_fieldsets + self.dados_sistemicos
        if request.user.is_superuser:
            meus_fieldsets += self.super_extra_fieldsets

        return meus_fieldsets

    def get_info_principal(self, obj):
        # mostrando afastamentos ou férias dos servidores na listagem
        mostrar_afast = obj.estah_afastado_ou_de_ferias_ateh(datetime.date.today())
        html_afast = ''
        if mostrar_afast:
            html_afast = f"""<div class="status-container d-flex flex-wrap">
                <span class="status status-default flex-grow-0"><span class="fas fa-info" aria-hidden="true"></span> {mostrar_afast}</span>
            </div>"""

        return mark_safe(f'<h3>{obj.__str__()}</h3>{html_afast}')

    get_info_principal.admin_order_field = 'pessoa_fisica__nome'
    get_info_principal.short_description = 'Nome/Matrícula'

    def save_model(self, request, obj, form, change):
        pessoa_fisica_dict: PessoaFisicaCadastro = {}
        available_fields = set(flatten_fieldsets(self.get_fieldsets(request, obj)))
        pessoa_fisica_fields = {
            'nome_registro',
            'nome_social',
            'nome_usual',
            'cpf',
            'nome_pai',
            'nascimento_municipio',
            'orcid',
            'tem_digital_fraca',
            'fator_rh',
            'grupo_sanguineo',
            'foto',
            'setores_adicionais',
            'povo_indigena',
        }.intersection(available_fields)
        for field in pessoa_fisica_fields:
            # tratamento especial para o campo foto
            if field == 'foto':
                cleaned_foto = form.cleaned_data.get(field)
                if cleaned_foto is False:
                    # usuário deseja limpar a foto
                    pessoa_fisica_dict[field] = None
                elif cleaned_foto is not None:
                    # usuário modificou a foto
                    pessoa_fisica_dict[field] = cleaned_foto
                # se for None, o usuário não modificou nada, não inclui no dict
                continue  # pula para o próximo campo
            # tratamento padrão para os outros campos
            pessoa_fisica_dict[field] = form.cleaned_data.get(field)

        # senha
        senha_ponto = form.cleaned_data.get('senha_ponto')
        if senha_ponto:
            pessoa_fisica_dict['senha_ponto'] = senha_ponto
        # servidor
        matricula = obj.matricula or form.cleaned_data.get('matricula', '')
        data_base_progressao = obj.data_base_progressao or form.cleaned_data.get('data_base_progressao', '')
        data_inicio_servico_publico = obj.data_inicio_servico_publico or form.cleaned_data.get('data_inicio_servico_publico', '')
        data_inicio_exercicio_no_cargo = obj.data_inicio_exercicio_no_cargo or form.cleaned_data.get('data_inicio_exercicio_no_cargo', '')
        data_posse_no_cargo = obj.data_posse_no_cargo or form.cleaned_data.get('data_posse_no_cargo', '')
        data_inicio_exercicio_na_instituicao = obj.data_inicio_exercicio_na_instituicao or form.cleaned_data.get(
            'data_inicio_exercicio_na_instituicao', ''
        )
        #
        dados: ServidorCadastro = {
            'pk': obj.pk,
            'matricula': matricula,
            'data_base_progressao': data_base_progressao,
            'pessoa_fisica': pessoa_fisica_dict,
            'ativo': obj.ativo,
            'data_inicio_servico_publico': data_inicio_servico_publico,
            'data_inicio_exercicio_no_cargo': data_inicio_exercicio_no_cargo,
            'data_posse_no_cargo': data_posse_no_cargo,
            'data_inicio_exercicio_na_instituicao': data_inicio_exercicio_na_instituicao,
        }
        servidor_fields = {'ativo', 'situacao', 'setor', 'setor_lotacao', 'setor_exercicio', 'cargo_emprego'}.intersection(available_fields)
        for field in servidor_fields:
            dados[field] = form.cleaned_data[field]
        Servidor.update_or_create(dados)

    def get_contatos(self, obj):
        show_telefones, show_email, show_pgd = '', '', ''
        if obj.pessoa_fisica.telefones_institucionais:
            show_telefones = '<dt>Telefones institucionais:</dt>'
            for telefone in obj.pessoa_fisica.telefones_institucionais.split(','):
                show_telefones += f'<dd>{telefone}</dd>'

        if obj.email_notificacao:
            show_email = f'<a href="mailto:{obj.email_notificacao}">{obj.email_notificacao}</a>'

        esta_em_pgd, adesao_pgd = estah_no_pgd_hoje_pgd1_pgd2(obj)
        if esta_em_pgd and adesao_pgd:
            show_pgd = f"""
                <dt>Contato PGD</dt>
                <dd>{adesao_pgd.get_contato_preferencia()}</dd>
            """
        out = f"""<dl class="definition-list">
            <dt>E-mail institucional</dt><dd>{show_email}</dd>
            {show_telefones}{show_pgd}
        </dl>"""
        return mark_safe(out)

    get_contatos.short_description = 'Contatos'

    def get_info_cargo(self, obj):
        out = ['<dl>']
        if obj.cargo_emprego:
            out.append(f'<dt>Cargo:</dt><dd>{obj.cargo_emprego.nome!s}</dd>')
        historico_funcao_servidor = obj.historico_funcao_ativa
        if historico_funcao_servidor.exists():
            for historico in historico_funcao_servidor.select_related('atividade'):
                out.append(f'<dt>{historico.funcao_display}:</dt>')
                out.append('<dd>{}</dd>'.format(historico.atividade.nome if historico.atividade_id else 'Sem Atividade'))
        if obj.situacao:
            if not obj.ativo:
                if obj.data_fim_servico_na_instituicao:
                    out.append(
                        '<dt>Situação:</dt><dd>{} <span class="false">(Excluído em {})</span></dd>'.format(
                            obj.situacao, obj.data_fim_servico_na_instituicao.strftime('%d/%m/%Y')
                        )
                    )
                else:
                    out.append(f'<dt>Situação:</dt><dd>{obj.situacao} <span class="false">(Excluído)</span></dd>')
            else:
                out.append(f'<dt>Situação:</dt><dd>{obj.situacao}</dd>')

        out.append('</dl>')
        return mark_safe(''.join(out))

    get_info_cargo.short_description = 'Cargo/Função/Situação'

    def get_info_funcional(self, obj):
        out = ['<dl>']

        if obj.setor_lotacao:
            out.append(f'<dt>SIAPE Lotação:</dt><dd>{obj.setor_lotacao.sigla}</dd>')
        if obj.setor_exercicio:
            out.append(f'<dt>SIAPE Exercício:</dt><dd>{obj.setor_exercicio.sigla}</dd>')
        if obj.setor:
            out.append(f'<dt>SUAP:</dt><dd>{obj.setor.sigla}</dd>')
        out.append('</dl>')
        return mark_safe(''.join(out))

    get_info_funcional.short_description = 'Setor'

    def get_foto(self, obj):
        img_src = obj.get_foto_75x100_url()
        return mark_safe(f'<div class="photo-circle"><img src="{img_src}" alt="{obj.__str__()}" /></div>')

    get_foto.short_description = 'Foto'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Matrícula',
            'Nome',
            'E-mail para Contato',
            'Cargo',
            'Funções',
            'Situação',
            f'{nomenclatura.campus} de Lotação',
            'Setor de Lotação',
            f'{nomenclatura.campus} Exercício',
            'Setor Exercício',
            f'{nomenclatura.campus} SUAP',
            'Setor SUAP',
            'Disciplina de Ingresso',
            'Ativo',
        ]
        if request.user.is_superuser:
            header.append('CPF')
        hoje = datetime.datetime.now()
        rows = [header]
        for idx, servidor in enumerate(processo.iterate(queryset), 1):
            historico_funcao_hoje = ''
            if servidor.historico_funcao(hoje, hoje):
                for historico in servidor.historico_funcao(hoje, hoje):
                    historico_funcao_hoje += (
                        f'{historico.funcao_display}:{historico.atividade.nome if historico.atividade_id else "Sem Atividade"} \n'
                    )
            row = [
                idx,
                servidor.matricula,
                servidor.pessoa_fisica.nome,
                servidor.email_institucional,
                servidor.cargo_emprego,
                historico_funcao_hoje,
                servidor.situacao,
                servidor.setor_lotacao.uo if servidor.setor_lotacao else '',
                servidor.setor_lotacao,
                servidor.setor_exercicio.uo if servidor.setor_exercicio else '',
                servidor.setor_exercicio,
                servidor.setor.uo if servidor.setor else '',
                servidor.setor,
                servidor.professor.disciplina if servidor.professor else '',
                'Sim' if servidor.ativo else 'Não',
            ]
            if request.user.is_superuser:
                row.append(servidor.pessoa_fisica.cpf)
            rows.append(row)
        return rows


admin.site.register(Servidor, ServidorAdmin)


###############
# Servidor Ocorrencia
###############


class ServidorOcorrenciaAdmin(ModelAdminPlus):
    list_display = ('servidor', 'ocorrencia', 'data', 'data_termino')
    ordering = ('servidor__pessoa_fisica__nome', 'data')
    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome', 'ocorrencia__nome', 'ocorrencia__grupo_ocorrencia__nome')


admin.site.register(ServidorOcorrencia, ServidorOcorrenciaAdmin)


class ReativacaoServidorAdminMixin:
    list_display_icons = True
    rotulo_solicitacao = ''
    rotulo_reativacao = ''
    select_related_fields = (
        'servidor',
        'servidor__pessoa_fisica',
        'servidor__setor',
    )
    prefetch_related_fields = (
        'servidor__vinculos',
        'servidor__vinculos__user',
    )
    servidor_select_related_fields = (
        'pessoa_fisica',
        'setor',
    )
    servidor_prefetch_related_fields = (
        'vinculos',
        'vinculos__user',
    )

    def _eh_rh_sistemico(self, request):
        return request.user.is_superuser or request.user.has_perm('rh.eh_rh_sistemico')

    def _eh_rh_campus(self, request):
        return request.user.has_perm('rh.eh_rh_campus') and not self._eh_rh_sistemico(request)

    def _get_campus_usuario(self, request):
        return request.user.get_relacionamento().setor.uo

    def _obj_no_escopo(self, request, obj):
        if self._eh_rh_sistemico(request):
            return True
        if self._eh_rh_campus(request) and obj.servidor.setor:
            return obj.servidor.setor.uo == self._get_campus_usuario(request)
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('servidor',)
        return ()

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = (
            super()
            .get_queryset(request, manager, *args, **kwargs)
            .select_related(*self.select_related_fields)
            .prefetch_related(*self.prefetch_related_fields)
        )
        if self._eh_rh_sistemico(request):
            return qs
        if self._eh_rh_campus(request):
            return qs.filter(servidor__setor__uo=self._get_campus_usuario(request))
        return qs.none()

    def get_object(self, request, object_id, from_field=None):
        filtro = {from_field or 'pk': object_id}
        return self.get_queryset(request).filter(**filtro).first()

    def _get_vinculo_servidor(self, servidor: Servidor) -> Vinculo | None:
        try:
            return servidor.vinculo
        except AttributeError, Vinculo.DoesNotExist:
            return servidor.get_vinculo()

    def _get_servidor_relacionado(self, servidor_id):
        return (
            Servidor.objects.select_related(*self.servidor_select_related_fields)
            .prefetch_related(*self.servidor_prefetch_related_fields)
            .get(pk=servidor_id)
        )

    def _get_user_servidor(self, servidor, vinculo=None):
        vinculo = vinculo or self._get_vinculo_servidor(servidor)
        if vinculo and vinculo.user_id:
            return vinculo.user
        return servidor.get_user()

    def has_change_permission(self, request, obj=None):
        permitido = super().has_change_permission(request, obj)
        if not permitido or obj is None:
            return permitido
        if self._eh_rh_sistemico(request):
            return True
        if self._eh_rh_campus(request) and self._obj_no_escopo(request, obj):
            return obj.situacao == obj.STATUS_SOLICITADA
        return False

    def get_action_bar(self, request):
        items = super().get_action_bar(request, True)
        if self.has_add_permission(request):
            label = self.rotulo_reativacao if self._eh_rh_sistemico(request) else self.rotulo_solicitacao
            items.append({'url': 'add/', 'label': label, 'css_class': 'success'})
        return items

    def add_view(self, request, form_url='', extra_context=None):
        title = self.rotulo_reativacao if self._eh_rh_sistemico(request) else self.rotulo_solicitacao
        more_context = {'title': title}
        more_context.update(extra_context or {})
        return super().add_view(request, form_url, more_context)


class ReativacaoTemporariaVigenciaFilter(admin.SimpleListFilter):
    title = 'Vigência'
    parameter_name = 'vigencia'

    def lookups(self, request, model_admin):
        return (
            ('vigentes', 'Vigentes'),
            ('encerradas', 'Encerradas'),
        )

    def queryset(self, request, queryset):
        hoje = get_datetime_now().date()
        valor = self.value()
        if valor == 'vigentes':
            return queryset.filter(situacao=ServidorReativacaoTemporaria.STATUS_AUTORIZADA, data_inicio__lte=hoje, data_fim__gte=hoje)
        if valor == 'encerradas':
            return queryset.filter(situacao=ServidorReativacaoTemporaria.STATUS_AUTORIZADA, data_fim__lt=hoje)
        return queryset


class ServidorReativacaoTemporariaAdmin(ReativacaoServidorAdminMixin, ModelAdminPlus):
    rotulo_solicitacao = 'Solicitar reativação temporária de servidor'
    rotulo_reativacao = 'Adicionar reativação temporária de servidor'
    list_display = ('servidor', 'situacao', 'autorizador', 'data_inicio', 'data_fim', 'cadastrado_por', 'data_cadastro', 'get_acoes')
    list_filter = ('situacao', ReativacaoTemporariaVigenciaFilter, 'cadastrado_por', 'autorizador')
    ordering = ('servidor__pessoa_fisica__nome', 'data_inicio')
    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome', 'cadastrado_por__username', 'autorizador__username')
    form = ServidorReativacaoTemporariaForm

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/autorizar/', self.admin_site.admin_view(self.autorizar_view), name='rh_servidorreativacaotemporaria_autorizar'),
            path('<int:pk>/negar/', self.admin_site.admin_view(self.negar_view), name='rh_servidorreativacaotemporaria_negar'),
            path('<int:pk>/encerrar/', self.admin_site.admin_view(self.encerrar_view), name='rh_servidorreativacaotemporaria_encerrar'),
        ]
        return custom + urls

    def _get_list_url(self):
        return reverse('admin:rh_servidorreativacaotemporaria_changelist')

    def _get_obj(self, request, pk):
        obj = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self._eh_rh_sistemico(request) or not self.has_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def _aplicar_autorizacao(self, request, obj):
        obj.autorizar(request.user)
        servidor = self._get_servidor_relacionado(obj.servidor_id)
        try:
            importador = ImportadorWs()
            cpf = servidor.pessoa_fisica.cpf
            importador.importacao_servidor(cpf, False, False)
            importador.atualizar_ferias_afastamentos(cpf=cpf, ano_inicio=1990)
            servidor = self._get_servidor_relacionado(obj.servidor_id)
            if servidor.ativo:
                ultimo_historico_setor = servidor.historico_setor_suap().order_by('-pk').first()
                if ultimo_historico_setor:
                    ultimo_historico_setor.data_fim_no_setor = None
                    ultimo_historico_setor.save()
                    servidor.setor = ultimo_historico_setor.setor
                    uo = ultimo_historico_setor.setor.uo
                    uo_siape = UnidadeOrganizacional.objects.filter(equivalente=uo).first()
                    servidor.setor_exercicio = uo_siape.setor
                    servidor.save()
        except ValidationError:
            pass
        vinculo = self._get_vinculo_servidor(servidor)
        user = self._get_user_servidor(servidor, vinculo=vinculo)
        if user:
            user.save()
        sync_ldap_user(servidor.matricula)

    def _encerrar(self, request, obj):
        obj.encerrar(request.user)
        servidor = self._get_servidor_relacionado(obj.servidor_id)
        vinculo = self._get_vinculo_servidor(servidor)
        if vinculo and not servidor.ativo and vinculo.ativo:
            Vinculo.objects.filter(pk=vinculo.pk).update(ativo=False)
        user = self._get_user_servidor(servidor, vinculo=vinculo)
        if user:
            user.save()
        sync_ldap_user(servidor.matricula)

    def save_model(self, request, obj, form, change):
        if not obj.cadastrado_por_id:
            obj.cadastrado_por = request.user
        if not change and self._eh_rh_sistemico(request):
            obj.situacao = obj.STATUS_AUTORIZADA
            obj.autorizador = request.user
            obj.data_autorizacao = get_datetime_now()
        elif not change:
            obj.situacao = obj.STATUS_SOLICITADA
        super().save_model(request, obj, form, change)

        if not change and self._eh_rh_sistemico(request):
            self._aplicar_autorizacao(request, obj)
        elif change and self._eh_rh_sistemico(request) and obj.situacao == obj.STATUS_AUTORIZADA and obj.data_fim < get_datetime_now().date():
            self._encerrar(request, obj)

    def autorizar_view(self, request, pk):
        obj = self._get_obj(request, pk)
        if obj.situacao != obj.STATUS_SOLICITADA:
            self.message_user(request, 'Só é possível autorizar solicitações pendentes.', level=messages.ERROR)
        else:
            self._aplicar_autorizacao(request, obj)
            self.message_user(request, 'Solicitação autorizada com sucesso.')
        return HttpResponseRedirect(self._get_list_url())

    def negar_view(self, request, pk):
        obj = self._get_obj(request, pk)
        if obj.situacao != obj.STATUS_SOLICITADA:
            self.message_user(request, 'Só é possível avaliar solicitações pendentes.', level=messages.ERROR)
        else:
            obj.negar(request.user)
            self.message_user(request, 'Solicitação não autorizada.')
        return HttpResponseRedirect(self._get_list_url())

    def encerrar_view(self, request, pk):
        obj = self._get_obj(request, pk)
        if obj.situacao != obj.STATUS_AUTORIZADA or obj.encerrada:
            self.message_user(request, 'Só é possível encerrar reativações temporárias autorizadas e ainda vigentes.', level=messages.ERROR)
        else:
            self._encerrar(request, obj)
            self.message_user(request, 'Reativação temporária encerrada com sucesso.')
        return HttpResponseRedirect(self._get_list_url())

    def get_acoes(self, obj):
        if not self._eh_rh_sistemico(self.request):
            return ''
        if obj.situacao == obj.STATUS_SOLICITADA:
            return mark_safe(
                f'<ul class="action-bar">'
                f'<li><a class="btn success" href="{reverse("admin:rh_servidorreativacaotemporaria_autorizar", args=[obj.pk])}">Autorizar</a></li>'
                f'<li><a class="btn danger" href="{reverse("admin:rh_servidorreativacaotemporaria_negar", args=[obj.pk])}">Não autorizar</a></li>'
                f'</ul>'
            )
        if obj.situacao == obj.STATUS_AUTORIZADA and not obj.encerrada:
            return mark_safe(
                f'<ul class="action-bar"><li><a class="btn warning" href="{reverse("admin:rh_servidorreativacaotemporaria_encerrar", args=[obj.pk])}">Encerrar</a></li></ul>'
            )
        return ''

    get_acoes.short_description = 'Ações'


admin.site.register(ServidorReativacaoTemporaria, ServidorReativacaoTemporariaAdmin)


class ServidorReativacaoPermanenteAdmin(ReativacaoServidorAdminMixin, ModelAdminPlus):
    rotulo_solicitacao = 'Solicitar reativação permanente de servidor'
    rotulo_reativacao = 'Adicionar reativação permanente de servidor'
    list_display = ('servidor', 'situacao', 'autorizador', 'ocorrencia_nome', 'ocorrencia_data', 'cadastrado_por', 'data_cadastro', 'get_acoes')
    list_filter = ('situacao', 'cadastrado_por', 'autorizador')
    ordering = ('-data_cadastro',)
    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome', 'ocorrencia_nome', 'cadastrado_por__username', 'autorizador__username')
    form = ServidorReativacaoPermanenteForm

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/autorizar/', self.admin_site.admin_view(self.autorizar_view), name='rh_servidorreativacaopermanente_autorizar'),
            path('<int:pk>/negar/', self.admin_site.admin_view(self.negar_view), name='rh_servidorreativacaopermanente_negar'),
        ]
        return custom + urls

    def _get_list_url(self):
        return reverse('admin:rh_servidorreativacaopermanente_changelist')

    def _get_obj(self, request, pk):
        obj = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self._eh_rh_sistemico(request) or not self.has_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def _aplicar_autorizacao(self, request, obj):
        servidor = self._get_servidor_relacionado(obj.servidor_id)
        servidor_ocorrencia = servidor.get_ocorrencia_exclusao_para_reativacao_permanente()
        obj.ocorrencia_removida = bool(servidor_ocorrencia)
        if servidor_ocorrencia:
            obj.ocorrencia_codigo = servidor_ocorrencia.ocorrencia.codigo
            obj.ocorrencia_nome = servidor_ocorrencia.ocorrencia.nome
            obj.ocorrencia_data = servidor_ocorrencia.data
            obj.ocorrencia_data_termino = servidor_ocorrencia.data_termino
            obj.subgrupo_descricao = servidor_ocorrencia.subgrupo.descricao if servidor_ocorrencia.subgrupo else ''
            obj.diploma_legal_num = servidor_ocorrencia.diploma_legal_num
            obj.diploma_legal_data = servidor_ocorrencia.diploma_legal_data
        else:
            obj.ocorrencia_codigo = None
            obj.ocorrencia_nome = None
            obj.ocorrencia_data = None
            obj.ocorrencia_data_termino = None
            obj.subgrupo_descricao = None
            obj.diploma_legal_num = None
            obj.diploma_legal_data = None
        obj.save(
            update_fields=[
                'ocorrencia_removida',
                'ocorrencia_codigo',
                'ocorrencia_nome',
                'ocorrencia_data',
                'ocorrencia_data_termino',
                'subgrupo_descricao',
                'diploma_legal_num',
                'diploma_legal_data',
            ]
        )
        obj.autorizar(request.user)
        if servidor_ocorrencia:
            servidor_ocorrencia.delete()
        Servidor.objects.filter(id=obj.servidor_id).update(ativo=True)
        servidor = self._get_servidor_relacionado(obj.servidor_id)
        vinculo = self._get_vinculo_servidor(servidor)
        if vinculo:
            Vinculo.objects.filter(pk=vinculo.pk).update(ativo=True)
        user = self._get_user_servidor(servidor, vinculo=vinculo)
        if user:
            user.save()
        sync_ldap_user(servidor.matricula)

    def save_model(self, request, obj, form, change):
        if not obj.cadastrado_por_id:
            obj.cadastrado_por = request.user
        if not change and self._eh_rh_sistemico(request):
            obj.situacao = obj.STATUS_AUTORIZADA
            obj.autorizador = request.user
            obj.data_autorizacao = get_datetime_now()
        elif not change:
            obj.situacao = obj.STATUS_SOLICITADA
        super().save_model(request, obj, form, change)

        if not change and self._eh_rh_sistemico(request):
            self._aplicar_autorizacao(request, obj)

    def autorizar_view(self, request, pk):
        obj = self._get_obj(request, pk)
        if obj.situacao != obj.STATUS_SOLICITADA:
            self.message_user(request, 'Só é possível autorizar solicitações pendentes.', level=messages.ERROR)
        else:
            self._aplicar_autorizacao(request, obj)
            self.message_user(request, 'Solicitação autorizada com sucesso.')
        return HttpResponseRedirect(self._get_list_url())

    def negar_view(self, request, pk):
        obj = self._get_obj(request, pk)
        if obj.situacao != obj.STATUS_SOLICITADA:
            self.message_user(request, 'Só é possível avaliar solicitações pendentes.', level=messages.ERROR)
        else:
            obj.negar(request.user)
            self.message_user(request, 'Solicitação não autorizada.')
        return HttpResponseRedirect(self._get_list_url())

    def get_acoes(self, obj):
        if not self._eh_rh_sistemico(self.request):
            return ''
        if obj.situacao == obj.STATUS_SOLICITADA:
            return mark_safe(
                f'<ul class="action-bar">'
                f'<li><a class="btn success" href="{reverse("admin:rh_servidorreativacaopermanente_autorizar", args=[obj.pk])}">Autorizar</a></li>'
                f'<li><a class="btn danger" href="{reverse("admin:rh_servidorreativacaopermanente_negar", args=[obj.pk])}">Não autorizar</a></li>'
                f'</ul>'
            )
        return ''

    get_acoes.short_description = 'Ações'


admin.site.register(ServidorReativacaoPermanente, ServidorReativacaoPermanenteAdmin)


class ServidorSetorHistoricoAdmin(ModelAdminPlus):
    form = ServidorSetorHistoricoForm
    list_display = ('servidor', 'setor', 'data_inicio_no_setor', 'data_fim_no_setor')
    list_filter = ['setor']
    search_fields = ['servidor__pessoa_fisica__nome', 'servidor__matricula', 'setor__nome']
    list_per_page = 20
    list_display_icons = True

    ordering = ('-data_inicio_no_setor', 'data_fim_no_setor')


admin.site.register(ServidorSetorHistorico, ServidorSetorHistoricoAdmin)


class ServidorSetorLotacaoHistoricoAdmin(ModelAdminPlus):
    list_display = ('servidor', 'setor_lotacao', 'setor_exercicio', 'data_inicio_setor_lotacao', 'data_fim_setor_lotacao')
    list_filter = get_uo_setor_listfilter('setor_lotacao', 'Setor Lotação', 'Campus Lotação', False) + get_uo_setor_listfilter(
        'setor_exercicio', 'Setor Exercício', 'Campus Exercício', False
    )
    search_fields = ['servidor__pessoa_fisica__nome', 'servidor__matricula']
    list_per_page = 20
    list_display_icons = True
    export_to_xls = True

    ordering = ('-data_inicio_setor_lotacao', 'data_fim_setor_lotacao')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.register(ServidorSetorLotacaoHistorico, ServidorSetorLotacaoHistoricoAdmin)


#########
# Setor #
#########


class SetorTelefoneInline(admin.TabularInline):
    model = SetorTelefone
    extra = 2
    form = SetorTelefoneForm


class SetorSuapSiapeFilter(admin.SimpleListFilter):
    title = 'Árvore de Setor'
    parameter_name = 'arvore_setor'

    def lookups(self, request, model_admin):
        return [[0, 'Todos'], [1, 'SUAP'], [2, 'SIAPE']]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == '1':
                return queryset.suap().distinct()
            elif self.value() == '0':
                return queryset.siape().distinct()
        return queryset


class SetorAdmin(ModelAdminPlus):
    form = SetorForm
    add_form = SetorAddForm
    list_display = ('show_info_principal', 'get_contatos', 'get_chefes', 'get_qtd_servidores', 'get_jornada', 'configuracoes')
    list_filter = ('uo', 'excluido', 'areas_vinculacao')
    list_display_icons = True
    list_per_page = 20
    export_to_xls = True
    ordering = ('sigla', 'nome')
    search_fields = ('sigla', 'nome', 'codigo')
    inlines = [SetorTelefoneInline]

    def get_list_filter(self, request):
        base = tuple(super().get_list_filter(request))
        if request.user.is_superuser and SetorSuapSiapeFilter not in base:
            return (*base, SetorSuapSiapeFilter)
        return base

    def restringir_queryset(self, request):
        """
        Superusuários podem ver todos os setores, os outros apenas os SUAP.
        """
        return request.user.is_superuser and Setor.objects or Setor.objects.suap()

    get_queryset = restringir_queryset

    def configuracoes(self, obj):
        out = ['<ul class="action-bar">']

        # Permissoes do processo e documento eletronico
        # ------------------------------------------------
        chefe_setor_ou_poder_de_chefe = False
        if self.request.user.eh_servidor and 'documento_eletronico' in settings.INSTALLED_APPS:
            from processo_eletronico.utils import chefe_ou_com_poder_de_chefe_no_setor

            chefe_setor_ou_poder_de_chefe = chefe_ou_com_poder_de_chefe_no_setor(self.request.user, obj)
            if chefe_setor_ou_poder_de_chefe:
                out.append(
                    '<li>'
                    f'<a class="btn primary" href="/processo_eletronico/permissoes/?setor={obj.pk:d}">Permissões para Documentos e Processos Eletrônicos</a>'
                    '</li>'
                )

        # Jornadas de Trabalho
        # ------------------------------------------------
        if self.request.user.has_perm('rh.pode_gerenciar_setor_jornada_historico'):
            out.append(f'<li><a class="btn primary" href="/rh/setor_jornada_historico/{obj.pk:d}/">Gerenciamento de Jornadas de Trabalho</a></li>')

        # Configuração de equivalência
        # ------------------------------------------------
        if self.request.user.has_perm('rh.eh_rh_sistemico') and obj.codigo is None:
            icon_ready = " <i class='fa fa-thumbs-up'></i>" if obj.equivalencia_codigo else ''
            out.append(f'<li><a class="btn success popup" href="/rh/equivalencia_setor/{obj.pk:d}/">Gerenciar Equivalência{icon_ready}</a></li>')

        out.append('</ul>')

        return mark_safe(''.join(out))

    configuracoes.short_description = 'Configurações'

    def show_info_principal(self, obj):
        # Principal
        out = [
            f"""
        <p><strong>{obj.sigla}</strong> ({obj.nome})</p>
        <p>{obj.get_caminho_as_html()}</p>"""
        ]

        return mark_safe(''.join(out))

    show_info_principal.short_description = 'Informações Principais'
    show_info_principal.admin_order_field = 'sigla'

    def get_jornada(self, obj):
        return obj.tipo_jornada_trabalho_por_data()

    get_jornada.short_description = 'Jornada de Trabalho'

    def get_qtd_servidores(self, obj):
        # Servidores
        qtd_servidores = Servidor.objects.filter(ativo=True, setor=obj).count()
        if qtd_servidores == 0:
            info_servidores = '<span class="status status-error">Nenhum servidor</span>'
        else:
            info_servidores = f"""
            <a href="/admin/rh/servidor/?ativo__exact=1&setor__id__exact={obj.pk}"
               title="Listar servidores">
                {qtd_servidores} servidor{'es' if qtd_servidores > 1 else ''}
            </a>"""
        return mark_safe(f'{info_servidores}')

    get_qtd_servidores.short_description = 'Qtd. de Servidores'

    def get_contatos(self, obj):
        saida = []

        if obj.setortelefone_set.all().exists():
            telefones = ''.join(f'<dd>{telefone}</dd>' for telefone in obj.setortelefone_set.all())
            saida.append(f'<dt>Telefones:</dt>{telefones}')

        if obj.email is not None:
            saida.append(f'<dt>Email:</dt><dd>{obj.email}</dd>')

        if saida:
            saida.insert(0, '<dl>')
            saida.append('</dl>')

        return mark_safe(''.join(saida))

    get_contatos.short_description = 'Contatos'

    def get_chefes(self, obj):
        out = []
        for servidor in Servidor.objects.ativos().filter(pk__in=obj.historico_funcao().values_list('servidor', flat=True).distinct()):
            out.append(f'<li>{format_user(servidor.get_user())}</li>')
        return mark_safe('<ul>{}</ul>'.format(''.join(out)))

    get_chefes.short_description = 'Chefes'

    def get_form(self, request, obj=None, **kwargs):
        if request.user.is_superuser:
            kwargs['exclude'] = []
        else:
            kwargs['exclude'] = ['codigo']
        return super().get_form(request, obj=obj, **kwargs)

    def to_xls(self, request, queryset, task):
        header = [
            '#',
            'Setor Nome',
            'Setor Sigla',
            nomenclatura.campus,
            f'{nomenclatura.campus} Sigla',
            'Hierarquia',
            'Código SIAPE',
            'Código Siorg',
            'Data da Criação',
            'Email',
            'Portaria Criação',
            'Bases legais internas',
            'Bases legais externas',
            'Telefones',
            'Chefes do Setor',
            'Tipo de Jornada Trabalho',
            'Quantidade de Servidores',
        ]
        rows = [header]
        for idx, obj in enumerate(task.iterate(queryset)):
            uo = obj.uo
            row = [
                idx + 1,
                f'{obj.nome}',
                f'{obj.sigla}',
                f'{obj.uo.nome}' if uo else '',
                f'{obj.uo.sigla}' if uo else '',
                ' -> '.join([f'{c.sigla}' for c in obj.get_caminho()]),
                obj.codigo or '',
                obj.codigo_siorg or '',
                obj.data_criacao.strftime('%d/%m/%Y') if obj.data_criacao else '',
                obj.email or '',
                obj.portaria_criacao or '',
                obj.bases_legais_internas,
                obj.bases_legais_externas,
                ','.join([f'{st.numero}(ramal:{st.ramal})' for st in obj.setortelefone_set.all()]),
                ','.join([str(chefe) for chefe in obj.chefes.all()]),
                obj.tipo_jornada_trabalho_por_data(),
                Servidor.objects.filter(ativo=True, setor=obj).count(),
            ]
            rows.append(row)
        return rows


admin.site.register(Setor, SetorAdmin)


###############
# Situacao
###############


class SituacaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'nome_siape', 'codigo', 'excluido')
    ordering = ('excluido', 'nome', 'nome_siape', 'codigo')
    list_filter = ['excluido']
    search_fields = ('nome', 'nome_siape', 'codigo')


admin.site.register(Situacao, SituacaoAdmin)


##########
# Campus #
##########
class TipoUnidadeOrganizacionalAdmin(ModelAdminPlus):
    pass


admin.site.register(TipoUnidadeOrganizacional, TipoUnidadeOrganizacionalAdmin)


class UoComCodigoUgFilter(admin.SimpleListFilter):
    title = 'Possui UG'
    parameter_name = 'possui_ug'

    def lookups(self, request: Any, model_admin: Any) -> tuple[tuple[str, str], tuple[str, str]]:
        return (('sim', 'Sim'), ('nao', 'Não'))

    def queryset(self, request: Any, queryset: Any) -> Any:
        if self.value() == 'sim':
            return queryset.exclude(codigo_ug='')
        if self.value() == 'nao':
            return queryset.filter(codigo_ug='')
        return queryset


class UoComCodigoUgrFilter(admin.SimpleListFilter):
    title = 'Possui UGR'
    parameter_name = 'possui_ugr'

    def lookups(self, request: Any, model_admin: Any) -> tuple[tuple[str, str], tuple[str, str]]:
        return (('sim', 'Sim'), ('nao', 'Não'))

    def queryset(self, request: Any, queryset: Any) -> Any:
        if self.value() == 'sim':
            return queryset.exclude(codigo_ugr='')
        if self.value() == 'nao':
            return queryset.filter(codigo_ugr='')
        return queryset


class UoSuapSiapeFilter(admin.SimpleListFilter):
    title = 'Tipo de cadastro'
    parameter_name = 'tipo_cadastro'

    def lookups(self, request: Any, model_admin: Any) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
        return (('todos', 'Todos'), ('suap', 'SUAP'), ('siape', 'SIAPE'))

    def queryset(self, request: Any, queryset: Any) -> Any:
        if self.value() == 'suap':
            return queryset.filter(setor__codigo__isnull=True)
        if self.value() == 'siape':
            return queryset.filter(setor__codigo__isnull=False)
        return queryset


class UnidadeOrganizacionalAdmin(ModelAdminPlus):
    list_display = ('id', 'nome', 'sigla', 'codigo_ug', 'codigo_ugr', 'setor', 'municipio', 'codigo_protocolo', 'show_tipo')
    list_filter = (UoComCodigoUgrFilter, UoComCodigoUgFilter, UoSuapSiapeFilter, 'tipo')
    search_fields = ('setor__sigla', 'setor__nome')
    list_display_icons = True
    export_to_xls = True

    def get_queryset(self, request, manager=None, *args, **kwargs):
        if request.user.is_superuser:
            queryset = UnidadeOrganizacional.objects
        else:
            queryset = UnidadeOrganizacional.objects.suap()
        return queryset

    def show_tipo(self, obj):
        return mark_safe(obj.setor.codigo and '<span class="false">SIAPE</span>' or '<span class="true">SUAP</span>')

    show_tipo.admin_order_field = 'setor__codigo'
    show_tipo.short_description = 'Tipo'

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = '',
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        uo = self.get_object(request, object_id)
        if request.method == 'GET' and uo and uo.setor and uo.setor.eh_suap and not uo.codigo_protocolo:
            self.message_user(
                request,
                'Prefixo para geração do número de protocolo não informado. Isso impede a geração de processos eletrônicos nesta unidade.',
                level=messages.WARNING,
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def get_form(self, request, obj=None, **kwargs):
        eh_siape = False
        if not obj:
            setor_qs = Setor.objects.filter(excluido=False)
            help_text = 'Exibindo todos os setores.'
        elif obj and obj.setor.codigo:
            setor_qs = Setor.objects.siape().all()
            eh_siape = True
            help_text = 'Exibindo apenas setores SIAPE.'
        else:
            setor_qs = Setor.objects.suap_ativos().all()
            help_text = 'Exibindo apenas setores SUAP.'
        if eh_siape:
            self.fieldsets = (
                (f'Tipo {nomenclatura.campus}', {'fields': ('tipo',)}),
                ('Dados gerais', {'fields': (('nome', 'sigla'), ('setor', 'cnpj'), ('codigo_ug', 'codigo_ugr'), 'equivalente')}),
                ('Endereço', {'fields': ('endereco', ('municipio', 'zona_rual'), ('cep', 'bairro'))}),
                ('Contato', {'fields': (('telefone', 'fax'),)}),
                ('Protocolo', {'fields': ('codigo_protocolo',)}),
                ('Acadêmico', {'fields': (('codigo_inep', 'codigo_censup', 'codigo_emec'), 'portaria_criacao')}),
                ('ConectaGOV - Barramento PEN', {'fields': ('id_repositorio_pen', 'id_estrutura_pen')}),
            )

        else:
            self.fieldsets = (
                (f'Tipo do {nomenclatura.campus}', {'fields': ('tipo',)}),
                ('Dados gerais', {'fields': (('nome', 'sigla'), ('setor', 'cnpj'), ('codigo_ug', 'codigo_ugr'))}),
                ('Endereço', {'fields': (('endereco', 'numero'), ('municipio', 'zona_rual'), ('cep', 'bairro'))}),
                ('Contato', {'fields': (('telefone', 'fax'),)}),
                ('Protocolo', {'fields': ('codigo_protocolo',)}),
                ('Acadêmico', {'fields': (('codigo_inep', 'codigo_censup'), ('codigo_emec', 'codigo_sistec'), 'portaria_criacao')}),
                ('ConectaGOV - Barramento PEN', {'fields': ('setor_recebimento_pen', 'id_repositorio_pen', 'id_estrutura_pen')}),
            )

        class UnidadeOrganizacionalForm(forms.ModelFormPlus):
            class Meta:
                model = UnidadeOrganizacional
                exclude = ()
                if not eh_siape:
                    exclude = ('equivalente',)

            setor = forms.ModelChoiceFieldPlus2(
                queryset=setor_qs, help_text=help_text, label_template='{{ obj }} ({% if obj.codigo %}SIAPE{% else %}SUAP{% endif %})'
            )

            setor_recebimento_pen = forms.ModelChoiceField(
                label='Setor de Recebimento de Processos Externos',
                queryset=Setor.objects.suap_ativos().all(),
                required=False,
                widget=AutocompleteWidget(),
            )

        return UnidadeOrganizacionalForm


admin.site.register(UnidadeOrganizacional, UnidadeOrganizacionalAdmin)


#############
# Avaliador #
#############
class AvaliadorInternoExternoFilter(admin.SimpleListFilter):
    title = 'Tipo de Avaliador'
    parameter_name = 'tipo_avaliador'

    def lookups(self, request, model_admin):
        tipo_avaliador = [[0, 'Avaliador Interno'], [1, 'Avaliador Externo']]
        return tipo_avaliador

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == '1':
                return queryset.filter(vinculo__tipo_relacionamento=ContentType.objects.get(Vinculo.SERVIDOR))
            elif self.value() == '0':
                return queryset.filter(vinculo__tipo_relacionamento=ContentType.objects.get(Vinculo.PRESTADOR))
        return queryset


class AvaliadorAdmin(ModelAdminPlus):
    list_display = (
        'get_cpf',
        'get_nome',
        'get_instituicao_origem',
        'get_dados_bancarios',
        'get_foto',
        'avaliacoes_realizadas_no_ano',
        'qtd_perda_prazo_aceite',
        'qtd_perda_prazo_avaliacao',
        'qtd_rejeicao_avaliacao',
        'nivel_atual',
        'area_conhecimento',
        'ativo',
    )
    list_filter = ('ativo', AvaliadorInternoExternoFilter, 'instituicao_origem', 'banco', 'nivel_atual', 'area_conhecimento')
    search_fields = ('vinculo__pessoa__nome', 'vinculo__user__vinculo__pessoa__pessoafisica__cpf', 'vinculo__user__username')
    form = AvaliadorExternoForm
    list_display_icons = True
    list_per_page = 40
    ordering = ('vinculo__pessoa__nome',)
    export_to_xls = True

    fieldsets = (
        (
            'Dados pessoais',
            {
                'fields': (
                    'nome',
                    'sexo',
                    'nascimento_data',
                    'email',
                    'matricula_siape',
                    'titulacao',
                    'numero_telefone',
                )
            },
        ),
        ('Dados institucionais', {'fields': ('padrao_vencimento', 'instituicao_origem', 'nivel_atual', 'area_conhecimento')}),
        (
            'Documentos',
            {
                'fields': (
                    'cpf',
                    'numero_documento_identificacao',
                    'emissor_documento_identificacao',
                    'pis_pasep',
                )
            },
        ),
        (
            'Dados bancários',
            {
                'fields': (
                    'banco',
                    'numero_agencia',
                    'tipo_conta',
                    'numero_conta',
                    'operacao',
                )
            },
        ),
        (
            'Endereço',
            {
                'fields': (
                    'endereco_cep',
                    ('endereco_municipio', 'endereco_logradouro', 'endereco_numero'),
                    (
                        'endereco_complemento',
                        'endereco_bairro',
                    ),
                )
            },
        ),
    )

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Matrícula',
            'Nome',
            'Data de nascimento',
            'CPF',
            'Telefone',
            'E-mail para contato',
            'Instituição de origem',
            'Nível atual',
            'Área de conhecimento',
            'Número do documento de identificação',
            'Emissor do documento de identificação',
            'PIS/PASEP',
            'Logradouro',
            'Número',
            'Município',
            'Complemento',
            'Bairro',
            'CEP',
            'Banco',
            'Número de agência',
            'Tipo de conta',
            'Número da conta',
            'Operação',
        ]

        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset), 1):
            row = [
                idx,
                obj.get_matricula(),
                obj.vinculo.user.get_profile().nome,
                obj.vinculo.user.get_profile().nascimento_data,
                obj.vinculo.user.get_profile().cpf,
                obj.vinculo.user.get_profile().telefones,
                obj.vinculo.email_pessoal,
                obj.instituicao_origem,
                obj.nivel_atual,
                obj.area_conhecimento,
                obj.numero_documento_identificacao,
                obj.emissor_documento_identificacao,
                obj.pis_pasep,
                obj.endereco_logradouro,
                obj.endereco_numero,
                obj.endereco_municipio,
                obj.endereco_complemento,
                obj.endereco_bairro,
                obj.endereco_cep,
                obj.banco,
                obj.numero_agencia,
                obj.tipo_conta,
                obj.numero_conta,
                obj.operacao,
            ]
            rows.append(row)
        return rows

    def avaliacoes_realizadas_no_ano(self, obj):
        return obj.avaliacoes_realizadas_no_ano()

    avaliacoes_realizadas_no_ano.short_description = 'Avaliações realizadas no ano'

    def get_instituicao_origem(self, obj):
        uasg = obj.instituicao_origem.uasg if obj.instituicao_origem else '-'
        ug = obj.instituicao_origem.unidade_gestora if obj.instituicao_origem else '-'
        out = """
        <dl>
            <dt>Instituição de Origem:</dt><dd>{instituicao}</dd>
            <dt>UG:</dt><dd>{ug} </dd>
            <dt>UASG:</dt><dd>{uasg} </dd>
        </dl>
        """.format(instituicao=obj.instituicao_origem or '-', ug=ug, uasg=uasg)
        return mark_safe(out)

    get_instituicao_origem.short_description = 'Instituição Origem'

    def get_dados_bancarios(self, obj):
        banco = obj.banco or '-'
        numero_agencia = obj.numero_agencia or '-'
        numero_conta = obj.numero_conta or '-'
        operacao = obj.operacao or '-'
        out = f"""
        <dl>
            <dt>Banco:</dt><dd>{banco}</dd>
            <dt>Agência:</dt><dd>{numero_agencia} </dd>
            <dt>Conta:</dt><dd>{numero_conta} </dd>
            <dt>Operação:</dt><dd>{operacao} </dd>
        </dl>
        """
        return mark_safe(out)

    get_dados_bancarios.short_description = 'Dados Bancários'

    def qtd_perda_prazo_aceite(self, obj):
        return obj.qtd_perda_prazo_aceite()

    qtd_perda_prazo_aceite.short_description = 'Excedeu prazo de aceite'

    def qtd_perda_prazo_avaliacao(self, obj):
        return obj.qtd_perda_prazo_avaliacao()

    qtd_perda_prazo_avaliacao.short_description = 'Excedeu prazo de avaliação'

    def qtd_rejeicao_avaliacao(self, obj):
        return obj.qtd_rejeicao_avaliacao()

    qtd_rejeicao_avaliacao.short_description = 'Rejeições de avaliação'

    def get_cpf(self, obj):
        return obj.vinculo.user.get_profile().cpf

    get_cpf.short_description = 'CPF'

    def get_nome(self, obj):
        return obj.vinculo.user.get_profile().nome

    get_nome.short_description = 'Nome'

    def get_foto(self, obj):
        return mark_safe(f'<img class="foto-miniatura" src="{obj.vinculo.user.get_vinculo().get_foto_75x100_url()}"/>')

    get_foto.short_description = 'Foto'


admin.site.register(Avaliador, AvaliadorAdmin)


#############
# AreaVinculacao #
#############


class AreaVinculacaoAdmin(ModelAdminPlus):
    list_display = ('id', 'ordem', 'descricao')
    fields = ('descricao', 'ordem')
    form = AreaVinculacaoForm


admin.site.register(AreaVinculacao, AreaVinculacaoAdmin)


class InstituicaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'unidade_gestora', 'uasg', 'ativo')
    ordering = ('ativo', 'nome')
    list_filter = ('ativo',)
    search_fields = ('nome',)
    form = InstituicaoForm


admin.site.register(Instituicao, InstituicaoAdmin)


class AcaoSaudeAtivoFilter(admin.SimpleListFilter):
    title = 'Ação de Saúde Ativas'
    parameter_name = 'acao_saude_ativa'

    def lookups(self, request, model_admin):
        options = [[1, 'Sim'], [0, 'Não']]
        return options

    def queryset(self, request, queryset):
        value = 1
        if self.value() and self.value() == '0':
            value = 0

        if value == 1:
            hoje = datetime.datetime.now()
            queryset = queryset.filter(periodo_inscricao_inicio__lte=hoje, periodo_inscricao_fim__gte=hoje)

        return queryset


class AcaoSaudeAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_filter = (AcaoSaudeAtivoFilter,)
    form = AcaoSaudeForm
    list_display_icons = True
    list_display_links = None
    list_display = ('descricao', 'data_inicio', 'data_fim', 'periodo_inscricao_inicio', 'periodo_inscricao_fim', 'get_dias_semanas')

    fieldsets = (('', {'fields': ('descricao', ('data_inicio', 'data_fim'), ('periodo_inscricao_inicio', 'periodo_inscricao_fim'), 'dias_semanas')}),)

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if AcaoSaude.pode_ver_toda_agenda(request.user):
            list_display = (*list_display, 'get_acoes')
        else:
            list_display = (*list_display, 'get_coluna_inscricao_horarios')
        return list_display

    def get_dias_semanas(self, obj):
        if obj.dias_semanas:
            lista = []
            dias_semanas = obj.dias_semanas.split(',')
            for i in range(len(dias_semanas)):
                dia_semana = int(dias_semanas[i])
                lista.append(DiaSemanaChoices.DIAS_RESUMIDO_CHOICES[dia_semana - 1][1])
            return ','.join(lista)
        return None

    get_dias_semanas.short_description = 'Dias de Semana'

    def get_acoes(self, obj):
        html = '<ul class="action-bar">'
        if (self.request.user.is_superuser or self.request.user.has_perm('rh.add_agendaatendimentohorario')) and obj.em_periodo_inscricao():
            html += f'<li><a href="/rh/adicionar_horario/{obj.id}/" class="btn success">Adicionar Horários</a></li>'

            if obj.agendaatendimentohorario_set.exists():
                html += '<li class="has-child"><a href="#" class="btn success">Agendar</a><ul style="display: none;">'
                for horario in obj.agendaatendimentohorario_set.all().order_by('hora_inicio'):
                    html += f'<li><a class="btn" href="/rh/agendar_horario/{horario.id}/"> {horario.horario_atendimento()} ({horario.profissional}) </a></li>'
                html += '</ul></li>'

        html += '</ul>'
        return mark_safe(html)

    get_acoes.short_description = 'Opções'

    def get_coluna_inscricao_horarios(self, obj):
        html = '<ul>'
        for horario in obj.agendaatendimentohorario_set.all().order_by('hora_inicio'):
            html += f'<li><a href="/rh/agendar_horario/{horario.id}/"> {horario.horario_atendimento()} </a></li>'
        html += '</ul>'
        return mark_safe(html)

    get_coluna_inscricao_horarios.short_description = 'Inscrição'


admin.site.register(AcaoSaude, AcaoSaudeAdmin)


class HorarioAgendadoAdmin(ModelAdminPlus):
    list_display = ('get_icons_actions', 'solicitante', 'get_acao_saude', 'get_horarios', 'data_consulta', 'cancelado')
    list_display_icons = False
    list_display_links = None
    search_fields = ('solicitante__pessoa__nome',)
    list_filter = ('horario__acao_saude', 'horario__profissional', 'cancelado')
    form = AgendarAtendimentoForm

    def get_acao_saude(self, obj):
        return mark_safe(obj.horario.acao_saude)

    get_acao_saude.short_description = 'Ação de Saúde'

    def get_horarios(self, obj):
        html = '<ul>'
        html += f'<li>{obj.horario.hora_inicio} às {obj.horario.hora_fim}</li>'
        html += '</ul>'
        return mark_safe(html)

    get_horarios.short_description = 'Horários'

    def get_icons_actions(self, obj):
        html = f"""
                <a href="/rh/cancelar_agendamento/{obj.id}/" class="btn warning confirm">Cancelar</a>
                <a href="/admin/rh/horarioagendado/{obj.id}/delete/" class="btn danger">Deletar</a>
                """
        return mark_safe(html)

    get_icons_actions.short_description = '#'


admin.site.register(HorarioAgendado, HorarioAgendadoAdmin)


class AgendaAtendimentoHorarioAdmin(ModelAdminPlus):
    list_display = ('acao_saude', 'profissional', 'get_periodo', 'quantidade_vaga', 'get_quantidade_inscritos', 'get_acoes')
    search_fields = ('acao_saude__descricao', 'profissional__pessoa_fisica__nome')
    list_filter = ('acao_saude',)
    list_display_icons = True
    form = AgendaAtendimentoHorarioForm

    def get_periodo(self, obj):
        return mark_safe('De {} até {}'.format(obj.hora_inicio.strftime('%H:%M'), obj.hora_fim.strftime('%H:%M')))

    get_periodo.short_description = 'Período'

    def get_quantidade_inscritos(self, obj):
        hoje = datetime.datetime.now()
        return obj.horarioagendado_set.filter(cancelado=False, data_consulta__gte=hoje).count()

    get_quantidade_inscritos.short_description = 'Quantidade de Inscritos'

    def get_acoes(self, obj):
        return mark_safe(f'<a href="/rh/agendar_horario/{obj.id}/" class="btn success">Inscrição</a>')

    get_acoes.short_description = 'Opções'


admin.site.register(AgendaAtendimentoHorario, AgendaAtendimentoHorarioAdmin)


class DataConsultaBloqueadaAdmin(ModelAdminPlus):
    list_display = ('acao_saude', 'data_consulta_bloqueada', 'motivo_bloqueio', 'houve_remarcacao')
    list_display_icons = True
    fields = ('acao_saude', 'data_consulta_bloqueada', 'motivo_bloqueio')
    list_filter = ('acao_saude',)
    form = DataConsultaBloqueadaForm


admin.site.register(DataConsultaBloqueada, DataConsultaBloqueadaAdmin)


class PapelAdmin(ModelAdminPlus):
    search_fields = ('vinculo__user__username', 'vinculo__pessoa__nome', 'descricao', 'detalhamento')
    list_filter = get_uo_setor_listfilter('setor_suap')
    list_display = ('vinculo', 'descricao', 'detalhamento', 'data_inicio', 'data_fim')
    fields = ('vinculo', 'descricao', 'detalhamento', 'data_inicio', 'data_fim')
    date_hierarchy = 'data_inicio'


admin.site.register(Papel, PapelAdmin)


class CargaHorariaReduzidaAdmin(ModelAdminPlus):
    list_display = ('opcoes', 'servidor', 'numero', 'data_inicio', 'data_termino', 'status_estilizado')
    search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')
    show_count_on_tabs = True
    list_filter = (CustomTabListFilter,)
    form = ProcessoCargaHorariaReduzidaRHForm

    def opcoes(self, obj: CargaHorariaReduzida) -> str:
        html = icon('view', f'/rh/abrir_processo_afastamento_parcial/{obj.id}/')
        if self.has_change_permission(self.request, obj.id):
            html += icon('edit', f'/admin/rh/cargahorariareduzida/{obj.id}/change/')

        if obj.pode_ser_excluido_por(self.request.user):
            html += icon('delete', f'/rh/excluir_processo_afastamento_parcial/{obj.id}/')

        return html

    opcoes.allow_tags = True
    opcoes.short_description = 'Ações'

    def status_estilizado(self, obj):
        return mark_safe(obj.status_estilizado)

    status_estilizado.allow_tags = True
    status_estilizado.admin_order_field = 'status'
    status_estilizado.short_description = 'Situação do Processo'

    def get_tabs(self, request):
        #
        # padrão
        tabs = []
        self.list_display = ('opcoes', 'servidor', 'tipo', 'get_numero', 'data_inicio', 'data_termino', 'status_estilizado')
        """Situaçoes:
        - eh chefe e pertence ao RH
        - eh chefe e nao pertence ao RH
        - nao eh chefe e pertence ao RH
        - nao eh chefe nem pertence ao RH
        """
        if self.existe_minhas_validacoes_como_chefe(request):
            if self._pertence_grupo_coordenador_rh(request):
                # 'eh chefe e RH'
                tabs = [
                    'tab_meus_processos',
                    'tab_processos_validados',
                    'tab_meus_processos_pendentes_de_validacao',
                    'tab_processos_validados_rh',
                    'tab_processos_pendentes_de_validacao_rh',
                ]
            else:
                # 'eh chefe e nao RH'
                tabs = ['tab_meus_processos', 'tab_processos_validados', 'tab_meus_processos_pendentes_de_validacao']
        else:
            if self._pertence_grupo_coordenador_rh(request):
                # 'nao eh chefe e pertence ao RH'
                tabs = ['tab_meus_processos', 'tab_processos_validados_rh', 'tab_processos_pendentes_de_validacao_rh']
            else:
                # 'nao eh chefe nem pertence ao RH'
                tabs = []
        return tabs

    def response_add(self, request, obj, post_url_continue=None):
        if obj.id:
            return httprr(f'/rh/abrir_processo_afastamento_parcial/{obj.id}/')
        return super().response_add(request, obj, post_url_continue)

    def get_numero(self, obj):
        if obj.protocolo_content_object:
            if obj.protocolo_content_type.app_label == 'processo_eletronico':
                return mark_safe(
                    f'<a href="/processo_eletronico/processo/{obj.protocolo_content_object.id}/" class="popup">{obj.protocolo_content_object}</a>'
                )
            elif obj.protocolo_content_type.app_label == 'protocolo':
                return mark_safe(f'<a href="/protocolo/processo/{obj.protocolo_content_object.id}/" class="popup">{obj.protocolo_content_object}</a>')
        return None

    get_numero.allow_tags = True
    get_numero.short_description = 'Número do Processo'

    def has_add_permission(self, request):
        usuario_logado_eh_rh_sistemico = request.user.has_perm('rh.eh_rh_sistemico')
        grupo_coordenador_rh_campus = request.user.has_perm('rh.eh_rh_campus')
        return (
            usuario_logado_eh_rh_sistemico
            or request.user.is_superuser
            or grupo_coordenador_rh_campus
            and ('processo_eletronico' in settings.INSTALLED_APPS or 'protocolo' in settings.INSTALLED_APPS)
        )

    def has_change_permission(self, request, obj=None):
        return self.has_add_permission(request)

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(f'/rh/abrir_processo_afastamento_parcial/{obj_pk}/')

    def get_queryset(self, request, manager=None, *args, **kwargs):
        # print 'nao eh chefe nem pertence ao RH'
        qs = super().get_queryset(request, manager, *args, **kwargs)
        return self.regras_filtro_queryset(request, qs)

    def regras_filtro_queryset(self, request: HttpRequest, qs: QuerySet[CargaHorariaReduzida]) -> QuerySet[CargaHorariaReduzida]:
        """Só o RH (e o superusuário) lista, e cada um só os processos do seu alcance (``CargaHorariaReduzida.filtro_escopo_rh``)."""
        if not in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico, Coordenador de Gestão de Pessoas'):
            raise PermissionDenied
        return qs.filter(
            CargaHorariaReduzida.filtro_escopo_rh(request.user),
            status__in=[
                CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH,
                CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH,
                CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH,
                CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO,
                CargaHorariaReduzida.STATUS_ALTERANDO_HORARIO,
            ],
        )

    def existe_minhas_validacoes_como_chefe(self, request):
        eu = request.user.get_relacionamento()
        minhas_validacoes = CargaHorariaReduzida.objects.filter(chefe_imediato_validador=eu)
        minhas_validacoes_pendentes = CargaHorariaReduzida.objects.filter(
            id__in=[hc.id for hc in CargaHorariaReduzida.get_processos_afastamento_aguardando_validacao(chefe_imediato_validador=eu)]
        )
        return minhas_validacoes.exists() or minhas_validacoes_pendentes.exists()

    """tabs de usuário que é chefe"""

    def tab_meus_processos(self, request, queryset):
        eu = request.user.get_relacionamento()
        return queryset.filter(servidor=eu)

    tab_meus_processos.short_description = 'Meus processos'

    def tab_processos_validados(self, request, queryset):
        eu = request.user.get_relacionamento()
        return queryset.filter(chefe_imediato_validador=eu)

    tab_processos_validados.short_description = 'Processos validados como chefe'

    def tab_meus_processos_pendentes_de_validacao(self, request, queryset):
        eu = request.user.get_relacionamento()
        return queryset.filter(
            id__in=[hc.id for hc in CargaHorariaReduzida.get_processos_afastamento_aguardando_validacao(chefe_imediato_validador=eu)]
        )

    tab_meus_processos_pendentes_de_validacao.short_description = 'Processos pendentes de validação do chefe'

    """tabs do usuário que pertence ao grupo de RH"""

    def tab_processos_pendentes_de_validacao_rh(self, request, queryset):
        return queryset.filter(status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH).exclude(
            id__in=[hc.id for hc in self.tab_meus_processos(request, queryset)]
        )

    tab_processos_pendentes_de_validacao_rh.short_description = 'Processos pendentes de validação do RH'

    def tab_processos_validados_rh(self, request, queryset):
        return queryset.filter(servidor_rh_validador__isnull=False)

    tab_processos_validados_rh.short_description = 'Processos validados pelo RH'

    def _pertence_grupo_coordenador_rh(self, request):
        # Grupo de pessoas responsáveis por gerenciar a validação do RH
        grupo_coordenador_sistemico = 'Coordenador de Gestão de Pessoas Sistêmico'
        grupo_coordenador_rh_campus = 'Coordenador de Gestão de Pessoas'
        user_groups = request.user.groups.values_list('name', flat=1)
        return grupo_coordenador_sistemico in user_groups or grupo_coordenador_rh_campus in user_groups


admin.site.register(CargaHorariaReduzida, CargaHorariaReduzidaAdmin)

######################
# Posicionamento PCA #
######################


class PosicionamentoPCAAdmin(ModelAdminPlus):
    list_display = ('get_servidor', 'forma_entrada', 'data_inicio_posicionamento_pca', 'data_fim_posicionamento_pca', 'eh_capacitacao')
    list_filter = ('forma_entrada',)
    search_fields = ('pca__servidor__pessoa_fisica__nome', 'pca__servidor__matricula')
    list_display_icons = True
    form = PosicionamentoPCAForm

    def get_servidor(self, obj):
        return obj.pca.servidor

    get_servidor.short_description = 'Servidor'
    get_servidor.admin_order_field = 'pca__servidor__pessoa_fisica__nome'


admin.site.register(PosicionamentoPCA, PosicionamentoPCAAdmin)


class JornadaTrabalhoPCAInline(admin.StackedInline):
    form = JornadaTrabalhoPCAForm
    model = JornadaTrabalhoPCA
    extra = 1


class RegimeJuridicoPCAInline(admin.StackedInline):
    form = RegimeJuridicoPCAForm
    model = RegimeJuridicoPCA
    extra = 1


class PosicionamentoPCAInline(admin.StackedInline):
    form = PosicionamentoPCAForm
    model = PosicionamentoPCA
    extra = 1


class PCAAdmin(ModelAdminPlus):
    list_display = ('servidor', 'data_entrada_pca', 'get_jornada_trabalho', 'get_regime_juridico', 'get_posicionamento_pca')
    list_filter = ('servidor',)
    inlines = [PosicionamentoPCAInline, JornadaTrabalhoPCAInline, RegimeJuridicoPCAInline]
    list_display_icons = True
    form = PCAForm

    def get_jornada_trabalho(self, obj):
        html = '<ul>'
        for j in obj.jornadatrabalhopca_set.all():
            html += f'<li><a href="/admin/rh/jornadatrabalhopca/{j.id}/">Data Início: {j.data_inicio_jornada_trabalho_pca} </a></li>'
        html += '</ul>'
        return mark_safe(html)

    get_jornada_trabalho.short_description = 'Jornada de Trabalho PCA'

    def get_regime_juridico(self, obj):
        html = '<ul>'
        for r in obj.regimejuridicopca_set.all():
            html += f'<li><a href="/admin/rh/regimejuridicopca/{r.id}/">Data Início: {r.data_inicio_regime_juridico_pca} </a></li>'
        html += '</ul>'
        return mark_safe(html)

    get_regime_juridico.short_description = 'Regime Jurídico PCA'

    def get_posicionamento_pca(self, obj):
        html = '<ul>'
        for p in obj.posicionamentopca_set.all():
            html += f'<li><a href="/admin/rh/posicionamentopca/{p.id}/">{p.forma_entrada.descricao} - Data Início: {p.data_inicio_posicionamento_pca}</a></li>'
        html += '</ul>'
        return mark_safe(html)

    get_posicionamento_pca.short_description = 'Posicionamento PCA'


admin.site.register(PCA, PCAAdmin)


class JornadaTrabalhoPCAAdmin(ModelAdminPlus):
    list_display = ('pca', 'data_inicio_jornada_trabalho_pca', 'data_fim_jornada_trabalho_pca', 'qtde_jornada_trabalho_pca')
    list_filter = ('pca__servidor',)
    list_display_icons = True
    search_fields = [f'pca__servidor__{term}' for term in Servidor.SEARCH_FIELDS]
    form = JornadaTrabalhoPCAForm


admin.site.register(JornadaTrabalhoPCA, JornadaTrabalhoPCAAdmin)


class RegimeJuridicoPCAAdmin(ModelAdminPlus):
    form = RegimeJuridicoPCAForm
    list_display = ('pca', 'regime_juridico', 'data_inicio_regime_juridico_pca', 'data_fim_regime_juridico_pca')
    list_display_icons = True
    list_filter = ('pca__servidor',)


admin.site.register(RegimeJuridicoPCA, RegimeJuridicoPCAAdmin)


class AreaConhecimentoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'superior')
    ordering = ('superior__descricao', 'descricao')
    search_fields = AreaConhecimento.SEARCH_FIELDS
    list_display_icons = True
    list_filter = ('superior',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(superior__isnull=False)


admin.site.register(AreaConhecimento, AreaConhecimentoAdmin)


class AfastamentoSiapeAdmin(ModelAdminPlus):
    list_display = (
        'codigo',
        'sigla',
        'nome',
        'tipo',
        'interrompe_pagamento',
        'interrompe_tempo_servico',
        'suspende_estagio_probatorio',
        'excluido',
    )
    search_fields = ('codigo', 'sigla', 'nome')
    list_display_icons = True
    list_filter = ('tipo', 'interrompe_pagamento', 'interrompe_tempo_servico', 'suspende_estagio_probatorio', 'excluido')


admin.site.register(AfastamentoSiape, AfastamentoSiapeAdmin)


class ServidorAfastamentoSiapeAdmin(ModelAdminPlus):
    list_display = (
        'servidor',
        'afastamento',
        'data_inicio',
        'data_termino',
        'qtd_minuto_afastamento',
        'quantidade_dias_afastamento',
        'tem_efeito_financeiro',
        'cancelado',
        'desconsiderar_regra_30_dias',
    )
    search_fields = (
        'servidor__pessoa_fisica__nome',
        'servidor__matricula',
        'afastamento__codigo',
        'afastamento__nome',
        'afastamento__sigla',
    )
    list_display_icons = True
    list_filter = (
        'cancelado',
        'afastamento__interrompe_pagamento',
        'tem_efeito_financeiro',
        'servidor__ativo',
        'afastamento',
    )

    def has_add_permission(self, request):
        return False

    form = ServidorAfastamentoSiapeForm


admin.site.register(ServidorAfastamento, ServidorAfastamentoSiapeAdmin)

########################
# Cronograma da Folha
########################


class CronogramaFolhaAdmin(ModelAdminPlus):
    list_display = (
        'get_mes_ano',
        'data_abertura_atualizacao_folha',
        'data_fechamento_processamento_folha',
        'data_consulta_previa_folha',
        'data_abertura_proxima_folha',
    )
    list_display_icons = True
    form = CronogramaFolhaForm

    def get_mes_ano(self, obj):
        return f'{Meses.get_mes(obj.mes)}/{obj.ano.ano}'

    get_mes_ano.short_description = 'Mês/Ano'


admin.site.register(CronogramaFolha, CronogramaFolhaAdmin)


class PessoaExternaAdmin(ModelAdminPlus):
    form = PessoaExternaForm
    search_fields = ('nome', 'cpf')
    list_display = ('nome', 'cpf', 'sexo', 'email')
    list_filter = ('sexo',)
    list_display_icons = True


admin.site.register(PessoaExterna, PessoaExternaAdmin)


#####################################
# Modelo usado em Progressões
#####################################


class PadraoVencimentoAdmin(ModelAdminPlus):
    list_display = ('categoria', 'classe', 'posicao_vertical')
    list_filter = ('categoria', 'classe')
    list_display_icons = True


admin.site.register(PadraoVencimento, PadraoVencimentoAdmin)


class ExcecaoDadosAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('servidor', 'tipo_extracao', 'get_campos')
    search_fields = ('servidor__pessoa_fisica__nome',)
    form = ExcecaoDadoForm

    def get_campos(self, obj):
        return list(obj.campos.all())

    get_campos.short_description = 'Campos que serão ignorados na atualização via webservice'


admin.site.register(ExcecaoDado, ExcecaoDadosAdmin)


class CampoExcecaoDadosAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('campo',)


admin.site.register(CampoExcecao, CampoExcecaoDadosAdmin)


###############################################
# Solicitação de Alteração de Foto Servidor
###############################################
class SolicitacaoAlteracaoFotoAdmin(ModelAdminPlus):
    list_display = ('get_foto', 'get_dados_solicitante', 'data_interacao', 'responsavel_interacao', 'get_situacao', 'motivo_rejeicao')
    search_fields = tuple(SolicitacaoAlteracaoFoto.SEARCH_FIELDS)
    list_display_icons = True
    form = SolicitacaoAlteracaoFotoForm
    actions = ('validar_em_lote',)
    list_filter = (CustomTabListFilter, 'solicitante__setor__uo')
    show_count_on_tabs = True

    fieldsets = (
        (
            '',
            {
                'fields': (
                    'foto',
                    'descricao',
                )
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        meus_fieldsets = self.fieldsets
        if request.user.has_perm('rh.eh_rh_sistemico') or request.user.has_perm('rh.eh_rh_campus'):
            meus_fieldsets = (*self.fieldsets, ('Para Gestão de Pessoas', {'fields': ('solicitante',)}))
        return meus_fieldsets

    def get_dados_solicitante(self, obj):
        out = '<dl>'
        out += f'<dt>Solicitante:</dt><dd>{obj.solicitante!s}</dd>'
        if obj.solicitante.email_institucional:
            out += f'<dt>E-mail:</dt><dd>{obj.solicitante.email_institucional!s}</dd>'
        if obj.solicitante.situacao:
            out += f'<dt>Situação:</dt><dd>{obj.solicitante.situacao}</dd>'
        if obj.solicitante.setor:
            out += f'<dt>Setor:</dt><dd>{obj.solicitante.setor!s}</dd>'
        if obj.descricao:
            out += f'<dt>Solicitação:</dt><dd>{obj.descricao!s}</dd>'
        out += '</dl>'
        return mark_safe(out)

    get_dados_solicitante.short_description = 'Solicitante'
    get_dados_solicitante.admin_order_field = 'solicitante'

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'
    get_situacao.admin_order_field = 'situacao'

    def get_validacao(self, obj):
        out = '<dl>'
        if obj.motivo_rejeicao:
            out += f'<dt>Motivo da Rejeição:</dt><dd>{obj.motivo_rejeicao!s}</dd>'
        if obj.data_interacao:
            out += f'<dt>Data da Interação:</dt><dd>{obj.data_interacao.strftime("%d/%m/%Y %H:%M")}</dd>'
        if obj.responsavel_interacao:
            out += f'<dt>Responsável pela Interação:</dt><dd>{obj.responsavel_interacao!s}</dd>'
        out += '</dl>'
        return mark_safe(out)

    get_validacao.short_description = 'Validação'
    get_validacao.admin_order_field = 'data_interacao'

    def has_add_permission(self, request):
        has_permission = super().has_add_permission(request)
        if has_permission:
            has_permission = SolicitacaoAlteracaoFoto.pode_solicitar_alteracao_foto(request.user)
        return has_permission

    def add_view(self, request, form_url='', extra_context=None):
        # só é permitido solicitar alterações de imagem:
        # - se superuser -> sempre
        # - se usuário comum -> se não hover outra solicitação para o mesmo usuário com a situacao "aguardando validação"
        if not request.user.is_superuser:
            tem_solicitacoes_pendentes = SolicitacaoAlteracaoFoto.get_solicitacoes_pendentes(request.user).exists()
            if tem_solicitacoes_pendentes:
                return httprr('/admin/rh/solicitacaoalteracaofoto/', 'Não é possível adicionar enquanto houver solicitações pendentes.', 'error')
        return super().add_view(request, form_url=form_url, extra_context=extra_context)

    def response_add(self, request, obj):
        return httprr('/admin/rh/solicitacaoalteracaofoto/', 'A solicitação de alteração de foto foi encaminhada para o setor de Gestão de Pessoas.')

    def tab_aguardando_validacao(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO)

    tab_aguardando_validacao.short_description = 'Aguardando Validação'

    def tab_validado(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAlteracaoFoto.VALIDADA)

    tab_validado.short_description = 'Validado'

    def tab_rejeitado(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAlteracaoFoto.REJEITADA)

    tab_rejeitado.short_description = 'Rejeitado'

    def get_tabs(self, request):
        return ['tab_aguardando_validacao', 'tab_validado', 'tab_rejeitado']

    def show_list_display_icons(self, obj):
        out = []
        out.append(icon('view', obj.get_absolute_url()))
        if obj.situacao == SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO:
            out.append(icon('edit', f'/admin/rh/solicitacaoalteracaofoto/{obj.id}/'))
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = '#'

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if SolicitacaoAlteracaoFoto.pode_analisar(request.user):
            list_display = (*list_display, 'get_acoes')
        return list_display

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('rh.eh_rh_sistemico') and not request.user.has_perm('rh.eh_rh_campus'):
            del actions['validar_em_lote']
        return actions

    def get_acoes(self, obj):
        if obj.situacao == SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO:
            html = f"""
            <ul class="action-bar">
                <li><a class="btn success confirm" href="/rh/validaralteracaofoto/{obj.id}/">Validar</a></li>
                <li><a class="btn danger popup no-confirm" href="/rh/rejeitaralteracaofoto/{obj.id}/">Rejeitar</a></li>
            </ul>
            """
            return mark_safe(html)
        return ''

    get_acoes.short_description = 'Ações'

    def validar_em_lote(self, request, queryset):
        try:
            if request.user.has_perm('rh.eh_rh_sistemico') or request.user.has_perm('rh.eh_rh_campus'):
                ids = request.POST.getlist('_selected_action')
                if ids:
                    ids = list(map(int, ids))
                qs_solicitacoes = queryset.filter(id__in=ids, situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO)
                if qs_solicitacoes.exists():
                    for solicitacao in qs_solicitacoes:
                        solicitacao.validar(request.user)
                    messages.success(request, 'Solicitações validadas com sucesso.')
        except Exception as ex:
            messages.error(request, ex)

    validar_em_lote.short_description = 'Validar em lote'

    def get_queryset(self, request):
        return SolicitacaoAlteracaoFoto.visiveis(request.user)

    def get_foto(self, obj):
        img_src = obj.foto.url
        return mark_safe(f'<div class="photo-circle"><img src="{img_src}" alt="{obj.__str__()}" /></div>')

    get_foto.short_description = 'Foto'


admin.site.register(SolicitacaoAlteracaoFoto, SolicitacaoAlteracaoFotoAdmin)


class AfastamentoSiapeEfetivoExercicioAdmin(ModelAdminPlus):
    search_fields = AfastamentoSiapeEfetivoExercicio.SEARCH_FIELDS
    list_display = ('dias_efetivo_exercicio', 'get_afastamentos', 'get_situacao')
    list_display_icons = True

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'
    get_situacao.admin_order_field = 'situacao'

    def get_afastamentos(self, obj):
        html = '<ul>'
        for i in obj.afastamentos.all():
            html += f'<li>{i}</li>'
        html += '</ul>'
        return mark_safe(html)

    get_afastamentos.short_description = 'Afastamentos'


admin.site.register(AfastamentoSiapeEfetivoExercicio, AfastamentoSiapeEfetivoExercicioAdmin)


class IndicadoresPublicosAdmin(ModelAdminPlus):
    list_display = ('titulo', 'render_to', 'liberar_area_publica')
    list_filter = ('titulo', 'render_to')
    list_display_icons = True
    actions = ('liberar', 'bloquear')

    def liberar(self, request, queryset):
        self._action(request, queryset, True, 'Gráficos liberados com sucesso.')

    liberar.short_description = 'Liberar gráfico na área pública'

    def bloquear(self, request, queryset):
        self._action(request, queryset, False, 'Gráficos bloqueados com sucesso.')

    bloquear.short_description = 'Bloquear gráfico na área pública'

    def _action(self, request, queryset, booleado, msg):
        try:
            if request.user.has_perm('rh.eh_rh_sistemico'):
                ids = request.POST.getlist('_selected_action')
                if ids:
                    ids = list(map(int, ids))
                qs = queryset.filter(id__in=ids)
                if qs.exists():
                    for i in qs:
                        i.liberar_area_publica = booleado
                        i.save()
                    messages.success(request, msg)
        except Exception as ex:
            messages.error(request, ex)


admin.site.register(IndicadoresPublicos, IndicadoresPublicosAdmin)


class FormaProvimentoVacanciaAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao')
    search_fields = ('descricao', 'codigo')
    list_display_icons = True


admin.site.register(FormaProvimentoVacancia, FormaProvimentoVacanciaAdmin)


class PessoaInfoComplementarAdmin(ModelAdminPlus):
    list_display = ('pessoa', 'api_origem', 'data_hora_consulta', 'informacoes')
    search_fields = ('pessoa__nome', 'pessoa__pessoafisica__cpf', 'informacoes', 'pessoa__pessoajuridica__cnpj')
    list_filter = ('api_origem', 'data_hora_consulta')
    list_display_icons = True

    def get_urls(self):
        return [
            path('historico-acessos/', self.admin_site.admin_view(self.historico_acessos_view), name='rh_pessoainfocomplementar_historico_acessos'),
            *super().get_urls(),
        ]

    def get_action_bar(self, request, remove_add_button=False):
        items = super().get_action_bar(request, remove_add_button=remove_add_button)
        items.append({'url': 'historico-acessos/', 'label': 'Ver histórico de acessos'})
        return items

    def _registrar_visualizacao_changelist(self, request):
        content_type = ContentType.objects.get_for_model(PessoaInfoComplementar)
        mensagem_log = 'Visualizou a listagem de informações complementares.'
        filtro_logs = LogEntry.objects.filter(
            content_type_id=content_type.id,
            user_id=request.user.id,
            change_message=mensagem_log,
        )
        ultimo_log = filtro_logs.order_by('-action_time').first()
        if ultimo_log:
            intervalo = timezone.now() - ultimo_log.action_time
            if intervalo < datetime.timedelta(minutes=20):
                return

        LogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=content_type.id,
            object_id='0',
            object_repr='Lista de Informações Complementares de Pessoa',
            action_flag=CHANGE,
            change_message=mensagem_log,
        )

    def changelist_view(self, request: HttpRequest, extra_context: dict | None = None) -> HttpResponse:
        if not request.session.get('2fa'):
            response = solicitar_autenticacao_2fa(request, request.get_full_path())
            if response:
                return response

        self._registrar_visualizacao_changelist(request)
        return super().changelist_view(request, extra_context=extra_context)

    def historico_acessos_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied

        content_type = ContentType.objects.get_for_model(PessoaInfoComplementar)
        mensagem_log = 'Visualizou a listagem de informações complementares.'
        logs = LogEntry.objects.filter(content_type_id=content_type.id, change_message=mensagem_log).select_related('user').order_by('-action_time')
        title = 'Histórico de acessos'
        return render(request, 'rh/admin/pessoainfocomplementar_historico_acessos.html', {'logs': logs, 'title': title})


admin.site.register(PessoaInfoComplementar, PessoaInfoComplementarAdmin)


@admin.register(AlertaGestaoPessoa)
class AlertaGestaoPessoaAdmin(ModelAdminPlus):
    list_display = ('vinculo_analizar', 'tipo_acao', 'data_acao', 'registro_afetado')
    search_fields = ('vinculo_analizar__search',)
    list_filter = ('tipo_acao',)
    list_display_icons = True

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        setor_rh_pk = Configuracao.get_valor_por_chave('rh', 'setor_rh')
        setor = Setor.objects.suap_ativos().filter(pk=setor_rh_pk or 0).first()
        if setor and request.user.get_relacionamento() in setor.chefes:
            return True
        return super().has_change_permission(request, obj)


@admin.register(AlertaGestaoPessoaVisualizacao)
class AlertaGestaoPessoaVisualizacaoAdmin(ModelAdminPlus):
    list_display = (
        'alerta_visualizado',
        'vinculo',
        'data_visualizacao',
    )
    search_fields = ('vinculo__search', 'alerta_visualizado__vinculo_analizar__search')
    list_display_icons = True

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModalidadePGD)
class ModalidadePGDAdmin(ModelAdminPlus):
    list_display = ('nome',)
    search_fields = ModalidadePGD.SEARCH_FIELDS
    list_display_icons = True

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
