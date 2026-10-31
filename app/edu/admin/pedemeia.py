from django.contrib import admin
from django.utils.safestring import mark_safe

from comum.models import APIExterna
from djtools.contrib.admin import ModelAdminPlus
from edu.models import Aluno, Modalidade, RelatoInconsistenciaPeDeMeia, SituacaoMatricula
from edu.models.pedemeia import OperacaoPeDeMeia, RequisicaoPeDeMeia, TransmissaoFrequenciaPeDeMeia, TransmissaoPeDeMeia


class OperacaoPeDeMeiaAdmin(ModelAdminPlus):
    search_fields = ('observacao',)
    list_display = ('tipo', 'ano', 'mes', 'data', 'observacao', 'get_lotes')
    date_hierarchy = 'data'
    list_filter = ('tipo',)
    list_display_icons = True
    fields = ('observacao',)

    def get_lotes(self, obj):
        ul = []
        ul.append('<ul>')
        for id, uuid in obj.lote_set.values_list('id', 'uuid'):
            ul.append(f'<li><a target="_blank" href="/edu/lote_pedemeia/{id}/">{uuid}</a></li>')
        ul.append('</ul>')
        return mark_safe(''.join(ul))

    get_lotes.short_description = 'Lotes'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_action_bar(self, request, remove_add_button=False):
        actions = super().get_action_bar(request, remove_add_button)
        actions.append({'url': '/edu/consultar_codigo_sgp/', 'label': 'Consultar Código SGP', 'css_class': 'default popup'})
        actions.append({'url': '/edu/calcular_frequencia_pedemeia/', 'label': 'Calcular Frequência Mensal', 'css_class': 'primary'})
        actions.append({'url': '/edu/cadastrar_operacao_pedemeia/', 'label': 'Cadastrar Operação', 'css_class': 'success'})
        return actions


admin.site.register(OperacaoPeDeMeia, OperacaoPeDeMeiaAdmin)


class RelatoInconsistenciaPeDeMeiaAdmin(ModelAdminPlus):
    search_fields = 'aluno__pessoa_fisica__nome_registro', 'aluno__pessoa_fisica__cpf', 'aluno__matricula'
    list_display = (
        'aluno',
        'data',
        'descricao',
        'resolvido',
    )
    date_hierarchy = 'data'
    list_filter = ('resolvido',)
    list_display_icons = True
    export_to_xls = True
    actions = ['marcar_como_resolvido']

    def marcar_como_resolvido(self, request, queryset):
        queryset.update(resolvido=True)
        self.message_user(request, 'Ação realizada com sucesso')


admin.site.register(RelatoInconsistenciaPeDeMeia, RelatoInconsistenciaPeDeMeiaAdmin)


class RequisicaoPeDeMeiaAdmin(ModelAdminPlus):
    search_fields = 'aluno__pessoa_fisica__nome_registro', 'aluno__pessoa_fisica__cpf', 'aluno__matricula', 'json_retorno'
    list_display = 'aluno', 'data', 'processada', 'get_campus', 'tipo', 'json_retorno'
    list_filter = 'data', 'mes', 'ano', 'processada', 'tipo'
    list_display_icons = True
    export_to_xls = True
    actions = ['enviar_requisicoes_cadastro', 'enviar_requisicoes_atualizacao_de_cadastro']

    def enviar_requisicoes_cadastro(self, request, queryset):
        qtd_cadastrado = 0
        qtd_falhas = 0
        api_externa_pedemeia = APIExterna.PEDEMEIA
        if api_externa_pedemeia.ativo:
            api_service = api_externa_pedemeia.get_service()
            for requisicao in queryset:
                if not requisicao.processada:
                    cadastrado, _status_code = api_service.cadastrar_estudante(requisicao.aluno)
                    if cadastrado:
                        qtd_cadastrado += 1
                    else:
                        qtd_falhas += 1
            self.message_user(request, f'{qtd_cadastrado} Alunos cadastrados com sucesso. {qtd_falhas} com erro no envio!')
        else:
            self.message_user(request, 'A integração com a API do Pé de Meia está desativada.', level='error')

    enviar_requisicoes_cadastro.short_description = 'Cadastrar Alunos no Pé de Meia'

    def enviar_requisicoes_atualizacao_de_cadastro(self, request, queryset):
        qtd_atualizado = 0
        qtd_falhas = 0
        api_externa_pedemeia = APIExterna.PEDEMEIA
        if api_externa_pedemeia.ativo:
            api_service = api_externa_pedemeia.get_service()
            for requisicao in queryset:
                if (requisicao.tipo == RequisicaoPeDeMeia.CADASTRO and requisicao.processada) or (requisicao.tipo == RequisicaoPeDeMeia.ATUALIZACAO):
                    atualizado, _status_code = api_service.atualizar_estudante(requisicao.aluno)
                    if atualizado:
                        qtd_atualizado += 1
                    else:
                        qtd_falhas += 1
            self.message_user(request, f'{qtd_atualizado} Alunos atualizados com sucesso. {qtd_falhas} com erro!')
        else:
            self.message_user(request, 'A integração com a API do Pé de Meia está desativada.', level='error')

    enviar_requisicoes_atualizacao_de_cadastro.short_description = 'Atualizar Alunos no Pé de Meia'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'aluno':
            # Filtrar o queryset para mostrar apenas alunos não cadastrados no pé de meia
            kwargs['queryset'] = (
                Aluno.objects.filter(matriz__isnull=False, situacao=SituacaoMatricula.MATRICULADO, curso_campus__modalidade=Modalidade.INTEGRADO)
                .select_related('curso_campus__diretoria__setor__uo')
                .exclude(requisicaopedemeia__tipo=RequisicaoPeDeMeia.CADASTRO, requisicaopedemeia__processada=True)
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_campus(self, obj):
        return obj.aluno.curso_campus.diretoria.setor.uo

    get_campus.short_description = 'Campus'

    def has_add_permission(self, request):
        return False


admin.site.register(RequisicaoPeDeMeia, RequisicaoPeDeMeiaAdmin)


class TransmissaoFrequenciaPeDeMeiaInline(admin.TabularInline):
    model = TransmissaoFrequenciaPeDeMeia
    extra = 1
    fields = 'transmissao', 'tipo', 'ano', 'mes'


class TransmissaoPeDeMeiaAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = 'ano_letivo', 'periodo_letivo', 'descricao', 'data_inicio_janela_transmissao', 'data_termino_janela_transmissao'
    list_filter = (
        'ano_letivo',
        'periodo_letivo',
        'modalidades',
    )
    list_display_icons = True
    export_to_xls = True
    fields = 'descricao', 'modalidades', 'data_inicio_janela_transmissao', 'data_termino_janela_transmissao'
    inlines = (TransmissaoFrequenciaPeDeMeiaInline,)


admin.site.register(TransmissaoPeDeMeia, TransmissaoPeDeMeiaAdmin)
