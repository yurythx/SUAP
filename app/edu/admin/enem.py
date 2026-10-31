from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import CadastrarSolicitacaoCertificadoENEMForm, ConfiguracaoCertificadoENEMForm, RegistroEmissaoCertificadoENEMForm
from edu.models import ConfiguracaoCertificadoENEM, RegistroEmissaoCertificadoENEM, SolicitacaoCertificadoENEM


class ConfiguracaoCertificadoENEMAdmin(ModelAdminPlus):
    list_filter = ('ano',)
    list_display = ('ano', 'data_primeira_prova', 'numero_portaria', 'get_total_registros_alunos')
    list_display_icons = True
    ordering = ('ano',)
    form = ConfiguracaoCertificadoENEMForm

    def get_total_registros_alunos(self, obj):
        return obj.registroalunoinep_set.all().count()

    get_total_registros_alunos.short_description = 'Nº de pedidos de certificados ENEM na Planilha do INEP'


admin.site.register(ConfiguracaoCertificadoENEM, ConfiguracaoCertificadoENEMAdmin)


class RegistroEmissaoCertificadoENEMAdmin(ModelAdminPlus):
    list_display = ('id', 'get_solicitante', 'get_edicao_enem', 'livro', 'numero_registro', 'data_expedicao', 'via', 'cancelado')
    search_fields = ('id', 'solicitacao__nome', 'solicitacao__email', 'solicitacao__cpf', 'livro', 'folha', 'numero_registro', 'data_expedicao')
    list_filter = ('cancelado', 'solicitacao__configuracao_certificado_enem__ano')
    list_display_icons = True
    list_per_page = 15
    date_hierarchy = 'data_expedicao'
    form = RegistroEmissaoCertificadoENEMForm

    def get_solicitante(self, obj):
        return f'{obj.solicitacao.nome} ({obj.solicitacao.cpf})'

    get_solicitante.short_description = 'Solicitante'

    def get_edicao_enem(self, obj):
        return obj.solicitacao.configuracao_certificado_enem.ano

    get_edicao_enem.short_description = 'Edição'


admin.site.register(RegistroEmissaoCertificadoENEM, RegistroEmissaoCertificadoENEMAdmin)


class SolicitacaoCertificadoENEMAdmin(ModelAdminPlus):
    export_to_xls = True
    list_filter = (CustomTabListFilter, 'configuracao_certificado_enem__ano', 'avaliador', 'tipo_certificado')
    list_display = (
        'nome',
        'cpf',
        'email',
        'configuracao_certificado_enem',
        'get_tipo_certificacao',
        'data_solicitacao',
        'get_data_primeira_prova',
        'get_acoes',
    )
    list_xls_display = ('nome', 'cpf', 'email', 'configuracao_certificado_enem', 'get_tipo_certificado_display', 'data_solicitacao', 'avaliador')
    list_display_icons = True
    search_fields = ('nome', 'cpf')
    ordering = ('nome', 'configuracao_certificado_enem__ano', 'data_solicitacao')
    date_hierarchy = 'data_solicitacao'
    form = CadastrarSolicitacaoCertificadoENEMForm
    fieldsets = CadastrarSolicitacaoCertificadoENEMForm.fieldsets

    def get_data_primeira_prova(self, obj):
        return obj.configuracao_certificado_enem.data_primeira_prova

    get_data_primeira_prova.short_description = 'Data da Primeira Prova'

    def get_tipo_certificacao(self, obj):
        return mark_safe(obj.get_tipo_certificacao(True))

    get_tipo_certificacao.short_description = 'Tipo de Certificado'

    def get_acoes(self, obj):
        lista = []
        if obj.data_avaliacao:
            if obj.avaliada:
                if not obj.razao_ressalva:
                    lista.append(
                        '<span class="status status-success">Atendida por {} em {}</span>'.format(
                            obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y')
                        )
                    )
                else:
                    lista.append(
                        '<span class="status status-success">Atendida com Ressalva por {} em {}</span>'.format(
                            obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y')
                        )
                    )

                if obj.registroemissaocertificadoenem_set.all().exists():
                    if obj.get_registro_emissao_certificado_enem().cancelado:
                        lista.append(
                            '<span class="status status-error">Certificado Cancelado por {} em {}</span>'.format(
                                obj.get_registro_emissao_certificado_enem().responsavel_cancelamento,
                                obj.get_registro_emissao_certificado_enem().data_cancelamento.strftime('%d/%m/%y'),
                            )
                        )

            else:
                lista.append(
                    '<span class="status status-error">Rejeitada por {} em {}</span>'.format(obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y'))
                )
        else:
            lista.append('<span class="status status-info">Não avaliada</span>')
        return mark_safe(' '.join(lista))

    get_acoes.short_description = 'Situação'

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_avaliadas']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=True)

    tab_pendentes.short_description = 'Pendentes'

    def tab_avaliadas(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=False)

    tab_avaliadas.short_description = 'Avaliadas'


admin.site.register(SolicitacaoCertificadoENEM, SolicitacaoCertificadoENEMAdmin)
