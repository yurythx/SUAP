from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from comum.models import UsuarioGrupoSetor
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group
from edu.forms import CertificadoDiplomaForm, RegistroEmissaoDiplomaForm
from edu.models import (
    AssinaturaDigital,
    AssinaturaEletronica,
    CertificadoDiploma,
    CodigoAutenticadorSistec,
    ConfiguracaoLivro,
    RegistroEmissaoDiploma,
    SolicitacaoAssinaturaEletronica,
)


class RegistroEmissaoDiplomaAdmin(ModelAdminPlus):
    list_display = (
        'aluno',
        'get_curso',
        'get_detalhe',
        'via',
        'get_situacao',
    )
    list_xls_display = (
        'id',
        'aluno',
        'get_curso',
        'data_expedicao',
        'data_registro',
        'get_livro',
        'folha',
        'numero_registro',
        'pasta',
        'via',
        'emissor',
        'cancelado',
    )
    search_fields = (
        'aluno__pessoa_fisica__nome_registro',
        'aluno__pessoa_fisica__nome_social',
        'aluno__matricula',
        'aluno__matriculaperiodo__turma__codigo',
        'pasta',
        'processo__numero_processo',
    )
    list_filter = (
        CustomTabListFilter,
        'sistema',
        'aluno',
        'aluno__curso_campus__diretoria__setor__uo',
        'aluno__curso_campus__diretoria',
        'aluno__curso_campus__modalidade',
        'livro',
        'aluno__curso_campus',
        'aluno__matriz__estrutura',
        'situacao',
    )
    list_display_icons = True
    export_to_xls = True
    list_per_page = 15
    date_hierarchy = 'data_expedicao'
    form = RegistroEmissaoDiplomaForm
    actions = ['imprimir_registros', 'gerar_diplomas', 'gerar_historicos', 'confirmar_assinatura_fisica', 'revogar_documentos']
    fieldsets = (('Dados gerais', {'fields': ('id', 'pasta', 'autenticacao_sistec')}),)

    def get_detalhe(self, obj):
        html = ['<dl>']
        html.append(f'<dt>Tipo:</dt><dd>{obj.get_tipo_display()}</dd>')
        html.append('<dt>Emissão:</dt><dd>{}</dd>'.format(obj.data_expedicao and obj.data_expedicao.strftime('%d/%m/%Y') or '-'))
        html.append(f'<dt>Emissor:</dt><dd>{obj.emissor}</dd>')
        html.append('<dt>Pasta:</dt><dd>{}</dd>'.format(obj.pasta or '-'))
        if obj.numero_registro:
            data_registro = obj.data_registro and obj.data_registro.strftime('%d/%m/%Y') or '-'
            html.append(f'<dt>Data do Registro:</dt><dd>{data_registro}</dd>')
            html.append(f'<dt>Número do Registro:</dt><dd>{obj.numero_registro}</dd>')
            html.append(f'<dt>Livro:</dt><dd>{obj.get_livro()}</dd>')
            html.append(f'<dt>Folha:</dt><dd>{obj.folha}</dd>')
        html.append('</dl>')
        return mark_safe(''.join(html))

    get_detalhe.short_description = 'Emissão e Registro'

    def get_tabs(self, request):
        return ['tab_assinados_manualmente', 'tab_assinados_eletronicamente', 'tab_assinados_digitalmente']

    def tab_assinados_manualmente(self, request, queryset):
        return queryset.exclude(configuracao_livro__descricao=ConfiguracaoLivro.NOME_LIVRO_ELETRONICO)

    tab_assinados_manualmente.short_description = 'Assinados Manualmente'

    def tab_assinados_eletronicamente(self, request, queryset):
        return queryset.filter(assinaturaeletronica__isnull=False, configuracao_livro__descricao=ConfiguracaoLivro.NOME_LIVRO_ELETRONICO)

    tab_assinados_eletronicamente.short_description = 'Assinados Eletronicamente (FIC, Técnicos e Pós)'

    def tab_assinados_digitalmente(self, request, queryset):
        return queryset.filter(assinaturadigital__isnull=False, configuracao_livro__descricao=ConfiguracaoLivro.NOME_LIVRO_ELETRONICO)

    tab_assinados_digitalmente.short_description = 'Assinados Eletronicamente (Graduação)'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            del actions['gerar_historicos']
            del actions['revogar_documentos']
        return actions

    def imprimir_registros(self, request, queryset):
        qs = queryset.values_list('id', flat=True)
        ids = []
        for pk in qs:
            ids.append(str(pk))
        url = '/edu/registrosemissaodiploma_pdf/{}/'.format('_'.join(ids))
        if qs.filter(numero_registro__isnull=True).exists():
            messages.error(request, 'Não é possível imprimir diplomas/certificados não registrados')
        else:
            return HttpResponseRedirect(url)

    imprimir_registros.short_description = 'Imprimir Registros Físicos'

    def gerar_diplomas(self, request, queryset):
        qs = queryset.values_list('id', flat=True)
        ids = []
        for pk in qs:
            ids.append(str(pk))

        erros = []
        if qs.filter(cancelado=True).exists():
            erros.append('Não é possível gerar diplomas/certificados de registros cancelados.')
        if qs.filter(assinaturaeletronica__isnull=False).exists():
            erros.append('Não é possível gerar diplomas/certificados com assinatura eletrônica existente.')
        if qs.filter(assinaturadigital__isnull=False).exists():
            erros.append('Não é possível gerar diplomas/certificados com assinatura digital existente.')
        if qs.filter(numero_registro__isnull=True).exists():
            erros.append('Não é possível imprimir diplomas/certificados não registrados.')

        if erros:
            for erro in erros:
                messages.error(request, erro)
        else:
            return HttpResponseRedirect('/edu/imprimir_diploma/{}/'.format('_'.join(ids)))

    gerar_diplomas.short_description = 'Gerar / Imprimir Diplomas'

    def confirmar_assinatura_fisica(self, request, queryset):
        queryset.filter(assinaturaeletronica__isnull=True, assinaturadigital__isnull=True).update(situacao=RegistroEmissaoDiploma.FINALIZADO)

    confirmar_assinatura_fisica.short_description = 'Confirmar Assinatura Física'

    def gerar_historicos(self, request, queryset):
        from edu.views import emitir_historico_final_eletronico_pdf, gerar_autenticacao_diploma_pdf

        contador = 0
        for obj in queryset:
            for assinatura_digital in obj.assinaturadigital_set.all():
                if assinatura_digital.registro_emissao_documento_historico_id is None:
                    registro_emissao_documento_historico = emitir_historico_final_eletronico_pdf(request, pk=str(obj.aluno.pk))
                    if isinstance(registro_emissao_documento_historico, HttpResponseRedirect):
                        continue
                    assinatura_digital.registro_emissao_documento_historico = registro_emissao_documento_historico
                    if assinatura_digital.registro_emissao_documento_diploma_id is None:
                        registro_emissao_documento_diploma = gerar_autenticacao_diploma_pdf(request, pk=obj.pk)
                        assinatura_digital.registro_emissao_documento_diploma = registro_emissao_documento_diploma
                    assinatura_digital.save()
                    contador += 1
        messages.success(request, f'{contador} histórico(s) gerado(s) com sucesso.')

    gerar_historicos.short_description = 'Gerar Históricos Eletrônicos'

    def revogar_documentos(self, request, queryset):
        from edu.diploma_digital.rap import AssinadorDigital

        assinador = AssinadorDigital()
        contador = 0
        for obj in queryset:
            for assinatura_digital in obj.assinaturadigital_set.all():
                if assinatura_digital.id_documentacao_academica_digital:
                    assinador.revogar_documento(assinatura_digital.id_documentacao_academica_digital)
                    contador += 1
                if assinatura_digital.id_dados_diploma_digital:
                    assinador.revogar_documento(assinatura_digital.id_dados_diploma_digital)
                    contador += 1
                if assinatura_digital.id_historico_escolar:
                    assinador.revogar_documento(assinatura_digital.id_historico_escolar)
                    contador += 1
                if assinatura_digital.id_representacao_diploma_digital:
                    assinador.revogar_documento(assinatura_digital.id_representacao_diploma_digital)
                    contador += 1
        messages.success(request, f'{contador} documentos revogados.')

    revogar_documentos.short_description = 'Revogar Documentos'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        return items

    def get_livro(self, obj):
        return obj.get_livro()

    get_livro.short_description = 'Livro'

    def get_curso(self, obj):
        html = [f'<p>{obj.aluno.curso_campus.descricao_historico}</p><br>']
        html.append('<dl>')
        if obj.tipo == RegistroEmissaoDiploma.TIPO_CERTIFICACAO_PARCIAL:
            html.append(f'<dt>Certificação parcial:</dt><dd>{obj.configuracao_certificacao_parcial.modalidade_certificacao}</dd>')
        html.append(f'<dt>Modalidade:</dt><dd>{obj.aluno.curso_campus.modalidade}</dd>')
        html.append(f'<dt>Campus:</dt><dd>{obj.aluno.curso_campus.diretoria.setor.uo}</dd>')
        html.append('</dl>')
        return mark_safe(''.join(html))

    get_curso.short_description = 'Curso'

    def get_situacao(self, obj):
        html = []
        html.append(
            f'<span class="status status-{obj.get_status_situacao()}">{obj.get_situacao_display()}</span>'
        ) if obj.situacao is not None else ''
        assinatura_eletronica = obj.is_eletronico() or obj.is_digital()
        if assinatura_eletronica and obj.situacao in (
            RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DIPLOMA,
            RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DOCUMENTACAO,
        ):
            html.append(
                f'<br /><ul class="action-bar"><li><a href="/edu/consultar_status_assinaturas/{obj.pk}/" class="btn default popup">Consultar Situação das Assinaturas</a></li></ul>'
            )
        return mark_safe(''.join(html))

    get_situacao.short_description = 'Situação'

    def get_queryset(self, request):
        return super().get_queryset(request, RegistroEmissaoDiploma.locals).distinct()

    def has_delete_permission(self, request, obj=None):
        if obj:
            return not obj.numero_formulario
        return True


admin.site.register(RegistroEmissaoDiploma, RegistroEmissaoDiplomaAdmin)


class AssinaturaEletronicaAdmin(ModelAdminPlus):
    list_filter = (
        CustomTabListFilter,
        'registro_emissao_diploma__aluno__curso_campus__diretoria',
        'registro_emissao_diploma__aluno__curso_campus__modalidade',
    )
    list_display = ('get_matricula', 'get_nome_aluno', 'get_curso_aluno', 'get_assinantes', 'get_situacao', 'get_acoes')
    search_fields = ('registro_emissao_diploma__aluno__matricula', 'registro_emissao_diploma__aluno__pessoa_fisica__nome')
    list_display_icons = True
    list_per_page = 10
    actions = 'assinar', 'excluir', 'revogar'

    def get_situacao(self, obj):
        if obj.data_revogacao:
            return mark_safe('<span class="status status-error">Solicitação Revogada</span>')
        if obj.data_assinatura:
            return mark_safe('<span class="status status-success">Concluída em {}</span>'.format(obj.data_assinatura.strftime('%d/%m/%Y')))
        else:
            return mark_safe('<span class="status status-alert">Em Andamento</span>')

    get_situacao.short_description = 'Situação'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab') == 'tab_pendentes_usuario':
            actions.pop('revogar')
            if not request.session.get('sessao_assinatura_eletronica'):
                actions.pop('assinar')
            if not in_group(request.user, 'Secretário Acadêmico'):
                actions.pop('excluir')
        elif request.GET.get('tab') == 'tab_assinadas':
            actions.pop('assinar')
            actions.pop('excluir')
            if not in_group(request.user, 'Diretor Geral, Diretor Acadêmico, Diretor de Ensino, Reitor'):
                actions.pop('revogar')
        else:
            actions.pop('assinar')
            actions.pop('excluir')
            actions.pop('revogar')
        return actions

    get_actions.short_description = 'Ações'

    def assinar(self, request, queryset):
        if (
            queryset.order_by('registro_emissao_diploma__aluno__curso_campus__modalidade_id')
            .values_list('registro_emissao_diploma__aluno__curso_campus__modalidade_id', flat=True)
            .distinct()
            .count()
            > 1
        ):
            messages.error(request, 'Por favor, selecione alunos de uma única modalidade de ensino.')
        else:
            qs = queryset.values_list('id', flat=True)
            ids = []
            for pk in qs:
                ids.append(str(pk))
            url = '/edu/assinar_diplomas_eletronicos/{}/'.format('_'.join(ids))
            return HttpResponseRedirect(url)

    assinar.short_description = 'Assinar Eletronicamente'

    def excluir(self, request, queryset):
        queryset.delete()
        messages.success(request, 'Assinaturas excluídas com sucesso.')

    excluir.short_description = 'Excluir Assinaturas'

    def revogar(self, request, queryset):
        qs = queryset.values_list('id', flat=True)
        ids = []
        for pk in qs:
            ids.append(str(pk))
        url = '/edu/revogar_assinatura_eletronica/{}/'.format('_'.join(ids))
        return HttpResponseRedirect(url)

    revogar.short_description = 'Revogar Assinaturas'

    def get_matricula(self, obj):
        return obj.get_matricula()

    get_matricula.short_description = 'Matrícula'

    def get_nome_aluno(self, obj):
        return obj.get_nome_aluno()

    get_nome_aluno.short_description = 'Nome'

    def get_curso_aluno(self, obj):
        return obj.get_curso_aluno()

    get_curso_aluno.short_description = 'Curso'

    def get_assinantes(self, obj):
        html = []
        html.append('<ul>')
        for solicitacao in obj.solicitacaoassinaturaeletronica_set.all():
            if solicitacao.data_assinatura:
                html.append(
                    '<li>{} <font style="color:green">{}</font></li>'.format(solicitacao.vinculo, solicitacao.data_assinatura.strftime('%d/%m/%Y'))
                )
            else:
                html.append(f'<li>{solicitacao.vinculo}Aguardando Assinatura</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_assinantes.short_description = 'Assinantes'

    def get_acoes(self, obj):
        html = []
        html.append('<ul class="action-bar">')
        if obj.registro_emissao_documento_historico:
            html.append('<li><a target="_blank" class="btn default" href="{}">Visualizar {}</a></li>'.format(obj.get_url_historico(), 'Histórico'))
        if obj.registro_emissao_documento_diploma:
            html.append('<li><a target="_blank" class="btn default" href="{}">Visualizar {}</a></li>'.format(obj.get_url_registro(), 'Registro'))
            html.append('<li><a target="_blank" class="btn default" href="{}">Visualizar {}</a></li>'.format(obj.get_url_diploma(), 'Diploma'))
        return mark_safe(''.join(html))

    get_acoes.short_description = 'Ações'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if in_group(request.user, ('Administrador Acadêmico', 'Reitor')):
            return qs

        if in_group(request.user, ('Coordenador de Registros Acadêmicos', 'Diretor Geral')):
            qs_filtrado_por_funcao = qs.filter(
                registro_emissao_diploma__aluno__curso_campus__diretoria__setor__uo=request.user.get_vinculo().setor.uo
            )
        elif in_group(request.user, 'Secretário Acadêmico'):
            setores = UsuarioGrupoSetor.objects.filter(
                usuario_grupo__user=request.user, usuario_grupo__group__name__in=('Secretário Acadêmico',)
            ).values_list('setor', flat=True)
            qs_filtrado_por_funcao = qs.filter(registro_emissao_diploma__aluno__curso_campus__diretoria__setor__in=setores)
        else:
            qs_filtrado_por_funcao = qs.none()

        return (qs_filtrado_por_funcao | qs.filter(solicitacaoassinaturaeletronica__vinculo__user=request.user)).distinct()

    def get_tabs(self, request):
        return ['tab_pendentes_usuario', 'tab_pendentes', 'tab_assinadas', 'tab_revogados']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(data_assinatura__isnull=True, data_revogacao__isnull=True)

    tab_pendentes.short_description = 'Pendentes de Assinatura'

    def tab_pendentes_usuario(self, request, queryset):
        ids = SolicitacaoAssinaturaEletronica.objects.filter(
            vinculo=request.user.get_vinculo(), data_assinatura__isnull=True, assinatura_eletronica__data_revogacao__isnull=True
        ).values_list('assinatura_eletronica', flat=True)
        return queryset.filter(id__in=ids)

    tab_pendentes_usuario.short_description = 'Pendentes de Minha Assinatura'

    def tab_assinadas(self, request, queryset):
        return queryset.filter(data_assinatura__isnull=False, data_revogacao__isnull=True)

    tab_assinadas.short_description = 'Assinadas'

    def tab_revogados(self, request, queryset):
        return queryset.filter(data_revogacao__isnull=False)

    tab_revogados.short_description = 'Revogados'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if in_group(request.user, 'Diretor Geral, Diretor Acadêmico, Diretor de Ensino, Reitor'):
            if request.session.get('sessao_assinatura_eletronica'):
                items.append({'url': '/edu/finalizar_sessao_assinatura_eletronica/', 'label': 'Finaliza Sessão de Assinatura'})
            else:
                items.append({'url': '/edu/iniciar_sessao_assinatura_eletronica/', 'label': 'Iniciar Sessão de Assinatura'})
        return items


admin.site.register(AssinaturaEletronica, AssinaturaEletronicaAdmin)


class CodigoAutenticadorSistecAdmin(ModelAdminPlus):
    list_display = 'cpf', 'codigo_unidade', 'codigo_curso', 'codigo_autenticacao'
    search_fields = ('cpf',)
    list_display_icons = True
    export_to_xls = True
    list_per_page = 15

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        items.append({'url': '/edu/importar_autenticacao_sistec/', 'label': 'Importar Autenticação SISTEC'})
        return items


admin.site.register(CodigoAutenticadorSistec, CodigoAutenticadorSistecAdmin)


class AssinaturaDigitalAdmin(ModelAdminPlus):
    list_filter = (
        CustomTabListFilter,
        'registro_emissao_diploma__aluno__curso_campus__diretoria',
        'registro_emissao_diploma__aluno__curso_campus__modalidade',
        'concluida',
    )
    list_display = ('get_matricula', 'get_nome_aluno', 'get_curso_aluno', 'get_situacao', 'get_acoes')
    search_fields = ('registro_emissao_diploma__aluno__matricula', 'registro_emissao_diploma__aluno__pessoa_fisica__nome')
    list_display_icons = True
    list_per_page = 10
    actions = ('sincronizar_assinatura_digital',)

    def get_action_bar(self, request, remove_add_button=False):
        return super().get_action_bar(request, remove_add_button=True)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab') == 'tab_pendentes':
            pass
        elif request.GET.get('tab') == 'tab_assinadas':
            actions.pop('sincronizar_assinatura_digital')
        else:
            actions.pop('sincronizar_assinatura_digital')
        return actions

    get_actions.short_description = 'Ações'

    def sincronizar_assinatura_digital(self, request, queryset):
        from edu.diploma_digital.rap import AssinadorDigital

        assinador = AssinadorDigital()
        for obj in queryset:
            assinador.sincronizar(obj)
        messages.success(request, 'Sincronização realizada com sucesso.')

    sincronizar_assinatura_digital.short_description = 'Sincronizar Assinatura'

    def get_matricula(self, obj):
        return obj.get_matricula()

    get_matricula.short_description = 'Matrícula'

    def get_nome_aluno(self, obj):
        return obj.get_nome_aluno()

    get_nome_aluno.short_description = 'Nome'

    def get_curso_aluno(self, obj):
        return obj.get_curso_aluno()

    get_curso_aluno.short_description = 'Curso'

    def get_situacao(self, obj):
        if obj.data_revogacao:
            return mark_safe('<span class="status status-error">Solicitação revogada</span>')
        if obj.concluida:
            return mark_safe('<span class="status status-success">Concluída</span>')
        else:
            return mark_safe('<span class="status status-alert">Em andamento</span>')

    get_situacao.short_description = 'Situação'

    def get_acoes(self, obj):
        html = []
        html.append('<ul class="action-bar">')
        html.append(
            f'<li><a class="btn default" href="/edu/registroemissaodiploma/{obj.registro_emissao_diploma_id}/" title="Visualizar Registro"><span class="fas fa-eye" aria-hidden="true"></span><span class="visually-hidden">Visualizar</span> Registro</a></li>'
        )
        html.append(
            f'<li><a class="btn default" href="{obj.get_url_historico()}" title="Visualizar Histórico"><span class="fas fa-eye" aria-hidden="true"></span><span class="visually-hidden">Visualizar</span> Histórico</a></li>'
        )
        if obj.diploma:
            html.append(
                f'<li><a class="btn default" href="{obj.get_url_diploma()}" title="Visualizar Diploma"><span class="fas fa-eye" aria-hidden="true"></span><span class="visually-hidden">Visualizar</span> Diploma</a></li>'
            )
        html.append(
            f'<li><a class="btn popup" href="{obj.get_url_status_assinaturas()}" title="Consultar situação das assinaturas"><span class="fas fa-eye" aria-hidden="true"></span>Consultar situação das assinaturas</a></li>'
        )
        html.append(
            f'<li><a class="btn" href="{obj.get_url_registro()}" title="Baixar Registro"><span class="fas fa-download" aria-hidden="true"></span><span class="visually-hidden">Baixar</span> Registro</a></li>'
        )
        if obj.status_documentacao_academica_digital:
            html.append(
                f'<li><a class="btn" href="{obj.get_url_xml_documentacao_academica()}" title="Baixar XML da Documentação Acadêmica"><span class="fas fa-download" aria-hidden="true"></span><span class="visually-hidden">Baixar</span> XML da Documentação Acadêmica</a></li>'
            )
        if obj.status_historico_escolar:
            html.append(
                f'<li><a class="btn" href="{obj.get_url_xml_historico_escolar()}" title="Baixar XML do Histórico"><span class="fas fa-download" aria-hidden="true"></span><span class="visually-hidden">Baixar</span> XML do Histórico</a></li>'
            )
        if obj.status_dados_diploma_digital:
            html.append(
                f'<li><a class="btn" href="{obj.get_url_xml_dados_diploma()}" title="Baixar XML do Diploma"><span class="fas fa-download" aria-hidden="true"></span><span class="visually-hidden">Baixar</span> XML do Diploma</a></li>'
            )
        if obj.status_representacao_diploma_digital:
            html.append(
                f'<li><a class="btn" href="{obj.get_url_pdf_representacao_visual()}" title="Baixar PDF do Diploma"><span class="fas fa-download" aria-hidden="true"></span><span class="visually-hidden">Baixar</span> PDF do Diploma</a></li>'
            )
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_acoes.short_description = 'Opções'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if in_group(request.user, ('Administrador Acadêmico', 'Reitor')):
            return qs
        elif in_group(request.user, ('Coordenador de Registros Acadêmicos', 'Diretor Geral')):
            return qs.filter(registro_emissao_diploma__aluno__curso_campus__diretoria__setor__uo=request.user.get_vinculo().setor.uo)
        elif in_group(request.user, 'Secretário Acadêmico'):
            setores = UsuarioGrupoSetor.objects.filter(
                usuario_grupo__user=request.user, usuario_grupo__group__name__in=('Secretário Acadêmico',)
            ).values_list('setor', flat=True)
            return qs.filter(registro_emissao_diploma__aluno__curso_campus__diretoria__setor__in=setores)
        else:
            return qs.none()

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_assinadas', 'tab_revogados']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(concluida=False, data_revogacao__isnull=True)

    tab_pendentes.short_description = 'Pendentes de Assinatura'

    def tab_assinadas(self, request, queryset):
        return queryset.filter(concluida=True, data_revogacao__isnull=True)

    tab_assinadas.short_description = 'Assinadas'

    def tab_revogados(self, request, queryset):
        return queryset.filter(data_revogacao__isnull=False)

    tab_revogados.short_description = 'Revogadas'


admin.site.register(AssinaturaDigital, AssinaturaDigitalAdmin)


class CertificadoDiplomaAdmin(ModelAdminPlus):
    list_display = 'get_matricula_aluno', 'get_nome_aluno', 'get_curso', 'processo', 'validade', 'get_acoes'
    search_fields = 'aluno__matricula', 'aluno__pessoa_fisica__cpf', 'aluno__pessoa_fisica__nome', 'processo__numero_protocolo'
    list_display_icons = False
    filter_filter = 'aluno__curso_campus__diretoria', 'aluno__curso_campus__diretoria__setor__uo'
    form = CertificadoDiplomaForm
    export_to_xls = True
    list_per_page = 15

    def get_matricula_aluno(self, obj):
        return obj.aluno.matricula

    get_matricula_aluno.short_description = 'Matrícula'

    def get_nome_aluno(self, obj):
        return obj.aluno.pessoa_fisica.nome

    get_nome_aluno.short_description = 'Aluno'

    def get_curso(self, obj):
        return f'{obj.aluno.curso_campus.codigo} - {obj.aluno.curso_campus.descricao_historico}'

    get_curso.short_description = 'Curso'

    def get_acoes(self, obj):
        html = []
        html.append('<ul class="action-bar">')
        html.append('<li><a target="_blank" class="btn default" href="{}">{}</a></li>'.format(f'/edu/certificado_diploma_pdf/{obj.pk}/', 'Imprimir'))
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_acoes.short_description = 'Ações'


admin.site.register(CertificadoDiploma, CertificadoDiplomaAdmin)
