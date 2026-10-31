import datetime
import os
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q, QuerySet, Sum
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.template.loader import render_to_string

from comum.forms import AdicionarUsuarioGrupoForm
from comum.models import Arquivo, Configuracao, TrocarSenha, User, UsuarioGrupo, Vinculo
from comum.utils import get_sigla_reitoria, get_uo
from djtools import layout, relatorios
from djtools.html.graficos import GroupedColumnChart, PieChart
from djtools.templatetags.filters import format_
from djtools.utils import PDFResponse, documento, httprr, permission_required, rtr, send_notification, to_ascii
from edu.models import Aluno, Modalidade
from projetos_ensino import tasks
from projetos_ensino.forms import (
    AceiteTermoForm,
    AlteraNotaCriterioProjetoForm,
    AlterarCoordenadorForm,
    AnexosDiversosProjetoForm,
    AnoForm,
    AvaliacaoFormFactory,
    AvaliarCancelamentoProjetoForm,
    AvaliarRecursoProjetoForm,
    BuscaProjetoForm,
    CancelarProjetoForm,
    CaracterizacaoBeneficiarioForm,
    ClonarEtapaForm,
    ClonarProjetoForm,
    CriterioAvaliacaoAlunoForm,
    CriterioAvaliacaoForm,
    DadosBancariosParticipanteForm,
    DataInativacaoForm,
    DesembolsoForm,
    EditaisForm,
    EditalAnexoAuxiliarForm,
    EditalAnexoForm,
    EditarFrequenciaForm,
    EditarProjetoEmExecucaoForm,
    EditarTermoCessaoForm,
    EmailCoordenadoresForm,
    EquipeEtapaForm,
    EquipeProjetoForm,
    EstatisticasForm,
    EtapaForm,
    FiltrarListaFrequenciaForm,
    FotoProjetoForm,
    GerarListaFrequenciaForm,
    InativarProjetoForm,
    IndicarAvaliadoresForm,
    IndicarAvaliadorForm,
    IndicarOrientadorForm,
    IndicarPreAvaliadorForm,
    ItemMemoriaCalculoForm,
    LicaoAprendidaForm,
    ListaAvaliadoresProjetosForm,
    ListaEditaisForm,
    MetaForm,
    MeusProjetosForm,
    OfertaProjetoForm,
    ParticipacaoAlunoForm,
    ParticipacaoColaboradorForm,
    ParticipacaoServidorForm,
    PreAvaliacaoForm,
    PrestacaoContaForm,
    ProjetoForm,
    ProjetoHistoricoDeEnvioForm,
    ProjetosAtrasadosForm,
    RecursoForm,
    RecursoProjetoForm,
    RegistrarFrequenciaForm,
    RegistroConclusaoProjetoForm,
    RegistroExecucaoEtapaForm,
    RegistroGastoForm,
    RelatorioCaracterizacaoBeneficiariosForm,
    RelatorioLicoesAprendidasForm,
    ReprovarExecucaoEtapaForm,
    ReprovarExecucaoGastoForm,
    SelecionarPreAvaliadorForm,
    SolicitoesCancelamentoForm,
    TermoCessaoForm,
    UploadArquivoForm,
    UploadEditalForm,
    ValidacaoConclusaoProjetoForm,
    ValidarAvaliacaoAlunoForm,
)
from projetos_ensino.models import (
    Avaliacao,
    AvaliacaoAluno,
    AvaliadorIndicado,
    CampusAdicional,
    CaracterizacaoBeneficiario,
    ComissaoEdital,
    CriterioAvaliacao,
    CriterioAvaliacaoAluno,
    Desembolso,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    EixoTematico,
    Etapa,
    FotoProjeto,
    HistoricoAlteracaoPeriodoProjeto,
    HistoricoEquipe,
    HistoricoOrientacaoProjeto,
    ItemAvaliacao,
    ItemAvaliacaoAluno,
    ItemMemoriaCalculo,
    LicaoAprendida,
    Meta,
    OfertaProjeto,
    Participacao,
    Projeto,
    ProjetoAnexo,
    ProjetoCancelado,
    ProjetoHistoricoDeEnvio,
    Recurso,
    RecursoProjeto,
    RegistroConclusaoProjeto,
    RegistroExecucaoEtapa,
    RegistroFrequencia,
    RegistroGasto,
    TipoVinculo,
)
from rh.models import Servidor, UnidadeOrganizacional
from rh.views import rh_servidor_view_tab


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.groups.filter(name='Coordenador de Projetos de Ensino').exists():
        # uo = get_uo(request.user)
        uos_user = CampusAdicional.get_campi_user(request.user)
        editais = Edital.objects.em_pre_avaliacao()
        if editais.exists():
            for edital in editais:
                # qtd_projetos = Projeto.objects.filter(
                #    edital=edital, data_pre_avaliacao=None, pre_aprovado=False, data_conclusao_planejamento__isnull=False, uo=uo
                # ).count()
                qtd_projetos = Projeto.objects.filter(
                    edital=edital, data_pre_avaliacao=None, pre_aprovado=False, data_conclusao_planejamento__isnull=False, uo__in=uos_user
                ).count()
                if qtd_projetos:
                    pendencias.append(
                        {
                            'url': f'/projetos_ensino/projetos_nao_avaliados/{edital.id}/?campus=&area_conhecimento=&area_tematica=&pendentes=on&preavaliacao_form=Aguarde...',
                            'titulo': f'O edital {edital.titulo} possui projeto{pluralize(qtd_projetos)} pendente{pluralize(qtd_projetos)} de pré-avaliação.',
                        }
                    )

    return pendencias


@layout.info()
def index_infos(request):
    """Sinaliza ao aluno avaliação de Projetos de Ensino pendente de considerações.

    Busca a primeira avaliação aprovada e não cancelada cujo registro de
    considerações do aluno ainda não foi feito, devolvendo link direto.

    Args:
        request: requisição HTTP usada para identificar o vínculo do aluno.

    Returns:
        list[dict]: aviso com ``url`` e ``titulo`` quando há pendência; lista vazia caso contrário.
    """
    infos = []

    if request.user.eh_aluno:
        vinculo = request.user.get_vinculo()
        pendente_consideracao = (
            AvaliacaoAluno.objects.filter(
                participacao__vinculo_pessoa=vinculo,
                data_validacao__isnull=True,
                participacao__projeto__pre_aprovado=True,
                participacao__projeto__aprovado=True,
                participacao__projeto__registroconclusaoprojeto__dt_avaliacao__isnull=True,
            )
            .exclude(participacao__projeto__projetocancelado__cancelado=True)
            .select_related('participacao__projeto')
            .first()
        )
        if pendente_consideracao:
            infos.append(
                {
                    'url': f'/projetos_ensino/registrar_consideracoes_aluno/{pendente_consideracao.id}/',
                    'titulo': f'Faça suas considerações na avaliação do projeto {pendente_consideracao.participacao.projeto.titulo}.',
                }
            )

    return infos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Lista pendências de Projetos de Ensino atribuídas ao usuário logado.

    Para servidores/aposentados, consolida em uma única consulta as ações
    relacionadas a projetos sob sua coordenação ou avaliação (cadastro,
    plano de trabalho, relatórios, frequências) usando ``select_related``.

    Args:
        request: requisição HTTP usada para obter o vínculo e os grupos do usuário.

    Returns:
        list[dict]: cartões de pendência específicos de Projetos de Ensino;
        lista vazia quando não há ações pendentes.
    """
    pendencias = []

    vinculo = request.user.get_vinculo()

    if request.user.groups.filter(name__in=['Servidor', 'Aposentado']).exists():
        hoje = datetime.datetime.now()
        qtd_coordena_projetos = Projeto.objects.filter(
            vinculo_coordenador=vinculo,
            data_conclusao_planejamento__isnull=True,
            edital__inicio_inscricoes__lte=hoje,
            edital__fim_inscricoes__gte=hoje,
        ).count()
        if qtd_coordena_projetos:
            pendencias.append(
                {
                    'url': '/projetos_ensino/meus_projetos/',
                    'titulo': 'Há <strong>projeto{plural}</strong> sob sua coordenação pendente{plural} de envio.'.format(
                        plural=pluralize(qtd_coordena_projetos)
                    ),
                }
            )

    # Era 1 query `.exists()` + 1 query no loop + 1 query por `registro.projeto` (FK lazy).
    # select_related elimina o N+1 do FK; break interrompe assim que o primeiro alerta é emitido.
    historicos_devolvidos = ProjetoHistoricoDeEnvio.objects.filter(
        projeto__vinculo_coordenador=vinculo, situacao=ProjetoHistoricoDeEnvio.DEVOLVIDO
    ).select_related('projeto')
    for registro in historicos_devolvidos.iterator():
        projeto = registro.projeto
        if projeto.get_status() == projeto.STATUS_EM_INSCRICAO:
            pendencias.append({'url': f'/projetos_ensino/projeto/{projeto.id}/', 'titulo': f'O projeto {projeto.titulo} foi devolvido.'})
            break

    # `.select_related('projeto').first()` substitui `.exists() + [0].projeto` (era 2 queries por bloco + acesso lazy → 1).
    if request.user.eh_aluno:
        pendencia_aceite_termo = (
            Participacao.objects.filter(
                ativo=True, projeto__edital__termo_compromisso_aluno__isnull=False, vinculo_pessoa=vinculo, termo_aceito_em__isnull=True
            )
            .exclude(projeto__edital__termo_compromisso_aluno='')
            .select_related('projeto')
            .first()
        )
        if pendencia_aceite_termo:
            pendencias.append(
                {
                    'url': f'/projetos_ensino/projeto/{pendencia_aceite_termo.projeto.id}/?tab=equipe',
                    'titulo': f'Você <strong>precisa aceitar o termo de compromisso</strong> do projeto <strong>{pendencia_aceite_termo.projeto.titulo}</strong>.',
                }
            )

    if request.user.eh_prestador:
        pendencia_aceite_termo = (
            Participacao.objects.filter(
                ativo=True,
                projeto__edital__termo_compromisso_colaborador_voluntario__isnull=False,
                vinculo_pessoa=vinculo,
                termo_aceito_em__isnull=True,
            )
            .exclude(projeto__edital__termo_compromisso_colaborador_voluntario='')
            .select_related('projeto')
            .first()
        )
        if pendencia_aceite_termo:
            pendencias.append(
                {
                    'url': f'/projetos_ensino/projeto/{pendencia_aceite_termo.projeto.id}/?tab=equipe',
                    'titulo': f'Você <strong>precisa aceitar o termo de compromisso</strong> do projeto <strong>{pendencia_aceite_termo.projeto.titulo}</strong>.',
                }
            )
    if request.user.eh_servidor:
        pendencia_aceite_termo = (
            Participacao.objects.filter(
                ativo=True,
                responsavel=False,
                projeto__edital__termo_compromisso_servidor__isnull=False,
                vinculo_pessoa=vinculo,
                termo_aceito_em__isnull=True,
            )
            .exclude(projeto__edital__termo_compromisso_servidor='')
            .select_related('projeto')
            .first()
        )
        if pendencia_aceite_termo:
            pendencias.append(
                {
                    'url': f'/projetos_ensino/projeto/{pendencia_aceite_termo.projeto.id}/?tab=equipe',
                    'titulo': f'Você <strong>precisa aceitar o termo de compromisso</strong> do projeto <strong>{pendencia_aceite_termo.projeto.titulo}</strong>.',
                }
            )

    if request.user.eh_servidor or request.user.eh_prestador:
        edital_para_avaliar = Edital.objects.em_selecao()
        if edital_para_avaliar.exists():
            ids_editais = edital_para_avaliar.values_list('id', flat=True)
            indicacoes = AvaliadorIndicado.objects.filter(vinculo=vinculo, projeto__edital_id__in=ids_editais).count()
            avaliacoes = Avaliacao.objects.filter(vinculo=vinculo, projeto__edital_id__in=ids_editais).count()
            if indicacoes > avaliacoes:
                qtd = indicacoes - avaliacoes
                pendencias.append(
                    {
                        'titulo': f'Projeto{pluralize(qtd)} de Ensino',
                        'subtitulo': 'aguardando avaliação',
                        'qtd': qtd,
                        'url': '/projetos_ensino/avaliacao/',
                    }
                )

    return pendencias


@layout.quadro('Projetos de Ensino', icone='suitcase', pode_esconder=True)
def index_quadros(quadro, request):
    vinculo = request.user.get_vinculo()

    if request.user.has_perm('projetos_ensino.pode_interagir_com_projeto'):
        hoje = datetime.datetime.now()
        editais_abertos = Edital.objects.filter(inicio_inscricoes__lte=hoje, fim_inscricoes__gte=hoje)
        editais_abertos_sem_continuo = editais_abertos.exclude(tipo_edital=Edital.ENSINO_CONTINUO)
        if editais_abertos_sem_continuo.exists():
            quadro.add_item(
                layout.ItemTitulo(
                    titulo='Inscrições abertas',
                )
            )
            for edital in editais_abertos_sem_continuo:
                quadro.add_item(
                    layout.ItemNoticia(
                        titulo=edital.titulo,
                        url='/projetos_ensino/editais_abertos/',
                        chapeu=f'Até {edital.fim_inscricoes.strftime("%d/%m/%Y %H:%M")}',
                    )
                )

    if vinculo.eh_aluno():
        participacoes = Participacao.objects.filter(vinculo_pessoa=vinculo, projeto__aprovado=True)

        projetos_do_aluno = Projeto.objects.filter(id__in=participacoes.values_list('projeto', flat=True))
        if projetos_do_aluno.exists():
            for projeto in projetos_do_aluno:
                quadro.add_item(
                    layout.ItemGrupo(
                        titulo=projeto.titulo,
                        grupo='Meus projetos',
                        url=f'/projetos_ensino/projeto/{projeto.pk}/',
                    )
                )

    elif request.user.has_perm('projetos_ensino.pode_gerenciar_edital', ignore_superuser=True):
        pids = UsuarioGrupo.objects.filter(group__name='Coordenador de Projetos de Ensino').values_list('user__id', flat=True)
        editais = Edital.objects.em_periodo_indicar_pre_avaliador()
        participacoes_preavaliador = Participacao.objects.filter(
            vinculo_pessoa__user__in=pids,
            projeto__data_pre_avaliacao__isnull=True,
            projeto__edital__in=editais,
            projeto__vinculo_autor_pre_avaliacao__id=F('vinculo_pessoa__id'),
            projeto__aprovado=True,
        )
        if participacoes_preavaliador.exists():
            qtd = participacoes_preavaliador.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo='Projeto{plural} Pendente{plural}'.format(plural=pluralize(qtd)),
                    subtitulo='De mudança de pré-avaliador',
                    qtd=qtd,
                    url=f'/projetos_ensino/selecionar_pre_avaliador/{participacoes_preavaliador[0].projeto.edital.id}/',
                )
            )

        participacoes_monitor = Participacao.objects.filter(
            projeto__vinculo_monitor__id=F('vinculo_pessoa__id'), projeto__aprovado=True, projeto__registroconclusaoprojeto__dt_avaliacao__isnull=True
        )

        if participacoes_monitor.exists():
            qtd = participacoes_monitor.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo='Projeto{plural} Pendente{plural}'.format(plural=pluralize(qtd)),
                    subtitulo='De mudança de monitor',
                    qtd=qtd,
                    url=f'/projetos_ensino/selecionar_monitor/{participacoes_monitor[0].projeto.edital.id}/',
                )
            )
    return quadro


def tem_permissao_acesso_edital(request, edital):
    if (
        request.user.has_perm('projetos_ensino.pode_gerenciar_edital')
        or request.user.has_perm('projetos_ensino.view_edital')
        and (
            (edital.cadastrado_por and edital.cadastrado_por.setor.uo == get_uo(request.user))
            or (OfertaProjeto.objects.filter(edital=edital, uo=get_uo(request.user)).exists())
        )
    ):
        return True
    raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.view_edital')
def edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if edital.tipo_edital == edital.ENSINO_CONTINUO:
        title = f'{edital.titulo} - Edital de Ensino - Fluxo Contínuo'
    else:
        title = f'{edital.titulo} - Edital de Ensino'

    FormClass = edital.get_form()
    form = FormClass(request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('.', 'Critérios adicionados com sucesso.')
    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def meus_projetos(request):
    title = 'Meus projetos'
    vinculo = request.user.get_vinculo()
    participacoes = Participacao.objects.filter(vinculo_pessoa=vinculo).order_by(
        '-projeto__edital__inicio_inscricoes', 'projeto__vinculo_coordenador'
    )
    ano = request.GET.get('ano')
    form = MeusProjetosForm(request.GET or None, ano=ano)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        situacao = form.cleaned_data.get('situacao')
        ano = form.cleaned_data.get('ano')
        if ano:
            participacoes = participacoes.filter(projeto__edital__inicio_inscricoes__year=ano)
        if edital:
            participacoes = participacoes.filter(projeto__edital=edital)

        if situacao:
            hoje = datetime.datetime.now()
            projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
            if situacao == MeusProjetosForm.PROJETOS_EM_EDICAO:
                participacoes = participacoes.filter(projeto__data_conclusao_planejamento__isnull=True, projeto__edital__fim_inscricoes__gte=hoje)
            elif situacao == MeusProjetosForm.PROJETOS_ENVIADOS:
                participacoes = participacoes.filter(
                    Q(projeto__data_conclusao_planejamento__isnull=False)
                    | Q(projeto__data_conclusao_planejamento__isnull=True, projeto__data_pre_avaliacao__isnull=False)
                )
            elif situacao == MeusProjetosForm.PROJETOS_PRE_SELECIONADOS:
                participacoes = participacoes.filter(projeto__pre_aprovado=True, projeto__data_pre_avaliacao__isnull=False)
            elif situacao == MeusProjetosForm.PROJETOS_EM_EXECUCAO:
                participacoes = participacoes.filter(projeto__aprovado=True, projeto__registroconclusaoprojeto__dt_avaliacao__isnull=True).distinct()
            elif situacao == MeusProjetosForm.PROJETOS_ENCERRADOS:
                participacoes = (
                    participacoes.filter(projeto__aprovado=True, projeto__registroconclusaoprojeto__dt_avaliacao__isnull=False)
                    .exclude(projeto__in=projetos_cancelados)
                    .distinct()
                )
            elif situacao == MeusProjetosForm.PROJETOS_CANCELADOS:
                participacoes = participacoes.filter(projeto__in=projetos_cancelados).distinct()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_pre_avaliar_projeto')
def pre_avaliacao(request):
    editais = Edital.objects.em_pre_avaliacao()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_projeto')
def avaliacao(request):
    title = 'Editais em Avaliação'
    editais_com_indicacao = AvaliadorIndicado.objects.filter(vinculo=request.user.get_vinculo())
    editais = Edital.objects.em_selecao().filter(pk__in=editais_com_indicacao.values_list('projeto__edital', flat=True))

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_projeto')
def projetos_pre_aprovados(request, edital_id, uo_id):
    title = 'Seleção de Projetos'
    edital = get_object_or_404(Edital, pk=edital_id)

    if not edital.is_periodo_selecao():
        raise PermissionDenied

    uo = UnidadeOrganizacional.objects.get(pk=uo_id)
    projetos = Projeto.objects.filter(avaliadorindicado__vinculo=request.user.get_vinculo(), edital=edital, pre_aprovado=True, uo=uo).order_by(
        '-pontuacao'
    )
    uos = [uo]

    for uo in uos:
        oferta = edital.ofertaprojeto_set.get(uo=uo)
        uo.qtd_ofertada = oferta.qtd_selecionados
        uo.qtd_aprovados = edital.projeto_set.filter(uo=uo, aprovado=True).count()
        uo.qtd_disponivel = oferta.qtd_selecionados - uo.qtd_aprovados

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_pre_avaliar_projeto')
def projetos_nao_avaliados(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)

    if not edital.is_periodo_pre_selecao():
        raise PermissionDenied

    title = f'Pré-Seleção de Projetos - {edital.titulo}'

    projetos = Projeto.objects.filter(edital=edital, data_conclusao_planejamento__isnull=False).order_by('titulo')

    uos = edital.get_uos()
    nao_eh_sistemico = False

    if request.user.groups.filter(name='Coordenador de Projetos de Ensino') and not request.user.groups.filter(
        name='Gerente Sistêmico de Projetos de Ensino'
    ):
        # projetos = projetos.filter(uo=get_uo(request.user))
        projetos = projetos.filter(uo__in=CampusAdicional.get_campi_user(request.user))

        nao_eh_sistemico = True
        uos = uos.filter(id__in=projetos.values_list('uo', flat=True))
        participacoes = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), projeto__edital=edital)
        if participacoes.exists():
            projetos = projetos.exclude(id__in=participacoes.values_list('projeto', flat=True))

    if (
        not request.user.groups.filter(name__in=['Gerente Sistêmico de Projetos de Ensino'])
        and get_uo(request.user).setor.sigla != get_sigla_reitoria()
    ):
        uo = get_uo(request.user)
        projetos = projetos.filter(uo=uo)
        nao_eh_sistemico = True
        uos = [uo]
    pode_pre_aprovar = True
    for uo in uos:
        tem_oferta = edital.ofertaprojeto_set.filter(uo=uo).count()
        if tem_oferta:
            oferta = edital.ofertaprojeto_set.get(uo=uo)
            uo.qtd_ofertada = oferta.qtd_aprovados
            uo.qtd_pre_aprovados = edital.num_total_projetos_pre_aprovados(uo)
            uo.qtd_inscritos = edital.num_total_projetos_inscritos(uo)
            uo.qtd_enviados = edital.num_total_projetos_enviados(uo)
            uo.qtd_disponivel = oferta.qtd_aprovados - uo.qtd_pre_aprovados
            if uo.qtd_disponivel == 0:
                pode_pre_aprovar = False
        else:
            pode_pre_aprovar = False

    form = PreAvaliacaoForm(request.POST or None, request=request, nao_eh_sistemico=nao_eh_sistemico)
    if form.is_valid():
        campus_escolhido = form.cleaned_data.get('campus')
        eixo_tematico = form.cleaned_data.get('eixo_tematico')
        pendentes = form.cleaned_data.get('pendentes')
        if campus_escolhido:
            projetos = projetos.filter(uo=campus_escolhido)
        if eixo_tematico:
            projetos = projetos.filter(eixo_tematico=eixo_tematico)
        if pendentes:
            projetos = projetos.filter(data_pre_avaliacao=None)
    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editais_abertos(request):
    title = 'Editais de Ensino e de Fluxo Contínuo com Inscrições Abertas'
    editais = Edital.objects.em_inscricao()
    pode_clonar_projeto = Projeto.objects.filter(vinculo_coordenador=request.user.get_vinculo()).exists()
    return locals()


def _resumo_recursos(projeto: Projeto) -> tuple[list[dict[str, object]], Decimal, Decimal]:
    """Resumo do plano de aplicação por recurso do edital, com os totais planejado e executado do projeto."""
    resumo_recursos: list[dict[str, object]] = []
    recursos = projeto.edital.recurso_set.filter()
    geral_planejado = Decimal(0)
    geral_executado = Decimal(0)
    for recurso in recursos:
        despesa = recurso.despesa
        origem = recurso.origem
        valor_reservado = recurso.valor
        soma_distribuido = Decimal(0)
        soma_executado = Decimal(0)
        for item in projeto.itemmemoriacalculo_set.filter(despesa=despesa, origem=origem):
            soma_distribuido += item.get_subtotal()
            soma_executado += item.get_total_executado()
        valor_distribuido = soma_distribuido
        valor_executado = soma_executado
        valor_planejado = sum(projeto.desembolso_set.filter(item__despesa=despesa, item__origem=origem).values_list('valor', flat=True))
        valor_disponivel_orcamento = valor_distribuido - valor_planejado
        valor_disponivel_execucao = valor_planejado - valor_executado

        geral_planejado = geral_planejado + valor_distribuido
        geral_executado = geral_executado + valor_executado

        if valor_disponivel_orcamento < 0:
            cor_valor_disponivel_orcamento = 'False'
        else:
            cor_valor_disponivel_orcamento = 'True'
        if valor_distribuido > valor_reservado:
            cor_valor_distribuido = 'false'
        else:
            cor_valor_distribuido = 'true'
        resumo_recursos.append(
            {
                'origem': recurso.origem,
                'valor_reservado': valor_reservado,
                'despesa': despesa,
                'valor_distribuido': valor_distribuido,
                'valor_planejado': valor_planejado,
                'valor_disponivel_orcamento': valor_disponivel_orcamento,
                'valor_executado': valor_executado,
                'valor_disponivel_execucao': valor_disponivel_execucao,
                'cor_valor_distribuido': cor_valor_distribuido,
                'cor_valor_disponivel_orcamento': cor_valor_disponivel_orcamento,
            }
        )
    return resumo_recursos, geral_planejado, geral_executado


def _filtrar_frequencias(registros_frequencia: QuerySet[RegistroFrequencia], filtros: Mapping[str, Any]) -> tuple[QuerySet[RegistroFrequencia], str]:
    """Aplica os filtros de ``FiltrarListaFrequenciaForm`` e devolve também esses filtros como query string."""
    data_inicio: datetime.date | None = filtros.get('data_inicio')
    data_termino: datetime.date | None = filtros.get('data_termino')
    participante: Vinculo | None = filtros.get('participante')
    retorno_inicio = retorno_fim = retorno_participante = ''
    if data_inicio:
        registros_frequencia = registros_frequencia.filter(data__gte=data_inicio)
        retorno_inicio = data_inicio.strftime('%d/%m/%Y')
    if data_termino:
        registros_frequencia = registros_frequencia.filter(data__lte=data_termino)
        retorno_fim = data_termino.strftime('%d/%m/%Y')
    if participante:
        registros_frequencia = registros_frequencia.filter(cadastrada_por=participante)
        retorno_participante = participante.id
    return registros_frequencia, f'data_inicio={retorno_inicio}&data_termino={retorno_fim}&participante={retorno_participante}'


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def projeto(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    vinculo = usuario_logado.get_vinculo()
    edital_projeto = projeto.edital
    tem_movimentacao = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).exists()
    title = f'Projeto de {projeto.edital.get_tipo_edital_display()}: {projeto.titulo}'
    periodo = projeto.get_periodo()
    status = projeto.get_status()
    status_pre_selecao = projeto.get_pre_selecionado(user=usuario_logado)
    status_selecao = projeto.get_selecionado()

    # mesmo_campus = projeto.uo == get_uo(usuario_logado)
    mesmo_campus = projeto.uo in CampusAdicional.get_campi_user(request.user)

    participantes = projeto.participacao_set.all()
    avaliador_pode_visualizar = projeto.avaliador_pode_visualizar()

    is_gerente_sistemico = projeto.is_gerente_sistemico(usuario_logado)

    is_avaliador = projeto.is_avaliador(usuario_logado)
    is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists() and mesmo_campus

    eh_visualizador = usuario_logado.groups.filter(name='Visualizador de Projetos de Ensino').exists()

    eh_participante = projeto.pode_acessar_projeto(usuario_logado)
    eh_coordenador = projeto.is_responsavel(usuario_logado)
    eh_monitor = vinculo == projeto.vinculo_monitor
    pode_gerenciar_projeto = is_gerente_sistemico or eh_coordenador
    eh_somente_leitura = projeto.eh_somente_leitura()
    eh_coordenador_de_curso = usuario_logado.groups.filter(name='Coordenador de Curso').exists()
    pode_editar_inscricao_execucao = projeto.pode_editar_inscricao_execucao()
    pode_registrar_execucao = projeto.pode_registrar_execucao()
    pode_finalizar_conclusao = projeto.pode_finalizar_conclusao()
    edicao_inscricao_execucao = projeto.edicao_inscricao_execucao()
    valor_financiado_por_projeto = projeto.edital.valor_financiado_por_projeto
    divulgacao_avaliacao_liberada = projeto.divulgacao_avaliacao_liberada()
    edital_exige_avaliacao_aluno = projeto.edital.exige_avaliacao_aluno

    pode_acessar_certificado = status in (Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO)
    hoje = datetime.datetime.now()
    divulgado = Projeto.objects.filter(id=projeto_id, edital__divulgacao_selecao__lte=hoje)
    edital_projeto = Edital.objects.get(pk=projeto.edital.id)
    avaliador_pode_imprimir = is_avaliador and edital_projeto.is_periodo_selecao()

    tem_cancelamento = ProjetoCancelado.objects.filter(projeto=projeto)

    registro_conclusao = projeto.get_registro_conclusao()
    tem_pendencias = projeto.tem_pendencias() or not registro_conclusao or (registro_conclusao and not registro_conclusao.dt_avaliacao)

    tem_historico_datas = HistoricoAlteracaoPeriodoProjeto.objects.filter(projeto=projeto)
    pode_ver_avaliacoes = projeto.is_coordenador(usuario_logado) or eh_monitor
    pode_inativar_projeto = is_pre_avaliador or is_gerente_sistemico

    liberar_botao_editar = False
    if hoje.date() > projeto.fim_execucao and registro_conclusao and pode_editar_inscricao_execucao:
        liberar_botao_editar = registro_conclusao.dt_avaliacao
    if not (
        eh_monitor
        or eh_coordenador
        or is_gerente_sistemico
        or is_avaliador
        or (is_pre_avaliador and mesmo_campus)
        or eh_participante
        or eh_visualizador
        or eh_coordenador_de_curso
    ):
        raise PermissionDenied

    edicao_inscricao = False
    if is_gerente_sistemico or (eh_coordenador and status == Projeto.STATUS_EM_INSCRICAO):
        edicao_inscricao = True

    edicao_inscricao_execucao = False
    if is_gerente_sistemico or (eh_coordenador and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO)):
        edicao_inscricao_execucao = True

    if eh_participante and not eh_coordenador:
        edicao_inscricao = False
        edicao_inscricao_execucao = False

    resumo_recursos, geral_planejado, geral_executado = _resumo_recursos(projeto)

    geral_saldo = projeto.edital.valor_financiado_por_projeto - geral_planejado
    geral_disponivel = geral_planejado - geral_executado

    termos_cessao = RegistroGasto.objects.filter(desembolso__projeto=projeto, arquivo_termo_cessao__isnull=False, arquivo_termo_cessao__gt='')

    devolucao = None
    if (
        ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).exists()
        and status == projeto.STATUS_EM_INSCRICAO
        and ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).latest('id').situacao == ProjetoHistoricoDeEnvio.DEVOLVIDO
    ):
        devolucao = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).latest('id')
    registros_frequencia = RegistroFrequencia.objects.filter(projeto=projeto).order_by('-data', 'cadastrada_por')
    pode_ver_frequencias = eh_coordenador or is_gerente_sistemico or is_pre_avaliador or eh_visualizador
    tem_frequencia_aluno_pendente = projeto.tem_frequencia_aluno_pendente()
    if not pode_ver_frequencias:
        registros_frequencia = registros_frequencia.filter(cadastrada_por=vinculo)
    form_frequencias = FiltrarListaFrequenciaForm(request.GET or None, projeto=projeto)
    if form_frequencias.is_valid():
        registros_frequencia, filtros_na_url = _filtrar_frequencias(registros_frequencia, form_frequencias.cleaned_data)
        if 'tab' not in request.GET:
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=registro_frequencia&{filtros_na_url}&filtrarlistafrequencia_form=Aguarde...')
    pode_ver_dados_bancarios = is_gerente_sistemico or eh_coordenador or is_pre_avaliador
    return locals()


@documento(enumerar_paginas=False)
@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def imprimir_projeto(request, projeto_id):
    is_avaliador = request.user.groups.filter(name='Avaliador de Projetos de Ensino')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
    cronograma = projeto.get_cronograma_desembolso_como_lista()
    plano_aplicacao = projeto.get_plano_aplicacao_como_dict()
    edital_projeto = Edital.objects.get(pk=projeto.edital.id)
    em_avaliacao = projeto.edital.is_periodo_pre_selecao() or projeto.edital.is_periodo_selecao()
    total_geral = projeto.itemmemoriacalculo_set.extra({'total': 'SUM(valor_unitario*qtd)'}).values('total')[0]['total']

    metas = projeto.get_metas()
    tipo_vinculo = TipoVinculo()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
    html = 'html' in request.GET

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def relatorio_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
    cronograma = projeto.get_cronograma_desembolso_como_lista()
    valor_financiamento_projeto = (
        RegistroGasto.objects.filter(item__projeto__id=projeto_id, aprovado=True)
        .extra(select={'total': 'SUM(projetos_ensino_registrogasto.qtd*projetos_ensino_registrogasto.valor_unitario)'})
        .values('total')[0]['total']
    )
    tipo_vinculo = TipoVinculo()
    pdf = False
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
    html = 'html' in request.GET

    return locals()


def _item_memoria_calculo_alteravel(projeto: Projeto, item_id: str) -> ItemMemoriaCalculo:
    """Item do projeto que a aba "Plano de Aplicação" oferece para editar/remover; senão 403 (#17546)."""
    item = get_object_or_404(ItemMemoriaCalculo, pk=item_id, projeto=projeto)
    if not item.pode_editar_e_remover_memoria_calculo():
        raise PermissionDenied
    return item


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def memoria_calculo(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Memória de Cálculo'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    url = f'/projetos_ensino/projeto/{projeto.id}/?tab=plano_aplicacao'
    tem_permissao(request, projeto)
    # A aba só oferece adicionar/editar/remover fora do somente leitura (cancelado, inativado, finalizado, enviado fora da execução).
    if projeto.eh_somente_leitura():
        raise PermissionDenied
    editavel = not projeto.data_pre_avaliacao and request.user.groups.filter(name__in=['Servidor', 'Aposentado']).exists()
    if editavel:
        editavel = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), responsavel=True).count() > 0

    if request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
        editavel = True

    is_operador = True

    item = None
    is_coordenador = projeto.is_coordenador(request.user)
    is_avaliador = projeto.is_avaliador(request.user)
    eh_edicao = False
    if 'edit_id' in request.GET:
        item = _item_memoria_calculo_alteravel(projeto, request.GET['edit_id'])
        eh_edicao = True

    if 'del_id' in request.GET:
        item = _item_memoria_calculo_alteravel(projeto, request.GET['del_id'])
        item.delete()
        item = None
        return httprr(url, 'Item removido com sucesso.')

    if request.method == 'POST':
        form = ItemMemoriaCalculoForm(data=request.POST, instance=item, projeto=projeto, edicao=eh_edicao)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            if not eh_edicao:
                o.despesa = form.cleaned_data['recurso'].despesa
                o.origem = form.cleaned_data['recurso'].origem
            o.save()
            if item:
                return httprr(url, 'Item editado com sucesso.')
            else:
                return httprr('..', 'Item adicionado com sucesso.')
    else:
        form = ItemMemoriaCalculoForm(instance=item, projeto=projeto, edicao=eh_edicao)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def registro_conclusao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    title = 'Conclusão do Projeto'
    registro = projeto.get_registro_conclusao()
    form = RegistroConclusaoProjetoForm(data=request.POST or None, instance=registro, projeto=projeto)
    if form.is_valid():
        registro = form.save(False)
        registro.projeto = projeto
        registro.save()
        return httprr('..', 'Conclusão do projeto registrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def registro_gasto(request: HttpRequest, item_id: int) -> dict | HttpResponse:
    title = 'Gastos Registrados'
    desembolso = get_object_or_404(Desembolso, pk=item_id)
    projeto = desembolso.projeto
    tem_permissao_gerenciar_gasto(request, projeto)
    ja_tem_registrogasto = desembolso.registrogasto_set.exists()
    is_coordenador = projeto.is_coordenador(request.user) or projeto.is_gerente_sistemico()
    registro = None
    edicao = False

    if request.method == 'GET' and 'registro_id' in request.GET:
        registro_gasto = get_object_or_404(RegistroGasto, pk=request.GET['registro_id'], desembolso=desembolso)
        if not registro_gasto.pode_editar_remover_registro_gasto():
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Não é possível excluir um registro de gasto avaliado.', 'alert')
        registro_gasto.delete()
        return httprr('.', 'Registro excluído com sucesso.')

    if 'editar_registro_id' in request.GET:
        registro = get_object_or_404(RegistroGasto, pk=request.GET['editar_registro_id'], desembolso=desembolso)
        edicao = True
        if _gasto_avaliado_com_comprovante(registro):
            return httprr(f'/projetos_ensino/projeto/{desembolso.projeto.id}/', 'Não é possível editar um registro de gasto avaliado.', 'alert')

    if request.method == 'POST':
        form = RegistroGastoForm(request.POST, request.FILES, instance=registro)
        if form.is_valid():
            registro_gasto = form.save(False)
            registro_gasto.desembolso = desembolso
            if not registro_gasto.data_cadastro:
                registro_gasto.data_cadastro = datetime.datetime.today()
            registro_gasto.save()
            if registro and registro.dt_avaliacao:
                return httprr(f'/projetos_ensino/projeto/{desembolso.projeto.id}/', 'Comprovante de gasto cadastrado com sucesso.')
            else:
                return httprr('.', 'Gasto registrado com sucesso.')
    else:
        if registro:
            form = RegistroGastoForm(instance=registro)
        else:
            initial = {
                'descricao': desembolso.item.descricao,
                'qtd': 1,
                'valor_unitario': desembolso.valor,
                'ano': desembolso.ano.pk,
                'mes': desembolso.mes,
            }
            form = RegistroGastoForm(initial=initial)
            field_qtd = form.fields['qtd']

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def registro_execucao_etapa(request, etapa_id):
    title = 'Registro de  Execução de Atividade'
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto)
    if projeto.pode_registrar_execucao() and not projeto.eh_somente_leitura():
        instance = etapa.get_registro_execucao()
        if not projeto.is_coordenador(request.user):
            return httprr('..', 'Apenas o cordenador do projeto tem acesso a essa página.', 'alert')
        if request.method == 'POST':
            form = RegistroExecucaoEtapaForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                registro_execucao_etapa = form.save(False)
                registro_execucao_etapa.etapa = etapa
                registro_execucao_etapa.data_cadastro_execucao = datetime.datetime.today()
                registro_execucao_etapa.save()
                return httprr('..', 'Execução registrada com sucesso.')
        else:
            if instance:
                form = RegistroExecucaoEtapaForm(instance=instance)
            else:
                initial = {'qtd': etapa.qtd, 'inicio_execucao': etapa.inicio_execucao, 'fim_execucao': etapa.fim_execucao}
                form = RegistroExecucaoEtapaForm(initial=initial)
            form.fields['qtd'].help_text = f'Quantidade de "{etapa.unidade_medida}"'

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def excluir_registro_execucao_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto)
    instance = etapa.get_registro_execucao()
    if projeto.pode_registrar_execucao() and not projeto.eh_somente_leitura() and instance and etapa.get_status_execucao() == 2:
        if not projeto.is_coordenador(request.user):
            return httprr('..', 'Apenas o cordenador do projeto tem acesso a essa página.', 'alert')
        instance.delete()
        return httprr(f'/projetos_ensino/projeto/{projeto.pk}/?tab=metas', 'Registro de execução de etapa removido com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projetos_em_monitoramento')
def validar_execucao_etapa(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Validar Execução'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    status = projeto.get_status()
    pode_validar = (projeto.vinculo_monitor == request.user.get_vinculo()) and not projeto.eh_participante(request.user)
    if pode_validar:
        if request.method == 'GET' and 'registro_id' in request.GET:
            registro = get_object_or_404(RegistroExecucaoEtapa, pk=request.GET['registro_id'], etapa__meta__projeto=projeto)
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = True
            registro.save()
            return httprr(f'/projetos_ensino/validar_execucao_etapa/{projeto.pk}/?tab=metas', 'Execução de atividade validada com sucesso.')

        elif request.method == 'GET' and 'item_id' in request.GET:
            registro = get_object_or_404(RegistroGasto, pk=request.GET['item_id'], item__projeto=projeto)
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = True
            registro.save()
            return httprr(f'/projetos_ensino/validar_execucao_etapa/{projeto.pk}/?tab=gastos', 'Gasto validado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_monitorar_projeto')
def reprovar_execucao_etapa(request, registroexecucaoetapa_id):
    title = 'Justificar Não Aprovação da Atividade'
    registro = RegistroExecucaoEtapa.objects.get(pk=registroexecucaoetapa_id)
    if request.user.get_vinculo() == registro.etapa.meta.projeto.vinculo_monitor:
        form = ReprovarExecucaoEtapaForm(request.POST or None)
        if form.is_valid():
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = False
            registro.justificativa_reprovacao = form.cleaned_data['obs']
            registro.save()
            return httprr('..', 'Execução de atividade avaliada com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_monitorar_projeto')
def reprovar_execucao_gasto(request, registroexecucaogasto_id):
    title = 'Justificar Não Aprovação do Gasto'
    registro = RegistroGasto.objects.get(pk=registroexecucaogasto_id)
    if request.user.get_vinculo() == registro.desembolso.projeto.vinculo_monitor:
        form = ReprovarExecucaoGastoForm(request.POST or None)
        if form.is_valid():
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = False
            registro.justificativa_reprovacao = form.cleaned_data['obs']
            registro.save()
            return httprr('..', 'Gasto avaliado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_participante_servidor(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Adicionar Participante'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao_alterar_equipe(request, projeto)
    if request.method == 'POST':
        form = ParticipacaoServidorForm(data=request.POST)
        form.projeto = projeto
        if form.is_valid():
            participacao = form.save(False)
            participacao.projeto = projeto
            if participacao.vinculo == TipoVinculo.BOLSISTA:
                participacao.bolsa_concedida = True
            participacao.pessoa = form.cleaned_data['servidor']
            participacao.vinculo_pessoa = form.cleaned_data['servidor'].get_vinculo()
            if Participacao.objects.filter(projeto=participacao.projeto, vinculo_pessoa=participacao.vinculo_pessoa).exists():
                return httprr('.', 'Este participante já pertence ao projeto.', tag='error')
            participacao.save()
            participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR, data_evento=form.cleaned_data.get('data'))
            Participacao.gerar_anexos_do_participante(participacao)
            if projeto.edital.exige_termo_servidor():
                titulo = '[SUAP] Projetos de Ensino: Termo de Compromisso do Servidor'
                texto = (
                    '<h1>Projetos de Ensino</h1>'
                    '<h2>Termo de Compromisso do Servidor</h2>'
                    f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('servidor').get_vinculo()])

            return httprr('..', 'Participante adicionado com sucesso.')
    else:
        form = ParticipacaoServidorForm()
        form.projeto = projeto

    return locals()


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_participante_servidor(request: HttpRequest, projeto_id: int, participacao_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao_alterar_equipe(request, projeto)
    participacao = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
    title = f'Editar Participação: {participacao.vinculo_pessoa.pessoa.nome}'
    form = ParticipacaoServidorForm(request.POST or None, instance=participacao)
    alterou = False
    if form.is_valid():
        participacao = form.save(False)
        if participacao.vinculo == TipoVinculo.BOLSISTA:
            participacao.bolsa_concedida = True
        participacao_anterior = Participacao.objects.get(id=participacao.id)
        if (
            form.cleaned_data.get('vinculo') != participacao_anterior.vinculo
            or form.cleaned_data.get('carga_horaria') != participacao_anterior.carga_horaria
        ):
            alterou = True
        participacao.save()
        if alterou:
            participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_EDICAO_SERVIDOR, data_evento=form.cleaned_data.get('data'))
            Participacao.gerar_anexos_do_participante(participacao)
        else:
            historico = HistoricoEquipe.objects.filter(participante=participacao, projeto=projeto).order_by('id')
            if historico.exists():
                registro = historico[0]
                registro.data_movimentacao = form.cleaned_data.get('data')
                registro.save()
        return httprr('..', 'Participante editado com sucesso.')

    return locals()


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_participante_aluno(request: HttpRequest, projeto_id: int, participacao_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao_alterar_equipe(request, projeto)
    participacao = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
    title = f'Editar Participação: {participacao.get_nome()}'
    form = ParticipacaoAlunoForm(request.POST or None, instance=participacao, editar=True, projeto=projeto)
    alterou = False
    adicionou_evento = False
    if form.is_valid():
        if participacao.vinculo == TipoVinculo.BOLSISTA:
            participacao.bolsa_concedida = True

        if not participacao.vinculo_pessoa and not form.cleaned_data.get('indicar_pessoa_posteriormente') and form.cleaned_data.get('aluno'):
            participacao.pessoa = form.cleaned_data.get('aluno').pessoa_fisica
            participacao.vinculo_pessoa = Vinculo.objects.get(id_relacionamento=form.cleaned_data.get('aluno').id, tipo_relacionamento__model='aluno')
            participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=form.cleaned_data.get('data'))
            adicionou_evento = True

        participacao_anterior = Participacao.objects.get(id=participacao.id)
        if (
            form.cleaned_data.get('vinculo') != participacao_anterior.vinculo
            or form.cleaned_data.get('carga_horaria') != participacao_anterior.carga_horaria
        ):
            alterou = True
        participacao.save()
        if alterou:
            if participacao.vinculo_pessoa and not adicionou_evento:
                participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_EDICAO_ALUNO, data_evento=form.cleaned_data.get('data'))
            Participacao.gerar_anexos_do_participante(participacao)
        else:
            historico = HistoricoEquipe.objects.filter(participante=participacao, projeto=projeto).order_by('id')
            if historico.exists() and not form.cleaned_data.get('indicar_pessoa_posteriormente') and form.cleaned_data.get('data'):
                registro = historico[0]
                registro.data_movimentacao = form.cleaned_data.get('data')
                registro.save()
        return httprr('..', 'Participante editado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def alterar_coordenador(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Alterar Coordenador'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao_alterar_equipe(request, projeto)
    participacao_anterior = Participacao.objects.get(projeto__id=projeto.pk, responsavel=True)
    participacoes = Participacao.objects.filter(projeto__id=projeto.pk, responsavel=False, ativo=True)
    participacoes = participacoes.filter(vinculo_pessoa__tipo_relacionamento__model='servidor')
    ids_excluidos = []
    for participacao in participacoes:
        if not participacao.vinculo_pessoa.ativo:
            ids_excluidos.append(participacao.id)
    participacoes = participacoes.exclude(id__in=ids_excluidos)

    if request.method == 'POST':
        form = AlterarCoordenadorForm(data=request.POST, projeto=projeto)
        if form.is_valid():
            participacao = form.cleaned_data['participacao']
            data = form.cleaned_data.get('data')
            participacao_anterior.responsavel = False
            participacao_anterior.save()
            participacao_anterior.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_DESISTITUIDO, data_evento=data)
            participacao.responsavel = True
            participacao.save()
            participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_SUBSTITUIDO, data_evento=data)
            return httprr('..', 'Coordenador alterado com sucesso.')
    else:
        form = AlterarCoordenadorForm(projeto=projeto)

    form.fields['participacao'].queryset = participacoes

    return locals()


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_participante_aluno(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Adicionar Aluno'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao_alterar_equipe(request, projeto)
    if request.method == 'POST':
        form = ParticipacaoAlunoForm(data=request.POST, editar=False, projeto=projeto)
        form.projeto = projeto
        if form.is_valid():
            participacao = form.save(False)
            participacao.projeto = projeto
            if participacao.vinculo == TipoVinculo.BOLSISTA:
                participacao.bolsa_concedida = True
            if form.cleaned_data.get('aluno'):
                participacao.pessoa = form.cleaned_data['aluno'].pessoa_fisica
                if Vinculo.objects.filter(id_relacionamento=form.cleaned_data['aluno'].id, tipo_relacionamento__model='aluno'):
                    participacao.vinculo_pessoa = Vinculo.objects.filter(
                        id_relacionamento=form.cleaned_data['aluno'].id, tipo_relacionamento__model='aluno'
                    )[0]
                if Participacao.objects.filter(projeto=participacao.projeto, vinculo_pessoa=participacao.vinculo_pessoa).exists():
                    return httprr('.', 'Este participante já pertence ao projeto.', tag='error')
            participacao.save()
            if form.cleaned_data.get('aluno'):
                participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=form.cleaned_data.get('data'))
            Participacao.gerar_anexos_do_participante(participacao)
            if projeto.edital.exige_termo_aluno() and form.cleaned_data.get('aluno'):
                titulo = '[SUAP] Projetos de Ensino: Termo de Compromisso do Aluno'
                texto = (
                    '<h1>Projetos de Ensino</h1>'
                    '<h2>Termo de Compromisso do Aluno</h2>'
                    f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('aluno').get_vinculo()])

            return httprr('..', 'Participante adicionado com sucesso.')
    else:
        form = ParticipacaoAlunoForm(editar=False, projeto=projeto)
        form.projeto = projeto

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_pre_avaliar_projeto')
def pre_aprovar(request, projeto_id):
    return pre_selecionar(request, projeto_id, rejeitar=False)


@rtr()
@permission_required('projetos_ensino.pode_pre_avaliar_projeto')
def pre_rejeitar(request, projeto_id):
    return pre_selecionar(request, projeto_id, rejeitar=True)


@rtr()
@permission_required('projetos_ensino.pode_avaliar_projeto')
def avaliar(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Avaliação de Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not projeto.pode_avaliar_projeto(request.user.get_vinculo()):
        raise PermissionDenied

    if not projeto.edital.criterioavaliacao_set.exists():
        raise PermissionDenied('Os critérios de seleção do edital não foram cadastrados.')

    avaliador = request.user.get_profile()
    vinculo = request.user.get_vinculo()

    try:
        avaliacao = Avaliacao.objects.get(projeto=projeto, vinculo=vinculo)
    except Exception:
        avaliacao = None
    form = AvaliacaoFormFactory(request, avaliacao, projeto, avaliador, vinculo)
    if form.is_valid():
        form.save()
        return httprr('..', 'Projeto avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def visualizar_ficha_avaliacao(request: HttpRequest, avaliacao_id: int) -> dict:
    title = 'Detalhamento da Avaliação do Projeto '
    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    eh_sistemico = False
    itens_avaliacao = ItemAvaliacao.objects.filter(avaliacao=avaliacao).order_by('-pontuacao')
    if itens_avaliacao.exists():
        projeto = itens_avaliacao[0].avaliacao.projeto
        # o mesmo predicado de `ver_alteracao_ficha_avaliacao`: Coordenador de Projetos de Ensino do campus ou `tem_permissao`
        pode_ver_alteracao = (
            eh_coordenador_ensino_do_campus(request.user, projeto)
            or projeto.is_responsavel(request.user)
            or projeto.is_gerente_sistemico(request.user)
        )

    if request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
        eh_sistemico = True

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projetos_em_monitoramento')
def projetos_em_execucao(request):
    title = 'Monitoramento'
    hoje = datetime.datetime.now()

    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos = (
        Projeto.objects.filter(
            aprovado=True, inativado=False, edital__divulgacao_selecao__lte=hoje, registroconclusaoprojeto__dt_avaliacao__isnull=True
        )
        .exclude(id__in=projetos_cancelados)
        .order_by('-edital__divulgacao_selecao')
    )
    ano = request.GET.get('ano')
    form = BuscaProjetoForm(data=request.GET or None, request=request, ano=ano)
    if request.user.has_group_cached('Coordenador de Extensão'):
        participacoes = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), ativo=True)
        if participacoes.exists():
            projetos = projetos.exclude(id__in=participacoes.values_list('projeto', flat=True))

    if not request.user.has_group_cached(
        ['Visualizador de Projetos de Ensino', 'Gerente Sistêmico de Projetos de Ensino', 'Monitor de Projetos de Ensino']
    ):
        projetos = projetos.filter(uo=get_uo(request.user))

    if request.user.has_group_cached('Monitor de Projetos de Ensino') and not request.user.has_group_cached(
        ['Gerente Sistêmico de Projetos de Ensino', 'Coordenador de Projetos de Ensino']
    ):
        projetos = projetos.filter(vinculo_monitor=request.user.get_vinculo())

    elif request.user.has_group_cached('Monitor de Projetos de Ensino') and request.user.has_group_cached('Coordenador de Projetos de Ensino'):
        # projetos = projetos.filter(uo=get_uo(request.user)) | projetos.filter(vinculo_monitor=request.user.get_vinculo())
        projetos = projetos.filter(uo__in=CampusAdicional.get_campi_user(request.user)) | projetos.filter(vinculo_monitor=request.user.get_vinculo())
    if form.is_valid():
        if form.cleaned_data.get('palavra_chave'):
            projetos = projetos.filter(titulo__icontains=form.cleaned_data['palavra_chave'])

        if form.cleaned_data.get('uo'):
            projetos = projetos.filter(uo=form.cleaned_data['uo'])

        if form.cleaned_data.get('ano'):
            projetos = projetos.filter(edital__inicio_inscricoes__year=form.cleaned_data['ano'])

        if form.cleaned_data.get('edital'):
            projetos = projetos.filter(edital=form.cleaned_data['edital'])

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def remover_participante(request: HttpRequest, participacao_id: int) -> dict | HttpResponse:
    title = 'Inativar Participante'
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    tem_permissao_alterar_equipe(request, projeto)
    form = DataInativacaoForm(request.POST or None, projeto=projeto, participacao=participacao)
    if form.is_valid():
        data_escolhida = form.cleaned_data.get('data')
        if (
            HistoricoOrientacaoProjeto.objects.filter(orientador=participacao, data_inicio__gte=data_escolhida).exists()
            or HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_inicio__gte=data_escolhida).exists()
        ):
            return httprr(
                f'/projetos_ensino/projeto/{projeto.id}/?tab=equipe',
                'O participante está vinculado à orientações com data de início maior do que a data informada.',
                tag='error',
            )

        HistoricoOrientacaoProjeto.objects.filter(orientador=participacao, data_termino__isnull=True).update(data_termino=data_escolhida)
        HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_termino__isnull=True).update(data_termino=data_escolhida)
        for registro in HistoricoOrientacaoProjeto.objects.filter(orientador=participacao):
            registro_participacao = get_object_or_404(Participacao, pk=registro.orientado.id)
            registro_participacao.orientador = None
            registro_participacao.save()

        participacao.ativo = False
        participacao.orientador = None
        participacao.save()
        participacao.adicionar_registro_historico_equipe(
            HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_evento=data_escolhida, obs=form.cleaned_data.get('justificativa')
        )

        return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=equipe', 'Participação encerrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def ativar_participante(request: HttpRequest, participacao_id: int) -> HttpResponse:
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    tem_permissao_alterar_equipe(request, projeto)
    participacao.ativo = True
    participacao.save()
    participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ATIVAR_PARTICIPANTE)

    return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=equipe', 'Participante ativado com sucesso.')


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_meta(request, projeto_id):
    title = 'Adicionar Meta'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if request.method == 'POST':
        form = MetaForm(data=request.POST)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            o.save()
            return httprr('..', 'Meta adicionada com sucesso.')
    else:
        form = MetaForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_meta(request, meta_id):
    meta = get_object_or_404(Meta, pk=meta_id)
    tem_permissao(request, meta.projeto)
    if request.method == 'POST':
        form = MetaForm(data=request.POST, instance=meta)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Meta editada com sucesso.')
    else:
        form = MetaForm(instance=meta)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def remover_meta(request, meta_id):
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto)
    meta.delete()

    return httprr(f'/projetos_ensino/projeto/{projeto.pk}/?tab=metas', 'Meta removida com sucesso.')


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_etapa(request, meta_id):
    title = 'Adicionar Atividade'
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto)
    if request.method == 'POST':
        form = EtapaForm(data=request.POST, proj=projeto)
        if form.is_valid():
            o = form.save(False)
            o.meta = meta
            o.save()
            form.save_m2m()
            return httprr('..', 'Atividade adicionada com sucesso.')
    else:
        form = EtapaForm(proj=projeto)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def remover_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto)
    etapa.delete()

    return httprr(f'/projetos_ensino/projeto/{projeto.pk}/?tab=metas', 'Atividade removida com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto)
    title = 'Editar Atividade'
    if request.method == 'POST':
        form = EtapaForm(data=request.POST, instance=etapa, proj=projeto)
        if form.is_valid():
            o = form.save(False)
            o.save()
            form.save_m2m()
            return httprr('..', 'Atividade editada com sucesso.')
    else:
        form = EtapaForm(instance=etapa, proj=projeto)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_equipe_etapa(request, etapa_id):
    title = 'Editar Equipe da Atividade'
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto)
    if request.method == 'POST':
        form = EquipeEtapaForm(data=request.POST, instance=etapa, proj=projeto)
        if form.is_valid():
            o = form.save(False)
            o.save()
            form.save_m2m()
            return httprr('..', 'Etapa editada com sucesso.')
    else:
        form = EquipeEtapaForm(instance=etapa, proj=projeto)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def adicionar_recurso(request, edital_id):
    title = 'Adicionar Recurso'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = RecursoForm(data=request.POST, edital=edital)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.origem = form.cleaned_data.get('origem_recurso').descricao
            o.save()
            return httprr('..', 'Recurso adicionado com sucesso.')
    else:
        form = RecursoForm(edital=edital)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def remover_recurso(request, recurso_id):
    recurso = get_object_or_404(Recurso, pk=recurso_id)
    edital = recurso.edital
    tem_permissao_acesso_edital(request, edital)
    recurso.delete()

    return httprr(f'/projetos_ensino/edital/{edital.id}/', 'Recurso removido com sucesso.')


@rtr()
@permission_required('projetos_ensino.view_edital')
def editar_recurso(request, recurso_id):
    title = 'Editar Fonte de Recurso'
    recurso = get_object_or_404(Recurso, pk=recurso_id)
    tem_permissao_acesso_edital(request, recurso.edital)
    if request.method == 'POST':
        form = RecursoForm(data=request.POST, instance=recurso, edital=recurso.edital)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Recurso editado com sucesso.')
    else:
        form = RecursoForm(instance=recurso, edital=recurso.edital)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def adicionar_criterio_avaliacao(request, pk):
    title = 'Adicionar Critério de Avaliação'
    edital = get_object_or_404(Edital, pk=pk)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = CriterioAvaliacaoForm(data=request.POST)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.save()
            return httprr('..', 'Critério de avaliação adicionado com sucesso.')
    else:
        form = CriterioAvaliacaoForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def remover_criterio_avaliacao(request, pk):
    criterio = get_object_or_404(CriterioAvaliacao, pk=pk)
    edital = criterio.edital
    tem_permissao_acesso_edital(request, edital)
    criterio.delete()

    return httprr(f'/projetos_ensino/edital/{edital.id}/', 'Critério de avaliação removido com sucesso.')


@rtr()
@permission_required('projetos_ensino.view_edital')
def editar_criterio_avaliacao(request, pk):
    title = 'Editar Critério de Avaliação'
    criterio = get_object_or_404(CriterioAvaliacao, pk=pk)
    tem_permissao_acesso_edital(request, criterio.edital)
    if request.method == 'POST':
        form = CriterioAvaliacaoForm(data=request.POST, instance=criterio)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Critério de avaliação editado com sucesso.')
    else:
        form = CriterioAvaliacaoForm(instance=criterio)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def adicionar_anexo_auxiliar(request, edital_id):
    title = 'Adicionar Anexo'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = EditalAnexoAuxiliarForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.save()
            return httprr('..', 'Anexo adicionado com sucesso.')
    else:
        form = EditalAnexoAuxiliarForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def adicionar_anexo(request, edital_id):
    title = 'Adicionar Anexo'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = EditalAnexoForm(data=request.POST, edital=edital)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.save()
            return httprr('..', 'Anexo adicionado com sucesso.')
    else:
        form = EditalAnexoForm(edital=edital)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def remover_anexo(request, anexo_id):
    anexo = get_object_or_404(EditalAnexo, pk=anexo_id)
    edital = anexo.edital
    tem_permissao_acesso_edital(request, edital)
    anexo.delete()

    return httprr(f'/projetos_ensino/edital/{edital.id}/', 'Anexo removido com sucesso.')


@rtr()
@permission_required('projetos_ensino.view_edital')
def remover_anexo_auxiliar(request, anexo_id):
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    edital = anexo.edital
    tem_permissao_acesso_edital(request, edital)
    anexo.delete()

    return httprr(f'/projetos_ensino/edital/{edital.id}/', 'Anexo removido com sucesso.')


@rtr()
@permission_required('projetos_ensino.view_edital')
def editar_anexo(request, anexo_id):
    title = 'Editar Anexo'
    anexo = get_object_or_404(EditalAnexo, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
    if request.method == 'POST':
        form = EditalAnexoForm(data=request.POST, instance=anexo, edital=anexo.edital)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Anexo editado com sucesso.')
    else:
        form = EditalAnexoForm(instance=anexo, edital=anexo.edital)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def editar_anexo_auxiliar(request, anexo_id):
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
    title = 'Editar Anexo Auxiliar'
    if request.method == 'POST':
        form = EditalAnexoAuxiliarForm(request.POST or None, request.FILES or None, instance=anexo)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Anexo editado com sucesso.')
    else:
        form = EditalAnexoAuxiliarForm(instance=anexo)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def adicionar_oferta_projeto(request, edital_id):
    title = 'Adicionar Oferta de Projeto'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = OfertaProjetoForm(data=request.POST, edital=edital)
        if form.is_valid():
            o = form.save(False)
            if edital.forma_selecao == Edital.TEMA or edital.forma_selecao == Edital.GERAL:
                o.qtd_selecionados = 0
            o.edital = edital
            o.save()
            form.save_m2m()
            return httprr('..', 'Oferta adicionada com sucesso.')
    else:
        form = OfertaProjetoForm(edital=edital)

    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def remover_oferta_projeto(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    oferta = get_object_or_404(OfertaProjeto, pk=oferta_projeto_id, edital=edital)
    oferta.delete()

    return httprr(f'/projetos_ensino/edital/{edital.id}/', 'Oferta removida com sucesso.')


@rtr()
@permission_required('projetos_ensino.view_edital')
def editar_oferta_projeto(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    oferta = get_object_or_404(OfertaProjeto, pk=oferta_projeto_id, edital=edital)
    title = 'Editar Oferta'
    if request.method == 'POST':
        form = OfertaProjetoForm(data=request.POST, instance=oferta, edital=edital)
        if form.is_valid():
            o = form.save(False)
            o.save()
            form.save_m2m()
            return httprr('..', 'Oferta editada com sucesso.')
    else:
        form = OfertaProjetoForm(instance=oferta, edital=edital)

    return locals()


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_desembolso(request, projeto_id):
    title = 'Adicionar Desembolso'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if request.method == 'POST':
        form = DesembolsoForm(data=request.POST, proj=projeto)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            if form.cleaned_data['clonar_operacao']:
                o.save()
                quantidade = form.cleaned_data['clonar_operacao'] - form.cleaned_data['mes']
                i = 1
                mes = form.cleaned_data['mes']
                while i <= quantidade:
                    o.pk = None
                    o.mes = mes + 1
                    o.save()
                    mes = mes + 1
                    i = i + 1
            else:
                o.save()
            return httprr('..', 'Desembolso adicionado com sucesso.')
    else:
        form = DesembolsoForm(proj=projeto)

    return locals()


def eh_coordenador_ensino_do_campus(user: User, projeto: Projeto) -> bool:
    return user.groups.filter(name='Coordenador de Projetos de Ensino').exists() and projeto.uo == get_uo(user)


def tem_permissao(request, projeto):
    is_responsavel = projeto.is_responsavel(request.user) or projeto.is_gerente_sistemico()
    if not is_responsavel:
        raise PermissionDenied


def tem_permissao_alterar_equipe(request: HttpRequest, projeto: Projeto) -> None:
    """Exige o que a aba "Equipe" exige para oferecer as ações de alterar a equipe (``projeto.html``)."""
    tem_permissao(request, projeto)
    if not (projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura()):
        raise PermissionDenied


def _gastos_gerenciaveis(projeto: Projeto) -> bool:
    """Estado do projeto em que a aba "Plano de Desembolso" oferece "Gerenciar Gasto" (``projeto.html``)."""
    return bool((projeto.pode_editar_gasto() and not projeto.eh_somente_leitura()) or projeto.is_gerente_sistemico())


def _gasto_avaliado_com_comprovante(registro: RegistroGasto) -> bool:
    """Gasto avaliado que já tem nota fiscal: ``registro_gasto`` não o edita mais (sem ela, só anexa os arquivos)."""
    return bool(registro.dt_avaliacao and registro.arquivo)


def tem_permissao_gerenciar_gasto(request: HttpRequest, projeto: Projeto) -> None:
    """Exige o que a aba "Plano de Desembolso" exige para oferecer "Gerenciar Gasto" (``projeto.html``)."""
    tem_permissao(request, projeto)
    if not _gastos_gerenciaveis(projeto):
        raise PermissionDenied


def _gastos_com_cadastro_de_arquivo(projeto: Projeto, registros: QuerySet) -> set[int]:
    """Gastos cujo "Cadastrar" de comprovante/cotação em ``prestacao_contas`` abre ``registro_gasto``."""
    if not _gastos_gerenciaveis(projeto):
        return set()
    return {registro.pk for registro in registros if not _gasto_avaliado_com_comprovante(registro)}


def _dados_pdf_prestacao_contas(registros: QuerySet) -> list:
    """Linhas da tabela de gastos do PDF de ``prestacao_contas``, com a linha de total."""
    dados = [['Ano', 'Mês', 'Despesa', 'Descrição/Observação', 'Qtd.', 'Valor Unitário (R$)', 'Subtotal (R$)']]
    total = 0
    for registro in registros:
        subtotal = registro.get_subtotal()
        if registro.observacao:
            descricao = f'{registro.descricao} - <b>Obs:</b> {registro.observacao}'
        else:
            descricao = registro.descricao
        dados.append([registro.ano, registro.mes, registro.desembolso.despesa, descricao, registro.qtd, registro.valor_unitario, subtotal])
        total = total + subtotal
    dados.append([' ', ' ', ' ', ' ', ' ', 'Total', total])
    return dados


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_desembolso(request, desembolso_id):
    title = 'Editar Desembolso'
    desembolso = get_object_or_404(Desembolso, pk=desembolso_id)
    tem_permissao(request, desembolso.projeto)

    if request.method == 'POST':
        form = DesembolsoForm(data=request.POST, instance=desembolso)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Desembolso editado com sucesso.')
    else:
        form = DesembolsoForm(instance=desembolso)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def remover_desembolso(request, desembolso_id):
    desembolso = get_object_or_404(Desembolso, pk=desembolso_id)
    tem_permissao(request, desembolso.projeto)
    projeto = desembolso.projeto
    url = f'/projetos_ensino/projeto/{projeto.id}/?tab=plano_desembolso'
    desembolso.delete()

    return httprr(url, 'Desembolso removido com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def upload_anexo(request, anexo_id):
    title = 'Upload de Arquivo'
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    tem_permissao(request, anexo.projeto)
    if request.method == 'POST':
        form = UploadArquivoForm(request.POST, request.FILES, instance=anexo)
        if form.is_valid():
            form.save()
            return httprr('..', 'Arquivo enviado com sucesso.')
    else:
        form = UploadArquivoForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_anexo_do_projeto(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = get_object_or_404(Projeto, pk=participacao.projeto.id)
    tem_permissao(request, projeto)
    title = f'Anexos do Participante: {participacao.get_nome()}'
    Participacao.gerar_anexos_do_participante(participacao)
    anexos = ProjetoAnexo.objects.filter(projeto=participacao.projeto, participacao=participacao, anexo_edital__isnull=False)
    return locals()


@rtr()
@permission_required('projetos_ensino.view_edital')
def upload_edital(request, edital_id):
    title = 'Adicionar Edital'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = UploadEditalForm(request.POST, request.FILES, instance=edital)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos_ensino/edital/{edital.id}/', 'Arquivo enviado com sucesso.')
    else:
        form = UploadArquivoForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def visualizar_arquivo(request, arquivo_id):
    arquivo = get_object_or_404(Arquivo, id=arquivo_id)
    if ProjetoAnexo.objects.filter(arquivo__id=arquivo_id).exists():
        projeto = ProjetoAnexo.objects.filter(arquivo__id=arquivo_id)[0].projeto
        usuario_logado = request.user
        eh_coordenador = projeto.is_responsavel(usuario_logado)
        is_gerente_sistemico = projeto.is_gerente_sistemico(usuario_logado)
        is_avaliador = projeto.is_avaliador(usuario_logado)

        is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists()
        mesmo_campus = projeto.uo == get_uo(usuario_logado)
        if is_pre_avaliador:
            mesmo_campus = projeto.uo in CampusAdicional.get_campi_user(request.user)

        eh_visualizador = usuario_logado.groups.filter(name='Visualizador de Projetos de Ensino').exists()
        eh_participante = projeto.eh_participante(usuario_logado)
        if (
            (not eh_coordenador)
            and (not is_gerente_sistemico)
            and (not is_avaliador)
            and (not (is_pre_avaliador and mesmo_campus))
            and (not eh_participante)
            and (not eh_visualizador)
        ):
            raise PermissionDenied
    arquivo_tmp = arquivo.load()
    if arquivo_tmp is not None:
        response = HttpResponse(arquivo_tmp.read(), content_type=arquivo.get_content_type())
        response['Content-Disposition'] = 'filename={}'.format(to_ascii(arquivo.nome.replace('º', '.').replace('/', '-').replace(' ', '')))
        arquivo_tmp.close()
        os.remove(arquivo_tmp.name)
        return response
    else:
        return HttpResponse('O arquivo socilitado foi adulterado ou não existe.')


@rtr()
@permission_required('projetos_ensino.pode_monitorar_projeto')
def avaliar_conclusao_projeto(request: HttpRequest, registro_id: int) -> dict | HttpResponse:
    title = 'Validação da Conclusão do Projeto'
    registro = get_object_or_404(RegistroConclusaoProjeto, pk=registro_id)
    # mesmo estado em que a aba oferece "Emitir Parecer" (Projeto.pode_emitir_parecer): finalizado e ainda sem parecer
    aguardando_parecer = registro.projeto.data_finalizacao_conclusao and not registro.dt_avaliacao
    eh_monitor_ou_gerente = registro.projeto.vinculo_monitor == request.user.get_vinculo() or request.user.has_perm(
        'projetos_ensino.pode_gerenciar_edital'
    )
    if not (aguardando_parecer and eh_monitor_ou_gerente):
        raise PermissionDenied
    form = ValidacaoConclusaoProjetoForm(request.POST or None, registro=registro)
    if form.is_valid():
        aprovado = form.cleaned_data['aprovado']
        obs = form.cleaned_data['obs']

        registro.dt_avaliacao = datetime.date.today()
        registro.avaliador = request.user.get_relacionamento()
        registro.aprovado = aprovado
        registro.obs_avaliador = obs
        registro.save()
        return httprr('..', 'Conclusão do projeto registrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_foto(request, projeto_id):
    title = 'Adicionar Foto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if request.method == 'POST':
        form = FotoProjetoForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            o.save()
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=fotos', 'Foto adicionada com sucesso.')
    else:
        form = FotoProjetoForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def remover_foto(request, foto_id):
    foto = get_object_or_404(FotoProjeto, pk=foto_id)
    tem_permissao(request, foto.projeto)
    projeto_id = foto.projeto.id
    foto.delete()

    return httprr(f'/projetos_ensino/projeto/{projeto_id}/', 'Foto removida com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_projeto(request, edital_id):
    title = 'Adicionar projeto'
    if request.user.eh_prestador:
        raise PermissionDenied
    edital = get_object_or_404(Edital, pk=edital_id)
    vinculo_do_usuario = request.user.get_vinculo()
    if not edital.pode_submeter_projeto(vinculo_do_usuario):
        raise PermissionDenied
    if not edital.get_uos().exists():
        return httprr('/projetos_ensino/editais_abertos/', 'O edital selecionado não possui plano de oferta por campus cadastrado.', tag='error')
    elif not edital.pode_escolher_campus_submissao and get_uo(request.user) not in edital.get_uos():
        return httprr('/projetos_ensino/editais_abertos/', 'O edital selecionado não possui plano de oferta para o seu campus.', tag='error')
    instance = Projeto()
    instance.edital = edital
    instance.coordenador = request.user.get_profile()
    instance.vinculo_coordenador = vinculo_do_usuario
    form = ProjetoForm(request.POST or None, instance=instance, request=request, edicao=False)
    if request.method == 'POST':
        if form.is_valid():
            if form.cleaned_data.get('deseja_receber_bolsa'):
                instance.bolsa_coordenador = form.cleaned_data['deseja_receber_bolsa']
            else:
                instance.bolsa_coordenador = False
            form.save()

            p = Participacao()
            p.projeto = instance
            p.pessoa = request.user.get_profile()
            p.vinculo_pessoa = vinculo_do_usuario
            if instance.bolsa_coordenador:
                p.vinculo = TipoVinculo.BOLSISTA
                p.bolsa_concedida = True
            else:
                p.vinculo = TipoVinculo.VOLUNTARIO
                p.bolsa_concedida = False
            p.responsavel = True
            p.carga_horaria = form.cleaned_data.get('carga_horaria')
            if edital.termo_compromisso_coordenador:
                p.termo_aceito_em = datetime.datetime.now()
            p.save()
            p.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_INSERIDO, data_evento=p.projeto.inicio_execucao)

            projeto_id = (
                Participacao.objects.filter(projeto__edital__id=edital_id, vinculo_pessoa=vinculo_do_usuario, responsavel=True)
                .order_by('-id')[0]
                .projeto.id
            )
            return httprr(f'/projetos_ensino/projeto/{projeto_id}/', 'Projeto cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_projeto(request, projeto_id):
    title = 'Editar Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if projeto.get_periodo() == Projeto.PERIODO_EXECUCAO:
        data_inicio_atual = projeto.inicio_execucao
        data_fim_atual = projeto.fim_execucao
        form = EditarProjetoEmExecucaoForm(request.POST or None, instance=projeto, request=request)
        if form.is_valid():
            form.save()
            if form.cleaned_data.get('justificativa_alteracoes'):
                novo_historico = HistoricoAlteracaoPeriodoProjeto()
                novo_historico.projeto = projeto
                novo_historico.inicio_execucao = data_inicio_atual
                novo_historico.fim_execucao = data_fim_atual
                novo_historico.justificativa = form.cleaned_data.get('justificativa_alteracoes')
                novo_historico.registrado_por = request.user.get_profile()
                novo_historico.vinculo_registrado_por = request.user.get_vinculo()
                novo_historico.save()
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Projeto editado com sucesso.')

    elif projeto.get_periodo() == Projeto.PERIODO_INSCRICAO:
        form = ProjetoForm(request.POST or None, instance=projeto, request=request, edicao=True)
        if request.method == 'POST':
            if form.is_valid():
                form.save()
                part = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), projeto=projeto)
                if part.exists() and part[0].carga_horaria != form.cleaned_data.get('carga_horaria'):
                    p = part[0]
                    p.carga_horaria = form.cleaned_data.get('carga_horaria')
                    p.save()
                    p.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_EDICAO_SERVIDOR, data_evento=form.cleaned_data.get('data'))

                return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Projeto editado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_caracterizacao_beneficiario(request, projeto_id):
    title = 'Adicionar Caracterização do Beneficiário'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    caracterizacao_beneficiario = CaracterizacaoBeneficiario()
    caracterizacao_beneficiario.projeto = projeto
    form = CaracterizacaoBeneficiarioForm(request.POST or None, instance=caracterizacao_beneficiario, atendida=False, edicao_inscricao=True)
    if form.is_valid():
        form.save()
        return httprr('..', 'Caracterização do beneficiário adicionada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_caracterizacao_beneficiario(request, caracterizacao_beneficiario_id):
    title = 'Adicionar Caracterização do Beneficiário'
    caracterizacao_beneficiario = get_object_or_404(CaracterizacaoBeneficiario, pk=caracterizacao_beneficiario_id)
    projeto = caracterizacao_beneficiario.projeto
    tem_permissao(request, projeto)
    edicao_inscricao = True
    if projeto.get_status() == Projeto.STATUS_EM_EXECUCAO:
        edicao_inscricao = False
    form = CaracterizacaoBeneficiarioForm(request.POST or None, instance=caracterizacao_beneficiario, edicao_inscricao=edicao_inscricao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Caracterização do beneficiário editada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def remover_caracterizacao_beneficiario(request, caracterizacao_beneficiario_id):
    caracterizacao_beneficiario = get_object_or_404(CaracterizacaoBeneficiario, pk=caracterizacao_beneficiario_id)
    tem_permissao(request, caracterizacao_beneficiario.projeto)
    caracterizacao_beneficiario.delete()

    return httprr(
        f'/projetos_ensino/projeto/{caracterizacao_beneficiario.projeto.id}/?tab=caracterizacao_beneficiario',
        'Caracterização do Beneficiário removida com sucesso.',
    )


@rtr()
@permission_required('projetos_ensino.pode_pre_avaliar_projeto')
def pre_selecionar(request: HttpRequest, projeto_id: int, rejeitar: bool | None = None, url: str | None = None) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not url:
        url = request.META.get('HTTP_REFERER', '.')

    if not projeto.edital.is_periodo_pre_selecao():
        raise PermissionDenied

    if projeto.data_conclusao_planejamento is None:
        return httprr(url, 'Impossível realizar essa operação, projeto não foi enviado.', tag='error')

    # O papel (`pode_pre_selecionar`), o estado e a cota que a tela exige para oferecer a ação (#17579).
    if not projeto.pode_receber_pre_avaliacao(rejeitar):
        raise PermissionDenied

    projeto.vinculo_autor_pre_avaliacao = request.user.get_vinculo()
    projeto.vinculo_monitor = projeto.vinculo_autor_pre_avaliacao
    projeto.data_pre_avaliacao = datetime.date.today()

    # A decisão é a da rota, não o inverso do estado atual (#17579).
    if rejeitar:
        projeto.pre_aprovado = False
        if projeto.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            projeto.aprovado = False
            projeto.pontuacao = 0
            projeto.data_avaliacao = None
    else:
        projeto.pre_aprovado = True
        if projeto.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            projeto.aprovado = True
            projeto.pontuacao = 0
            projeto.data_avaliacao = None
    projeto.save()

    return httprr(f'/projetos_ensino/projetos_nao_avaliados/{projeto.edital.id}/', 'Projeto pré-avaliado com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def historico_equipe(request, participacao_id):
    title = 'Histórico da Participação'
    eh_sistemico = request.user.has_perm('projetos_ensino.pode_gerenciar_edital')
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    historico = HistoricoEquipe.objects.filter(participante=participacao_id).order_by('id').exclude(movimentacao='Ativado')
    como_coordenador = historico.filter(categoria=HistoricoEquipe.COORDENADOR)
    como_membro = historico.filter(categoria=HistoricoEquipe.MEMBRO)
    tipo_vinculo = TipoVinculo()
    orientacoes = None
    if not participacao.is_servidor():
        orientacoes = HistoricoOrientacaoProjeto.objects.filter(orientado=participacao).order_by('-id')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def concluir_planejamento(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    metas = Meta.objects.filter(projeto_id=projeto_id)
    tem_plano_aplicacao = ItemMemoriaCalculo.objects.filter(projeto_id=projeto_id)
    tem_desembolso = True
    mensagem_erro = ''
    for memoria_calculo in tem_plano_aplicacao:
        if not Desembolso.objects.filter(item=memoria_calculo).exists():
            tem_desembolso = False

    if projeto.edital.tipo_edital == Edital.ENSINO_CONTINUO:
        tem_desembolso = True
        tem_plano_aplicacao = True

    if not tem_desembolso:
        mensagem_erro = mensagem_erro + 'Cadastre o Plano de Desembolso para cada Item de Mémoria de Cálculo antes de enviar o Projeto.</br>'

    if not tem_plano_aplicacao and Recurso.objects.filter(edital=projeto.edital).exists():
        mensagem_erro = mensagem_erro + 'Cadastre o Plano de Aplicação antes de enviar o Projeto.</br>'

    if not metas:
        mensagem_erro = mensagem_erro + 'Cadastre as Metas/Atividades antes de enviar o Projeto.</br>'

    tem_atividade = False
    for meta in metas:
        atividade = Etapa.objects.filter(meta_id=meta.id)
        if atividade:
            tem_atividade = True
    if not tem_atividade:
        mensagem_erro = mensagem_erro + 'Cadastre as Atividades de cada Meta antes de enviar o Projeto.</br>'
    if mensagem_erro != '':
        return httprr(f'/projetos_ensino/projeto/{projeto.id}/', mensagem_erro, tag='error')
    projeto.data_conclusao_planejamento = datetime.date.today()
    if not projeto.vinculo_coordenador:
        projeto.vinculo_coordenador = Participacao.objects.filter(projeto=projeto, responsavel=True)[0].vinculo_pessoa

    projeto.save()
    historico_projeto = ProjetoHistoricoDeEnvio()
    historico_projeto.projeto = projeto
    historico_projeto.data_operacao = datetime.datetime.now()
    historico_projeto.situacao = ProjetoHistoricoDeEnvio.ENVIADO
    if request.user.get_vinculo().eh_servidor():
        historico_projeto.operador = request.user.get_relacionamento()
    historico_projeto.vinculo_operador = request.user.get_vinculo()
    historico_projeto.save()

    return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Projeto enviado com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def finalizar_conclusao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    mensagem_erro = ''
    if not projeto.data_finalizacao_conclusao:
        tem_permissao(request, projeto)

        if projeto.tem_registro_execucao_etapa_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois não há registro de execução de atividades ou existe registro não avaliados pelo monitor do projeto.'
        if projeto.tem_registro_gasto_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois existem desembolsos sem o registro das despesas realizadas ou existe despesa não avaliada pelo monitor do projeto.'
        if projeto.tem_registro_anexos_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois não há registro dos anexos do projeto.'
        if projeto.tem_registro_foto_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois não há registro das fotos do projeto. '

        if projeto.tem_caracterizacao_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois não foi informada a quantidade de beneficiários atendidos.'

        if projeto.tem_avaliacao_aluno_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois existe aluno sem a avaliação final cadastrada'

        if mensagem_erro != '':
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=conclusao', mensagem_erro, tag='error')

        projeto.data_finalizacao_conclusao = datetime.datetime.now()
        projeto.save()
        historico = ProjetoHistoricoDeEnvio()
        historico.projeto = projeto
        historico.data_operacao = datetime.datetime.now()
        historico.situacao = ProjetoHistoricoDeEnvio.FINALIZADO
        if request.user.get_vinculo().eh_servidor():
            historico.operador = request.user.get_relacionamento()
        historico.vinculo_operador = request.user.get_vinculo()
        historico.save()
        movimentacoes_sem_data_saida = HistoricoEquipe.objects.filter(projeto=projeto, data_movimentacao_saida__isnull=True)
        if movimentacoes_sem_data_saida:
            for movimentacao in movimentacoes_sem_data_saida:
                movimentacao.data_movimentacao_saida = datetime.datetime.today()
                movimentacao.save()

        titulo = '[SUAP] Finalização de Projeto'
        texto = (
            '<h1>Ensino</h1>'
            '<h2>Finalização de Projeto</h2>'
            f"<p>O Projeto '{projeto.titulo}' foi finalizado pelo Coordenador de Ensino. Acesse o SUAP para mais detalhes.</p>"
        )

        for membro in Participacao.objects.filter(projeto=projeto, ativo=True, vinculo_pessoa__isnull=False):
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [membro.vinculo_pessoa])

        return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Conclusão finalizada com sucesso.')
    else:
        return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Este projeto já foi concluído.', tag='error')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def gerenciar_historico_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    historico = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto_id).order_by('data_operacao')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Movimentação do Projeto: {projeto.titulo} '
    is_pre_avaliador = projeto.is_pre_avaliador(request.user) or projeto.is_gerente_sistemico(request.user)
    # O template só esconde o formulário: sem esta checagem, qualquer um devolvia o projeto por POST (#17515).
    if request.method == 'POST' and not projeto.pode_devolver_projeto():
        raise PermissionDenied
    form = ProjetoHistoricoDeEnvioForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.data_operacao = datetime.datetime.now()
        o.situacao = ProjetoHistoricoDeEnvio.DEVOLVIDO
        o.operador = request.user.get_relacionamento()
        o.vinculo_operador = request.user.get_vinculo()
        o.save()
        projeto.data_conclusao_planejamento = None
        projeto.save()
        responsavel = Participacao.objects.get(projeto__id=projeto_id, responsavel=True)
        titulo = '[SUAP] Devolução de Projeto'
        texto = (
            f"<h1>Ensino</h1><h2>Devolução de Projeto</h2><p>O Projeto '{projeto.titulo}' foi devolvido pelo Coordenador de Projetos de Ensino.</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])
        return httprr('.', 'Devolução do projeto registrada com sucesso.')

    else:
        form = ProjetoHistoricoDeEnvioForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def plano_trabalho_participante(request: HttpRequest, projeto_id: int, participacao_id: int) -> dict:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    participante = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
    if not participante.pode_emitir_plano_de_trabalho():
        raise PermissionDenied
    eh_coordenador = projeto.is_coordenador(request.user)
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
    descricao_plano = []
    metas = projeto.get_metas()
    for meta in metas:
        etapas = meta.etapa_set.filter(integrantes__in=[participante.id]).order_by('ordem')
        if etapas:
            descricao_plano.extend(etapas)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def ver_plano_trabalho(request: HttpRequest, projeto_id: int, participacao_id: int) -> dict:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    participante = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
    if not participante.pode_emitir_plano_de_trabalho():
        raise PermissionDenied
    title = f'Plano de Trabalho - {participante}'
    eh_coordenador = projeto.is_coordenador(request.user)
    descricao_plano = []
    metas = projeto.get_metas()
    for meta in metas:
        etapas = meta.etapa_set.filter(integrantes__in=[participante.id]).order_by('ordem')
        if etapas:
            descricao_plano.extend(etapas)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_gerenciar_edital')
def reabrir_projeto(request, projeto_id):
    historico = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto_id).order_by('data_operacao')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Reabertura do Projeto: {projeto.titulo}'
    form = ProjetoHistoricoDeEnvioForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.situacao = ProjetoHistoricoDeEnvio.REBAERTO
        o.data_operacao = datetime.datetime.now()
        o.operador = request.user.get_relacionamento()
        o.vinculo_operador = request.user.get_vinculo()
        o.save()
        projeto.data_finalizacao_conclusao = None
        projeto.save()
        if RegistroConclusaoProjeto.objects.filter(projeto=projeto).exists():
            registro_conclusao = RegistroConclusaoProjeto.objects.get(projeto=projeto)
            registro_conclusao.aprovado = False
            registro_conclusao.dt_avaliacao = None
            registro_conclusao.save()

        responsavel = Participacao.objects.get(projeto__id=projeto_id, responsavel=True)
        titulo = '[SUAP] Reabetura de Projeto'
        texto = (
            '<h1>Ensino</h1>'
            '<h2>Reabetura de Projeto</h2>'
            f"<p>O Projeto '{projeto.titulo}' foi reaberto pelo Gerente Sistêmico de Projetos de Ensino.</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])
        return httprr('..', 'Reabertura do projeto realizada com sucesso.')

    else:
        form = ProjetoHistoricoDeEnvioForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_licao_aprendida(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Adicionar Lição Aprendida'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    licao = None
    if request.method == 'GET' and 'deletar_licao' in request.GET:
        get_object_or_404(LicaoAprendida, pk=request.GET['deletar_licao'], projeto=projeto).delete()
        return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=licoes_aprendidas', 'Lição excluída com sucesso.')

    if 'editar_licao' in request.GET:
        licao = get_object_or_404(LicaoAprendida, pk=request.GET['editar_licao'], projeto=projeto)
    if request.method == 'POST':
        form = LicaoAprendidaForm(data=request.POST, instance=licao)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            o.save()
            return httprr('..', 'Lição adicionada com sucesso.')
    else:
        if licao:
            form = LicaoAprendidaForm(instance=licao)
        else:
            form = LicaoAprendidaForm()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def relatorio_licoes_aprendidas(request):
    title = 'Relatório de Lições Aprendidas'
    achou_licoes = False
    buscou_area = False
    form = RelatorioLicoesAprendidasForm(request.GET or None, request=request)
    if form.is_valid():
        area = form.cleaned_data.get('area')
        edital = form.cleaned_data.get('edital')
        campus = form.cleaned_data.get('campus')
        if request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino']):
            licoes = LicaoAprendida.objects.filter(projeto__uo=get_uo(request.user)).order_by('-projeto')
        elif request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']):
            licoes = LicaoAprendida.objects.filter(projeto__uo__in=CampusAdicional.get_campi_user(request.user)).order_by('-projeto')
        else:
            licoes = LicaoAprendida.objects.all().order_by('-projeto')
        if area:
            licoes = licoes.filter(area_licao_aprendida=area)
            buscou_area = True
        else:
            area = 'Todas as Áreas de Conhecimento'

        if edital:
            licoes = licoes.filter(projeto__edital=edital)

        if campus:
            licoes = licoes.filter(projeto__uo=campus)

        if licoes:
            achou_licoes = True

        if 'xls' in request.GET:
            return tasks.relatorio_licoes_aprendidas_to_xls(licoes)

    return locals()


@permission_required('projetos_ensino.pode_avaliar_projeto')
def excluir_avaliacao(resquest, avaliacao_id):
    avaliacao_deletada = get_object_or_404(Avaliacao, pk=avaliacao_id)
    projeto = avaliacao_deletada.projeto
    avaliacao_deletada.delete()
    return httprr(f'/projetos_ensino/projeto/{projeto.pk}/?tab=dados_selecao', 'Avaliação removida com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def lista_email_coordenadores(request):
    title = 'Lista de Emails dos Coordenadores'
    form = EmailCoordenadoresForm(data=request.POST or None, request=request)
    if form.is_valid():
        hoje = datetime.datetime.now()
        emails = ''
        edital = form.cleaned_data['edital']
        situacao = form.cleaned_data['situacao']
        if situacao == EmailCoordenadoresForm.PROJETOS_EM_EDICAO:
            titulo_box = 'em Edição'
            title = 'Lista de Email dos Coordenadores - Projetos em Edição'
            projetos = Projeto.objects.filter(edital=edital)
            projetos = projetos.filter(data_conclusao_planejamento__isnull=True, edital__fim_inscricoes__gte=hoje)

        elif situacao == EmailCoordenadoresForm.PROJETOS_ENVIADOS:
            titulo_box = 'Enviados'
            title = 'Lista de Email dos Coordenadores - Projetos Inscritos'
            projetos = Projeto.objects.filter(edital=edital)
            projetos = projetos.filter(
                Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
            )

        elif situacao == EmailCoordenadoresForm.PROJETOS_PRE_SELECIONADOS:
            titulo_box = 'Pré-Selecionados'
            title = 'Lista de Email dos Coordenadores - Projetos Pré-Selecionados'
            projetos = Projeto.objects.filter(edital=edital)
            projetos = projetos.filter(pre_aprovado=True, data_pre_avaliacao__isnull=False)

        elif situacao == EmailCoordenadoresForm.PROJETOS_EM_EXECUCAO:
            titulo_box = 'em Execução'
            title = 'Lista de Email dos Coordenadores - Projetos em Execução'
            projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
            projetos = (
                Projeto.objects.filter(edital=edital, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True)
                .exclude(id__in=projetos_cancelados)
                .distinct()
            )

        elif situacao == EmailCoordenadoresForm.PROJETOS_EM_ATRASO:
            titulo_box = 'em Atraso'
            title = 'Lista de Email dos Coordenadores - Projetos em Atraso'
            projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
            projetos = (
                Projeto.objects.filter(
                    edital=edital, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, fim_execucao__lt=hoje.date()
                )
                .exclude(id__in=projetos_cancelados)
                .distinct()
            )

        elif situacao == EmailCoordenadoresForm.PROJETOS_CONCLUIDOS:
            titulo_box = 'Concluídos'
            title = 'Lista de Email dos Coordenadores - Concluídos'
            projetos = Projeto.objects.filter(edital=edital, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=False).distinct()

        if request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino']):
            projetos = projetos.filter(uo=get_uo(request.user))
        if request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']):
            projetos = projetos.filter(uo__in=CampusAdicional.get_campi_user(request.user))

        for contador, projeto in enumerate(projetos, 1):
            emails = emails + projeto.vinculo_coordenador.email_notificacao + ';'
            if contador % 10:
                emails = emails + '\n'

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def listar_equipes_dos_projetos(request):
    title = 'Lista de Equipes dos Projetos'
    form = EquipeProjetoForm(data=request.GET or None, request=request)
    tipo_exibicao = 0  # Detalhado
    dados_do_projeto = []
    participacoes = None
    if request.GET:
        if request.GET.getlist('pessoa').count('') == 1:
            return httprr('/projetos_ensino/listar_equipes_dos_projetos/', 'Nenhum projeto encontrado para a pessoa informada.', tag='error')

        if not request.user.groups.filter(name__in=['Gerente Sistêmico de Projetos de Ensino', 'Visualizador de Projetos de Ensino']):
            projetos = Projeto.objects.filter(aprovado=True, uo=get_uo(request.user))
        else:
            projetos = Projeto.objects.filter(aprovado=True)

        ano = request.GET.get('ano')
        if ano:
            projetos = projetos.filter(edital__inicio_inscricoes__year=ano)

        if request.GET.get('edital'):
            projetos = projetos.filter(edital=request.GET.get('edital'))

        if request.GET.get('campus'):
            projetos = projetos.filter(uo=request.GET.get('campus'))

        if request.GET.get('pessoa'):
            participacoes = Participacao.objects.filter(vinculo_pessoa=request.GET.get('pessoa'), projeto__aprovado=True, projeto__in=projetos)
            projetos = projetos.filter(participacao__in=participacoes)

        situacao = int(request.GET.get('situacao', 0))
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
        if situacao == 1:
            projetos = projetos.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False).exclude(id__in=projetos_cancelados)

        elif situacao == 2:
            projetos = projetos.filter(registroconclusaoprojeto__dt_avaliacao__isnull=True).exclude(id__in=projetos_cancelados)

        tipo_exibicao = int(request.GET.get('tipo_de_exibicao', 0))
        if not participacoes:
            participacoes = Participacao.objects.filter(projeto__in=projetos, ativo=True).order_by('projeto__titulo', 'vinculo_pessoa__pessoa__nome')
        else:
            participacoes = participacoes.filter(ativo=True).order_by('projeto__titulo', 'vinculo_pessoa__pessoa__nome')
        dados_do_projeto = get_lista_de_equipes(participacoes)
        if 'xls' in request.GET:
            return tasks.listar_equipes_dos_projetos_to_xls(dados_do_projeto)

    return locals()


def get_lista_de_equipes(participacoes):
    lista = []
    pessoa_id_anterior = 0
    for participacao in participacoes:
        em_duplicidade = False
        if participacao.vinculo_pessoa and pessoa_id_anterior == participacao.vinculo_pessoa.id:
            em_duplicidade = True
            lista[-1]['em_duplicidade'] = True

        participante = participacao.get_participante()
        matricula = participacao.get_identificador()
        if participacao.ativo:
            ativo = 'Sim'
        else:
            ativo = 'Não'
        titulacao = participacao.get_titulacao()
        curso = ''
        lattes = ''
        if participacao.vinculo_pessoa and not participacao.vinculo_pessoa.eh_aluno():
            if participante:
                nome = participante.nome
            else:
                nome = ''
            lattes = ''
        else:
            nome = participacao.get_nome()
            if participante:
                lattes = participante.pessoa_fisica.lattes
                curso = participante.curso_campus
        if participacao.responsavel:
            vinculo = 'Coordenador'
        else:
            vinculo = 'Membro'
        if participacao.vinculo == 'Bolsista' and participacao.bolsa_concedida:
            vinculo = vinculo + ' Bolsista'
        else:
            vinculo = vinculo + ' Não Bolsista'
        agencia = '-'
        banco = '-'
        conta = '-'
        if participacao.instituicao:
            agencia = participacao.numero_agencia
            banco = participacao.instituicao
            op = ' (Operação: ' + participacao.operacao + ') - ' if participacao.operacao else ' - '
            conta = participacao.numero_conta + op + participacao.tipo_conta
        item = {
            'idprojeto': participacao.projeto.id,
            'projeto': participacao.projeto.titulo,
            'nome': nome,
            'lattes': lattes,
            'matricula': matricula,
            'vinculo': vinculo,
            'ativo': ativo,
            'titulacao': titulacao,
            'curso': curso,
            'edital': participacao.projeto.edital.titulo,
            'campus': participacao.projeto.uo.sigla,
            'ehcoordenador': participacao.responsavel,
            'em_duplicidade': em_duplicidade,
            'banco': banco,
            'agencia': agencia,
            'conta': conta,
        }
        lista.append(item)
        pessoa_id_anterior = participacao.vinculo_pessoa and participacao.vinculo_pessoa.id

    return lista


@documento('Projetos de Ensino', enumerar_paginas=False, validade=360)
@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def emitir_certificado_participacao_pdf(request, pk):
    participacao = get_object_or_404(Participacao, pk=pk)

    if not participacao.pode_emitir_certificado_de_participacao():
        return httprr('/', 'Você não tem permissão para este acesso.', 'error')
    else:
        hoje = datetime.datetime.now()
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
        mes = meses[hoje.month - 1]
        title = str(participacao.projeto)
        movimentacao = HistoricoEquipe.objects.filter(participante=pk).order_by('id')
        if movimentacao:
            fim_projeto = participacao.projeto.fim_execucao
            inicio_projeto = participacao.projeto.inicio_execucao
            como_coordenador = (
                movimentacao.filter(categoria=HistoricoEquipe.COORDENADOR, data_movimentacao_saida__gt=F('data_movimentacao'))
                .exclude(data_movimentacao__gt=fim_projeto)
                .exclude(data_movimentacao_saida__lt=inicio_projeto)
                .exclude(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)
            )
            como_membro = (
                movimentacao.filter(categoria=HistoricoEquipe.MEMBRO, data_movimentacao_saida__gt=F('data_movimentacao'))
                .exclude(data_movimentacao__gt=fim_projeto)
                .exclude(data_movimentacao_saida__lt=inicio_projeto)
                .exclude(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)
            )

            if como_coordenador.exists() or como_membro.exists():
                return locals()
            else:
                return httprr(
                    f'/projetos_ensino/projeto/{participacao.projeto.id}/',
                    'Este participante não possui nenhum vínculo passível de emissão de certificado.',
                    'error',
                )

        else:
            return httprr(f'/projetos_ensino/projeto/{participacao.projeto.id}/', 'Não existe movimentação para este participante.', 'error')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def cancelar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_cancelar_projeto():
        raise PermissionDenied
    title = 'Cancelar Projeto'
    form = CancelarProjetoForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.data_solicitacao = datetime.datetime.now()
        o.save()
        return httprr('..', 'Solicitação encaminhada para análise.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def solicitacoes_de_cancelamento(request):
    title = 'Projetos com Solicitações de Cancelamento'
    if request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
        projetos_cancelados = ProjetoCancelado.objects.all()

    else:
        projetos_cancelados = ProjetoCancelado.objects.filter(projeto__uo=get_uo(request.user))

    ano = request.GET.get('ano')
    form = SolicitoesCancelamentoForm(request.GET or None, request=request, ano=ano)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            projetos_cancelados = projetos_cancelados.filter(projeto__edital__inicio_inscricoes__year=form.cleaned_data['ano'])
        if form.cleaned_data.get('edital'):
            projetos_cancelados = projetos_cancelados.filter(projeto__edital=form.cleaned_data['edital'])

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def avaliar_cancelamento_projeto(request: HttpRequest, cancelamento_id: int) -> dict | HttpResponse:
    pedido_cancelamento = get_object_or_404(ProjetoCancelado, pk=cancelamento_id)
    # mesmo recorte da lista (`solicitacoes_de_cancelamento`): fora do gerente sistêmico, só o pedido do próprio campus (#17520)
    if not request.user.has_group_cached('Gerente Sistêmico de Projetos de Ensino') and pedido_cancelamento.projeto.uo != get_uo(request.user):
        raise PermissionDenied
    edicao = False
    if pedido_cancelamento.data_avaliacao:
        edicao = True
    title = 'Avaliar Cancelamento do Projeto'
    eh_continuo = False
    if pedido_cancelamento.projeto.edital.tipo_edital == Edital.ENSINO_CONTINUO:
        eh_continuo = True
    form = AvaliarCancelamentoProjetoForm(request.POST or None, instance=pedido_cancelamento, eh_continuo=eh_continuo)
    if form.is_valid():
        o = form.save(False)
        o.projeto = pedido_cancelamento.projeto
        o.data_avaliacao = datetime.datetime.now()
        o.avaliador = request.user.get_relacionamento()
        o.save()

        if o.cancelado is True:
            if not edicao:
                participantes = Participacao.ativos.filter(projeto=pedido_cancelamento.projeto, vinculo='Bolsista')
                for participante in participantes:
                    if not participante.is_servidor():
                        participante.gerencia_bolsa_ae()

            if form.cleaned_data.get('aprova_proximo') and form.cleaned_data['aprova_proximo'] is True:
                if pedido_cancelamento.projeto.edital.forma_selecao == Edital.GERAL:
                    proximo_projeto = Projeto.objects.filter(edital=pedido_cancelamento.projeto.edital, aprovado=False).order_by('classificacao')
                elif pedido_cancelamento.projeto.edital.forma_selecao == Edital.TEMA:
                    proximo_projeto = Projeto.objects.filter(
                        edital=pedido_cancelamento.projeto.edital, eixo_tematico=pedido_cancelamento.projeto.eixo_tematico, aprovado=False
                    ).order_by('classificacao')
                else:
                    proximo_projeto = Projeto.objects.filter(
                        edital=pedido_cancelamento.projeto.edital, uo=pedido_cancelamento.projeto.uo, aprovado=False
                    ).order_by('classificacao')

                if proximo_projeto.exists() and o.proximo_projeto is None:
                    o.proximo_projeto = proximo_projeto[0]
                    o.save()
                    projeto = proximo_projeto[0]
                    projeto.aprovado = True
                    projeto.save()
                    responsavel = Participacao.objects.get(projeto__id=projeto.id, responsavel=True)
                    titulo = '[SUAP] Aprovação de Projeto'
                    texto = (
                        '<h1>Ensino</h1>'
                        '<h2>Aprovação de Projeto</h2>'
                        f"<p>O projeto '{projeto.titulo}' foi aprovado em decorrência de uma desistência.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])

        return httprr('/projetos_ensino/solicitacoes_de_cancelamento/', 'Cancelamento avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def indicar_pre_avaliador(request):
    editais = Edital.objects.em_periodo_indicar_pre_avaliador()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def selecionar_pre_avaliador_do_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital') and projeto.uo != get_uo(request.user):
        return httprr('..', 'Permissão negada.', tag='error')
    title = 'Indicar Pré-Avaliador'
    form = SelecionarPreAvaliadorForm(request.POST or None, campus=projeto.uo)
    if form.is_valid():
        usuario = form.cleaned_data['user']
        if projeto.participacao_set.filter(vinculo_pessoa=usuario).exists():
            return httprr('..', 'A pessoa escolhida é membro do projeto.', tag='error')
        projeto.vinculo_autor_pre_avaliacao = usuario
        projeto.save()
        return httprr('..', 'Pré-avaliador cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def selecionar_pre_avaliador(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Selecionar Pré-Avaliadores - {edital.titulo}'
    pids = UsuarioGrupo.objects.filter(group__name='Coordenador de Projetos de Ensino').values_list('user__id', flat=True)
    participacoes = Participacao.objects.filter(vinculo_pessoa__user__in=pids, projeto__edital=edital)
    projetos = Projeto.objects.filter(
        edital=edital,
        data_conclusao_planejamento__isnull=False,
        id__in=participacoes.values_list('projeto', flat=True),
        vinculo_autor_pre_avaliacao__isnull=True,
    ).order_by('titulo')
    em_conflito = True
    form = IndicarPreAvaliadorForm(request.GET or None, request=request)
    if form.is_valid():
        status_avaliacao = form.cleaned_data['status_avaliacao']
        palavra_chave = form.cleaned_data['palavra_chave']
        uo = form.cleaned_data['uo']

        if status_avaliacao:
            if int(status_avaliacao) == 0:
                em_conflito = False
                projetos = Projeto.objects.filter(edital=edital, data_conclusao_planejamento__isnull=False).order_by('titulo')
            elif int(status_avaliacao) == 2:
                em_conflito = False
                projetos = Projeto.objects.filter(edital=edital, data_conclusao_planejamento__isnull=False, vinculo_monitor__isnull=True).order_by(
                    'titulo'
                )
        if uo:
            projetos = projetos.filter(uo__id=uo.id)

        if palavra_chave:
            projetos = projetos.filter(vinculo_autor_pre_avaliacao__pessoa__nome__icontains=palavra_chave)

    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
        projetos = projetos.filter(uo=get_uo(request.user))

    return locals()


@rtr()
@permission_required('projetos_ensino.add_comissaoedital')
def editais_para_avaliacao(request):
    title = 'Editais em Avaliação'
    hoje = datetime.datetime.now()
    editais = Edital.objects.filter(divulgacao_selecao__gt=hoje).exclude(tipo_edital=Edital.ENSINO_CONTINUO)
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
        editais = editais.filter(id__in=OfertaProjeto.objects.filter(uo=get_uo(request.user)).values_list('edital', flat=True))

    return locals()


@rtr()
@permission_required('projetos_ensino.add_comissaoedital')
def selecionar_avaliadores(request, edital_id):
    edital = Edital.objects.get(pk=edital_id)
    if not edital_ofertado_ao_usuario(request.user, edital):
        raise PermissionDenied
    title = f'Selecionar avaliadores dos Projetos do {edital.titulo}'

    projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('titulo')
    form = IndicarAvaliadorForm(request.POST or None)
    if form.is_valid():
        status_avaliacao = form.cleaned_data['status_avaliacao']
        palavra_chave = form.cleaned_data['palavra_chave']
        uo = form.cleaned_data['uo']
        if status_avaliacao:
            if int(status_avaliacao) == 1:  # avaliados
                projetos = projetos.filter(avaliacao__isnull=False).distinct()
            elif int(status_avaliacao) == 2:  # não avaliados
                projetos = projetos.filter(avaliacao__isnull=True).distinct()
            elif int(status_avaliacao) == 3:  # parcialmente avaliados
                ids = []
                for projeto in projetos:
                    tem_avaliacao_realizada = nao_tem_avaliacao_realizada = False
                    ids_avaliadores = AvaliadorIndicado.objects.filter(projeto=projeto).values_list('vinculo', flat=True)
                    for id in ids_avaliadores:
                        if not tem_avaliacao_realizada:
                            tem_avaliacao_realizada = Avaliacao.objects.filter(projeto=projeto, vinculo=id).exists()
                        if not nao_tem_avaliacao_realizada:
                            nao_tem_avaliacao_realizada = not Avaliacao.objects.filter(projeto=projeto, vinculo=id).exists()

                    if tem_avaliacao_realizada and nao_tem_avaliacao_realizada:
                        ids.append(projeto.id)

                projetos = projetos.filter(id__in=ids)
            elif int(status_avaliacao) == 4:  # avaliações com divergência maior que 20 pontos
                ids = []
                for projeto in projetos:
                    avaliacoes = Avaliacao.objects.filter(projeto=projeto).order_by('pontuacao')
                    if avaliacoes.count() >= 2:
                        menor_pontuacao = avaliacoes[0].pontuacao
                        limite_divergencia = menor_pontuacao + 20
                        if avaliacoes.filter(pontuacao__gte=limite_divergencia).exists():
                            ids.append(projeto.id)
                projetos = projetos.filter(id__in=ids)

        if uo:
            projetos = projetos.filter(uo__id=uo.id)
        if palavra_chave:
            projetos = projetos.filter(avaliadorindicado__vinculo__pessoa__nome__icontains=palavra_chave)

    return locals()


def edital_ofertado_ao_usuario(user: User, edital: Edital) -> bool:
    """Quem não gerencia o edital só indica avaliadores em edital com oferta no próprio campus (#17550)."""
    return user.has_perm('projetos_ensino.pode_gerenciar_edital') or OfertaProjeto.objects.filter(edital=edital, uo=get_uo(user)).exists()


@rtr()
@permission_required('projetos_ensino.add_comissaoedital')
def selecionar_avaliadores_do_projeto(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not edital_ofertado_ao_usuario(request.user, projeto.edital):
        raise PermissionDenied
    title = f'Indicar Avaliadores do Projeto {projeto.titulo}'
    form = IndicarAvaliadoresForm(request.POST or None, projeto=projeto)
    avaliadores_cadastrados = AvaliadorIndicado.objects.filter(projeto=projeto)
    if form.is_valid():
        grupo = Group.objects.get(name='Avaliador de Projetos de Ensino')
        for avaliador in avaliadores_cadastrados:
            if avaliador.vinculo not in form.cleaned_data['avaliadores']:
                avaliador.delete()
                if not AvaliadorIndicado.objects.filter(vinculo=avaliador.vinculo).exists():
                    avaliador.vinculo.user.groups.remove(grupo)
        for avaliador in form.cleaned_data['avaliadores']:
            if avaliador.id not in avaliadores_cadastrados.values_list('vinculo', flat=True):
                novo_avaliador = AvaliadorIndicado()
                novo_avaliador.pessoa_fisica = avaliador.user.get_profile()
                novo_avaliador.vinculo = avaliador
                novo_avaliador.projeto = projeto
                novo_avaliador.save()
                novo_avaliador.vinculo.user.groups.add(grupo)

                titulo = '[SUAP] Avaliação de Projeto de Ensino'
                texto = (
                    '<h1>Ensino</h1>'
                    '<h2>Avaliação de Projeto</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de ensino: {novo_avaliador.projeto.titulo}.</p>'
                    f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos_ensino/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos_ensino/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(projeto.edital.fim_selecao)}</strong>.</p>'
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [avaliador])

        return httprr('..', 'Avaliadores cadastrados com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_gerenciar_edital')
def lista_emails_comissao(request, comissao_id):
    comissao = get_object_or_404(ComissaoEdital, pk=comissao_id)
    title = f'Lista de Emails - {comissao}'

    emails = ''
    emails_avaliador = ''
    contador_avaliador = 0

    for contador, membro in enumerate(comissao.vinculos_membros.all(), 1):
        emails = emails + membro.email_notificacao + ';'
        if AvaliadorIndicado.objects.filter(vinculo=membro).exists():
            emails_avaliador = emails_avaliador + membro.email_notificacao + ';'
            contador_avaliador = contador_avaliador + 1
        if contador % 10:
            emails = emails + '\n'
        if contador_avaliador % 10:
            emails_avaliador = emails_avaliador + '\n'

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_projeto')
def emitir_declaracao_avaliador(request):
    title = 'Declarações'
    from django.db.models import Count

    projetos_avaliados = (
        Avaliacao.objects.filter(vinculo=request.user.get_vinculo())
        .values('projeto__edital__titulo', 'projeto__edital')
        .annotate(total=Count('projeto'))
        .order_by('-projeto__edital')
    )
    dados = []
    for projeto in projetos_avaliados:
        dados.append([projeto['projeto__edital'], projeto['projeto__edital__titulo'], projeto['total'], request.user.get_vinculo().id])

    return locals()


@documento('Projetos de Ensino', enumerar_paginas=False, validade=360)
@rtr()
@permission_required('projetos_ensino.pode_avaliar_projeto')
def emitir_declaracao_avaliador_pdf(request: HttpRequest, pk: int, edital_id: int, qtd: int) -> dict:
    edital = get_object_or_404(Edital, pk=edital_id)
    pessoa = request.user.get_vinculo().pessoa.nome
    hoje = datetime.datetime.now()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
    meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    mes = meses[hoje.month - 1]
    ano = edital.inicio_inscricoes.year
    data_inicio = edital.inicio_selecao.strftime('%d/%m/%Y')
    data_termino = edital.fim_selecao.strftime('%d/%m/%Y')
    from django.db.models import Count

    registros = Avaliacao.objects.filter(projeto__edital=edital, vinculo=request.user.get_vinculo())
    if not registros.exists():
        raise PermissionDenied
    cidade = 'Natal'
    if registros.exists():
        cidade = registros[0].projeto.uo.municipio.nome
    projetos_avaliados = registros.values('projeto__eixo_tematico', 'projeto__eixo_tematico__descricao').annotate(
        total=Count('projeto__eixo_tematico')
    )
    dados = []
    for projeto in projetos_avaliados:
        dados.append([projeto['projeto__eixo_tematico__descricao'], projeto['total']])

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def gerenciar_monitores(request):
    title = 'Gerenciar Monitores'
    editais = Edital.objects.all().order_by('-inicio_inscricoes')
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
        editais = editais.filter(id__in=OfertaProjeto.objects.filter(uo=get_uo(request.user)).values_list('edital', flat=True))
    form = AnoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            editais = editais.filter(inicio_inscricoes__year=form.cleaned_data.get('ano'))

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def selecionar_monitor(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital') and edital.id not in OfertaProjeto.objects.filter(
        uo=get_uo(request.user)
    ).values_list('edital', flat=True):
        raise PermissionDenied
    title = f'Selecionar Monitores - {edital.titulo}'
    participacoes = Participacao.objects.filter(projeto__edital=edital, projeto__vinculo_monitor__id=F('vinculo_pessoa__id'), projeto__aprovado=True)
    projetos = Projeto.objects.filter(
        registroconclusaoprojeto__dt_avaliacao__isnull=True, id__in=participacoes.values_list('projeto', flat=True)
    ).order_by('titulo')

    form = IndicarPreAvaliadorForm(request.GET or None, request=request)
    em_conflito = True
    if form.is_valid():
        status_avaliacao = form.cleaned_data.get('status_avaliacao')
        palavra_chave = form.cleaned_data.get('palavra_chave')
        uo = form.cleaned_data.get('uo')
        area_tematica = form.cleaned_data.get('area_tematica')

        if status_avaliacao:
            if int(status_avaliacao) == 1:
                participacoes = Participacao.objects.filter(projeto__vinculo_monitor__id=F('vinculo_pessoa__id'), projeto__aprovado=True)
                projetos = projetos.filter(id__in=participacoes.values_list('projeto', flat=True)).order_by('titulo')

            elif int(status_avaliacao) == 2:
                em_conflito = False
                projetos = Projeto.objects.filter(registroconclusaoprojeto__dt_avaliacao__isnull=True, vinculo_monitor__isnull=True, edital=edital)

            else:
                em_conflito = False
                projetos = Projeto.objects.filter(edital=edital, aprovado=True).order_by('titulo')

        if uo:
            projetos = projetos.filter(uo__id=uo.id)

        if palavra_chave:
            projetos = projetos.filter(vinculo_monitor__pessoa__nome__icontains=palavra_chave)

        if area_tematica:
            projetos = projetos.filter(area_tematica=area_tematica)

    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
        projetos = projetos.filter(uo=get_uo(request.user))
    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def selecionar_monitor_do_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital') and projeto.uo != get_uo(request.user):
        return httprr('..', 'Permissão negada.', tag='error')
    title = 'Indicar Monitor'
    grupo = Group.objects.get(name='Monitor de Projetos de Ensino')
    form = AdicionarUsuarioGrupoForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            projeto.vinculo_monitor = usuario.get_vinculo()
            usuario.groups.add(grupo)
            projeto.save()
        return httprr('..', 'Monitor cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def recurso_projeto(request: HttpRequest, recurso_id: int) -> dict:
    recurso = get_object_or_404(RecursoProjeto, pk=recurso_id)
    # o mesmo filtro de campus de `solicitacoes_de_recurso`, a lista que oferece o link
    if not request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino').exists() and not (
        recurso.projeto.edital.campus_especifico and recurso.projeto.uo == get_uo(request.user)
    ):
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def enviar_recurso(request, projeto_id):
    title = 'Enviar Recurso'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if not projeto.pode_enviar_recurso():
        raise PermissionDenied

    form = RecursoProjetoForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.data_solicitacao = datetime.datetime.now()
        o.save()
        return httprr(f'/projetos_ensino/projeto/{projeto.id}', 'Recurso encaminhado para análise.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def avaliar_recurso_projeto(request, recurso_id):
    recurso = get_object_or_404(RecursoProjeto, pk=recurso_id)
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital') and (
        not recurso.projeto.edital.campus_especifico or (recurso.projeto.edital.campus_especifico and not recurso.projeto.uo == get_uo(request.user))
    ):
        raise PermissionDenied
    title = 'Avaliar Recurso'
    form = AvaliarRecursoProjetoForm(request.POST or None, instance=recurso)
    if form.is_valid():
        o = form.save(False)
        o.projeto = recurso.projeto
        o.data_avaliacao = datetime.datetime.now()
        o.avaliador = request.user.get_relacionamento()
        o.save()

        return httprr(f'/projetos_ensino/projeto/{recurso.projeto.id}/?tab=recursos', 'Recurso avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def registro_beneficiario_atendido(request, caracterizacao_id):
    caracterizacao = get_object_or_404(CaracterizacaoBeneficiario, pk=caracterizacao_id)
    title = 'Quantidade de Beneficiários Atendidos'
    form = CaracterizacaoBeneficiarioForm(request.POST or None, instance=caracterizacao, atendida=True)
    if form.is_valid():
        form.save()
        return httprr('..', 'Caracterização registrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_anexo_diverso_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    title = 'Adicionar Anexo ao Projeto'
    if request.POST:
        form = AnexosDiversosProjetoForm(request.POST, request.FILES, projeto=projeto)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            if form.cleaned_data.get('vinculo_membro_equipe') and form.cleaned_data.get('vinculo_membro_equipe').user:
                o.membro_equipe = form.cleaned_data.get('vinculo_membro_equipe').user.get_profile()
            o.save()
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=anexos', 'Anexo cadastrado com sucesso.')
    else:
        participacao = None
        if 'termo_desligamento' in request.GET:
            participacao = get_object_or_404(Participacao, pk=request.GET.get('termo_desligamento'), projeto=projeto)
            title = 'Adicionar Termo de Desligamento do Participante'

        form = AnexosDiversosProjetoForm(request.POST or None, projeto=projeto, participacao=participacao)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def prestacao_contas(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_responsavel = projeto.is_responsavel(request.user)
    if not (
        eh_responsavel
        or projeto.is_gerente_sistemico()
        or request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino', 'Coordenador de Projetos de Ensino'])
        or request.user.get_vinculo() == projeto.vinculo_monitor
    ):
        raise PermissionDenied
    title = f'Prestação de Contas do Projeto "{projeto.titulo}"'
    if projeto.tem_registro_gasto_registrado():
        form = PrestacaoContaForm(request.GET or None, projeto=projeto)
        if form.is_valid():
            if form.cleaned_data['tipo_relatorio'] == '1':
                registros = RegistroGasto.objects.filter(
                    desembolso__projeto=projeto, ano=form.cleaned_data['ano_relatorio'], mes=form.cleaned_data['mes_relatorio']
                )
            else:
                registros = RegistroGasto.objects.filter(desembolso__projeto=projeto).order_by('mes', 'ano')

            if form.cleaned_data.get('despesa'):
                registros = registros.filter(desembolso__despesa=form.cleaned_data.get('despesa'))

            topo = relatorios.get_topo_pdf(title)
            dados = _dados_pdf_prestacao_contas(registros)
            if form.cleaned_data['tipo_relatorio'] == '1':
                periodo = '{}/{}'.format(form.cleaned_data['mes_relatorio'], form.cleaned_data['ano_relatorio'])
                info = [['Tipo do Relatório:', 'Parcial'], ['Período:', periodo], ['Emitido em:', datetime.datetime.now()]]
            else:
                info = [['Tipo do Relatório:', 'Final'], ['Emitido em', datetime.datetime.now()]]
            tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
            tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[12, 10, 60, 80, 10, 18, 18], count=0)
            body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
            if request.GET and 'pdf' in request.GET:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                gastos_com_cadastro = _gastos_com_cadastro_de_arquivo(projeto, registros)
                return locals()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_avaliar_cancelamento_projeto')
def solicitacoes_de_recurso(request):
    title = 'Projetos com Solicitações de Recurso'
    projetos_com_recurso = RecursoProjeto.objects.all()
    if not request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
        projetos_com_recurso = projetos_com_recurso.filter(projeto__edital__campus_especifico=True, projeto__uo=get_uo(request.user))
    ano = request.GET.get('ano')
    form = EditaisForm(request.GET or None, request=request, ano=ano)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            projetos_com_recurso = projetos_com_recurso.filter(projeto__edital__inicio_inscricoes__year=form.cleaned_data.get('ano'))
        if form.cleaned_data.get('edital'):
            projetos_com_recurso = projetos_com_recurso.filter(projeto__edital=form.cleaned_data.get('edital'))

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_termo_cessao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    title = 'Adicionar Termo de Cessão/Doação'
    if projeto.tem_registro_gasto_registrado():
        if request.POST:
            form = TermoCessaoForm(request.POST, request.FILES, projeto=projeto)
            if form.is_valid():
                registro = get_object_or_404(RegistroGasto, pk=form.cleaned_data['registro'].id)
                registro.arquivo_termo_cessao = form.cleaned_data.get('arquivo')
                registro.obs_cessao = form.cleaned_data.get('obs')
                registro.save()
                return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=prestacao_contas', 'Termo cadastrado com sucesso.')
        else:
            form = TermoCessaoForm(request.POST or None, projeto=projeto)
    else:
        return httprr(
            f'/projetos_ensino/projeto/{projeto.id}/?tab=prestacao_contas',
            'O projeto não possui nenhum registro de gasto para ser vinculado ao termo de cessão.',
            tag='error',
        )

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def resultado_edital(request, periodo):
    title = 'Editais com Resultados Disponíveis'
    hoje = datetime.datetime.now()

    if periodo == 1:
        final = True
        editais = Edital.objects.filter(divulgacao_selecao__lt=hoje, tipo_edital=Edital.ENSINO).order_by('-divulgacao_selecao', '-inicio_inscricoes')
    else:
        final = False
        editais = Edital.objects.filter(fim_selecao__lt=hoje, divulgacao_selecao__gt=hoje).order_by('-divulgacao_selecao', '-inicio_inscricoes')
    form = AnoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            ano = int(form.cleaned_data['ano'])
            editais = editais.filter(inicio_inscricoes__year=ano)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def divulgar_resultado_edital(self, edital_id, periodo):
    edital = get_object_or_404(Edital, pk=edital_id)
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
    tabela = {}
    resultado = {}
    final = False
    if periodo == 1:
        final = True
    if periodo == 1 and edital.pode_divulgar_resultado() or periodo == 2 and edital.pode_divulgar_resultado_parcial():
        if edital.forma_selecao == Edital.GERAL:
            projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True).order_by('classificacao', '-pontuacao')
            tabela['Geral'] = []
            for projeto in projetos:
                tabela['Geral'].append(projeto)
        else:
            projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True).order_by('uo__sigla', 'classificacao', '-pontuacao')
            campi = projetos.values('uo__sigla', 'uo__nome').distinct()
            for campus in campi:
                chave = str(campus['uo__nome'])
                tabela[chave] = []

            for projeto in projetos:
                chave = f'{projeto.uo.nome}'
                tabela[chave].append(projeto)

        import collections

        resultado = collections.OrderedDict(sorted(tabela.items()))
        total_aprovados = projetos.exclude(
            id__in=ProjetoCancelado.objects.filter(proximo_projeto__isnull=False).values_list('proximo_projeto__id', flat=True)
        ).count()
    return locals()


@rtr()
@permission_required('projetos_ensino.pode_gerenciar_edital')
def alterar_ficha_avaliacao(request, itemavaliacao_id):
    itemavaliacao = get_object_or_404(ItemAvaliacao, pk=itemavaliacao_id)
    projeto = itemavaliacao.avaliacao.projeto
    tem_permissao(request, projeto)
    title = 'Alterar Pontuação'
    if itemavaliacao.pontuacao_original:
        form = AlteraNotaCriterioProjetoForm(
            request.POST or None, instance=itemavaliacao, initial={'exibe_pontuacao': itemavaliacao.pontuacao_original}
        )
    else:
        form = AlteraNotaCriterioProjetoForm(request.POST or None, instance=itemavaliacao, initial={'exibe_pontuacao': itemavaliacao.pontuacao})

    if form.is_valid():
        o = form.save(False)

        if not o.pontuacao_original:
            o.pontuacao_original = o.pontuacao
        o.pontuacao = form.cleaned_data['nova_pontuacao']
        o.responsavel_alteracao = request.user.get_profile()
        o.vinculo_responsavel_alteracao = request.user.get_vinculo()
        o.data_alteracao = datetime.datetime.now()
        o.save()
        itemavaliacao.avaliacao.save()
        return httprr('..', 'Nota atualizada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def ver_alteracao_ficha_avaliacao(request: HttpRequest, itemavaliacao_id: int) -> dict:
    itemavaliacao = get_object_or_404(ItemAvaliacao, pk=itemavaliacao_id)
    projeto = itemavaliacao.avaliacao.projeto
    if not eh_coordenador_ensino_do_campus(request.user, projeto):
        tem_permissao(request, projeto)
    eh_sistemico = False
    if request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
        eh_sistemico = True

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def upload_outro_anexo(request, anexo_id):
    title = 'Upload de Arquivo'
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    tem_permissao(request, anexo.projeto)
    if not anexo.anexo_edital and not anexo.projeto.eh_somente_leitura():
        form = UploadArquivoForm(request.POST or None, request.FILES or None, instance=anexo)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos_ensino/projeto/{anexo.projeto.id}/?tab=anexos', 'Anexo alterado com sucesso.')
    else:
        return httprr(f'/projetos_ensino/projeto/{anexo.projeto.id}/?tab=anexos', 'Este anexo não pode ser alterado.', tag='error')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def excluir_outro_anexo(request, anexo_id):
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    tem_permissao(request, anexo.projeto)
    if not anexo.anexo_edital and not anexo.projeto.eh_somente_leitura():
        anexo.delete()
        return httprr(f'/projetos_ensino/projeto/{anexo.projeto.id}/?tab=anexos', 'Anexo removido com sucesso.')
    else:
        return httprr(f'/projetos_ensino/projeto/{anexo.projeto.id}/?tab=anexos', 'Anexo não pode ser removido.', tag='error')


@documento('Projetos de Ensino', enumerar_paginas=False, validade=360)
@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def emitir_declaracao_orientacao_pdf(request, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_declaracao_orientacao():
        return httprr('/', 'Você não tem permissão para este acesso.', tag='error')
    else:
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
        hoje = datetime.datetime.now()
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes = meses[hoje.month - 1]

        title = str(participacao.projeto)
        participante = participacao.get_participante()
        nome = participante.nome
        matricula = participante.matricula
        cpf = participante.cpf
        rg = participante.rg
        rg_orgao = participante.rg_orgao
        rg_uf = participante.rg_uf
        vinculo = 'coordenador(a)'

        logradouro = participante.endereco_logradouro
        bairro = participante.endereco_bairro
        cidade = participante.endereco_municipio
        orientacoes = HistoricoOrientacaoProjeto.objects.filter(
            Q(projeto=participacao.projeto), Q(orientador=participacao), Q(data_termino__gt=F('data_inicio')) | Q(data_termino__isnull=True)
        )
        em_execucao = participacao.projeto.get_status() == Projeto.STATUS_EM_EXECUCAO
        if not orientacoes.exists():
            return httprr(f'/projetos_ensino/projeto/{participacao.projeto.id}/?tab=equipe', 'Este participante não orientou nenhum aluno.', 'error')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def lista_email_avaliadores(request):
    title = 'Lista de Emails dos Avaliadores'

    avaliadores_internos = set()
    emails_internos = ''
    for contador, avaliador in enumerate(sorted(avaliadores_internos), 1):
        emails_internos = emails_internos + avaliador + ';'
        if contador % 10:
            emails_internos = emails_internos + '\n'

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def listar_projetos_em_atraso(request):
    title = 'Lista de Projetos em Atraso'
    form = ProjetosAtrasadosForm(request.GET or None, request=request)
    projetos = Projeto.objects.filter(
        pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, projetocancelado__isnull=True, inativado=False
    ).order_by('fim_execucao')
    if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
        projetos = projetos.filter(uo=get_uo(request.user))

    if form.is_valid():
        situacao = form.cleaned_data.get('situacao')
        edital = form.cleaned_data.get('edital')
        ano = form.cleaned_data.get('ano')
        campus = form.cleaned_data.get('campus')
        if campus:
            projetos = projetos.filter(uo=campus)
        if ano:
            projetos = projetos.filter(edital__inicio_inscricoes__year=ano)

        if edital:
            projetos = projetos.filter(edital=edital)

        if situacao:
            hoje = datetime.datetime.now().date()
            if int(situacao) == 1:
                projetos = projetos.filter(fim_execucao__lt=hoje)
            elif int(situacao) == 2:
                etapas_atrasadas = Etapa.objects.filter(fim_execucao__lt=hoje, registroexecucaoetapa__isnull=True)
                projetos = projetos.filter(id__in=etapas_atrasadas.values_list('meta__projeto', flat=True))
            elif int(situacao) == 3:
                etapas_atrasadas = Etapa.objects.filter(fim_execucao__lt=hoje, registroexecucaoetapa__isnull=True)
                projetos = projetos.filter(fim_execucao__gte=hoje).exclude(id__in=etapas_atrasadas.values_list('meta__projeto', flat=True))

        if 'xls' in request.GET:
            return tasks.listar_projetos_em_atraso_export_to_xls(projetos)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def listar_avaliadores_de_projetos(request):
    title = 'Lista de Avaliadores de Projeto'
    form = ListaAvaliadoresProjetosForm(request.GET or None)

    if request.GET:
        avaliadores = AvaliadorIndicado.objects.all().order_by('vinculo__pessoa__nome').distinct('vinculo__pessoa__nome')
        if 'edital' in request.GET and request.GET.get('edital'):
            avaliadores = avaliadores.filter(projeto__edital=request.GET.get('edital'))

        if 'xls' in request.GET:
            return tasks.listar_avaliadores_de_projetos_export_to_xls(avaliadores)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def ver_alteracoes_data(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    registros = HistoricoAlteracaoPeriodoProjeto.objects.filter(projeto=projeto)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def avaliacoes_aluno(request: HttpRequest, participacao_id: int) -> dict:
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if not participacao.pode_ver_avaliacoes():
        raise PermissionDenied
    title = f'Avaliações do Aluno - {participacao}'
    avaliacoes = AvaliacaoAluno.objects.filter(participacao=participacao)
    eh_coordenador = Participacao.objects.filter(projeto=participacao.projeto, vinculo_pessoa=request.user.get_vinculo(), responsavel=True).exists()
    eh_somente_leitura = participacao.projeto.eh_somente_leitura()

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def adicionar_avaliacao_aluno(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    title = f'Avaliar {participacao.vinculo_pessoa.pessoa.nome}'
    if participacao.projeto.eh_somente_leitura() or not participacao.pode_fazer_avaliacoes():
        raise PermissionDenied
    form = CriterioAvaliacaoAlunoForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.participacao = participacao
        o.data_avaliacao = datetime.datetime.now()
        o.avaliado_por = request.user.get_profile()
        o.vinculo_avaliado_por = request.user.get_vinculo()
        o.save()
        ids_valores = str(CriterioAvaliacaoAluno.objects.values_list('id', flat=True))
        for item in request.POST.items():
            if item[1] and item[0] in ids_valores:
                novo_criterio = ItemAvaliacaoAluno()
                novo_criterio.criterio = get_object_or_404(CriterioAvaliacaoAluno, pk=item[0])
                novo_criterio.avaliacao = o
                novo_criterio.pontuacao = item[1]
                novo_criterio.save()

        titulo = '[SUAP] Projeto de Ensino: Registrar Considerações em Avaliação'
        url = f'{settings.SITE_URL}/projetos_ensino/registrar_consideracoes_aluno/{o.id}/'
        texto = (
            '<h1>Projeto de Ensino</h1>'
            '<h2>Registrar Considerações em Avaliação</h2>'
            f"<p>O Coordenador do Projeto '{participacao.projeto.titulo}' registrou a avaliação do seu desempenho. Por favor, acesse o SUAP para registrar suas considerações: {url}</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.vinculo_pessoa])
        return httprr(f'/projetos_ensino/avaliacoes_aluno/{participacao.id}/', 'Avaliação cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def ver_avaliacao_aluno(request: HttpRequest, avaliacao_id: int) -> dict:
    avaliacao = get_object_or_404(AvaliacaoAluno, pk=avaliacao_id)
    if not avaliacao.participacao.pode_ver_avaliacoes():
        raise PermissionDenied
    title = f'Avaliação - {avaliacao.participacao.vinculo_pessoa.pessoa.nome}'
    itens = ItemAvaliacaoAluno.objects.filter(avaliacao=avaliacao)

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_registrar_consideracao_aluno')
def registrar_consideracoes_aluno(request, avaliacao_id):
    avaliacao = get_object_or_404(AvaliacaoAluno, pk=avaliacao_id)
    if (not avaliacao.participacao.vinculo_pessoa == request.user.get_vinculo()) or avaliacao.data_validacao:
        raise PermissionDenied
    itens = ItemAvaliacaoAluno.objects.filter(avaliacao=avaliacao)
    title = f'Avaliação - {avaliacao.participacao.vinculo_pessoa.pessoa.nome}'
    form = ValidarAvaliacaoAlunoForm(request.POST or None, instance=avaliacao)
    if form.is_valid():
        o = form.save(False)
        o.data_validacao = datetime.datetime.now()
        o.save()
        return httprr(f'/projetos_ensino/projeto/{avaliacao.participacao.projeto.id}/?tab=equipe', 'Avaliação validada com sucesso.')

    return locals()


@transaction.atomic
@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def deletar_participante(request, participacao_id):
    url = request.META.get('HTTP_REFERER', '.')
    participante = get_object_or_404(Participacao, pk=participacao_id)
    if not participante.pode_remover_participacao():
        raise PermissionDenied
    if Etapa.objects.filter(meta__projeto=participante.projeto, integrantes__in=[participante.id]).exists():
        return httprr(
            url, 'O participante está vinculado à uma ou mais atividades. Acesse o plano de trabalho do mesmo e faça a desvinculação.', tag='error'
        )
    if Etapa.objects.filter(meta__projeto=participante.projeto, responsavel=participante).exists():
        return httprr(
            url,
            'O participante é responsável por uma ou mais atividades. Acesse a aba Metas/Atividades e altere o responsável pela(s) atividade(s).',
            tag='error',
        )

    if HistoricoOrientacaoProjeto.objects.filter(orientador=participante, data_termino__isnull=True).exists():
        orientacao = HistoricoOrientacaoProjeto.objects.filter(orientador=participante, data_termino__isnull=True).order_by('-id')[0]
        return httprr(url, f'O participante é orientador do discente {orientacao.orientado.get_nome()} e não pode ser removido.', tag='error')
    else:
        ProjetoAnexo.objects.filter(projeto=participante.projeto, vinculo_membro_equipe=participante.vinculo_pessoa).delete()

        participante.delete()
        return httprr(url, 'Participante removido com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_termo_cessao(request, termo_id):
    title = 'Editar Termo de Cessão/Doação'
    termo = get_object_or_404(RegistroGasto, pk=termo_id)
    projeto = termo.desembolso.projeto
    if projeto.pode_editar_inscricao_execucao():
        form = EditarTermoCessaoForm(request.POST or None, request.FILES or None, instance=termo)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=prestacao_contas', 'Termo de Cessão editado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def excluir_termo_cessao(request, termo_id):
    termo = get_object_or_404(RegistroGasto, pk=termo_id)
    projeto = termo.desembolso.projeto
    if projeto.pode_editar_inscricao_execucao():
        termo.arquivo_termo_cessao = None
        termo.obs_cessao = None
        termo.save()
        return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=prestacao_contas', 'Termo de cessão/doação removido com sucesso.')

    raise PermissionDenied


@permission_required('projetos_ensino.pode_interagir_com_projeto')
def filtrar_editais_por_ano(request):
    data = '[]'
    if request.method == 'GET':
        ano = request.GET.get('ano')
        if ano and ano != 'Selecione um ano':
            registro = Edital.objects.filter(inicio_inscricoes__year=ano).order_by('-inicio_inscricoes')
            if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
                registro = registro.filter(id__in=OfertaProjeto.objects.filter(uo=get_uo(request.user)).values_list('edital', flat=True))
            if registro.exists():
                from django.core import serializers

                data = serializers.serialize(
                    'json',
                    list(registro.all()),
                    fields=(
                        'titulo',
                        'id',
                    ),
                )
    return HttpResponse(data, content_type='application/json')


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def indicar_orientador(request: HttpRequest, participacao_id: int) -> dict | HttpResponse:
    title = 'Indicar Orientador'
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.is_servidor():
        return httprr('..', 'O participante não é aluno.', tag='error')
    projeto = participacao.projeto
    tem_permissao_alterar_equipe(request, projeto)
    form = IndicarOrientadorForm(request.POST or None, projeto=projeto, participacao=participacao)
    if form.is_valid():
        participacao.orientador = form.cleaned_data.get('participacao')
        participacao.save()
        if HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_termino__isnull=True).exists():
            finaliza_orientacao = HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_termino__isnull=True)[0]
            finaliza_orientacao.data_termino = form.cleaned_data.get('data_inicio')
            finaliza_orientacao.save()

        novo_historico = HistoricoOrientacaoProjeto()
        novo_historico.projeto = projeto
        novo_historico.orientado = participacao
        novo_historico.orientador = form.cleaned_data.get('participacao')
        novo_historico.data_inicio = form.cleaned_data.get('data_inicio')
        novo_historico.save()

        return httprr('..', 'Orientador alterado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editais(request):
    title = 'Editais'
    editais = Edital.objects.all()
    form = ListaEditaisForm(request.GET or None)
    if form.is_valid():
        ano = form.cleaned_data.get('ano')
        periodo = form.cleaned_data.get('periodo')
        uo = form.cleaned_data.get('uo')
        if ano and ano != 'Selecione um ano':
            editais = editais.filter(inicio_inscricoes__year=ano)
        if uo:
            editais = editais.filter(id__in=OfertaProjeto.objects.filter(uo=uo).values_list('edital_id', flat=True))
        if periodo:
            if periodo == ListaEditaisForm.INSCRICAO:
                editais = editais.em_inscricao()
            elif periodo == ListaEditaisForm.PRE_SELECAO:
                editais = editais.em_pre_avaliacao()
            elif periodo == ListaEditaisForm.SELECAO:
                editais = editais.em_selecao()
            elif periodo == ListaEditaisForm.EXECUCAO:
                editais = editais.em_execucao()
            elif periodo == ListaEditaisForm.CONCLUIDO:
                editais = editais.concluidos()
        editais = editais.order_by('-inicio_inscricoes')

    return locals()


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projetos_em_monitoramento')
def cancelar_avaliacao_etapa(request, registroexecucao_id):
    registro = get_object_or_404(RegistroExecucaoEtapa, pk=registroexecucao_id)
    is_gerente_sistemico = request.user.has_perm('projetos_ensino.pode_gerenciar_edital')
    projeto = registro.etapa.meta.projeto
    pode_validar = (projeto.vinculo_monitor == request.user.get_vinculo()) or is_gerente_sistemico
    if pode_validar and not projeto.eh_somente_leitura():
        registro.justificativa_reprovacao = ''
        registro.dt_avaliacao = None
        registro.avaliador = None
        registro.aprovado = False
        registro.save()
        return httprr(f'/projetos_ensino/validar_execucao_etapa/{projeto.pk}/?tab=metas', 'Avaliação da atividade cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projetos_em_monitoramento')
def cancelar_avaliacao_gasto(request, registrogasto_id):
    registro = get_object_or_404(RegistroGasto, pk=registrogasto_id)
    is_gerente_sistemico = request.user.has_perm('projetos_ensino.pode_gerenciar_edital')
    projeto = registro.desembolso.projeto
    pode_validar = (projeto.vinculo_monitor == request.user.get_vinculo()) or is_gerente_sistemico
    if pode_validar and not projeto.eh_somente_leitura():
        registro.justificativa_reprovacao = None
        registro.dt_avaliacao = None
        registro.avaliador = None
        registro.aprovado = False
        registro.save()
        return httprr(f'/projetos_ensino/validar_execucao_etapa/{projeto.pk}/?tab=gastos', 'Avaliação do gasto cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def desvincular_participante_atividades(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if not participacao.projeto.is_coordenador(request.user):
        raise PermissionDenied
    for etapa in Etapa.objects.filter(integrantes=participacao):
        etapa.integrantes.remove(participacao)
    return httprr(f'/projetos_ensino/projeto/{participacao.projeto.id}/?tab=equipe', 'Participante removido das atividades com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def estatisticas(request):
    projetos = Projeto.objects.all()
    if not request.user.has_perm('projetos_ensino.add_edital'):
        campus_do_usuario = get_uo(request.user)
        projetos = projetos.filter(uo=campus_do_usuario)
        title = f'Indicadores de Projetos de Ensino - Campus {campus_do_usuario}'
    else:
        title = 'Indicadores de Projetos de Ensino'
    ano = request.GET.get('ano')
    form = EstatisticasForm(request.GET or None, ano=ano, request=request)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')

        if ano:
            projetos = projetos.filter(edital__inicio_inscricoes__year=ano)
        if edital:
            projetos = projetos.filter(edital=edital)
        if campus:
            projetos = projetos.filter(uo=campus)
        if form.cleaned_data.get('tipo_edital'):
            if form.cleaned_data.get('tipo_edital') == 'Edital de Campus':
                projetos = projetos.filter(edital__campus_especifico=True)
            elif form.cleaned_data.get('tipo_edital') == 'Edital Sistêmico':
                projetos = projetos.filter(edital__campus_especifico=False)

    hoje = datetime.datetime.now()
    enviados = projetos.filter(
        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
    )
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)
    aprovados = enviados.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje)
    execucao = aprovados.filter(
        pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, edital__divulgacao_selecao__lt=hoje, inativado=False
    ).exclude(id__in=projetos_cancelados)
    concluidos = aprovados.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False)
    cancelados = aprovados.filter(id__in=projetos_cancelados)
    inativados = aprovados.filter(inativado=True)
    dados = []
    dados.append(['Projetos em Execução', execucao.count()])
    dados.append(['Projetos Concluídos', concluidos.count()])
    dados.append(['Projetos Cancelados', cancelados.count()])
    dados.append(['Projetos Inativados', inativados.count()])

    grafico = PieChart(
        'grafico',
        title='Situação Atual dos Projetos Aprovados',
        subtitle='Quantidade de projetos aprovados em execução, concluídos e cancelados',
        minPointLength=0,
        data=dados,
    )

    grafico.id = 'grafico'

    dados2 = []
    for area in EixoTematico.objects.all():
        valor = aprovados.filter(eixo_tematico=area).count()
        if valor:
            dados2.append([area.descricao, valor])

    grafico2 = PieChart(
        'grafico2', title='Projetos por Eixo Temático', subtitle='Quantidade de projetos aprovados por eixo temático', minPointLength=0, data=dados2
    )

    grafico2.id = 'grafico2'

    dados3 = []
    participacoes = Participacao.objects.filter(projeto__in=aprovados.values_list('id')).distinct()
    alunos = Aluno.objects.filter(vinculos__in=participacoes.values_list('vinculo_pessoa', flat=True)).distinct()
    docentes = Servidor.objects.filter(
        ativo=True, vinculos__id__in=participacoes.values_list('vinculo_pessoa', flat=True), eh_docente=True
    ).distinct()
    tecnicos_adm = Servidor.objects.filter(
        ativo=True, vinculos__id__in=participacoes.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
    ).distinct()
    dados3.append(['Discentes', alunos.count()])
    dados3.append(['Docentes', docentes.count()])
    dados3.append(['Técnicos Administrativos', tecnicos_adm.count()])

    grafico3 = PieChart(
        'grafico3',
        title='Participantes por Categoria',
        subtitle='Quantidade de discentes, téc. administrativos e docentes únicos envolvidos nos projetos aprovados',
        minPointLength=0,
        data=dados3,
    )

    grafico3.id = 'grafico3'

    bolsistas = Participacao.objects.filter(vinculo='Bolsista', projeto__in=aprovados.values_list('id')).distinct()
    voluntarios = Participacao.objects.filter(vinculo='Voluntário', projeto__in=aprovados.values_list('id')).distinct()
    alunos_bolsistas = Aluno.objects.filter(vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True)).distinct().count()
    alunos_voluntarios = Aluno.objects.filter(vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True)).distinct().count()
    docentes_bolsistas = (
        Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True), eh_docente=True).distinct().count()
    )
    docentes_voluntarios = (
        Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True), eh_docente=True).distinct().count()
    )
    tecnicos_adm_bolsistas = (
        Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True)
        .distinct()
        .count()
    )
    tecnicos_adm_voluntarios = (
        Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True)
        .distinct()
        .count()
    )

    series2 = []
    serie = ['Discentes']
    serie.append(alunos_bolsistas)
    serie.append(alunos_voluntarios)
    series2.append(serie)

    serie = ['Docentes']
    serie.append(docentes_bolsistas)
    serie.append(docentes_voluntarios)
    series2.append(serie)

    serie = ['Técnicos Administrativos']
    serie.append(tecnicos_adm_bolsistas)
    serie.append(tecnicos_adm_voluntarios)
    series2.append(serie)

    groups = ['Bolsistas', 'Voluntários']

    grafico4 = GroupedColumnChart(
        'grafico4',
        title='Tipo de Vínculo por Categoria',
        subtitle='Quantidade de bolsistas e voluntários por categoria nos projetos aprovados',
        data=series2,
        groups=groups,
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )

    grafico4.id = 'grafico4'

    dados5 = []
    for modalidade in Modalidade.objects.all():
        valor = alunos.filter(curso_campus__modalidade=modalidade).count()
        if valor > 0:
            dados5.append([modalidade.descricao, valor])

    grafico5 = PieChart(
        'grafico5',
        title='Discentes por Modalidade de Ensino',
        subtitle='Quantidade de discentes classificados por modalidade de ensino',
        minPointLength=0,
        data=dados5,
    )

    grafico5.id = 'grafico5'

    pie_chart_lists = [grafico, grafico2, grafico3, grafico4, grafico5]

    return locals()


@rtr()
@permission_required('projetos_ensino.change_projeto')
def inativar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    # if (
    #    usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists() and (get_uo(usuario_logado) == projeto.uo)
    # ) or projeto.is_gerente_sistemico(usuario_logado):
    if (
        usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists()
        and (projeto.uo in CampusAdicional.get_campi_user(usuario_logado))
    ) or projeto.is_gerente_sistemico(usuario_logado):
        title = f'Inativar Projeto - {projeto.titulo}'
        form = InativarProjetoForm(request.POST or None, instance=projeto)
        if form.is_valid():
            o = form.save(False)
            o.inativado = True
            o.inativado_em = datetime.datetime.now()
            o.inativado_por = request.user.get_relacionamento()
            o.save()
            return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Projeto inativado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def clonar_projeto(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Clonar Projeto no Edital: {edital}'
    form = ClonarProjetoForm(request.POST or None, request=request, edital=edital)
    if form.is_valid():
        projeto_clonado = form.processar()
        return httprr(f'/projetos_ensino/projeto/{projeto_clonado.id}/', 'Projeto clonado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def clonar_etapa(request, meta_id):
    title = 'Clonar Atividade'
    meta = get_object_or_404(Meta, pk=meta_id)
    tem_permissao(request, meta.projeto)
    form = ClonarEtapaForm(request.POST or None, projeto=meta.projeto)
    if form.is_valid():
        etapa_escolhida = get_object_or_404(Etapa, pk=form.cleaned_data.get('etapa').id)
        etapa_clonada = get_object_or_404(Etapa, pk=form.cleaned_data.get('etapa').id)
        etapa_clonada.id = None
        etapa_clonada.meta = meta
        ordem = 1
        if Etapa.objects.filter(meta=meta).order_by('-ordem').exists():
            ordem = Etapa.objects.filter(meta=meta).order_by('-ordem')[0].ordem + 1
        etapa_clonada.ordem = ordem
        etapa_clonada.data_cadastro = datetime.date.today()
        etapa_clonada.save()
        etapa_clonada.integrantes.set(etapa_escolhida.integrantes.all())
        etapa_clonada.save()
        return httprr('..', 'Atividade clonada com sucesso.')
    return locals()


@receiver(rh_servidor_view_tab)
def servidor_view_tab_participacoes_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    participacoes_ensino = Participacao.objects.filter(
        vinculo_pessoa__id_relacionamento=servidor.id, vinculo_pessoa__tipo_relacionamento__model='servidor', projeto__aprovado=True
    )

    if participacoes_ensino.exists():
        return render_to_string(
            template_name='projetos_ensino/templates/servidor_view_tab.html',
            context={
                'servidor': servidor,
                'participacoes_ensino': participacoes_ensino,
                'verificacao_propria': verificacao_propria,
            },
            request=request,
        )
    return False


@rtr()
@permission_required('projetos_ensino.pode_gerenciar_edital')
def cancelar_pre_avaliacao_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.pode_cancelar_pre_avaliacao():
        projeto.pre_aprovado = False
        projeto.aprovado = False
        projeto.autor_pre_avaliacao = None
        projeto.autor_avaliacao = None
        projeto.data_pre_avaliacao = None
        projeto.data_avaliacao = None
        projeto.save()
        return httprr(f'/projetos_ensino/projetos_nao_avaliados/{projeto.edital.id}/', 'Pré-avaliação cancelada com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_relatorios_projetos_ensino')
def relatorio_caracterizacao_beneficiarios(request):
    title = 'Relatório de Caracterização de Beneficiários'
    form = RelatorioCaracterizacaoBeneficiariosForm(request.GET or None, request=request)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')
        tipo_beneficiario = form.cleaned_data.get('tipo_beneficiario')
        area_tematica = form.cleaned_data.get('area_tematica')
        situacao = form.cleaned_data.get('situacao')
        tipo_edital = form.cleaned_data.get('tipo_edital')
        if request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino']):
            registros = CaracterizacaoBeneficiario.objects.filter(projeto__uo=get_uo(request.user), projeto__aprovado=True).order_by('-projeto')
        elif request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']):
            registros = CaracterizacaoBeneficiario.objects.filter(
                projeto__uo__in=CampusAdicional.get_campi_user(request.user), projeto__aprovado=True
            ).order_by('-projeto')
        else:
            registros = CaracterizacaoBeneficiario.objects.filter(projeto__aprovado=True).order_by('-projeto')

        if edital:
            registros = registros.filter(projeto__edital=edital)

        if tipo_edital:
            if tipo_edital == 'Edital de Campus':
                registros = registros.filter(projeto__edital__campus_especifico=True)
            elif tipo_edital == 'Edital Sistêmico':
                registros = registros.filter(projeto__edital__campus_especifico=False)

        if campus:
            registros = registros.filter(projeto__uo=campus)

        if ano:
            registros = registros.filter(projeto__edital__inicio_inscricoes__year=ano)

        if area_tematica:
            registros = registros.filter(projeto__area_tematica=area_tematica)

        if tipo_beneficiario:
            registros = registros.filter(tipo_beneficiario=tipo_beneficiario)

        if situacao:
            hoje = datetime.datetime.now()
            if situacao == RelatorioCaracterizacaoBeneficiariosForm.PROJETOS_EM_EXECUCAO:
                registros = registros.filter(
                    projeto__registroconclusaoprojeto__dt_avaliacao__isnull=True,
                    projeto__edital__divulgacao_selecao__lt=hoje,
                    projeto__inativado=False,
                    projeto__projetocancelado__isnull=True,
                )
            elif situacao == RelatorioCaracterizacaoBeneficiariosForm.PROJETOS_CONCLUIDOS:
                registros = registros.filter(projeto__registroconclusaoprojeto__dt_avaliacao__isnull=False)

        total_prevista = registros.aggregate(total=Sum('quantidade'))['total']
        total_atendida = registros.aggregate(total=Sum('quantidade_atendida'))['total']

        if 'xls' in request.GET:
            return tasks.relatorio_caracterizacao_beneficiarios_to_xls(registros)
    return locals()


@documento('Projetos de Ensino', enumerar_paginas=False, validade=360)
@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def emitir_declaracao_participacao_pdf(self: HttpRequest, pk: int) -> dict | HttpResponse:
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_declaracao_de_participacao():
        return httprr('/', 'Você não tem permissão para ver isso.', 'error')
    carga_horaria = participacao.carga_horaria
    participante = participacao.get_participante()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos_ensino', 'nome_proen') or 'Pró-Reitoria de Ensino'
    historico = (
        HistoricoEquipe.objects.filter(participante=participacao)
        .order_by('id')
        .exclude(movimentacao='Ativado')
        .exclude(data_movimentacao_saida__lt=participacao.projeto.inicio_execucao)
    )
    eh_aluno = False
    possui_bolsa = False
    if participacao.vinculo == TipoVinculo.BOLSISTA:
        possui_bolsa = True

    eh_coordenador = False
    if participacao.responsavel:
        eh_coordenador = True

    if participacao.is_servidor():
        nome = participante.nome
        cpf = participante.cpf
        rg = participante.rg
        rg_orgao = participante.rg_orgao
        rg_uf = participante.rg_uf
        if participacao.responsavel:
            vinculo = 'coordenador(a)'
        else:
            vinculo = 'membro'
        logradouro = participante.endereco_logradouro
        bairro = participante.endereco_bairro
        cidade = participante.endereco_municipio

    elif participacao.eh_aluno():  # participante é aluno
        eh_aluno = True
        nome = participacao.get_nome()
        cpf = participante.pessoa_fisica.cpf
        rg = participante.pessoa_fisica.rg
        rg_orgao = participante.pessoa_fisica.rg_orgao
        rg_uf = participante.pessoa_fisica.rg_uf
        logradouro = participante.logradouro
        bairro = participante.bairro
        cidade = participante.cidade
    else:
        nome = participante.nome
        if participante.prestador.cpf:
            cpf = participante.prestador.cpf
            rg = participante.prestador.rg
            rg_orgao = participante.prestador.rg_orgao
            rg_uf = participante.prestador.rg_uf
        else:
            eh_estrangeiro = True
            cpf = participante.prestador.username
        logradouro = participante.prestador.endereco_logradouro
        bairro = participante.prestador.endereco_bairro
        cidade = participante.prestador.endereco_municipio
        vinculo = 'membro'
    if participacao.historicoequipe_set.exists():
        if participacao.historicoequipe_set.first().data_movimentacao > participacao.projeto.inicio_execucao:
            data_inicio_vinculo = participacao.historicoequipe_set.first().data_movimentacao
        else:
            data_inicio_vinculo = participacao.projeto.inicio_execucao

        if not participacao.ativo and participacao.data_inativacao:
            data_fim_vinculo = participacao.data_inativacao
        elif not participacao.ativo and participacao.historicoequipe_set.filter(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE).exists():
            data_fim_vinculo = participacao.historicoequipe_set.filter(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)[
                0
            ].data_movimentacao
        else:
            if participacao.historicoequipe_set.last().data_movimentacao_saida:
                if participacao.historicoequipe_set.last().data_movimentacao_saida < participacao.projeto.fim_execucao:
                    data_fim_vinculo = participacao.historicoequipe_set.last().data_movimentacao_saida
                else:
                    data_fim_vinculo = participacao.projeto.fim_execucao
            else:
                data_fim_vinculo = participacao.projeto.fim_execucao

    else:
        data_inicio_vinculo = participacao.projeto.inicio_execucao
        data_fim_vinculo = participacao.projeto.fim_execucao

    matricula = None
    if participacao.eh_aluno() or participacao.is_servidor():
        matricula = participante.matricula

    hoje = datetime.datetime.now()
    meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    mes = meses[hoje.month - 1]

    return locals()


@rtr()
@permission_required('projetos_ensino.change_projeto')
def reativar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    # if projeto.pode_ser_inativado() and (
    #    (usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists() and (get_uo(usuario_logado) == projeto.uo))
    #    or projeto.is_gerente_sistemico(usuario_logado)
    # ):
    if projeto.pode_ser_inativado() and (
        (
            usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists()
            and (projeto.uo in CampusAdicional.get_campi_user(request.user))
        )
        or projeto.is_gerente_sistemico(usuario_logado)
    ):
        projeto.inativado = False
        projeto.inativado_em = None
        projeto.inativado_por = None
        projeto.save()
        return httprr(f'/projetos_ensino/projeto/{projeto.id}/', 'Projeto reativado com sucesso.')

    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def adicionar_participante_colaborador(request, projeto_id):
    title = 'Adicionar Participante'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = ParticipacaoColaboradorForm(data=request.POST, projeto=projeto)
            form.projeto = projeto
            if form.is_valid():
                participacao = form.save(False)
                participacao.projeto = projeto
                participacao.vinculo = form.cleaned_data.get('vinculo') or TipoVinculo.VOLUNTARIO
                participacao.bolsa_concedida = False
                participacao.pessoa = form.cleaned_data['prestador'].prestador
                participacao.vinculo_pessoa = form.cleaned_data['prestador'].prestador.get_vinculo()
                if Participacao.objects.filter(projeto=participacao.projeto, vinculo_pessoa=participacao.vinculo_pessoa).exists():
                    return httprr('.', 'Este participante já pertence ao projeto.', tag='error')
                participacao.save()
                participacao.adicionar_registro_historico_equipe(
                    HistoricoEquipe.EVENTO_ADICIONAR_COLABORADOR, data_evento=form.cleaned_data.get('data')
                )
                Participacao.gerar_anexos_do_participante(participacao)
                if projeto.edital.exige_termo_colaborador():
                    obj = TrocarSenha.objects.create(username=form.cleaned_data['prestador'].prestador.username)
                    url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
                    titulo = '[SUAP] Projetos de Ensino: Termo de Compromisso do Colaborador Externo'
                    texto = f"""
                        <h1>Projetos de Ensino</h1>
                        <h2>Termo de Compromisso do Colaborador Externo</h2>
                        <p>Você foi cadastrado(a) como membro da equipe do projeto \'{projeto.titulo}\'. Acesse o SUAP para aceitar o termo de compromisso.</p>
                        <p>Caso ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
                        <br />
                        <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf' ('usuário' tem que ser sem pontuação).</p>
                        <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>'
                        """
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('prestador').prestador.get_vinculo()])

                return httprr('..', 'Participante adicionado com sucesso.')
        else:
            form = ParticipacaoColaboradorForm(projeto=projeto)
            form.projeto = projeto

        return locals()
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def editar_participante_colaborador(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        participacao = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
        title = f'Editar Participação: {participacao.get_nome()}'
        form = ParticipacaoColaboradorForm(request.POST or None, instance=participacao, projeto=projeto)
        alterou = False
        if form.is_valid():
            participacao = form.save(False)
            participacao_anterior = Participacao.objects.get(id=participacao.id)
            if (
                form.cleaned_data.get('vinculo') != participacao_anterior.vinculo
                or form.cleaned_data.get('carga_horaria') != participacao_anterior.carga_horaria
            ):
                alterou = True
            participacao.save()
            if alterou:
                participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_EDICAO_COLABORADOR, data_evento=form.cleaned_data.get('data'))
                Participacao.gerar_anexos_do_participante(participacao)
            else:
                historico = HistoricoEquipe.objects.filter(participante=participacao, projeto=projeto).order_by('id')
                if historico.exists():
                    registro = historico[0]
                    registro.data_movimentacao = form.cleaned_data.get('data')
                    registro.save()
            return httprr('..', 'Participante editado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def cadastrar_frequencia(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_participante = projeto.pode_acessar_projeto(request.user)
    title = 'Registrar Frequência/Atividade Diária'
    if eh_participante and not projeto.eh_somente_leitura():
        form = RegistrarFrequenciaForm(request.POST or None)
        if form.is_valid():
            o = form.save(False)
            o.cadastrada_em = datetime.datetime.now()
            o.cadastrada_por = request.user.get_vinculo()
            o.projeto = projeto
            if projeto.is_responsavel(request.user):
                o.validada_em = datetime.datetime.now()
                o.validada_por = request.user.get_vinculo()
            o.save()
            data_fim = form.cleaned_data.get('data_fim')
            if data_fim:
                data_atual = form.cleaned_data.get('data') + relativedelta(days=1)
                while data_atual <= data_fim:
                    novo_registro = RegistroFrequencia()
                    novo_registro.descricao = o.descricao
                    novo_registro.carga_horaria = o.carga_horaria
                    novo_registro.data = data_atual
                    novo_registro.cadastrada_em = o.cadastrada_em
                    novo_registro.cadastrada_por = o.cadastrada_por
                    novo_registro.projeto = projeto
                    if projeto.is_responsavel(request.user):
                        novo_registro.validada_em = o.validada_em
                        novo_registro.validada_por = o.validada_por
                    novo_registro.save()
                    data_atual += relativedelta(days=1)

            return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária cadastrada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_interagir_com_projeto')
def validar_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if registro.projeto.is_responsavel(request.user):
        url_origem = request.META.get('HTTP_REFERER', '.')
        registro.validada_em = datetime.datetime.now()
        registro.validada_por = request.user.get_vinculo()
        registro.save()
        return httprr(url_origem, 'Frequência/Atividade diária validada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def gerar_lista_frequencia(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_participante = projeto.eh_participante(request.user)
    usuario_logado = request.user
    is_gerente_sistemico = projeto.is_gerente_sistemico(usuario_logado)

    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    if usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists():
        mesmo_campus = projeto.uo in CampusAdicional.get_campi_user(request.user)

    is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Projetos de Ensino').exists() and mesmo_campus
    eh_visualizador = usuario_logado.groups.filter(name='Visualizador de Projetos de Ensino').exists()
    eh_coordenador = projeto.is_responsavel(usuario_logado)
    pode_ver_frequencias = eh_coordenador or is_gerente_sistemico or is_pre_avaliador or eh_visualizador
    title = 'Gerar Lista de Frequência/Atividade Diária'
    if eh_participante or pode_ver_frequencias:
        form = GerarListaFrequenciaForm(request.POST or None, projeto=projeto)
        if form.is_valid():
            registros = RegistroFrequencia.objects.filter(projeto=projeto).order_by('data')
            data_inicio = form.cleaned_data.get('data_inicio')
            data_termino = form.cleaned_data.get('data_termino')
            participante = form.cleaned_data.get('participante')
            if data_inicio:
                registros = registros.filter(data__gte=data_inicio)
            if data_termino:
                registros = registros.filter(data__lte=data_termino)
            if participante:
                registros = registros.filter(cadastrada_por=participante)
        return locals()

    else:
        raise PermissionDenied


def validar_ou_cancelar_frequencias(registros: QuerySet[RegistroFrequencia], acao: str, vinculo_usuario: Vinculo, url_origem: str) -> HttpResponse:
    """Valida (``acao == 'Validar'``) ou cancela a validação, em lote, dos registros de frequência informados."""
    if not registros:
        return httprr(url_origem, 'Nenhum registro selecionado.', tag='error')
    if acao == 'Validar':
        for registro in registros.filter(validada_em__isnull=True):
            registro.validada_em = datetime.datetime.now()
            registro.validada_por = vinculo_usuario
            registro.save()
        return httprr(url_origem, 'Registros de Frequência/Atividade diária validados com sucesso.')
    for registro in registros:
        registro.validada_em = None
        registro.validada_por = None
        registro.save()
    return httprr(url_origem, 'Validações dos Registros de Frequência/Atividade diária canceladas com sucesso.')


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def validar_registros_frequencia(request: HttpRequest, projeto_id: int) -> HttpResponse | None:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    vinculo_usuario = request.user.get_vinculo()
    if request.method == 'POST' and projeto.eh_participante(request.user):
        url_origem = request.META.get('HTTP_REFERER', '.')
        acao = request.POST.getlist('action')[0]
        # Só os registros do projeto da URL: o id de frequência de outro projeto, forjado no POST, é ignorado.
        registros = RegistroFrequencia.objects.filter(pk__in=request.POST.getlist('registros'), projeto=projeto)
        if projeto.is_responsavel(request.user) and acao in ('Validar', 'Cancelar Validação'):
            return validar_ou_cancelar_frequencias(registros, acao, vinculo_usuario, url_origem)
        if acao == 'Excluir Registros':
            if registros:
                for registro in registros:
                    if not registro.validada_em and registro.cadastrada_por == vinculo_usuario:
                        registro.delete()
                return httprr(url_origem, 'Os Registros de Frequência/Atividade diária não validados foram excluídos com sucesso.')
            return httprr(url_origem, 'Nenhum registro selecionado.', tag='error')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def editar_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if not registro.validada_em and registro.cadastrada_por == request.user.get_vinculo():
        title = 'Editar Frequência/Atividade Diária'
        form = EditarFrequenciaForm(request.POST or None, instance=registro)
        if form.is_valid():
            form.save()
            return httprr(
                f'/projetos_ensino/projeto/{registro.projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária editada com sucesso.'
            )
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def excluir_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if not registro.validada_em and registro.cadastrada_por == request.user.get_vinculo():
        projeto = registro.projeto
        registro.delete()
        return httprr(f'/projetos_ensino/projeto/{projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária excluída com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos_ensino.pode_visualizar_projeto')
def aceitar_termo_compromisso(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.vinculo_pessoa == request.user.get_vinculo():
        title = 'Aceitar Termo de Compromisso'
        form = AceiteTermoForm(request.POST or None, participacao=participacao, request=request)
        if form.is_valid():
            participacao.termo_aceito_em = datetime.datetime.now()
            participacao.save()
            return httprr(f'/projetos_ensino/projeto/{participacao.projeto.id}/?tab=equipe', 'Termo de compromisso aceito com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr(two_factor_authentication=True)
@permission_required('projetos_ensino.pode_visualizar_projeto')
def cadastrar_dados_bancarios(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.vinculo_pessoa == request.user.get_vinculo() and not participacao.projeto.eh_somente_leitura():
        title = 'Cadastrar/Atualizar Dados Bancários'
        form = DadosBancariosParticipanteForm(request.POST or None, instance=participacao)
        if form.is_valid():
            form.save()
            titulo = '[SUAP] Projeto de Ensino: Dados bancários atualizados'
            texto = (
                '<h1>Projeto de Ensino</h1>'
                '<h2>Dados bancários atualizados</h2>'
                f"<p>Seus dados bancários cadastrados no projeto '{participacao.projeto.titulo}' foram atualizados. Se você não realizou esta alteração, procure o coordenador do projeto e o coordenador de projetos de ensino do seu campus.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.vinculo_pessoa])
            return httprr(f'/projetos_ensino/projeto/{participacao.projeto.id}/?tab=equipe', 'Dados bancários atualizados com sucesso.')
        return locals()
    else:
        raise PermissionDenied
