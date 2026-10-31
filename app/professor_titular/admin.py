from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.utils.safestring import SafeString, mark_safe

from comum.models import Ano
from djtools.contrib.admin import CustomTabListFilter, DateRangeListFilter, ModelAdminPlus
from djtools.templatetags.tags import icon
from djtools.utils import httprr
from professor_titular.forms import AvaliacaoForm, ProcessoAvaliadorForm, ProcessoProfessorTitularForm
from professor_titular.models import (
    Arquivo,
    ArquivosExigidos,
    Avaliacao,
    CategoriaMemorialDescritivo,
    Criterio,
    Grupo,
    Indicador,
    PontuacaoMinima,
    ProcessoAvaliador,
    ProcessoTitular,
    Unidade,
    ConfiguracaoTitular,
)


class UnidadeAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla')


admin.site.register(Unidade, UnidadeAdmin)


class GrupoTitularAdmin(ModelAdminPlus):
    list_display = ('nome', 'percentual')


admin.site.register(Grupo, GrupoTitularAdmin)


class PontuacaoMinimaTitularAdmin(ModelAdminPlus):
    list_display = ('ano', 'grupo', 'pontuacao_exigida', 'qtd_minima_grupos')


admin.site.register(PontuacaoMinima, PontuacaoMinimaTitularAdmin)


class IndicadorAdmin(ModelAdminPlus):
    list_display = ('grupo', 'nome', 'descricao')


admin.site.register(Indicador, IndicadorAdmin)


class CriterioAdmin(ModelAdminPlus):
    list_display = ('indicador', 'artigo', 'nome', 'descricao', 'status', 'pontos', 'unidade', 'categoria_memorial_descritivo')


admin.site.register(Criterio, CriterioAdmin)


class CategoriaMemorialDescritivoAdmin(ModelAdminPlus):
    list_display = ('nome',)


admin.site.register(CategoriaMemorialDescritivo, CategoriaMemorialDescritivoAdmin)


class AvaliacaoAdmin(ModelAdminPlus):
    list_display = ('processo', 'avaliador', 'get_status')
    search_fields = ('processo__servidor__matricula', 'processo__servidor__pessoa_fisica__nome', 'avaliador__vinculo__pessoa__nome')
    list_display_icons = True
    form = AvaliacaoForm

    def get_status(self, obj):
        return mark_safe(obj.status_estilizado)

    get_status.short_description = 'Situação da Avaliação'


admin.site.register(Avaliacao, AvaliacaoAdmin)


class ProcessoTitularAdmin(ModelAdminPlus):
    list_display = (
        'opcoes',
        'servidor',
        'get_numero',
        'get_pontuacao_media_final',
        'get_data_processo',
        'status_estilizado',
        'botao_imprimir',
        'get_acoes',
    )
    list_filter = (CustomTabListFilter,)
    list_display_icons = False
    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')
    form = ProcessoProfessorTitularForm
    show_count_on_tabs = True
    export_to_xls = True

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        """
        se a pessoa não tiver a permissão "pode_validar_processotitular" filtra apenas os próprios processos
        pois não é um membro da CPPD
        """
        if not request.user.has_perm('professor_titular.pode_validar_processotitular'):
            queryset = queryset.filter(servidor_id=request.user.get_relacionamento().id)

        """
        se for um membro da CPPD (tiver a permissão pode_validar_processotitular) irá filtrar apenas os processos que não estejam
        com o avaliado e também trará os próprios processos
        """
        if request.user.has_perm('professor_titular.pode_validar_processotitular'):
            queryset = queryset.exclude(
                status__in=[ProcessoTitular.STATUS_AGUARDANDO_AJUSTES_USUARIO, ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD]
            ) | queryset.filter(servidor_id=request.user.get_relacionamento().id)

        if not request.user.has_perm('professor_titular.pode_avaliar_processotitular') and not request.user.has_perm(
            'professor_titular.pode_validar_processotitular'
        ):
            queryset = queryset.filter(servidor_id=request.user.get_relacionamento().id)

        return queryset

    def get_list_display(self, request):
        default_list_display = super().get_list_display(request)
        if request.GET.get('tab') == 'tab_processos_finalizados':
            coluna_pagamento = ('get_situacao_pagamento',)
            nova_list_display = default_list_display + coluna_pagamento
            return nova_list_display
        return default_list_display

    def get_situacao_pagamento(self, obj):
        avaliacoes = obj.avaliacao_set.filter(status__in=[Avaliacao.FINALIZADA])
        qtd_pagas = avaliacoes.filter(avaliacao_paga=True).count()
        qtd_nao_pagas = avaliacoes.filter(avaliacao_paga=False).count()
        if qtd_nao_pagas == 0:
            situacao = 'Todas as Avaliações foram pagas.'
            class_css = 'status-success'
        else:
            situacao = f'Avaliações Pagas: {qtd_pagas} <br /> Avaliações Não Pagas: {qtd_nao_pagas}'
            class_css = 'status-info'
        return mark_safe(f'<span class="status {class_css} text-nowrap-normal">{situacao}</span>')

    get_situacao_pagamento.short_description = 'Situação dos Pagamentos'

    def get_data_processo(self, obj):
        retorno = ''
        if obj.processo_eletronico:
            retorno = obj.processo_eletronico.data_hora_criacao
        elif obj.protocolo:
            retorno = obj.protocolo.data_cadastro
        return retorno

    get_data_processo.short_description = 'Data Processo'

    def get_numero(self, obj):
        if obj.protocolo:
            return mark_safe(f'<a href="/protocolo/processo/{obj.protocolo.id}/" class="popup">{obj.protocolo.numero_processo}</a>')
        elif obj.processo_eletronico:
            return mark_safe(f'<a href="/processo_eletronico/processo/{obj.processo_eletronico.id}/" class="popup">{obj.processo_eletronico}</a>')
        return None

    get_numero.admin_order_field = 'protocolo__numero_processo'
    get_numero.short_description = 'Número do Processo'

    def get_pontuacao_media_final(self, obj):
        return mark_safe(f'{obj.pontuacao_media_final():.2f}')

    get_pontuacao_media_final.short_description = 'Pontuação Validada'

    def get_tabs(self, request):
        result = ['tab_meus_processos']
        if request.user.has_perm('professor_titular.pode_validar_processotitular'):
            result.append('tab_processos_rejeitados')
            result.append('tab_processos_pendentes')
            result.append('tab_processos_validados')
            result.append('tab_processos_em_avaliacao')
            result.append('tab_aguardando_ciencia')
            result.append('tab_processos_ciente_resultado')
            result.append('tab_processos_finalizados')
        return result

    def tab_meus_processos(self, request, queryset):
        return queryset.filter(servidor__vinculos__user=request.user)

    tab_meus_processos.short_description = 'Meus Processos'

    def tab_processos_rejeitados(self, request, queryset):
        if not request.user.has_perm('professor_titular.pode_validar_processotitular'):
            queryset = queryset.filter(servidor__vinculos__user=request.user)
        return queryset.filter(status=ProcessoTitular.STATUS_REJEITADO)

    tab_processos_rejeitados.short_description = 'Processos Rejeitados'

    def tab_processos_pendentes(self, request, queryset):
        if not request.user.has_perm('professor_titular.pode_validar_processotitular'):
            queryset = queryset.filter(servidor__vinculos__user=request.user)
        return queryset.filter(status__in=[ProcessoTitular.STATUS_AGUARDANDO_VALIDACAO_CPPD, ProcessoTitular.STATUS_AGUARDANDO_NOVA_VALIDACAO])

    tab_processos_pendentes.short_description = 'Processos pendentes'

    """
    Aba que mostra os processos já validados pela CPPD e que estão esperando a atribuição de avaliadores
    """

    def tab_processos_validados(self, request, queryset):
        return queryset.filter(status=ProcessoTitular.STATUS_AGUARDANDO_AVALIADORES)

    tab_processos_validados.short_description = 'Processos Validados'

    """
    Aba que mostra os processos que já tem avaliadores selecionados ou que já estão em avaliação
    Aba está renomeada para "Processos em análise" para melhor entendimento
    """

    def tab_processos_em_avaliacao(self, request, queryset):
        return queryset.filter(status__in=[ProcessoTitular.STATUS_EM_AVALIACAO, ProcessoTitular.STATUS_AGUARDANDO_ACEITE_AVALIADOR])

    tab_processos_em_avaliacao.short_description = 'Processos em Análise'

    """
    Aba que mostra os processos que estão aguardando a ciência do avaliado
    """

    def tab_aguardando_ciencia(self, request, queryset):
        return queryset.filter(status=ProcessoTitular.STATUS_AGUARDANDO_CIENCIA)

    tab_aguardando_ciencia.short_description = 'Aguardando Ciência'

    """
    Aba que mostra os processos que os avaliados deram ciência do resultado (avaliação finalizada)
    """

    def tab_processos_ciente_resultado(self, request, queryset):
        return queryset.filter(status=ProcessoTitular.STATUS_CIENTE_DO_RESULTADO)

    tab_processos_ciente_resultado.short_description = 'Processos Cientes de Resultado'

    """
    Aba que mostra os processos finalizados
    """

    def tab_processos_finalizados(self, request, queryset):
        return queryset.filter(status__in=[ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_REPROVADO])

    tab_processos_finalizados.short_description = 'Processos Finalizados'

    def status_estilizado(self, obj):
        return mark_safe(obj.status_estilizado)

    status_estilizado.admin_order_field = 'status'
    status_estilizado.short_description = 'Situação'

    def get_acoes(self, obj):
        html = '<ul class="action-bar">'
        if obj.pode_ser_validado() and self.request.user.has_perm('professor_titular.pode_validar_processotitular'):
            html += f'<li><a href="/professor_titular/validar_processo_titular/{obj.id}" class="btn success">Validar</a></li>'
        elif (
            obj.status in [ProcessoTitular.STATUS_REJEITADO, ProcessoTitular.STATUS_REPROVADO]
            and self.request.user.get_vinculo() == obj.servidor.get_vinculo()
        ):
            html += f'<li><a href="/professor_titular/clonar_processo_titular/{obj.pk:d}/" class="btn primary">Clonar</a></li>'
        elif obj.status in [ProcessoTitular.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoTitular.STATUS_EM_AVALIACAO]:
            html += f'<li><a href="/professor_titular/acompanhar_avaliacao/{obj.pk:d}/" class="btn popup success">Acompanhar Avaliação</a></li>'
        elif obj.status in [
            ProcessoTitular.STATUS_APROVADO,
            ProcessoTitular.STATUS_REPROVADO,
            ProcessoTitular.STATUS_AGUARDANDO_CIENCIA,
            ProcessoTitular.STATUS_CIENTE_DO_RESULTADO,
        ]:
            html += f'<li><a href="/professor_titular/acompanhar_avaliacao/{obj.pk:d}/" class="btn default">Visualizar Avaliação</a></li>'
        if obj.pode_selecionar_avaliadores() and self.request.user.has_perm(
            'professor_titular.change_indicador'
        ):  # testando uma permissão específica de membro CPPD
            html += f'<li><a href="/professor_titular/selecionar_avaliadores/{obj.pk:d}/" class="btn popup">Selecionar avaliadores</a></li>'
        if (
            obj.concorda_deferimento
            and obj.status == ProcessoTitular.STATUS_CIENTE_DO_RESULTADO
            and self.request.user.has_perm('professor_titular.pode_validar_processotitular')
        ):
            html += f'<li><a href="/professor_titular/finalizar_processo/{obj.pk:d}/" class="btn warning confirm">Finalizar Processo</a></li>'
        if obj.status != ProcessoTitular.STATUS_REJEITADO and self.request.user.has_perm('professor_titular.pode_validar_processotitular'):
            html += f'<li><a href="/professor_titular/rejeitar_processo_cppd/{obj.pk:d}/" class="btn danger no-confirm popup">Rejeitar</a></li>'
        html += '</ul>'
        return mark_safe(html)

    get_acoes.short_description = 'Opções'

    def botao_imprimir(self, obj: ProcessoTitular) -> SafeString:
        if obj.status != ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD:
            result = """<div class="dropdown" style="position:static">
                            <button class="btn btn-secondary dropdown-toggle" type="button" data-bs-toggle="menu" aria-expanded="false">
                                Documentos
                            </button>
                            <div class="dropdown-menu menu">"""
            # if obj.protocolo:
            #     result += (
            #         f""" <a class="dropdown-item menu-item" href="/professor_titular/processo_capa/{obj.id}/" target="_blank"> Capa do Processo </a>"""
            #     )

            result += f"""          <a class="dropdown-item menu-item" href="/professor_titular/requerimento_pdf/{obj.id}/" target="_blank"> Requerimento </a>
                                    <a class="dropdown-item menu-item" href="/professor_titular/relatorio_descritivo_pdf/{obj.id}" target="_blank"> Memorial Descritivo </a>
                                    <a class="dropdown-item menu-item" href="/professor_titular/formulario_pontuacao_pdf/{obj.id}/" target="_blank"> Formulário de Pontuação </a>
                                    <a class="dropdown-item menu-item" href="/professor_titular/documentos_anexados_pdf/{obj.id}/" target="_blank">Listagem dos Documentos Anexados </a>
                                    <a class="dropdown-item menu-item" href="/professor_titular/download_arquivos/{obj.id}/"> Downloads dos Arquivos </a>
                                    <a class="dropdown-item menu-item" href="/professor_titular/gerar_processo_completo/{obj.id}/"> Gerar Processo Completo </a>
                        """

            if obj.status in [ProcessoTitular.STATUS_APROVADO, ProcessoTitular.STATUS_CIENTE_DO_RESULTADO]:
                result += f"""<a class="dropdown-item menu-item" href="/professor_titular/imprimir_documentos_pdf/{obj.id}/" target="_blank"> Documentos para Impressão </a>"""
                result += f"""<a class="dropdown-item menu-item" href="/professor_titular/encaminhamento_banca_pdf/{obj.id}/" target="_blank"> Documento de Encaminhamento da Banca </a>"""

            result += """</div>
                    </div>"""

            return mark_safe(result)

        else:
            return mark_safe('<span class="status status-error">Não enviado</span>')

    botao_imprimir.short_description = 'Documentos'

    def has_add_permission(self, request):
        tem_permissao = super().has_add_permission(request)
        return tem_permissao and request.user.eh_docente

    def add_view(self, request):
        if self.has_add_permission(request):
            return httprr('/professor_titular/criar_processo_titular/')
        else:
            raise PermissionDenied('Você não tem permissão para acessar esta página!')

    def opcoes(self, obj):
        html = ''
        if (obj.avaliado_pode_editar() or obj.avaliado_pode_ajustar()) and self.request.user.get_relacionamento().id == obj.servidor.id:
            html += icon('edit', f'/professor_titular/abrir_processo_titular/{obj.id}/')
        else:
            html += icon('view', f'/professor_titular/abrir_processo_titular/{obj.id}/')

        if obj.avaliado_pode_editar() and self.request.user.get_relacionamento().id == obj.servidor.id:
            html += icon('delete', f'/professor_titular/excluir_processo_titular/{obj.id}/')

        return mark_safe(html)

    opcoes.short_description = 'Ações'

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Servidor', 'Número do Processo', 'Data do Processo', 'Pontuação Média Final', 'Situação']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            numero_processo = ''
            if obj.processo_eletronico:
                numero_processo = obj.processo_eletronico.data_hora_criacao
            elif obj.protocolo:
                numero_processo = obj.protocolo.data_cadastro
            row = [idx + 1, obj.servidor, numero_processo, self.get_data_processo(obj), self.get_pontuacao_media_final(obj), obj.get_status_display()]
            rows.append(row)
        return rows


admin.site.register(ProcessoTitular, ProcessoTitularAdmin)


class ProtocoloYearFilter(admin.SimpleListFilter):
    title = 'Ano do Protocolo'
    parameter_name = 'protocolo_year'

    def lookups(self, request, model_admin):
        return [[ano, ano] for ano in Ano.objects.all().values_list('ano', flat=True)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(processo__protocolo__data_cadastro__year=self.value()).distinct()


class ProcessoAvaliacaoAdmin(ModelAdminPlus):
    list_display = (
        'processo',
        'get_numero',
        'get_situacao_processo',
        'vinculo_responsavel_cadastro',
        'get_avaliador',
        'get_situacao_avaliador_processo',
        'get_situacao_avaliacao',
        'data_convite',
        'data_aceite',
        'get_data_conclusao_avaliacao',
    )
    list_display_icons = True
    list_filter = ('status', 'processo__status', ProtocoloYearFilter, ('data_aceite', DateRangeListFilter))
    search_fields = ('processo__servidor__matricula', 'processo__servidor__pessoa_fisica__nome', 'avaliador__vinculo__pessoa__nome')
    export_to_xls = True
    form = ProcessoAvaliadorForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Traga tudo que as colunas usam via select_related (FK/OneToOne)…
        qs = qs.select_related(
            'processo',
            'processo__protocolo',
            'processo__servidor',
            'processo__servidor__pessoa_fisica',
            'vinculo_responsavel_cadastro',
            'vinculo_responsavel_cadastro__pessoa',
            'avaliador',
            'avaliador__vinculo',
            'avaliador__vinculo__pessoa',
        )
        return qs

    def _get_avaliacao_correspondente_cached(self, obj):
        # Se você tem um método obj.avaliacao_correspondente() que faz query,
        # primeiro tente usar o cache do prefetch.
        if hasattr(obj, '_avaliacoes_cache') and obj._avaliacoes_cache:
            # se é 1-para-1, pegue a primeira
            return obj._avaliacoes_cache[0]
        # fallback para quem acessar direto a página de edição etc.
        if not hasattr(obj, '_avaliacao_corr'):
            obj._avaliacao_corr = obj.avaliacao_correspondente()
        return obj._avaliacao_corr

    def get_data_conclusao_avaliacao(self, obj):
        av = self._get_avaliacao_correspondente_cached(obj)
        return av.data_finalizacao if av else None

    get_data_conclusao_avaliacao.short_description = 'Data Conclusão Avaliação'

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.user.has_perm('professor_titular.delete_processoavaliador'):
            list_display = (*list_display, 'get_acao')
        return list_display

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Interessado',
            'Matrícula SIAPE',
            'Processo',
            'Data de entrada do processo',
            'Situação do Processo',
            'Responsável Cadastro do Avaliador',
            'Avaliador',
            'Matrícula SIAPE/CPF',
            'Data de Convite',
            'Data de Aceite',
            'Situação Avaliação',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.processo.servidor.pessoa_fisica.nome,
                obj.processo.servidor.matricula,
                obj.processo.protocolo.numero_processo if obj.processo.protocolo else '',
                obj.processo.protocolo.data_cadastro if obj.processo.protocolo else '',
                obj.processo.get_status_display(),
                obj.vinculo_responsavel_cadastro,
                obj.avaliador.vinculo.pessoa.nome,
                obj.avaliador.matricula_siape or obj.avaliador.vinculo.pessoa.pessoafisica.cpf,
                obj.data_convite,
                obj.data_aceite,
                obj.get_status_display(),
            ]
            rows.append(row)
        return rows

    def get_avaliador(self, obj):
        if obj.avaliador:
            return mark_safe(f'<a href="/rh/avaliador/{obj.avaliador.id}/" class="popup">{obj.avaliador}</a>')
        return ''

    get_avaliador.admin_order_field = 'avaliador'
    get_avaliador.short_description = 'Avaliador'

    def get_numero(self, obj):
        if obj.processo.protocolo:
            return mark_safe(f'<a href="/protocolo/processo/{obj.processo.protocolo.id}/" class="popup">{obj.processo.protocolo.numero_processo}</a>')
        return ''

    get_numero.admin_order_field = 'processo__protocolo__numero_processo'
    get_numero.short_description = 'Número do Processo'

    def get_situacao_avaliador_processo(self, obj):
        return mark_safe(obj.situacao_avaliador())

    get_situacao_avaliador_processo.admin_order_field = 'status'
    get_situacao_avaliador_processo.short_description = 'Situação'

    def get_situacao_processo(self, obj):
        return mark_safe(obj.processo.status_estilizado)

    get_situacao_processo.admin_order_field = 'processo__status'
    get_situacao_processo.short_description = 'Situação do Processo'

    def get_situacao_avaliacao(self, obj):
        av = self._get_avaliacao_correspondente_cached(obj)
        return mark_safe(av.status_estilizado) if av else ''

    get_situacao_avaliacao.short_description = 'Situação da Avaliação'

    def get_acao(self, obj):
        return mark_safe(
            f'<ul class="action-bar"><li><a class="btn danger no-confirm" href="/admin/professor_titular/processoavaliador/{obj.pk}/delete/">Apagar?</a></li></ul>'
        )

    get_acao.short_description = 'Ação'


admin.site.register(ProcessoAvaliador, ProcessoAvaliacaoAdmin)


class ArquivoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('processo', 'criterio', 'nome', 'diretorio', 'nota_pretendida', 'qtd_itens', 'data_referencia', 'tamanho', 'descricao')
    search_fields = ('processo__servidor__pessoa_fisica__nome',)


admin.site.register(Arquivo, ArquivoAdmin)


class ArquivosExigidosAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('processo', 'nome', 'tamanho', 'tipo')
    search_fields = ('processo__servidor__pessoa_fisica__nome',)


admin.site.register(ArquivosExigidos, ArquivosExigidosAdmin)


@admin.register(ConfiguracaoTitular)
class ConfiguracaoTitularAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'descricao',
        'dias_para_aceite',
        'dias_para_avaliacao',
    )

    def has_add_permission(self, request):
        return not ConfiguracaoTitular.objects.exists()
