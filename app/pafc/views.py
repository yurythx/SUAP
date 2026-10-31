import datetime
from functools import reduce

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Prefetch, When, Case, Value
from django.db.models.fields import BooleanField
from django.forms import modelform_factory
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.safestring import mark_safe

from comum.forms import ConfirmarComSenhaForm
from comum.models import Configuracao, Sala, UsuarioGrupo
from djtools import layout
from djtools.forms import ModelFormPlus
from djtools.templatetags.filters import in_group
from djtools.utils import JsonResponse, documento, httprr, permission_required, rtr, transaction, get_datetime_now
from edu.models import CursoCampus, Diretoria, Log, RegistroDiferenca
from pafc import tasks
from pafc.admin import PendenciaFilter, VinculacaoFilter
from pafc.forms import (
    AnexarFichaRevisaoTecnicaForm,
    ComentarioGeralForm,
    ComentarioRevisaoForm,
    ConfirmacaoForm,
    ConteudoForm,
    ConteudoPAFCForm,
    ConvocarCamaraPAFCForm,
    ConvocarConsepexPAFCForm,
    ConvocarConsupPAFCForm,
    EditarDadosCursoForm,
    EditarDocentesDisciplinaForm,
    EditarMembroEquipePAFCForm,
    EditarProReitoriaForm,
    EditarLaboratorioForm,
    InformarColaboradoresForm,
    InformarCoordenadorCursoForm,
    InformarLaboratoriosForm,
    InformarTecnicosAdministrativosForm,
    JustificarIndisponibilidadeDocentesForm,
    ReplicarModeloPAFCForm,
    SecaoForm,
    SecaoPAFCForm,
    DocumentoHibridoForm,
    VincularMatrizPAFCForm,
    AtualizarBibliografiaPAFC,
    AnexarRelatorioAnalisePreliminarForm,
    emitir_documento_pafc_formfactory,
    IndeferirSolicitacaoTramitacaoAdReferendumForm,
    SolicitarCorrecaoEmConselhosForm,
    SecaoProgramaPlanoDisciplinaModificadoForm,
    EditarEmentaPlanoDisciplinaModificadoForm,
)
from pafc.models import (
    PAFC,
    ComentarioGeralPAFC,
    ComentarioRevisao,
    Conteudo,
    ConteudoPAFC,
    DocumentoEmitidoPAFC,
    DocumentoHibrido,
    MembroComissaoPAFC,
    ModeloPAFC,
    MovimentacaoPAFC,
    RevisorTecnicoPAFC,
    Secao,
    SecaoPAFC,
    ValidadorPAFC,
    MatrizPAFC,
    BibliografiaPAFC,
    SolicitacaoTramitacaoAdReferendumPAFC,
    PlanoDisciplinaPOMC,
    PlanoDisciplinaModificado,
    SecaoProgramaPlanoDisciplinaModificado,
    RevisaoPlanoDisciplinaModificado,
    InfraestruturaExternaPAFC,
    PoloEadPAFC,
    TutorMediadorEadPAFC,
)


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    if request.user.eh_servidor:
        # Modelos de PAFC sem seção ou conteúdo (responsabilidade do Administrador de PAFC)
        if in_group(request.user, 'Administrador de PAFC', ignore_groups_if_superuser=False):
            qs_modelos_pafc = ModeloPAFC.objects.ativos()
            # FK reversa simples — LEFT JOIN com WHERE NULL não duplica linhas, .distinct() desnecessário.
            qtd_pafc_sem_revisor_t = qs_modelos_pafc.filter(secao__isnull=True).count()
            if qtd_pafc_sem_revisor_t:
                pendencias.append(
                    {
                        'titulo': f'Modelo{pluralize(qtd_pafc_sem_revisor_t)} de PAFC',
                        'subtitulo': 'sem seções',
                        'qtd': qtd_pafc_sem_revisor_t,
                        'url': '/admin/pafc/modelopafc/?tab=tab_sem_secoes',
                    }
                )
            # JOIN duplo (Secao→Conteudo) pode duplicar quando um modelo tem várias seções sem conteúdo: .distinct() necessário.
            qtd_modelos_pafc_sem_conteudo = qs_modelos_pafc.filter(secao__conteudo__isnull=True).distinct().count()
            if qtd_modelos_pafc_sem_conteudo:
                pendencias.append(
                    {
                        'titulo': f'Modelo{pluralize(qtd_modelos_pafc_sem_conteudo)} de PAFC',
                        'subtitulo': 'faltando conteúdo de seções',
                        'qtd': qtd_modelos_pafc_sem_conteudo,
                        'url': '/admin/pafc/modelopafc/?tab=tab_sem_conteudo',
                    }
                )

        # PAFCs sem revisores (responsabilidade do Operador Sistêmico PAFC)

        if request.user.has_group_cached(['Operador Sistêmico PAFC'], ignore_groups_if_superuser=False):
            qtd_pafc_sem_revisor_tec = PAFC.objects.filter(revisortecnicopafc__isnull=True).count()
            if qtd_pafc_sem_revisor_tec:
                pendencias.append(
                    {
                        'titulo': f'PAFC{pluralize(qtd_pafc_sem_revisor_tec)}',
                        'subtitulo': 'sem revisores técnicos',
                        'qtd': qtd_pafc_sem_revisor_tec,
                        'url': f'/admin/pafc/pafc/?pendencia={PendenciaFilter.SEM_REVISORES_TECNICOS}',
                    }
                )
            qtd_pafc_sem_revisor_tec = PAFC.objects.filter(validadorpafc__isnull=True).count()
            if qtd_pafc_sem_revisor_tec:
                pendencias.append(
                    {
                        'titulo': f'PAFC{pluralize(qtd_pafc_sem_revisor_tec)}',
                        'subtitulo': 'sem validadores',
                        'qtd': qtd_pafc_sem_revisor_tec,
                        'url': f'/admin/pafc/pafc/?pendencia={PendenciaFilter.SEM_VALIDADORES}',
                    }
                )

    return pendencias


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    if request.user.eh_servidor:
        hoje = datetime.date.today()
        vinculo_usuario = request.user.get_vinculo()
        diretoria_como_dg = Diretoria.objects.filter(Q(diretor_geral=vinculo_usuario) | Q(diretor_geral_exercicio=vinculo_usuario)).first()
        diretoria_como_da = Diretoria.objects.filter(Q(diretor_academico=vinculo_usuario) | Q(diretor_academico_exercicio=vinculo_usuario)).first()

        # Responsabilidades do Diretor Acadêmico
        if diretoria_como_da:
            # Cadastro da comissão de elaboração
            qtd_pafc_sem_comissao = (
                PAFC.objects.filter(setor=diretoria_como_da.setor, situacao=PAFC.EM_SOLICITACAO, membrocomissaopafc__isnull=True).distinct().count()
            )
            if qtd_pafc_sem_comissao:
                pendencias.append(
                    {
                        'titulo': f'Comiss{pluralize(qtd_pafc_sem_comissao, "ão,ões")} de Elaboração de PAFC',
                        'subtitulo': 'a definir',
                        'qtd': qtd_pafc_sem_comissao,
                        'url': f'/admin/pafc/pafc/?vinculo={VinculacaoFilter.MEUS_COMO_DA}&tab=tab_sem_comissao_elaboracao',
                    }
                )

            # Solicitação da Portaria da comissão de elaboração (situação EM SOLICITAÇÃO e comissão já definida)
            ids_pafc_sp_pendente = (
                PAFC.objects.filter(
                    setor=diretoria_como_da.setor,
                    situacao=PAFC.EM_SOLICITACAO,
                    membrocomissaopafc__isnull=False,
                )
                .distinct()
                .values_list('id', flat=True)
            )
            if ids_pafc_sp_pendente:
                pendencias.append(
                    {
                        'titulo': f'Portaria{pluralize(len(ids_pafc_sp_pendente))} de Comissão de Elaboração de PAFC',
                        'subtitulo': f'pronta{pluralize(len(ids_pafc_sp_pendente))} para solicitar',
                        'qtd': len(ids_pafc_sp_pendente),
                        'url': '/admin/pafc/pafc/'
                        f'?vinculo={VinculacaoFilter.MEUS_COMO_DA}'
                        f'&situacao__exact={PAFC.EM_SOLICITACAO}'
                        f'&pendencia={PendenciaFilter.SEM_PORTARIA_COMISSAO}'
                        f'&tab=tab_comissao_elaboracao_definida',
                    }
                )

        # Responsabilidades do Diretor-Geral
        if diretoria_como_dg:
            # Emissão da portaria da comissão de elaboração (responsabilidade do Diretor Geral)
            qtd_portarias_pendentes = (
                PAFC.objects.filter(
                    diretor_geral__vinculos__in=diretoria_como_dg.get_diretores_gerais(),
                    situacao=PAFC.AGUARDANDO_PORTARIA,
                    portaria_comissao_elaboracao_vigente__isnull=True,
                )
                .distinct()
                .count()
            )
            if qtd_portarias_pendentes:
                pendencias.append(
                    {
                        'titulo': f'Portaria{pluralize(qtd_portarias_pendentes)} da Comissão de Elaboração de PAFC',
                        'subtitulo': 'a emitir',
                        'qtd': qtd_portarias_pendentes,
                        'url': f'/admin/pafc/pafc/'
                        f'?situacao__exact={PAFC.AGUARDANDO_PORTARIA}'
                        f'&pendencia={PendenciaFilter.SEM_PORTARIA_COMISSAO}'
                        f'&setor__uo={diretoria_como_dg.setor.uo_id}',
                    }
                )

        servidor = request.user.get_relacionamento()

        # Preenchimento do PAFC (responsabilidade da comissão de elaboração)
        qtd_pafcs_sem_tecnicos = PAFC.objects.filter(membrocomissaopafc__servidor=servidor, situacao=PAFC.EM_ELABORACAO).distinct().count()
        if qtd_pafcs_sem_tecnicos:
            pendencias.append(
                {
                    'titulo': f'PAFC{pluralize(qtd_pafcs_sem_tecnicos)}',
                    'subtitulo': 'em elaboração',
                    'qtd': qtd_pafcs_sem_tecnicos,
                    'url': f'/admin/pafc/pafc/?situacao__exact={PAFC.EM_ELABORACAO}&vinculo={VinculacaoFilter.MEUS_COMO_ELABORADOR}',
                }
            )

        # Análise preliminar (responsabilidade dos validadores)
        qtd_pafcs_a_analisar = PAFC.objects.filter(situacao=PAFC.EM_ANALISE_PRELIMINAR, validadorpafc__servidor=servidor).distinct().count()
        if qtd_pafcs_a_analisar:
            pendencias.append(
                {
                    'titulo': f'PAFC{pluralize(qtd_pafcs_a_analisar)}',
                    'subtitulo': 'a realizar análise preliminar',
                    'qtd': qtd_pafcs_a_analisar,
                    'url': f'/admin/pafc/pafc/?situacao__exact={PAFC.EM_ANALISE_PRELIMINAR}&vinculo={VinculacaoFilter.MEUS_COMO_VALIDADOR}',
                }
            )

        # Revisão do PAFC (responsabilidade dos revisores técnicos)
        qtd_pafcs_a_revisar = PAFC.objects.filter(situacao=PAFC.AGUARDANDO_REVISAO_TECNICA, revisortecnicopafc__servidor=servidor).distinct().count()
        if qtd_pafcs_a_revisar:
            pendencias.append(
                {
                    'titulo': f'PAFC{pluralize(qtd_pafcs_a_revisar)}',
                    'subtitulo': 'a revisar',
                    'qtd': qtd_pafcs_a_revisar,
                    'url': f'/admin/pafc/pafc/?situacao__exact={PAFC.AGUARDANDO_REVISAO_TECNICA}&vinculo={VinculacaoFilter.MEUS_COMO_REVISOR}',
                }
            )

        # Validação do PAFC (responsabilidade dos validadores)
        qtd_pafcs_a_validar = PAFC.objects.filter(situacao=PAFC.AGUARDANDO_VALIDACAO, validadorpafc__servidor=servidor).distinct().count()
        if qtd_pafcs_a_validar:
            pendencias.append(
                {
                    'titulo': f'PAFC{pluralize(qtd_pafcs_a_validar)}',
                    'subtitulo': 'a validar',
                    'qtd': qtd_pafcs_a_validar,
                    'url': f'/admin/pafc/pafc/?situacao__exact={PAFC.AGUARDANDO_VALIDACAO}&vinculo={VinculacaoFilter.MEUS_COMO_VALIDADOR}',
                }
            )

        # Parecer da pró-reitoria (responsabilidade do pró-reitor)
        qtd_pareceres_proreitoria_pendentes = (
            PAFC.objects.filter(situacao=PAFC.EM_ANALISE_PROREITORIA, proreitoria__setor_id=vinculo_usuario.setor_id)
            .exclude(
                documentos_emitidos__situacao_pafc=PAFC.EM_ANALISE_PROREITORIA,
                documentos_emitidos__documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            )
            .distinct()
            .count()
        )
        if qtd_pareceres_proreitoria_pendentes:
            pendencias.append(
                {
                    'titulo': f'Parecer{pluralize(qtd_pareceres_proreitoria_pendentes, "es")} da Pró-Reitoria',
                    'subtitulo': f'a emitir para PAFC{pluralize(qtd_pareceres_proreitoria_pendentes)}',
                    'qtd': qtd_pareceres_proreitoria_pendentes,
                    'url': '/admin/pafc/pafc/'
                    f'?vinculo={VinculacaoFilter.MEUS_COMO_PROREITOR}'
                    f'&situacao__exact={PAFC.EM_ANALISE_PROREITORIA}'
                    f'&pendencia={PendenciaFilter.SEM_PARECER_PROREITORIA}',
                }
            )

        # PENDÊNCIAS DA CÂMARA
        # Data da reunião (responsabilidade do coordenador ou secretário)
        qtd_pafs_sem_data_reuniao_camara = (
            PAFC.objects.filter(
                Q(situacao=PAFC.AGUARDANDO_APROVACAO_CAMARA, decisao_camara__isnull=True, data_convocacao_camara__isnull=True),
                Q(camara__coordenador=servidor) | Q(camara__secretario=servidor),
            )
            .distinct()
            .count()
        )
        if qtd_pafs_sem_data_reuniao_camara:
            pendencias.append(
                {
                    'titulo': f'PAFC{pluralize(qtd_pafs_sem_data_reuniao_camara)}',
                    'subtitulo': 'a definir data de reunião da Câmara',
                    'qtd': qtd_pafs_sem_data_reuniao_camara,
                    'url': '/admin/pafc/pafc/'
                    f'?vinculo={VinculacaoFilter.MEUS_COMO_INTEGR_CAMARA}'
                    f'&situacao__exact={PAFC.AGUARDANDO_APROVACAO_CAMARA}'
                    f'&pendencia={PendenciaFilter.SEM_DATA_REUNIAO_CAMARA}',
                }
            )

        # Parecer (responsabilidade do coordenador ou secretário)
        qtd_pareceres_camara_pendentes = (
            PAFC.objects.filter(
                Q(situacao=PAFC.AGUARDANDO_APROVACAO_CAMARA, decisao_camara__isnull=True, data_convocacao_camara__lte=hoje),
                Q(camara__coordenador=servidor) | Q(camara__secretario=servidor),
            )
            .exclude(
                documentos_emitidos__situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CAMARA,
                documentos_emitidos__documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            )
            .distinct()
            .count()
        )
        if qtd_pareceres_camara_pendentes:
            pendencias.append(
                {
                    'titulo': f'Parecer{pluralize(qtd_pareceres_camara_pendentes, "es")} da Câmara',
                    'subtitulo': f'a emitir para PAFC{pluralize(qtd_pareceres_camara_pendentes)}',
                    'qtd': qtd_pareceres_camara_pendentes,
                    'url': '/admin/pafc/pafc/'
                    f'?vinculo={VinculacaoFilter.MEUS_COMO_INTEGR_CAMARA}'
                    f'&situacao__exact={PAFC.AGUARDANDO_APROVACAO_CAMARA}'
                    f'&pendencia={PendenciaFilter.SEM_PARECER_CAMARA}',
                }
            )

        # PENDÊNCIAS DOS CONSELHOS
        # Data da reunião (responsabilidade do secretário)
        id_setor_secretaria_conselhos = Configuracao.get_valor_por_chave('ppc', 'setor_secretaria_conselhos')
        eh_secretario = id_setor_secretaria_conselhos and vinculo_usuario.setor_id == int(id_setor_secretaria_conselhos)
        if eh_secretario:
            qtd_pafs_sem_data_reuniao_consepex = (
                PAFC.objects.filter(
                    situacao=PAFC.AGUARDANDO_APROVACAO_CONSEPEX,
                    decisao_consepex__isnull=True,
                    data_convocacao_consepex__isnull=True,
                )
                .distinct()
                .count()
            )
            if qtd_pafs_sem_data_reuniao_consepex:
                pendencias.append(
                    {
                        'titulo': f'PAFC{pluralize(qtd_pafs_sem_data_reuniao_consepex)}',
                        'subtitulo': 'a definir data de reunião do CONSEPEX',
                        'qtd': qtd_pafs_sem_data_reuniao_consepex,
                        'url': '/admin/pafc/pafc/'
                        f'?situacao__exact={PAFC.AGUARDANDO_APROVACAO_CONSEPEX}'
                        f'&pendencia={PendenciaFilter.SEM_DATA_REUNIAO_CONSEPEX}',
                    }
                )
            qtd_pafs_sem_data_reuniao_consup = (
                PAFC.objects.filter(
                    situacao=PAFC.AGUARDANDO_APROVACAO_CONSUP,
                    decisao_consup__isnull=True,
                    data_convocacao_consup__isnull=True,
                )
                .distinct()
                .count()
            )
            if qtd_pafs_sem_data_reuniao_consup:
                pendencias.append(
                    {
                        'titulo': f'PAFC{pluralize(qtd_pafs_sem_data_reuniao_consup)}',
                        'subtitulo': 'a definir data de reunião do CONSUP',
                        'qtd': qtd_pafs_sem_data_reuniao_consup,
                        'url': '/admin/pafc/pafc/'
                        f'?situacao__exact={PAFC.AGUARDANDO_APROVACAO_CONSUP}'
                        f'&pendencia={PendenciaFilter.SEM_DATA_REUNIAO_CONSUP}',
                    }
                )

        # Deliberação e Resolução (responsabilidade do presidente e secretário)
        diretoria = Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA).first()
        eh_presidente = diretoria and UsuarioGrupo.objects.filter(user=request.user, group__name='Reitor', setores=diretoria.setor).exists()
        if eh_presidente:
            qtd_solicitacoes = SolicitacaoTramitacaoAdReferendumPAFC.objects.filter(deferida__isnull=True).count()
            if qtd_solicitacoes:
                pendencias.append(
                    {
                        'titulo': f'Solicitaç{pluralize(qtd_solicitacoes, "ão,ões")} de tramitação Ad Referendum de PAFC',
                        'subtitulo': f'a ser{pluralize(qtd_solicitacoes, "em")} avaliada{pluralize(qtd_solicitacoes)}',
                        'qtd': qtd_solicitacoes,
                        'url': f'{reverse("admin:pafc_solicitacaotramitacaoadreferendumpafc_changelist")}?deferida__isnull=True',
                    }
                )

        if eh_secretario or eh_presidente:
            # Deliberação do CONSEPEX
            qtd_deliberacoes_consepex_pendentes = (
                PAFC.objects.filter(
                    situacao=PAFC.AGUARDANDO_APROVACAO_CONSEPEX,
                    data_convocacao_consepex__lte=hoje,
                )
                .exclude(
                    documentos_emitidos__documento__tipo=DocumentoHibrido.DELIBERACAO,
                    documentos_emitidos__situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX,
                    documentos_emitidos__documento__situacao__in=[DocumentoHibrido.DOCUMENTO_CRIADO, DocumentoHibrido.DOCUMENTO_FINALIZADO],
                )
                .distinct()
                .count()
            )
            if qtd_deliberacoes_consepex_pendentes:
                pendencias.append(
                    {
                        'titulo': f'PAFC{pluralize(qtd_deliberacoes_consepex_pendentes)}',
                        'subtitulo': f'a emitir deliberaç{pluralize(qtd_deliberacoes_consepex_pendentes, "ão,ões")} do CONSEPEX',
                        'qtd': qtd_deliberacoes_consepex_pendentes,
                        'url': '/admin/pafc/pafc/'
                        f'?situacao__exact={PAFC.AGUARDANDO_APROVACAO_CONSEPEX}'
                        f'&pendencia={PendenciaFilter.SEM_DELIBERACAO_CONSEPEX}',
                    }
                )

            # Resolução do CONSUP
            qtd_resolucoes_consup_pendentes = (
                PAFC.objects.filter(
                    situacao=PAFC.AGUARDANDO_APROVACAO_CONSUP,
                    data_convocacao_consup__lte=hoje,
                )
                .exclude(
                    documentos_emitidos__documento__tipo=DocumentoHibrido.RESOLUCAO,
                    documentos_emitidos__situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSUP,
                    documentos_emitidos__documento__situacao__in=[DocumentoHibrido.DOCUMENTO_CRIADO, DocumentoHibrido.DOCUMENTO_FINALIZADO],
                )
                .distinct()
                .count()
            )
            if qtd_resolucoes_consup_pendentes:
                pendencias.append(
                    {
                        'titulo': f'PAFC{pluralize(qtd_resolucoes_consup_pendentes)}',
                        'subtitulo': f'a emitir resoluç{pluralize(qtd_resolucoes_consup_pendentes, "ão,ões")} do CONSUP',
                        'qtd': qtd_resolucoes_consup_pendentes,
                        'url': f'/admin/pafc/pafc/?situacao__exact={PAFC.AGUARDANDO_APROVACAO_CONSUP}&pendencia={PendenciaFilter.SEM_RESOLUCAO_CONSUP}',
                    }
                )

    return pendencias


@permission_required('pafc.view_modelopafc')
@rtr()
def modelo_pafc(request, pk):
    modelo = ModeloPAFC.objects.get(id=pk)
    title = f'Modelo {modelo.descricao}'

    secoes = list(modelo.secao_set.prefetch_related(Prefetch('conteudo_set', to_attr='conteudos')))
    possui_secoes = len(secoes) > 0
    qtd_conteudos = reduce(lambda acc, secao: acc + len(secao.conteudos), secoes, 0)

    marcadores = ModeloPAFC.get_marcadores()
    return locals()


@permission_required('pafc.add_modelopafc')
@rtr()
def replicar_modelo_pafc(request, pk):
    modelo = ModeloPAFC.objects.get(id=pk)
    title = f'Replicar Modelo de PAFC {modelo.descricao}'
    form = ReplicarModeloPAFCForm(data=request.POST or None)
    if form.is_valid():
        replicado = form.replicar(modelo)
        return httprr(replicado.get_absolute_url(), 'Modelo de PAFC replicado com sucesso.')
    return locals()


@permission_required('pafc.view_modelopafc')
@rtr()
def visualizar_modelopafc(request, pk):
    modelo = ModeloPAFC.objects.get(id=pk)
    title = f'Modelo de PAFC: {modelo.descricao}'
    return locals()


@documento(enumerar_paginas=True)
@permission_required('pafc.view_modelopafc')
@rtr('pafc_pdf.html')
def minuta_modelopafc_pdf(request, pk):
    modelo = ModeloPAFC.objects.get(id=pk)
    title = f'Modelo de PAFC: {modelo.descricao}'
    pafc = {
        'modelo': modelo,
        'nome_curso': '[Nome do Curso]',
        'modalidade': '[Modalidade]',
        'setor': {'uo': {'nome': 'Campus XXX', 'sigla': 'CX'}},
        'data_aprovacao': datetime.date.today(),
        'get_texto_aprovacoes': '((texto das aprovações))',
        'reitor': {'pessoa_fisica': {'nome': 'Nome do Reitor'}},
        'pro_reitor_ensino': {'pessoa_fisica': {'nome': 'Nome do Pró-Reitor'}},
        'pro_reitor_extensao': {'pessoa_fisica': {'nome': 'Nome do Pró-Reitor'}},
        'pro_reitor_pesquisa': {'pessoa_fisica': {'nome': 'Nome do Pró-Reitor'}},
        'diretor_geral': {'pessoa_fisica': {'nome': 'Nome do Diretor-Geral'}},
        'diretor_academico': {'pessoa_fisica': {'nome': 'Nome do Diretor Acadêmico'}},
        'coordenador_extensao': {'pessoa_fisica': {'nome': 'Nome do Coordenador de Extensão do Campus'}},
        'coordenador_pesquisa': {'pessoa_fisica': {'nome': 'Nome do Coordenador de Pesquisa do Campus'}},
        'coordenador_curso': {'pessoa_fisica': {'nome': 'Nome do Coordenador do Curso'}},
        'membrocomissaopafc_set': {
            'all': [
                {'servidor': {'pessoa_fisica': {'nome': 'Nome do Membro Coordenador'}}},
                {'servidor': {'pessoa_fisica': {'nome': 'Nome do Membro 2'}}},
                {'servidor': {'pessoa_fisica': {'nome': 'Nome do Membro 3'}}},
            ]
        },
        'colaboradores': {
            'exists': True,
            'all': [
                {'nome': '(opcional)'},
            ],
        },
        'revisortecnicopafc_set': {
            'all': [
                {'servidor': {'pessoa_fisica': {'nome': 'Nome do Revisor Coordenador'}}},
                {'servidor': {'pessoa_fisica': {'nome': 'Nome do Revisor 2'}}},
                {'servidor': {'pessoa_fisica': {'nome': 'Nome do Revisor 3'}}},
            ]
        },
        'get_secoes': modelo.get_secoes(),
    }
    minuta = True
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    return locals()


@permission_required('pafc.add_modelopafc')
@rtr()
def adicionar_secao(request, pk):
    title = 'Adicionar Seção'
    form = SecaoForm(data=request.POST or None, modelo_pafc_id=pk)
    if form.is_valid():
        form.save()
        return httprr(f'/pafc/modelo_pafc/{pk}/', 'Seção adicionada com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.add_modelopafc')
@rtr()
def editar_secao(request, pk):
    secao = Secao.objects.get(id=pk)
    title = 'Editar Seção'
    form = SecaoForm(data=request.POST or None, instance=secao)
    if form.is_valid():
        form.save()
        return httprr(secao.modelo_pafc.get_absolute_url(), 'Seção atualizada com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.add_modelopafc')
@rtr()
def adicionar_conteudo(request, pk):
    title = 'Adicionar Conteúdo'
    form = ConteudoForm(data=request.POST or None, modelo_pafc_id=pk)
    if form.is_valid():
        form.save()
        return httprr(f'/pafc/modelo_pafc/{pk}/', 'Conteúdo adicionado com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.add_modelopafc')
@rtr()
def editar_conteudo(request, pk):
    conteudo = Conteudo.objects.get(id=pk)
    title = 'Editar Conteúdo'
    form = ConteudoForm(data=request.POST or None, instance=conteudo)
    if form.is_valid():
        form.save()
        return httprr(conteudo.secao.modelo_pafc.get_absolute_url(), 'Conteúdo atualizado com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def pafc(request, pk):
    obj = get_object_or_404(PAFC, pk=pk)
    url = f'/pafc/pafc/{obj.pk}/'
    title = f'PAFC: {obj}'
    # Verifica se documentos associados já foram finalizados e atualiza dados do PAFC caso necessário.
    obj.atualizar_situacoes()
    camara = obj.camara
    documentos_emissao = obj.get_documentos_para_emissao(request.user)
    comentarios_servidores = obj.comentarios_gerais.filter(escopo=ComentarioGeralPAFC.ESCOPO_SERVIDORES)
    comentarios_instalacoes = obj.comentarios_gerais.filter(escopo=ComentarioGeralPAFC.ESCOPO_INSTALACOES)
    comentarios_matrizes = obj.comentarios_gerais.filter(escopo=ComentarioGeralPAFC.ESCOPO_MATRIZES)
    comentarios_bibliografia = obj.comentarios_gerais.filter(escopo=ComentarioGeralPAFC.ESCOPO_BIBLIOGRAFIA)
    comentarios_infraestrutura_ead = obj.comentarios_gerais.filter(escopo=ComentarioGeralPAFC.ESCOPO_INFRAESTRUTURA_EAD)
    existem_comentarios_servidores_pendentes = comentarios_servidores.filter(resolvido=False).exists()
    existem_comentarios_instalacoes_pendentes = comentarios_instalacoes.filter(resolvido=False).exists()
    existem_comentarios_matrizes_pendentes = comentarios_matrizes.filter(resolvido=False).exists()
    existem_comentarios_bibliografia_pendentes = comentarios_bibliografia.filter(resolvido=False).exists()
    existem_comentarios_infraestrutura_ead_pendentes = comentarios_infraestrutura_ead.filter(resolvido=False).exists()

    if obj.is_pafc_adequacao() and obj.numero_vagas_curso is not None:
        quantidade_de_vagas_aumentou = obj.numero_vagas_curso > (obj.curso.quantidade_vagas or 0)
        quantidade_de_vagas_diminuiu = obj.numero_vagas_curso < (obj.curso.quantidade_vagas or 0)
    secoes = list(obj.get_secoes())
    tem_secao = len(secoes) > 0
    is_equipe_definida = obj.membrocomissaopafc_set.exists() and obj.revisortecnicopafc_set.exists() and obj.validadorpafc_set.exists()
    is_servidores_definidos = obj.is_servidores_definidos
    is_instalacoes_definidas = obj.is_instalacoes_definidas
    is_tutores_definidos = obj.is_tutores_definidos
    is_infraestrutura_ead_definida = obj.is_infraestrutura_ead_definida
    is_matrizes_pomc_definidos = obj.is_matrizes_definidas and obj.is_pomc_definido
    matrizes = list(obj.matrizpafc_set.all())
    laboratorios = list(
        obj.salas.annotate(
            mesmo_campus=Case(
                When(predio__uo__in=[obj.setor.uo, obj.setor.uo.equivalente], then=Value(True)), default=Value(False), output_field=BooleanField()
            )
        )
        .order_by('-mesmo_campus', 'nome')
        .all()
    )
    infraestruturas_externas = list(obj.infraestruturas_externas.all())
    is_bibliografia_definida = obj.is_bibliografia_definida
    quantitativos_bibliografia_informados = BibliografiaPAFC.quantitativos_foram_informados(obj)
    is_documentos_anexados = not (obj.em_analise_preliminar() or obj.em_revisao_tecnica()) or bool(
        obj.em_analise_preliminar() and obj.relatorio_analise_preliminar or obj.em_revisao_tecnica() and obj.ficha_revisao_tecnica
    )
    bibliografias = list(obj.bibliografiapafc_set.all())
    conteudos = obj.get_conteudos()
    if obj.em_revisao_tecnica():
        aba_conteudo_foi_resolvida = obj.percentual_revisao_tecnica == 100
    elif obj.em_validacao():
        aba_conteudo_foi_resolvida = obj.percentual_validacao == 100
    else:
        aba_conteudo_foi_resolvida = obj.percentual_elaboracao == 100
    servidor = request.user.get_relacionamento()
    pode_pre_visualizar = obj.situacao >= PAFC.EM_ELABORACAO
    tem_permissao_administrador = obj.tem_permissao_administrador(request.user)
    tem_permissao_edicao = obj.tem_permissao_edicao(request.user)
    is_diretor_academico = obj.is_diretor_academico(request.user)
    is_elaborador = obj.is_elaborador(request.user)
    is_elaborador_coordenador = obj.is_elaborador_coordenador(request.user)
    pode_editar = obj.pode_editar(request.user)
    is_revisor_tecnico = obj.is_revisor_tecnico(request.user)
    is_validador = obj.is_validador(request.user)
    pode_elaborar = obj.pode_elaborar(request.user)
    pode_enviar_para_validacao = obj.pode_enviar_para_validacao(request.user)
    pode_marcar_tudo_como_revisado = obj.pode_marcar_tudo_como_revisado(request.user)
    pode_ter_planos_revisados_em_massa = PlanoDisciplinaModificado.revisao_pode_ser_realizada_em_massa(obj)
    pode_solicitar_portaria_comissao_elaboracao = obj.pode_solicitar_portaria_comissao_elaboracao(request.user)
    pode_convocar_camara = obj.pode_convocar_camara(request.user)
    pode_convocar_consepex = obj.pode_convocar_consepex(request.user)
    pode_convocar_consup = obj.pode_convocar_consup(request.user)
    pode_solicitar_tramitacao_ad_referendum = obj.pode_solicitar_tramitacao_ad_referendum(request.user)
    pode_solicitar_correcao_nos_conselhos = obj.pode_solicitar_correcao_nos_conselhos(request.user)
    pode_emitir_aprovacoes_conselhos = obj.pode_emitir_aprovacoes_conselhos()
    pode_visualizar_solicitacoes_tramitacao_ad_referendum = SolicitacaoTramitacaoAdReferendumPAFC.usuario_pode_visualizar(request.user)

    pode_criar_curso = obj.pode_criar_curso(request.user)
    pode_ter_curso_criado = obj.pode_ter_curso_criado()
    pode_atualizar_curso = obj.pode_atualizar_curso(request.user)
    pode_ter_curso_atualizado = obj.pode_ter_curso_atualizado()
    pode_finalizar = obj.pode_finalizar(request.user)
    pode_ser_finalizado = obj.pode_ser_finalizado()

    pendencias = obj.get_pendencias(request.user)
    movimentacoes = list(obj.movimentacaopafc_set.order_by('-data').all())
    marcadores = ModeloPAFC.get_marcadores()
    if not obj.requer_cadastro_de_polos():
        marcadores.pop(ModeloPAFC.MARCADOR_POLOS)
    if not obj.requer_cadastro_de_tutores():
        marcadores.pop(ModeloPAFC.MARCADOR_TUTORES)

    solicitacoes_tramitacao_ad_referendum_consepex = list(
        obj.solicitacoes_tramitacao_ad_referendum.filter(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX).all()
    )
    solicitacoes_tramitacao_ad_referendum_consup = list(
        obj.solicitacoes_tramitacao_ad_referendum.filter(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSUP).all()
    )

    # DOCUMENTOS
    documentos_emitidos = DocumentoEmitidoPAFC.objects.filter(pafc_id=pk).order_by('-documento__tipo', '-data_emissao')

    abas_com_pendencias = []
    if not is_servidores_definidos and obj.em_elaboracao():
        abas_com_pendencias.append('Servidores')
    if not is_instalacoes_definidas and obj.em_elaboracao():
        abas_com_pendencias.append('Instalações e Equipamentos')
    if obj.modelo.possui_ch_ead() and not is_infraestrutura_ead_definida and obj.em_elaboracao():
        abas_com_pendencias.append('Infraestrutura EaD')
    if not is_matrizes_pomc_definidos and obj.em_elaboracao():
        abas_com_pendencias.append('Matrizes')
    if not is_bibliografia_definida and obj.em_elaboracao():
        abas_com_pendencias.append('Bibliografia')
    if not is_documentos_anexados:
        abas_com_pendencias.append('Documentos')

    acao = request.GET.get('acao')
    if acao == 'enviar_para_analise_preliminar' and tem_permissao_edicao and obj.pode_ser_enviado_para_analise_preliminar():
        obj.enviar_para_analise_preliminar(request.user)
        return httprr(f'{url}?tab=conteudo', 'Ação realizada com sucesso')
    if acao == 'enviar_para_revisao_tecnica' and tem_permissao_edicao and obj.pode_ser_enviado_para_revisao_tecnica():
        obj.enviar_para_revisao_tecnica(request.user)
        return httprr(f'{url}?tab=conteudo', 'Ação realizada com sucesso')
    if acao == 'devolver_para_elaboracao' and tem_permissao_edicao and obj.pode_ser_devolvido_para_elaboracao:
        obj.devolver_para_elaboracao(request.user)
        return httprr(f'{url}?tab=conteudo', 'Ação realizada com sucesso')
    if acao == 'enviar_para_validacao' and pode_enviar_para_validacao and obj.pode_ser_enviado_para_validacao():
        obj.enviar_para_validacao(request.user)
        return httprr(f'{url}?tab=conteudo', 'Ação realizada com sucesso')
    if acao == 'marcar_tudo_como_revisado' and pode_marcar_tudo_como_revisado:
        obj.marcar_todas_as_secoes_como_revisadas(request.user)
        return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if acao == 'marcar_tudo_como_validado' and obj.em_validacao() and tem_permissao_edicao:
        obj.marcar_todas_as_secoes_como_validadas(request.user)
        return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if (
        acao == 'solicitar_portaria_comissao_elaboracao'
        and pode_solicitar_portaria_comissao_elaboracao
        and obj.pode_ter_portaria_comissao_elaboracao_solicitada()
    ):
        obj.solicitar_portaria_comissao_elaboracao(request.user)
        return httprr(url, 'Ação realizada com sucesso')
    if request.GET.get('iniciar_edicao'):
        secao = obj.get_secoes().get(pk=request.GET.get('iniciar_edicao'))
        if secao.pode_ter_edicao_iniciada() and (is_elaborador and tem_permissao_edicao or tem_permissao_administrador):
            secao.iniciar_edicao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('liberar_edicao'):
        secao = obj.get_secoes().get(pk=request.GET.get('liberar_edicao'))
        if secao.pode_ter_edicao_liberada() and (is_elaborador and tem_permissao_edicao or tem_permissao_administrador):
            secao.liberar_edicao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('concluir_edicao'):
        secao = obj.get_secoes().get(pk=request.GET.get('concluir_edicao'))
        if secao.pode_ter_edicao_concluida() and (is_elaborador and tem_permissao_edicao or tem_permissao_administrador):
            secao.concluir_edicao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('cancelar_conclusao_edicao'):
        secao = obj.get_secoes().get(pk=request.GET.get('cancelar_conclusao_edicao'))
        if secao.pode_cancelar_conclusao_edicao() and (is_elaborador and tem_permissao_edicao or tem_permissao_administrador):
            secao.cancelar_conclusao_edicao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('iniciar_revisao_tecnica'):
        secao = obj.get_secoes().get(pk=request.GET.get('iniciar_revisao_tecnica'))
        if secao.pode_ter_revisao_tecnica_iniciada() and (is_revisor_tecnico and tem_permissao_edicao or tem_permissao_administrador):
            secao.iniciar_revisao_tecnica(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('liberar_revisao_tecnica'):
        secao = obj.get_secoes().get(pk=request.GET.get('liberar_revisao_tecnica'))
        if secao.pode_ter_revisao_tecnica_liberada() and (is_revisor_tecnico and tem_permissao_edicao or tem_permissao_administrador):
            secao.liberar_revisao_tecnica(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('concluir_revisao_tecnica'):
        secao = obj.get_secoes().get(pk=request.GET.get('concluir_revisao_tecnica'))
        if secao.pode_ter_revisao_tecnica_concluida() and (is_revisor_tecnico and tem_permissao_edicao or tem_permissao_administrador):
            secao.concluir_revisao_tecnica(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('cancelar_conclusao_revisao_tecnica'):
        secao = obj.get_secoes().get(pk=request.GET.get('cancelar_conclusao_revisao_tecnica'))
        if secao.pode_cancelar_conclusao_revisao_tecnica() and (is_revisor_tecnico and tem_permissao_edicao or tem_permissao_administrador):
            secao.cancelar_conclusao_revisao_tecnica(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('marcar_como_validada'):
        secao = obj.get_secoes().get(pk=request.GET.get('marcar_como_validada'))
        if secao.pode_ter_validacao_iniciada() and (is_validador and tem_permissao_edicao or tem_permissao_administrador):
            secao.marcar_como_validada(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('iniciar_validacao'):
        secao = obj.get_secoes().get(pk=request.GET.get('iniciar_validacao'))
        if secao.pode_ter_validacao_iniciada() and (is_validador and tem_permissao_edicao or tem_permissao_administrador):
            secao.iniciar_validacao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('liberar_validacao'):
        secao = obj.get_secoes().get(pk=request.GET.get('liberar_validacao'))
        if secao.pode_ter_validacao_liberada() and (is_validador and tem_permissao_edicao or tem_permissao_administrador):
            secao.liberar_validacao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('concluir_validacao'):
        secao = obj.get_secoes().get(pk=request.GET.get('concluir_validacao'))
        if secao.pode_ter_validacao_concluida() and (is_validador and tem_permissao_edicao or tem_permissao_administrador):
            secao.concluir_validacao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')
    if request.GET.get('cancelar_conclusao_validacao'):
        secao = obj.get_secoes().get(pk=request.GET.get('cancelar_conclusao_validacao'))
        if secao.pode_cancelar_conclusao_validacao() and (is_validador and tem_permissao_edicao or tem_permissao_administrador):
            secao.cancelar_conclusao_validacao(request.user)
            return httprr(f'{url}?tab=conteudo#abas', 'Ação realizada com sucesso')

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_elaborador_pafc(request, pk):
    title = 'Editar elaborador'
    elaborador = get_object_or_404(MembroComissaoPAFC, pk=pk)
    if elaborador.pafc.pode_alterar_elaboradores(request.user):
        form = EditarMembroEquipePAFCForm(data=request.POST or None, instance=elaborador)
        if form.is_valid():
            form.save()
            return httprr('.', 'Elaborador atualizado com sucesso.', close_popup=True)
        return locals()
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def arquivar_pafc(request, pk):
    title = 'Arquivar PAFC'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.pode_ser_arquivado() or not pafc.pode_arquivar(request.user):
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        pafc.arquivar(request.user)
        return httprr('.', 'PAFC arquivado com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.change_pafc')
@rtr()
def finalizar_pafc(request, pk):
    title = 'Finalizar PAFC'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.pode_ser_finalizado() or not pafc.pode_finalizar(request.user):
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        pafc.finalizar(request.user)
        return httprr('.', 'PAFC finalizado com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_dados_do_curso(request, pk):
    title = 'Editar dados do curso'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_editado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = EditarDadosCursoForm(data=request.POST or None, request=request, instance=pafc)
    if form.is_valid():
        form.save()
        return httprr('..', 'Dados atualizados com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_revisortecnico_pafc(request, pk):
    title = 'Editar revisor técnico'
    revisor = get_object_or_404(RevisorTecnicoPAFC, pk=pk)
    if revisor.pafc.pode_alterar_revisores_tecnicos(request.user):
        form = EditarMembroEquipePAFCForm(data=request.POST or None, instance=revisor)
        if form.is_valid():
            form.save()
            return httprr('.', 'Revisor atualizado com sucesso.', close_popup=True)
        return locals()
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def editar_validador_pafc(request, pk):
    title = 'Editar validador'
    revisor = get_object_or_404(ValidadorPAFC, pk=pk)
    if revisor.pafc.pode_alterar_validadores(request.user):
        form = EditarMembroEquipePAFCForm(data=request.POST or None, instance=revisor)
        if form.is_valid():
            form.save()
            return httprr('.', 'Revisor atualizado com sucesso.', close_popup=True)
        return locals()
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def adicionar_secaopafc(request, pk):
    title = 'Adicionar Seção'
    obj = PAFC.objects.get(pk=pk)
    if not obj.is_elaborador(request.user):
        return HttpResponseForbidden()
    form = SecaoPAFCForm(data=request.POST or None, pafc_id=pk)
    if form.is_valid():
        form.save()
        return httprr(f'/pafc/pafc/{pk}/', 'Seção adicionada com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_secaopafc(request, pk):
    secao = SecaoPAFC.objects.get(id=pk)
    title = 'Editar Seção'
    if not secao.pafc.is_elaborador(request.user):
        return HttpResponseForbidden()
    form = SecaoPAFCForm(data=request.POST or None, instance=secao)
    if form.is_valid():
        form.save()
        return httprr(secao.pafc.get_absolute_url(), 'Seção atualizada com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def adicionar_conteudopafc(request, pk):
    title = 'Adicionar Conteúdo'
    obj = PAFC.objects.get(pk=pk)
    if not obj.is_elaborador(request.user):
        return HttpResponseForbidden()
    form = ConteudoPAFCForm(data=request.POST or None, pafc_id=pk)
    if form.is_valid():
        form.save()
        return httprr(f'/pafc/pafc/{pk}/', 'Conteúdo adicionado com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_conteudopafc(request, pk):
    title = 'Editar Conteúdo'
    conteudo = ConteudoPAFC.objects.get(id=pk)
    pafc = conteudo.secao.pafc
    if not conteudo.editavel or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = ConteudoPAFCForm(data=request.POST or None, instance=conteudo)
    if form.is_valid():
        form.save()
        return httprr(conteudo.secao.pafc.get_absolute_url(), 'Conteúdo atualizado com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def fazer_observacao_conteudo(request, pk):
    title = 'Fazer observação'
    conteudo = ConteudoPAFC.objects.get(id=pk)

    pafc = conteudo.secao.pafc
    is_revisor = pafc.is_revisor_tecnico(request.user)
    is_validador = pafc.is_validador(request.user)

    if not (
        is_validador
        and pafc.em_analise_preliminar()
        or is_revisor
        and pafc.em_revisao_tecnica()
        or is_validador
        and pafc.em_validacao()
        and not pafc.parecer_validacao_ja_foi_emitido
    ):
        return HttpResponseForbidden()

    form = ComentarioRevisaoForm(data=request.POST or None, request=request, conteudo=conteudo)
    if form.is_valid():
        form.save()
        return httprr('..', 'Observação registrada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def resolver_observacao_conteudo(request, pk):
    title = 'Marcar comentário como resolvido'
    comentario = ComentarioRevisao.objects.get(id=pk)
    pafc = comentario.conteudo.secao.pafc
    if comentario.resolvido or not pafc.is_elaborador(request.user) or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        comentario.resolvido = True
        comentario.resolvido_por = request.user.get_relacionamento()
        comentario.data_resolucao = datetime.datetime.now()
        comentario.save()
        return httprr('..', 'Observação resolvida com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_observacao_conteudo(request, pk):
    comentario = ComentarioRevisao.objects.get(id=pk)
    pafc = comentario.conteudo.secao.pafc
    if (
        comentario.resolvido
        or comentario.servidor is None
        or comentario.servidor != request.user.get_relacionamento()
        or not (pafc.em_analise_preliminar() or pafc.em_revisao_tecnica() or pafc.em_validacao())
    ):
        return HttpResponseForbidden()
    secao = comentario.conteudo.secao
    comentario.delete()
    return httprr(f'{reverse("pafc", args=(secao.pafc.pk,))}?tab=conteudo#abas', 'Comentário removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def adicionar_comentario_geral(request, pafc_id, tipo):
    title = 'Adicionar comentário'
    pafc = get_object_or_404(PAFC, pk=pafc_id)

    is_revisor = pafc.is_revisor_tecnico(request.user)
    is_validador = pafc.is_validador(request.user)

    if not (
        is_validador
        and pafc.em_analise_preliminar()
        or is_revisor
        and pafc.em_revisao_tecnica()
        or is_validador
        and pafc.em_validacao()
        and not pafc.parecer_validacao_ja_foi_emitido
    ):
        return HttpResponseForbidden()

    escopos_comentario = {
        'servidores': ComentarioGeralPAFC.ESCOPO_SERVIDORES,
        'instalacoes': ComentarioGeralPAFC.ESCOPO_INSTALACOES,
        'matrizes': ComentarioGeralPAFC.ESCOPO_MATRIZES,
        'bibliografia': ComentarioGeralPAFC.ESCOPO_BIBLIOGRAFIA,
        'infraestrutura-ead': ComentarioGeralPAFC.ESCOPO_INFRAESTRUTURA_EAD,
    }

    if tipo not in escopos_comentario:
        return HttpResponseBadRequest(f'Tipo inválido: {tipo}.')
    form = ComentarioGeralForm(
        data=request.POST or None,
        pafc=pafc,
        request=request,
        escopo=escopos_comentario[tipo],
    )
    if form.is_valid():
        form.save()
        return httprr('..', 'Comentário registrado com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def resolver_comentario_geral(request, comentario_id):
    title = 'Marcar comentário como resolvido'
    comentario = get_object_or_404(ComentarioGeralPAFC, pk=comentario_id)
    pafc = comentario.pafc
    if comentario.resolvido or not pafc.em_elaboracao() or not pafc.is_elaborador(request.user):
        return HttpResponseForbidden()
    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        comentario.resolvido = True
        comentario.resolvido_por = request.user.get_relacionamento()
        comentario.data_resolucao = datetime.datetime.now()
        comentario.save()
        return httprr('..', 'Comentário resolvido com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_comentario_geral(request, comentario_id):
    comentario = get_object_or_404(ComentarioGeralPAFC, pk=comentario_id)
    pafc: PAFC = comentario.pafc
    if (
        comentario.resolvido
        or comentario.servidor is None
        or comentario.servidor != request.user.get_relacionamento()
        or not (pafc.em_analise_preliminar() or pafc.em_revisao_tecnica() or pafc.em_validacao())
    ):
        return HttpResponseForbidden()
    tab = {
        ComentarioGeralPAFC.ESCOPO_SERVIDORES: 'servidores',
        ComentarioGeralPAFC.ESCOPO_INSTALACOES: 'instalacoes',
        ComentarioGeralPAFC.ESCOPO_MATRIZES: 'matrizes',
        ComentarioGeralPAFC.ESCOPO_BIBLIOGRAFIA: 'bibliografia',
        ComentarioGeralPAFC.ESCOPO_INFRAESTRUTURA_EAD: 'infraestrutura_ead',
    }[comentario.escopo]
    comentario.delete()
    return httprr(f'{reverse("pafc", args=(pafc.pk,))}?tab={tab}', 'Comentário removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def visualizar_conteudo_pafc(request, pk):
    pafc = PAFC.objects.get(pk=pk)
    title = f'PAFC: {pafc.nome_curso}'
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def historico_conteudo_pafc(request, pk):
    title = 'Histórico de alterações'

    conteudo_pafc = get_object_or_404(ConteudoPAFC, pk=pk)

    logs_conteudo = Log.objects.filter(app='pafc', modelo='ConteudoPAFC', ref=pk)
    for log in logs_conteudo:
        diferencas = RegistroDiferenca.objects.filter(log=log).values_list('valor_anterior', 'valor_atual')
        log.anterior = '<br>'.join(diff[0] for diff in diferencas)
        log.novo = '<br>'.join(diff[1] for diff in diferencas)

    logs_secao = Log.objects.filter(app='pafc', modelo='SecaoPAFC', ref=conteudo_pafc.secao_id)

    logs_comentarios = Log.objects.filter(
        app='pafc',
        modelo='ComentarioRevisao',
        ref__in=ComentarioRevisao.objects.filter(conteudo_id=pk).values_list('pk', flat=True),
    )

    logs = list(logs_conteudo) + list(logs_comentarios) + list(logs_secao)
    return locals()


@permission_required('pafc.view_pafc')
def minuta_pafc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    if pafc.is_finalizado():
        return httprr(reverse('pafc', args=(pk,)), 'Não é possível visualizar a minuta do PAFC em pdf uma vez que o mesmo está aprovado.', 'error')
    return tasks.gerar_minuta_pafc(request, pafc)


@documento(enumerar_paginas=True)
@permission_required('pafc.view_pafc')
@rtr('pafc_pdf.html')
def minuta_pafc_pdf(request, pafc):
    title = 'PAFC'
    minuta = True
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    return locals()


@documento(tipo_para_verificacao='Projetos de autorização de funcionamento de cursos', modelo='pafc.pafc', enumerar_paginas=True)
@permission_required('pafc.view_pafc')
@rtr('pafc_pdf.html')
def pafc_pdf(request, pk):
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.is_finalizado():
        return httprr(reverse('pafc', args=(pk,)), 'Não é possível visualizar o PAFC em pdf enquanto o projeto não estiver aprovado.', 'error')
    title = 'Minuta do PAFC'
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_colaboradores(request, pk):
    title = 'Informar colaboradores'
    obj = PAFC.objects.get(pk=pk)
    if not obj.pode_ter_colaboradores_editados() or not obj.pode_alterar_colaboradores(request.user):
        return HttpResponseForbidden()
    form = InformarColaboradoresForm(data=request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_colaborador(request, pafc_pk, colaborador_pk):
    pafc = get_object_or_404(PAFC, pk=pafc_pk)
    if not pafc.pode_ter_colaboradores_editados() or not pafc.pode_alterar_colaboradores(request.user):
        return HttpResponseForbidden('Você não tem permissão para isso.')
    colaborador = pafc.colaboradores.filter(pk=colaborador_pk).first()
    if not colaborador:
        return HttpResponseBadRequest('O colaborador não está associado ao PAFC.')
    pafc.colaboradores.remove(colaborador)
    MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, f'Colaborador removido: {colaborador}.')
    return httprr(f'{pafc.get_absolute_url()}?tab=equipe', 'Colaborador removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def informar_coordenador_curso(request, pk):
    title = 'Informar Coordenador do Curso'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = InformarCoordenadorCursoForm(data=request.POST or None, request=request, instance=pafc)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_coordenador_curso(request, pk):
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    pafc.coordenador_curso = None
    pafc.save()

    MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, 'Coordenador de curso removido.')
    return httprr(f'{pafc.get_absolute_url()}?tab=servidores', 'Coordenador removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def informar_tecnicos_administrativos(request, pk):
    title = 'Informar Técnicos Administrativos'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = InformarTecnicosAdministrativosForm(data=request.POST or None, instance=pafc, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def justificar_indisponibilidade_tecnicos_administrativos(request, pk):
    title = 'Justificar indisponibilidade de Técnicos Administrativos'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()

    form = modelform_factory(model=PAFC, form=ModelFormPlus, fields=('justificativa_indisponibilidade_tecnicos_administrativos',))(
        request=request,
        instance=pafc,
        data=request.POST or None,
    )
    form.fields['justificativa_indisponibilidade_tecnicos_administrativos'].required = True

    if form.is_valid():
        form.save()
        return httprr('..', 'Justificativa registrada com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_justificativa_indisponibilidade_tecnicos_administrativos(request, pk):
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()

    pafc.justificativa_indisponibilidade_tecnicos_administrativos = None
    pafc.save()
    return httprr(f'{pafc.get_absolute_url()}?tab=servidores', 'Justificativa removida com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def remover_tecnico_administrativo(request, pafc_pk, tecnico_pk):
    pafc = get_object_or_404(PAFC, pk=pafc_pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden('Você não tem permissão para isso.')
    tecnico = pafc.tecnicos_administrativos.filter(pk=tecnico_pk).first()
    if not tecnico:
        return HttpResponseBadRequest('O servidor não está associado ao PAFC.')
    pafc.tecnicos_administrativos.remove(tecnico)
    MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, f'Técnico-Administrativo removido: {tecnico}.')
    return httprr(f'{pafc.get_absolute_url()}?tab=servidores', 'Servidor técnico-administrativo removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def editar_docentes_disciplina(request, pafc_pk, disciplina_pk):
    pafc = get_object_or_404(PAFC, pk=pafc_pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    disciplina = get_object_or_404(pafc.disciplinas, pk=disciplina_pk)
    title = f'Atribuir docentes à disciplina {disciplina}'

    form = EditarDocentesDisciplinaForm(data=request.POST or None, instance=disciplina, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def justificar_indisponibilidade_docentes(request, pafc_pk, disciplina_pk):
    pafc = get_object_or_404(PAFC, pk=pafc_pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    disciplina = get_object_or_404(pafc.disciplinas, pk=disciplina_pk)
    if disciplina.docentes.exists():
        return HttpResponseForbidden()
    title = f'Justificar indisponibilidade de docentes para a disciplina {disciplina}'

    form = JustificarIndisponibilidadeDocentesForm(data=request.POST or None, instance=disciplina, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_justificativa_indisponibilidade_docentes(request, pafc_pk, disciplina_pk):
    pafc = get_object_or_404(PAFC, pk=pafc_pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    disciplina = get_object_or_404(pafc.disciplinas, pk=disciplina_pk)
    if disciplina.docentes.exists():
        return HttpResponseForbidden()
    title = f'Remover justificativa de indisponibilidade de docentes para a disciplina {disciplina}'

    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        disciplina.justificativa_indisponibilidade_docentes = None
        disciplina.save()
        MovimentacaoPAFC.registrar_movimentacao(
            request.user, pafc, f'Removida a justificativa de indisponibilidade de docente para disciplina "{disciplina}".'
        )
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def informar_laboratorios(request, pk):
    title = 'Informar laboratórios'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = InformarLaboratoriosForm(data=request.POST or None, instance=pafc, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def justificar_indisponibilidade_laboratorios(request, pk):
    title = 'Justificar indisponibilidade de laboratórios'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()

    form = modelform_factory(model=PAFC, form=ModelFormPlus, fields=('justificativa_indisponibilidade_laboratorios',))(
        request=request,
        instance=pafc,
        data=request.POST or None,
    )
    form.fields['justificativa_indisponibilidade_laboratorios'].required = True

    if form.is_valid():
        form.save()
        return httprr('..', 'Justificativa registrada com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_justificativa_indisponibilidade_laboratorios(request, pk):
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()

    pafc.justificativa_indisponibilidade_laboratorios = None
    pafc.save()
    return httprr(f'{pafc.get_absolute_url()}?tab=instalacoes', 'Justificativa removida com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def remover_laboratorio(request, pafc_pk, sala_pk):
    pafc = get_object_or_404(PAFC, pk=pafc_pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden('Você não tem permissão para isso.')
    laboratorio = pafc.salas.filter(pk=sala_pk).first()
    if not laboratorio:
        return HttpResponseBadRequest('O laboratório não está associada ao PAFC.')
    pafc.salas.remove(laboratorio)
    InfraestruturaExternaPAFC.processar_mudancas_na_infraestrutura(pafc)
    MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, f'Laboratório removido: {laboratorio}.')
    return httprr(f'{pafc.get_absolute_url()}?tab=instalacoes', 'Laboratório removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def editar_laboratorio(request, pk, sala_pk):
    title = 'Editar laboratório'
    pafc = PAFC.objects.get(pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    laboratorio = Sala.objects.get(pk=sala_pk)
    form = EditarLaboratorioForm(data=request.POST or None, instance=laboratorio, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def cadastrar_comprovante_disponibilidade_infraestrutura(request, pk):
    infraestrutura_externa = get_object_or_404(InfraestruturaExternaPAFC, pk=pk)
    title = f'Cadastrar comprovante de disponibilidade do campus {infraestrutura_externa.campus}'

    if not infraestrutura_externa.pafc.pode_ser_elaborado():
        raise PermissionDenied('O PAFC não está em elaboração.')
    if not infraestrutura_externa.pafc.tem_permissao_edicao(request.user):
        raise PermissionDenied('Você não tem as permissões necessárias.')
    if infraestrutura_externa.comprovante_disponibilidade is not None:
        raise PermissionDenied('O comprovante de disponibilidade já foi cadastrado.')

    form = DocumentoHibridoForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        comprovante = form.save()
        infraestrutura_externa.comprovante_disponibilidade = comprovante
        infraestrutura_externa.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_comprovante_disponibilidade_infraestrutura(request, id_infra, id_documento):
    title = 'Editar documento'
    infraestrutura = get_object_or_404(InfraestruturaExternaPAFC, pk=id_infra)
    documento = get_object_or_404(DocumentoHibrido, pk=id_documento)
    if not infraestrutura.pafc.pode_ser_elaborado():
        raise PermissionDenied('O PAFC não está em elaboração.')
    if not infraestrutura.pafc.tem_permissao_edicao(request.user):
        raise PermissionDenied('Você não tem as permissões necessárias.')
    if infraestrutura.comprovante_disponibilidade != documento:
        raise PermissionDenied('O comprovante não corresponde ao laboratório escolhido.')

    form = DocumentoHibridoForm(data=request.POST or None, files=request.FILES or None, instance=documento, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Comprovante editado com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_comprovante_disponibilidade_infraestrutura(request, id_infra, id_documento):
    title = 'Editar documento'
    infraestrutura = get_object_or_404(InfraestruturaExternaPAFC, pk=id_infra)
    documento = get_object_or_404(DocumentoHibrido, pk=id_documento)
    if not infraestrutura.pafc.pode_ser_elaborado():
        raise PermissionDenied('O PAFC não está em elaboração.')
    if not infraestrutura.pafc.tem_permissao_edicao(request.user):
        raise PermissionDenied('Você não tem as permissões necessárias.')
    if infraestrutura.comprovante_disponibilidade != documento:
        raise PermissionDenied('O comprovante não corresponde ao laboratório escolhido.')

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        documento.delete()
        return httprr('..', 'Comprovante removido com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_polo(request, polo_pk):
    polo = get_object_or_404(PoloEadPAFC, pk=polo_pk)
    if not polo.pafc.pode_ser_elaborado() or not polo.pafc.tem_permissao_edicao(request.user):
        raise PermissionDenied('Você não tem permissão para isso.')
    if not polo.pafc.modelo.eh_versao_totalmente_ead():
        raise PermissionDenied('Este PAFC não prevê o cadastro de polos, pois curso não é totalmente EaD.')
    polo_str = str(polo)
    polo.delete()
    MovimentacaoPAFC.registrar_movimentacao(request.user, polo.pafc, f'{polo_str} removido.')
    return httprr(f'{polo.pafc.get_absolute_url()}?tab=infraestrutura_ead', 'Polo removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def remover_tutor(request, tutor_pk):
    tutor = get_object_or_404(TutorMediadorEadPAFC, pk=tutor_pk)
    if not tutor.pafc.pode_ser_elaborado() or not tutor.pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden('Você não tem permissão para isso.')
    tutor_str = str(tutor)
    tutor.delete()
    MovimentacaoPAFC.registrar_movimentacao(request.user, tutor.pafc, f'Tutor removido: {tutor_str}.')
    return httprr(f'{tutor.pafc.get_absolute_url()}?tab=infraestrutura_ead', 'Tutor removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def vincular_matriz_ppc(request, pk):
    title = 'Vincular matriz ao PAFC'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.pode_ser_elaborado() or not pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden()
    form = VincularMatrizPAFCForm(pafc=pafc, data=request.POST or None, request=request)
    if form.is_valid():
        with transaction.atomic():
            matriz = form.save()
            MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, f'Matriz "{matriz}" vinculada ao PAFC.')
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def desvincular_matriz_pafc(request, pk):
    matriz = get_object_or_404(MatrizPAFC, pk=pk)
    if not matriz.pode_excluir(request.user):
        return HttpResponseForbidden()
    nome_matriz = matriz.matriz_ppc.nome
    pafc = matriz.pafc
    with transaction.atomic():
        matriz.delete()
        MovimentacaoPAFC.registrar_movimentacao(request.user, matriz.pafc, f'Matriz "{nome_matriz}" desvinculada do PAFC.')
    return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Matriz desvinculada com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def visualizar_bibliografia_pafc(request, pk):
    title = 'Pré-visualização da bibliografia'
    pafc = get_object_or_404(PAFC, pk=pk)
    bibliografias = (
        ('Bibliografia Básica', pafc.quadro_bibliografia_basica_html),
        ('Bibliografia Complementar', pafc.quadro_bibliografia_complementar_html),
    )
    return locals()


@permission_required('pafc.view_pafc')
def atualizar_bibliografia(request, pk):
    bibliografia = get_object_or_404(BibliografiaPAFC, pk=pk)
    if not bibliografia.pafc.pode_ser_elaborado() or not bibliografia.pafc.tem_permissao_edicao(request.user):
        return HttpResponseForbidden('Você não tem permissão para isso.')

    form = AtualizarBibliografiaPAFC(data=request.POST or None, instance=bibliografia)
    if form.is_valid():
        form.save()
        return HttpResponse()
    else:
        mensagem_retorno = '<li>'
        for campo in [chave for chave in form.errors if chave != 'code']:
            mensagem_retorno += '</li><li>'.join(form.errors[campo])
        mensagem_retorno += '</li>'
        return HttpResponseBadRequest(mark_safe(mensagem_retorno))


@permission_required('pafc.view_pafc')
def reprocessar_bibliografia_do_pafc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.em_elaboracao():
        raise PermissionDenied('A bibliografia só pode ser reprocessada durante etapa de elaboração.')
    if not pafc.tem_permissao_edicao(request.user):
        raise PermissionDenied('Você não tem permissão para reimportar a bibliografia do PAFC.')

    return tasks.reprocessar_bibliografia_pafc(request, pafc)


@permission_required('pafc.view_pafc')
@rtr()
def habilitar_elaboracao_pomc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = f'Habilitar elaboração do POMC para o PAFC {pafc}'
    if not (
        pafc.pode_ter_pomc_implementado
        and pafc.pode_ser_elaborado()
        and (pafc.tem_permissao_edicao(request.user) or pafc.tem_permissao_administrador(request.user))
    ):
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    if pafc.resumo_trabalho_necessario_para_elaborar_pomc:
        form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
        form.SUBMIT_LABEL = 'Confimar habilitação'
        if form.is_valid():
            pafc.sincronizar_planos_disciplina_entre_ppc_e_pomc(request.user, forcar_sincronia=True)
            return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'PAFC configurado para elaborar o POMC.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def cancelar_elaboracao_pomc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = f'Cancelar elaboração do POMC para o PAFC {pafc}'
    if not (
        pafc.implementa_pomc
        and pafc.pode_ser_elaborado()
        and (pafc.tem_permissao_edicao(request.user) or pafc.tem_permissao_administrador(request.user))
    ):
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    if pafc.pomc_eh_obrigatorio:
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'O POMC é obrigatório para este PAFC.', tag='error', close_popup=True)

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    form.SUBMIT_LABEL = 'Confirmar cancelamento'
    if form.is_valid():
        pafc.remover_pomc(request.user)
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Elaboração do POMC cancelada com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_comprovante_aprovacao_pomc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    eh_edicao = pafc.comprovante_aprovacao_pomc is not None
    title = f'{"Editar" if eh_edicao else "Anexar"} Ata do Colegiado aprovando o POMC'
    if not (
        pafc.implementa_pomc
        and pafc.pode_ser_elaborado()
        and (pafc.tem_permissao_edicao(request.user) or pafc.tem_permissao_administrador(request.user))
    ):
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    ata = pafc.comprovante_aprovacao_pomc if eh_edicao else DocumentoHibrido()
    form = DocumentoHibridoForm(data=request.POST or None, files=request.FILES or None, instance=ata, request=request)
    if form.is_valid():
        if form.has_changed():
            with transaction.atomic():
                ata = form.save()
                pafc.comprovante_aprovacao_pomc = ata
                pafc.cadastrador_comprovante_aprovacao_pomc = request.user.get_vinculo()
                pafc.data_cadastro_comprovante_aprovacao_pomc = get_datetime_now()
                pafc.save()
                MovimentacaoPAFC.registrar_movimentacao(
                    request.user,
                    pafc,
                    f'A ata da reunião do Colegiado que aprovou a elaboração do POMC foi {"editada" if eh_edicao else "cadastrada"}.',
                )

        return httprr(
            f'{pafc.get_absolute_url()}?tab=matrizes', f'Documento {"editado" if eh_edicao else "cadastrado"} com sucesso.', close_popup=True
        )

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_comprovante_aprovacao_pomc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = 'Remover Ata do Colegiado aprovando o POMC'
    if not (
        pafc.implementa_pomc
        and pafc.pode_ser_elaborado()
        and (pafc.tem_permissao_edicao(request.user) or pafc.tem_permissao_administrador(request.user))
    ):
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    if pafc.comprovante_aprovacao_pomc is None:
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'A ata ainda não foi anexada.', tag='error', close_popup=True)

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        pafc.remover_comprovante_aprovacao_pomc(request.user)
        return httprr(f'{pafc.get_absolute_url()}?tab=matrizes', 'Documento removido com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_planodisciplinapomc')
@rtr()
def visualizar_planodisciplinapomc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPOMC, pk=pk)
    title = 'Plano de disciplina de curso'
    secoes = plano.get_secoes_plano_disciplina_impressao()

    return locals()


@documento()
@permission_required('pafc.view_planodisciplinapomc')
@rtr()
def imprimir_planodisciplinapomc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPOMC, pk=pk)
    return locals()


@documento('Plano de disciplina (versão do campus)', validade=30, modelo='pafc.planodisciplinapomc', exibe_emissor=True)
@login_required
@rtr('imprimir_planodisciplinapomc.html')
def pdf_autenticado_planodisciplinapomc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPOMC, pk=pk)
    return locals()


@permission_required('pafc.view_planodisciplinamodificado')
@rtr()
def visualizar_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = 'Plano de disciplina de curso'

    pode_elaborar = plano.pode_elaborar(request.user)
    pode_revisar = plano.pode_revisar(request.user)

    tem_secao_ead = plano.get_secoes_ead().exists()
    revisoes = list(plano.revisoes.order_by('-data').all())
    nenhuma_revisao_pendente = not RevisaoPlanoDisciplinaModificado.possui_revisoes_nao_resolvidas(plano.pafc, planos_disciplinas=plano)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def concluir_edicao_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = f'Concluir elaboração do {plano}'

    if not plano.pode_elaborar(request.user) or not plano.elaboracao_pode_ser_concluida():
        return httprr('..', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        plano.concluir_elaboracao(request.user)
        return httprr('..', 'Edição de plano de disciplina concluída com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def retomar_edicao_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = f'Retomar elaboração {plano}'

    if not plano.pode_elaborar(request.user) or not plano.elaboracao_pode_ser_retomada():
        return httprr('..', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        plano.retomar_elaboracao(request.user)
        return httprr('..', 'Edição de plano de disciplina retomada com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_ementa_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = f'Editar ementa da disciplina "{plano.nome_disciplina}"'
    if plano.elaborado() or not plano.pode_elaborar(request.user):
        return httprr(f'{plano.get_absolute_url()}', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    form = EditarEmentaPlanoDisciplinaModificadoForm(data=request.POST or None, instance=plano, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'{plano.get_absolute_url()}', 'Ementa editada com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def editar_secaoprogramaplanodisciplina(request, pk):
    secao = get_object_or_404(SecaoProgramaPlanoDisciplinaModificado, pk=pk)
    title = f'Editar seção "{secao.titulo}"'
    plano = secao.plano_disciplina
    if plano.elaborado() or not plano.pode_elaborar(request.user):
        return httprr(f'{plano.get_absolute_url()}', 'Você não tem permissão para isso.', tag='error', close_popup=True)

    form = SecaoProgramaPlanoDisciplinaModificadoForm(data=request.POST or None, instance=secao, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'{plano.get_absolute_url()}', 'Seção editada com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def concluir_revisao_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = f'Concluir revisão do {plano}'

    if not plano.pode_revisar(request.user) or not plano.revisao_pode_ser_concluida():
        raise PermissionDenied('A revisão não pode ser concluída. Verifique se você tem as permissões necessárias e se ela não possui pendências.')

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        plano.concluir_revisao(request.user)
        return httprr('..', 'Revisão de plano de disciplina concluída com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def concluir_revisao_planodisciplina_em_massa(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = f'Concluir revisão de todos os planos de disciplina do PAFC #{pafc.id}'

    if not pafc.is_validador(request.user) or not PlanoDisciplinaModificado.revisao_pode_ser_realizada_em_massa(pafc):
        raise PermissionDenied('Verifique suas permissões e se a etapa do PAFC permite essa operação.')

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        PlanoDisciplinaModificado.concluir_revisao_em_massa(pafc, request.user)
        return httprr('..', 'Revisões concluídas com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def retomar_revisao_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = f'Retomar revisão do {plano}'

    if not plano.pode_revisar(request.user) or not plano.revisao_pode_ser_retomada():
        raise PermissionDenied('Você não tem permissão para retomar a revisão ou ela não pode ser retomada na situação atual do PAFC.')

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        plano.retomar_revisao(request.user)
        return httprr('..', 'Revisão de plano de disciplina retomada com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def adicionar_revisao_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplinaModificado, pk=pk)
    title = f'Fazer observação sobre o {plano}'

    if not plano.pode_revisar(request.user) or not plano.pode_receber_revisao():
        raise PermissionDenied('Você não tem permissão para cadastrar revisões ou o plano de disciplina não aceita revisões no momento.')

    tipo_revisao = RevisaoPlanoDisciplinaModificado.get_tipo_de_revisao_correspondente(plano.pafc.situacao)
    revisao = RevisaoPlanoDisciplinaModificado(plano_disciplina=plano, tipo_revisao=tipo_revisao, revisor=request.user.get_vinculo())

    RevisaoForm = modelform_factory(RevisaoPlanoDisciplinaModificado, ModelFormPlus, fields=['comentario'])
    form = RevisaoForm(request.POST or None, request=request, instance=revisao)

    if form.is_valid():
        form.instance.data = get_datetime_now()
        form.save()
        return httprr('..', 'Revisão de plano de disciplina adicionada com sucesso.', tag='success', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def resolver_revisao_planodisciplina(request, pk):
    revisao = get_object_or_404(RevisaoPlanoDisciplinaModificado, pk=pk)
    title = f'Marcar revisão #{revisao.pk} como resolvida'

    if not revisao.pode_resolver(request.user):
        raise PermissionDenied('Você não tem permissão para resolver esta revisão. Verifique suas permissões e a situação atual do PAFC.')

    form = ConfirmarComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        revisao.resolvida = True
        revisao.resolvida_por = request.user.get_vinculo()
        revisao.data_resolucao = get_datetime_now()
        revisao.save()
        return httprr('..', 'Revisão marcada como resolvida com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def anexar_relatorio_analise_preliminar(request, pk):
    title = 'Anexar Relatório da Análise Preliminar'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.tem_permissao_edicao(request.user) or not pafc.em_analise_preliminar():
        return HttpResponseForbidden('Você não tem permissão para isso.')
    form = AnexarRelatorioAnalisePreliminarForm(data=request.POST or None, files=request.FILES or None, instance=pafc, request=request)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Ação realizada com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_relatorio_analise_preliminar(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.tem_permissao_edicao(request.user) or not pafc.em_analise_preliminar() or not pafc.relatorio_analise_preliminar:
        return HttpResponseForbidden('Você não tem permissão para isso.')
    pafc.relatorio_analise_preliminar.delete()
    pafc.data_upload_relatorio_analise_preliminar = None
    pafc.relatorio_analise_preliminar_cadastrado_por = None
    pafc.save()
    MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, 'Relatório da Análise Preliminar removido.')
    return httprr('..', 'Relatório removido com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def anexar_ficha_revisao_tecnica(request, pk):
    title = 'Anexar Ficha de Revisão Técnica'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.tem_permissao_edicao(request.user) or not pafc.em_revisao_tecnica():
        return HttpResponseForbidden('Você não tem permissão para isso.')
    form = AnexarFichaRevisaoTecnicaForm(data=request.POST or None, files=request.FILES or None, instance=pafc, request=request)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Ação realizada com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def remover_ficha_revisao_tecnica(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.tem_permissao_edicao(request.user) or not pafc.em_revisao_tecnica():
        return HttpResponseForbidden('Você não tem permissão para isso.')
    pafc.ficha_revisao_tecnica.delete()
    pafc.data_upload_ficha_revisao_tecnica = None
    pafc.ficha_revisao_tecnica_cadastrada_por = None
    pafc.save()
    MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, 'Ficha de Revisão Técnica removida.')
    return httprr('..', 'Ficha removida com sucesso.')


@permission_required('pafc.view_pafc')
@rtr()
def editar_proreitoria(request, pk):
    title = 'Editar Pró-Reitoria'
    pafc = PAFC.objects.get(pk=pk)
    if (not pafc.pode_ser_editado() and pafc.situacao != PAFC.EM_ANALISE_PROREITORIA) or not pafc.tem_permissao_administrador(request.user):
        return HttpResponseForbidden()
    form = EditarProReitoriaForm(data=request.POST or None, request=request, instance=pafc)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def emitir_documento_pafc(request, pk, tipo_documento):
    title = 'Emitir/vincular documento do PAFC'
    pafc = get_object_or_404(PAFC, id=pk)
    pode_emitir = pafc.pode_emitir_documento(request.user, tipo_documento)

    if not pode_emitir:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)

    form = emitir_documento_pafc_formfactory(request, pafc, tipo_documento)
    if form.is_valid():
        try:
            form.processar()
        except Exception as e:
            return httprr('.', f'Erro ao emitir documento: {e}.', 'error', close_popup=True)

        return httprr('.', 'Documento cadastrado com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def substituir_documento_pafc(request, pk):
    title = 'Substituir documento do PAFC'
    documento = get_object_or_404(DocumentoEmitidoPAFC, pk=pk)
    if request.user.has_perm('pafc.change_documentohibrido') or request.user == documento.emissor.get_vinculo().user:
        form = DocumentoHibridoForm(data=request.POST or None, files=request.FILES or None, instance=documento.documento, request=request)
        if form.is_valid():
            form.save()
            return httprr('.', 'Documento substituído com sucesso.', close_popup=True)

        return locals()
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def remover_documento_pafc(request, pk):
    documento = get_object_or_404(DocumentoEmitidoPAFC, pk=pk)
    title = f'Remover {documento.documento} do PAFC'
    pafc = documento.pafc
    if documento.situacao_pafc != pafc.situacao or not documento.can_delete(request.user):
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)

    form = ConfirmacaoForm(data=request.POST or None, request=request)
    if form.is_valid():
        if documento.situacao_pafc == PAFC.AGUARDANDO_APROVACAO_CAMARA:
            pafc.decisao_camara = None
        elif documento.situacao_pafc == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
            pafc.decisao_consepex = None
        elif documento.situacao_pafc == PAFC.AGUARDANDO_APROVACAO_CONSUP:
            pafc.decisao_consup = None

        descricao_documento = str(documento.documento)
        with transaction.atomic():
            documento.documento.delete()
            documento.delete()
        MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, f'{descricao_documento} removido do PAFC.')
        return httprr('.', 'Documento removido com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def solicitar_correcao_pafc(request, pk):
    title = 'Solicitar correção do PAFC'
    pafc = get_object_or_404(PAFC, id=pk)

    if not pafc.pode_solicitar_correcao_nos_conselhos(request.user):
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)

    form = SolicitarCorrecaoEmConselhosForm(pafc, request=request, data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        try:
            form.processar()
        except Exception as e:
            return httprr('.', f'Erro ao processar solicitação: {e}.', 'error', close_popup=True)

        return httprr('.', 'Solicitação registrada com sucesso.', close_popup=True)

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def convocar_camara_pafc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = 'Informar dados da Câmara'
    if pafc.pode_convocar_camara(request.user):
        form = ConvocarCamaraPAFCForm(data=request.POST or None, instance=pafc, request=request)
        if form.is_valid():
            pafc = form.save()
            return httprr('.', 'Dados informados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def convocar_consepex_pafc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = 'Convocar CONSEPEX'
    if pafc.pode_convocar_consepex(request.user):
        form = ConvocarConsepexPAFCForm(data=request.POST or None, instance=pafc, request=request)
        if form.is_valid():
            pafc = form.save()
            return httprr('', 'Dados atualizados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def convocar_consup_pafc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = 'Convocar CONSUP'
    if pafc.pode_convocar_consup(request.user):
        form = ConvocarConsupPAFCForm(data=request.POST or None, instance=pafc, request=request)
        if form.is_valid():
            pafc = form.save()
            return httprr('', 'Dados atualizados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def solicitar_tramitacao_ad_referendum_pafc(request, pk):
    pafc = get_object_or_404(PAFC, pk=pk)
    title = f'Solicitar tramitação Ad Referendum do PAFC {pafc}'
    if pafc.pode_solicitar_tramitacao_ad_referendum(request.user):
        conselho = 'CONSEPEX' if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX else 'CONSUP'
        solicitacao = SolicitacaoTramitacaoAdReferendumPAFC(
            pafc=pafc,
            situacao_pafc=pafc.situacao,
            solicitante=request.user.get_vinculo(),
        )
        form = modelform_factory(SolicitacaoTramitacaoAdReferendumPAFC, ModelFormPlus, fields=['justificativa'])(
            data=request.POST or None, instance=solicitacao
        )
        if form.is_valid():
            solicitacao = form.save()
            return httprr('..', 'Solicitação registrada com sucesso.', close_popup=True)
        return locals()
    return httprr('..', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('pafc.view_pafc')
@rtr()
def visualizar_solicitacaotramitacaoadreferendumpafc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoTramitacaoAdReferendumPAFC, pk=pk)
    if not solicitacao.usuario_pode_visualizar(request.user):
        return httprr('..', 'Você não tem permissão para isso.', 'error')

    title = str(solicitacao)
    usuario_pode_avaliar = solicitacao.usuario_pode_avaliar(request.user)[0]

    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def deferir_solicitacaotramitacaoadreferendumpafc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoTramitacaoAdReferendumPAFC, pk=pk)
    title = f'Deferir {solicitacao}'
    usuario_pode_avaliar, motivo_negativa = solicitacao.usuario_pode_avaliar(request.user)
    if not usuario_pode_avaliar:
        return httprr('..', f'Operação não permitida pelo seguinte motivo: {motivo_negativa}.', 'error')

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        solicitacao.resolver_solicitacao(request.user.get_vinculo(), deferir=True)
        return httprr('..', 'Solicitação deferida com sucesso.', close_popup=True)
    return locals()


@permission_required('pafc.view_pafc')
@rtr()
def indeferir_solicitacaotramitacaoadreferendumpafc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoTramitacaoAdReferendumPAFC, pk=pk)
    title = f'Indeferir {solicitacao}'
    usuario_pode_avaliar, motivo_negativa = solicitacao.usuario_pode_avaliar(request.user)
    if not usuario_pode_avaliar:
        return httprr('..', f'Operação não permitida pelo seguinte motivo: {motivo_negativa}.', 'error')

    form = IndeferirSolicitacaoTramitacaoAdReferendumForm(data=request.POST or None, request=request)
    if form.is_valid():
        solicitacao.resolver_solicitacao(request.user.get_vinculo(), deferir=False, motivo_indeferimento=form.get_motivo_informado())
        return httprr('..', 'Solicitação indeferida com sucesso.', close_popup=True)

    return locals()


@permission_required('edu.add_cursocampus')
@rtr()
def criar_curso(request, pk):
    title = 'Criar curso'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.pode_ter_curso_criado() or not pafc.pode_criar_curso(request.user):
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        pafc.criar_curso(request.user)
        return httprr(
            '.', mark_safe(f'Curso criado com sucesso. <a href="{pafc.curso.get_absolute_url()}">Clique aqui</a> para consultá-lo.'), close_popup=True
        )
    return locals()


@permission_required('edu.change_cursocampus')
@rtr()
def atualizar_curso(request, pk):
    title = 'Atualizar curso'
    pafc = get_object_or_404(PAFC, pk=pk)
    if not pafc.pode_ter_curso_atualizado() or not pafc.pode_atualizar_curso(request.user):
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    form = ConfirmacaoForm(data=request.POST or None)
    if form.is_valid():
        pafc.atualizar_curso(request.user)
        return httprr(
            '.',
            mark_safe(f'Curso atualizado com sucesso. <a href="{pafc.curso.get_absolute_url()}">Clique aqui</a> para consultá-lo.'),
            close_popup=True,
        )
    return locals()


@permission_required('pafc.view_pafc')
def get_total_vagas_curso(request, curso_id):
    curso: CursoCampus = get_object_or_404(CursoCampus, pk=curso_id)
    return JsonResponse(curso.quantidade_vagas or 0)
