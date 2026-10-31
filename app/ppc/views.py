import copy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.db.utils import IntegrityError
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse

from comum.models import Configuracao
from djtools import layout
from djtools.utils import documento, httprr, permission_required, rtr, JsonResponse
from edu.models import Log, Modalidade, CursoCampus
from ppc import tasks
from ppc.forms import (
    AdicionarConfiguracaoOptativasMatrizPPCForm,
    AtualizacaoComissaoElaboracaoForm,
    CertificacaoParcialForm,
    ColaboradorPPCForm,
    ComentarioConteudoPPCForm,
    ComentarioRevisaoPlanoDisciplinaForm,
    ComponenteExigidoDiretrizForm,
    ConfiguracaoOptativasMatrizPPCForm,
    ConteudoForm,
    ConvocarCamaraForm,
    ConvocarCONSEPEXForm,
    ConvocarCONSUPForm,
    DevolverMatrizCurricularForm,
    DevolverModalidadePraticaProfissionalForm,
    DevolverSolicitacaoPPCForm,
    EditarTextoConteudoForm,
    EixoTecnologicoDiretrizForm,
    ElaboradorPPCForm,
    EmentaPlanoDisciplinaForm,
    EmitirDeliberacaoCONSEPEXForm,
    EmitirDocumentoForm,
    EmitirParecerCamaraForm,
    EmitirDespachoProReitoriaForm,
    EmitirParecerRevisaoForm,
    EmitirResolucaoCONSUPForm,
    GerarCursoPPCForm,
    GerarMatrizPPCForm,
    IndicacaoElaboradorPPCForm,
    InformarReitoriaForm,
    MatrizPPCForm,
    MembroColegiadoForm,
    ModalidadePraticaProfissionalDiretrizForm,
    ModalidadePraticaProfissionalPPCForm,
    ModeloSecaoPlanoDisciplinaForm,
    NucleoDiretrizForm,
    PeriodoDiretrizForm,
    PlanoDisciplinaCertificacaoParcialForm,
    PlanoDisciplinaForm,
    PlanoDisciplinaPPCForm,
    RejeitarIndicacaoElaboradorPPCForm,
    RejeitarSolicitacaoPPCForm,
    ReplicarDiretrizForm,
    ReplicarMatrizPPCForm,
    ReplicarModeloPlanoDisciplinaForm,
    ReplicarModeloPPCForm,
    RequisitosPlanoDisciplinaPPCForm,
    RevisarConteudoPPCForm,
    RevisorPPCForm,
    SecaoForm,
    SecaoPlanoDisciplinaForm,
    SolicitarAvaliacaoElaboradorForm,
    VincularCursoPPCForm,
    VincularDocumentoPPCForm,
    VincularPortariaSolicitacaoPPCForm,
    DuplicarPlanoDisciplinaForm,
)
from ppc.models import (
    AdministradorTipoOferta,
    CertificacaoParcial,
    ColaboradorPPC,
    ComentarioConteudoPPC,
    ComentarioRevisaoPlanoDisciplina,
    ComissaoPTDEM,
    ComponenteExigidoDiretriz,
    ConfiguracaoOptativasMatrizPPC,
    Conteudo,
    ConteudoPPC,
    Diretriz,
    DocumentoPPC,
    EixoTecnologicoDiretriz,
    ElaboradorPPC,
    IndicacaoElaboradorPPC,
    MatrizPPC,
    ModalidadePraticaProfissionalDiretriz,
    ModalidadePraticaProfissionalPPC,
    ModeloPlanoDisciplina,
    ModeloPPC,
    ModeloSecaoPlanoDisciplina,
    NucleoDiretriz,
    PeriodoDiretriz,
    PlanoDisciplina,
    PlanoDisciplinaPPC,
    ProjetoPedagogicoCurso,
    RevisaoPlanoDisciplina,
    RevisorPPC,
    Secao,
    SecaoPlanoDisciplina,
    SolicitacaoPPC,
)
from rh.models import Servidor, Setor


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    vinculo = request.user.get_vinculo() if request.user else None
    if vinculo is None:
        return []

    pendencias = []
    # plano de disciplina
    qtd_pd_elaboracao = PlanoDisciplina.get_meus_planos(vinculo, PlanoDisciplina.objects.all()).filter(situacao=PlanoDisciplina.ELABORACAO).count()
    if qtd_pd_elaboracao:
        pendencias.append(
            {
                'titulo': f'Plano{pluralize(qtd_pd_elaboracao)} de disciplina{pluralize(qtd_pd_elaboracao)}',
                'subtitulo': 'em elaboração',
                'qtd': qtd_pd_elaboracao,
                'url': '/admin/ppc/planodisciplina/?tab=tab_meus_planos&situacao__exact=1',
            }
        )
    if vinculo.eh_servidor():
        servidor = vinculo.relacionamento

        if PlanoDisciplina.is_avaliador(request.user):
            qtd_pd_analise = PlanoDisciplina.objects.filter(situacao=PlanoDisciplina.AGUARDANDO_ANALISE).count()
            if qtd_pd_analise:
                pendencias.append(
                    {
                        'titulo': f'Plano{pluralize(qtd_pd_analise)} de disciplina{pluralize(qtd_pd_analise)}',
                        'subtitulo': 'aguardando análise',
                        'qtd': qtd_pd_analise,
                        'url': '/admin/ppc/planodisciplina/?situacao__exact=2&tab=tab_any_data',
                    }
                )

        # solicitação
        qtd_ata_pendente = SolicitacaoPPC.get_solicitacoes_emissao_ata_pendente(SolicitacaoPPC.objects.all(), servidor).count()
        if qtd_ata_pendente:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_ata_pendente, "ão,ões")} de PPC',
                    'subtitulo': 'aguardando emissão de ata',
                    'qtd': qtd_ata_pendente,
                    'url': '/admin/ppc/solicitacaoppc/?tab=tab_emissao_ata&minhas_pendencias=1',
                }
            )

        qtd_analise_pendente = SolicitacaoPPC.get_solicitacoes_analise_pendente(SolicitacaoPPC.objects.all(), servidor).count()
        if qtd_analise_pendente:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_analise_pendente, "ão,ões")} de PPC',
                    'subtitulo': 'aguardando análise',
                    'qtd': qtd_analise_pendente,
                    'url': '/admin/ppc/solicitacaoppc/?tab=tab_analise&minhas_pendencias=1',
                }
            )

        qtd_solicitacao_portaria_pendente = SolicitacaoPPC.get_solicitacoes_solicitacao_portaria_pendente(
            SolicitacaoPPC.objects.all(), servidor
        ).count()
        if qtd_solicitacao_portaria_pendente:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_solicitacao_portaria_pendente, "ão,ões")} de PPC',
                    'subtitulo': 'aguardando solicitação de emissão de portaria',
                    'qtd': qtd_solicitacao_portaria_pendente,
                    'url': '/admin/ppc/solicitacaoppc/?tab=tab_solicitacao_portaria&minhas_pendencias=1',
                }
            )

        qtd_emissao_portaria_pendente = SolicitacaoPPC.get_solicitacoes_emissao_portaria_pendente(SolicitacaoPPC.objects.all(), servidor).count()
        if qtd_emissao_portaria_pendente:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_emissao_portaria_pendente, "ão,ões")} de PPC',
                    'subtitulo': 'aguardando emissão de portaria',
                    'qtd': qtd_emissao_portaria_pendente,
                    'url': '/admin/ppc/solicitacaoppc/?tab=tab_emissao_portaria&minhas_pendencias=1',
                }
            )

        if request.user.has_perm('comum.is_administrador_academico') or request.user.has_perm('comum.is_administrador_de_ppc'):
            qtd_geracao_pendente = SolicitacaoPPC.get_solicitacoes_geracao_ppc_pendente(SolicitacaoPPC.objects.all()).count()
            if qtd_geracao_pendente:
                pendencias.append(
                    {
                        'titulo': f'Solicitaç{pluralize(qtd_geracao_pendente, "ão,ões")} de PPC',
                        'subtitulo': 'com pendências para finalizar solicitação',
                        'qtd': qtd_geracao_pendente,
                        'url': '/admin/ppc/solicitacaoppc/?tab=tab_geracao_ppc',
                    }
                )

        # PPC
        if request.user.has_perm('comum.is_administrador_de_ppc'):
            qtd_ppc_iniciado = ProjetoPedagogicoCurso.objects.filter(situacao=ProjetoPedagogicoCurso.INICIADO).count()
            if qtd_ppc_iniciado:
                pendencias.append(
                    {
                        'titulo': f'PPC{pluralize(qtd_ppc_iniciado)} iniciado{pluralize(qtd_ppc_iniciado)}',
                        'subtitulo': 'sem equipe de elaboração',
                        'qtd': qtd_ppc_iniciado,
                        'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=1',
                    }
                )

            qtd_ppc_aprovado = ProjetoPedagogicoCurso.objects.filter(situacao=ProjetoPedagogicoCurso.APROVADO).count()
            if qtd_ppc_aprovado:
                pendencias.append(
                    {
                        'titulo': f'PPC{pluralize(qtd_ppc_aprovado)} aprovado{pluralize(qtd_ppc_aprovado)}',
                        'subtitulo': 'aguardando finalização',
                        'qtd': qtd_ppc_aprovado,
                        'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=7',
                    }
                )

        setor_conselhos_id = Configuracao.get_valor_por_chave('ppc', 'setor_secretaria_conselhos')
        if setor_conselhos_id and int(setor_conselhos_id) == request.user.get_vinculo().setor_id:
            qtd_ppc_consepex = ProjetoPedagogicoCurso.objects.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CONSEPEX).count()
            if qtd_ppc_consepex:
                pendencias.append(
                    {
                        'titulo': f'PPC{pluralize(qtd_ppc_consepex)}',
                        'subtitulo': 'em análise do CONSEPEX',
                        'qtd': qtd_ppc_consepex,
                        'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=5',
                    }
                )

            qtd_ppc_consup = ProjetoPedagogicoCurso.objects.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CONSUP).count()
            if qtd_ppc_consup:
                pendencias.append(
                    {
                        'titulo': f'PPC{pluralize(qtd_ppc_consup)}',
                        'subtitulo': 'em análise do CONSUP',
                        'qtd': qtd_ppc_consup,
                        'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=6',
                    }
                )

    return pendencias


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()

        # plano de disciplina
        qtd_pd_analise = PlanoDisciplina.objects.filter(situacao=PlanoDisciplina.EM_ANALISE, avaliador=servidor).count()
        if qtd_pd_analise:
            pendencias.append(
                {
                    'titulo': f'Plano{pluralize(qtd_pd_analise)} de disciplina{pluralize(qtd_pd_analise)}',
                    'subtitulo': 'em análise',
                    'qtd': qtd_pd_analise,
                    'url': '/admin/ppc/planodisciplina/?situacao__exact=3&tab=tab_any_data',
                }
            )

        # solicitação
        qtd_solicitada = SolicitacaoPPC.get_solicitacoes_envio_analise_pendente(SolicitacaoPPC.objects.all(), servidor).count()
        if qtd_solicitada:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_solicitada, "ão,ões")} de PPC',
                    'subtitulo': 'a enviar para análise',
                    'qtd': qtd_solicitada,
                    'url': f'/admin/ppc/solicitacaoppc/?solicitante={servidor.id}&tab=tab_envio',
                }
            )

        qtd_solicitada_fic = SolicitacaoPPC.objects.filter(
            solicitante=servidor, situacao=SolicitacaoPPC.SOLICITADA, tipo_oferta_id=Modalidade.FIC_MENOS
        ).count()
        if qtd_solicitada_fic:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_solicitada_fic, "ão,ões")} de PPC',
                    'subtitulo': 'a solicitar emissão de ata',
                    'qtd': qtd_solicitada_fic,
                    'url': f'/admin/ppc/solicitacaoppc/?tipo_oferta={Modalidade.FIC_MENOS}&solicitante={servidor.id}&situacao__exact={SolicitacaoPPC.SOLICITADA}&tab=tab_any_data',
                }
            )

        qtd_finalizacao_ata_pendente = SolicitacaoPPC.get_solicitacoes_finalizacao_ata_pendente(SolicitacaoPPC.objects.all(), servidor).count()
        if qtd_finalizacao_ata_pendente:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_finalizacao_ata_pendente, "ão,ões")} de PPC',
                    'subtitulo': 'aguardando finalização da ata',
                    'qtd': qtd_finalizacao_ata_pendente,
                    'url': '/admin/ppc/solicitacaoppc/?tab=tab_finalizacao_ata&minhas_pendencias=1',
                }
            )

        qtd_indicacoes = SolicitacaoPPC.get_solicitacoes_indicacao_pendente(SolicitacaoPPC.objects.all(), servidor).count()
        if qtd_indicacoes:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_indicacoes, "ão,ões")} de PPC',
                    'subtitulo': 'sem indicação de elaboradores',
                    'qtd': qtd_indicacoes,
                    'url': f'/admin/ppc/solicitacaoppc/?solicitante={servidor.id}&tab=tab_indicacao',
                }
            )

        qtd_finalizacao_portaria_pendente = SolicitacaoPPC.get_solicitacoes_finalizacao_portaria_pendente(
            SolicitacaoPPC.objects.all(), servidor
        ).count()
        if qtd_finalizacao_portaria_pendente:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_finalizacao_portaria_pendente, "ão,ões")} de PPC',
                    'subtitulo': 'aguardando finalização de portaria',
                    'qtd': qtd_finalizacao_portaria_pendente,
                    'url': '/admin/ppc/solicitacaoppc/?tab=tab_finalizacao_portaria&minhas_pendencias=1',
                }
            )

        # PPC
        qtd_ppc_elaboracao = ElaboradorPPC.objects.filter(ppc__situacao=ProjetoPedagogicoCurso.EM_ELABORACAO, servidor=servidor).count()
        if qtd_ppc_elaboracao:
            pendencias.append(
                {
                    'titulo': f'PPC{pluralize(qtd_ppc_elaboracao)}',
                    'subtitulo': 'em elaboração',
                    'qtd': qtd_ppc_elaboracao,
                    'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=2&tab=tab_meus',
                }
            )

        qtd_ppc_revisao = RevisorPPC.objects.filter(ppc__situacao=ProjetoPedagogicoCurso.EM_REVISAO, servidor=servidor).count()
        if qtd_ppc_revisao:
            pendencias.append(
                {
                    'titulo': f'PPC{pluralize(qtd_ppc_revisao)}',
                    'subtitulo': 'em revisão',
                    'qtd': qtd_ppc_revisao,
                    'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=3&tab=tab_meus',
                }
            )

        qs_ppc_camara = ProjetoPedagogicoCurso.objects.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CAMARA)
        qs = qs_ppc_camara.filter(camara__secretario=servidor) | qs_ppc_camara.filter(camara__coordenador=servidor)
        qtd_ppc_camara = qs.distinct().count()
        if qtd_ppc_camara:
            pendencias.append(
                {
                    'titulo': f'PPC{pluralize(qtd_ppc_camara)}',
                    'subtitulo': 'em análise da Câmara',
                    'qtd': qtd_ppc_camara,
                    'url': '/admin/ppc/projetopedagogicocurso/?situacao__exact=4&tab=tab_meus',
                }
            )

    return pendencias


@permission_required('comum.is_servidor')
@rtr()
def painel(request):
    title = 'Painel'
    painel = []

    painel_planos = []
    qs_planos = PlanoDisciplina.objects.all()
    qtd_pd_andamento = qs_planos.exclude(situacao__in=[PlanoDisciplina.REJEITADO, PlanoDisciplina.APROVADO]).count()
    qtd_pd_finalizada = qs_planos.filter(situacao=PlanoDisciplina.APROVADO).count()
    qtd_pd_rejeitada = qs_planos.filter(situacao=PlanoDisciplina.REJEITADO).count()
    if qtd_pd_andamento > 0:
        for situacao in PlanoDisciplina.SITUACAO_CHOICES[0:3]:
            qtd = qs_planos.filter(situacao=situacao[0]).count()
            if qtd > 0:
                painel_planos.append([situacao[1], qtd, f'/admin/ppc/planodisciplina/?situacao__exact={situacao[0]}'])
                if situacao[0] == PlanoDisciplina.EM_ANALISE:
                    for i in qs_planos.filter(situacao=PlanoDisciplina.EM_ANALISE).values('avaliador').annotate(total=Count('id')):
                        avaliador = Servidor.objects.get(id=i['avaliador'])
                        painel_planos.append(
                            [f'Em revisão por {avaliador}', i['total'], f'/admin/ppc/planodisciplina/?avaliador={i["avaliador"]}&situacao__exact=3']
                        )
    painel_planos.append(
        [
            'Inconsistentes',
            qs_planos.filter(comissao_ptdem__isnull=True, planodisciplinappc__isnull=True).count(),
            '/admin/ppc/planodisciplina/?tab=tab_inconsistente',
        ]
    )
    painel.append(['Planos de disciplinas', qtd_pd_andamento, qtd_pd_finalizada, qtd_pd_rejeitada, painel_planos])

    painel_projetos = []
    qs_projetos = ProjetoPedagogicoCurso.objects.all()
    qtd_ppc_andamento = qs_projetos.exclude(situacao__in=[ProjetoPedagogicoCurso.REJEITADO, ProjetoPedagogicoCurso.FINALIZADO]).count()
    qtd_ppc_finalizada = qs_projetos.filter(situacao=ProjetoPedagogicoCurso.FINALIZADO).count()
    qtd_ppc_rejeitada = qs_projetos.filter(situacao=ProjetoPedagogicoCurso.REJEITADO).count()
    if qtd_ppc_andamento > 0:
        for situacao in ProjetoPedagogicoCurso.SITUACAO_CHOICES[0:8]:
            qtd = qs_projetos.filter(situacao=situacao[0]).count()
            if qtd > 0:
                painel_projetos.append([situacao[1], qtd, f'/admin/ppc/projetopedagogicocurso/?situacao__exact={situacao[0]}'])

        qtd = qs_projetos.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CAMARA, data_convocacao_camara=None).count()
        if qtd:
            painel_projetos.append(
                [
                    'Sem data de reunião da câmara',
                    qtd,
                    f'/admin/ppc/projetopedagogicocurso/?situacao__exact={ProjetoPedagogicoCurso.ANALISE_CAMARA}&tab=tab_sem_reuniao',
                ]
            )

        qtd = qs_projetos.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CONSEPEX, data_convocacao_consepex=None).count()
        if qtd:
            painel_projetos.append(
                [
                    'Sem data de reunião do CONSPEX',
                    qtd,
                    f'/admin/ppc/projetopedagogicocurso/?situacao__exact={ProjetoPedagogicoCurso.ANALISE_CONSEPEX}&tab=tab_sem_reuniao',
                ]
            )

        qtd = qs_projetos.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CONSUP, data_convocacao_consup=None).count()
        if qtd:
            painel_projetos.append(
                [
                    'Sem data de reunião da CONSUP',
                    qtd,
                    f'/admin/ppc/projetopedagogicocurso/?situacao__exact={ProjetoPedagogicoCurso.ANALISE_CONSUP}&tab=tab_sem_reuniao',
                ]
            )

        qtd = qs_projetos.filter(documentoppc__situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO).distinct().count()
        if qtd:
            painel_projetos.append(
                ['Aguardando finalização de documento', qtd, '/admin/ppc/projetopedagogicocurso/?tab=tab_sem_documento_finalizado']
            )

        qtd = qs_projetos.filter(situacao=ProjetoPedagogicoCurso.APROVADO, matrizppc__isnull=True).count()
        if qtd:
            painel_projetos.append(
                [
                    'Aprovado sem matriz',
                    qtd,
                    f'/admin/ppc/projetopedagogicocurso/?situacao__exact={ProjetoPedagogicoCurso.APROVADO}&tab=tab_sem_matriz',
                ]
            )
    painel.append(['Projetos pedagógicos de curso', qtd_ppc_andamento, qtd_ppc_finalizada, qtd_ppc_rejeitada, painel_projetos])

    painel_solicitacoes = []
    qs_solicitacoes = SolicitacaoPPC.objects.all()
    qtd_s_andamento = qs_solicitacoes.exclude(situacao__in=[SolicitacaoPPC.REJEITADA, SolicitacaoPPC.FINALIZADA]).count()
    qtd_s_finalizada = qs_solicitacoes.filter(situacao=SolicitacaoPPC.FINALIZADA).count()
    qtd_s_rejeitada = qs_solicitacoes.filter(situacao=SolicitacaoPPC.REJEITADA).count()
    if qtd_s_andamento > 0:
        for situacao in SolicitacaoPPC.SITUACAO_CHOICES[0:5]:
            qtd = qs_solicitacoes.filter(situacao=situacao[0]).count()
            if qtd > 0:
                painel_solicitacoes.append([situacao[1], qtd, f'/admin/ppc/solicitacaoppc/?situacao__exact={situacao[0]}'])
    painel.append(['Solicitações', qtd_s_andamento, qtd_s_finalizada, qtd_s_rejeitada, painel_solicitacoes])

    return locals()


@permission_required('ppc.view_diretriz')
@rtr()
def diretriz(request, pk):
    diretriz = get_object_or_404(Diretriz, pk=pk)
    title = f'Diretriz: {diretriz.descricao}'
    tem_nucleo = diretriz.nucleodiretriz_set.exists()
    eixo_pendente = False
    qs_nd = diretriz.nucleodiretriz_set.filter(exige_eixo_tecnologico=True)
    if qs_nd.exists():
        nd_com_eixo = EixoTecnologicoDiretriz.objects.filter(nucleo_diretriz__diretriz_id=pk).values_list('nucleo_diretriz_id', flat=True)
        eixo_pendente = qs_nd.exclude(id__in=nd_com_eixo).exists()

    pode_editar = diretriz.can_change(request.user)
    alerta_edicao = pode_editar and diretriz.possui_ppc()
    return locals()


@rtr()
def equivalencia_hr_ha_diretriz(request, pk):
    diretriz = Diretriz.objects.filter(id=pk).only('equivalencia_hr_ha').first()
    return JsonResponse({'equivalencia_hr_ha': diretriz.equivalencia_hr_ha})


@permission_required('ppc.change_diretriz')
@rtr()
def replicar_diretriz(request, pk):
    diretriz = Diretriz.objects.get(id=pk)
    title = f'Replicar diretriz {diretriz.descricao}'
    form = ReplicarDiretrizForm(data=request.POST or None, files=request.FILES or None, diretriz=diretriz)
    if form.is_valid():
        replicado = form.replicar(diretriz)
        return httprr(replicado.get_absolute_url(), 'Diretriz replicada com sucesso.')
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def adicionar_nucleo_diretriz(request, pk):
    title = 'Adicionar núcleo à diretriz'
    form = NucleoDiretrizForm(data=request.POST or None, diretriz_id=pk)
    if form.is_valid():
        form.save()
        return httprr(f'/ppc/diretriz/{pk}/', 'Núcleo adicionado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def editar_nucleo_diretriz(request, pk):
    nucleodiretriz = NucleoDiretriz.objects.get(id=pk)
    title = f'Editar {nucleodiretriz.nucleo.descricao}'
    form = NucleoDiretrizForm(data=request.POST or None, instance=nucleodiretriz)
    if form.is_valid():
        form.save()
        return httprr('.', 'Núcleo atualizado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def adicionar_eixotecnologicodiretriz(request, pk):
    title = 'Adicionar eixo tecnológico ao núcleo da diretriz'
    form = EixoTecnologicoDiretrizForm(data=request.POST or None, nucleodiretriz_id=pk)
    if form.is_valid():
        form.save()
        return httprr('.', 'Eixo tecnológico adicionado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def editar_eixotecnologicodiretriz(request, pk):
    eixo = EixoTecnologicoDiretriz.objects.get(id=pk)
    title = f'Editar {eixo.eixo_tecnologico.descricao}'
    form = EixoTecnologicoDiretrizForm(data=request.POST or None, instance=eixo)
    if form.is_valid():
        form.save()
        return httprr('.', 'Eixo tecnológico atualizado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def adicionar_periodo_diretriz(request, pk):
    title = 'Adicionar Período à Diretriz'
    diretriz = Diretriz.objects.get(id=pk)
    form = PeriodoDiretrizForm(data=request.POST or None, diretriz=diretriz)
    if form.is_valid():
        form.save()
        return httprr(diretriz.get_absolute_url(), 'Período adicionado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def editar_periodo_diretriz(request, pk):
    periododiretriz = PeriodoDiretriz.objects.get(id=pk)
    title = 'Editar Período'
    form = PeriodoDiretrizForm(data=request.POST or None, instance=periododiretriz)
    if form.is_valid():
        form.save()
        return httprr(periododiretriz.diretriz.get_absolute_url(), 'Período atualizado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def adicionar_componente_exigido(request, pk):
    title = 'Adicionar Componente Exigido'
    form = ComponenteExigidoDiretrizForm(data=request.POST or None)
    if form.is_valid():
        form.cadastrar(pk)
        return httprr(f'/ppc/diretriz/{pk}/', 'Componente exigido adicionado com sucesso.', close_popup=True)

    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def editar_componente_exigido(request, pk):
    componenteexigido = ComponenteExigidoDiretriz.objects.get(id=pk)
    title = 'Editar Componente Exigido'
    form = ComponenteExigidoDiretrizForm(data=request.POST or None, instance=componenteexigido)
    if form.is_valid():
        form.save()
        return httprr(componenteexigido.diretriz.get_absolute_url(), 'Componente exigido atualizado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.view_modeloppc')
@rtr()
def modeloppc(request, pk):
    modelo = get_object_or_404(ModeloPPC, pk=pk)
    title = f'Modelo {modelo.descricao}'

    pode_replicar = modelo.is_administrador(request.user)
    pode_editar = modelo.can_change(request.user)
    pode_ativar = modelo.pode_ativar(request.user)
    pode_inativar = modelo.pode_inativar(request.user)
    pode_sobrescrever_conteudo_ppc = modelo.pode_sobrescrever_conteudo_ppc(request.user)

    possui_secao = modelo.secao_set.exists()
    possui_ppc = modelo.projetopedagogicocurso_set.exists()

    if possui_secao:
        secoes_conteudo_pendente = modelo.secao_set.filter(conteudo__isnull=True).only('titulo')
        tem_pendencia_secao = secoes_conteudo_pendente.exists()
    else:
        secoes_conteudo_pendente = []
        tem_pendencia_secao = False

    tab = request.GET.get('tab')
    if tab in [None, 'secao', 'conteudo']:
        pode_adicionar_secao = modelo.pode_adicionar_secao(request.user)
        pode_editar_secao = modelo.pode_editar_secao(request.user)

    if tab == 'conteudo':
        conteudos = Conteudo.objects.filter(secao__modelo_ppc_id=pk)

    if tab == 'ppc':
        ppcs = modelo.projetopedagogicocurso_set.all().only('id', 'situacao', 'nome_curso')
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def ativar_modeloppc(request, pk):
    modelo = ModeloPPC.objects.get(id=pk)
    if modelo.pode_ativar(request.user):
        modelo.ativar()
        return httprr(modelo.get_absolute_url(), 'Modelo de PPC ativado com sucesso.')
    return httprr(modelo.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_modeloppc')
@rtr()
def inativar_modeloppc(request, pk):
    modelo = ModeloPPC.objects.get(id=pk)
    if modelo.pode_inativar(request.user):
        modelo.inativar()
        return httprr(modelo.get_absolute_url(), 'Modelo de PPC inativado com sucesso.')
    return httprr(modelo.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@rtr()
def habilitar_sobrescrita_ppc_modeloppc(request, pk):
    modelo = ModeloPPC.objects.get(id=pk)
    if modelo.pode_sobrescrever_conteudo_ppc(request.user):
        modelo.habilitar_sobrescrita_ppc()
        return httprr(modelo.get_absolute_url(), 'Modelo de PPC habilitado para sobrescrita de PPC com sucesso.')
    return httprr(modelo.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.view_modeloppc')
@rtr()
def visualizar_modeloppc(request, pk):
    modelo = ModeloPPC.objects.get(id=pk)
    title = f'Modelo de PPC: {modelo.descricao}'
    conteudos = Conteudo.objects.filter(secao__modelo_ppc_id=pk)
    ppcs = ProjetoPedagogicoCurso.objects.filter(modelo_ppc_id=pk)
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def replicar_modelo_ppc(request, pk):
    modelo = ModeloPPC.objects.get(id=pk)
    if modelo.is_administrador(request.user):
        title = f'Replicar Modelo de PPC {modelo.descricao}'
        form = ReplicarModeloPPCForm(data=request.POST or None, user=request.user)
        if form.is_valid():
            replicado = form.replicar(modelo)
            return httprr(replicado.get_absolute_url(), 'Modelo de PPC replicado com sucesso.')
    else:
        return httprr(modelo.get_absolute_url(), 'Você não tem permissão para replicar este modelo de PPC.', 'error')
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def adicionar_secao(request, pk):
    title = 'Adicionar Seção'
    modeloppc = ModeloPPC.objects.get(id=pk)
    if modeloppc.pode_adicionar_secao(request.user):
        form = SecaoForm(data=request.POST or None, modelo_ppc_id=pk)
        if form.is_valid():
            form.save()
            return httprr('.', 'Seção adicionada com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para adicionar seção neste modelo de PPC', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def editar_secao(request, pk):
    secao = Secao.objects.get(id=pk)
    if secao.modelo_ppc.pode_editar_secao(request.user):
        title = 'Editar Seção'
        form = SecaoForm(data=request.POST or None, instance=secao)
        if form.is_valid():
            form.save()
            return httprr('.', 'Seção atualizada com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para alterar esta seção.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def adicionar_conteudo(request, pk):
    title = 'Adicionar Conteúdo'
    modeloppc = ModeloPPC.objects.get(id=pk)
    if modeloppc.pode_adicionar_secao(request.user):
        form = ConteudoForm(data=request.POST or None, modelo_ppc_id=pk)
        if form.is_valid():
            form.processar()
            return httprr('.', 'Conteúdo adicionado com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para adicionar conteúdo neste modelo de PPC.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def editar_conteudo(request, pk):
    conteudo = Conteudo.objects.get(id=pk)
    if conteudo.secao.modelo_ppc.pode_editar_secao(request.user):
        title = 'Editar Conteúdo'
        form = ConteudoForm(data=request.POST or None, instance=conteudo)
        if form.is_valid():
            form.processar()
            return httprr('.', 'Conteúdo atualizado com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para editar este conteúdo.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.view_modeloplanodisciplina')
@rtr()
def modeloplanodisciplina(request, pk):
    modelo = ModeloPlanoDisciplina.objects.get(id=pk)
    title = modelo.descricao
    tem_secao = modelo.modelosecaoplanodisciplina_set.exists()
    pode_adicionar_secao = modelo.pode_adicionar_secao(request.user)
    if request.GET.get('tab', '') == 'planos':
        planos = (
            modelo.planodisciplina_set.all().only('nome_disciplina', 'ch_disciplina', 'tipo_oferta', 'ativo').order_by('-ativo', 'nome_disciplina')
        )
    return locals()


@permission_required('ppc.add_modeloplanodisciplina')
@rtr()
def replicar_modeloplanodisciplina(request, pk):
    modelo = ModeloPlanoDisciplina.objects.get(id=pk)
    title = f'Replicar {modelo.descricao}'
    form = ReplicarModeloPlanoDisciplinaForm(data=request.POST or None)
    if form.is_valid():
        replicado = form.replicar(modelo)
        return httprr(replicado.get_absolute_url(), 'Modelo de plano de disciplina replicado com sucesso.')
    return locals()


@permission_required('ppc.add_modeloplanodisciplina')
@rtr()
def ativar_modeloplanodisciplina(request, pk):
    modelo = ModeloPlanoDisciplina.objects.get(id=pk)
    modelo.ativo = True
    modelo.save()
    return httprr(modelo.get_absolute_url(), 'Modelo de plano de disciplina ativo com sucesso.')


@permission_required('ppc.add_modeloplanodisciplina')
@rtr()
def adicionar_modelosecaoplanodisciplina(request, pk):
    title = 'Adicionar Seção'
    form = ModeloSecaoPlanoDisciplinaForm(data=request.POST or None, modelo_plano_disciplina_id=pk)
    if form.is_valid():
        form.save()
        return httprr('.', 'Seção adicionada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.add_modeloplanodisciplina')
@rtr()
def editar_modelosecaoplanodisciplina(request, pk):
    secao = ModeloSecaoPlanoDisciplina.objects.get(id=pk)
    title = 'Editar Seção'
    form = ModeloSecaoPlanoDisciplinaForm(data=request.POST or None, instance=secao)
    if form.is_valid():
        form.save()
        return httprr('.', 'Seção atualizada com sucesso.', close_popup=True)

    return locals()


@permission_required('ppc.view_solicitacaoppc')
@rtr()
def solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    title = f'Solicitação de {solicitacao.get_tipo_solicitacao_display().lower()} de PPC: {solicitacao.nome_curso}'
    situacoes = solicitacao.get_situacoes()

    erro = None
    ata = None
    portaria = None
    qtd_documentos = 0
    try:
        if solicitacao.id_ata:
            ata = solicitacao.get_ata()
            if ata == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE:
                ata = None
            else:
                qtd_documentos += 1
                solicitacao = solicitacao.atualizar_situacao(ata)

        if solicitacao.id_portaria:
            portaria = solicitacao.get_portaria()
            if portaria == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE:
                portaria = None
            else:
                qtd_documentos += 1
                solicitacao = solicitacao.atualizar_situacao(portaria)
    except ValidationError as e:
        erro = e.message

    pode_editar = solicitacao.pode_editar(request.user)
    pode_solicitar_ata = solicitacao.pode_solicitar_ata(request.user)
    pode_emitir_ata = solicitacao.pode_emitir_ata(request.user)
    pode_reemitir_ata = solicitacao.id_ata and ata is None and solicitacao.pode_emitir_ata(request.user, ignore_id=True) or False
    pode_indicar_elaborador = solicitacao.pode_indicar_elaborador(request.user)
    pode_solicitar_avaliacao_elaboradores = solicitacao.pode_solicitar_avaliacao_elaboradores(request.user)
    pode_avaliar_elaboradores = solicitacao.pode_avaliar_elaboradores(request.user)
    pode_editar_setor_avaliacao_elaboradores = solicitacao.pode_editar_setor_avaliacao_elaboradores(request.user)
    pode_solicitar_portaria = solicitacao.pode_solicitar_portaria(request.user)
    pode_emitir_portaria = solicitacao.pode_emitir_portaria(request.user)
    pode_devolver_analise = solicitacao.pode_devolver_analise(request.user)
    pode_reemitir_portaria = solicitacao.id_portaria and portaria is None and solicitacao.pode_emitir_portaria(request.user, ignore_id=True) or False
    pode_vincular_portaria = Configuracao.get_valor_por_chave('ppc', 'permite_vincular_portaria_solicitacao') and (
        pode_editar or pode_solicitar_portaria
    )
    exige_ata = solicitacao.exige_ata_colegiado()

    indicacoes = solicitacao.indicacaoelaboradorppc_set.all()
    indicacoes_deferidas = solicitacao.indicacaoelaboradorppc_set.filter(deferido=True)

    processo_convenio = solicitacao.get_processo_convenio()
    movimentacoes = solicitacao.movimentacaosolicitacaoppc_set.all()
    ppc = solicitacao.get_ppc()

    exibe_alerta_indicacao_elaborador = pode_indicar_elaborador and not indicacoes.exists()
    exibe_alerta_sem_portaria = solicitacao.situacao == SolicitacaoPPC.EMISSAO_PORTARIA and portaria is None
    exibe_alerta_portaria_pendente = solicitacao.situacao == SolicitacaoPPC.EMISSAO_PORTARIA and portaria and not portaria.estah_finalizado
    exibe_alerta_ata_pendente = solicitacao.situacao == SolicitacaoPPC.EMISSAO_ATA and ata and not ata.estah_finalizado
    exibe_alerta_avaliacao_elaborador = solicitacao.situacao == SolicitacaoPPC.EM_ANALISE and (
        solicitacao.indicacaoelaboradorppc_set.filter(deferido=None).exists() or not solicitacao.indicacaoelaboradorppc_set.exists()
    )
    exibe_alerta_nome_curso = (
        solicitacao.is_criacao()
        and ppc is None
        and CursoCampus.objects.filter(ativo=True)
        .filter(Q(descricao_historico=solicitacao.nome_curso) | Q(descricao=solicitacao.nome_curso))
        .exists()
    )

    return locals()


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def emitir_ata_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    ignore_id = solicitacao.id_ata and solicitacao.get_ata() == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE
    if solicitacao.pode_emitir_ata(request.user, ignore_id=ignore_id):
        solicitacao.emitir_ata(request.user)
        return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', 'Ata gerada com sucesso.')
    return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def emitir_portaria_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    ignore_id = solicitacao.id_portaria and solicitacao.get_portaria() == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE
    if solicitacao.pode_emitir_portaria(request.user, ignore_id=ignore_id):
        try:
            solicitacao.emitir_portaria(request.user)
        except ValidationError as e:
            return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', e.message, 'error')
        return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', 'Portaria gerada com sucesso.')
    return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def devolver_analise_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    if solicitacao.pode_devolver_analise(request.user):
        solicitacao.devolver_analise(request.user)
        return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', 'Solicitação devolvida para análise com sucesso.')
    return httprr(f'{solicitacao.get_absolute_url()}?tab=documentos', 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def reprovar_solicitacaoppc(request, pk):
    title = f'Reprovar Solicitação {pk}'
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    form = RejeitarSolicitacaoPPCForm(data=request.POST or None, instance=solicitacao)
    if form.is_valid():
        form.processar(request.user)
        return httprr(solicitacao.get_absolute_url(), 'Solicitação reprovada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def devolver_solicitacaoppc(request, pk):
    title = 'Solicitar correção'
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    form = DevolverSolicitacaoPPCForm(data=request.POST or None, instance=solicitacao)
    if form.is_valid():
        form.processar(request.user)
        return httprr('.', 'Solicitação enviada para correção com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def suspender_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    title = f'Suspender solicitação {solicitacao.id}'
    return locals()


@permission_required('ppc.add_solicitacaoppc')
@rtr()
def enviar_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    if solicitacao.pode_solicitar_avaliacao_elaboradores(request.user):
        if solicitacao.tipo_oferta_id == Modalidade.FIC_MENOS:
            form = SolicitarAvaliacaoElaboradorForm(data=request.POST or None, instance=solicitacao)
            if form.is_valid():
                form.processar(request.user)
                return httprr('.', 'Solicitação enviada com sucesso.', close_popup=True)
            return locals()
        else:
            setor_id = Configuracao.get_valor_por_chave('ppc', 'setor_revisao_plano_disciplina')
            setor = setor_id and Setor.objects.suap_ativos().get(id=setor_id) or None
            try:
                solicitacao.enviar_analise(request.user, setor)
            except ValidationError as e:
                return httprr('.', e.message, 'error', close_popup=True)
            return httprr('.', 'Solicitação enviada com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.add_solicitacaoppc')
@rtr()
def editar_setor_avaliacao_elaboradores_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    if solicitacao.pode_editar_setor_avaliacao_elaboradores(request.user):
        form = SolicitarAvaliacaoElaboradorForm(data=request.POST or None, instance=solicitacao)
        if form.is_valid():
            form.processar(request.user)
            return httprr(solicitacao.get_absolute_url(), 'Alteração realizada com sucesso.', close_popup=True)
        return locals()
    else:
        return httprr(solicitacao.get_absolute_url(), 'Você não tem permissão para isso.', close_popup=True)


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def aprovar_indicacao_elaboracao(request, pk):
    indicacao = IndicacaoElaboradorPPC.objects.get(id=pk)
    if indicacao.solicitacao.pode_avaliar_elaboradores(request.user):
        indicacao.aprovar(request.user)
        return httprr(f'{indicacao.solicitacao.get_absolute_url()}?tab=indicacao', 'Indicação aprovada com sucesso.')
    return httprr(f'{indicacao.solicitacao.get_absolute_url()}?tab=indicacao', 'Você não tem permissão para isso.')


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def negar_indicacao_elaboracao(request, pk):
    title = 'Reprovar indicação'
    indicacao = IndicacaoElaboradorPPC.objects.get(id=pk)
    if indicacao.solicitacao.pode_avaliar_elaboradores(request.user):
        form = RejeitarIndicacaoElaboradorPPCForm(data=request.POST or None, instance=indicacao)
        if form.is_valid():
            form.processar(request.user)
            return httprr(f'{indicacao.solicitacao.get_absolute_url()}?tab=indicacao', 'Indicação negada com sucesso.', close_popup=True)
        return locals()
    return httprr(f'{indicacao.solicitacao.get_absolute_url()}?tab=indicacao', 'Você não tem permissão para isso.', close_popup=True)


@permission_required('ppc.add_solicitacaoppc')
@rtr()
def solicitar_ata_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    if solicitacao.pode_solicitar_ata(request.user):
        solicitacao.solicitar_ata(request.user)
        return httprr(solicitacao.get_absolute_url(), 'Emissão de ata solicitada com sucesso.')
    else:
        return httprr(solicitacao.get_absolute_url(), 'Você não tem permissão para solicitar a emissão de ata.')


@permission_required('ppc.add_solicitacaoppc')
@rtr()
def vincular_portaria_solicitacaoppc(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    if solicitacao.pode_editar(request.user) or solicitacao.pode_solicitar_portaria(request.user):
        form = VincularPortariaSolicitacaoPPCForm(data=request.POST or None, instance=solicitacao)
        if form.is_valid():
            form.save()
            return httprr('.', 'Portaria vinculada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.add_solicitacaoppc')
@rtr()
def solicitar_emissao_portaria(request, pk):
    solicitacao = get_object_or_404(SolicitacaoPPC, pk=pk)
    if solicitacao.pode_solicitar_portaria(request.user):
        solicitacao.solicitar_portaria(request.user)
        return httprr(solicitacao.get_absolute_url(), 'Emissão de portaria solicitada com sucesso.')
    else:
        return httprr(solicitacao.get_absolute_url(), 'Você não tem permissão para solicitar a emissão de portaria.')


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def adicionar_avaliador_solicitacaoppc(request, pk):
    title = 'Adicionar Membro'
    form = MembroColegiadoForm(data=request.POST or None)
    if form.is_valid():
        form.cadastrar(pk)
        return httprr(f'/ppc/solicitacaoppc/{pk}/', 'Avaliador adicionado com sucesso.', close_popup=True)

    return locals()


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def indicar_avaliador_solicitacaoppc(request, pk):
    title = 'Adicionar Indicação'
    form = IndicacaoElaboradorPPCForm(data=request.POST or None)
    if form.is_valid():
        form.cadastrar(pk, request.user)
        return httprr('.', 'Indicação adicionada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_solicitacaoppc')
@rtr()
def editar_indicacaoelaboradorppc(request, pk):
    indicacao = IndicacaoElaboradorPPC.objects.get(pk=pk)
    title = f'Editar indicação - {indicacao.vinculo.pessoa.nome_usual}'
    form = IndicacaoElaboradorPPCForm(data=request.POST or None, instance=indicacao)
    if form.is_valid():
        form.save()
        return httprr('.', 'Indicação atualizada com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def conteudo_visualizar(request, projeto_pedagogico_curso_id):
    projeto = ProjetoPedagogicoCurso.objects.get(pk=projeto_pedagogico_curso_id)
    title = f'Projeto Pedagógico de Curso: {projeto.nome_curso}'
    conteudos = projeto.conteudoppc_set.all()
    return locals()


@permission_required('ppc.view_projetopedagogicocurso')
def minuta_projetopedagogicocurso(request, pk):
    projeto = ProjetoPedagogicoCurso.objects.get(pk=pk)
    if projeto.is_finalizado():
        return httprr(reverse('projetopedagogicocurso', args=(pk,)), 'Não é possível gerar a minuta de PPC finalizado.', 'error')
    return tasks.gerar_minuta_ppc(request, projeto)


@documento(enumerar_paginas=True)
@rtr('ppc_pdf.html')
def minuta_ppc_pdf(request, projeto):
    title = 'Minuta do projeto pedagógico de curso'
    minuta = True
    secoes = projeto.get_secoes_conteudo()
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    return locals()


@documento(tipo_para_verificacao='Projeto pedagógico de curso', modelo='ppc.projetopedagogicocurso', enumerar_paginas=True)
@login_required
@rtr('ppc_pdf.html')
def ppc_pdf(request, pk):
    projeto = ProjetoPedagogicoCurso.objects.get(pk=pk)
    if not projeto.is_finalizado():
        return httprr(reverse('projetopedagogicocurso', args=(pk,)), 'Esta ação estará disponível após finalização do PPC.', 'error')
    title = 'Projeto pedagógico de curso'
    secoes = projeto.get_secoes_conteudo()
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    return locals()


@documento(enumerar_paginas=True)
@rtr()
def imprimir_modeloppc(request, pk):
    title = 'Preview'
    modeloppc = get_object_or_404(ModeloPPC, pk=pk)
    conteudos = Conteudo.objects.filter(secao__modelo_ppc_id=pk)
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def editar_texto_conteudo(request, pk):
    conteudo = get_object_or_404(Conteudo, pk=pk)
    if conteudo.pode_editar_texto(request.user):
        form = EditarTextoConteudoForm(request.POST or None, instance=conteudo)
        if form.is_valid():
            form.processar()
            return httprr('.', 'Conteúdo atualizado com sucesso.', close_popup=True)
    else:
        return httprr('.', 'O texto deste conteúdo não pode ser alterado', close_popup=True)
    return locals()


@permission_required('ppc.change_modeloppc')
@rtr()
def tornar_editavel_conteudo(request, pk, editavel):
    conteudo = get_object_or_404(Conteudo, pk=pk)
    if editavel == 'SIM' and conteudo.pode_tornar_editavel(request.user):
        conteudo.tornar_editavel()
        return httprr(f'{conteudo.secao.modelo_ppc.get_absolute_url()}?tab=conteudo', 'Alteração realizada com sucesso.')
    elif editavel == 'NAO' and conteudo.pode_tornar_nao_editavel(request.user):
        conteudo.tornar_nao_editavel()
        return httprr(f'{conteudo.secao.modelo_ppc.get_absolute_url()}?tab=conteudo', 'Alteração realizada com sucesso.')
    else:
        return httprr(f'{conteudo.secao.modelo_ppc.get_absolute_url()}?tab=conteudo', 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.view_projetopedagogicocurso')
@rtr()
def matrizppc(request, pk):
    matrizppc = get_object_or_404(MatrizPPC, pk=pk)
    title = f'Matriz: {matrizppc.nome}'
    pode_elaborar = matrizppc.ppc.pode_elaborar(request.user)
    pode_revisar = matrizppc.ppc.pode_revisar(request.user)
    nucleos_matriz = matrizppc.ppc.get_nucleos_matriz().distinct()
    pode_elaborar_matriz = pode_elaborar and matrizppc.situacao_matriz == MatrizPPC.MATRIZ_EM_ELABORACAO and matrizppc.ppc.periodicidade
    lista_periodos = matrizppc.get_periodos()
    maior_periodo = matrizppc.quantidade_periodos

    # MATRIZ CURRICULAR
    if request.GET.get('tab') in ['matriz', None]:
        pode_concluir_matriz = matrizppc.pode_concluir_matriz(request.user)
        pode_desfazer_aprovacao_matriz = matrizppc.pode_desfazer_aprovacao_matriz(request.user)
        pode_retomar_edicao_matriz = pode_elaborar and matrizppc.situacao_matriz == MatrizPPC.MATRIZ_AGUARDANDO_REVISAO
        pode_revisar_matriz = pode_revisar and matrizppc.situacao_matriz == MatrizPPC.MATRIZ_EM_REVISAO
        pode_aprovar_revisao_matriz = (
            pode_revisar_matriz
            and not matrizppc.planodisciplinappc_set.exclude(
                plano_disciplina__situacao=PlanoDisciplina.APROVADO, plano_disciplina__ativo=True
            ).exists()
        )
        exige_ead = matrizppc.ppc.diretriz.percentual_min_ead or matrizppc.ppc.diretriz.percentual_max_ead

    # QUADRO RESUMO
    if request.GET.get('tab') == 'quadro-resumo':
        semestres = [1, 2]
        planos_disciplinappc = matrizppc.get_planos_disciplinappc()
        tem_extensao = matrizppc.ppc.ch_cc_extensao > 0 or planos_disciplinappc.filter(ch_extensao__gt=0).exists()
        tem_optativo = matrizppc.ppc.ch_cc_optativo > 0 or planos_disciplinappc.filter(optativo=True).exists()
        planos_disciplinas_com_associacao = matrizppc.get_planos_disciplinas_com_associacao()

    # PRATICA PROFISSIONAL
    if request.GET.get('tab') == 'pratica':
        pode_concluir_modalidadepraticaprofissional = matrizppc.pode_concluir_modalidadepraticaprofissional(request.user)
        pode_desfazer_aprovacao_modalidadepraticaprofissional = matrizppc.pode_desfazer_aprovacao_modalidadepraticaprofissional(request.user)
        pode_retomar_edicao_modalidadepraticaprofissional = (
            pode_elaborar and matrizppc.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO
        )
        pode_revisar_modalidadepraticaprofissional = matrizppc.pode_revisar_modalidadepraticaprofissional(request.user)
        pode_elaborar_pratica = (
            pode_elaborar and matrizppc.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO
        )

    # MATRIZ E CURSOS
    if request.GET.get('tab') == 'matriz_cursos':
        pode_gerar_curso = matrizppc.pode_gerar_curso(request.user)
        pode_vincular_curso = matrizppc.pode_vincular_curso(request.user)
        pode_remover_curso = pode_gerar_curso or pode_vincular_curso

    # PENDENCIAS
    exibe_pendencias = matrizppc.ppc.situacao in [
        ProjetoPedagogicoCurso.INICIADO,
        ProjetoPedagogicoCurso.EM_ELABORACAO,
        ProjetoPedagogicoCurso.EM_REVISAO,
        ProjetoPedagogicoCurso.APROVADO,
    ]
    tem_pendencia = matrizppc.get_pendencias(check_fast=True) if exibe_pendencias else False
    if request.GET.get('tab') == 'pendencias':
        pendencias = matrizppc.get_pendencias() if tem_pendencia else []

    return locals()


@permission_required('ppc.view_projetopedagogicocurso')
@rtr()
def projetopedagogicocurso(request, pk):
    projeto = get_object_or_404(ProjetoPedagogicoCurso, pk=pk)
    title = f'PPC: {projeto.nome_curso}'

    projeto.atualizar_situacao()
    DocumentoPPC.atualizar_situacao(projeto)
    documentos_emissao = projeto.get_documentos_para_emissao(request.user)
    alerts = projeto.get_alerts(request.user)
    infos = projeto.get_infos(request.user)
    criticals = projeto.get_criticals(request.user)

    em_elaboracao = projeto.situacao == ProjetoPedagogicoCurso.EM_ELABORACAO
    em_revisao = projeto.situacao == ProjetoPedagogicoCurso.EM_REVISAO

    pode_convocar_camara = projeto.pode_convocar_camara(request.user)

    solicitacao = projeto.solicitacao
    portaria = solicitacao.get_portaria()

    situacoes = copy.copy(ProjetoPedagogicoCurso.SITUACAO_CHOICES)
    if projeto.situacao != ProjetoPedagogicoCurso.REJEITADO:
        situacoes.pop(int(ProjetoPedagogicoCurso.REJEITADO) - 1)

    if projeto.is_tramite_adequacao() and not projeto.consepex_inexistente:
        situacoes.pop(int(ProjetoPedagogicoCurso.ANALISE_CONSUP) - 1)

    pode_finalizar = projeto.pode_finalizar(request.user)
    camara = projeto.camara
    movimentacoes = projeto.movimentacaoppc_set.all()
    pode_gerar_matrizes = projeto.pode_gerar_matrizes(request.user)

    pode_adicionar_portaria_elaboracao = projeto.pode_adicionar_portaria_elaboracao(request.user)
    pode_atualizar_comissao_elaboracao = projeto.pode_atualizar_comissao_elaboracao(request.user)
    pode_editar_elaborador = projeto.is_coordenador_elaboracao(request.user) and not projeto.is_comissao_em_atualizacao()
    pode_enviar_elaboracao = projeto.pode_enviar_elaboracao(request.user)

    pode_adicionar_revisor = projeto.pode_adicionar_revisor(request.user)
    pode_elaborar = projeto.pode_elaborar(request.user)

    pode_convocar_consepex = camara and projeto.pode_convocar_consepex(request.user)
    pode_convocar_consup = camara and projeto.pode_convocar_consup(request.user)

    qtd_equipe = projeto.elaboradorppc_set.count() + projeto.revisorppc_set.count() + projeto.colaboradorppc_set.filter(ativo=True).count()

    tab = request.GET.get('tab', '')

    # DADOS DO CURSO
    pode_editar_dados_curso = projeto.can_change(request.user)

    # CONTEUDO
    if tab == 'conteudo':
        secoes = projeto.get_secoes_conteudo()

        pode_assumir_revisao = projeto.pode_assumir_revisao(request.user)
        pode_revisar = projeto.pode_revisar(request.user)

        qtd_total_conteudo = projeto.conteudoppc_set.count() if em_elaboracao or em_revisao else 0
        if em_elaboracao:
            qtd_concluido = projeto.conteudoppc_set.exclude(situacao=ConteudoPPC.EM_EDICAO).count()
            percentual_concluido = round(qtd_concluido * 100 / qtd_total_conteudo)

        elif em_revisao:
            qtd_concluido = projeto.conteudoppc_set.filter(situacao=ConteudoPPC.HOMOLOGADO).count()
            percentual_concluido = round(qtd_concluido * 100 / qtd_total_conteudo)

        lista_marcadores_dinamicos = []
        for item, nucleo in projeto.get_marcadores_dinamicos():
            lista_marcadores_dinamicos.append(
                f'{{{{ {item} }}}}: Incorporta no texto a listagem da ementa e programa dos planos de disciplinas do núcleo {nucleo}.'
            )

    # MATRIZES
    alertas_matriz = projeto.get_alerts_matriz()

    # REITORIA
    pode_informar_reitoria = projeto.pode_informar_reitoria(request.user)
    pendencia_reitoria = projeto.possui_pendencia_reitoria()

    # PENDENCIAS
    exibe_pendencias = projeto.situacao in [
        ProjetoPedagogicoCurso.INICIADO,
        ProjetoPedagogicoCurso.EM_ELABORACAO,
        ProjetoPedagogicoCurso.EM_REVISAO,
        ProjetoPedagogicoCurso.APROVADO,
    ]
    if exibe_pendencias:
        pendencias = projeto.get_pendencias()

    # DOCUMENTOS
    documentos = DocumentoPPC.objects.filter(ppc_id=pk).order_by('-tipo_documento', '-data_emissao')

    # PAFC
    pafcs = projeto.get_pafcs()

    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def gerar_bibliografia_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    if ppc.pode_elaborar(request.user) or ppc.pode_revisar(request.user):
        return tasks.gerar_bibliografia(ppc)
    return httprr(
        ppc.get_absolute_url('tab=bibliografia'),
        'Você não tem permissão para isso.',
        'error',
    )


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def alterar_modelo_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    modelo = ppc.modelo_ppc
    url_retorno = f'{modelo.get_absolute_url()}?tab=ppc'
    if ppc.pode_alterar_modeloppc(request.user):
        try:
            ppc.alterar_modeloppc()
            return httprr(url_retorno, f'Modelo do PPC {ppc} alterado com sucesso.')
        except ValidationError as e:
            return httprr(url_retorno, e.message, 'error')
    return httprr(url_retorno, 'Você não tem permissão para alterar o modelo do PPC.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def gerar_matriz_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Gerar matriz curricular'
    if ppc.pode_gerar_matrizes(request.user):
        form = GerarMatrizPPCForm(data=request.POST or None, instance=ppc)
        if form.is_valid():
            form.processar(request.user)
            return httprr('.', 'Matriz curricular gerada com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def gerar_cursos_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Gerar curso'
    if matrizppc.pode_gerar_curso(request.user):
        form = GerarCursoPPCForm(data=request.POST or None, instance=matrizppc)
        if form.is_valid():
            form.processar(request.user)
            return httprr('.', 'Cursos gerados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def vincular_cursos_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Vincular cursos à matriz curricular'
    if matrizppc.pode_vincular_curso(request.user):
        form = VincularCursoPPCForm(data=request.POST or None, instance=matrizppc)
        if form.is_valid():
            form.processar(request.user)
            return httprr('.', 'Cursos vinculados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def remover_curso_matrizppc(request, pk, curso_id):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.pode_vincular_curso(request.user):
        curso = matrizppc.cursos.filter(id=curso_id).first()
        if curso:
            matrizcurso = curso.get_matrizcurso(matrizppc.matriz_id)
            if matrizcurso is None or matrizcurso.pode_ser_excluida():
                matrizppc.remover_matrizcurso(request.user, matrizcurso, curso)
                return httprr(matrizppc.get_absolute_url('tab=matriz_cursos'), 'Curso desvinculado da matriz com sucesso.')
    elif matrizppc.pode_gerar_curso(request.user):
        curso = matrizppc.cursos.filter(id=curso_id).first()
        if curso is None:
            matrizppc.cursos.remove(curso)
            return httprr(matrizppc.get_absolute_url('tab=matriz_cursos'), 'Curso removido deste PPC com sucesso.')
        else:
            matrizcurso = curso.get_matrizcurso(matrizppc.matriz_id)
            if matrizcurso is None or matrizcurso.pode_ser_excluida():
                matrizppc.remover_matrizcurso(request.user, matrizcurso, curso, remove_curso=True)
                return httprr(matrizppc.get_absolute_url('tab=matriz_cursos'), 'Curso removido deste PPC com sucesso.')
    return httprr(matrizppc.get_absolute_url('tab=matriz_cursos'), 'Você não tem permissão para isso.', 'error')


@permission_required('comum.is_administrador_academico')
@rtr()
def finalizar_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    if ppc.pode_finalizar(request.user):
        ppc.finalizar(request.user)
        return httprr(ppc.get_absolute_url(), 'PPC finalizado com sucesso.')
    else:
        return httprr(ppc.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_matrizppc(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Adicionar matriz ao PPC'
    if ppc.pode_elaborar(request.user):
        form = MatrizPPCForm(data=request.POST or None, ppc=ppc)
        if form.is_valid():
            form.processar()
            return httprr('.', 'Matriz adicionada com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def replicar_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Replicar matriz do PPC'
    if matrizppc.ppc.pode_elaborar(request.user):
        form = ReplicarMatrizPPCForm(data=request.POST or None, instance=matrizppc)
        if form.is_valid():
            nova_matriz = form.processar()
            return httprr(nova_matriz.get_absolute_url(), 'Matriz replicada com sucesso.')
    else:
        return httprr(matrizppc.get_absolute_url(), 'Você não tem permissão para isso.', 'error')
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Editar matriz do PPC'
    if matrizppc.ppc.pode_elaborar(request.user):
        form = MatrizPPCForm(data=request.POST or None, instance=matrizppc)
        if form.is_valid():
            form.save()
            return httprr('.', 'Matriz atualizada com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_configuracaooptativasmatrizppc(request, pk):
    obj = ConfiguracaoOptativasMatrizPPC.objects.get(id=pk)
    title = f'Editar configuração de optativas do {obj.periodo}° período'
    if obj.matriz_ppc.ppc.pode_elaborar(request.user):
        form = ConfiguracaoOptativasMatrizPPCForm(data=request.POST or None, instance=obj)
        if form.is_valid():
            try:
                form.save()
                return httprr('.', 'Configuração de optativas da matriz atualizada com sucesso.', close_popup=True)
            except IntegrityError:
                return httprr('.', 'O núcleo informado já está configurado em outra configuração deste período da matriz.', 'error', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_configuracaooptativasmatrizppc(request, pk):
    obj = MatrizPPC.objects.get(id=pk)
    title = 'Adicionar configuração de optativas'
    if obj.ppc.pode_elaborar(request.user):
        form = AdicionarConfiguracaoOptativasMatrizPPCForm(data=request.POST or None, matriz_ppc=obj)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                return httprr('.', 'O núcleo informado já está configurado em outra configuração deste período da matriz.', 'error', close_popup=True)
            return httprr('.', 'Configuração de optativas da matriz adicionada com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def informar_reitoria_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Informar dados da Reitoria'
    if ppc.pode_informar_reitoria(request.user):
        form = InformarReitoriaForm(data=request.POST or None, instance=ppc)
        if form.is_valid():
            form.save()
            return httprr('.', 'Dados informados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def convocar_camara_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Informar dados da Câmara'
    if ppc.pode_convocar_camara(request.user):
        form = ConvocarCamaraForm(data=request.POST or None, instance=ppc)
        if form.is_valid():
            ppc = form.save()
            return httprr('.', 'Dados informados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def emitir_documento_projetopedagogicocurso(request, pk, documento, documento_existe=None):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    pode_emitir = ppc.pode_emitir_documento(request.user, documento)
    title = f'Emitir {documento}' if documento_existe is None else f'Vincular {documento}'
    setor = None
    if pode_emitir:
        setor_id = request.user.get_vinculo().setor_id
        if documento == 'Parecer':
            if ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO:
                form = EmitirParecerRevisaoForm(data=request.POST or None, instance=ppc, setor_id=setor_id, documento_existe=documento_existe)
                if form.is_valid():
                    ppc, setor, documento_eletronico = form.processar()
                else:
                    return locals()
            elif ppc.situacao == ProjetoPedagogicoCurso.ANALISE_CAMARA:
                form = EmitirParecerCamaraForm(data=request.POST or None, instance=ppc, setor_id=setor_id, documento_existe=documento_existe)
                if form.is_valid():
                    ppc, setor, documento_eletronico = form.processar()
                else:
                    return locals()
        elif documento in ['Deliberação', 'Deliberação de homologação', 'Deliberação Ad Referendum']:
            form = EmitirDeliberacaoCONSEPEXForm(
                data=request.POST or None, instance=ppc, documento=documento, setor_id=setor_id, documento_existe=documento_existe
            )
            if form.is_valid():
                ppc, setor, documento_eletronico = form.processar()
            else:
                return locals()
        elif documento in ['Resolução', 'Resolução de homologação', 'Resolução Ad Referendum']:
            form = EmitirResolucaoCONSUPForm(
                data=request.POST or None, instance=ppc, documento=documento, setor_id=setor_id, documento_existe=documento_existe
            )
            if form.is_valid():
                ppc, setor, documento_eletronico = form.processar()
            else:
                return locals()
        elif documento == 'Despacho':
            if ppc.situacao == ProjetoPedagogicoCurso.ANALISE_PROREITORIA:
                form = EmitirDespachoProReitoriaForm(data=request.POST or None, instance=ppc, setor_id=setor_id, documento_existe=documento_existe)
                if form.is_valid():
                    ppc, setor, documento_eletronico = form.processar()
                else:
                    return locals()
            elif ppc.situacao in [ProjetoPedagogicoCurso.ANALISE_CONSEPEX, ProjetoPedagogicoCurso.ANALISE_CAMARA]:
                form = EmitirDocumentoForm(data=request.POST or None, instance=ppc, setor_id=setor_id, documento_existe=documento_existe)
                if form.is_valid():
                    ppc, setor, documento_eletronico = form.processar()
                else:
                    return locals()
        else:
            return httprr('.', 'Tipo de documento não informado.', 'error', close_popup=True)
        DocumentoPPC.emitir_documento(ppc, request.user, documento, setor, documento_eletronico)
        return httprr('.', 'Documento gerado com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('comum.is_administrador_de_ppc')
@rtr()
def vincular_documentoeletronico_documentoppc(request, pk):
    documentoppc = DocumentoPPC.objects.get(id=pk)
    pode_vincular = documentoppc.pode_vincular_documento(request.user)
    title = f'Vincular {documentoppc.get_tipo_documento_display()} ao PPC'
    if pode_vincular:
        form = VincularDocumentoPPCForm(data=request.POST or None, documentoppc=documentoppc)
        if form.is_valid():
            form.save()
            return httprr('.', 'Documento vinculado com sucesso.', close_popup=True)
        return locals()
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def convocar_consepex_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Convocar CONSEPEX'
    if ppc.pode_convocar_consepex(request.user):
        form = ConvocarCONSEPEXForm(data=request.POST or None, instance=ppc)
        if form.is_valid():
            ppc = form.save()
            return httprr('', 'Dados atualizados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def convocar_consup_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Convocar CONSUP'
    if ppc.pode_convocar_consup(request.user):
        form = ConvocarCONSUPForm(data=request.POST or None, instance=ppc)
        if form.is_valid():
            ppc = form.save()
            return httprr('', 'Dados atualizados com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_portaria_elaboracao_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Atualizar comissão de elaboração'
    if ppc.pode_adicionar_portaria_elaboracao(request.user):
        form = AtualizacaoComissaoElaboracaoForm(data=request.POST or None)
        if form.is_valid():
            form.processar(pk)
            return httprr('.', 'Portaria da comissão de elaboração adicionada com sucesso. Atualize os membros da comissão.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def concluir_atualizacao_portaria_elaboracao_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    if ppc.pode_atualizar_comissao_elaboracao(request.user):
        atualizacao = ppc.get_atualizacao_comissao()
        atualizacao.concluida = True
        atualizacao.save()
        return httprr(ppc.get_absolute_url('tab=equipe'), 'Atualização da comissão de elaboração concluída com sucesso.')
    else:
        return httprr(ppc.get_absolute_url('tab=equipe'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def remover_elaborador_projetopedagogicocurso(request, pk):
    elaborador = ElaboradorPPC.objects.get(id=pk)
    if elaborador.ppc.pode_atualizar_comissao_elaboracao(request.user):
        elaborador.remover()
        return httprr(elaborador.ppc.get_absolute_url('tab=equipe'), 'Servidor removido com sucesso.')
    else:
        return httprr(elaborador.ppc.get_absolute_url('tab=equipe'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_elaborador_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Adicionar elaborador'
    if ppc.pode_atualizar_comissao_elaboracao(request.user):
        form = ElaboradorPPCForm(data=request.POST or None)
        if form.is_valid():
            form.cadastrar(pk)
            return httprr('.', 'Elaborador adicionado com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_colaborador_projetopedagogicocurso(request, pk):
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    title = 'Adicionar colaborador'
    if ppc.pode_adicionar_revisor(request.user):
        form = ColaboradorPPCForm(data=request.POST or None, ppc_id=pk)
        if form.is_valid():
            form.save()
            return httprr('.', 'Colaborador adicionado com sucesso.', close_popup=True)
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_colaborador_projetopedagogicocurso(request, pk):
    colaborador = ColaboradorPPC.objects.get(pk=pk)
    title = f'Editar {colaborador.servidor}'
    if colaborador.ppc.pode_adicionar_revisor(request.user):
        form = ColaboradorPPCForm(data=request.POST or None, instance=colaborador)
        if form.is_valid():
            form.save()
            return httprr('.', 'Colaborador atualizado com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def concluir_matrizcurricular_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.ppc.pode_elaborar(request.user):
        matrizppc.concluir_matrizcurricular()
        return httprr(matrizppc.ppc.get_absolute_url(), 'Matriz curricular enviada para revisão.')
    return httprr(matrizppc.get_absolute_url('tab=matriz'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def aprovar_matrizcurricular_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.ppc.pode_revisar(request.user):
        matrizppc.aprovar_matrizcurricular()
        return httprr(matrizppc.ppc.get_absolute_url(), 'Matriz curricular revisada com sucesso.')
    return httprr(matrizppc.get_absolute_url('tab=matriz'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def devolver_matrizcurricular_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Devolver matriz curricular'
    if matrizppc.ppc.pode_revisar(request.user):
        form = DevolverMatrizCurricularForm(data=request.POST or None, instance=matrizppc)
        if form.is_valid():
            form.processar()
            return httprr(matrizppc.ppc.get_absolute_url(), 'Matriz curricular enviada para correção.')
        return locals()
    return httprr(matrizppc.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def retomar_matrizcurricular_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.ppc.pode_elaborar(request.user):
        matrizppc.retomar_matrizcurricular()
        return httprr(matrizppc.ppc.get_absolute_url(), 'Situação atualizada com sucesso.')
    else:
        return httprr(matrizppc.get_absolute_url('tab=matriz'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def desfazer_aprovacao_matrizcurricular_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.pode_desfazer_aprovacao_matriz(request.user):
        matrizppc.desfazer_aprovacao_matrizcurricular()
        return httprr(matrizppc.get_absolute_url(), 'Situação atualizada com sucesso.')
    else:
        return httprr(matrizppc.get_absolute_url('tab=matriz'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def concluir_modalidadepraticaprofissional_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.ppc.pode_elaborar(request.user):
        matrizppc.concluir_modalidadepraticaprofissional()
        return httprr(matrizppc.ppc.get_absolute_url(), 'Modalidade de prática profissional enviada para revisão.')
    return httprr(matrizppc.get_absolute_url('tab=pratica'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def aprovar_modalidadepraticaprofissional_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.ppc.pode_revisar(request.user):
        matrizppc.aprovar_modalidadepraticaprofissional()
        return httprr(matrizppc.ppc.get_absolute_url(), 'Modalidade de prática profissional revisada com sucesso.')
    return httprr(matrizppc.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def devolver_modalidadepraticaprofissional_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Devolver modalidades de prática profissional'
    if matrizppc.ppc.pode_revisar(request.user):
        form = DevolverModalidadePraticaProfissionalForm(data=request.POST or None, instance=matrizppc)
        if form.is_valid():
            form.processar()
            return httprr(matrizppc.ppc.get_absolute_url(), 'Modalidade de prática profissional enviada para correção.')
        return locals()
    return httprr(matrizppc.get_absolute_url(), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def retomar_modalidadepraticaprofissional_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.ppc.pode_elaborar(request.user):
        matrizppc.retomar_modalidadepraticaprofissional()
        return httprr(matrizppc.ppc.get_absolute_url(), 'Situação atualizada com sucesso.')
    else:
        return httprr(matrizppc.get_absolute_url('tab=pratica'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def desfazer_aprovacao_modalidadepraticaprofissional_matrizppc(request, pk):
    matrizppc = MatrizPPC.objects.get(id=pk)
    if matrizppc.pode_desfazer_aprovacao_modalidadepraticaprofissional(request.user):
        matrizppc.desfazer_aprovacao_modalidadepraticaprofissional()
        return httprr(matrizppc.get_absolute_url('tab=pratica'), 'Situação atualizada com sucesso.')
    else:
        return httprr(matrizppc.get_absolute_url('tab=pratica'), 'Você não tem permissão para isso.', 'error')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_elaborador_ppc(request, pk):
    title = 'Editar Elaborador'
    elaborador = ElaboradorPPC.objects.get(pk=pk)
    if elaborador.ppc.is_coordenador_elaboracao(request.user):
        form = ElaboradorPPCForm(data=request.POST or None, instance=elaborador)
        if form.is_valid():
            form.save()
            return httprr('.', 'Elaborador atualizado com sucesso.', close_popup=True)
        return locals()
    else:
        return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_revisor_ppc(request, pk):
    title = 'Adicionar Revisor'
    projeto = ProjetoPedagogicoCurso.objects.get(id=pk)
    if projeto.pode_adicionar_revisor(request.user):
        form = RevisorPPCForm(data=request.POST or None)
        if form.is_valid():
            revisor = form.cadastrar(pk)
            return httprr(revisor.ppc.get_absolute_url(), 'Revisor adicionado com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_revisor_ppc(request, pk):
    revisor = RevisorPPC.objects.get(pk=pk)
    title = f'Editar {revisor.servidor}'
    if revisor.ppc.pode_adicionar_revisor(request.user):
        form = RevisorPPCForm(data=request.POST or None, instance=revisor)
        if form.is_valid():
            form.save()
            return httprr(revisor.ppc.get_absolute_url(), 'Revisor atualizado com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_comentario_conteudo_ppc(request, pk):
    title = 'Adicionar Comentário'
    comentario = ComentarioConteudoPPC.objects.filter(conteudo_ppc_id=pk, revisor=request.user.get_relacionamento()).first()
    form = ComentarioConteudoPPCForm(data=request.POST or None, instance=comentario)
    if form.is_valid():
        if comentario:
            form.save()
        else:
            comentario = form.cadastrar(pk, request.user)
        return httprr(comentario.conteudo_ppc.ppc.get_absolute_url(), 'Comentário adicionado com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_planodisciplina')
@rtr()
def editar_secaoplanodisciplina(request, pk):
    secao = SecaoPlanoDisciplina.objects.get(id=pk)
    title = f'Editar {secao.get_titulo()}'
    form = SecaoPlanoDisciplinaForm(data=request.POST or None, instance=secao)
    if form.is_valid():
        form.processar()
        return httprr('.', 'Plano de disciplina vinculada com sucesso.', close_popup=True)
    return locals()


@permission_required('comum.is_servidor')
@rtr()
def historico_conteudoppc(request, pk):
    title = 'Histórico'
    logs = Log.objects.filter(ref=pk, modelo='ConteudoPPC').order_by('-dt')
    return locals()


@documento(enumerar_paginas=True)
@permission_required('ppc.change_projetopedagogicocurso')
@rtr('pdf_conteudoppc.html')
def pdf_conteudoppc(request, pk):
    obj = get_object_or_404(ConteudoPPC, pk=pk)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def alterar_situacao_ppc(request, pk, situacao):
    projeto = ProjetoPedagogicoCurso.objects.get(id=pk)
    if situacao == ProjetoPedagogicoCurso.EM_ELABORACAO:
        if projeto.pode_enviar_elaboracao(request.user):
            projeto.enviar_para_elaboracao(request.user)
            return httprr(projeto.get_absolute_url(), 'Situação atualizada com sucesso.')

    return locals()


@permission_required('ppc.change_conteudoppc')
@rtr()
def alterar_situacao_conteudoppc(request, pk, situacao):
    conteudo = ConteudoPPC.objects.get(id=pk)
    if situacao == ConteudoPPC.AGUARDANDO_REVISAO:
        if conteudo.pode_editar(request.user):
            conteudo.enviar_para_revisao(request.user)
            return httprr(conteudo.ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    elif situacao == ConteudoPPC.EM_REVISAO:
        if conteudo.pode_desfazer_homologacao(request.user):
            conteudo.desfazer_homologacao(request.user)
            return httprr(conteudo.ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    elif situacao == ConteudoPPC.ENVIADO_CORRECAO:
        if conteudo.pode_revisar(request.user):
            form = RevisarConteudoPPCForm(data=request.POST or None, instance=conteudo)
            if form.is_valid():
                form.processar(request.user)
                return httprr(conteudo.ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.', close_popup=True)
            return locals()
    elif situacao == ConteudoPPC.HOMOLOGADO:
        if conteudo.pode_revisar(request.user):
            conteudo.homologar(request.user)
            return httprr(conteudo.ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    return locals()


@permission_required('ppc.change_conteudoppc')
@rtr()
def retomar_edicao(request, pk):
    conteudo = ConteudoPPC.objects.get(id=pk)
    if conteudo.pode_retomar_edicao(request.user):
        conteudo.retomar_edicao(request.user)
        return httprr(conteudo.ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    return locals()


@permission_required('ppc.change_conteudoppc')
@rtr()
def assumir_revisao(request, pk, tipo, secao_id=None):
    if tipo in ['ppc', 'secao']:
        ppc = get_object_or_404(ProjetoPedagogicoCurso, pk=pk)
    if tipo == 'ppc':
        for conteudo in ConteudoPPC.objects.filter(ppc_id=pk, conteudo_modelo__editavel=True):
            if conteudo.pode_assumir_revisao(request.user):
                conteudo.assumir_revisao(request.user)
        return httprr(ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    elif tipo == 'secao':
        for conteudo in ConteudoPPC.objects.filter(conteudo_modelo__secao_id=secao_id, ppc_id=pk, conteudo_modelo__editavel=True):
            if conteudo.pode_assumir_revisao(request.user):
                conteudo.assumir_revisao(request.user)
        return httprr(ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    elif tipo == 'conteudo':
        conteudo = ConteudoPPC.objects.get(id=pk)
        if conteudo.pode_assumir_revisao(request.user):
            conteudo.assumir_revisao(request.user)
            return httprr(conteudo.ppc.get_absolute_url('tab=conteudo'), 'Situação atualizada com sucesso.')
    return locals()


@permission_required('ppc.view_planodisciplina')
@rtr()
def planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano.situacao != PlanoDisciplina.REJEITADO:
        situacoes = copy.copy(PlanoDisciplina.SITUACAO_CHOICES)
        situacoes.pop(int(PlanoDisciplina.REJEITADO) - 1)

    title = plano
    ppc = plano.ppc_criacao
    pode_editar = plano.can_change(request.user)
    pode_enviar_analise = plano.pode_enviar_analise(request.user)
    pode_analisar = plano.pode_analisar(request.user)
    pode_aprovar = plano.pode_aprovar(request.user)
    pode_desaprovar = plano.pode_desaprovar(request.user)
    pode_devolver = plano.pode_devolver(request.user)
    pode_cadastrar_revisao = plano.pode_cadastrar_revisao(request.user)
    pode_excluir = plano.can_delete(request.user)
    pode_inativar = plano.pode_inativar(request.user)
    pode_reativar = plano.pode_reativar(request.user)
    pode_replicar = plano.pode_replicar(request.user)
    pode_duplicar = plano.pode_duplicar(request.user)
    pode_criar_versao_ead = plano.pode_criar_versao_ead(request.user)
    pode_excluir_versao_ead = plano.pode_excluir_versao_ead(request.user)
    possui_revisao_pendente = plano.possui_revisao_pendente()
    is_avaliador_and_analise = plano.estah_em_analise() and plano.is_avaliador(request.user)
    is_elaborador_and_elaboracao = plano.is_elaboracao() and plano.is_elaborador(request.user)
    user_apto_remover_comentario = is_elaborador_and_elaboracao or is_avaliador_and_analise
    pode_remover_ppc_vinculado = plano.pode_remover_ppc_vinculado(request.user)
    tem_secao_pendente = plano.get_secoes().filter(texto='').exists()
    tem_secao_ead_pendente = plano.get_secoes_ead().filter(texto='').exists()
    tem_secao_ead = plano.get_secoes_ead().exists()
    planos_mesmo_nome = PlanoDisciplina.objects.filter(
        nome_disciplina=plano.nome_disciplina, tipo_oferta=plano.tipo_oferta, nucleo=plano.nucleo, ativo=True
    ).exclude(id=plano.id)
    situacao_inconsistente = (
        plano.planodisciplinappc_set.filter(matriz_ppc__situacao_matriz=MatrizPPC.MATRIZ_APROVADA).exists() and not plano.is_aprovado()
    )

    if request.GET.get('tab') == 'revisoes':
        revisoes = plano.revisaoplanodisciplina_set.all().order_by('-data_criacao')
    if request.GET.get('tab') == 'ppc':
        ppcs = PlanoDisciplinaPPC.objects.select_related('matriz_ppc__ppc').filter(plano_disciplina__id=pk)
    if request.GET.get('tab') == 'movimentacoes':
        movimentacoes = plano.movimentacaoplanodisciplina_set.all()

    return locals()


@rtr()
@login_required
def adicionar_comentario_revisaoplanodisciplina(request, pk_revisao):
    revisao = get_object_or_404(RevisaoPlanoDisciplina, pk=pk_revisao)
    form = ComentarioRevisaoPlanoDisciplinaForm(data=request.POST or None, request=request)
    if form.is_valid():
        form.processar(revisao, request.user.get_vinculo())
        messages.success(request, 'Comentário adicionado com sucesso.')
        return httprr('..')

    return locals()


@rtr()
@login_required
def desconsiderar_comentario_planodisciplina(request, pk_revisao, pk):
    revisao = get_object_or_404(RevisaoPlanoDisciplina, pk=pk_revisao)
    comentario = get_object_or_404(ComentarioRevisaoPlanoDisciplina, pk=pk)
    vinculo = request.user.get_vinculo()
    if not comentario.pode_desconsiderar_comentario(vinculo):
        return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Você não tem permissão.', 'erro')
    comentario.desconsiderar_comentario()
    return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Comentário desconsiderado com sucesso.')


@rtr()
@login_required
def excluir_comentario_planodisciplina(request, pk_revisao, pk):
    revisao = get_object_or_404(RevisaoPlanoDisciplina, pk=pk_revisao)
    comentario = get_object_or_404(ComentarioRevisaoPlanoDisciplina, pk=pk)
    vinculo = request.user.get_vinculo()
    if not comentario.pode_remover_comentario(vinculo.user):
        return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Você não tem permissão.', 'erro')
    comentario.remover_comentario(request.user)
    return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Comentário removido com sucesso.')


@rtr()
@login_required
def atualizar_revisaoplanodisciplina_resolvida(request, pk_revisao):
    revisao = get_object_or_404(RevisaoPlanoDisciplina, pk=pk_revisao)
    vinculo = request.user.get_vinculo()
    if not revisao.pode_marcar_resolvido(request.user):
        return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Você não tem permissão.', 'erro')
    try:
        revisao.atualizar_resolvida(vinculo)
        return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Revisão resolvida com sucesso.')
    except ValidationError as e:
        return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', e.message, 'error')


@rtr()
@login_required
def retornar_revisaoplanodisciplina_para_analise(request, pk_revisao):
    revisao = get_object_or_404(RevisaoPlanoDisciplina, pk=pk_revisao)
    vinculo = request.user.get_vinculo()
    if not revisao.pode_marcar_resolvido(request.user):
        return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Você não tem permissão.', 'erro')
    revisao.retornar_para_nao_resovida(vinculo)
    return httprr(f'{revisao.plano_disciplina.get_absolute_url()}?tab=revisoes', 'Revisão retornou para não resolvida.')


@documento()
@permission_required('ppc.view_planodisciplina')
@rtr()
def imprimir_planodisciplina(request, pk):
    plano = get_object_or_404(PlanoDisciplina, pk=pk)
    versao_ead = 'ead' in request.GET
    secoes = plano.get_secoes_impressao(versao_ead)
    return locals()


@documento()
@permission_required('ppc.view_planodisciplinappc')
@rtr()
def imprimir_planodisciplinappc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPPC, pk=pk)
    versao_ead = 'ead' in request.GET
    secoes = plano.plano_disciplina.get_secoes_impressao(versao_ead)
    return locals()


@documento('Plano de disciplina', validade=30, modelo='ppc.planodisciplinappc', exibe_emissor=True)
@login_required
@rtr('imprimir_planodisciplinappc.html')
def pdf_autenticado_planodisciplinappc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPPC, pk=pk)
    secoes = plano.get_secoes_plano_disciplina_impressao()
    return locals()


@login_required
@rtr()
def visualizar_planodisciplinappc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPPC, pk=pk)
    title = 'Plano de disciplina de curso'
    secoes = plano.get_secoes_plano_disciplina_impressao()
    return locals()


@permission_required('ppc.change_planodisciplina')
@rtr()
def enviar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_enviar_analise(request.user):
        plano_disciplina.enviar_analise(request.user)
        return httprr(plano_disciplina.get_absolute_url(), 'Plano de disciplina enviado para análise com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para alterar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def analisar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_analisar(request.user):
        plano_disciplina.analisar(request.user)
        return httprr(plano_disciplina.get_absolute_url(), 'Plano de disciplina alterado para em análise com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para alterar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def aprovar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_aprovar(request.user):
        plano_disciplina.aprovar(request.user)
        return httprr(plano_disciplina.get_absolute_url(), 'Plano de disciplina aprovado com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para aprovar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def desaprovar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_desaprovar(request.user):
        plano_disciplina.desaprovar(request.user)
        return httprr(plano_disciplina.get_absolute_url(), 'Aprovação do plano de disciplina desfeita com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para desfazer a aprovação deste plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def inativar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_inativar(request.user):
        plano_disciplina.inativar()
        return httprr(plano_disciplina.get_absolute_url(), 'Plano de disciplina inativado com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para inativar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def reativar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_reativar(request.user):
        plano_disciplina.reativar()
        return httprr(plano_disciplina.get_absolute_url(), 'Plano de disciplina reativado com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para reativar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def replicar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_replicar(request.user):
        novo = plano_disciplina.replicar()
        return httprr(novo.get_absolute_url(), 'Plano de disciplina replicado com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para replicar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def criar_versao_ead_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_criar_versao_ead(request.user):
        plano_disciplina.criar_versao_ead()
        return httprr(plano_disciplina.get_absolute_url(), 'Seções EAD criadas com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para criar seções EAD neste plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def excluir_versao_ead_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_excluir_versao_ead(request.user):
        plano_disciplina.excluir_versao_ead()
        return httprr(plano_disciplina.get_absolute_url(), 'Seções EAD removidas com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para excluir seções EAD neste plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def devolver_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_devolver(request.user):
        plano_disciplina.enviar_elaboracao(request.user)
        return httprr(plano_disciplina.get_absolute_url(), 'Plano de disciplina devolvido com sucesso.')
    return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para alterar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def editar_ementa_planodisciplina(request, pk):
    pd = get_object_or_404(PlanoDisciplina, pk=pk)
    title = 'Editar ementa'
    form = EmentaPlanoDisciplinaForm(data=request.POST or None, instance=pd)
    if form.is_valid():
        form.processar()
        return httprr('.', 'Ementa atualizada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_planodisciplina')
@rtr()
def reprovar_planodisciplina(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if plano_disciplina.pode_cadastrar_revisao(request.user):
        plano_disciplina.rejeitar(request.user)
        return httprr('.', 'Plano de disciplina reprovado com sucesso.', close_popup=True)
    return httprr('.', 'Você não tem permissão para alterar este plano de disciplina.', 'error')


@permission_required('ppc.change_planodisciplina')
@rtr()
def requisitos_planodisciplinappc(request, pk):
    plano_disciplina = get_object_or_404(PlanoDisciplinaPPC, pk=pk)
    form = RequisitosPlanoDisciplinaPPCForm(data=request.POST or None, instance=plano_disciplina)
    if form.is_valid():
        form.save()
        return httprr('.', 'Requisitos configurados com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_planodisciplina')
@rtr()
def desvincular_requisito_planodisciplina(request, pk, tipo, requisito_id):
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    requisito = PlanoDisciplina.objects.get(id=requisito_id)
    if tipo == 'pre':
        plano_disciplina.pre_requisitos.remove(requisito)
    elif tipo == 'co':
        plano_disciplina.co_requisitos.remove(requisito)
    else:
        return httprr(plano_disciplina.get_absolute_url(), 'Operação inválida.', 'error')
    return httprr(f'{plano_disciplina.get_absolute_url()}?tab=requisitos', 'Requisito removido com sucesso.')


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_planodisciplina(request, pk, nucleo_id):
    matriz_ppc = MatrizPPC.objects.get(id=pk)
    title = 'Adicionar plano de disciplina'
    form = PlanoDisciplinaForm(data=request.POST or None, nucleo_id=nucleo_id, request=request, diretriz_id=matriz_ppc.ppc.diretriz_id)
    if form.is_valid():
        try:
            plano = form.processar(matriz_ppc, request.user)
            return httprr(
                f'/admin/ppc/planodisciplinappc/{plano.pk}/change/?show_message',
                'Plano de disciplina vinculado à matriz do PPC. Complete o cadastro.',
            )
        except ValidationError as e:
            return httprr(f'/ppc/planodisciplina/{pk}/adicionar/{nucleo_id}/', e.message, 'error')
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def listar_planodisciplina(request, tipo_oferta_id, nucleo_id, matriz_ppc_id):
    title = 'Planos de disiciplina'

    planos = (
        PlanoDisciplina.objects.filter(tipo_oferta_id=tipo_oferta_id, nucleo_id=nucleo_id, ativo=True)
        .exclude(situacao=PlanoDisciplina.REJEITADO)
        .exclude(planodisciplinappc__matriz_ppc_id=matriz_ppc_id)
        .order_by('nome_disciplina')
    )

    matrizppc = MatrizPPC.objects.filter(id=matriz_ppc_id).first()
    if matrizppc.ppc.is_curso_semestral():
        planos = planos.exclude(periodicidade=PlanoDisciplina.PERIODICIDADE_ANUAL)

    if planos.exists():
        p = planos[0]
        title = f'{title} {p.tipo_oferta} - {p.nucleo}'

    pode_vincular_plano = matrizppc.ppc.pode_elaborar(request.user) and matrizppc.situacao_matriz == MatrizPPC.MATRIZ_EM_ELABORACAO
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_planodisciplinappc(request, pk, nucleo_id, plano_disciplina_id=None):
    matrizppc = MatrizPPC.objects.get(id=pk)
    title = 'Vincular plano de disciplina à matriz do PPC'
    form = PlanoDisciplinaPPCForm(data=request.POST or None, nucleo_id=nucleo_id, matrizppc=matrizppc, plano_disciplina_id=plano_disciplina_id)
    if form.is_valid():
        form.save()
        return httprr(matrizppc.get_absolute_url('tab=matriz'), 'Plano de disciplina criado com sucesso.')
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def planodisciplinappc(request, pk):
    plano = get_object_or_404(PlanoDisciplinaPPC, pk=pk)
    title = plano
    pode_editar = plano.can_change(request.user)
    pode_editar_dados_basicos = plano.plano_disciplina.can_change(request.user)
    secoes = plano.get_secoes_plano_disciplina_impressao()
    plano_associado = plano.plano_disciplinappc_associado
    plano_principal = plano.get_plano_disciplinappc_principal()
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def adicionar_modalidadepraticaprofissionaldiretriz(request, pk):
    title = 'Adicionar modalidade de prática profissional obrigatória'
    form = ModalidadePraticaProfissionalDiretrizForm(data=request.POST or None, nucleo_diretriz_id=pk)
    if form.is_valid():
        form.save()
        return httprr('.', 'Modalidade de prática profissional adicionada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_diretriz')
@rtr()
def editar_modalidadepraticaprofissionaldiretriz(request, pk):
    title = 'Editar modalidade de prática profissional obrigatória'
    modalidade = ModalidadePraticaProfissionalDiretriz.objects.get(pk=pk)
    form = ModalidadePraticaProfissionalDiretrizForm(data=request.POST or None, instance=modalidade)
    if form.is_valid():
        form.save()
        return httprr('.', 'Modalidade de prática profissional atualizada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_modalidadepraticaprofissionalppc(request, pk, nucleo_id):
    title = 'Adicionar modalidade de prática profissional'
    form = ModalidadePraticaProfissionalPPCForm(data=request.POST or None, nucleo_id=nucleo_id, matriz_ppc_id=pk)
    if form.is_valid():
        form.save()
        return httprr('.', 'Modalidade de prática profissional criada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_modalidadepraticaprofissionalppc(request, pk):
    title = 'Editar modalidade de prática profissional'
    modalidade = get_object_or_404(ModalidadePraticaProfissionalPPC, pk=pk)
    form = ModalidadePraticaProfissionalPPCForm(data=request.POST or None, instance=modalidade)
    if form.is_valid():
        form.save()
        return httprr('.', 'Modalidade de prática profissional atualizada com sucesso.', close_popup=True)
    return locals()


@permission_required('ppc.view_comissaoptdem')
@rtr()
def comissaoptdem(request, pk):
    comissao = ComissaoPTDEM.objects.get(id=pk)
    title = comissao.nome
    return locals()


@permission_required('ppc.view_administradortipooferta')
@rtr()
def administradortipooferta(request, pk):
    obj = AdministradorTipoOferta.objects.get(id=pk)
    title = obj
    return locals()


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def adicionar_certificacaointermediaria(request, pk):
    title = 'Adicionar certificação intermediária'
    ppc = ProjetoPedagogicoCurso.objects.get(id=pk)
    if ppc.pode_elaborar(request.user):
        form = CertificacaoParcialForm(data=request.POST or None)
        if form.is_valid():
            form.processar(pk)
            return httprr('.', 'Certificação intermediária adicionada com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def editar_certificacaointermediaria(request, pk):
    cp = CertificacaoParcial.objects.filter(id=pk).first()
    if cp is None:
        return httprr('.', 'Certificação intermediária não encontrada.', 'error', close_popup=True)
    title = f'Editar {cp.descricao}'
    if cp.ppc.pode_elaborar(request.user):
        form = CertificacaoParcialForm(data=request.POST or None, instance=cp)
        if form.is_valid():
            form.save()
            return httprr('.', 'Certificação intermediária adicionada com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_projetopedagogicocurso')
@rtr()
def vincular_planodisciplina_certificacaointermediaria(request, pk):
    cp = CertificacaoParcial.objects.filter(id=pk).first()
    if cp is None:
        return httprr('.', 'Certificação intermediária não encontrada.', 'error', close_popup=True)
    title = 'Adicionar plano de disciplina'
    if cp.ppc.pode_elaborar(request.user):
        form = PlanoDisciplinaCertificacaoParcialForm(data=request.POST or None, certificacao_parcial=cp)
        if form.is_valid():
            form.save()
            return httprr('.', 'Plano de disciplina adicionado com sucesso.', close_popup=True)
        return locals()
    return httprr('.', 'Você não tem permissão para isso.', 'error', close_popup=True)


@permission_required('ppc.change_planodisciplina')
@rtr()
def duplicar_plano_disciplina(request, pk):
    title = 'Duplicar Plano de Disciplina'
    plano_disciplina = get_object_or_404(PlanoDisciplina, pk=pk)
    if not plano_disciplina.pode_duplicar(request.user):
        return httprr(plano_disciplina.get_absolute_url(), 'Você não tem permissão para duplicar este plano de disciplina.', 'error')
    form = DuplicarPlanoDisciplinaForm(data=request.POST or None, plano_disciplina=plano_disciplina)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Duplicação realizada com sucesso', close_popup=True)
    return locals()
