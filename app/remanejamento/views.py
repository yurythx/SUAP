import datetime

import sentry_sdk
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify
from django.urls import reverse_lazy

from comum.models import Configuracao
from djtools import layout
from djtools.utils import XlsResponse, deprecated, group_required, httprr, permission_required, rtr
from documento_eletronico.models import (
    CompartilhamentoDocumentoPessoa,
    Documento,
    DocumentoTexto,
    HipoteseLegal,
    ModeloDocumento,
    NivelPermissao,
    TipoVinculoDocumento,
    VinculoDocumentoTexto,
)
from documento_eletronico.utils import EstagioProcessamentoVariavel, get_variaveis, processar_template_ckeditor
from remanejamento.forms import (
    AvaliadorInscricaoFormFactory,
    CadastrarAreasCorrelatasVagaEditalForm,
    CadastrarCargosCorrelatosVagaEditalForm,
    CadastrarDisciplinasCorrelatasVagaEditalForm,
    CadastrarVagasEditalForm,
    ConfigurarCargosVagasEditalForm,
    ConfigurarDisciplinasEditalForm,
    CoordenadorInscricaoEditarFormFactory,
    DisciplinaForm,
    DisciplinaItemForm,
    EditalRecursoForm,
    EditalRecursoRespostaForm,
    EditarDadosInscricaoForm,
    FiltroInscricoesForm,
    InabilitarInscricaoForm,
    InscreverFormFactory,
    InscricaoContempladaExtraordinariaForm,
    InscricaoRecursoForm,
    InscricaoRespostaRecursoForm,
    ReabilitarInscricaoForm,
    VincularResultadoEditalForm,
)
from remanejamento.models import (
    AfastamentoRemocaoInterna,
    Disciplina,
    Edital,
    EditalAfastamento,
    EditalRecurso,
    Inscricao,
    InscricaoContemplada,
    ServidorAfastamentoRemocaoInterna,
    VagaEdital,
)
from rh.models import Servidor, ServidorAfastamento, Setor


@layout.info()
def index_infos(request):
    infos = []

    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        for recurso in Edital.get_em_periodo_recurso_edital_servidor(servidor):
            if recurso.permite_recursos_contra_edital:
                infos.append({'url': recurso.get_url_recurso, 'titulo': f'Recurso ao Edital {recurso.titulo}.'})

        for inscricao in Inscricao.get_em_periodo_cancelamento_servidor(servidor):
            infos.append({'url': '/admin/remanejamento/inscricao/', 'titulo': f'Cancelamento de Inscrição {inscricao.edital.titulo}.'})

        for inscricao in Inscricao.get_em_periodo_recurso_servidor(servidor):
            infos.append(
                {'url': inscricao.get_absolute_url(), 'titulo': f'Recurso ao Resultado da Inscrição {inscricao} do Edital {inscricao.edital}.'}
            )

    return infos


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        for edital in Edital.get_em_periodo_de_inscricao_servidor(servidor):
            inscricoes.append({'url': edital.get_url_inscrever, 'titulo': f'Inscrever-se para Remoção Interna: <strong>{edital.titulo}</strong>.'})
    return inscricoes


@rtr()
@login_required()
def recurso_edital(request, edital_pk):
    edital = get_object_or_404(Edital, pk=edital_pk)
    title = f'Recurso ao {edital.titulo}'
    servidor = request.user.get_relacionamento()
    if not servidor.eh_servidor or not edital.is_em_periodo_de_recurso_edital_servidor(servidor):
        raise PermissionDenied('Acesso negado.')

    form = EditalRecursoForm(request.POST or None, id_edital=edital_pk)
    if form.is_valid():
        recurso = EditalRecurso()
        recurso.edital = form.cleaned_data['edital']
        recurso.recurso_texto = form.cleaned_data['recurso_texto']
        recurso.servidor = servidor
        recurso.save()
        return httprr('/admin/remanejamento/editalrecurso/', 'Recurso cadastrado com sucesso.')

    return locals()


@rtr()
@login_required()
def visualizar_recurso_edital(request, recurso_pk):
    recurso = get_object_or_404(EditalRecurso, pk=recurso_pk)
    title = f'Recurso ao {recurso.edital}'
    exibir_resposta_recurso = recurso.pode_exibir_resposta_recurso_edital(request.user)
    servidor_logado = request.user.get_relacionamento()
    sou_coordenador = recurso.edital.coordenadores.filter(pk=request.user.pk).exists()
    if recurso.servidor == servidor_logado or sou_coordenador:
        if sou_coordenador and not recurso.edital.is_pode_exibir_resultado_recurso():
            form = EditalRecursoRespostaForm(request.POST or None, instance=recurso)
            if form.is_valid():
                recurso.recurso_resposta = form.cleaned_data['recurso_resposta']
                recurso.dh_resposta = datetime.datetime.now()
                recurso.recurso_respondido = True
                recurso.save()

                return httprr('/admin/remanejamento/editalrecurso/', 'Resposta ao Recurso cadastrada com sucesso.')

        return locals()
    raise PermissionDenied('Acesso negado.')


def _filtrar_inscricoes(request: HttpRequest, edital: Edital, inscricoes: QuerySet) -> QuerySet:
    """Aplica às inscrições os filtros de texto e cargo/disciplina do ``FiltroInscricoesForm``."""
    texto = request.GET.get('texto', None)
    if texto:
        inscricoes = inscricoes.filter(Q(servidor__pessoa_fisica__nome__icontains=texto) | Q(id__icontains=texto))
    if 'cargo' in request.GET:
        if not edital.eh_edital_remocao_docente() and request.GET.get('cargo'):
            inscricoes = inscricoes.filter(servidor__cargo_emprego__pk=request.GET.get('cargo'))
    elif 'disciplina' in request.GET:
        inscricoes = inscricoes.filter(vaga_edital__disciplina__pk__in=[request.GET.get('disciplina')])
    return inscricoes


@rtr('remanejamento/templates/gerenciar_edital.html')
@group_required('Coordenador de Remanejamento, Avaliador de Remanejamento, Coordenador de Gestão de Pessoas Sistêmico')
def gerenciar_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    user = request.user
    eh_coordenador_sistemico_rh = user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico')

    if not edital.pode_editar(user):
        raise PermissionDenied('Você não tem permissão para gerenciar o Edital.')

    title = edital

    # if not edital.is_pode_exibir_resultado(): #So quem não tem resultado final
    steps = '<ul class="steps">'
    for etapa, ativa in edital.get_etapas_com_status():
        if ativa:
            steps += f'<li aria-label="{etapa}" class="hint hint-bottom"><span class="step-{slugify(etapa)} active">{etapa}</span></li>'
        else:
            steps += f'<li aria-label="{etapa}" class="hint hint-bottom"><span class="step-{slugify(etapa)}">{etapa}</span></li>'
    steps += '</ul>'

    hoje = datetime.date.today()

    pode_editar = edital.pode_editar(request.user)

    total_inscritos = edital.inscricao_set.filter(confirmada=True).count()
    total_recursos = edital.inscricao_set.exclude(
        recurso_texto=''
    ).count()  # Fixme criar metodo em Edital para retornar recursos com param respondido=False que verifica no campo resposta_recurso
    criterios_classificacao = edital.editalcriterioclassificacao_set.all().order_by('ordem')
    licencas_afastamentos = edital.editalafastamento_set.all()
    inscricoes_confirmadas = edital.inscricao_set.filter(confirmada=True).order_by('servidor__pessoa_fisica__nome')
    inscricoes_com_recursos_nao_respondidos = edital.inscricao_set.filter(avaliacao_recurso='').exclude(recurso_texto='')
    inscricoes_com_recursos_respondidos = edital.inscricao_set.exclude(avaliacao_recurso='')
    historico_acoes_edital = edital.acaoeditalhistorico_set.all()
    inscricoes_contempladas_resultado = InscricaoContemplada.objects.filter(
        inscricao__edital=edital,
        situacao__in=[
            InscricaoContemplada.CONTEMPLADO,
            InscricaoContemplada.PUBLICADA_PARCIAL,
            InscricaoContemplada.PUBLICADA_FINAL,
            InscricaoContemplada.HOMOLOGADA,
        ],
    ).order_by('inscricao__servidor__cargo_emprego__nome')
    if edital.eh_edital_remocao_docente():
        vagas_edital = VagaEdital.objects.filter(edital=edital).distinct('cargo', 'disciplina')
    else:
        vagas_edital = VagaEdital.objects.filter(edital=edital).distinct('cargo', 'cargo_emprego_area')

    form = FiltroInscricoesForm(request.GET or None, edital=edital)
    # A aba padrão é a de inscrições, mas o ?tab= de quem redirecionou para cá (ex.: após salvar) prevalece, salvo ao filtrar
    filtrou_inscricoes = any(campo in request.GET for campo in form.fields)
    if 'tab' not in request.GET or filtrou_inscricoes:
        tab = 'inscricoes'

    if filtrou_inscricoes and form.is_valid():
        inscricoes_confirmadas = _filtrar_inscricoes(request, edital, inscricoes_confirmadas)

    return locals()


@login_required()
def processar_resultado(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    user = request.user

    if not edital.pode_editar(user):
        raise PermissionDenied('Você não tem permissão para gerenciar o Edital.')

    if edital.resultado_final_foi_homologado():
        return httprr('..', 'Edital não está em fase que permita processar resultados.', 'error')

    if not VagaEdital.objects.filter(edital=edital).exclude(qtd_edital=0).exists():
        return httprr('..', 'Não existem vagas cadastradas para processar o resultado do Edital.', 'error')

    if edital.existem_anexos_nao_avaliados():
        return httprr('..', 'Não é possível processar o resultado, pois existem inscrições com anexos não avaliados', 'error')

    if edital.existem_inscricoes_com_avaliacoes_pendentes():
        return httprr('..', 'Não é possível processar o resultado, pois existem inscrições com avaliações pendentes', 'error')

    try:
        from remanejamento import tasks

        return tasks.processar_resultado_edital(edital)
    except Exception as e:
        if settings.DEBUG:
            raise (e)
        messages.error(request, 'Ocorreu erro ao processar resultado.')
    url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}) + '?tab=inscricoes'
    return httprr(url)


@transaction.atomic()
@login_required()
def publicar_resultado(request, edital, final=False):
    """
    Gera o documento eltronico (DocumentoTexto) com Resultado da Remoção
    params:
    edital: edital
    inscricoes_contempladas_resultado:queryset
    final: se final == True,  indica se será geração do Resultado Final
    """
    user = request.user
    tipo_resultado = 'Final' if final else 'Parcial'

    # Instanciar modelo de documento texto
    modelo = None
    try:
        modelo = ModeloDocumento.objects.get(nome='Resultado de Remoção Interna')
    except Exception:
        messages.error(request, 'Não existe o modelo de documento texto com nome de "Resultado de Remoção Interna".')

    try:
        user = request.user

        inscricoes_contempladas_resultado = edital.get_inscricoes_contempladas_resultado(final)
        assunto = f'Resultado {tipo_resultado} do  edital {edital.titulo}'
        setor_dono_id = Configuracao.get_valor_por_chave('rh', 'setor_remocaointerna_rh')
        setor_dono = Setor.objects.suap_ativos().filter(pk=setor_dono_id).first()

        dados_classificados_cargo_ou_disciplina = edital.get_dados_classificados_por_cargo_resultado()
        if edital.eh_edital_remocao_docente():
            dados_classificados_cargo_ou_disciplina = edital.get_dados_classificados_por_disciplina_resultado()

        variaveis = {}
        variaveis['resultado_html'] = edital.get_resultado_html(dados_classificados_cargo_ou_disciplina, inscricoes_contempladas_resultado, final)
        variaveis_correntes = get_variaveis(
            documento_identificador=None,
            estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
            usuario=user,
            setor_dono=setor_dono,
        )

        # Obtem o atributo referente ao resultado processado (parcial ou final)
        if final:
            edital_documentotexto_vinculado = edital.resultado_final_documentotexto
        else:
            edital_documentotexto_vinculado = edital.resultado_parcial_documentotexto

        def gerar_documento(edital, final):
            hipotese_legal = HipoteseLegal.objects.filter(pk=6).first()
            documento_novo = DocumentoTexto.adicionar_documento_texto(
                usuario=user,
                setor_dono=setor_dono,
                modelo=modelo,
                assunto=assunto,
                nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
                hipotese_legal=hipotese_legal,
                variaveis=variaveis,
            )
            # Vincula o documento digital criado ao edital de remoção interna
            if final:
                edital.resultado_final_documentotexto = documento_novo
            else:
                edital.resultado_parcial_documentotexto = documento_novo
            edital.save()
            return documento_novo

        msg = ''
        if not edital_documentotexto_vinculado:
            edital_documentotexto_vinculado = gerar_documento(edital, final)
            # Compartilha documento com membros - coordenadores do Edital de Remoção
            for user_coordenador in edital.coordenadores.all():
                CompartilhamentoDocumentoPessoa.objects.get_or_create(
                    vinculo_permitido=user_coordenador.get_vinculo(), documento=edital_documentotexto_vinculado, nivel_permissao=NivelPermissao.EDITAR
                )
            msg = f'Resultado {tipo_resultado} de Remoção Interna gerado com sucesso.'
        elif edital_documentotexto_vinculado.estah_assinado or edital_documentotexto_vinculado.estah_finalizado:
            msg = f'Este documento está na situação {edital_documentotexto_vinculado.get_status()} que não permite edição. Para gerar um novo resultado você deve cancelar este documento: {edital_documentotexto_vinculado.identificador}'
        elif edital_documentotexto_vinculado.estah_cancelado:
            documento_antigo = edital_documentotexto_vinculado
            novo_documento_resultado = gerar_documento(edital, final)
            tipo_vinculo = TipoVinculoDocumento.objects.get(descricao='Retificação')
            # Vincula documentos
            vinculo_documentos = VinculoDocumentoTexto()
            vinculo_documentos.tipo_vinculo_documento = tipo_vinculo
            vinculo_documentos.documento_texto_base = novo_documento_resultado
            vinculo_documentos.documento_texto_alvo = documento_antigo
            vinculo_documentos.usuario_criacao = user
            vinculo_documentos.save()
            # Atualiza referencia do atributo referente ao documento texto do resultado
            edital_documentotexto_vinculado = novo_documento_resultado
            edital.save()
            msg = f'Resultado {tipo_resultado} de Remoção Interna substituído com sucesso.'
        elif edital_documentotexto_vinculado.estah_em_rascunho or edital_documentotexto_vinculado.estah_concluido:
            variaveis_correntes.update(variaveis)
            edital_documentotexto_vinculado.corpo = processar_template_ckeditor(texto=modelo.corpo_padrao, variaveis=variaveis_correntes)
            if edital_documentotexto_vinculado.estah_concluido:
                edital_documentotexto_vinculado.editar_documento()
            edital_documentotexto_vinculado.save()
            msg = f'Resultado {tipo_resultado} de Remoção Interna atualizado com sucesso.'

        if edital_documentotexto_vinculado and msg:
            # atualiza as incrições contempladas para a situação publicado_parcial ou publicado_final
            situacao_update = InscricaoContemplada.PUBLICADA_FINAL if final else InscricaoContemplada.PUBLICADA_PARCIAL
            inscricoes_contempladas_resultado.update(situacao=situacao_update)
            return httprr(edital_documentotexto_vinculado.get_absolute_url(), msg)
        else:
            return httprr('..', f'Erro ao tentar gerar Resultado {tipo_resultado}.', 'error')
    except Exception as e:
        if settings.DEBUG:
            raise e
        sentry_sdk.capture_exception(e)
        return httprr('..', f'Erro ao tentar gerar Resultado {tipo_resultado}.', 'error')


@login_required()
@transaction.atomic()
def publicar_homologacao_resultado_final(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    user = request.user

    if not edital.pode_editar(user):
        raise PermissionDenied('Você não tem permissão para gerenciar o Edital.')

    if not edital.pode_publicar_homologacao_resultado_final():
        return httprr(
            '..',
            f'A Homologação do Resultado Final somente pode ser publicada quando o documento do Resultado Final estiver finalizado e após a data de fim de homologação do resultado: {edital.data_homologacao_resultado.strftime("%d/%m/%Y")}.',
            'error',
        )

    # Criar documento com mesmo conteúdo do resultado final porém com texto da homologação
    # O documento deve conter todas as inscrições contempladas que estão sendo homologadas nesta ação
    # compartilhar documento com os coordenadores do edital
    # Instanciar modelo de documento texto
    modelo = None
    try:
        modelo = ModeloDocumento.objects.get(nome='Resultado de Remoção Interna')
    except Exception:
        messages.error(request, 'Não existe o modelo de documento texto com nome de "Resultado de Remoção Interna".')

    user = request.user

    inscricoes_contempladas_resultado = InscricaoContemplada.objects.filter(
        inscricao__edital=edital, situacao__in=InscricaoContemplada.PUBLICADA_FINAL
    )
    assunto = f'Homologação do Resultado Final do  edital {edital.titulo}'
    setor_dono_id = Configuracao.get_valor_por_chave('rh', 'setor_remocaointerna_rh')
    setor_dono = Setor.objects.filter(pk=setor_dono_id).first()

    dados_classificados_cargo_ou_disciplina = edital.get_dados_classificados_por_cargo_resultado()
    if edital.eh_edital_remocao_docente():
        dados_classificados_cargo_ou_disciplina = edital.get_dados_classificados_por_disciplina_resultado()

    variaveis = {}
    variaveis['resultado_html'] = edital.get_resultado_html(
        dados_classificados_cargo_ou_disciplina, inscricoes_contempladas_resultado, final=True, homologacao=True
    )
    variaveis_correntes = get_variaveis(
        documento_identificador=None,
        estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
        usuario=user,
        setor_dono=setor_dono,
    )

    def gerar_documento(edital):
        hipotese_legal = HipoteseLegal.objects.filter(pk=6).first()
        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user,
            setor_dono=setor_dono,
            modelo=modelo,
            assunto=assunto,
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
            hipotese_legal=hipotese_legal,
            variaveis=variaveis,
        )
        # Vincula o documento digital criado ao edital de remoção interna
        edital.resultado_final_homologacao_documentotexto = documento_novo
        edital.save()
        return documento_novo

    msg = ''
    if not edital.resultado_final_homologacao_documentotexto:
        documento_homologacao = gerar_documento(edital)
        # Compartilha documento com membros - coordenadores do Edital de Remoção
        for user_coordenador in edital.coordenadores.all():
            CompartilhamentoDocumentoPessoa.objects.get_or_create(
                vinculo_permitido=user_coordenador.get_vinculo(), documento=documento_homologacao, nivel_permissao=NivelPermissao.EDITAR
            )
        msg = 'Homologação do Resultado Final de Remoção Interna gerado com sucesso.'
        return httprr(documento_homologacao.get_absolute_url(), msg)

    if edital.resultado_final_homologacao_documentotexto.estah_assinado or edital.resultado_final_homologacao_documentotexto.estah_finalizado:
        msg = f'Este documento está na situação {edital.resultado_final_homologacao_documentotexto.get_status()} que não permite edição. Para gerar um novo resultado você deve cancelar este documento: {edital.resultado_final_homologacao_documentotexto.identificador}'
    elif edital.resultado_final_homologacao_documentotexto.estah_cancelado:
        documento_antigo = edital.resultado_final_homologacao_documentotexto
        documento_homologacao = gerar_documento(edital)
        tipo_vinculo = TipoVinculoDocumento.objects.get(descricao='Retificação')
        # Vincula documentos
        vinculo_documentos = VinculoDocumentoTexto()
        vinculo_documentos.tipo_vinculo_documento = tipo_vinculo
        vinculo_documentos.documento_texto_base = documento_homologacao
        vinculo_documentos.documento_texto_alvo = documento_antigo
        vinculo_documentos.usuario_criacao = user
        vinculo_documentos.save()
        edital.save()
        msg = 'Homologação do Resultado Final da Remoção Interna substituído com sucesso.'
    elif edital.resultado_final_homologacao_documentotexto.estah_em_rascunho or edital.resultado_final_homologacao_documentotexto.estah_concluido:
        variaveis_correntes.update(variaveis)
        edital.resultado_final_homologacao_documentotexto.corpo = processar_template_ckeditor(
            texto=modelo.corpo_padrao, variaveis=variaveis_correntes
        )
        if edital.resultado_final_homologacao_documentotexto.estah_concluido:
            edital.resultado_final_homologacao_documentotexto.editar_documento()
        edital.resultado_final_homologacao_documentotexto.save()
        msg = 'Homologação do Resultado Final da Remoção Interna atualizado com sucesso.'

    if edital.resultado_final_homologacao_documentotexto and msg:
        # atualiza as incrições contempladas para a situação Homologada
        InscricaoContemplada.objects.filter(inscricao__edital=edital, situacao=InscricaoContemplada.PUBLICADA_FINAL).update(
            situacao=InscricaoContemplada.HOMOLOGADA
        )
        return httprr(edital.resultado_final_homologacao_documentotexto.get_absolute_url(), msg)


@login_required()
def publicar_resultado_parcial(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    user = request.user

    if not edital.pode_editar(user):
        raise PermissionDenied('Você não tem permissão para gerenciar o Edital.')

    if not edital.pode_publicar_resultado_parcial():
        raise PermissionDenied('Edital não está em fase que permita a publicação dos resultados.')

    return publicar_resultado(request, edital, final=False)


@login_required()
def publicar_resultado_final(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    user = request.user

    if not edital.pode_editar(user):
        raise PermissionDenied('Você não tem permissão para gerenciar o Edital.')

    if not edital.pode_publicar_resultado_final():
        return httprr(
            '..',
            f'Resultado Final somente pode ser publicado quando o documento do Resultado Parcial estiver finalizado e após a data de fim dos recursos: {edital.fim_recursos.strftime("%d/%m/%Y")}.',
            'error',
        )

    return publicar_resultado(request, edital, final=True)


def _afastamentos_impeditivos_vigentes(servidor: Servidor, edital: Edital) -> QuerySet[ServidorAfastamento]:
    """Afastamentos do servidor em usufruto hoje cujo tipo o edital marcou como impeditivo."""
    hoje = datetime.date.today()
    afastamentos_impeditivos_do_edital = EditalAfastamento.objects.filter(edital=edital, impeditivo=True).values_list('afastamento', flat=True)
    return (
        servidor.servidorafastamento_set.filter(afastamento__in=afastamentos_impeditivos_do_edital, cancelado=False)
        .filter(Q(data_inicio__lte=hoje) | Q(data_inicio__isnull=True))
        .filter(Q(data_termino__gt=hoje) | Q(data_termino__isnull=True))
        .select_related('afastamento')
        .order_by('data_inicio')
    )


@rtr()
@login_required()
def inscrever(request, edital_pk):
    # Se não tem inscrição, vamos verificar se ainda está no período
    edital = get_object_or_404(Edital, pk=edital_pk)
    servidor = request.user.get_relacionamento()
    if not request.user.eh_servidor or not edital.is_em_periodo_de_inscricao_servidor(request.user.get_relacionamento()):
        raise PermissionDenied('Edital não está em período de inscrição.')

    title = 'Inscrição para Edital de Remoção Interna'

    # O bloqueio é exibido na própria tela, no lugar do formulário, listando os afastamentos
    afastamentos_impeditivos = list(_afastamentos_impeditivos_vigentes(servidor, edital))
    if afastamentos_impeditivos:
        return locals()

    # Obtém dados iniciais da última inscrição validada caso exista
    ultima_inscricao_validada = Inscricao.objects.filter(
        servidor=request.user.get_relacionamento(), confirmada=True, validado_por__isnull=False
    ).last()
    initial_data = {}
    if ultima_inscricao_validada:
        initial_data = {
            'concurso_ingresso_eh_ifrn': ultima_inscricao_validada.concurso_ingresso_eh_ifrn,
            'classificacao_concurso': ultima_inscricao_validada.classificacao_concurso,
            'dou_numero': ultima_inscricao_validada.dou_numero,
            'dou_data': ultima_inscricao_validada.dou_data,
            'dou_pagina': ultima_inscricao_validada.dou_pagina,
            'dou_sessao': ultima_inscricao_validada.dou_sessao,
        }

    FormClass = InscreverFormFactory(edital, request.user)
    form = FormClass(request.POST or None, request.FILES or None, initial=initial_data)
    if form.is_valid():
        inscricao = form.save()

        # Salva informações do validador e data de validação das informações de inscrição do servidor
        if ultima_inscricao_validada:
            inscricao.validado_por = ultima_inscricao_validada.validado_por
            inscricao.validado_em = ultima_inscricao_validada.validado_em
            inscricao.save()

        return httprr(f'/remanejamento/inscricao/{inscricao.pk}/', 'Inscrição realizada com sucesso.')
    return locals()


@rtr()
@login_required()
def inscricao(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    title = f'Comprovante de Inscrição #{inscricao_pk}'
    pode_ver = inscricao.pode_ver(request.user)
    if not pode_ver:
        raise PermissionDenied('Você não tem permissão para ver a página solicitada.')

    pode_mudar_status = inscricao.pode_mudar_status(request.user)
    pode_avaliar = inscricao.pode_avaliar(request.user)
    pode_cadastrar_recurso = inscricao.pode_cadastrar_recurso(request.user)
    avaliador_pode_habilitar = inscricao.avaliador_pode_habilitar(request.user)
    pode_ver_parecer = inscricao.pode_ver_parecer(request.user)
    pode_ver_resultado_recurso = inscricao.pode_ver_resultado_recurso(request.user)
    pode_excluir_recurso = inscricao.pode_excluir_recurso(request.user)
    pode_desistir = inscricao.is_pode_desistir(request.user)
    eh_coordenador = request.user.is_superuser or (request.user in inscricao.edital.coordenadores.all())
    eh_avaliador = inscricao.disciplina and request.user in inscricao.disciplina.avaliadores.all()

    # tratamento diferenciado para respostas a recursos de TAE's
    pode_responder_recurso_adm = eh_coordenador and inscricao.recurso_texto and not inscricao.edital.is_pode_exibir_resultado_recurso()
    if pode_responder_recurso_adm:
        form_recurso_resposta = InscricaoRespostaRecursoForm(request.POST or None, instance=inscricao)
        if form_recurso_resposta.is_valid():
            form_recurso_resposta.save()
            form_recurso_resposta.instance.recurso_respondido_por = request.user.get_vinculo()
            form_recurso_resposta.instance.recurso_respondido_em = datetime.datetime.now()
            form_recurso_resposta.instance.save()
            return httprr(f'/remanejamento/inscricao/{inscricao.pk}/', 'Resposta ao recurso do resultado parcial cadastrado com sucesso.')

    if pode_mudar_status:
        CoordenadorInscricaoEditarForm = CoordenadorInscricaoEditarFormFactory(inscricao)
        form_coordenador = CoordenadorInscricaoEditarForm(request.POST or None, instance=inscricao)
        if form_coordenador.is_valid():
            form_coordenador.save()
            return httprr(f'/remanejamento/inscricao/{inscricao.pk}/', 'Inscrição alterada com sucesso!')

    if pode_avaliar:
        AvaliadorInscricaoForm = AvaliadorInscricaoFormFactory(inscricao)
        if request.method == 'POST' and 'observacao' in request.POST:
            form_avaliador = AvaliadorInscricaoForm(data=request.POST)
            if form_avaliador.is_valid():
                form_avaliador.save()
            return httprr(f'/remanejamento/inscricao/{inscricao.pk}/', 'Inscrição avaliada com sucesso!')
        else:
            form_avaliador = AvaliadorInscricaoForm()

    if pode_cadastrar_recurso:
        form_recurso = InscricaoRecursoForm(request.POST or None, instance=inscricao)
        if form_recurso.is_valid():
            form_recurso.save()
            form_recurso.instance.situacao_recurso = 'PENDENTE_DE_ANALISE'
            form_recurso.instance.save()
            return httprr(f'/remanejamento/inscricao/{inscricao.pk}/', 'Recurso ao resultado cadastrado com sucesso.')
    return locals()


@login_required()
def inscricao_desistir(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    if not inscricao.is_pode_desistir:
        raise PermissionDenied('Você não tem permissão para ver a página solicitada.')

    inscricao.efetivar_desistencia()

    return httprr(f'/remanejamento/inscricao/{inscricao.pk}/')


@rtr()
@login_required()
def adicionar_inscricao_contemplada_extraordinaria(request, edital_pk):
    edital = get_object_or_404(Edital, pk=edital_pk)
    if not edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar a inscrição.')

    if (
        not InscricaoContemplada.objects.filter(
            inscricao__edital=edital,
            situacao__in=[
                InscricaoContemplada.CONTEMPLADO,
                InscricaoContemplada.PUBLICADA_PARCIAL,
                InscricaoContemplada.PUBLICADA_FINAL,
                InscricaoContemplada.HOMOLOGADA,
            ],
        )
        .order_by('-id')
        .exists()
    ):
        raise PermissionDenied(
            'Não é possível adicionar inscrição contemplada extraordinária, pois ainda não realizado o processamento do resultado deste edital.'
        )

    form = InscricaoContempladaExtraordinariaForm(
        request.POST or None,
        request=request,
        edital_pk=edital.id,
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Inscrição Contemplada Extraordinária incluída com sucesso.')
        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}) + '?tab=inscricoes'
        return httprr(url)

    return locals()


@rtr()
@login_required()
def editar_inscricao_coordenador(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    if not inscricao.is_pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar a inscrição.')

    form = EditarDadosInscricaoForm(request.POST or None, instance=inscricao, request=request)
    if form.is_valid():
        form.save()
        messages.success(request, 'Inscrição alterada com sucesso.')
        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': inscricao.edital.id}) + '?tab=inscricoes'
        return httprr(url, close_popup=True)

    return locals()


@rtr()
@login_required()
def inabililitar_inscricao(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)

    if not inscricao.is_pode_inabilitar(request.user):
        raise PermissionDenied('Você não tem permissão para inabilitar a inscrição.')

    form = InabilitarInscricaoForm(request.POST or None, title=f'Inscrição de {inscricao.servidor}')
    if form.is_valid():
        inscricao.efetivar_inaptidao(motivo_inapta=form.cleaned_data['motivo_inapta'], vinculo=request.user.get_vinculo())

        messages.success(request, 'Inscrição inabilitada com sucesso.')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': inscricao.edital.id}) + '?tab=inscricoes'
        return httprr(url)

    return locals()


@rtr()
@login_required()
def reabilitar_inscricao(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    if not inscricao.is_pode_inabilitar(request.user):
        raise PermissionDenied('Você não tem permissão para reabilitar a inscrição.')

    form = ReabilitarInscricaoForm(request.POST or None, title=f'Inscrição de {inscricao.servidor}')
    if form.is_valid():
        inscricao.efetivar_reabilitacao(observacao=form.cleaned_data['observacao'], vinculo=request.user.get_vinculo())

        messages.success(request, 'Inscrição reabilitada com sucesso.')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': inscricao.edital.id}) + '?tab=inscricoes'
        return httprr(url)

    return locals()


@rtr()
@login_required()
def cadastrar_vagas_edital(request, edital_id, vagaedital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    vagaedital = get_object_or_404(VagaEdital, pk=vagaedital_id)
    url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}) + '?tab=edital_info'

    if not edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar informações do edital.')

    if edital.resultado_parcial_foi_homologado():
        return httprr(url, 'Edital com Resultado Final homologado.', 'error', close_popup=True)

    form = CadastrarVagasEditalForm(request.POST or None, edital=edital, vagaedital=vagaedital, request=request)
    if form.is_valid():
        form.processar()
        messages.success(request, 'Vagas cadastradas com sucesso!.')
        return httprr(url, close_popup=True)

    return locals()


@rtr()
@login_required()
def excluir_vagas_edital(request, edital_id, vagaedital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    vagaedital = get_object_or_404(VagaEdital, pk=vagaedital_id)

    if not edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar informações do edital.')

    if not vagaedital.pode_excluir():
        raise PermissionDenied('As vagas do edital para este Cargo/Área não pode ser excluído pois existem inscrições contempladas.')

    url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}) + '?tab=edital_info'
    try:
        if edital.eh_edital_remocao_docente():
            VagaEdital.objects.filter(edital=vagaedital.edital, cargo=vagaedital.cargo, disciplina=vagaedital.disciplina).delete()
        else:
            VagaEdital.objects.filter(edital=vagaedital.edital, cargo=vagaedital.cargo, cargo_emprego_area=vagaedital.cargo_emprego_area).delete()
        messages.success(request, 'Vagas excluídas com sucesso!.')
        return httprr(url, close_popup=True)
    except Exception as e:
        return httprr(url, str(e), 'error')


@rtr()
@login_required()
def cadastrar_areas_correlatas_edital(request, vagaedital_id):
    vagaedital = get_object_or_404(VagaEdital, pk=vagaedital_id)
    if not vagaedital.edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão.')

    form = CadastrarAreasCorrelatasVagaEditalForm(request.POST or None, vagaedital_id=vagaedital_id)
    if form.is_valid():
        form.processar()
        messages.success(request, 'Áreas correlatas cadastradas com sucesso!.')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': vagaedital.edital.id}) + '?tab=edital_info'
        return httprr(url, close_popup=True)

    return locals()


@rtr()
@login_required()
def cadastrar_cargos_correlatos_edital(request, vagaedital_id):
    vagaedital = get_object_or_404(VagaEdital, pk=vagaedital_id)
    if not vagaedital.edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão.')

    form = CadastrarCargosCorrelatosVagaEditalForm(request.POST or None, vagaedital_id=vagaedital_id)
    if form.is_valid():
        form.processar()
        messages.success(request, 'Cargos correlatos cadastrados com sucesso!')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': vagaedital.edital.id}) + '?tab=edital_info'
        return httprr(url, close_popup=True)

    return locals()


@rtr()
@login_required()
def cadastrar_disciplinas_correlatas_edital(request, vagaedital_id):
    vagaedital = get_object_or_404(VagaEdital, pk=vagaedital_id)
    if not vagaedital.edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão.')
    form = CadastrarDisciplinasCorrelatasVagaEditalForm(request.POST or None, vagaedital_id=vagaedital_id)
    if form.is_valid():
        form.processar()
        messages.success(request, 'Disciplinas correlatas cadastradas com sucesso!.')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': vagaedital.edital.id}) + '?tab=edital_info'
        return httprr(url, close_popup=True)

    return locals()


@rtr()
@login_required()
def atualizar_afastamentos(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if not edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão.')

    if afastamentos := AfastamentoRemocaoInterna.objects.all():
        for afastamentoremocaointerna in afastamentos:
            EditalAfastamento.objects.update_or_create(
                edital=edital,
                afastamento=afastamentoremocaointerna.afastamento,
                defaults={
                    'impeditivo': afastamentoremocaointerna.impeditivo,
                    'desconta_exercicio': afastamentoremocaointerna.desconta_exercicio,
                    'atualizado_por': request.user.get_vinculo(),
                    'atualizado_em': datetime.datetime.now(),
                },
            )

    messages.success(request, 'Afastamentos atualizados com sucesso!.')

    return httprr(reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}), close_popup=True)


@rtr()
@login_required()
def configurar_cargos_vagas_edital(request, edital_id):
    """
    Utilizado para configurar quais os cargos e áreas estaram presentes no edital, exemplo: Administrador, Tecnico de Laboratório Área - Química etc
    """
    edital = get_object_or_404(Edital, pk=edital_id)
    if not edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar informações do edital.')

    form = ConfigurarCargosVagasEditalForm(request.POST or None, edital_id=edital.id, request=request)
    if form.is_valid():
        form.processar()
        messages.success(request, 'Cargos configurados com sucesso!.')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}) + '?tab=edital_info'
        return httprr(url, close_popup=True)

    return locals()


@rtr()
@login_required()
def configurar_disciplinas_edital(request, edital_id):
    """
    Utilizado para configurar quais as disciplinas estaram presentes no edital, exemplo: Matemática, Física etc
    """
    edital = get_object_or_404(Edital, pk=edital_id)
    if not edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar informações do edital.')

    if edital.resultado_parcial_foi_homologado():
        raise PermissionDenied('Não permitido. Edital com Resultado Parcial já homologado.')

    form = ConfigurarDisciplinasEditalForm(request.POST or None, edital_id=edital.id, request=request)
    if form.is_valid():
        form.processar()
        messages.success(request, 'Disciplina adicionada com sucesso!.')

        url = reverse_lazy('configurar_disciplinas_edital', kwargs={'edital_id': edital.id})
        return httprr(url)
    disciplinas_edital = (
        VagaEdital.objects.filter(edital=edital)
        .order_by('cargo_id', 'disciplina_id', 'disciplina__descricao', 'possui_concurso_vigente')
        .distinct('cargo', 'disciplina')
    )

    return locals()


@rtr()
@login_required()
def vincular_documento_resultado(request, edital_id, tipo_doc):
    """
    Utilizado para vincular um documento de resultado ao edital, exemplo: Resultado Parcial, Resultado Final, Homologação do Resultado Final
    """
    edital = get_object_or_404(Edital, pk=edital_id)
    eh_coordenador_sistemico_rh = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico')
    if not edital.pode_editar(request.user) and eh_coordenador_sistemico_rh:
        raise PermissionDenied('Você não tem permissão para alterar informações do edital.')

    form = VincularResultadoEditalForm(request.POST or None, request=request)
    if form.is_valid():
        documento = form.cleaned_data['documento']
        if tipo_doc == 'resultado_parcial':
            edital.resultado_parcial_documentotexto = documento
        elif tipo_doc == 'resultado_final':
            edital.resultado_final_documentotexto = documento
        elif tipo_doc == 'resultado_final_homologacao':
            edital.resultado_final_homologacao_documentotexto = documento
        edital.save()
        messages.success(request, 'Documento de resultado vinculado com sucesso!.')

        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': edital.id}) + '?tab=edital_info'
        return httprr(url, close_popup=True)

    return locals()


@login_required()
@rtr()
def inscricao_imprimir(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    pode_imprimir = (
        request.user.is_superuser or request.user in inscricao.edital.coordenadores.all() or request.user in inscricao.disciplina.avaliadores.all()
    )

    if not pode_imprimir:
        raise PermissionDenied('Você não tem permissão para ver a página solicitada.')

    return locals()


@login_required()
def inscricao_excluir_recurso(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    if not inscricao.pode_excluir_recurso(request.user):
        raise PermissionDenied('Você não tem permissão para ver a página solicitada.')

    inscricao.recurso_texto = ''
    inscricao.save()

    return httprr(f'/remanejamento/inscricao/{inscricao.pk}/')


@rtr()
@login_required()
def validar_afastamentos(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    if not inscricao.edital.pode_editar(request.user):
        raise PermissionDenied('Você não tem permissão para ver a página solicitada.')

    # atualizar/exibir afastamentos do servidor até a data atual que descontam tempo
    afastamentos_do_edital = EditalAfastamento.objects.filter(edital=inscricao.edital, desconta_exercicio=True)
    afastamentos_do_servidor_para_este_edital = ServidorAfastamento.objects.filter(
        servidor=inscricao.servidor,
        cancelado=False,
        data_inicio__gte=inscricao.servidor.data_inicio_exercicio_no_cargo,
        afastamento__id__in=afastamentos_do_edital.values_list('afastamento__id', flat=True),
    )

    for servidor_afastamento in afastamentos_do_servidor_para_este_edital:
        ServidorAfastamentoRemocaoInterna.objects.get_or_create(
            servidor_afastamento=servidor_afastamento,
            inscricao=inscricao,
            afastamento=servidor_afastamento.afastamento,
        )

    if request.GET.get('action') == 'validar' and not inscricao.licenca_afastamento_verificado_por:
        for servidor_afastamento in afastamentos_do_servidor_para_este_edital:
            ServidorAfastamentoRemocaoInterna.objects.update_or_create(
                inscricao=inscricao,
                servidor_afastamento=servidor_afastamento,
                afastamento=servidor_afastamento.afastamento,
                defaults={
                    'validado_por': request.user.get_vinculo(),
                    'validado_em': datetime.datetime.now(),
                },
            )
        inscricao.licenca_afastamento_verificado_por = request.user.get_vinculo()
        inscricao.licenca_afastamento_verificado_em = datetime.datetime.now()
        inscricao.save()
        messages.success(request, 'Afastamentos do servidor validados com sucesso.')
        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': inscricao.edital.id}) + '?tab=inscricoes'
        return httprr(url, close_popup=True)

    afastamentos_do_servidor_inscricao = ServidorAfastamentoRemocaoInterna.objects.filter(inscricao=inscricao)

    return locals()


@login_required()
def inscricoes_csv(request, edital_pk):
    edital = get_object_or_404(Edital, pk=edital_pk)

    dados = edital.get_lista_inscritos_com_cabecalho()

    return XlsResponse(dados)


@rtr()
@login_required()
@permission_required('remanejamento.view_edital')
def avaliar_anexo_inscricao(request, inscricao_pk):
    inscricao = get_object_or_404(Inscricao, pk=inscricao_pk)
    if not inscricao.edital.is_coordenador(request.user):
        raise PermissionDenied('Você não tem permissão.')

    if request.method == 'GET' and request.GET.get('action') == 'deferir':
        inscricao.deferir_anexo(request.user.get_vinculo())
        messages.success(request, 'Anexo da inscrição foi deferido.')
        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': inscricao.edital.id}) + '?tab=inscricoes'
        return httprr(url, close_popup=True)
    elif request.method == 'GET' and request.GET.get('action') == 'indeferir':
        inscricao.efetivar_inaptidao(motivo_inapta='Anexo da inscrição indeferido.', vinculo=request.user.get_vinculo())
        inscricao.indeferir_anexo(request.user.get_vinculo())
        messages.success(request, 'Anexo da inscrição foi indeferido. A inscrição foi inabilitada.')
        url = reverse_lazy('gerenciar_edital', kwargs={'edital_id': inscricao.edital.id}) + '?tab=inscricoes'
        return httprr(url, close_popup=True)

    return locals()


# FIXME: remover essa view não utilizada no sistema
@deprecated(reason='View não utilizada', expire_date='2026-12-31')
@rtr()
@login_required()
@permission_required('remanejamento.add_disciplina')
def adicionar_disciplinas(request, edital_pk):
    edital = get_object_or_404(Edital, pk=edital_pk)
    if request.user not in edital.coordenadores.all() and not request.user.is_superuser:
        raise PermissionDenied
    form = DisciplinaForm(request.POST or None, id_edital=edital_pk)
    if form.is_valid():
        disciplinas = form.cleaned_data['disciplinas']
        edital = form.cleaned_data['edital']
        for disciplina in disciplinas:
            Disciplina.objects.get_or_create(descricao=disciplina.descricao, edital=Edital.objects.get(id=edital_pk))
        return httprr('/admin/remanejamento/disciplina/', 'Disciplinas cadastradas com sucesso.')

    return locals()


# FIXME: remover essa view não utilizada no sistema
@deprecated(reason='View não utilizada', expire_date='2026-12-31')
@rtr()
@login_required()
def adicionar_disciplina_itens(request, edital_pk):
    if not request.user.is_superuser:
        raise PermissionDenied

    edital = get_object_or_404(Edital, pk=edital_pk)
    if request.method == 'POST':
        form = DisciplinaItemForm(request.POST)
        if form.is_valid():
            form.save(edital)
            return httprr('/admin/remanejamento/disciplina/', 'Itens cadastrados com sucesso.')
    else:
        form = DisciplinaItemForm()
    return locals()
