import collections
import datetime
import io
import zipfile
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ExpressionWrapper, F, FloatField, Q, QuerySet, Sum
from django.dispatch import receiver
from django.forms import inlineformset_factory
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import get_valid_filename

from comum.forms import AdicionarUsuarioGrupoForm
from comum.models import Arquivo, Configuracao, TrocarSenha, User, UsuarioGrupo, Vinculo
from comum.utils import get_sigla_reitoria, get_uo
from djtools import documentos, layout, relatorios
from djtools.html.graficos import ColumnChart, GroupedColumnChart, PieChart
from djtools.templatetags.filters import format_
from djtools.utils import (
    JsonResponse,
    PDFResponse,
    anonimizar_cpf,
    documento,
    httprr,
    permission_required,
    render_to_string,
    rtr,
    running_tests,
    send_notification,
)
from edu.models import Aluno, Modalidade
from projetos import tasks
from projetos.forms import (
    AceiteTermoForm,
    AdicionarAlunosEmLoteForm,
    AlteraNotaCriterioProjetoForm,
    AlterarChefiaParticipanteForm,
    AlterarCoordenadorForm,
    AnexosDiversosProjetoForm,
    AnoForm,
    AvaliacaoFormFactory,
    AvaliadoresAreaTematicaForm,
    AvaliarCancelamentoProjetoForm,
    AvaliarInteresseCusteioForm,
    AvaliarRecursoExtensaoForm,
    AvaliarRecursoProjetoForm,
    AvaliarRecursosExtensaoForm,
    BuscaProjetoForm,
    CancelarProjetoForm,
    CaracterizacaoBeneficiarioForm,
    ClonarEditalForm,
    ClonarEtapaForm,
    ClonarProjetoForm,
    ComprovanteGRUForm,
    CriterioAvaliacaoAlunoForm,
    CriterioAvaliacaoForm,
    CriterioPreSelecaoForm,
    DadosBancariosParticipanteForm,
    DataInativacaoForm,
    DesembolsoForm,
    EditaisForm,
    EditalAnexoAuxiliarForm,
    EditalAnexoForm,
    EditalTemasForm,
    EditarChExtensaoForm,
    EditarFrequenciaForm,
    EditarProjetoEmExecucaoForm,
    EditarTermoCessaoForm,
    EmailCoordenadoresForm,
    EncerrarAlunosEmLoteForm,
    EquipeEtapaForm,
    EquipeProjetoForm,
    EstatisticasForm,
    EtapaForm,
    ExtratoMensalForm,
    FiltrarListaFrequenciaForm,
    FiltrarNEPPForm,
    FotoNEPPForm,
    FotoProjetoForm,
    GerarListaFrequenciaForm,
    InativarProjetoForm,
    IndefereAlteracaoDataForm,
    IndicarAuxiliarForm,
    IndicarAvaliadoresForm,
    IndicarAvaliadorForm,
    IndicarOrientadorForm,
    IndicarPreAvaliadorForm,
    InterporRecursoExtensaoForm,
    ItemMemoriaCalculoForm,
    LicaoAprendidaForm,
    ListaAvaliadoresProjetosForm,
    ListaEditaisForm,
    ListaMensalBolsistaForm,
    MembroNEPPForm,
    MetaForm,
    MeusProjetosForm,
    OfertaProjetoEmLoteForm,
    OfertaProjetoForm,
    OfertaProjetoFormMultiplo,
    OfertaProjetoGrupoForm,
    OfertaProjetoPorTemaForm,
    ParticipacaoAlunoForm,
    ParticipacaoColaboradorForm,
    ParticipacaoServidorForm,
    PreAvaliacaoForm,
    PreSelecaoForm,
    PrestacaoContaForm,
    ProjetoAvaliadorForm,
    ProjetoExtensaoForm,
    ProjetoHistoricoDeEnvioForm,
    ProjetosAtrasadosForm,
    RecursoForm,
    RecursoProjetoForm,
    RegistrarFrequenciaForm,
    RegistrarOcorrenciaForm,
    RegistroConclusaoProjetoForm,
    RegistroConclusaoProjetoObsForm,
    RegistroExecucaoEtapaForm,
    RegistroGastoForm,
    RegistrosBolsistasForm,
    RelatorioAlunoPorProjetoForm,
    RelatorioCaracterizacaoBeneficiariosForm,
    RelatorioDimensaoExtensaoForm,
    RelatorioFinanceiroExtensaoForm,
    RelatorioLicoesAprendidasForm,
    RelatorioPareceresEmitidosForm,
    ReprovarExecucaoEtapaForm,
    ReprovarExecucaoGastoForm,
    ReprovarManualmenteForm,
    SolicitoesCancelamentoForm,
    TermoCessaoForm,
    TermoParceriaAdesaoForm,
    TermoParceriaAdesaoInlineFormSet,
    UploadArquivoForm,
    ValidacaoConclusaoProjetoForm,
    ValidarAvaliacaoAlunoForm,
    ArquivoInativacaoProjetoForm,
    FinalizacaoSistemicaForm,
    ArquivoFinalizacaoProjetoForm,
    IndicarAvaliadorEmLoteForm,
    NovaMensagemForm,
)
from projetos.models import (
    AreaTematica,
    Avaliacao,
    campus_do_coordenador_extensao,
    AvaliacaoAluno,
    AvaliadorExterno,
    AvaliadorIndicado,
    CaracterizacaoBeneficiario,
    ComissaoEdital,
    CriterioAvaliacao,
    CriterioAvaliacaoAluno,
    CriterioPreSelecao,
    Desembolso,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    EditalArquivo,
    Etapa,
    ExtratoMensalProjeto,
    FocoTecnologico,
    FotoNEPP,
    FotoProjeto,
    HistoricoAlteracaoPeriodoProjeto,
    HistoricoEquipe,
    HistoricoInteresseCusteioProjeto,
    HistoricoOrientacaoProjeto,
    ItemAvaliacao,
    ItemAvaliacaoAluno,
    ItemMemoriaCalculo,
    ItemPreSelecao,
    LicaoAprendida,
    MembroNEPP,
    Meta,
    NucleoExtensao,
    OcorrenciaProjeto,
    OfertaProjeto,
    OfertaProjetoPorGrupo,
    OfertaProjetoPorTema,
    Participacao,
    PreSelecao,
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
    Tema,
    TermoParceriaAdesao,
    TipoVinculo,
    VisitaTecnica,
    Comunicador,
    ArquivoInativacaoProjeto,
    ArquivoFinalizacaoProjeto,
)
from rh.models import PessoaJuridica, Servidor, Titulacao, UnidadeOrganizacional, Situacao
from rh.views import rh_servidor_view_tab


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    participacoes = Participacao.objects.filter(vinculo_pessoa__id=request.user.get_vinculo().id, ativo=True, projeto__aprovado=True)
    for participacao in participacoes:
        if participacao.pode_emitir_certificado_de_participacao_extensao():
            data.append(
                (
                    'Extensão',
                    'Projetos de Extensão',
                    'Certificado de Participação',
                    participacao.projeto,
                    f'/projetos/emitir_certificado_extensao_pdf/{participacao.pk}/',
                )
            )
        if participacao.pode_emitir_declaracao_orientacao():
            data.append(
                (
                    'Extensão',
                    'Projetos de Extensão',
                    'Declaração de Orientação',
                    participacao.projeto,
                    f'/projetos/emitir_declaracao_orientacao_pdf/{participacao.pk}/',
                )
            )
        if participacao.pode_emitir_declaracao_de_participacao():
            data.append(
                (
                    'Extensão',
                    'Projetos de Extensão',
                    'Declaração de Participação',
                    participacao.projeto,
                    f'/projetos/emitir_declaracao_participacao_pdf/{participacao.pk}/',
                )
            )
    # servidor = Servidor.objects.filter(vinculo__user=request.user).first()
    # FIXME: URL está com id diferente, deveria ser o id de VisitaPraticaProfissional e não de VisitaPraticaProfissional
    # for visita_tecnica in VisitaTecnica.objects.filter(participantes=servidor).order_by('-data'):
    #     data.append(('Extensão', 'Estágios', 'Relatório de Visita Técnica', visita_tecnica, f'/estagios/gerar_relatorio_visita_estagio/{visita_tecnica.pk}/'))


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Lista pendências do módulo Projetos atribuídas ao usuário logado.

    Cobre devoluções de projetos enviados pelo usuário, projetos aguardando
    envio, avaliações pendentes (cadastros, planos de trabalho, relatórios)
    e ações de coordenadores/gestores de editais, conforme o perfil.

    Args:
        request: requisição HTTP usada para obter o vínculo do usuário.

    Returns:
        list[dict]: cartões de pendência; lista vazia quando não há ações pendentes.
    """
    pendencias = []

    vinculo = request.user.get_vinculo()

    gerou_alerta_devolucao = False
    qs_historico_envio = ProjetoHistoricoDeEnvio.objects.filter(
        projeto__vinculo_coordenador_id=vinculo.id, situacao=ProjetoHistoricoDeEnvio.DEVOLVIDO
    )
    if qs_historico_envio.exists():
        for registro in qs_historico_envio:
            projeto = registro.projeto
            if not gerou_alerta_devolucao and projeto.get_status() == projeto.STATUS_EM_INSCRICAO:
                pendencias.append({'url': f'/projetos/projeto/{projeto.id}/', 'titulo': f'O projeto {projeto.titulo} foi devolvido.'})
                gerou_alerta_devolucao = True

    # `aberto_ha_2_anos()` é só `inicio_execucao + 2 anos <= hoje` — traduzido para SQL pra eliminar o loop N+1.
    limite_2_anos = (datetime.datetime.now() - relativedelta(years=2)).date()
    projeto_2_anos = (
        Projeto.objects.filter(
            vinculo_coordenador=vinculo,
            pre_aprovado=True,
            aprovado=True,
            inativado=False,
            projetocancelado__isnull=True,
            registroconclusaoprojeto__isnull=True,
            inicio_execucao__lte=limite_2_anos,
        )
        .only('id', 'titulo')
        .first()
    )
    if projeto_2_anos:
        pendencias.append(
            {
                'url': f'/projetos/projeto/{projeto_2_anos.id}/',
                'titulo': f'O projeto <strong>{projeto_2_anos.titulo}</strong> está em execução há mais de dois anos e poderá ser inativado.',
            }
        )

    if request.user.has_group_cached('Coordenador de Extensão', ignore_groups_if_superuser=False):
        # `.order_by('-id').first()` substitui `.exists() + .latest('id')` (era 2 queries → 1).
        registro = Edital.objects.filter(autorizado=None, cadastrado_por=vinculo).order_by('-id').only('id', 'titulo').first()
        if registro:
            pendencias.append(
                {
                    'titulo': f'O edital <strong>{registro.titulo}</strong> ainda não foi autorizado pelo Gerente Sistêmico.',
                    'url': f'/projetos/edital/{registro.id}/',
                }
            )

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
                    'url': f'/projetos/projeto/{pendencia_aceite_termo.projeto.id}/?tab=equipe',
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
                    'url': f'/projetos/projeto/{pendencia_aceite_termo.projeto.id}/?tab=equipe',
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
                    'url': f'/projetos/projeto/{pendencia_aceite_termo.projeto.id}/?tab=equipe',
                    'titulo': f'Você <strong>precisa aceitar o termo de compromisso</strong> do projeto <strong>{pendencia_aceite_termo.projeto.titulo}</strong>.',
                }
            )

        participacoes = Participacao.objects.filter(
            anuencia_registrada_em__isnull=True, projeto__projetocancelado__isnull=True, responsavel_anuencia=request.user.get_relacionamento()
        ).count()
        if participacoes:
            pendencias.append(
                {
                    'titulo': f'Participaç{pluralize(participacoes, "ão,ões")} de Projeto{pluralize(participacoes)} de Extensão',
                    'subtitulo': 'aguardando anuência',
                    'qtd': participacoes,
                    'url': '/projetos/participacoes_pendentes_anuencia/',
                }
            )

    if request.user.has_group_cached(['Servidor', 'Aposentado']):
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
                    'titulo': f'Projeto{pluralize(qtd_coordena_projetos)} de Extensão sob sua Coordenação',
                    'subtitulo': 'aguardando envio',
                    'qtd': qtd_coordena_projetos,
                    'url': '/projetos/meus_projetos/',
                }
            )

    if request.user.eh_servidor or request.user.eh_prestador:
        if AreaTematica.objects.filter(vinculo=vinculo).exists():
            edital_para_avaliar = Edital.objects.em_selecao()
            if edital_para_avaliar.exists():
                ids_editais = edital_para_avaliar.values_list('id', flat=True)
                indicacoes = AvaliadorIndicado.objects.filter(vinculo=vinculo, projeto__edital_id__in=ids_editais).count()
                avaliacoes = Avaliacao.objects.filter(vinculo=vinculo, projeto__edital_id__in=ids_editais).count()
                if indicacoes > avaliacoes:
                    qtd = indicacoes - avaliacoes
                    pendencias.append(
                        {
                            'titulo': f'Projeto{pluralize(qtd)} de Extensão',
                            'subtitulo': 'aguardando avaliação',
                            'qtd': qtd,
                            'url': '/projetos/avaliacao/',
                        }
                    )

    projeto_externo_pendente_validacao = Projeto.objects.filter(
        data_conclusao_planejamento__isnull=False,
        aprovado=False,
        edital__tipo_fomento=Edital.FOMENTO_EXTERNO,
        data_avaliacao__isnull=True,
        vinculo_monitor=vinculo,
    )
    if projeto_externo_pendente_validacao.exists():
        qtd = projeto_externo_pendente_validacao.count()
        pendencias.append(
            {
                'titulo': f'Projeto{pluralize(qtd)} de Extensão com Fomento Externo',
                'subtitulo': 'aguardando validação',
                'qtd': qtd,
                'url': f'/projetos/projeto/{projeto_externo_pendente_validacao[0].id}/',
            }
        )

    projeto_externo_pendente_conclusao = Projeto.objects.filter(
        data_finalizacao_conclusao__isnull=True,
        registroconclusaoprojeto__isnull=False,
        edital__tipo_fomento=Edital.FOMENTO_EXTERNO,
        vinculo_monitor=vinculo,
    )
    if projeto_externo_pendente_conclusao.exists():
        qtd = 0
        for projeto in projeto_externo_pendente_conclusao:
            if not projeto.tem_pendencias():
                qtd += 1
        pendencias.append(
            {
                'titulo': f'Projeto{pluralize(qtd)} de Extensão com Fomento Externo',
                'subtitulo': 'aguardando finalização',
                'qtd': qtd,
                'url': f'/projetos/projeto/{projeto.id}/?tab=conclusao',
            }
        )

    projetos_pendentes_aceite = Projeto.objects.filter(
        avaliacao_aceite_sem_fomento_em=None,
        pre_aprovado=True,
        aprovado=False,
        autorizada_sem_fomento=True,
        vinculo_coordenador=request.user.get_vinculo(),
    ).count()
    if projetos_pendentes_aceite:
        pendencias.append(
            {
                'titulo': f'Projeto{pluralize(projetos_pendentes_aceite)} de Extensão com execução sem fomento autorizado{pluralize(projetos_pendentes_aceite)}',
                'subtitulo': 'aguardando aceite',
                'qtd': projetos_pendentes_aceite,
                'url': '/projetos/meus_projetos_autorizados_sem_fomento/',
            }
        )
    editais = Edital.objects.all().em_avaliacao_recursos()
    if editais.exists():
        recursos_pendentes = ItemAvaliacao.objects.exclude(texto_recurso=None).filter(
            avaliacao__projeto__edital__in=editais.values_list('id', flat=True), avaliacao__vinculo=vinculo, recurso_avaliado_em=None
        )
        if recursos_pendentes.exists():
            total = recursos_pendentes.count()
            pendencias.append(
                {
                    'titulo': f'Recurso{pluralize(total)} de Projeto{pluralize(total)}',
                    'subtitulo': 'pendentes de avaliação',
                    'qtd': total,
                    'url': '/projetos/avaliar_recursos/',
                }
            )
    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    uo = get_uo(request.user)
    if request.user.has_group_cached('Coordenador de Extensão', ignore_groups_if_superuser=False):
        alteracoes_data = HistoricoAlteracaoPeriodoProjeto.objects.filter(aceito=None, projeto__uo_id=uo.pk)
        primeiro_projeto_id = alteracoes_data.values_list('projeto_id', flat=True).first()
        if primeiro_projeto_id is not None:
            qtd_alteracoes_data = alteracoes_data.count()
            pendencias.append(
                {
                    'titulo': f'Pedido{pluralize(qtd_alteracoes_data)} de Alteração de Datas de Projetos de Extensão',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_alteracoes_data,
                    'url': f'/projetos/ver_alteracoes_data/{primeiro_projeto_id}/',
                }
            )
        qtd_recursos_aceitos = RecursoProjeto.objects.filter(
            data_avaliacao__isnull=True, projeto__uo=uo, projeto__edital__campus_especifico=True
        ).count()
        if qtd_recursos_aceitos:
            pendencias.append(
                {
                    'titulo': f'Recurso{pluralize(qtd_recursos_aceitos)} de Projetos de Extensão',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_recursos_aceitos,
                    'url': '/projetos/solicitacoes_de_recurso/?ano=&edital=&situacao=Pendentes+de+Avaliação&editais_form=Aguarde...',
                }
            )

    if request.user.has_group_cached(['Coordenador de Extensão', 'Gerente Sistêmico de Extensão'], ignore_groups_if_superuser=False):
        projetos_sem_monitor = Projeto.objects.filter(
            uo=uo,
            edital__tipo_fomento=Edital.FOMENTO_EXTERNO,
            data_conclusao_planejamento__isnull=False,
            data_pre_avaliacao__isnull=True,
            vinculo_monitor__isnull=True,
        )
        primeiro_edital_id = projetos_sem_monitor.values_list('edital_id', flat=True).first()
        if primeiro_edital_id is not None:
            qtd_projetos_sem_monitor = projetos_sem_monitor.count()
            pendencias.append(
                {
                    'titulo': f'Projeto{pluralize(qtd_projetos_sem_monitor)} de Extensão com fomento externo',
                    'subtitulo': 'a indicar monitor',
                    'qtd': qtd_projetos_sem_monitor,
                    'url': f'/projetos/selecionar_pre_avaliador/{primeiro_edital_id}/?palavra_chave=&uo=&area_tematica=&status_avaliacao=2',
                }
            )

        projetos_cancelados = ProjetoCancelado.objects.filter(data_avaliacao__isnull=True)
        if not request.user.has_group_cached('Gerente Sistêmico de Extensão'):
            projetos_cancelados = projetos_cancelados.filter(projeto__uo=uo)
        qtd_projetos_cancelados = projetos_cancelados.count()
        if qtd_projetos_cancelados:
            pendencias.append(
                {
                    'titulo': f'Pedido{pluralize(qtd_projetos_cancelados)} de Cancelamento de Projetos de Extensão',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_projetos_cancelados,
                    'url': '/projetos/solicitacoes_de_cancelamento/?ano=&edital=&situacao=Pendentes+de+Avaliação&solicitoescancelamento_form=Aguarde...',
                }
            )
    if request.user.has_group_cached('Gerente Sistêmico de Extensão', ignore_groups_if_superuser=False):
        qtd_recursos_aceitos = RecursoProjeto.objects.filter(data_avaliacao__isnull=True).count()
        if qtd_recursos_aceitos:
            pendencias.append(
                {
                    'titulo': f'Recurso{pluralize(qtd_recursos_aceitos)} de Projetos de Extensão',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_recursos_aceitos,
                    'url': '/projetos/solicitacoes_de_recurso/?ano=&edital=&situacao=Pendentes+de+Avaliação&editais_form=Aguarde...',
                }
            )

        edital_pendente_autorizacao = Edital.objects.filter(autorizado__isnull=True).count()
        if edital_pendente_autorizacao:
            pendencias.append(
                {
                    'titulo': f'Edita{pluralize(edital_pendente_autorizacao, "l,is")} de Projetos de Extensão',
                    'subtitulo': 'a autorizar',
                    'qtd': edital_pendente_autorizacao,
                    'url': '/admin/projetos/edital/?pendente_autorizacao=1&tab=tab_any_data',
                }
            )

        alteracao_interesse_fomento = HistoricoInteresseCusteioProjeto.objects.filter(aceito=None).count()
        if alteracao_interesse_fomento:
            pendencias.append(
                {
                    'titulo': f'Alteraç{pluralize(alteracao_interesse_fomento, "ão,ões")} de Interesse por Custeio do Projeto',
                    'subtitulo': 'a autorizar',
                    'qtd': alteracao_interesse_fomento,
                    'url': '/admin/projetos/historicointeressecusteioprojeto/?aceito__isnull=True&tab=tab_any_data',
                }
            )

    return pendencias


@layout.info()
def index_infos(request):
    """Sinaliza ao aluno logado avaliação de projeto pendente de considerações.

    Procura a primeira avaliação de projeto aprovada e ainda sem registro de
    considerações nem cancelamento, atribuindo link direto para o registro.

    Args:
        request: requisição HTTP usada para identificar o vínculo do aluno.

    Returns:
        list[dict]: aviso com ``url`` e ``titulo`` quando há avaliação pendente;
        lista vazia caso contrário.
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
                    'url': f'/projetos/registrar_consideracoes_aluno/{pendente_consideracao.id}/',
                    'titulo': f'Faça suas considerações na avaliação do projeto {pendente_consideracao.participacao.projeto.titulo}.',
                }
            )

    return infos


@layout.quadro('Editais de Extensão', icone='suitcase', pode_esconder=True)
def index_quadros_editais(quadro, request):
    if request.user.has_group_cached(['Servidor', 'Aposentado']):
        editais_abertos_extensao = Edital.objects.em_inscricao().order_by('titulo')
        if editais_abertos_extensao.exists():
            quadro.add_item(
                layout.ItemTitulo(
                    titulo='Inscrições abertas',
                )
            )
            for edital in editais_abertos_extensao:
                quadro.add_item(
                    layout.ItemNoticia(
                        titulo=edital.titulo, url='/projetos/editais_abertos/', chapeu=f'Até {edital.fim_inscricoes.strftime("%d/%m/%Y %H:%M")}'
                    )
                )
    return quadro


@layout.quadro('Projetos de Extensão', icone='suitcase', pode_esconder=False)
def index_quadros_projetos_extensao(quadro, request):
    agora = datetime.datetime.now()
    hoje = agora.date()
    projetos_em_execucao = Projeto.objects.filter(
        aprovado=True, pre_aprovado=True, cancelado=False, inativado=False, concluido=False, vinculo_coordenador=request.user.get_vinculo()
    ).filter(Q(edital__divulgacao_selecao__lt=agora) | Q(edital__tipo_fomento=Edital.FOMENTO_EXTERNO))
    if projetos_em_execucao.exists():
        em_atraso = projetos_em_execucao.filter(fim_execucao__lt=hoje)
        if em_atraso.exists():
            qtd = em_atraso.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Projeto{pluralize(qtd)}',
                    subtitulo='Com o prazo de finalização expirado',
                    qtd=qtd,
                    url='/projetos/meus_projetos/?ano=&edital=&situacao=Todos&pendencia=1&vinculo_membro=1&meusprojetos_form=Aguarde...',
                )
            )
        etapas = Etapa.objects.filter(fim_execucao__lt=agora, registroexecucaoetapa__isnull=True)
        etapas_atrasadas = projetos_em_execucao.filter(id__in=etapas.values_list('meta__projeto', flat=True))
        if etapas_atrasadas.exists():
            qtd = etapas_atrasadas.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Projeto{pluralize(qtd)}',
                    subtitulo='Com registro de execução de atividade em atraso',
                    qtd=qtd,
                    url='/projetos/meus_projetos/?ano=&edital=&situacao=Todos&pendencia=2&vinculo_membro=1&meusprojetos_form=Aguarde...',
                )
            )
        perto_terminar = projetos_em_execucao.filter(fim_execucao__range=[hoje, hoje + datetime.timedelta(15)])
        if perto_terminar.exists():
            qtd = perto_terminar.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Projeto{pluralize(qtd)}',
                    subtitulo=f'Próximo{pluralize(qtd)} da data final de execução',
                    qtd=qtd,
                    url='/projetos/meus_projetos/?ano=&edital=&situacao=Todos&pendencia=3&vinculo_membro=1&meusprojetos_form=Aguarde...',
                )
            )
    return quadro


@layout.quadro('Extensão', icone='suitcase', pode_esconder=True)
def index_quadros(quadro, request):
    vinculo = request.user.get_vinculo()
    if vinculo.eh_aluno() or vinculo.eh_prestador():
        participacoes = Participacao.objects.filter(vinculo_pessoa=vinculo, projeto__aprovado=True)

        projetos_do_aluno = Projeto.objects.filter(id__in=participacoes.values_list('projeto', flat=True))
        if projetos_do_aluno.exists():
            for projeto in projetos_do_aluno:
                quadro.add_item(layout.ItemGrupo(titulo=projeto.titulo, grupo='Meus Projetos', url=f'/projetos/projeto/{projeto.pk}/'))

    elif request.user.has_perm('projetos.pode_gerenciar_edital'):
        pids = UsuarioGrupo.objects.filter(group__name='Coordenador de Extensão').values_list('user__id', flat=True)
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
                    url=f'/projetos/selecionar_pre_avaliador/{participacoes_preavaliador[0].projeto.edital.id}/',
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
                    url=f'/projetos/selecionar_monitor/{participacoes_monitor[0].projeto.edital.id}/',
                )
            )

    hoje = datetime.datetime.now()
    if request.user.has_group_cached('Coordenador de Extensão'):
        id_editais_em_pre_avaliacao = Edital.objects.em_pre_avaliacao().values_list('id', flat=True)
        projetos = Projeto.objects.filter(
            edital__in=id_editais_em_pre_avaliacao, data_pre_avaliacao=None, uo=get_uo(request.user), data_conclusao_planejamento__isnull=False
        )
        participacoes = Participacao.objects.filter(vinculo_pessoa=vinculo).only('projeto')
        if participacoes.exists():
            projetos = projetos.exclude(id__in=participacoes.values_list('projeto', flat=True))

        if projetos.exists():
            qtd = projetos.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Projeto{pluralize(qtd)}',
                    subtitulo='Aguardando pré-avaliação',
                    qtd=qtd,
                    url='/projetos/pre_avaliacao/',
                )
            )

    if request.user.eh_prestador or request.user.eh_servidor:
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).only('projeto').values_list('projeto', flat=True)
        projetos_em_monitoramento = (
            Projeto.objects.filter(
                vinculo_monitor=vinculo,
                aprovado=True,
                inativado=False,
                edital__divulgacao_selecao__lte=hoje,
                registroconclusaoprojeto__dt_avaliacao__isnull=True,
                edital__tipo_fomento=Edital.FOMENTO_INTERNO,
            )
            .exclude(id__in=projetos_cancelados)
            .only('id')
        )
        participacoes = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), ativo=True)
        if participacoes.exists():
            projetos_em_monitoramento = projetos_em_monitoramento.exclude(id__in=participacoes.values_list('projeto', flat=True))

        if projetos_em_monitoramento.exists():
            qtd = projetos_em_monitoramento.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Projeto{pluralize(qtd)}',
                    subtitulo='Monitorados por você',
                    qtd=qtd,
                    url='/projetos/projetos_em_execucao/',
                )
            )
    return quadro


def pode_submeter_novo_projeto(request, edital):
    eh_interno = edital.eh_fomento_interno()
    mensagem_erro = None
    if (
        request.user.eh_aluno
        or request.user.eh_prestador
        or request.user.has_group_cached('Aposentado', ignore_groups_if_superuser=False)
        or (
            request.user.has_perm('projetos.pode_gerenciar_edital', ignore_superuser=True)
            and not Configuracao.get_valor_por_chave('projetos', 'gerente_pode_submeter')
            and not edital.sistemico_pode_submeter
        )
    ):
        raise PermissionDenied

    if not running_tests():
        setores = ()
        servidor_logado = request.user.get_relacionamento()
        if servidor_logado.setor_lotacao:
            if servidor_logado.setor_lotacao.uo.equivalente:
                setores += (servidor_logado.setor_lotacao.uo.equivalente.sigla,)
            else:
                setores += (servidor_logado.setor_lotacao.uo.sigla,)
        if servidor_logado.setor_exercicio:
            setores += (servidor_logado.setor_exercicio.uo.sigla,)
        if servidor_logado.setor:
            setores += (servidor_logado.setor.uo.sigla,)
        if not OfertaProjeto.objects.filter(edital=edital, uo__sigla__in=setores).exists():
            mensagem_erro = 'Este edital não possui oferta para o seu campus.'
            return mensagem_erro
        if not FocoTecnologico.objects.filter(campi__sigla__in=setores).exists():
            mensagem_erro = 'Não existe foco tecnológico cadastrado para o seu campus. Entre em contato com a {}.'.format(
                Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
            )
            return mensagem_erro
        if edital.exige_nivel_superior and (
            not servidor_logado.titulacao or servidor_logado.titulacao.codigo not in Titulacao.CODIGOS_NIVEL_SUPERIOR
        ):
            mensagem_erro = 'Este edital exige que o coordenador possua nível superior.'
            return mensagem_erro

        if eh_interno:
            projetos_pendentes = Projeto.pendencias_editais_anteriores(request.user.get_vinculo(), edital)
            if projetos_pendentes.exists():
                mensagem_erro = f'Não é possível submeter novo projeto enquanto existir outro projeto sob sua coordenação com execução em atraso: "{projetos_pendentes[0].titulo}"'
                return mensagem_erro
    return mensagem_erro


def tem_permissao_acesso_edital(request, edital):
    if (
        request.user.has_perm('projetos.pode_gerenciar_edital')
        or request.user.has_perm('projetos.view_edital')
        and (
            (edital.cadastrado_por and edital.cadastrado_por.setor.uo == get_uo(request.user))
            or (edital.autorizado_em and OfertaProjeto.objects.filter(edital=edital, uo=get_uo(request.user)).exists())
        )
    ):
        return True
    raise PermissionDenied


@rtr()
@permission_required('projetos.view_edital')
def edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    eh_interno = edital.eh_fomento_interno()
    if edital.tipo_edital == edital.EXTENSAO_FLUXO_CONTINUO:
        title = f'{edital.titulo} - Edital de Extensão - Fluxo Contínuo'
    else:
        title = f'{edital.titulo} - Edital de Extensão'

    foco_tecnologico_campus = FocoTecnologico.objects.all()
    temas = edital.temas.all().order_by('areatematica__descricao', 'descricao')
    FormClass = edital.get_form()
    form = FormClass(request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('.', 'Critérios adicionados com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def meus_projetos(request):
    title = 'Meus Projetos'
    vinculo = request.user.get_vinculo()
    participacoes = Participacao.objects.filter(vinculo_pessoa=vinculo).order_by(
        '-projeto__edital__inicio_inscricoes', 'projeto__vinculo_coordenador'
    )
    ano = request.GET.get('ano')
    form = MeusProjetosForm(request.GET or None, ano=ano)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        situacao = form.cleaned_data.get('situacao')
        pendencia = form.cleaned_data.get('pendencia')
        ano = form.cleaned_data.get('ano')
        vinculo_membro = form.cleaned_data.get('vinculo_membro')
        agora = datetime.datetime.now()
        hoje = agora.date()
        if ano:
            participacoes = participacoes.filter(projeto__edital__inicio_inscricoes__year=ano)
        if edital:
            participacoes = participacoes.filter(projeto__edital=edital)

        if situacao:
            projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
            if situacao == MeusProjetosForm.PROJETOS_EM_EDICAO:
                participacoes = participacoes.filter(projeto__data_conclusao_planejamento__isnull=True, projeto__edital__fim_inscricoes__gte=agora)
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
        if pendencia:
            if pendencia == '1':
                participacoes = participacoes.filter(
                    projeto__aprovado=True,
                    projeto__concluido=False,
                    projeto__inativado=False,
                    projeto__cancelado=False,
                    projeto__fim_execucao__lt=hoje,
                )
            elif pendencia == '2':
                etapas_atrasadas = Etapa.objects.filter(fim_execucao__lt=hoje, registroexecucaoetapa__isnull=True)
                participacoes = participacoes.filter(
                    projeto__aprovado=True,
                    projeto__concluido=False,
                    projeto__inativado=False,
                    projeto__cancelado=False,
                    projeto__registroconclusaoprojeto__dt_avaliacao__isnull=True,
                    projeto__id__in=etapas_atrasadas.values_list('meta__projeto', flat=True),
                )
            elif pendencia == '3':
                participacoes = participacoes.filter(
                    projeto__aprovado=True,
                    projeto__concluido=False,
                    projeto__inativado=False,
                    projeto__cancelado=False,
                    projeto__registroconclusaoprojeto__dt_avaliacao__isnull=True,
                    projeto__fim_execucao__range=[hoje, hoje + datetime.timedelta(15)],
                )
        if vinculo_membro:
            if vinculo_membro == '1':
                participacoes = participacoes.filter(responsavel=True)
            elif vinculo_membro == '2':
                participacoes = participacoes.filter(responsavel=False)

    return locals()


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def pre_avaliacao(request):
    title = 'Editais em pré-seleção'
    editais = Edital.objects.em_pre_avaliacao()

    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def avaliacao(request):
    title = 'Editais em Avaliação'
    editais_com_indicacao = AvaliadorIndicado.objects.filter(vinculo=request.user.get_vinculo())
    editais = Edital.objects.em_selecao().filter(pk__in=editais_com_indicacao.values_list('projeto__edital', flat=True))

    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def projetos_pre_aprovados(request, edital_id, uo_id):
    title = 'Seleção de Projetos'
    edital = get_object_or_404(Edital, pk=edital_id)

    if not edital.is_periodo_selecao():
        raise PermissionDenied

    uo = UnidadeOrganizacional.objects.suap().get(pk=uo_id)
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
@permission_required('projetos.pode_pre_avaliar_projeto')
def projetos_nao_avaliados(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)

    if not edital.is_periodo_pre_selecao():
        raise PermissionDenied

    title = f'Pré-Seleção de Projetos - {edital.titulo}'

    projetos = Projeto.objects.filter(edital=edital, data_conclusao_planejamento__isnull=False).order_by('titulo')

    uos = edital.get_uos()
    nao_eh_sistemico = False
    if (
        request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Extensão')
        and not request.user.has_group_cached('Gerente Sistêmico de Extensão')
        and not request.user.has_group_cached('Coordenador de Extensão')
    ):
        projetos = projetos.filter(vinculo_autor_pre_avaliacao=request.user.get_vinculo())

        uos = uos.filter(id__in=projetos.values_list('uo', flat=True))

    if request.user.has_group_cached('Coordenador de Extensão') and not request.user.has_group_cached('Gerente Sistêmico de Extensão'):
        projetos = projetos.filter(uo=get_uo(request.user))
        nao_eh_sistemico = True
        uos = uos.filter(id__in=projetos.values_list('uo', flat=True))
        participacoes = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), projeto__edital=edital)
        if participacoes.exists():
            projetos = projetos.exclude(id__in=participacoes.values_list('projeto', flat=True))

    if (
        not request.user.has_group_cached(['Gerente Sistêmico de Extensão', 'Pré-Avaliador Sistêmico de Projetos de Extensão'])
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
            uo.qtd_inscritos = edital.num_total_projetos_isncritos(uo)
            uo.qtd_enviados = edital.num_total_projetos_enviados(uo)
            uo.qtd_disponivel = oferta.qtd_aprovados - uo.qtd_pre_aprovados
            if uo.qtd_disponivel == 0:
                pode_pre_aprovar = False
        else:
            pode_pre_aprovar = False

    form = PreAvaliacaoForm(request.GET or None, request=request, nao_eh_sistemico=nao_eh_sistemico)
    if form.is_valid():
        campus_escolhido = form.cleaned_data.get('campus')
        area_conhecimento = form.cleaned_data.get('area_conhecimento')
        area_tematica = form.cleaned_data.get('area_tematica')
        pendentes = form.cleaned_data.get('pendentes')
        if campus_escolhido:
            projetos = projetos.filter(uo=campus_escolhido)
        if area_conhecimento:
            projetos = projetos.filter(area_conhecimento=area_conhecimento)
        if area_tematica:
            projetos = projetos.filter(area_tematica=area_tematica)
        if pendentes:
            projetos = projetos.filter(data_pre_avaliacao=None)
    return locals()


@rtr()
@permission_required('projetos.pode_submeter_projeto')
def editais_abertos(request):
    title = 'Editais de Extensão e de Fluxo Contínuo com Inscrições Abertas'
    nao_pode_submeter = False
    pode_gerenciar_edital = request.user.has_perm('projetos.pode_gerenciar_edital', ignore_superuser=True)
    if (
        request.user.eh_aluno
        or request.user.has_group_cached('Aposentado', ignore_groups_if_superuser=False)
        or (
            pode_gerenciar_edital
            and not Configuracao.get_valor_por_chave('projetos', 'gerente_pode_submeter')
            and not Edital.objects.filter(sistemico_pode_submeter=True).exists()
        )
    ):
        editais = None
        nao_pode_submeter = True
    elif pode_gerenciar_edital:
        if Configuracao.get_valor_por_chave('projetos', 'gerente_pode_submeter'):
            editais = Edital.objects.em_inscricao()
        else:
            editais = Edital.objects.filter(sistemico_pode_submeter=True).em_inscricao()
        pode_clonar_projeto = Projeto.objects.filter(vinculo_coordenador=request.user.get_vinculo()).exists()
    elif request.user.eh_servidor:
        editais = Edital.objects.em_inscricao()
        pode_clonar_projeto = Projeto.objects.filter(vinculo_coordenador=request.user.get_vinculo()).exists()
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    edital_projeto = projeto.edital
    usuario_logado = request.user
    tem_movimentacao = ProjetoHistoricoDeEnvio.objects.filter(projeto_id=projeto.id).exists()
    title = f'Projeto de {projeto.edital.get_tipo_edital_display()}: {projeto.titulo}'
    eh_interno = projeto.eh_fomento_interno()
    registro_conclusao = projeto.get_registro_conclusao()
    periodo = projeto.get_periodo(registro_conclusao)
    status = projeto.get_status(periodo, registro_conclusao)
    status_pre_selecao = projeto.get_pre_selecionado(user=usuario_logado)
    status_selecao = projeto.get_selecionado()
    mesmo_campus = projeto.uo == get_uo(usuario_logado)

    # Equipe
    participantes = projeto.participacao_set.all().select_related('vinculo_pessoa')
    coordenadores = participantes.filter(responsavel=True)
    docentes = participantes.filter(
        responsavel=False,
        vinculo_pessoa__tipo_relacionamento__model='servidor',
        vinculo_pessoa__id_relacionamento__in=Servidor.objects.filter(eh_docente=True).values_list('id', flat=True),
    ).order_by('vinculo', 'vinculo_pessoa__pessoa__nome')
    discentes = (
        participantes.filter(responsavel=False)
        .filter(Q(vinculo_pessoa__tipo_relacionamento__model='aluno') | Q(vinculo_pessoa=None))
        .order_by('vinculo', 'vinculo_pessoa__pessoa__nome')
    )
    tec_adm = (
        participantes.filter(responsavel=False, vinculo_pessoa__tipo_relacionamento__model='servidor')
        .exclude(
            vinculo_pessoa__id_relacionamento__in=Servidor.objects.filter(eh_docente=True).values_list('id', flat=True),
        )
        .order_by('vinculo', 'vinculo_pessoa__pessoa__nome')
    )
    col_ext = participantes.filter(responsavel=False, vinculo_pessoa__tipo_relacionamento__model='prestadorservico').order_by(
        'vinculo', 'vinculo_pessoa__pessoa__nome'
    )

    avaliador_pode_visualizar = projeto.avaliador_pode_visualizar()
    vinculo = request.user.get_vinculo()
    is_gerente_sistemico = projeto.is_gerente_sistemico(usuario_logado)
    pode_reprovar_manualmente = projeto.pode_reprovar_manualmente(usuario_logado)
    pode_reverter_reprovacao = projeto.pode_reverter_reprovacao(usuario_logado)
    pode_ver_reprovacao_manual = projeto.pode_ver_reprovacao_manual(usuario_logado)
    is_avaliador_do_projeto = projeto.is_avaliador_do_projeto(usuario_logado)
    is_coex = usuario_logado.groups.filter(name='Coordenador de Extensão').exists()
    is_pre_avaliador = is_coex and mesmo_campus
    pode_alterar_chefia_imediata = is_pre_avaliador or is_gerente_sistemico
    eh_visualizador = usuario_logado.groups.filter(name='Visualizador de Projetos').exists()
    eh_visualizador_campus = usuario_logado.groups.filter(name='Visualizador de Projetos do Campus').exists() and mesmo_campus
    eh_participante = projeto.pode_acessar_projeto(usuario_logado)
    eh_coordenador = projeto.is_responsavel(usuario_logado)
    eh_gerenciador_projeto = projeto.is_gerenciador_projeto(request.user)
    eh_monitor = usuario_logado.get_vinculo() == projeto.vinculo_monitor
    pode_gerenciar_projeto = is_gerente_sistemico or eh_coordenador
    eh_somente_leitura = projeto.eh_somente_leitura(periodo)
    eh_coordenador_de_curso = usuario_logado.groups.filter(name='Coordenador de Curso').exists()
    pode_editar_inscricao_execucao = projeto.pode_editar_inscricao_execucao()
    eh_docente = request.user and request.user.eh_servidor and vinculo.relacionamento.eh_docente
    vinculo_coordenador = projeto.vinculo_coordenador
    coordenador_com_situacao_inativa = bool(
        vinculo_coordenador
        and vinculo_coordenador.eh_servidor()
        and (not vinculo_coordenador.relacionamento.ativo or vinculo_coordenador.relacionamento.situacao.codigo not in Situacao.SITUACOES_ATIVOS)
    )
    pode_finalizar_conclusao = projeto.pode_finalizar_conclusao(registro_conclusao)
    edicao_inscricao_execucao = projeto.edicao_inscricao_execucao()
    valor_financiado_por_projeto = projeto.edital.valor_financiado_por_projeto
    if not projeto.tem_interesse_cartao_pesquisador and Recurso.objects.filter(edital=projeto.edital, eh_vinculada_cartao_pesquisador=True).exists():
        valor_financiado_por_projeto = (
            valor_financiado_por_projeto
            - Recurso.objects.filter(edital=projeto.edital, eh_vinculada_cartao_pesquisador=True).aggregate(total=Sum('valor'))['total']
        )
    divulgacao_avaliacao_liberada = projeto.divulgacao_avaliacao_liberada()
    edital_exige_avaliacao_aluno = projeto.edital.exige_avaliacao_aluno
    pode_ver_dados_bancarios = is_gerente_sistemico or eh_coordenador or is_pre_avaliador
    pode_acessar_certificado = status in (Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO)
    projeto_pode_registrar_execucao = projeto.pode_registrar_execucao(status)
    pode_enviar_projeto = projeto.pode_enviar_projeto(periodo)
    pode_cancelar_projeto = projeto.pode_cancelar_projeto(usuario_logado, status, periodo)
    pode_remover_projeto = projeto.pode_remover_projeto(usuario_logado, status, periodo)
    pode_ser_inativado = projeto.pode_ser_inativado()
    pode_editar_projeto = projeto.pode_editar_projeto(status, periodo, eh_interno)
    pode_registrar_conclusao = projeto.pode_registrar_conclusao(usuario_logado, status)
    pode_reabrir_projeto = projeto.pode_reabrir_projeto(usuario_logado)
    pode_devolver_projeto = projeto.pode_devolver_projeto()
    pode_ver_dados_selecao = is_gerente_sistemico or (edital_projeto.is_periodo_pos_selecao() and (is_pre_avaliador or eh_coordenador))
    hoje = datetime.datetime.now()
    eh_avaliador_em_tempo_avaliacao = is_avaliador_do_projeto and projeto.projeto_em_avaliacao()
    pode_ver_comprovante_gru = eh_coordenador or eh_monitor or is_pre_avaliador or is_gerente_sistemico
    tem_cancelamento = ProjetoCancelado.objects.filter(projeto=projeto)
    tem_pendencias = not registro_conclusao or (registro_conclusao and not registro_conclusao.dt_avaliacao) or projeto.tem_pendencias()
    tem_historico_datas = HistoricoAlteracaoPeriodoProjeto.objects.filter(projeto=projeto)
    pode_ver_avaliacoes = eh_coordenador or eh_monitor
    pode_inativar_projeto = status == Projeto.STATUS_EM_EXECUCAO and is_gerente_sistemico
    pode_reativar_projeto = projeto.inativado and is_gerente_sistemico
    pode_editar_termos = projeto.pode_editar_inscricao_execucao() and not eh_somente_leitura
    pode_editar_ch_extensao = pode_editar_termos or is_gerente_sistemico
    exibe_abas_financeiras = not projeto.autorizada_sem_fomento or projeto.fomento_autorizado_em
    pode_autorizar_fomento = projeto.autorizada_sem_fomento and not projeto.fomento_autorizado_em and (is_gerente_sistemico or is_pre_avaliador)
    liberar_botao_editar = False
    prazo_execucao_expirou = hoje.date() > projeto.fim_execucao
    if prazo_execucao_expirou and registro_conclusao and pode_editar_inscricao_execucao:
        liberar_botao_editar = registro_conclusao.dt_avaliacao
    eh_responsavel_anuencia = (
        request.user
        and request.user.eh_servidor
        and (Participacao.objects.filter(projeto=projeto, responsavel_anuencia=request.user.get_relacionamento()).exists())
    )

    edicao_inscricao = False
    mensagem_erro = ''
    if is_gerente_sistemico or (eh_coordenador and status == Projeto.STATUS_EM_INSCRICAO):
        edicao_inscricao = True
        mensagem_erro = projeto_com_pendencias_para_envio(projeto_id)

    edicao_inscricao_execucao = False
    if is_gerente_sistemico or (eh_coordenador and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO)):
        edicao_inscricao_execucao = True

    if eh_participante and not eh_coordenador:
        edicao_inscricao = False
        edicao_inscricao_execucao = False

    resumo_recursos = []
    recursos = projeto.edital.recurso_set.filter()
    if not projeto.tem_interesse_cartao_pesquisador:
        recursos = recursos.exclude(eh_vinculada_cartao_pesquisador=True)
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

    geral_saldo = valor_financiado_por_projeto - geral_planejado
    geral_disponivel = geral_planejado - geral_executado

    extratos_mensais = ExtratoMensalProjeto.objects.filter(projeto=projeto)

    termos_cessao = RegistroGasto.objects.filter(desembolso__projeto=projeto, arquivo_termo_cessao__isnull=False, arquivo_termo_cessao__gt='')
    itens_com_recurso = ItemAvaliacao.objects.filter(avaliacao__projeto=projeto).exclude(texto_recurso=None).order_by('criterio_avaliacao')
    devolucao = None
    if (
        ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).exists()
        and status == projeto.STATUS_EM_INSCRICAO
        and ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).latest('id').situacao == ProjetoHistoricoDeEnvio.DEVOLVIDO
    ):
        devolucao = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).latest('id')
    memorias_de_calculo = projeto.itemmemoriacalculo_set.all().select_related('despesa')
    ocorrencias = OcorrenciaProjeto.objects.filter(projeto=projeto).order_by('-id')
    pode_registrar_ocorrencia = (is_pre_avaliador and mesmo_campus) or is_gerente_sistemico
    registros_frequencia = (
        RegistroFrequencia.objects.filter(projeto=projeto)
        .select_related('cadastrada_por', 'cadastrada_por__user', 'validada_por', 'validada_por__user')
        .order_by('-data', 'cadastrada_por')
    )
    tem_registros_frequencia = registros_frequencia.exists()
    pode_ver_frequencias = eh_coordenador or is_gerente_sistemico or is_pre_avaliador or eh_visualizador or eh_visualizador_campus
    tem_frequencia_aluno_pendente = projeto.tem_frequencia_aluno_pendente()
    if not pode_ver_frequencias:
        registros_frequencia = registros_frequencia.filter(cadastrada_por=request.user.get_vinculo())
    form_frequencias = FiltrarListaFrequenciaForm(request.GET or None, projeto=projeto)
    if form_frequencias.is_valid():
        data_inicio = form_frequencias.cleaned_data.get('data_inicio')
        data_termino = form_frequencias.cleaned_data.get('data_termino')
        participante = form_frequencias.cleaned_data.get('participante')
        situacao = form_frequencias.cleaned_data.get('situacao')
        retorno_inicio = retorno_fim = retorno_participante = retorno_situacao = ''
        if data_inicio:
            registros_frequencia = registros_frequencia.filter(data__gte=data_inicio)
            retorno_inicio = data_inicio.strftime('%d/%m/%Y')
        if data_termino:
            registros_frequencia = registros_frequencia.filter(data__lte=data_termino)
            retorno_fim = data_termino.strftime('%d/%m/%Y')
        if situacao:
            if situacao == 'Pendentes':
                registros_frequencia = registros_frequencia.filter(validada_por=None)
            else:
                registros_frequencia = registros_frequencia.exclude(validada_por=None)
            retorno_situacao = situacao
        if participante:
            registros_frequencia = registros_frequencia.filter(cadastrada_por=participante)
            retorno_participante = participante.id

        if 'tab' not in request.GET:
            return httprr(
                f'/projetos/projeto/{projeto.id}/?tab=registro_frequencia&data_inicio={retorno_inicio}&data_termino={retorno_fim}&participante={retorno_participante}&situacao={retorno_situacao}&filtrarlistafrequencia_form=Aguarde...'
            )
    if not (
        eh_monitor
        or eh_coordenador
        or is_gerente_sistemico
        or eh_avaliador_em_tempo_avaliacao
        or is_pre_avaliador
        or eh_participante
        or eh_visualizador
        or eh_visualizador_campus
        or eh_coordenador_de_curso
        or eh_responsavel_anuencia
    ):
        return httprr(f'/projetos/consulta_projeto/{projeto.id}/')

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def consulta_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Projeto de {projeto.edital.get_tipo_edital_display()}: {projeto.titulo}'
    status = projeto.get_status()
    periodo = projeto.get_periodo()
    eh_interno = projeto.eh_fomento_interno()
    divulgacao_avaliacao_liberada = projeto.divulgacao_avaliacao_liberada()
    avaliador_pode_visualizar = projeto.avaliador_pode_visualizar()
    status_pre_selecao = projeto.get_pre_selecionado()
    status_selecao = projeto.get_selecionado()
    participantes = projeto.participacao_set.all().select_related('vinculo_pessoa')
    coordenadores = participantes.filter(responsavel=True)
    docentes = participantes.filter(
        responsavel=False,
        vinculo_pessoa__tipo_relacionamento__model='servidor',
        vinculo_pessoa__id_relacionamento__in=Servidor.objects.filter(eh_docente=True).values_list('id', flat=True),
    ).order_by('vinculo', 'vinculo_pessoa__pessoa__nome')
    discentes = (
        participantes.filter(responsavel=False)
        .filter(Q(vinculo_pessoa__tipo_relacionamento__model='aluno') | Q(vinculo_pessoa=None))
        .order_by('vinculo', 'vinculo_pessoa__pessoa__nome')
    )
    tec_adm = participantes.filter(
        responsavel=False,
        vinculo_pessoa__tipo_relacionamento__model='servidor',
        vinculo_pessoa__id_relacionamento__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('id', flat=True),
    ).order_by('vinculo', 'vinculo_pessoa__pessoa__nome')
    col_ext = participantes.filter(responsavel=False, vinculo_pessoa__tipo_relacionamento__model='prestadorservico').order_by(
        'vinculo', 'vinculo_pessoa__pessoa__nome'
    )

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def imprimir_projeto(request, projeto_id):
    is_avaliador = request.user.has_group_cached('Avaliador de Projetos de Extensão')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
    cronograma = projeto.get_cronograma_desembolso_como_lista()
    plano_aplicacao = projeto.get_plano_aplicacao_como_dict()
    edital_projeto = get_object_or_404(Edital, pk=projeto.edital.id)
    em_avaliacao = False
    eh_interno = projeto.eh_fomento_interno()
    pode_visualizar_equipe = projeto.avaliador_pode_visualizar()
    if eh_interno:
        em_avaliacao = projeto.edital.is_periodo_pre_selecao() or projeto.edital.is_periodo_selecao()
    total_geral = projeto.itemmemoriacalculo_set.extra({'total': 'SUM(valor_unitario*qtd)'}).values('total')[0]['total']

    metas = projeto.get_metas()
    tipo_vinculo = TipoVinculo()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
    html = 'html' in request.GET

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def relatorio_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
    cronograma = projeto.get_cronograma_desembolso_como_lista()
    valor_financiamento_projeto = (
        RegistroGasto.objects.filter(item__projeto__id=projeto_id, aprovado=True)
        .extra(select={'total': 'SUM(projetos_registrogasto.qtd*projetos_registrogasto.valor_unitario)'})
        .values('total')[0]['total']
    )
    tipo_vinculo = TipoVinculo()
    eh_interno = projeto.eh_fomento_interno()
    pdf = False
    pode_visualizar_equipe = projeto.avaliador_pode_visualizar()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
    html = 'html' in request.GET

    return locals()


def _item_memoria_calculo_alteravel(projeto: Projeto, item_id: str) -> ItemMemoriaCalculo:
    """Item do projeto que a aba "Plano de Aplicação" oferece para editar/remover; senão 403 (#17546)."""
    item = get_object_or_404(ItemMemoriaCalculo, pk=item_id, projeto=projeto)
    if not item.pode_editar_e_remover_memoria_calculo():
        raise PermissionDenied
    return item


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def memoria_calculo(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Memória de Cálculo'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    url = f'/projetos/projeto/{projeto.id}/?tab=plano_aplicacao'
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        editavel = not projeto.data_pre_avaliacao and request.user.has_group_cached(['Servidor', 'Aposentado'])
        if editavel:
            editavel = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), responsavel=True).count() > 0

        if request.user.has_perm('projetos.pode_gerenciar_edital'):
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def registro_conclusao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.pode_registrar_conclusao():
        title = 'Conclusão do Projeto'
        registro = projeto.get_registro_conclusao()
        form = RegistroConclusaoProjetoForm(data=request.POST or None, instance=registro, projeto=projeto)
        if form.is_valid():
            registro = form.save(False)
            registro.projeto = projeto
            registro.save()
            return httprr('..', 'Conclusão do projeto registrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


def _so_comprovante_registro_gasto(registro: RegistroGasto, user: User) -> bool:
    """Gasto aprovado e ainda sem nota fiscal: o gerenciador do projeto só anexa os arquivos, mantendo a aprovação."""
    return bool(
        not registro.pode_editar_remover_registro_gasto() and not registro.arquivo and registro.desembolso.projeto.is_gerenciador_projeto(user)
    )


def _salvar_registro_gasto(form: RegistroGastoForm, desembolso: Desembolso, so_comprovante: bool) -> HttpResponse:
    """Salva o gasto; a edição completa volta o gasto para avaliação, o cadastro só do comprovante preserva a aprovação."""
    registro_gasto = form.save(False)
    registro_gasto.desembolso = desembolso
    if not registro_gasto.data_cadastro:
        registro_gasto.data_cadastro = datetime.datetime.today()
    if form.cleaned_data.get('observacao') and form.cleaned_data.get('gasto_nao_executado'):
        registro_gasto.valor_unitario = 0.00
    if so_comprovante:
        registro_gasto.save()
        return httprr(f'/projetos/projeto/{desembolso.projeto.id}/', 'Comprovante de gasto cadastrado com sucesso.')
    registro_gasto.dt_avaliacao = None
    registro_gasto.avaliador = None
    registro_gasto.justificativa_reprovacao = None
    registro_gasto.save()
    return httprr('.', 'Gasto registrado com sucesso.')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def registro_gasto(request: HttpRequest, item_id: int) -> dict | HttpResponse:
    title = 'Gastos Registrados'
    desembolso = get_object_or_404(Desembolso, pk=item_id)
    projeto = desembolso.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if (projeto.pode_editar_gasto() and not projeto.eh_somente_leitura()) or projeto.is_gerente_sistemico():
        ja_tem_registrogasto = desembolso.registrogasto_set.exists()
        is_coordenador = projeto.is_coordenador(request.user) or projeto.is_gerente_sistemico()
        registro = None
        edicao = False
        if request.method == 'GET' and 'registro_id' in request.GET:
            registro_gasto = get_object_or_404(RegistroGasto, pk=request.GET['registro_id'], desembolso=desembolso)
            if not registro_gasto.pode_editar_remover_registro_gasto():
                return httprr(f'/projetos/projeto/{projeto.id}/', 'Não é possível excluir um registro de gasto avaliado.', 'alert')
            registro_gasto.delete()
            return httprr('.', 'Registro excluído com sucesso.')

        so_comprovante = False
        if 'editar_registro_id' in request.GET:
            registro = get_object_or_404(RegistroGasto, pk=request.GET['editar_registro_id'], desembolso=desembolso)
            edicao = True
            so_comprovante = _so_comprovante_registro_gasto(registro, request.user)
            if not so_comprovante and not registro.pode_editar_remover_registro_gasto():
                return httprr(f'/projetos/projeto/{projeto.id}/', 'Não é possível editar um registro de gasto avaliado.', 'alert')

        if request.method == 'POST':
            form = RegistroGastoForm(request.POST, request.FILES, instance=registro, desembolso=desembolso)
            if form.is_valid():
                return _salvar_registro_gasto(form, desembolso, so_comprovante)
        else:
            if registro:
                form = RegistroGastoForm(instance=registro, desembolso=desembolso)
            else:
                initial = {
                    'descricao': desembolso.item.descricao,
                    'qtd': 1,
                    'valor_unitario': desembolso.valor,
                    'ano': desembolso.ano.pk,
                    'mes': desembolso.mes,
                }
                form = RegistroGastoForm(initial=initial, desembolso=desembolso)
                field_qtd = form.fields['qtd']

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def registro_execucao_etapa(request, etapa_id):
    title = 'Registro de Execução de Atividade'
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    instance = etapa.get_registro_execucao()
    if instance and instance.aprovado:
        raise PermissionDenied
    if etapa.pode_registrar_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = RegistroExecucaoEtapaForm(request.POST, request.FILES, instance=instance, projeto=projeto)
            if form.is_valid():
                with transaction.atomic():
                    registro_execucao_etapa = form.save(False)
                    registro_execucao_etapa.etapa = etapa
                    registro_execucao_etapa.data_cadastro_execucao = datetime.datetime.today()
                    registro_execucao_etapa.dt_avaliacao = None
                    registro_execucao_etapa.avaliador = None
                    registro_execucao_etapa.justificativa_reprovacao = None
                    registro_execucao_etapa.save()
                    return httprr('..', 'Execução registrada com sucesso.')
        else:
            if instance:
                form = RegistroExecucaoEtapaForm(instance=instance, projeto=projeto)
            else:
                initial = {'qtd': etapa.qtd, 'inicio_execucao': etapa.inicio_execucao, 'fim_execucao': etapa.fim_execucao}
                form = RegistroExecucaoEtapaForm(initial=initial, projeto=projeto)
            form.fields['qtd'].help_text = f'Quantidade de "{etapa.unidade_medida}"'

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_registro_execucao_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=False)
    instance = etapa.get_registro_execucao()
    if projeto.pode_registrar_execucao() and not projeto.eh_somente_leitura() and instance:
        if not projeto.is_coordenador(request.user):
            return httprr('..', 'Apenas o cordenador do projeto tem acesso a essa página.', 'alert')
        instance.delete()
        return httprr(f'/projetos/projeto/{projeto.pk}/?tab=metas', 'Registro de execução de etapa removido com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def validar_execucao_etapa(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Validar Execução'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_gastos = RegistroGasto.objects.filter(item__projeto=projeto).exists()
    status = projeto.get_status()
    pode_validar = (projeto.vinculo_monitor == request.user.get_vinculo()) and not projeto.eh_participante(request.user)
    if not projeto.pode_acessar_monitoramento(request.user):
        raise PermissionDenied
    if pode_validar:
        if request.method == 'GET' and 'registro_id' in request.GET:
            registro = get_object_or_404(RegistroExecucaoEtapa, pk=request.GET['registro_id'], etapa__meta__projeto=projeto)
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = True
            registro.save()
            return httprr(f'/projetos/validar_execucao_etapa/{projeto.pk}/?tab=metas', 'Execução de atividade validada com sucesso.')

        elif request.method == 'GET' and 'item_id' in request.GET:
            registro = get_object_or_404(RegistroGasto, pk=request.GET['item_id'], item__projeto=projeto)
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = True
            registro.save()
            return httprr(f'/projetos/validar_execucao_etapa/{projeto.pk}/?tab=gastos', 'Gasto validado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def reprovar_execucao_etapa(request, registroexecucaoetapa_id):
    title = 'Justificar Não Aprovação da Atividade'
    registro = get_object_or_404(RegistroExecucaoEtapa, pk=registroexecucaoetapa_id)
    projeto = registro.etapa.meta.projeto
    if request.user.get_vinculo() == projeto.vinculo_monitor:
        form = ReprovarExecucaoEtapaForm(request.POST or None)
        if form.is_valid():
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = False
            registro.justificativa_reprovacao = form.cleaned_data['obs']
            registro.save()

            titulo = '[SUAP] Extensão: Registro de execução de atividade não aprovado'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Registro de execução de atividade não aprovado</h2>'
                f"<p>Um registro de execução de atividade do projeto '{projeto.titulo}' não foi aprovado pelo monitor do projeto. Acesse o SUAP para mais detalhes.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
            return httprr('..', 'Execução de atividade avaliada com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def reprovar_execucao_gasto(request, registroexecucaogasto_id):
    title = 'Justificar Não Aprovação do Gasto'
    registro = get_object_or_404(RegistroGasto, pk=registroexecucaogasto_id)
    projeto = registro.desembolso.projeto
    if request.user.get_vinculo() == projeto.vinculo_monitor:
        form = ReprovarExecucaoGastoForm(request.POST or None)
        if form.is_valid():
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = False
            registro.justificativa_reprovacao = form.cleaned_data['obs']
            registro.save()
            titulo = '[SUAP] Extensão: Registro de gasto não aprovado'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Registro de gasto não aprovado</h2>'
                f"<p>Um registro de gasto do projeto '{projeto.titulo}' não foi aprovado pelo monitor do projeto. Acesse o SUAP para mais detalhes.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
            return httprr('..', 'Gasto avaliado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_participante_servidor(request, projeto_id):
    title = 'Adicionar Participante'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Extensão').exists() and mesmo_campus
    if not is_pre_avaliador:
        tem_permissao(request, projeto, pode_auxiliar=True)
    if (projeto.pode_editar_inscricao_execucao() or is_pre_avaliador) and not projeto.eh_somente_leitura():
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
                    titulo = '[SUAP] Extensão: Termo de Compromisso do Servidor'
                    texto = (
                        '<h1>Extensão</h1>'
                        '<h2>Termo de Compromisso do Servidor</h2>'
                        f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('servidor').get_vinculo()])

                if participacao.exige_anuencia():
                    servidor = participacao.vinculo_pessoa.relacionamento
                    chefes = servidor.chefes_na_data(datetime.datetime.now().date()).order_by('funcao')
                    if chefes:
                        participacao.responsavel_anuencia = chefes[0]
                        participacao.save()

                return httprr('..', 'Participante adicionado com sucesso.')
        else:
            form = ParticipacaoServidorForm()
            form.projeto = projeto

        return locals()
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_participante_colaborador(request, projeto_id):
    title = 'Adicionar Participante'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if not projeto.edital.permite_colaborador_voluntario:
        raise PermissionDenied('Acesso negado.')
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
                    obj = TrocarSenha.objects.create(username=form.cleaned_data['prestador'].prestador.matricula)
                    url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
                    titulo = '[SUAP] Extensão: Termo de Compromisso do Colaborador Externo'
                    texto = f"""
                        <h1>Extensão</h1>
                        <h2>Termo de Compromisso do Colaborador Externo</h2>
                        <p>Você foi cadastrado(a) como membro da equipe do projeto \'{projeto.titulo}\'. Acesse o SUAP para aceitar o termo de compromisso.</p>
                        <p>Acesse o SUAP através do link {settings.SITE_URL} e escolha a opção "Entrar com Gov.BR".</p>
                        <p>Caso não seja possível e ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
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
@permission_required('projetos.pode_interagir_com_projeto')
def editar_participante_servidor(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
                historico = HistoricoEquipe.objects.filter(ativo=True, participante=participacao, projeto=projeto).order_by('id')
                if historico.exists():
                    registro = historico[0]
                    registro.data_movimentacao = form.cleaned_data.get('data')
                    registro.save()
            return httprr('..', 'Participante editado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def editar_participante_aluno(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
                participacao.vinculo_pessoa = Vinculo.objects.get(
                    id_relacionamento=form.cleaned_data.get('aluno').id, tipo_relacionamento__model='aluno'
                )
                participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=form.cleaned_data.get('data'))
                adicionou_evento = True
            elif participacao.vinculo_pessoa and not HistoricoEquipe.objects.filter(ativo=True, participante=participacao, projeto=projeto).exists():
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
                    participacao.gerencia_bolsa_ae()
                Participacao.gerar_anexos_do_participante(participacao)
            else:
                historico = HistoricoEquipe.objects.filter(ativo=True, participante=participacao, projeto=projeto).order_by('id')
                if historico.exists() and not form.cleaned_data.get('indicar_pessoa_posteriormente') and form.cleaned_data.get('data'):
                    registro = historico[0]
                    registro.data_movimentacao = form.cleaned_data.get('data')
                    registro.save()
            return httprr('..', 'Participante editado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def editar_participante_colaborador(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
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
                historico = HistoricoEquipe.objects.filter(ativo=True, participante=participacao, projeto=projeto).order_by('id')
                if historico.exists():
                    registro = historico[0]
                    registro.data_movimentacao = form.cleaned_data.get('data')
                    registro.save()
            return httprr('..', 'Participante editado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def alterar_coordenador(request, projeto_id):
    title = 'Alterar Coordenador'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Extensão').exists() and mesmo_campus

    eh_gerenciador_projeto = projeto.is_gerenciador_projeto(request.user)
    if ((projeto.pode_editar_inscricao_execucao() and eh_gerenciador_projeto) or is_pre_avaliador) and not projeto.eh_somente_leitura():
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
                historico = ProjetoHistoricoDeEnvio()
                historico.projeto = projeto
                historico.data_operacao = datetime.datetime.now()
                if request.user.eh_servidor:
                    historico.operador = request.user.get_relacionamento()
                historico.parecer_devolucao = (
                    f'Alteração do Coordenador. Justificativa: {form.cleaned_data.get("justificativa")} por {request.user.get_relacionamento()}'
                )

                historico.save()
                return httprr('..', 'Coordenador alterado com sucesso.')
        else:
            form = AlterarCoordenadorForm(projeto=projeto)

        form.fields['participacao'].queryset = participacoes

        return locals()
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_participante_aluno(request, projeto_id):
    title = 'Adicionar Aluno'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
                    participacao.adicionar_registro_historico_equipe(
                        HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=form.cleaned_data.get('data')
                    )
                Participacao.gerar_anexos_do_participante(participacao)
                if projeto.edital.exige_termo_aluno() and form.cleaned_data.get('aluno'):
                    titulo = '[SUAP] Extensão: Termo de Compromisso do Aluno'
                    texto = (
                        '<h1>Extensão</h1>'
                        '<h2>Termo de Compromisso do Aluno</h2>'
                        f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('aluno').get_vinculo()])

                return httprr('..', 'Participante adicionado com sucesso.')
        else:
            form = ParticipacaoAlunoForm(editar=False, projeto=projeto)
            form.projeto = projeto

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def pre_aprovar(request, projeto_id):
    return pre_selecionar(request, projeto_id, rejeitar=False)


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def pre_rejeitar(request, projeto_id):
    return pre_selecionar(request, projeto_id, rejeitar=True)


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def avaliar(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Avaliação do Projeto - {projeto.titulo}'

    if not projeto.edital.is_periodo_selecao():
        raise PermissionDenied
    vinculo = request.user.get_vinculo()
    if projeto.pode_avaliar_projeto(vinculo):
        try:
            avaliacao = Avaliacao.objects.get(projeto=projeto, vinculo=vinculo)
        except Exception:
            avaliacao = None
        form = AvaliacaoFormFactory(request, avaliacao, projeto, vinculo)
        if form.is_valid():
            form.save()
            return httprr('..', 'Projeto avaliado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def visualizar_ficha_avaliacao(request: HttpRequest, avaliacao_id: int) -> dict:
    title = 'Detalhamento da Avaliação do Projeto '
    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    projeto = avaliacao.projeto
    eh_sistemico = bool(request.user.has_group_cached('Gerente Sistêmico de Extensão'))
    usuario_logado = request.user
    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    is_coex = usuario_logado.groups.filter(name='Coordenador de Extensão').exists()
    is_pre_avaliador = is_coex and mesmo_campus
    eh_coordenador = projeto.is_responsavel(usuario_logado)
    pode_ver_dados_selecao = eh_sistemico or (projeto.edital.is_periodo_pos_selecao() and (is_pre_avaliador or eh_coordenador))
    # o mesmo predicado de `ver_alteracao_ficha_avaliacao`: Coordenador de Extensão do campus ou `tem_permissao(pode_auxiliar=True)`
    pode_ver_alteracao = (
        is_pre_avaliador
        or eh_coordenador
        or projeto.is_gerente_sistemico(usuario_logado)
        or bool(projeto.auxiliar and projeto.auxiliar == usuario_logado.get_vinculo())
    )
    if pode_ver_dados_selecao:
        itens_avaliacao = ItemAvaliacao.objects.filter(avaliacao=avaliacao).order_by('-pontuacao')
        if itens_avaliacao.exists():
            projeto = itens_avaliacao[0].avaliacao.projeto
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def projetos_em_execucao(request):
    title = 'Monitoramento'
    hoje = datetime.datetime.now()
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos = (
        Projeto.objects.filter(
            aprovado=True,
            inativado=False,
            edital__divulgacao_selecao__lte=hoje,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            edital__tipo_fomento=Edital.FOMENTO_INTERNO,
        )
        .exclude(id__in=projetos_cancelados)
        .order_by('-edital__divulgacao_selecao')
    )
    ano = request.GET.get('ano')

    if request.user.has_group_cached('Coordenador de Extensão'):
        participacoes = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), ativo=True)
        if participacoes.exists():
            projetos = projetos.exclude(id__in=participacoes.values_list('projeto', flat=True))

    if not request.user.has_group_cached(
        ['Visualizador de Projetos', 'Gerente Sistêmico de Extensão', 'Pré-Avaliador Sistêmico de Projetos de Extensão']
    ):
        projetos = projetos.filter(vinculo_monitor=request.user.get_vinculo())

    if request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Extensão') and not request.user.has_group_cached(
        ['Gerente Sistêmico de Extensão', 'Coordenador de Extensão']
    ):
        projetos = projetos.filter(vinculo_monitor=request.user.get_vinculo())

    elif request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Extensão') and request.user.has_group_cached(
        'Coordenador de Extensão'
    ):
        projetos = projetos.filter(uo=get_uo(request.user)) | projetos.filter(vinculo_monitor=request.user.get_vinculo())

    form = BuscaProjetoForm(data=request.GET or None, request=request, ano=ano, projetos=projetos)

    if form.is_valid():
        if form.cleaned_data.get('palavra_chave'):
            projetos = projetos.filter(titulo__icontains=form.cleaned_data['palavra_chave'])

        if form.cleaned_data.get('uo'):
            projetos = projetos.filter(uo=form.cleaned_data['uo'])

        if form.cleaned_data.get('ano'):
            projetos = projetos.filter(edital__inicio_inscricoes__year=form.cleaned_data['ano'])

        if form.cleaned_data.get('edital'):
            projetos = projetos.filter(edital=form.cleaned_data['edital'])

        if form.cleaned_data.get('por_mim'):
            projetos = projetos.filter(vinculo_monitor=request.user.get_vinculo())

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def remover_participante(request, participacao_id):
    title = 'Inativar Participante'
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura() and not participacao.responsavel:
        form = DataInativacaoForm(request.POST or None, projeto=projeto, participacao=participacao)
        if form.is_valid():
            data_escolhida = form.cleaned_data.get('data')
            ch_extensao = form.cleaned_data.get('ch_extensao')
            if (
                HistoricoOrientacaoProjeto.objects.filter(orientador=participacao, data_inicio__gte=data_escolhida).exists()
                or HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_inicio__gte=data_escolhida).exists()
            ):
                return httprr(
                    f'/projetos/projeto/{projeto.id}/?tab=equipe',
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
            participacao.ch_extensao = ch_extensao
            participacao.orientador = None
            participacao.data_inativacao = data_escolhida
            participacao.save(encerrar=True)
            participacao.adicionar_registro_historico_equipe(
                HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_evento=data_escolhida, obs=form.cleaned_data.get('justificativa')
            )
            if projeto.auxiliar and projeto.auxiliar == participacao.vinculo_pessoa:
                projeto.auxiliar = None
                projeto.save()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=equipe', 'Participação encerrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def ativar_participante(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        participacao.ativo = True
        participacao.data_inativacao = None
        participacao.save(reativar=True)
        participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ATIVAR_PARTICIPANTE)
        return httprr(f'/projetos/projeto/{projeto.id}/?tab=equipe', 'Participante ativado com sucesso.')
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_meta(request, projeto_id):
    title = 'Adicionar Meta'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_meta(request, meta_id):
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Editar Meta'
        if request.method == 'POST':
            form = MetaForm(data=request.POST, instance=meta)
            if form.is_valid():
                o = form.save(False)
                o.save()
                return httprr('..', 'Meta editada com sucesso.')
        else:
            form = MetaForm(instance=meta)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def remover_meta(request, meta_id):
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        meta.delete()
        return httprr(f'/projetos/projeto/{projeto.pk}/?tab=metas', 'Meta removida com sucesso.')
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_etapa(request, meta_id):
    title = 'Adicionar Atividade'
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def remover_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        etapa.delete()

        return httprr(f'/projetos/projeto/{projeto.pk}/?tab=metas', 'Atividade removida com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_equipe_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Editar Equipe da Atividade'
        if request.method == 'POST':
            form = EquipeEtapaForm(data=request.POST, instance=etapa, proj=projeto)
            if form.is_valid():
                o = form.save(False)
                o.save()
                form.save_m2m()
                return httprr('..', 'Equipe da atividade editada com sucesso.')
        else:
            form = EquipeEtapaForm(instance=etapa, proj=projeto)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.view_edital')
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
@permission_required('projetos.view_edital')
def remover_recurso(request, recurso_id):
    recurso = get_object_or_404(Recurso, pk=recurso_id)
    edital = recurso.edital
    tem_permissao_acesso_edital(request, edital)
    recurso.delete()

    return httprr(f'/projetos/edital/{edital.id}/?tab=fonte_recursos', 'Recurso removido com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def editar_recurso(request, recurso_id):
    recurso = get_object_or_404(Recurso, pk=recurso_id)
    tem_permissao_acesso_edital(request, recurso.edital)
    title = 'Editar Recurso do Edital'
    if request.method == 'POST':
        form = RecursoForm(data=request.POST, instance=recurso, edital=recurso.edital)
        if form.is_valid():
            o = form.save(False)
            o.origem = form.cleaned_data.get('origem_recurso').descricao
            o.save()
            return httprr('..', 'Recurso editado com sucesso.')
    else:
        form = RecursoForm(instance=recurso, edital=recurso.edital)

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def adicionar_criterio_avaliacao(request, pk):
    title = 'Adicionar Critério de Avaliação'
    edital = get_object_or_404(Edital, pk=pk)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = CriterioAvaliacaoForm(data=request.POST, edital=edital)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.save()
            return httprr('..', 'Critério de avaliação adicionado com sucesso.')
    else:
        form = CriterioAvaliacaoForm(edital=edital)

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def remover_criterio_avaliacao(request, pk):
    criterio = get_object_or_404(CriterioAvaliacao, pk=pk)
    if not criterio.pode_ser_removido():
        return httprr('..', 'Critério de avaliação não pode ser removido, pois existem avaliações feitas para esse critério.', tag='error')
    edital = criterio.edital
    tem_permissao_acesso_edital(request, edital)
    criterio.delete()

    return httprr(f'/projetos/edital/{edital.id}/?tab=criterios_avaliacao', 'Critério de avaliação removido com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def editar_criterio_avaliacao(request, pk):
    title = 'Editar Critério de Avaliação'
    criterio = get_object_or_404(CriterioAvaliacao, pk=pk)
    tem_permissao_acesso_edital(request, criterio.edital)
    if request.method == 'POST':
        form = CriterioAvaliacaoForm(data=request.POST, instance=criterio, edital=criterio.edital)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Critério de avaliação editado com sucesso.')
    else:
        form = CriterioAvaliacaoForm(instance=criterio, edital=criterio.edital)

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def adicionar_anexo_auxiliar(request, edital_id):
    title = 'Adicionar Anexo'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = EditalAnexoAuxiliarForm(data=request.POST)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.save()
            return httprr('..', 'Anexo adicionado com sucesso.')
    else:
        form = EditalAnexoAuxiliarForm()

    return locals()


@rtr()
@permission_required('projetos.view_edital')
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
            return httprr(f'/projetos/edital/{edital.id}/?tab=anexos_edital', 'Anexo adicionado com sucesso.')
    else:
        form = EditalAnexoForm(edital=edital)

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def remover_anexo(request, anexo_id):
    anexo = get_object_or_404(EditalAnexo, pk=anexo_id)
    edital = anexo.edital
    tem_permissao_acesso_edital(request, anexo.edital)
    anexo.delete()

    return httprr(f'/projetos/edital/{edital.id}/?tab=anexos_edital', 'Anexo removido com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def remover_anexo_auxiliar(request, anexo_id):
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    edital = anexo.edital
    tem_permissao_acesso_edital(request, edital)
    anexo.delete()

    return httprr(f'/projetos/edital/{edital.id}/?tab=anexos_edital', 'Anexo removido com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def editar_anexo(request, anexo_id):
    anexo = get_object_or_404(EditalAnexo, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
    title = 'Editar Anexo do Projeto'
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
@permission_required('projetos.view_edital')
def editar_anexo_auxiliar(request, anexo_id):
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
    title = 'Editar Anexo do Edital'
    if request.method == 'POST':
        form = EditalAnexoAuxiliarForm(data=request.POST, instance=anexo)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Anexo editado com sucesso.')
    else:
        form = EditalAnexoAuxiliarForm(instance=anexo)

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def adicionar_oferta_projeto(request, edital_id):
    title = 'Adicionar Oferta de Projeto'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    eh_fomento_interno = edital.eh_fomento_interno()
    if request.method == 'POST':
        if eh_fomento_interno:
            form = OfertaProjetoForm(data=request.POST, edital=edital)
        else:
            form = OfertaProjetoFormMultiplo(data=request.POST)
        if form.is_valid():
            if eh_fomento_interno:
                o = form.save(False)
                if edital.forma_selecao == Edital.GRUPO:
                    o.qtd_aprovados = 0
                if edital.forma_selecao != Edital.CAMPUS:
                    o.qtd_selecionados = 0
                o.edital = edital
                o.save()
                form.save_m2m()
                return httprr('..', 'Oferta adicionada com sucesso.')
            else:
                campi = form.cleaned_data['campi']
                for campus in campi:
                    qs = OfertaProjeto.objects.filter(edital=edital, uo=campus)
                    if qs.exists():
                        oferta = qs[0]
                    else:
                        oferta = OfertaProjeto()
                    oferta.edital = edital
                    oferta.uo = campus
                    oferta.save()
                return httprr(f'/projetos/edital/{edital.id}/?tab=oferta_por_campus', 'Oferta adicionada com sucesso.')
    else:
        if eh_fomento_interno:
            form = OfertaProjetoForm(edital=edital)
        else:
            form = OfertaProjetoFormMultiplo()

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def remover_oferta_projeto(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    oferta = get_object_or_404(OfertaProjeto, pk=oferta_projeto_id, edital=edital)
    oferta.delete()

    return httprr(f'/projetos/edital/{edital.id}/?tab=oferta_por_campus', 'Oferta removida com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def editar_oferta_projeto(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    title = 'Editar Plano de Oferta por Campus'
    oferta = get_object_or_404(OfertaProjeto, pk=oferta_projeto_id, edital=edital)
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
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_desembolso(request, projeto_id):
    title = 'Adicionar Desembolso'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
    else:
        raise PermissionDenied


def tem_permissao(request, projeto, pode_auxiliar=True):
    eh_auxiliar = False
    if pode_auxiliar:
        eh_auxiliar = projeto.auxiliar and projeto.auxiliar == request.user.get_vinculo()
    is_responsavel = projeto.is_responsavel(request.user) or projeto.is_gerente_sistemico()
    if not is_responsavel and not eh_auxiliar:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_desembolso(request, desembolso_id):
    title = 'Editar Desembolso'
    desembolso = get_object_or_404(Desembolso, pk=desembolso_id)
    projeto = desembolso.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = DesembolsoForm(data=request.POST, instance=desembolso)
            if form.is_valid():
                o = form.save(False)
                o.save()
                return httprr('..', 'Desembolso editado com sucesso.')
        else:
            form = DesembolsoForm(instance=desembolso)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def remover_desembolso(request, desembolso_id):
    desembolso = get_object_or_404(Desembolso, pk=desembolso_id)
    projeto = desembolso.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        url = f'/projetos/projeto/{projeto.id}/?tab=plano_desembolso'
        desembolso.delete()

        return httprr(url, 'Desembolso removido com sucesso.')
    else:
        raise PermissionDenied


def salvar_arquivo(projeto_anexo, arquivo_up, vinculo, request):
    arquivo_up.seek(0)
    content = arquivo_up.read()
    nome = arquivo_up.name
    if projeto_anexo.arquivo:
        arquivo = projeto_anexo.arquivo
    else:
        arquivo = Arquivo()
    arquivo.save(nome, vinculo)
    projeto_anexo.arquivo = arquivo
    projeto_anexo.save()
    arquivo.store(request.user, content)

    return arquivo


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def upload_anexo(request, anexo_id):
    title = 'Upload de Arquivo'
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    projeto = anexo.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = UploadArquivoForm(request.POST, request.FILES)
            if form.is_valid():
                arquivo_up = request.FILES['arquivo']
                vinculo = request.user.get_vinculo()
                salvar_arquivo(anexo, arquivo_up, vinculo, request)
                return httprr('..', 'Arquivo enviado com sucesso.')
        else:
            form = UploadArquivoForm()

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_anexo_do_projeto(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = get_object_or_404(Projeto, pk=participacao.projeto.id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = f'Anexos do Participante: {participacao.get_nome()}'
        Participacao.gerar_anexos_do_participante(participacao)
        anexos = ProjetoAnexo.objects.filter(projeto=participacao.projeto, participacao=participacao, anexo_edital__isnull=False)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.view_edital')
def upload_anexo_auxiliar(request, anexo_id):
    title = 'Upload de Arquivo'
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
    if request.method == 'POST':
        form = UploadArquivoForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo_up = request.FILES['arquivo']
            arquivo_up.seek(0)
            content = arquivo_up.read()
            nome = arquivo_up.name
            vinculo = request.user.get_vinculo()
            if anexo.arquivo:
                arquivo = anexo.arquivo
            else:
                arquivo = Arquivo()
            arquivo.save(nome, vinculo)
            anexo.arquivo = arquivo
            anexo.save()
            arquivo.store(request.user, content)
            return httprr(f'/projetos/edital/{anexo.edital.id}/', 'Arquivo enviado com sucesso.')
    else:
        form = UploadArquivoForm()

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def upload_edital(request, edital_id):
    title = 'Adicionar Edital'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)

    form = UploadArquivoForm(request.POST or None, request.FILES or None, edital=edital)
    if form.is_valid():
        arquivo_up = request.FILES.get('arquivo')
        if arquivo_up:
            novo_arquivo = EditalArquivo()
            novo_arquivo.edital = edital
            novo_arquivo.arquivo = arquivo_up
            novo_arquivo.data_cadastro = datetime.datetime.now()
            novo_arquivo.vinculo_autor = request.user.get_vinculo()
            novo_arquivo.save()
        if form.cleaned_data.get('documento'):
            edital.id_documento_edital = form.cleaned_data.get('documento').id
            edital.save()
            novo_arquivo = EditalArquivo()
            novo_arquivo.edital = edital
            novo_arquivo.id_documento_edital = form.cleaned_data.get('documento').id
            novo_arquivo.data_cadastro = datetime.datetime.now()
            novo_arquivo.vinculo_autor = request.user.get_vinculo()
            novo_arquivo.save()
        return httprr(f'/projetos/edital/{edital.id}/', 'Arquivo enviado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def visualizar_arquivo(request, arquivo_id):
    arquivo = get_object_or_404(Arquivo, id=arquivo_id)
    content = arquivo.load(request.user)
    if content:
        response = HttpResponse(content, content_type=arquivo.get_content_type(content))
        response['Content-Disposition'] = f'inline; filename={get_valid_filename(arquivo.nome)}'
        return response
    else:
        return HttpResponse('O arquivo solicitado foi adulterado ou não existe.')


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def avaliar_conclusao_projeto(request: HttpRequest, registro_id: int) -> dict | HttpResponse:
    title = 'Validação da Conclusão do Projeto'
    registro = get_object_or_404(RegistroConclusaoProjeto, pk=registro_id)
    # mesmo estado em que a aba oferece "Emitir Parecer" (Projeto.pode_emitir_parecer): finalizado e ainda sem parecer
    aguardando_parecer = registro.projeto.data_finalizacao_conclusao and not registro.dt_avaliacao
    eh_monitor_ou_gerente = request.user.get_vinculo() == registro.projeto.vinculo_monitor or request.user.has_group_cached(
        'Gerente Sistêmico de Extensão'
    )
    if aguardando_parecer and eh_monitor_ou_gerente:
        form = ValidacaoConclusaoProjetoForm(request.POST or None, registro=registro)
        if form.is_valid():
            obs = form.cleaned_data['obs']

            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.obs_avaliador = obs
            registro.save()
            registro.projeto.concluir()
            return httprr('..', 'Conclusão do projeto registrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_foto(request, projeto_id):
    title = 'Adicionar Foto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = FotoProjetoForm(data=request.POST, files=request.FILES)
            if form.is_valid():
                o = form.save(False)
                o.projeto = projeto
                o.save()
                return httprr('..', 'Foto adicionada com sucesso.')
        else:
            form = FotoProjetoForm()

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def remover_foto(request, foto_id):
    foto = get_object_or_404(FotoProjeto, pk=foto_id)
    projeto = foto.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        projeto_id = foto.projeto.id
        foto.delete()

        return httprr(f'/projetos/projeto/{projeto_id}/?tab=fotos', 'Foto removida com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_projeto(request, edital_id):
    title = 'Adicionar Projeto'
    edital = get_object_or_404(Edital, pk=edital_id)
    retorno = pode_submeter_novo_projeto(request, edital)
    if retorno:
        return httprr('/projetos/editais_abertos/', retorno, tag='error')
    vinculo_do_usuario = request.user.get_vinculo()
    if edital.atingiu_limite_submissoes(vinculo_do_usuario):
        return httprr('/projetos/editais_abertos/', 'Você já submeteu a quantidade máxima permitida de projetos neste edital.', tag='error')
    instance = Projeto()
    instance.edital = edital
    instance.vinculo_coordenador = vinculo_do_usuario
    form = ProjetoExtensaoForm(request.POST or None, request.FILES or None, instance=instance, request=request, edicao=False)
    execucao_de_testes = running_tests()
    if not execucao_de_testes:
        termos = inlineformset_factory(
            Projeto,
            TermoParceriaAdesao,
            fields=['descricao', 'arquivo'],
            can_delete=True,
            extra=0,
            form=TermoParceriaAdesaoForm,
            formset=TermoParceriaAdesaoInlineFormSet,
            min_num=0,
        )
        formset = termos(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if execucao_de_testes:
            formset_valido = True
        else:
            formset_valido = formset.is_valid()
        if form.is_valid() and formset_valido:
            if form.cleaned_data.get('deseja_receber_bolsa'):
                instance.bolsa_coordenador = form.cleaned_data['deseja_receber_bolsa']
            else:
                instance.bolsa_coordenador = False
            form.save()
            if not execucao_de_testes and form.cleaned_data.get('executado_com_parceria') == 'True':
                formset.instance = form.instance
                formset.save()

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
            Participacao.gerar_anexos_do_participante(p)
            if p.exige_anuencia():
                servidor = p.vinculo_pessoa.relacionamento
                chefes = servidor.chefes_na_data(datetime.datetime.now().date()).order_by('funcao')
                if chefes:
                    p.responsavel_anuencia = chefes[0]
                    p.save()
            p.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_INSERIDO, data_evento=p.projeto.inicio_execucao)

            projeto_id = (
                Participacao.objects.filter(projeto__edital__id=edital_id, vinculo_pessoa=vinculo_do_usuario, responsavel=True)
                .order_by('-id')[0]
                .projeto.id
            )
            historico = ProjetoHistoricoDeEnvio()
            historico.projeto = instance
            historico.parecer_devolucao = 'Projeto cadastrado. Situação: em edição.'
            historico.data_operacao = datetime.datetime.now()
            historico.operador = request.user.get_relacionamento()
            historico.save()
            return httprr(f'/projetos/projeto/{projeto_id}/', 'Projeto cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_projeto(request, projeto_id):
    title = 'Editar Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.get_periodo() == Projeto.PERIODO_EXECUCAO:
        data_inicio_atual = projeto.inicio_execucao
        data_fim_atual = projeto.fim_execucao
        titulo_atual = projeto.titulo
        form = EditarProjetoEmExecucaoForm(request.POST or None, request.FILES or None, instance=projeto, request=request)
        if form.is_valid():
            if form.cleaned_data.get('executado_com_parceria') != 'True':
                form.instance.termo_parceria_adesao = None
            form.save()
            if form.cleaned_data.get('justificativa_alteracoes'):
                novo_historico = HistoricoAlteracaoPeriodoProjeto()
                novo_historico.projeto = projeto
                novo_historico.inicio_execucao = data_inicio_atual
                novo_historico.fim_execucao = data_fim_atual
                novo_historico.novo_inicio_execucao = form.cleaned_data.get('novo_inicio_execucao')
                novo_historico.novo_fim_execucao = form.cleaned_data.get('novo_fim_execucao')
                novo_historico.justificativa = form.cleaned_data.get('justificativa_alteracoes')
                novo_historico.vinculo_registrado_por = request.user.get_vinculo()
                novo_historico.save()
            if titulo_atual != form.cleaned_data.get('titulo'):
                historico = ProjetoHistoricoDeEnvio()
                historico.projeto = projeto
                historico.data_operacao = datetime.datetime.now()
                if request.user.eh_servidor:
                    historico.operador = request.user.get_relacionamento()
                historico.parecer_devolucao = (
                    f'Alteração do título de {titulo_atual} para {form.cleaned_data.get("titulo")} por {request.user.get_relacionamento()}'
                )
                historico.save()
            if form.cleaned_data.get('motivo_alteracao_interesse_custeio'):
                historico = HistoricoInteresseCusteioProjeto()
                historico.projeto = projeto
                historico.tinha_interesse = projeto.tem_interesse_cartao_pesquisador
                historico.tem_interesse = not projeto.tem_interesse_cartao_pesquisador
                historico.justificativa = form.cleaned_data.get('motivo_alteracao_interesse_custeio')
                historico.cadastrado_por = request.user.get_vinculo()
                historico.save()
            return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto editado com sucesso.')

    elif projeto.get_periodo() == Projeto.PERIODO_INSCRICAO:
        form = ProjetoExtensaoForm(request.POST or None, request.FILES or None, instance=projeto, request=request, edicao=True)
        if request.method == 'POST':
            if form.is_valid():
                if form.cleaned_data.get('executado_com_parceria') != 'True':
                    form.instance.termo_parceria_adesao = None
                form.save()
                part = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), projeto=projeto)
                if part.exists() and part[0].carga_horaria != form.cleaned_data.get('carga_horaria'):
                    p = part[0]
                    p.carga_horaria = form.cleaned_data.get('carga_horaria')
                    p.save()
                    p.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_EDICAO_SERVIDOR, data_evento=form.cleaned_data.get('data'))

                return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto editado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_caracterizacao_beneficiario(request, projeto_id):
    title = 'Adicionar Caracterização do Beneficiário'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        caracterizacao_beneficiario = CaracterizacaoBeneficiario()
        caracterizacao_beneficiario.projeto = projeto
        form = CaracterizacaoBeneficiarioForm(request.POST or None, instance=caracterizacao_beneficiario, atendida=False, edicao_inscricao=True)
        if form.is_valid():
            form.save()
            return httprr('..', 'Caracterização do beneficiário adicionada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_caracterizacao_beneficiario(request, caracterizacao_beneficiario_id):
    title = 'Adicionar Caracterização do Beneficiário'
    caracterizacao_beneficiario = get_object_or_404(CaracterizacaoBeneficiario, pk=caracterizacao_beneficiario_id)
    projeto = caracterizacao_beneficiario.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        edicao_inscricao = True
        if projeto.get_status() == Projeto.STATUS_EM_EXECUCAO:
            edicao_inscricao = False
        form = CaracterizacaoBeneficiarioForm(request.POST or None, instance=caracterizacao_beneficiario, edicao_inscricao=edicao_inscricao)
        if form.is_valid():
            form.save()
            return httprr('..', 'Caracterização do beneficiário editada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def remover_caracterizacao_beneficiario(request, caracterizacao_beneficiario_id):
    caracterizacao_beneficiario = get_object_or_404(CaracterizacaoBeneficiario, pk=caracterizacao_beneficiario_id)
    projeto = caracterizacao_beneficiario.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        caracterizacao_beneficiario.delete()

        return httprr(f'/projetos/projeto/{projeto.id}/?tab=caracterizacao_beneficiario', 'Caracterização do Beneficiário removida com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def pre_selecionar(request: HttpRequest, projeto_id: int, rejeitar: bool | None = None, url: str | None = None) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    edital = projeto.edital
    if not url:
        url = request.META.get('HTTP_REFERER', '.')
    if not projeto.edital.is_periodo_pre_selecao():
        raise PermissionDenied

    if projeto.data_conclusao_planejamento is None:
        return httprr(url, 'Impossível realizar essa operação, projeto não foi enviado.', tag='error')

    if projeto.tem_aceite_pendente():
        return httprr(
            f'/projetos/projetos_nao_avaliados/{projeto.edital.id}/', 'Este projeto possui aceite de termo de compromisso pendente.', tag='error'
        )

    # O papel (`is_pre_avaliador`), o estado e a cota que a tela exige para oferecer a ação (#17579).
    if not projeto.pode_receber_pre_avaliacao(rejeitar):
        raise PermissionDenied

    vinculo_logado = request.user.get_vinculo()
    try:
        avaliacao = PreSelecao.objects.get(projeto=projeto, avaliador=vinculo_logado)
    except Exception:
        avaliacao = None
    form = PreSelecaoForm(request.POST or None, projeto=projeto, avaliacao=avaliacao, vinculo=vinculo_logado, url=url)
    title = f'Pré-avaliar - {projeto.titulo}'
    if not edital.criteriopreselecao_set.exists() or form.is_valid():
        if form.is_valid():
            form.save()
            rejeitar = form.cleaned_data.get('pre_aprovado') == 'False'
            url = form.cleaned_data.get('url')
        if not projeto.vinculo_autor_pre_avaliacao:
            projeto.vinculo_autor_pre_avaliacao = vinculo_logado
        projeto.vinculo_monitor = projeto.vinculo_autor_pre_avaliacao
        projeto.data_pre_avaliacao = datetime.date.today()

        # A decisão é a pedida (rota ou ficha), não o inverso do estado atual (#17579).
        if rejeitar:
            projeto.pre_aprovado = False
            if projeto.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
                projeto.aprovado = False
                projeto.data_avaliacao = None
                projeto.vinculo_autor_avaliacao = None
                projeto.pontuacao = 0
        else:
            if (
                edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO
                and edital.forma_selecao == Edital.GERAL
                and Projeto.objects.filter(edital=edital, aprovado=True).count() >= edital.qtd_projetos_selecionados
            ):
                return httprr(
                    f'/projetos/projetos_nao_avaliados/{edital.id}/',
                    'O número máximo de projetos aprovados para este edital já foi atingido.',
                    tag='error',
                )

            projeto.pre_aprovado = True
            if projeto.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO and not projeto.edital.exige_etapa_avaliacao:
                projeto.aprovado = True
                projeto.data_avaliacao = datetime.date.today()
                projeto.vinculo_autor_avaliacao = request.user.get_vinculo()
                projeto.pontuacao = 0
        projeto.save()

        return httprr(url, 'Projeto pré-avaliado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def historico_equipe(request, participacao_id):
    title = 'Histórico da Participação'
    eh_sistemico = request.user.has_perm('projetos.pode_gerenciar_edital')
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if eh_sistemico:
        historico = HistoricoEquipe.objects.filter(participante=participacao_id).order_by('id').exclude(movimentacao='Ativado')
    else:
        historico = HistoricoEquipe.objects.filter(ativo=True, participante=participacao_id).order_by('id').exclude(movimentacao='Ativado')
    como_coordenador = historico.filter(categoria=HistoricoEquipe.COORDENADOR)
    como_membro = historico.filter(categoria=HistoricoEquipe.MEMBRO)
    tipo_vinculo = TipoVinculo()
    orientacoes = None
    if not participacao.is_servidor():
        orientacoes = HistoricoOrientacaoProjeto.objects.filter(orientado=participacao).order_by('-id')

    return locals()


def projeto_com_pendencias_para_envio(projeto_id):
    mensagem_erro = ''
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    edital = projeto.edital
    metas = Meta.objects.filter(projeto_id=projeto_id)
    tem_plano_aplicacao = ItemMemoriaCalculo.objects.filter(projeto_id=projeto_id)
    tem_caracterizacao = CaracterizacaoBeneficiario.objects.filter(projeto_id=projeto_id).exists()
    tem_desembolso = True
    tem_desembolso_valor_faltando = False
    for memoria_calculo in tem_plano_aplicacao:
        registros_desembolso = Desembolso.objects.filter(item=memoria_calculo)
        if not registros_desembolso.exists():
            tem_desembolso = False
        if registros_desembolso.exists() and registros_desembolso.aggregate(total=Sum('valor'))['total'] != memoria_calculo.get_subtotal():
            tem_desembolso_valor_faltando = True

    if edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
        tem_desembolso = True
        tem_plano_aplicacao = True
    if projeto.titulo.isupper():
        mensagem_erro = mensagem_erro + '* O título do projeto não pode ser escrito com todas as letras em caixa alta.</br>'
    if edital.participa_aluno and not projeto.tem_aluno():
        if edital.permite_indicacao_tardia_equipe:
            mensagem_erro = (
                mensagem_erro
                + '* O projeto precisa da inclusão de um aluno na equipe ou da indicação de que haverá pelo menos um aluno na equipe.</br>'
            )
        else:
            mensagem_erro = mensagem_erro + '* O projeto deve ter pelo menos um aluno na equipe.</br>'

    participacao_coordenador = Participacao.objects.filter(projeto=projeto, responsavel=True)[0]
    if participacao_coordenador.exige_anuencia() and not participacao_coordenador.anuencia:
        mensagem_erro = mensagem_erro + '* O coordenador do projeto precisa da anuência da chefia.</br>'
    if edital.exige_nivel_superior and not participacao_coordenador.tem_nivel_superior():
        mensagem_erro = mensagem_erro + '* Este edital exige que o coordenador possua nível superior.</br>'
    if (
        edital.restringe_prof_temporario
        and participacao_coordenador.vinculo_pessoa.relacionamento.id in Servidor.objects.temporarios().values_list('id', flat=True)
        and not projeto.tem_servidores_efetivos_ativos()
    ):
        mensagem_erro = (
            mensagem_erro
            + '* Este edital exige que, se o coordenador for professor visitante/substituto, a equipe do projeto possua pelo menos um servidor efetivo.</br>'
        )
    if projeto.eh_fomento_interno():
        if not tem_desembolso:
            mensagem_erro = mensagem_erro + '* Cadastre o Plano de Desembolso para cada Item de Mémoria de Cálculo antes de enviar o Projeto.</br>'
        if tem_desembolso_valor_faltando:
            mensagem_erro = (
                mensagem_erro + '* A soma dos valores dos desembolsos tem que ser igual ao total orçado da memória de cálculo correspondente.</br>'
            )
        if not tem_plano_aplicacao and Recurso.objects.filter(edital=edital, valor__gt=0).exists():
            mensagem_erro = mensagem_erro + '* Cadastre o Plano de Aplicação antes de enviar o Projeto.</br>'

        if not tem_caracterizacao:
            mensagem_erro = mensagem_erro + '* Cadastre a Caracterização dos Beneficiários antes de enviar o Projeto.</br>'

        if not metas:
            mensagem_erro = mensagem_erro + '* Cadastre as Metas/Atividades antes de enviar o Projeto.</br>'

        if edital.atividade_todo_mes and not projeto.tem_atividade_todo_mes():
            mensagem_erro = mensagem_erro + '* O projeto deve ter pelo menos uma atividade sendo executada em cada mês.</br>'
        else:
            tem_atividade = False
            for meta in metas:
                atividade = Etapa.objects.filter(meta_id=meta.id)
                if atividade:
                    tem_atividade = True
            if not tem_atividade:
                mensagem_erro = mensagem_erro + '* Cadastre as Atividades de cada Meta antes de enviar o Projeto.</br>'
    if edital.impedir_projeto_sem_anexo and (
        not ProjetoAnexo.objects.filter(projeto=projeto).exists() and not TermoParceriaAdesao.objects.filter(projeto=projeto).exists()
    ):
        mensagem_erro = mensagem_erro + '* O projeto deve ter pelo menos um arquivo anexo ou termo de adesão.</br>'
    if edital.impede_com_pendencia_anuencia and projeto.tem_anuencia_pendente():
        mensagem_erro = mensagem_erro + '* O projeto só pode ser enviado após registro da anuência da chefia.</br>'
    if edital.impede_com_pendencia_termo and projeto.tem_aceite_pendente():
        mensagem_erro = mensagem_erro + '* O projeto só pode ser enviado após o registro de aceite de todos os termos de compromisso.</br>'
    if edital.forma_selecao == Edital.GRUPO and not projeto.grupo:
        mensagem_erro = (
            mensagem_erro
            + '* O projeto só pode ser enviado após indicar em qual grupo o projeto irá concorrer. Informe o grupo através do botão "Editar Projeto" na aba "Dados do projeto".</br>'
        )
    return mensagem_erro


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def concluir_planejamento(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    edital = projeto.edital
    if edital.atingiu_limite_submissoes(projeto.vinculo_coordenador):
        return httprr(f'/projetos/projeto/{projeto.id}/', 'Você já submeteu a quantidade máxima permitida de projetos neste edital.', tag='error')

    mensagem_erro = projeto_com_pendencias_para_envio(projeto_id)
    if mensagem_erro != '':
        return httprr(
            f'/projetos/projeto/{projeto.id}/',
            mark_safe('Atenção! O projeto não pode ser enviado. Resolva as pendências descritas abaixo!'),
            tag='error',
        )
    projeto.data_conclusao_planejamento = datetime.datetime.now()
    if not projeto.vinculo_coordenador:
        projeto.vinculo_coordenador = Participacao.objects.filter(projeto=projeto, responsavel=True)[0].vinculo_pessoa
    projeto.save()
    historico_projeto = ProjetoHistoricoDeEnvio()
    historico_projeto.projeto = projeto
    historico_projeto.data_operacao = datetime.datetime.now()
    historico_projeto.situacao = ProjetoHistoricoDeEnvio.ENVIADO
    historico_projeto.operador = request.user.get_relacionamento()
    historico_projeto.save()

    return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto enviado com sucesso.')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def finalizar_conclusao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_interno = projeto.eh_fomento_interno()
    mensagem_erro = ''
    if not projeto.data_finalizacao_conclusao:
        if eh_interno:
            tem_permissao(request, projeto, pode_auxiliar=False)
        else:
            if not (projeto.vinculo_monitor == request.user.get_vinculo()):
                raise PermissionDenied
        if projeto.tem_pendencias():
            return httprr(
                f'/projetos/projeto/{projeto.id}/?tab=pendencias', 'O projeto não pode ser finalizado. Verifique as pendências.', tag='error'
            )

        registro = RegistroConclusaoProjeto.objects.filter(projeto=projeto).first()
        if registro is None:
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=conclusao', 'Registre a conclusão antes de finalizar.', tag='error')
        if not eh_interno:
            title = 'Finalizar Projeto'
            if request.method == 'POST':
                form = RegistroConclusaoProjetoObsForm(data=request.POST, instance=registro)
                if form.is_valid():
                    registro = form.save(False)
                    registro.projeto = projeto
                    registro.dt_avaliacao = datetime.datetime.now()
                    registro.avaliador = request.user.get_relacionamento()
                    registro.save()
                    projeto.concluido = True
                    projeto.save()
                    for membro in Participacao.objects.filter(projeto=projeto, ativo=True, vinculo_pessoa__isnull=False):
                        membro.gerar_atividade_curricular_extensao()
            else:
                form = RegistroConclusaoProjetoObsForm(instance=registro)

        if eh_interno or registro.avaliador:
            projeto.data_finalizacao_conclusao = datetime.datetime.now()
            projeto.save()
            historico = ProjetoHistoricoDeEnvio()
            historico.projeto = projeto
            historico.data_operacao = datetime.datetime.now()
            historico.situacao = ProjetoHistoricoDeEnvio.FINALIZADO
            historico.operador = request.user.get_relacionamento()
            historico.save()
            movimentacoes_sem_data_saida = HistoricoEquipe.objects.filter(ativo=True, projeto=projeto, data_movimentacao_saida__isnull=True)
            if movimentacoes_sem_data_saida:
                for movimentacao in movimentacoes_sem_data_saida:
                    movimentacao.data_movimentacao_saida = datetime.datetime.today()
                    movimentacao.save()

            titulo = '[SUAP] Extensão: Finalização de Projeto'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Finalização de Projeto</h2>'
                f"<p>O Projeto '{projeto.titulo}' foi finalizado pelo Coordenador de Extensão. Acesse o SUAP para mais detalhes.</p>"
            )

            for membro in Participacao.objects.filter(projeto=projeto, ativo=True, vinculo_pessoa__isnull=False):
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [membro.vinculo_pessoa])
                membro.gerar_atividade_curricular_extensao()

            return httprr(f'/projetos/projeto/{projeto.id}/', 'Conclusão finalizada com sucesso.')
    else:
        return httprr(f'/projetos/projeto/{projeto.id}/', 'Este projeto já foi concluído.', tag='error')

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def gerenciar_historico_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    historico = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto_id).order_by('data_operacao')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
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
        o.save()
        projeto.data_conclusao_planejamento = None
        if projeto.edital.tipo_edital == Edital.EXTENSAO:
            projeto.pre_aprovado = False
            projeto.aprovado = False
            projeto.data_pre_avaliacao = None
            projeto.data_avaliacao = None
            projeto.vinculo_autor_pre_avaliacao = None
            projeto.vinculo_autor_avaliacao = None
        projeto.save()
        responsavel = Participacao.objects.get(projeto__id=projeto_id, responsavel=True)
        titulo = '[SUAP] Extensão: Devolução de Projeto'
        texto = f"<h1>Extensão</h1><h2>Devolução de Projeto</h2><p>O Projeto '{projeto.titulo}' foi devolvido pelo Coordenador de Extensão.</p>"
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])
        return httprr('.', 'Devolução do projeto registrada com sucesso.')

    else:
        form = ProjetoHistoricoDeEnvioForm()

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
def relatorio_dimensao_extensao(request):
    # ----------------------------------------------------
    quantidade_projetos = []
    quantidade_participantes = []
    participantes_por_area_tematica = []
    alunos_por_modalidade = []
    coordenadores_por_categoria = []
    # ----------------------------------------------------
    escolheu_ano = False
    form = RelatorioDimensaoExtensaoForm(data=request.GET or None, request=request)
    soma_total = 0
    soma_aprovados = 0
    TWOPLACES = Decimal(10) ** -2
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        campus_relatorio = get_uo(request.user)
    else:
        campus_relatorio = None
    hoje = datetime.datetime.now()
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            ano = int(form.cleaned_data['ano'])
            escolheu_ano = True
            editais = Edital.objects.filter(
                id__in=Projeto.objects.filter(inicio_execucao__year=ano)
                .filter(Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False))
                .values_list('edital', flat=True)
            )
            if form.cleaned_data.get('campus'):
                campus_escolhido = form.cleaned_data.get('campus')
                campus_relatorio = get_object_or_404(UnidadeOrganizacional, pk=campus_escolhido.id)
            if campus_relatorio:
                editais_tem_oferta = OfertaProjeto.objects.filter(uo=campus_relatorio).values_list('edital', flat=True)
                editais = editais.filter(id__in=editais_tem_oferta).order_by('inicio_inscricoes')

            if form.cleaned_data.get('tipo_edital'):
                if form.cleaned_data.get('tipo_edital') == 'Edital de Campus':
                    editais = editais.filter(campus_especifico=True)
                elif form.cleaned_data.get('tipo_edital') == 'Edital Sistêmico':
                    editais = editais.filter(campus_especifico=False)

            if form.cleaned_data.get('tipo_fomento'):
                editais = editais.filter(tipo_fomento=form.cleaned_data.get('tipo_fomento'))

            projetos_area_tematica_comunicacao_total = 0
            projetos_area_tematica_cultura_total = 0
            projetos_area_tematica_direito_total = 0
            projetos_area_tematica_educacao_total = 0
            projetos_area_tematica_meio_ambiente_total = 0
            projetos_area_tematica_saude_total = 0
            projetos_area_tematica_tecnologia_total = 0
            projetos_area_tematica_trabalho_total = 0
            projetos_area_tematica_multidisciplinar_total = 0
            projetos_area_tematica_outros_total = 0
            projetos_area_tematica_total = 0

            projetos_area_tematica_comunicacao_aprovados = 0
            projetos_area_tematica_cultura_aprovados = 0
            projetos_area_tematica_direito_aprovados = 0
            projetos_area_tematica_educacao_aprovados = 0
            projetos_area_tematica_meio_ambiente_aprovados = 0
            projetos_area_tematica_saude_aprovados = 0
            projetos_area_tematica_tecnologia_aprovados = 0
            projetos_area_tematica_trabalho_aprovados = 0
            projetos_area_tematica_multidisciplinar_aprovados = 0
            projetos_area_tematica_outros_aprovados = 0
            projetos_area_tematica_aprovados = 0

            total_membros_edital_geral = 0
            total_membros_edital_alunos_bolsistas = 0
            total_membros_edital_alunos_voluntarios = 0
            total_membros_edital_docentes_bolsistas = 0
            total_membros_edital_docentes_voluntarios = 0
            total_membros_edital_tecnicos_adm_bolsistas = 0
            total_membros_edital_tecnicos_adm_voluntarios = 0

            area_tematica_total_docente_bols = 0
            area_tematica_total_docente_vol = 0
            area_tematica_total_tec_adm_bols = 0
            area_tematica_total_tec_adm_vol = 0
            area_tematica_total_aluno_bols = 0
            area_tematica_total_aluno_vol = 0
            area_tematica_total_geral = 0

            for edital in editais:
                # ----------------------------------------------------
                projetos_por_edital_total = Projeto.objects.filter(edital=edital, inicio_execucao__year=ano)
                if campus_relatorio:
                    projetos_por_edital_total = projetos_por_edital_total.filter(uo=campus_relatorio)

                projetos_por_edital_total = projetos_por_edital_total.filter(
                    Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                )
                projetos_por_edital_aprovados = projetos_por_edital_total.filter(
                    aprovado=True, edital__divulgacao_selecao__lt=hoje
                ) | projetos_por_edital_total.filter(aprovado=True, edital__tipo_fomento=Edital.FOMENTO_EXTERNO)
                soma_total = soma_total + projetos_por_edital_total.count()
                soma_aprovados = soma_aprovados + projetos_por_edital_aprovados.count()
                # ----------------------------------------------------
                comunicacao_total = projetos_por_edital_total.filter(area_tematica__descricao='Comunicação').count()
                cultura_total = projetos_por_edital_total.filter(area_tematica__descricao='Cultura').count()
                direito_total = projetos_por_edital_total.filter(area_tematica__descricao='Direitos Humanos e Justiça').count()
                educacao_total = projetos_por_edital_total.filter(area_tematica__descricao='Educação').count()
                meio_ambiente_total = projetos_por_edital_total.filter(area_tematica__descricao='Meio Ambiente').count()
                saude_total = projetos_por_edital_total.filter(area_tematica__descricao='Saúde').count()
                tecnologia_total = projetos_por_edital_total.filter(area_tematica__descricao='Tecnologia e Produção').count()
                trabalho_total = projetos_por_edital_total.filter(area_tematica__descricao='Trabalho').count()
                multidisciplinar_total = projetos_por_edital_total.filter(area_tematica__descricao='Multidisciplinar').count()

                projetos_area_tematica_comunicacao_total = projetos_area_tematica_comunicacao_total + comunicacao_total
                projetos_area_tematica_cultura_total = projetos_area_tematica_cultura_total + cultura_total
                projetos_area_tematica_direito_total = projetos_area_tematica_direito_total + direito_total
                projetos_area_tematica_educacao_total = projetos_area_tematica_educacao_total + educacao_total
                projetos_area_tematica_meio_ambiente_total = projetos_area_tematica_meio_ambiente_total + meio_ambiente_total
                projetos_area_tematica_saude_total = projetos_area_tematica_saude_total + saude_total
                projetos_area_tematica_tecnologia_total = projetos_area_tematica_tecnologia_total + tecnologia_total
                projetos_area_tematica_trabalho_total = projetos_area_tematica_trabalho_total + trabalho_total
                projetos_area_tematica_multidisciplinar_total = projetos_area_tematica_multidisciplinar_total + multidisciplinar_total

                # ----------------------------------------------------
                comunicacao_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Comunicação').count()
                cultura_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Cultura').count()
                direito_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Direitos Humanos e Justiça').count()
                educacao_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Educação').count()
                meio_ambiente_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Meio Ambiente').count()
                saude_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Saúde').count()
                tecnologia_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Tecnologia e Produção').count()
                trabalho_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Trabalho').count()
                multidisciplinar_aprovados = projetos_por_edital_aprovados.filter(area_tematica__descricao='Multidisciplinar').count()
                area_tematica_total = comunicacao_total + cultura_total + direito_total + educacao_total + meio_ambiente_total
                area_tematica_total = area_tematica_total + saude_total + tecnologia_total + trabalho_total + multidisciplinar_total
                area_tematica_aprovados = comunicacao_aprovados + cultura_aprovados + direito_aprovados + educacao_aprovados + meio_ambiente_aprovados
                area_tematica_aprovados = (
                    area_tematica_aprovados + saude_aprovados + tecnologia_aprovados + trabalho_aprovados + multidisciplinar_aprovados
                )

                outros_total = projetos_por_edital_total.count() - area_tematica_total

                projetos_area_tematica_outros_total = projetos_area_tematica_outros_total + outros_total

                outros_aprovados = projetos_por_edital_aprovados.count() - area_tematica_aprovados

                projetos_area_tematica_outros_aprovados = projetos_area_tematica_outros_aprovados + outros_aprovados

                projetos_area_tematica_comunicacao_aprovados = projetos_area_tematica_comunicacao_aprovados + comunicacao_aprovados
                projetos_area_tematica_cultura_aprovados = projetos_area_tematica_cultura_aprovados + cultura_aprovados
                projetos_area_tematica_direito_aprovados = projetos_area_tematica_direito_aprovados + direito_aprovados
                projetos_area_tematica_educacao_aprovados = projetos_area_tematica_educacao_aprovados + educacao_aprovados
                projetos_area_tematica_meio_ambiente_aprovados = projetos_area_tematica_meio_ambiente_aprovados + meio_ambiente_aprovados
                projetos_area_tematica_saude_aprovados = projetos_area_tematica_saude_aprovados + saude_aprovados
                projetos_area_tematica_tecnologia_aprovados = projetos_area_tematica_tecnologia_aprovados + tecnologia_aprovados
                projetos_area_tematica_trabalho_aprovados = projetos_area_tematica_trabalho_aprovados + trabalho_aprovados
                projetos_area_tematica_multidisciplinar_aprovados = projetos_area_tematica_multidisciplinar_aprovados + multidisciplinar_aprovados

                projetos_area_tematica_total = projetos_area_tematica_total + projetos_por_edital_total.count()
                projetos_area_tematica_aprovados = projetos_area_tematica_aprovados + projetos_por_edital_aprovados.count()
                # ----------------------------------------------------
                quantidade_projetos.append(
                    {
                        'edital': edital,
                        'total': projetos_por_edital_total.count(),
                        'aprovados': projetos_por_edital_aprovados.count(),
                        'comunicacao_total': comunicacao_total,
                        'cultura_total': cultura_total,
                        'direito_total': direito_total,
                        'educacao_total': educacao_total,
                        'meio_ambiente_total': meio_ambiente_total,
                        'saude_total': saude_total,
                        'tecnologia_total': tecnologia_total,
                        'trabalho_total': trabalho_total,
                        'multidisciplinar_total': multidisciplinar_total,
                        'comunicacao_aprovados': comunicacao_aprovados,
                        'cultura_aprovados': cultura_aprovados,
                        'direito_aprovados': direito_aprovados,
                        'educacao_aprovados': educacao_aprovados,
                        'meio_ambiente_aprovados': meio_ambiente_aprovados,
                        'saude_aprovados': saude_aprovados,
                        'tecnologia_aprovados': tecnologia_aprovados,
                        'trabalho_aprovados': trabalho_aprovados,
                        'multidisciplinar_aprovados': multidisciplinar_aprovados,
                        'outros_total': outros_total,
                        'outros_aprovados': outros_aprovados,
                    }
                )
                # ----------------------------------------------------
                bolsistas = Participacao.objects.filter(vinculo='Bolsista', projeto__in=projetos_por_edital_aprovados.values_list('id')).distinct()
                voluntarios = Participacao.objects.filter(
                    vinculo='Voluntário', projeto__in=projetos_por_edital_aprovados.values_list('id')
                ).distinct()

                alunos_bolsistas = Aluno.objects.filter(vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True)).distinct().count()
                alunos_voluntarios = Aluno.objects.filter(vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True)).distinct().count()
                docentes_bolsistas = (
                    Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                    .distinct()
                    .count()
                )
                docentes_voluntarios = (
                    Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                    .distinct()
                    .count()
                )
                tecnicos_adm_bolsistas = (
                    Servidor.objects.filter(
                        ativo=True, vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                    )
                    .distinct()
                    .count()
                )
                tecnicos_adm_voluntarios = (
                    Servidor.objects.filter(
                        ativo=True, vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                    )
                    .distinct()
                    .count()
                )
                # ----------------------------------------------------

                total_membros_edital = (
                    alunos_bolsistas
                    + alunos_voluntarios
                    + docentes_bolsistas
                    + docentes_voluntarios
                    + tecnicos_adm_bolsistas
                    + tecnicos_adm_voluntarios
                )

                total_membros_edital_geral = total_membros_edital_geral + total_membros_edital

                total_membros_edital_alunos_bolsistas = total_membros_edital_alunos_bolsistas + alunos_bolsistas
                total_membros_edital_alunos_voluntarios = total_membros_edital_alunos_voluntarios + alunos_voluntarios

                total_membros_edital_docentes_bolsistas = total_membros_edital_docentes_bolsistas + docentes_bolsistas
                total_membros_edital_docentes_voluntarios = total_membros_edital_docentes_voluntarios + docentes_voluntarios

                total_membros_edital_tecnicos_adm_bolsistas = total_membros_edital_tecnicos_adm_bolsistas + tecnicos_adm_bolsistas
                total_membros_edital_tecnicos_adm_voluntarios = total_membros_edital_tecnicos_adm_voluntarios + tecnicos_adm_voluntarios

                quantidade_participantes.append(
                    {
                        'edital': edital,
                        'alunos_bolsistas': alunos_bolsistas,
                        'alunos_voluntarios': alunos_voluntarios,
                        'docentes_bolsistas': docentes_bolsistas,
                        'docentes_voluntarios': docentes_voluntarios,
                        'tecnicos_adm_bolsistas': tecnicos_adm_bolsistas,
                        'tecnicos_adm_voluntarios': tecnicos_adm_voluntarios,
                        'total_membros_edital': total_membros_edital,
                    }
                )
            # ----------------------------------------------------
            if campus_relatorio:
                projetos_area_tematica = Projeto.objects.filter(uo=campus_relatorio, edital__in=editais.values_list('id'), aprovado=True)
            else:
                projetos_area_tematica = Projeto.objects.filter(edital__in=editais.values_list('id'), aprovado=True)

            bolsistas_comunicacao = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Comunicação'
            ).distinct()
            bolsistas_cultura = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Cultura'
            ).distinct()
            bolsistas_direitos_humanos = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Direitos Humanos e Justiça',
            ).distinct()
            bolsistas_educacao = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Educação'
            ).distinct()
            bolsistas_meio_ambiente = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Meio Ambiente'
            ).distinct()
            bolsistas_saude = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Saúde'
            ).distinct()
            bolsistas_tecnologia_producao = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Tecnologia e Produção',
            ).distinct()
            bolsistas_trabalho = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Trabalho'
            ).distinct()
            bolsistas_multidisciplinar = Participacao.objects.filter(
                vinculo=TipoVinculo.BOLSISTA,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Multidisciplinar',
            ).distinct()

            voluntarios_comunicacao = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Comunicação'
            ).distinct()
            voluntarios_cultura = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Cultura'
            ).distinct()
            voluntarios_direitos_humanos = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Direitos Humanos e Justiça',
            ).distinct()
            voluntarios_educacao = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Educação'
            ).distinct()
            voluntarios_meio_ambiente = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Meio Ambiente',
            ).distinct()
            voluntarios_saude = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Saúde'
            ).distinct()
            voluntarios_tecnologia_producao = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Tecnologia e Produção',
            ).distinct()
            voluntarios_trabalho = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO, projeto__in=projetos_area_tematica.values_list('id'), projeto__area_tematica__descricao='Trabalho'
            ).distinct()
            voluntarios_multidisciplinar = Participacao.objects.filter(
                vinculo=TipoVinculo.VOLUNTARIO,
                projeto__in=projetos_area_tematica.values_list('id'),
                projeto__area_tematica__descricao='Multidisciplinar',
            ).distinct()

            total_alunos_voluntarios_comunicacao = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_comunicacao.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_cultura = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_cultura.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_direitos_humanos = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_direitos_humanos.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_educacao = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_educacao.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_meio_ambiente = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_meio_ambiente.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_saude = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_saude.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_tecnologia_producao = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_tecnologia_producao.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_trabalho = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_trabalho.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_voluntarios_multidisciplinar = (
                Aluno.objects.filter(vinculos__id__in=voluntarios_multidisciplinar.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )

            total_alunos_bolsistas_comunicacao = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_comunicacao.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_cultura = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_cultura.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_direitos_humanos = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_direitos_humanos.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_educacao = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_educacao.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_meio_ambiente = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_meio_ambiente.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_saude = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_saude.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_tecnologia_producao = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_tecnologia_producao.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_trabalho = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_trabalho.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )
            total_alunos_bolsistas_multidisciplinar = (
                Aluno.objects.filter(vinculos__id__in=bolsistas_multidisciplinar.values_list('vinculo_pessoa', flat=True)).distinct().count()
            )

            total_docentes_voluntarios_comunicacao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_comunicacao.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_voluntarios_cultura = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios_cultura.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_voluntarios_direitos_humanos = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_direitos_humanos.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_voluntarios_educacao = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios_educacao.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_voluntarios_meio_ambiente = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_meio_ambiente.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_voluntarios_saude = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios_saude.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_voluntarios_tecnologia_producao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_tecnologia_producao.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_voluntarios_trabalho = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios_trabalho.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_voluntarios_multidisciplinar = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_multidisciplinar.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )

            total_docentes_bolsistas_comunicacao = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas_comunicacao.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_bolsistas_cultura = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas_cultura.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_bolsistas_direitos_humanos = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_direitos_humanos.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_bolsistas_educacao = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas_educacao.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_bolsistas_meio_ambiente = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_meio_ambiente.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_bolsistas_saude = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas_saude.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_bolsistas_tecnologia_producao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_tecnologia_producao.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            total_docentes_bolsistas_trabalho = (
                Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas_trabalho.values_list('vinculo_pessoa', flat=True), eh_docente=True)
                .distinct()
                .count()
            )
            total_docentes_bolsistas_multidisciplinar = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_multidisciplinar.values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )

            total_tec_adm_voluntarios_comunicacao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_comunicacao.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_cultura = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_cultura.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_direitos_humanos = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_direitos_humanos.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_educacao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_educacao.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_meio_ambiente = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_meio_ambiente.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_saude = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_saude.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_tecnologia_producao = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_tecnologia_producao.values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_trabalho = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_trabalho.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_voluntarios_multidisciplinar = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_multidisciplinar.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )

            total_tec_adm_bolsistas_comunicacao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_comunicacao.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_cultura = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_cultura.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_direitos_humanos = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_direitos_humanos.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_educacao = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_educacao.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_meio_ambiente = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_meio_ambiente.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_saude = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_saude.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_tecnologia_producao = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_tecnologia_producao.values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_trabalho = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_trabalho.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )
            total_tec_adm_bolsistas_multidisciplinar = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_multidisciplinar.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
                )
                .distinct()
                .count()
            )

            total_comunicacao = (
                total_alunos_bolsistas_comunicacao
                + total_alunos_voluntarios_comunicacao
                + total_docentes_bolsistas_comunicacao
                + total_docentes_voluntarios_comunicacao
                + total_tec_adm_bolsistas_comunicacao
                + total_tec_adm_voluntarios_comunicacao
            )

            area_tematica_total_geral = area_tematica_total_geral + total_comunicacao

            participantes_por_area_tematica.append(
                {
                    'area': 'Comunicação',
                    'alunos_bolsistas': total_alunos_bolsistas_comunicacao,
                    'alunos_voluntarios': total_alunos_voluntarios_comunicacao,
                    'docentes_bolsistas': total_docentes_bolsistas_comunicacao,
                    'docentes_voluntarios': total_docentes_voluntarios_comunicacao,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_comunicacao,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_comunicacao,
                    'total': total_comunicacao,
                }
            )

            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_comunicacao
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_comunicacao
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_comunicacao
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_comunicacao
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_comunicacao
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_comunicacao

            total_cultura = (
                total_alunos_bolsistas_cultura
                + total_alunos_voluntarios_cultura
                + total_docentes_bolsistas_cultura
                + total_docentes_voluntarios_cultura
                + total_tec_adm_bolsistas_cultura
                + total_tec_adm_voluntarios_cultura
            )
            area_tematica_total_geral = area_tematica_total_geral + total_cultura

            participantes_por_area_tematica.append(
                {
                    'area': 'Cultura',
                    'alunos_bolsistas': total_alunos_bolsistas_cultura,
                    'alunos_voluntarios': total_alunos_voluntarios_cultura,
                    'docentes_bolsistas': total_docentes_bolsistas_cultura,
                    'docentes_voluntarios': total_docentes_voluntarios_cultura,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_cultura,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_cultura,
                    'total': total_cultura,
                }
            )

            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_cultura
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_cultura
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_cultura
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_cultura
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_cultura
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_cultura

            total_direito = (
                total_alunos_bolsistas_direitos_humanos
                + total_alunos_voluntarios_direitos_humanos
                + total_docentes_bolsistas_direitos_humanos
                + total_docentes_voluntarios_direitos_humanos
                + total_tec_adm_bolsistas_direitos_humanos
                + total_tec_adm_voluntarios_direitos_humanos
            )

            area_tematica_total_geral = area_tematica_total_geral + total_direito
            participantes_por_area_tematica.append(
                {
                    'area': 'Direitos Humanos e Justiça',
                    'alunos_bolsistas': total_alunos_bolsistas_direitos_humanos,
                    'alunos_voluntarios': total_alunos_voluntarios_direitos_humanos,
                    'docentes_bolsistas': total_docentes_bolsistas_direitos_humanos,
                    'docentes_voluntarios': total_docentes_voluntarios_direitos_humanos,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_direitos_humanos,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_direitos_humanos,
                    'total': total_direito,
                }
            )

            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_direitos_humanos
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_direitos_humanos
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_direitos_humanos
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_direitos_humanos
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_direitos_humanos
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_direitos_humanos

            total_educacao = (
                total_alunos_bolsistas_educacao
                + total_alunos_voluntarios_educacao
                + total_docentes_bolsistas_educacao
                + total_docentes_voluntarios_educacao
                + total_tec_adm_bolsistas_educacao
                + total_tec_adm_voluntarios_educacao
            )

            area_tematica_total_geral = area_tematica_total_geral + total_educacao
            participantes_por_area_tematica.append(
                {
                    'area': 'Educação',
                    'alunos_bolsistas': total_alunos_bolsistas_educacao,
                    'alunos_voluntarios': total_alunos_voluntarios_educacao,
                    'docentes_bolsistas': total_docentes_bolsistas_educacao,
                    'docentes_voluntarios': total_docentes_voluntarios_educacao,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_educacao,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_educacao,
                    'total': total_educacao,
                }
            )
            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_educacao
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_educacao
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_educacao
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_educacao
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_educacao
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_educacao

            total_meio_ambiente = (
                total_alunos_bolsistas_meio_ambiente
                + total_alunos_voluntarios_meio_ambiente
                + total_docentes_bolsistas_meio_ambiente
                + total_docentes_voluntarios_meio_ambiente
                + total_tec_adm_bolsistas_meio_ambiente
                + total_tec_adm_voluntarios_meio_ambiente
            )

            area_tematica_total_geral = area_tematica_total_geral + total_meio_ambiente
            participantes_por_area_tematica.append(
                {
                    'area': 'Meio Ambiente',
                    'alunos_bolsistas': total_alunos_bolsistas_meio_ambiente,
                    'alunos_voluntarios': total_alunos_voluntarios_meio_ambiente,
                    'docentes_bolsistas': total_docentes_bolsistas_meio_ambiente,
                    'docentes_voluntarios': total_docentes_voluntarios_meio_ambiente,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_meio_ambiente,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_meio_ambiente,
                    'total': total_meio_ambiente,
                }
            )

            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_meio_ambiente
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_meio_ambiente
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_meio_ambiente
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_meio_ambiente
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_meio_ambiente
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_meio_ambiente

            total_saude = (
                total_alunos_bolsistas_saude
                + total_alunos_voluntarios_saude
                + total_docentes_bolsistas_saude
                + total_docentes_voluntarios_saude
                + total_tec_adm_bolsistas_saude
                + total_tec_adm_voluntarios_saude
            )

            area_tematica_total_geral = area_tematica_total_geral + total_saude
            participantes_por_area_tematica.append(
                {
                    'area': 'Saúde',
                    'alunos_bolsistas': total_alunos_bolsistas_saude,
                    'alunos_voluntarios': total_alunos_voluntarios_saude,
                    'docentes_bolsistas': total_docentes_bolsistas_saude,
                    'docentes_voluntarios': total_docentes_voluntarios_saude,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_saude,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_saude,
                    'total': total_saude,
                }
            )
            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_saude
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_saude
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_saude
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_saude
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_saude
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_saude

            total_tecnologia = (
                total_alunos_bolsistas_tecnologia_producao
                + total_alunos_voluntarios_tecnologia_producao
                + total_docentes_bolsistas_tecnologia_producao
                + total_docentes_voluntarios_tecnologia_producao
                + total_tec_adm_bolsistas_tecnologia_producao
                + total_tec_adm_voluntarios_tecnologia_producao
            )

            area_tematica_total_geral = area_tematica_total_geral + total_tecnologia
            participantes_por_area_tematica.append(
                {
                    'area': 'Tecnologia e Produção',
                    'alunos_bolsistas': total_alunos_bolsistas_tecnologia_producao,
                    'alunos_voluntarios': total_alunos_voluntarios_tecnologia_producao,
                    'docentes_bolsistas': total_docentes_bolsistas_tecnologia_producao,
                    'docentes_voluntarios': total_docentes_voluntarios_tecnologia_producao,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_tecnologia_producao,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_tecnologia_producao,
                    'total': total_tecnologia,
                }
            )

            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_tecnologia_producao
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_tecnologia_producao
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_tecnologia_producao
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_tecnologia_producao
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_tecnologia_producao
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_tecnologia_producao

            total_trabalho = (
                total_alunos_bolsistas_trabalho
                + total_alunos_voluntarios_trabalho
                + total_docentes_bolsistas_trabalho
                + total_docentes_voluntarios_trabalho
                + total_tec_adm_bolsistas_trabalho
                + total_tec_adm_voluntarios_trabalho
            )

            area_tematica_total_geral = area_tematica_total_geral + total_trabalho
            participantes_por_area_tematica.append(
                {
                    'area': 'Trabalho',
                    'alunos_bolsistas': total_alunos_bolsistas_trabalho,
                    'alunos_voluntarios': total_alunos_voluntarios_trabalho,
                    'docentes_bolsistas': total_docentes_bolsistas_trabalho,
                    'docentes_voluntarios': total_docentes_voluntarios_trabalho,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_trabalho,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_trabalho,
                    'total': total_trabalho,
                }
            )
            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_trabalho
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_trabalho
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_trabalho
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_trabalho
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_trabalho
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_trabalho

            total_multidisciplinar = (
                total_alunos_bolsistas_multidisciplinar
                + total_alunos_voluntarios_multidisciplinar
                + total_docentes_bolsistas_multidisciplinar
                + total_docentes_voluntarios_multidisciplinar
                + total_tec_adm_bolsistas_multidisciplinar
                + total_tec_adm_voluntarios_multidisciplinar
            )

            area_tematica_total_geral = area_tematica_total_geral + total_multidisciplinar
            participantes_por_area_tematica.append(
                {
                    'area': 'Multidisciplinar',
                    'alunos_bolsistas': total_alunos_bolsistas_multidisciplinar,
                    'alunos_voluntarios': total_alunos_voluntarios_multidisciplinar,
                    'docentes_bolsistas': total_docentes_bolsistas_multidisciplinar,
                    'docentes_voluntarios': total_docentes_voluntarios_multidisciplinar,
                    'tec_adm_bolsistas': total_tec_adm_bolsistas_multidisciplinar,
                    'tec_adm_voluntarios': total_tec_adm_voluntarios_multidisciplinar,
                    'total': total_multidisciplinar,
                }
            )
            area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas_multidisciplinar
            area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios_multidisciplinar
            area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas_multidisciplinar
            area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios_multidisciplinar
            area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas_multidisciplinar
            area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios_multidisciplinar

            bolsista = []
            total_bolsistas_discentes = {}
            total_voluntarios_discentes = {}
            total_bolsistas_coordenadores = {}
            total_voluntarios_coordenadores = {}
            total_geral_bolsistas_discentes = 0
            total_geral_voluntarios_discentes = 0
            total_geral_bolsistas_coordenadores = 0
            total_geral_voluntarios_coordenadores = 0
            for modalidade in Modalidade.objects.all():
                total_bolsistas_discentes[f'{modalidade.descricao}'] = {'total': 0}
                total_voluntarios_discentes[f'{modalidade.descricao}'] = {'total': 0}

            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_comunicacao.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_comunicacao.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Comunicação', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_cultura.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_cultura.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Cultura', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_direitos_humanos.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_direitos_humanos.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Direitos Humanos e Justiça', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_educacao.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_educacao.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Educação', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_meio_ambiente.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_meio_ambiente.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Meio Ambiente', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_saude.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_saude.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Saúde', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_tecnologia_producao.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_tecnologia_producao.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Tecnologia e Produção', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_trabalho.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_trabalho.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Trabalho', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=bolsistas_multidisciplinar.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    bolsista.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_bolsistas_discentes[chave]['total'] = total_bolsistas_discentes[chave]['total'] + valor
                    total_geral_bolsistas_discentes += valor

            voluntario = []
            for modalidade in Modalidade.objects.all():
                valor = Aluno.objects.filter(
                    vinculos__id__in=voluntarios_multidisciplinar.values_list('vinculo_pessoa', flat=True), curso_campus__modalidade=modalidade
                ).count()
                if valor:
                    voluntario.append([modalidade.descricao, valor])
                    chave = f'{modalidade.descricao}'
                    total_voluntarios_discentes[chave]['total'] = total_voluntarios_discentes[chave]['total'] + valor
                    total_geral_voluntarios_discentes += valor
            if bolsista or voluntario:
                alunos_por_modalidade.append({'area': 'Multidisciplinar', 'bolsistas': bolsista, 'voluntarios': voluntario})
            # ----------------------------------------------------------------------------------------------------

            bolsista = []
            total_bolsistas_coordenadores['Docente'] = {'total': 0}
            total_bolsistas_coordenadores['Téc. Adm.'] = {'total': 0}
            total_voluntarios_coordenadores['Docente'] = {'total': 0}
            total_voluntarios_coordenadores['Téc. Adm.'] = {'total': 0}
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_comunicacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_comunicacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_comunicacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_comunicacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Comunicação', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_cultura.filter(responsavel=True).values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_cultura.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_cultura.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_cultura.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Cultura', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_direitos_humanos.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_direitos_humanos.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_direitos_humanos.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_direitos_humanos.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Direitos Humanos e Justiça', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_educacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_educacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_educacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_educacao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Educação', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_meio_ambiente.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_meio_ambiente.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_meio_ambiente.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_meio_ambiente.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Meio Ambiente', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_saude.filter(responsavel=True).values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_saude.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=voluntarios_saude.filter(responsavel=True).values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_saude.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Saúde', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_tecnologia_producao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_tecnologia_producao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_tecnologia_producao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_tecnologia_producao.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Tecnologia e Produção', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True, vinculos__id__in=bolsistas_trabalho.filter(responsavel=True).values_list('vinculo_pessoa', flat=True), eh_docente=True
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_trabalho.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_bolsistas_coordenadores += valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_trabalho.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_trabalho.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Trabalho', 'bolsistas': bolsista, 'voluntarios': voluntario})

            bolsista = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_multidisciplinar.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Docente', valor])
                total_bolsistas_coordenadores['Docente']['total'] = total_bolsistas_coordenadores['Docente']['total'] + valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=bolsistas_multidisciplinar.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                bolsista.append(['Téc. Adm.', valor])
                total_bolsistas_coordenadores['Téc. Adm.']['total'] = total_bolsistas_coordenadores['Téc. Adm.']['total'] + valor

            voluntario = []
            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_multidisciplinar.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_docente=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Docente', valor])
                total_voluntarios_coordenadores['Docente']['total'] = total_voluntarios_coordenadores['Docente']['total'] + valor
                total_geral_voluntarios_coordenadores += valor

            valor = (
                Servidor.objects.filter(
                    ativo=True,
                    vinculos__id__in=voluntarios_multidisciplinar.filter(responsavel=True).values_list('vinculo_pessoa', flat=True),
                    eh_tecnico_administrativo=True,
                )
                .distinct()
                .count()
            )
            if valor:
                voluntario.append(['Téc. Adm.', valor])
                total_voluntarios_coordenadores['Téc. Adm.']['total'] = total_voluntarios_coordenadores['Téc. Adm.']['total'] + valor
                total_geral_voluntarios_coordenadores += valor
            if bolsista or voluntario:
                coordenadores_por_categoria.append({'area': 'Multidisciplinar', 'bolsistas': bolsista, 'voluntarios': voluntario})

            if 'xls' in request.POST and escolheu_ano:
                return tasks.relatorio_dimensao_export_to_xls(quantidade_projetos, quantidade_participantes, participantes_por_area_tematica)

    if campus_relatorio:
        title = f'Relatório de Dimensão dos Projetos de Extensão - Campus {campus_relatorio}'
    else:
        title = 'Relatório de Dimensão dos Projetos de Extensão'

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def plano_trabalho_participante(request: HttpRequest, projeto_id: int, participacao_id: int) -> dict:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    participante = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
    if not participante.pode_emitir_plano_de_trabalho():
        raise PermissionDenied
    eh_coordenador = projeto.is_coordenador(request.user)
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
    descricao_plano = []
    metas = projeto.get_metas()
    for meta in metas:
        etapas = meta.etapa_set.filter(integrantes__in=[participante.id]).order_by('ordem')
        if etapas:
            descricao_plano.extend(etapas)

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
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
@permission_required('projetos.pode_gerenciar_edital')
def reabrir_projeto(request, projeto_id):
    historico = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto_id).order_by('data_operacao')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Reabertura do Projeto: {projeto.titulo} '
    form = ProjetoHistoricoDeEnvioForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.situacao = ProjetoHistoricoDeEnvio.REBAERTO
        o.data_operacao = datetime.datetime.now()
        o.operador = request.user.get_relacionamento()
        o.save()
        projeto.data_finalizacao_conclusao = None
        projeto.concluido = False
        projeto.cancelado = False
        projeto.inativado = False
        projeto.finalizacao_sistemica_em = None
        projeto.finalizacao_sistemica_por = None
        projeto.motivo_finalizacao_sistemica = None
        projeto.save()
        if RegistroConclusaoProjeto.objects.filter(projeto=projeto).exists():
            registro_conclusao = RegistroConclusaoProjeto.objects.get(projeto=projeto)
            registro_conclusao.aprovado = False
            registro_conclusao.dt_avaliacao = None
            registro_conclusao.avaliador = None
            registro_conclusao.save()

        responsavel = Participacao.objects.get(projeto__id=projeto_id, responsavel=True)
        titulo = '[SUAP] Extensão: Reabertura de Projeto'
        texto = f"<h1>Extensão</h1><h2>Reabertura de Projeto</h2><p>O Projeto '{projeto.titulo}' foi reaberto pelo Gerente Sistêmico de Extensão.</p>"
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])
        return httprr('..', 'Reabertura do projeto realizada com sucesso.')

    else:
        form = ProjetoHistoricoDeEnvioForm()

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_licao_aprendida(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Adicionar Lição Aprendida'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        licao = None
        if request.method == 'GET' and 'deletar_licao' in request.GET:
            get_object_or_404(LicaoAprendida, pk=request.GET['deletar_licao'], projeto=projeto).delete()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=licoes_aprendidas', 'Lição excluída com sucesso.')

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
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
def relatorio_licoes_aprendidas(request):
    title = 'Relatório de Lições Aprendidas'
    achou_licoes = False
    buscou_area = False
    form = RelatorioLicoesAprendidasForm(request.GET or None, request=request)
    if form.is_valid():
        area = form.cleaned_data.get('area')
        edital = form.cleaned_data.get('edital')
        campus = form.cleaned_data.get('campus')
        if request.user.has_group_cached(['Coordenador de Extensão', 'Visualizador de Projetos do Campus']):
            licoes = LicaoAprendida.objects.filter(projeto__uo=get_uo(request.user)).order_by('-projeto')
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


@permission_required('projetos.pode_gerenciar_edital')
def excluir_avaliacao(resquest, avaliacao_id):
    avaliacao_deletada = get_object_or_404(Avaliacao, pk=avaliacao_id)
    projeto = avaliacao_deletada.projeto
    avaliacao_deletada.delete()
    return httprr(f'/projetos/projeto/{projeto.pk}/?tab=dados_selecao', 'Avaliação removida com sucesso.')


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def adicionar_oferta_projeto_por_tema(request, edital_id):
    title = 'Adicionar Oferta de Projeto por Tema'
    edital = get_object_or_404(Edital, pk=edital_id)
    if request.method == 'POST':
        form = OfertaProjetoPorTemaForm(data=request.POST)
        if form.is_valid():
            ofertas_existentes = OfertaProjetoPorTema.objects.filter(edital=edital, tema__isnull=True).values_list('area_tematica', flat=True)
            if form.cleaned_data['area_tematica'].id in ofertas_existentes:
                return httprr('.', 'Já existe uma oferta para esta área temática.', tag='error')
            else:
                o = form.save(False)
                o.edital = edital
                o.save()
                return httprr('..', 'Oferta por tema adicionada com sucesso.')
    else:
        form = OfertaProjetoPorTemaForm()

    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def remover_oferta_projeto_por_tema(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    oferta = get_object_or_404(OfertaProjetoPorTema, pk=oferta_projeto_id)
    oferta.delete()
    return httprr(f'/projetos/edital/{edital.id}/?tab=oferta_por_tema', 'Oferta removida com sucesso.')


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def editar_oferta_projeto_por_tema(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    oferta = get_object_or_404(OfertaProjetoPorTema, pk=oferta_projeto_id)
    if request.method == 'POST':
        form = OfertaProjetoPorTemaForm(data=request.POST, instance=oferta)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Oferta editada com sucesso.')
    else:
        form = OfertaProjetoPorTemaForm(instance=oferta)

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
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

        if request.user.has_group_cached(['Coordenador de Extensão', 'Visualizador de Projetos do Campus']):
            projetos = projetos.filter(uo=get_uo(request.user))

        for contador, projeto in enumerate(projetos, 1):
            emails = emails + projeto.vinculo_coordenador.email_notificacao + ';'
            if contador % 10:
                emails = emails + '\n'

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
def listar_equipes_dos_projetos(request):
    title = 'Lista de Equipes dos Projetos'
    form = EquipeProjetoForm(data=request.GET or None, request=request)
    tipo_exibicao = 0  # Detalhado
    dados_do_projeto = []
    participacoes = None
    if request.GET:
        if request.GET.getlist('pessoa').count('') == 1:
            return httprr('/projetos/listar_equipes_dos_projetos/', 'Nenhum projeto encontrado para a pessoa informada.', tag='error')

        if not request.user.has_group_cached(['Gerente Sistêmico de Extensão', 'Visualizador de Projetos']):
            projetos = Projeto.objects.filter(aprovado=True, uo=get_uo(request.user), inativado=False)
        else:
            projetos = Projeto.objects.filter(aprovado=True, inativado=False)

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
            projetos = (
                projetos.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False).exclude(id__in=projetos_cancelados).filter(inativado=False)
            )

        elif situacao == 2:
            projetos = (
                projetos.filter(registroconclusaoprojeto__dt_avaliacao__isnull=True).exclude(id__in=projetos_cancelados).filter(inativado=False)
            )

        tipo_exibicao = int(request.GET.get('tipo_de_exibicao', 0))
        if not participacoes:
            participacoes = Participacao.objects.filter(projeto__in=projetos, ativo=True).order_by('projeto__titulo', 'vinculo_pessoa__pessoa__nome')
        else:
            participacoes = participacoes.filter(ativo=True).order_by('projeto__titulo', 'vinculo_pessoa__pessoa__nome')

        apenas_bolsistas = request.GET.get('apenas_bolsistas')
        if apenas_bolsistas:
            participacoes = participacoes.filter(vinculo=TipoVinculo.BOLSISTA)

        tipo_participantes = request.GET.get('tipo_participantes')
        if tipo_participantes:
            if tipo_participantes == '1':
                participacoes = participacoes.filter(vinculo_pessoa__tipo_relacionamento__model='servidor')
            elif tipo_participantes == '2':
                participacoes = participacoes.filter(vinculo_pessoa__tipo_relacionamento__model='aluno')

        dados_do_projeto = get_lista_de_equipes(participacoes)
        total_projetos_encontrados = len(set(participacoes.values_list('projeto', flat=True)))
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
        ativo = 'Sim' if participacao.ativo else 'Não'
        titulacao = participacao.get_titulacao()
        nivel_ensino = ''
        obs = ''
        dados_participante = get_dados_participante_equipe(participacao, participante)
        vinculo = 'Coordenador' if participacao.responsavel else 'Membro'
        if participacao.vinculo == 'Bolsista' and participacao.bolsa_concedida:
            vinculo = vinculo + ' Bolsista'
        else:
            vinculo = vinculo + ' Não Bolsista'
        if not participacao.vinculo_pessoa:
            nivel_ensino = participacao.nivel_ensino
            obs = participacao.obs
        item = {
            'idprojeto': participacao.projeto.id,
            'projeto': participacao.projeto.titulo,
            'nome': dados_participante['nome'],
            'lattes': dados_participante['lattes'],
            'orcid': dados_participante['orcid'],
            'matricula': matricula,
            'vinculo': vinculo,
            'ativo': ativo,
            'titulacao': titulacao,
            'curso': dados_participante['curso'],
            'banco': participacao.instituicao and str(participacao.instituicao) or '-',
            'agencia': participacao.numero_agencia or '-',
            'tipo_conta': participacao.tipo_conta or '-',
            'numero_conta': participacao.numero_conta or '-',
            'operacao': participacao.operacao or '-',
            'cpf': dados_participante['cpf'],
            'edital': participacao.projeto.edital.titulo,
            'campus': participacao.projeto.uo.sigla,
            'ehcoordenador': participacao.responsavel,
            'em_duplicidade': em_duplicidade,
            'nivel_ensino': nivel_ensino,
            'obs': obs,
        }
        lista.append(item)
        pessoa_id_anterior = participacao.vinculo_pessoa and participacao.vinculo_pessoa.id

    return lista


def get_dados_participante_equipe(participacao: object, participante: object) -> dict:
    dados = {'nome': '', 'lattes': '', 'orcid': '', 'curso': '', 'cpf': ''}
    if participacao.vinculo_pessoa and not participacao.vinculo_pessoa.eh_aluno():
        if participante and participacao.is_servidor():
            dados['nome'] = participante.pessoa_fisica.nome
            dados['cpf'] = participante.pessoa_fisica.cpf
            dados['orcid'] = participante.pessoa_fisica.orcid
        elif participante:
            dados['nome'] = participante.nome
            dados['cpf'] = participante.prestador.pessoa_fisica.cpf
        return dados

    dados['nome'] = participacao.get_nome()
    if participante:
        dados['lattes'] = participante.pessoa_fisica.lattes
        dados['orcid'] = participante.pessoa_fisica.orcid
        dados['curso'] = participante.curso_campus
        dados['cpf'] = participante.pessoa_fisica.cpf
    return dados


@documento('Certificado de Participação', enumerar_paginas=False, validade=360, modelo='projetos.participacao', forcar_recriacao=True)
@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def emitir_certificado_extensao_pdf(request, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    participante = participacao.get_participante()
    eh_servidor_ou_aluno = participacao.is_servidor() or participacao.eh_aluno()
    eh_estrangeiro = not eh_servidor_ou_aluno and not participante.prestador.pessoa_fisica.cpf
    if not participacao.pode_emitir_certificado_de_participacao_extensao():
        return httprr('/', 'Você não tem permissão para este acesso.', 'error')
    else:
        hoje = datetime.datetime.now()
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
        mes = meses[hoje.month - 1]
        title = str(participacao.projeto)
        movimentacao = HistoricoEquipe.objects.filter(ativo=True, participante=pk).order_by('id')
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
                    f'/projetos/projeto/{participacao.projeto.id}/',
                    'Este participante não possui nenhum vínculo passível de emissão de certificado.',
                    'error',
                )

        else:
            return httprr(f'/projetos/projeto/{participacao.projeto.id}/', 'Não existe movimentação para este participante.', 'error')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
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
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def solicitacoes_de_cancelamento(request):
    title = 'Projetos com Solicitações de Cancelamento'
    if request.user.has_group_cached('Gerente Sistêmico de Extensão'):
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
        if form.cleaned_data.get('situacao'):
            if form.cleaned_data.get('situacao') == SolicitoesCancelamentoForm.PENDENTES_AVALIACAO:
                projetos_cancelados = projetos_cancelados.filter(data_avaliacao__isnull=True)
            elif form.cleaned_data.get('situacao') == SolicitoesCancelamentoForm.PARECER_FAVORAVEL:
                projetos_cancelados = projetos_cancelados.filter(cancelado=True)
            elif form.cleaned_data.get('situacao') == SolicitoesCancelamentoForm.INDEFERIDA:
                projetos_cancelados = projetos_cancelados.filter(cancelado=False, data_avaliacao__isnull=False)

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def avaliar_cancelamento_projeto(request: HttpRequest, cancelamento_id: int) -> dict | HttpResponse:
    pedido_cancelamento = get_object_or_404(ProjetoCancelado, pk=cancelamento_id)
    campus_restrito = campus_do_coordenador_extensao(request.user)
    if campus_restrito and pedido_cancelamento.projeto.uo != campus_restrito:
        raise PermissionDenied
    edicao = False
    if pedido_cancelamento.data_avaliacao:
        edicao = True
    title = 'Avaliar Cancelamento do Projeto'
    eh_continuo = False
    if pedido_cancelamento.projeto.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
        eh_continuo = True
    form = AvaliarCancelamentoProjetoForm(request.POST or None, instance=pedido_cancelamento, eh_continuo=eh_continuo, edicao=edicao)
    if form.is_valid():
        o = form.save(False)
        o.projeto = pedido_cancelamento.projeto
        o.data_avaliacao = datetime.datetime.now()
        o.avaliador = request.user.get_relacionamento()
        o.save()

        if o.cancelado is True:
            projeto = pedido_cancelamento.projeto
            projeto.cancelado = True
            projeto.save()
            if not edicao:
                participantes = Participacao.ativos.filter(projeto=pedido_cancelamento.projeto, vinculo='Bolsista')
                for participante in participantes:
                    if not participante.is_servidor():
                        participante.gerencia_bolsa_ae()

            if form.cleaned_data.get('aprova_proximo') and form.cleaned_data['aprova_proximo'] == 'True' and not eh_continuo:
                if pedido_cancelamento.projeto.edital.forma_selecao == Edital.GERAL:
                    proximo_projeto = Projeto.objects.filter(edital=pedido_cancelamento.projeto.edital, aprovado=False, pre_aprovado=True).order_by(
                        'classificacao'
                    )
                elif pedido_cancelamento.projeto.edital.forma_selecao == Edital.TEMA:
                    proximo_projeto = Projeto.objects.filter(
                        edital=pedido_cancelamento.projeto.edital, tema=pedido_cancelamento.projeto.tema, aprovado=False, pre_aprovado=True
                    ).order_by('classificacao')
                else:
                    proximo_projeto = Projeto.objects.filter(
                        edital=pedido_cancelamento.projeto.edital, uo=pedido_cancelamento.projeto.uo, aprovado=False, pre_aprovado=True
                    ).order_by('classificacao')

                if proximo_projeto.exists() and o.proximo_projeto is None:
                    o.proximo_projeto = proximo_projeto[0]
                    o.save()
                    projeto = proximo_projeto[0]
                    projeto.aprovado = True
                    projeto.save()
                    responsavel = Participacao.objects.get(projeto__id=projeto.id, responsavel=True)
                    titulo = '[SUAP] Extensão: Aprovação de Projeto'
                    texto = (
                        '<h1>Extensão</h1>'
                        '<h2>Aprovação de Projeto</h2>'
                        f"<p>O projeto '{projeto.titulo}' foi aprovado em decorrência de uma desistência.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])

        return httprr('/projetos/solicitacoes_de_cancelamento/', 'Cancelamento avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def indicar_pre_avaliador(request):
    editais = Edital.objects.em_periodo_indicar_pre_avaliador()

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def selecionar_pre_avaliador(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Selecionar Pré-Avaliadores - {edital.titulo}'
    pids = UsuarioGrupo.objects.filter(group__name='Coordenador de Extensão').values_list('user__id', flat=True)
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
        area_tematica = form.cleaned_data['area_tematica']

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

        if area_tematica:
            projetos = projetos.filter(area_tematica=area_tematica)
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        projetos = projetos.filter(uo=get_uo(request.user))

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def selecionar_pre_avaliador_do_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_perm('projetos.pode_gerenciar_edital') and projeto.uo != get_uo(request.user):
        return httprr('..', 'Permissão negada.', tag='error')
    title = 'Indicar Pré-Avaliador'
    grupo = Group.objects.get(name='Pré-Avaliador Sistêmico de Projetos de Extensão')
    form = AdicionarUsuarioGrupoForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            if projeto.eh_participante(usuario):
                return httprr(
                    '..',
                    f'{usuario.get_vinculo()} é membro do projeto e por este motivo não pode ser indicado como pré-avaliador/monitor.',
                    tag='error',
                )
            projeto.vinculo_autor_pre_avaliacao = usuario.get_vinculo()
            if not projeto.eh_fomento_interno():
                projeto.vinculo_monitor = usuario.get_vinculo()
            usuario.groups.add(grupo)
            projeto.save()
        return httprr('..', 'Pré-avaliador cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.change_projeto')
def editais_para_avaliacao(request):
    title = 'Editais em Avaliação'
    hoje = datetime.datetime.now()
    editais = Edital.objects.filter(divulgacao_selecao__gt=hoje) | Edital.objects.filter(
        tipo_edital=Edital.EXTENSAO_FLUXO_CONTINUO, exige_etapa_avaliacao=True, fim_inscricoes__gt=hoje
    )
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        editais = editais.filter(campus_especifico=True, ofertaprojeto__uo=get_uo(request.user))
    return locals()


@rtr()
@permission_required('projetos.change_projeto')
def selecionar_avaliadores(request, edital_id):
    edital = Edital.objects.get(pk=edital_id)
    title = f'Selecionar avaliadores dos Projetos do {edital.titulo}'
    if edital.tipo_edital == Edital.EXTENSAO:
        projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('titulo')
    else:
        projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False).order_by('titulo')
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        campus_logado_user = get_uo(request.user)
        if not edital.campus_especifico or not OfertaProjeto.objects.filter(edital=edital, uo=campus_logado_user).exists():
            raise PermissionDenied
        projetos = projetos.filter(uo=campus_logado_user)
    form = IndicarAvaliadorForm(request.GET or None)
    if form.is_valid():
        status_avaliacao = form.cleaned_data['status_avaliacao']
        palavra_chave = form.cleaned_data['palavra_chave']
        area_tematica = form.cleaned_data['area_tematica']
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
            elif int(status_avaliacao) == 4 and form.cleaned_data.get('pontos'):
                ids = []
                for projeto in projetos:
                    avaliacoes = Avaliacao.objects.filter(projeto=projeto).order_by('pontuacao')
                    if avaliacoes.count() >= 2:
                        menor_pontuacao = avaliacoes[0].pontuacao
                        limite_divergencia = menor_pontuacao + form.cleaned_data.get('pontos')
                        if avaliacoes.filter(pontuacao__gte=limite_divergencia).exists():
                            ids.append(projeto.id)
                projetos = projetos.filter(id__in=ids)

        if uo:
            projetos = projetos.filter(uo__id=uo.id)
        if palavra_chave:
            projetos = projetos.filter(avaliadorindicado__vinculo__pessoa__nome__icontains=palavra_chave)
        if area_tematica:
            projetos = projetos.filter(area_tematica=area_tematica)

    return locals()


def membros_comissao_do_projeto(projeto: Projeto) -> QuerySet[Vinculo]:
    """Vínculos de onde sai a lista de avaliadores do projeto: a comissão do edital ou, sem ela, quem tem área temática."""
    if projeto.edital.exige_comissao:
        return Vinculo.objects.filter(id__in=ComissaoEdital.objects.filter(edital=projeto.edital).values_list('vinculos_membros', flat=True))
    return Vinculo.objects.exclude(tipo_relacionamento__model='aluno').filter(id__in=AreaTematica.objects.all().values_list('vinculo', flat=True))


def excluir_impedidos_de_avaliar(projeto: Projeto, membros: QuerySet[Vinculo]) -> QuerySet[Vinculo]:
    """Tira de ``membros`` a equipe do projeto, o próprio campus (edital não específico) e quem não é da área temática.

    Em edital com temas, projeto sem área temática não tem avaliador elegível (``filter(id=None)`` é vazio).
    """
    ids_servidores = [servidor.vinculo_pessoa.id for servidor in projeto.get_participacoes_servidores_ativos()]
    membros = membros.exclude(id__in=ids_servidores)
    if not projeto.edital.campus_especifico:
        membros = membros.exclude(id__in=[avaliador.id for avaliador in membros if get_uo(avaliador.user) == projeto.uo])
    if projeto.edital.temas.exists():
        membros = membros.filter(id__in=AreaTematica.objects.filter(id=projeto.area_tematica_id).values_list('vinculo', flat=True))
    return membros


@rtr()
@permission_required('projetos.change_projeto')
def selecionar_avaliadores_do_projeto(request: HttpRequest, projeto_id: int) -> dict:
    projeto = Projeto.objects.get(pk=projeto_id)
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        if not projeto.uo == get_uo(request.user) or not projeto.edital.campus_especifico:
            raise PermissionDenied
    title = f'Indicar Avaliadores do Projeto {projeto.titulo}'
    try:
        url = request.get_full_path().split('url=')[1]
    except Exception:
        raise PermissionDenied('Endereço inválido')
    form = IndicarAvaliadoresForm(request.POST or None)
    if form.is_valid():
        avaliadores_cadastrados = AvaliadorIndicado.objects.filter(projeto=projeto)
        membros_comissao = membros_comissao_do_projeto(projeto)

        if form.cleaned_data.get('nome'):
            membros_comissao = membros_comissao.filter(pessoa__nome__icontains=form.cleaned_data.get('nome'))
        if form.cleaned_data.get('matricula'):
            membros_comissao = membros_comissao.filter(
                id__in=Servidor.objects.filter(matricula=form.cleaned_data.get('matricula')).values_list('vinculos', flat=True)
            )
        if form.cleaned_data.get('area_tematica'):
            membros_comissao = membros_comissao.filter(id__in=form.cleaned_data.get('area_tematica').vinculo.all().values_list('id', flat=True))

        membros_comissao = excluir_impedidos_de_avaliar(projeto, membros_comissao)
        lista_avaliadores = []
        for pessoa in membros_comissao.order_by('pessoa__nome'):
            indicacoes_no_edital = AvaliadorIndicado.objects.filter(vinculo=pessoa, projeto__edital=projeto.edital).count()
            indicacoes_total = AvaliadorIndicado.objects.filter(vinculo=pessoa).count()
            avaliacoes_total = Avaliacao.objects.filter(vinculo=pessoa).count()
            if pessoa.id in avaliadores_cadastrados.values_list('vinculo', flat=True):
                lista_avaliadores.append([pessoa, True, indicacoes_no_edital, indicacoes_total, avaliacoes_total])
            else:
                lista_avaliadores.append([pessoa, False, indicacoes_no_edital, indicacoes_total, avaliacoes_total])

    return locals()


@rtr()
@permission_required('projetos.change_projeto')
def salvar_avaliadores_do_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        if not projeto.uo == get_uo(request.user) or not projeto.edital.campus_especifico:
            raise PermissionDenied
    avaliadores_cadastrados = AvaliadorIndicado.objects.filter(projeto=projeto)
    grupo = Group.objects.get(name='Avaliador de Projetos de Extensão')
    escolhidos = request.POST.getlist('registros')
    url = request.get_full_path().split('url=')[1]
    ids_escolhidos = []
    if escolhidos:
        for item in escolhidos:
            ids_escolhidos.append(int(item))
    # Só quem a tela oferece: os ids do POST fora da lista são ignorados.
    escolhidos_validos = excluir_impedidos_de_avaliar(projeto, membros_comissao_do_projeto(projeto).filter(id__in=ids_escolhidos))
    for avaliador in escolhidos_validos:
        if avaliador.user and avaliador.id not in avaliadores_cadastrados.values_list('vinculo', flat=True):
            novo_avaliador = AvaliadorIndicado()
            novo_avaliador.vinculo = avaliador
            novo_avaliador.convidado_em = datetime.datetime.now()
            novo_avaliador.projeto = projeto
            if projeto.edital.prazo_aceite_indicacao:
                prazo_aceite = datetime.datetime.now() + relativedelta(days=projeto.edital.prazo_aceite_indicacao)
                novo_avaliador.prazo_para_aceite = prazo_aceite
                if projeto.edital.prazo_avaliacao:
                    prazo_avaliacao = prazo_aceite + relativedelta(days=projeto.edital.prazo_avaliacao)
                    novo_avaliador.prazo_para_avaliacao = prazo_avaliacao
            novo_avaliador.save()
            novo_avaliador.vinculo.user.groups.add(grupo)

            titulo = '[SUAP] Avaliação de Projeto de Extensão'
            if projeto.edital.prazo_aceite_indicacao:
                texto = (
                    '<h1>Extensão</h1>'
                    '<h2>Avaliação de Projeto</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de extensão: {novo_avaliador.projeto.titulo}.</p>'
                    f'<p>Prazo para registrar que aceita a indicação: {format_(novo_avaliador.prazo_para_aceite)}.</p>'
                    f'<p>Prazo para realizar a avaliação: {format_(novo_avaliador.prazo_para_avaliacao)}.</p>'
                    '<p>Caso os prazos não sejam cumpridos, a indicação será cancelada automaticamente.</p>'
                    f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(projeto.edital.fim_selecao)}</strong>.</p>'
                )
            else:
                texto = (
                    '<h1>Extensão</h1>'
                    '<h2>Avaliação de Projeto</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de extensão: {novo_avaliador.projeto.titulo}.</p>'
                    f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(projeto.edital.fim_selecao)}</strong>.</p>'
                )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [avaliador])
    return httprr(url, 'Avaliadores cadastrados com sucesso.')


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def remover_indicacao_avaliador(request, avaliador_id):
    avaliador = get_object_or_404(AvaliadorIndicado, pk=avaliador_id)
    avaliador.delete()
    url = request.META.get('HTTP_REFERER', '.')
    if not AvaliadorIndicado.objects.filter(vinculo=avaliador.vinculo).exists():
        grupo = Group.objects.get(name='Avaliador de Projetos de Extensão')
        avaliador.vinculo.user.groups.remove(grupo)
    return httprr(url, 'Indicação de avaliador removida com sucesso.')


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
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
@permission_required('projetos.pode_se_tornar_avaliador')
def emitir_declaracao_avaliador(request):
    title = 'Declarações'
    from django.db.models import Count

    projetos_avaliados = (
        Avaliacao.objects.filter(vinculo=request.user.get_vinculo())
        .values('projeto__edital__titulo', 'projeto__edital')
        .annotate(total=Count('projeto'))
        .order_by('-projeto__edital')
    )

    return locals()


@documento('Declaração de Avaliador', enumerar_paginas=False, forcar_recriacao=True, modelo='projetos.edital')
@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def emitir_declaracao_avaliador_pdf(request: HttpRequest, pk: int) -> dict:
    edital = get_object_or_404(Edital, pk=pk)
    pessoa = request.user.get_vinculo().pessoa.nome
    hoje = datetime.datetime.now()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
    meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    mes = meses[hoje.month - 1]
    ano = edital.inicio_inscricoes.year
    data_inicio = edital.inicio_selecao.strftime('%d/%m/%Y')
    data_termino = edital.fim_selecao.strftime('%d/%m/%Y')
    from django.db.models import Count

    vinculo = request.user.get_vinculo()
    registros = Avaliacao.objects.filter(projeto__edital=edital, vinculo=request.user.get_vinculo()).order_by('projeto__area_tematica')
    if not registros.exists():
        raise PermissionDenied
    cidade = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
    if edital.campus_especifico and registros.exists():
        cidade = registros[0].projeto.uo.municipio.nome
    projetos_avaliados = registros.values('projeto__area_tematica', 'projeto__area_tematica__descricao').annotate(
        total=Count('projeto__area_tematica')
    )
    dados = []
    for projeto in projetos_avaliados:
        dados.append([projeto['projeto__area_tematica__descricao'], projeto['total']])

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def gerenciar_monitores(request):
    title = 'Gerenciar Monitores'
    editais = Edital.objects.all().order_by('-inicio_inscricoes')
    form = AnoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            editais = editais.filter(inicio_inscricoes__year=form.cleaned_data.get('ano'))

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def selecionar_monitor(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
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
                projetos = Projeto.objects.filter(
                    registroconclusaoprojeto__dt_avaliacao__isnull=True, vinculo_monitor__isnull=True, edital=edital
                ).exclude(data_conclusao_planejamento=None)

            else:
                em_conflito = False
                projetos = Projeto.objects.filter(edital=edital, aprovado=True).order_by('titulo')

        if uo:
            projetos = projetos.filter(uo__id=uo.id)

        if palavra_chave:
            projetos = projetos.filter(vinculo_monitor__pessoa__nome__icontains=palavra_chave)

        if area_tematica:
            projetos = projetos.filter(area_tematica=area_tematica)

    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        projetos = projetos.filter(uo=get_uo(request.user))
    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def selecionar_monitor_do_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_perm('projetos.pode_gerenciar_edital') and projeto.uo != get_uo(request.user):
        return httprr('..', 'Permissão negada.', tag='error')
    title = 'Indicar Monitor'
    grupo = Group.objects.get(name='Pré-Avaliador Sistêmico de Projetos de Extensão')
    form = AdicionarUsuarioGrupoForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            if projeto.eh_participante(usuario):
                return httprr(
                    '..',
                    f'{usuario.get_vinculo()} é membro do projeto e por este motivo não pode ser indicado como pré-avaliador/monitor.',
                    tag='error',
                )
            projeto.vinculo_monitor = usuario.get_vinculo()
            usuario.groups.add(grupo)
            projeto.save()
        return httprr('..', 'Monitor cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def recurso_projeto(request: HttpRequest, recurso_id: int) -> dict:
    recurso = get_object_or_404(RecursoProjeto, pk=recurso_id)
    # o mesmo filtro de campus de `solicitacoes_de_recurso`, a lista que oferece o link
    if not request.user.has_group_cached('Gerente Sistêmico de Extensão') and not (
        recurso.projeto.edital.campus_especifico and recurso.projeto.uo == get_uo(request.user)
    ):
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def enviar_recurso(request, projeto_id):
    title = 'Enviar Recurso'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    if not projeto.pode_enviar_recurso():
        raise PermissionDenied

    form = RecursoProjetoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.data_solicitacao = datetime.datetime.now()
        o.save()
        return httprr(f'/projetos/projeto/{projeto.id}', 'Recurso encaminhado para análise.')

    return locals()


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def avaliar_recurso_projeto(request, recurso_id):
    recurso = get_object_or_404(RecursoProjeto, pk=recurso_id)
    if not request.user.has_group_cached('Gerente Sistêmico de Extensão') and (
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

        return httprr(f'/projetos/projeto/{recurso.projeto.id}/?tab=recursos', 'Recurso avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def registro_beneficiario_atendido(request, caracterizacao_id):
    caracterizacao = get_object_or_404(CaracterizacaoBeneficiario, pk=caracterizacao_id)
    title = 'Quantidade de Beneficiários Atendidos'
    projeto = caracterizacao.projeto
    if projeto.pode_registrar_execucao() and not projeto.eh_somente_leitura():
        form = CaracterizacaoBeneficiarioForm(request.POST or None, instance=caracterizacao, atendida=True)
        if form.is_valid():
            form.save()
            return httprr('..', 'Caracterização registrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_anexo_diverso_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Adicionar Anexo ao Projeto'
        if request.POST:
            form = AnexosDiversosProjetoForm(request.POST, request.FILES, projeto=projeto)
            if form.is_valid():
                o = form.save(False)
                o.projeto = projeto
                arquivo_up = request.FILES['arquivo_anexo']
                arquivo_up.seek(0)
                if not o.mes:
                    o.mes = 0
                content = arquivo_up.read()
                nome = arquivo_up.name
                vinculo = request.user.get_vinculo()
                arquivo = Arquivo()
                arquivo.save(nome, vinculo)
                o.arquivo = arquivo
                o.save()
                arquivo.store(request.user, content)

                return httprr(f'/projetos/projeto/{projeto.id}/?tab=anexos', 'Anexo cadastrado com sucesso.')
        else:
            participacao = None
            if 'termo_desligamento' in request.GET:
                participacao = get_object_or_404(Participacao, pk=request.GET.get('termo_desligamento'), projeto=projeto)
                title = 'Adicionar Termo de Desligamento do Participante'

            form = AnexosDiversosProjetoForm(request.POST or None, projeto=projeto, participacao=participacao)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def prestacao_contas(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_responsavel = projeto.is_responsavel(request.user)
    if not projeto.pode_ver_prestacao_contas(request.user):
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

            body = _corpo_pdf_prestacao_contas(title, form.cleaned_data, registros)
            if request.GET and 'pdf' in request.GET:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            elif request.GET and 'download' in request.GET:
                return _zip_comprovantes_gastos(projeto, registros)
            else:
                gastos_com_cadastro = _gastos_com_cadastro_de_arquivo(projeto, registros, request.user)
                return locals()

    return locals()


def _gastos_com_cadastro_de_arquivo(projeto: Projeto, registros: QuerySet, user: User) -> set[int]:
    """Gastos cujo "Cadastrar" de comprovante/cotação em ``prestacao_contas`` abre ``registro_gasto`` (#17567).

    Mesmos portões de ``registro_gasto`` com ``?editar_registro_id``: o do projeto é cópia do da view, que
    não foi extraído para não mexer nela; o do gasto reusa os predicados dela.
    """
    if not ((projeto.pode_editar_gasto() and not projeto.eh_somente_leitura()) or projeto.is_gerente_sistemico()):
        return set()
    return {
        registro.pk
        for registro in registros.select_related('desembolso__projeto')
        if _so_comprovante_registro_gasto(registro, user) or registro.pode_editar_remover_registro_gasto()
    }


def _corpo_pdf_prestacao_contas(title: str, cleaned_data: dict, registros: QuerySet) -> list:
    """Topo, quadro do período e tabela de gastos do PDF de ``prestacao_contas``."""
    topo = relatorios.get_topo_pdf(title)
    dados = [['Ano', 'Mês', 'Despesa', 'Descrição/Observação', 'Qtd.', 'Valor Unitário (R$)', 'Subtotal (R$)']]

    total = 0
    for registro in registros:
        subtotal = registro.get_subtotal()
        if registro.observacao:
            descricao = f'{escape(registro.descricao)} - <b>Obs:</b> {escape(registro.observacao)}'
        else:
            descricao = escape(registro.descricao)
        dados.append([registro.ano, registro.mes, escape(registro.desembolso.despesa), descricao, registro.qtd, registro.valor_unitario, subtotal])
        total = total + subtotal
    dados.append([' ', ' ', ' ', ' ', ' ', 'Total', total])
    if cleaned_data['tipo_relatorio'] == '1':
        periodo = '{}/{}'.format(cleaned_data['mes_relatorio'], cleaned_data['ano_relatorio'])
        info = [['Tipo do Relatório:', 'Parcial'], ['Período:', periodo], ['Emitido em:', datetime.datetime.now()]]
    else:
        info = [['Tipo do Relatório:', 'Final'], ['Emitido em', datetime.datetime.now()]]
    tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[12, 10, 60, 80, 10, 18, 18], count=0, escape=False)
    return [*topo, tabela_info, relatorios.space(8), tabela_dados]


def _zip_comprovantes_gastos(projeto: Projeto, registros: QuerySet) -> HttpResponse:
    """Zip com os comprovantes dos gastos de ``prestacao_contas`` (arquivo, cotação de preços e termo de cessão)."""
    zip_buffer = io.BytesIO()
    zip_file = zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED)

    for registro in registros:
        if registro.arquivo:
            zip_file.writestr(registro.arquivo.name.split('/')[-1], registro.arquivo.read())
        if registro.cotacao_precos:
            zip_file.writestr(registro.cotacao_precos.name.split('/')[-1], registro.cotacao_precos.read())
        if registro.arquivo_termo_cessao:
            zip_file.writestr(registro.arquivo_termo_cessao.name.split('/')[-1], registro.arquivo_termo_cessao.read())
    zip_file.close()
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename=comprovantes_gastos_{projeto.id}.zip'
    return response


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def solicitacoes_de_recurso(request):
    title = 'Projetos com solicitações de recurso contra o edital'
    projetos_com_recurso = RecursoProjeto.objects.all()
    if not request.user.has_group_cached('Gerente Sistêmico de Extensão'):
        projetos_com_recurso = projetos_com_recurso.filter(projeto__edital__campus_especifico=True, projeto__uo=get_uo(request.user))
    ano = request.GET.get('ano')
    form = EditaisForm(request.GET or None, request=request, ano=ano)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            projetos_com_recurso = projetos_com_recurso.filter(projeto__edital__inicio_inscricoes__year=form.cleaned_data.get('ano'))
        if form.cleaned_data.get('edital'):
            projetos_com_recurso = projetos_com_recurso.filter(projeto__edital=form.cleaned_data.get('edital'))
        if form.cleaned_data.get('situacao'):
            if form.cleaned_data.get('situacao') == EditaisForm.PENDENTES_AVALIACAO:
                projetos_com_recurso = projetos_com_recurso.filter(data_avaliacao__isnull=True)
            elif form.cleaned_data.get('situacao') == EditaisForm.PARECER_FAVORAVEL:
                projetos_com_recurso = projetos_com_recurso.filter(aceito=True)
            elif form.cleaned_data.get('situacao') == EditaisForm.INDEFERIDA:
                projetos_com_recurso = projetos_com_recurso.filter(aceito=False, data_avaliacao__isnull=False)
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_extrato_mensal(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Adicionar Extrato Mensal'
        if request.POST:
            form = ExtratoMensalForm(request.POST or None, request.FILES, projeto=projeto)
            if form.is_valid():
                o = form.save(False)
                o.projeto = projeto
                o.save()
                return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Extrato cadastrado com sucesso.')
        else:
            form = ExtratoMensalForm(request.POST or None, projeto=projeto)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_termo_cessao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Adicionar Termo de Cessão/Doação'
        if projeto.tem_registro_gasto_registrado():
            if request.POST:
                form = TermoCessaoForm(request.POST, request.FILES, projeto=projeto)
                if form.is_valid():
                    registro = get_object_or_404(RegistroGasto, pk=form.cleaned_data['registro'].id)
                    registro.arquivo_termo_cessao = form.cleaned_data.get('arquivo')
                    registro.obs_cessao = form.cleaned_data.get('obs')
                    registro.save()
                    return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Termo cadastrado com sucesso.')
            else:
                form = TermoCessaoForm(request.POST or None, projeto=projeto)
        else:
            return httprr(
                f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas',
                'O projeto não possui nenhum registro de gasto para ser vinculado ao termo de cessão.',
                tag='error',
            )

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def resultado_edital(request, periodo):
    title = 'Editais com Resultados Disponíveis'
    hoje = datetime.datetime.now()

    if periodo == 1:
        final = True
        editais = Edital.objects.filter(divulgacao_selecao__lt=hoje, tipo_edital=Edital.EXTENSAO, tipo_fomento=Edital.FOMENTO_INTERNO).order_by(
            '-divulgacao_selecao', '-inicio_inscricoes'
        )
    else:
        final = False
        editais = Edital.objects.filter(fim_selecao__lt=hoje, divulgacao_selecao__gt=hoje, tipo_fomento=Edital.FOMENTO_INTERNO).order_by(
            '-divulgacao_selecao', '-inicio_inscricoes'
        )
    form = AnoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            ano = int(form.cleaned_data['ano'])
            editais = editais.filter(inicio_inscricoes__year=ano)

    return locals()


@rtr()
def divulgar_resultado_edital(request, edital_id, periodo):
    edital = get_object_or_404(Edital, pk=edital_id)
    if edital.eh_fomento_interno():
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
        tabela = {}
        resultado = {}
        final = False
        if periodo == 1:
            final = True
            queryset_projeto = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True)
        else:
            queryset_projeto = (
                Projeto.objects.filter(edital=edital, pre_aprovado=True)
                .exclude(aprovado_pos_recurso=True)
                .filter(Q(aprovado=True) | Q(reprovacao_manual_em__isnull=False))
            )
        if edital.pode_visualizar_resultado(request.user, periodo):
            if edital.forma_selecao == Edital.GERAL:
                if final:
                    projetos = queryset_projeto.exclude(autorizada_sem_fomento=True).order_by('classificacao', '-pontuacao')
                else:
                    projetos = queryset_projeto.exclude(autorizada_sem_fomento=True).order_by('classificacao', '-pontuacao_parcial')
                tabela['Geral'] = {'aprovados': [], 'reprovados': []}
                for projeto in projetos:
                    tabela['Geral']['aprovados'].append(projeto)
                if final:
                    reprovados = (
                        Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False)
                        .exclude(autorizada_sem_fomento=True)
                        .exclude(reprovacao_manual_em=None)
                        .order_by('classificacao', '-pontuacao')
                    )
                else:
                    reprovados = (
                        Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False)
                        .exclude(autorizada_sem_fomento=True)
                        .exclude(reprovacao_manual_em=None)
                        .order_by('classificacao', '-pontuacao_parcial')
                    )
                for projeto in reprovados:
                    tabela['Geral']['reprovados'].append(projeto)

            elif edital.forma_selecao == Edital.GRUPO:
                if final:
                    projetos = queryset_projeto.exclude(autorizada_sem_fomento=True).order_by('uo__sigla', 'classificacao', '-pontuacao')
                else:
                    projetos = queryset_projeto.exclude(autorizada_sem_fomento=True).order_by('uo__sigla', 'classificacao', '-pontuacao_parcial')
                grupos = projetos.values('grupo__grupo').distinct()
                for campus in grupos:
                    chave = str(campus['grupo__grupo'])
                    tabela[chave] = {'aprovados': [], 'reprovados': []}

                for projeto in projetos:
                    chave = f'{projeto.grupo.grupo}'
                    tabela[chave]['aprovados'].append(projeto)
                if final:
                    reprovados = (
                        Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False)
                        .exclude(autorizada_sem_fomento=True)
                        .exclude(reprovacao_manual_em=None)
                        .order_by('uo__sigla', 'classificacao', '-pontuacao')
                    )
                else:
                    reprovados = (
                        Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False)
                        .exclude(autorizada_sem_fomento=True)
                        .exclude(reprovacao_manual_em=None)
                        .order_by('uo__sigla', 'classificacao', '-pontuacao_parcial')
                    )
                for projeto in reprovados:
                    chave = f'{projeto.grupo.grupo}'
                    tabela[chave]['reprovados'].append(projeto)
            else:
                if final:
                    projetos = queryset_projeto.exclude(autorizada_sem_fomento=True).order_by('uo__sigla', 'classificacao', '-pontuacao')
                else:
                    projetos = queryset_projeto.exclude(autorizada_sem_fomento=True).order_by('uo__sigla', 'classificacao', '-pontuacao_parcial')
                campi = projetos.values('uo__sigla', 'uo__nome').distinct()
                for campus in campi:
                    chave = str(campus['uo__nome'])
                    tabela[chave] = {'aprovados': [], 'reprovados': []}

                for projeto in projetos:
                    chave = f'{projeto.uo.nome}'
                    tabela[chave]['aprovados'].append(projeto)
                if final:
                    reprovados = (
                        Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False)
                        .exclude(autorizada_sem_fomento=True)
                        .exclude(reprovacao_manual_em=None)
                        .order_by('uo__sigla', 'classificacao', '-pontuacao')
                    )
                else:
                    reprovados = (
                        Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=False)
                        .exclude(autorizada_sem_fomento=True)
                        .exclude(reprovacao_manual_em=None)
                        .order_by('uo__sigla', 'classificacao', '-pontuacao_parcial')
                    )
                for projeto in reprovados:
                    chave = f'{projeto.uo.nome}'
                    tabela[chave]['reprovados'].append(projeto)

            resultado = collections.OrderedDict(sorted(tabela.items()))
            total_aprovados = projetos.exclude(
                id__in=ProjetoCancelado.objects.filter(proximo_projeto__isnull=False).values_list('proximo_projeto__id', flat=True)
            ).count()
        return locals()
    raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def alterar_ficha_avaliacao(request, itemavaliacao_id):
    itemavaliacao = get_object_or_404(ItemAvaliacao, pk=itemavaliacao_id)
    projeto = itemavaliacao.avaliacao.projeto
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
        o.vinculo_responsavel_alteracao = request.user.get_vinculo()
        o.data_alteracao = datetime.datetime.now()
        o.save()
        itemavaliacao.avaliacao.save()
        return httprr('..', 'Nota atualizada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def ver_alteracao_ficha_avaliacao(request: HttpRequest, itemavaliacao_id: int) -> dict:
    itemavaliacao = get_object_or_404(ItemAvaliacao, pk=itemavaliacao_id)
    projeto = itemavaliacao.avaliacao.projeto
    eh_coex_do_campus = request.user.has_group_cached('Coordenador de Extensão') and projeto.uo == get_uo(request.user)
    if not eh_coex_do_campus:
        tem_permissao(request, projeto, pode_auxiliar=True)
    eh_sistemico = False
    if request.user.has_group_cached('Gerente Sistêmico de Extensão'):
        eh_sistemico = True

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def upload_outro_anexo(request, anexo_id):
    title = 'Upload de Arquivo'
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    projeto = anexo.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if not anexo.anexo_edital and not projeto.eh_somente_leitura():
            if request.method == 'POST':
                form = UploadArquivoForm(request.POST, request.FILES)
                if form.is_valid():
                    arquivo_up = request.FILES['arquivo']
                    vinculo = request.user.get_vinculo()
                    salvar_arquivo(anexo, arquivo_up, vinculo, request)
                    return httprr(f'/projetos/projeto/{projeto.id}/?tab=anexos', 'Anexo alterado com sucesso.')
            else:
                form = UploadArquivoForm()
        else:
            return httprr(f'/projetos/projeto/{anexo.projeto.id}/?tab=anexos', 'Este anexo não pode ser alterado.', tag='error')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_outro_anexo(request, anexo_id):
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    projeto = anexo.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if not anexo.anexo_edital and not projeto.eh_somente_leitura():
            anexo.delete()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=anexos', 'Anexo removido com sucesso.')
        else:
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=anexos', 'Anexo não pode ser removido.', tag='error')
    else:
        raise PermissionDenied


@documento('Declaração de Orientação', enumerar_paginas=False, validade=360, modelo='projetos.participacao', forcar_recriacao=True)
@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def emitir_declaracao_orientacao_pdf(request, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_declaracao_orientacao():
        return httprr('/', 'Você não tem permissão para este acesso.', tag='error')
    else:
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
        hoje = datetime.datetime.now()
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes = meses[hoje.month - 1]

        title = str(participacao.projeto)
        participante = participacao.get_participante()
        nome = participante.pessoa_fisica.nome
        matricula = participante.matricula
        cpf = participante.pessoa_fisica.cpf and anonimizar_cpf(participante.pessoa_fisica.cpf)
        rg = participante.pessoa_fisica.rg
        rg_orgao = participante.pessoa_fisica.rg_orgao
        rg_uf = participante.pessoa_fisica.rg_uf
        vinculo = 'coordenador(a)'
        logradouro = participante.pessoa_fisica.endereco_logradouro
        bairro = participante.pessoa_fisica.endereco_bairro
        cidade = participante.pessoa_fisica.endereco_municipio
        orientacoes = HistoricoOrientacaoProjeto.objects.filter(
            Q(projeto=participacao.projeto), Q(orientador=participacao), Q(data_termino__gt=F('data_inicio')) | Q(data_termino__isnull=True)
        )
        em_execucao = participacao.projeto.get_status() == Projeto.STATUS_EM_EXECUCAO
        if not orientacoes.exists():
            return httprr(f'/projetos/projeto/{participacao.projeto.id}/?tab=equipe', 'Este participante não orientou nenhum aluno.', 'error')

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_avaliadores_externos')
def lista_email_avaliadores(request):
    title = 'Lista de Emails dos Avaliadores'

    avaliadores = AvaliadorExterno.objects.filter(ativo=True)
    emails = ''
    for contador, avaliador in enumerate(avaliadores, 1):
        emails = emails + avaliador.email + ';'
        if contador % 10:
            emails = emails + '\n'

    areas = AreaTematica.objects.all()
    avaliadores_internos = set()
    for area in areas:
        for pessoa in area.vinculo.exclude(tipo_relacionamento__model='aluno'):
            if pessoa.email_notificacao:
                avaliadores_internos.add(pessoa.email_notificacao)
    emails_internos = ''
    for contador, avaliador in enumerate(sorted(avaliadores_internos), 1):
        emails_internos = emails_internos + avaliador + ';'
        if contador % 10:
            emails_internos = emails_internos + '\n'

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
def listar_projetos_em_atraso(request):
    title = 'Lista de Projetos em Atraso'
    form = ProjetosAtrasadosForm(request.GET or None, request=request)
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos = (
        Projeto.objects.filter(
            pre_aprovado=True,
            aprovado=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            data_finalizacao_conclusao__isnull=True,
            inativado=False,
            concluido=False,
        )
        .exclude(id__in=projetos_cancelados)
        .order_by('fim_execucao')
    )
    if not request.user.has_perm('projetos.pode_visualizar_avaliadores_externos'):
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
@permission_required('projetos.pode_visualizar_avaliadores_externos')
def listar_avaliadores_de_projetos(request):
    title = 'Lista de Avaliadores de Projeto'
    form = ListaAvaliadoresProjetosForm(request.GET or None)

    if request.GET:
        avaliadores = AvaliadorIndicado.objects.all().order_by('vinculo__pessoa__nome').distinct('vinculo__pessoa__nome')
        if 'edital' in request.GET and request.GET.get('edital'):
            avaliadores = avaliadores.filter(projeto__edital=request.GET.get('edital'))

        if 'tipo' in request.GET and request.GET.get('tipo') == '1':
            avaliadores = avaliadores.filter(vinculo__tipo_relacionamento__model='servidor')

        if 'tipo' in request.GET and request.GET.get('tipo') == '2':
            avaliadores = avaliadores.filter(vinculo__tipo_relacionamento__model='prestadorservico')
        if 'area_tematica' in request.GET and request.GET.get('area_tematica'):
            area = AreaTematica.objects.filter(id=request.GET.get('area_tematica'))
            avaliadores = avaliadores.filter(vinculo__in=area.values_list('vinculo', flat=True))

        if 'xls' in request.GET:
            return tasks.listar_avaliadores_de_projetos_export_to_xls(avaliadores)

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def ver_alteracoes_data(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
    title = 'Alterações no Período de Execução do Projeto'
    mesmo_campus = projeto.uo == get_uo(request.user)
    is_pre_avaliador = (request.user.groups.filter(name='Coordenador de Extensão').exists() and mesmo_campus) or request.user.has_perm(
        'projetos.view_historicoalteracaoperiodoprojeto'
    )
    registros = HistoricoAlteracaoPeriodoProjeto.objects.filter(projeto=projeto)

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
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
@permission_required('projetos.pode_visualizar_projeto')
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
        o.vinculo_avaliado_por = request.user.get_vinculo()
        o.save()
        ids_valores = str(CriterioAvaliacaoAluno.objects.values_list('id', flat=True))
        for item in list(request.POST.items()):
            if item[1] and item[0] in ids_valores:
                novo_criterio = ItemAvaliacaoAluno()
                novo_criterio.criterio = get_object_or_404(CriterioAvaliacaoAluno, pk=item[0])
                novo_criterio.avaliacao = o
                novo_criterio.pontuacao = item[1]
                novo_criterio.save()

        titulo = '[SUAP] Projeto de Extensão: Registrar Considerações em Avaliação'
        url = f'{settings.SITE_URL}/projetos/registrar_consideracoes_aluno/{o.id}/'
        texto = (
            '<h1>Projeto de Extensão</h1>'
            '<h2>Registrar Considerações em Avaliação</h2>'
            f"<p>O Coordenador do Projeto '{participacao.projeto.titulo}' registrou a avaliação do seu desempenho. Por favor, acesse o SUAP para registrar suas considerações: {url}</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.vinculo_pessoa])
        return httprr(f'/projetos/avaliacoes_aluno/{participacao.id}/', 'Avaliação cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def ver_avaliacao_aluno(request: HttpRequest, avaliacao_id: int) -> dict:
    avaliacao = get_object_or_404(AvaliacaoAluno, pk=avaliacao_id)
    if not avaliacao.participacao.pode_ver_avaliacoes():
        raise PermissionDenied
    title = f'Avaliação - {avaliacao.participacao.vinculo_pessoa.pessoa.nome}'
    itens = ItemAvaliacaoAluno.objects.filter(avaliacao=avaliacao)

    return locals()


@rtr()
@permission_required('projetos.pode_registrar_consideracao_aluno')
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
        return httprr(f'/projetos/projeto/{avaliacao.participacao.projeto.id}/?tab=equipe', 'Avaliação validada com sucesso.')

    return locals()


@transaction.atomic
@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def deletar_participante(request, participacao_id):
    url = request.META.get('HTTP_REFERER', '.')
    participante = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participante.projeto
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
        if projeto.auxiliar and projeto.auxiliar == participante.vinculo_pessoa:
            projeto.auxiliar = None
            projeto.save()
        participante.delete()
        return httprr(url, 'Participante removido com sucesso.')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_extrato_mensal(request, extrato_id):
    title = 'Editar Extrato Mensal'
    extrato = get_object_or_404(ExtratoMensalProjeto, pk=extrato_id)
    if extrato.projeto.pode_editar_inscricao_execucao():
        form = ExtratoMensalForm(request.POST or None, instance=extrato, projeto=extrato.projeto)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos/projeto/{extrato.projeto.id}/?tab=prestacao_contas', 'Extrato editado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_extrato_mensal(request, extrato_id):
    extrato = get_object_or_404(ExtratoMensalProjeto, pk=extrato_id)
    projeto = extrato.projeto
    if extrato.projeto.pode_editar_inscricao_execucao():
        extrato.delete()
        return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Extrato removido com sucesso.')

    raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_termo_cessao(request, termo_id):
    title = 'Editar Termo de Cessão/Doação'
    termo = get_object_or_404(RegistroGasto, pk=termo_id)
    projeto = termo.desembolso.projeto
    if projeto.pode_editar_inscricao_execucao():
        form = EditarTermoCessaoForm(request.POST or None, request.FILES or None, instance=termo)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Termo de Cessão editado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_termo_cessao(request, termo_id):
    termo = get_object_or_404(RegistroGasto, pk=termo_id)
    projeto = termo.desembolso.projeto
    if projeto.pode_editar_inscricao_execucao():
        termo.arquivo_termo_cessao = None
        termo.obs_cessao = None
        termo.save()
        return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Termo de cessão/doação removido com sucesso.')

    raise PermissionDenied


@rtr()
@transaction.atomic
@permission_required('projetos.pode_se_tornar_avaliador')
def indicar_areas_tematicas_de_interesse(request):
    title = 'Tornar-se Avaliador: Indique as Áreas Temáticas de seu Interesse'
    vinculo_pessoa = request.user.get_vinculo()
    areas_tematicas = AreaTematica.objects.filter(vinculo=vinculo_pessoa).order_by('descricao')
    form = ProjetoAvaliadorForm(data=request.POST or None, request=request, pessoa=vinculo_pessoa)
    if form.is_valid():
        ids_areas = []
        for area in form.cleaned_data.get('areas_tematicas_extensao'):
            ids_areas.append(area.id)
            if vinculo_pessoa not in area.vinculo.all():
                area.vinculo.add(vinculo_pessoa)
        outras_areas = AreaTematica.objects.exclude(id__in=ids_areas)
        if outras_areas.exists():
            for area in outras_areas:
                area.vinculo.remove(vinculo_pessoa)

        return httprr('.', 'Área de conhecimento cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def adicionar_tema_edital(request, edital_id):
    title = 'Adicionar Tema'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    temas = Tema.objects.all().order_by('areatematica__descricao', 'descricao')
    todos_temas = []
    for tema in temas:
        if edital.temas.filter(id=tema.id).exists():
            todos_temas.append([tema, True])
        else:
            todos_temas.append([tema, False])
    form = EditalTemasForm(request.POST or None)
    if form.is_valid():
        todos_temas = []
        for tema in temas.filter(areatematica=form.cleaned_data.get('areatematica')):
            if edital.temas.filter(id=tema.id).exists():
                todos_temas.append([tema, True])
            else:
                todos_temas.append([tema, False])
    return locals()


@rtr()
@permission_required('projetos.view_edital')
def salvar_temas_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    a_deferir = request.POST.getlist('registros')
    if a_deferir:
        for item in a_deferir:
            tema = get_object_or_404(Tema, pk=int(item))
            edital.temas.add(tema)

        return httprr(f'/projetos/adicionar_tema_edital/{edital.id}', 'Temas adicionados com sucesso.')
    else:
        return httprr(f'/projetos/adicionar_tema_edital/{edital.id}', 'Nenhum tema selecionado.', tag='error')


@rtr()
@permission_required('projetos.view_edital')
def remover_tema_edital(request, edital_id, tema_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    tema = get_object_or_404(Tema, pk=tema_id)
    edital.temas.remove(tema)
    if request.GET.get('origem') == '2':
        return httprr(f'/projetos/adicionar_tema_edital/{edital.id}/', 'Tema removido com sucesso.')
    return httprr(f'/projetos/edital/{edital.id}/?tab=oferta_por_tema', 'Tema removido com sucesso.')


@permission_required('projetos.pode_interagir_com_projeto')
def filtrar_editais_por_ano(request):
    data = '[]'
    if request.method == 'GET':
        ano = request.GET.get('ano')
        if ano and ano != 'Selecione um ano':
            registro = Edital.objects.filter(inicio_inscricoes__year=ano).order_by('-inicio_inscricoes')
            if registro.exists():
                from django.core import serializers

                data = serializers.serialize('json', list(registro.all()), fields=('titulo', 'id'))
    return HttpResponse(data, content_type='application/json')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_comprovante_gru(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Adicionar Comprovante de Pagamento de GRU'
        if request.POST:
            form = ComprovanteGRUForm(request.POST or None, request.FILES, instance=projeto)
            if form.is_valid():
                o = form.save(False)
                o.projeto = projeto
                o.save()
                if projeto.edital.ocultar_aba_prestacao_contas:
                    return httprr(f'/projetos/projeto/{projeto.id}/?tab=plano_desembolso', 'Comprovante cadastrado com sucesso.')
                else:
                    return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Comprovante cadastrado com sucesso.')
        else:
            form = ComprovanteGRUForm(request.POST or None, instance=projeto)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_comprovante_gru(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        projeto.arquivo_comprovante_gru = None
        projeto.save()
        return httprr(f'/projetos/projeto/{projeto.id}/?tab=prestacao_contas', 'Comprovante removido com sucesso.')

    raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def indicar_orientador(request, participacao_id):
    title = 'Indicar Orientador'
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.is_servidor():
        return httprr('..', 'O participante não é aluno.', tag='error')
    projeto = participacao.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editais(request):
    title = 'Todos os editais'
    editais = Edital.objects.filter(publicado=True)
    tem_aviso = Configuracao.get_valor_por_chave('projetos', 'aviso_editais')
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
@permission_required('projetos.pode_se_tornar_avaliador')
def cancelar_avaliacao_etapa(request, registroexecucao_id):
    registro = get_object_or_404(RegistroExecucaoEtapa, pk=registroexecucao_id)
    is_gerente_sistemico = request.user.has_perm('projetos.pode_gerenciar_edital')
    projeto = registro.etapa.meta.projeto
    pode_validar = (projeto.vinculo_monitor == request.user.get_vinculo()) or is_gerente_sistemico
    if pode_validar and not projeto.eh_somente_leitura():
        registro.justificativa_reprovacao = ''
        registro.dt_avaliacao = None
        registro.avaliador = None
        registro.aprovado = False
        registro.save()
        return httprr(f'/projetos/validar_execucao_etapa/{projeto.pk}/?tab=metas', 'Avaliação da atividade cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def cancelar_avaliacao_gasto(request, registrogasto_id):
    registro = get_object_or_404(RegistroGasto, pk=registrogasto_id)
    is_gerente_sistemico = request.user.has_perm('projetos.pode_gerenciar_edital')
    projeto = registro.desembolso.projeto
    pode_validar = (projeto.vinculo_monitor == request.user.get_vinculo()) or is_gerente_sistemico
    if pode_validar and not projeto.eh_somente_leitura():
        registro.justificativa_reprovacao = None
        registro.dt_avaliacao = None
        registro.avaliador = None
        registro.aprovado = False
        registro.save()
        return httprr(f'/projetos/validar_execucao_etapa/{projeto.pk}/?tab=gastos', 'Avaliação do gasto cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def desvincular_participante_atividades(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if not participacao.projeto.is_coordenador(request.user):
        raise PermissionDenied
    if participacao.projeto.eh_somente_leitura():
        raise PermissionDenied
    for etapa in Etapa.objects.filter(integrantes=participacao):
        etapa.integrantes.remove(participacao)
    return httprr('..', 'Participante removido das atividades com sucesso.')


@rtr()
@permission_required('projetos.pode_visualizar_avaliadores_externos')
def listar_avaliadores(request):
    title = 'Lista de Avaliadores Cadastrados'
    form = AvaliadoresAreaTematicaForm(request.GET or None, request=request)
    if form.is_valid():
        areas_vinculos = Vinculo.objects.exclude(tipo_relacionamento__model='aluno').filter(
            id__in=AreaTematica.objects.all().values_list('vinculo', flat=True)
        )
        avaliadores = Vinculo.objects.filter(id__in=areas_vinculos).order_by('pessoa__nome')
        area_tematica = form.cleaned_data['area_tematica']
        palavra_chave = form.cleaned_data['palavra_chave']
        vinculo = form.cleaned_data.get('vinculo')
        situacao = form.cleaned_data.get('situacao')
        uo = form.cleaned_data.get('uo')
        instituicoes = form.cleaned_data.get('instituicoes')
        if area_tematica:
            ids_pessoas = []
            area = AreaTematica.objects.get(id=area_tematica.id)
            for pessoa in area.vinculo.exclude(tipo_relacionamento__model='aluno'):
                ids_pessoas.append(pessoa.id)
            avaliadores = avaliadores.filter(id__in=ids_pessoas)
        if uo:
            avaliadores = avaliadores.filter(tipo_relacionamento__model='servidor', id_relacionamento__in=Servidor.objects.filter(setor__uo=uo.id))
        if palavra_chave:
            avaliadores = avaliadores.filter(pessoa__nome__icontains=palavra_chave)
        if vinculo:
            if vinculo == 'Interno':
                avaliadores = avaliadores.filter(tipo_relacionamento__model='servidor')
            elif vinculo == 'Externo':
                avaliadores = avaliadores.filter(tipo_relacionamento__model='prestadorservico')
        if situacao:
            if situacao == 'Ativos':
                avaliadores = avaliadores.filter(
                    Q(tipo_relacionamento__model='servidor'),
                    id_relacionamento__in=Servidor.objects.ativos().filter(ativo=True).values_list('id', flat=True),
                ) | avaliadores.filter(tipo_relacionamento__model='prestadorservico')
            else:
                avaliadores = avaliadores.filter(
                    Q(tipo_relacionamento__model='servidor'),
                    Q(id_relacionamento__in=Servidor.objects.inativos().values_list('id', flat=True))
                    | Q(id_relacionamento__in=Servidor.objects.filter(ativo=False).values_list('id', flat=True)),
                ) | avaliadores.filter(tipo_relacionamento__model='prestadorservico')
        if instituicoes:
            avaliadores_por_instituicao = AvaliadorExterno.objects.filter(instituicao_origem__nome=instituicoes)
            avaliadores = avaliadores.filter(id__in=avaliadores_por_instituicao.values_list('vinculo', flat=True))
    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def validar_projeto_externo(request: HttpRequest, projeto_id: int, opcao: str) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    # mesmas condições dos botões "Deferir/Indeferir Registro" (projeto.html)
    pode_validar = (
        not projeto.eh_fomento_interno()
        and not projeto.aprovado
        and not projeto.data_avaliacao
        and projeto.data_conclusao_planejamento
        and request.user.get_vinculo() == projeto.vinculo_monitor
    )
    if pode_validar:
        if opcao == '1':
            projeto.pre_aprovado = True
            projeto.aprovado = True
            projeto.data_pre_avaliacao = datetime.date.today()
            projeto.data_avaliacao = datetime.date.today()
            projeto.vinculo_autor_pre_avaliacao = request.user.get_vinculo()
            projeto.vinculo_autor_avaliacao = request.user.get_vinculo()
            projeto.save()
            return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto deferido com sucesso.')
        elif opcao == '2':
            projeto.pre_aprovado = False
            projeto.aprovado = False
            projeto.data_pre_avaliacao = datetime.date.today()
            projeto.data_avaliacao = datetime.date.today()
            projeto.vinculo_autor_pre_avaliacao = request.user.get_vinculo()
            projeto.vinculo_autor_avaliacao = request.user.get_vinculo()
            projeto.save()
            return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto indeferido com sucesso.')

        else:
            raise PermissionDenied

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
def estatisticas(request):
    projetos = Projeto.objects.all()
    if not request.user.has_perm('projetos.pode_visualizar_avaliadores_externos'):
        campus_do_usuario = get_uo(request.user)
        projetos = projetos.filter(uo=campus_do_usuario)
        title = f'Indicadores de Projetos de Extensão - Campus {campus_do_usuario}'
    else:
        title = 'Indicadores de Projetos de Extensão'
    ano = request.GET.get('ano')
    form = EstatisticasForm(request.GET or None, ano=ano, request=request)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')
        tipo_fomento = form.cleaned_data.get('tipo_fomento')
        cunho_social = form.cleaned_data.get('cunho_social')
        acoes_empreendedorismo = form.cleaned_data.get('acoes_empreendedorismo')
        vinculados_nepps = form.cleaned_data.get('vinculados_nepps')
        executado_com_parceria = form.cleaned_data.get('executado_com_parceria')
        integracao_curricular = form.cleaned_data.get('integracao_curricular')
        inicio_periodo = form.cleaned_data.get('inicio_periodo')
        fim_periodo = form.cleaned_data.get('fim_periodo')
        if inicio_periodo:
            projetos = projetos.filter(inicio_execucao__gte=inicio_periodo)
        if fim_periodo:
            projetos = projetos.filter(inicio_execucao__lte=fim_periodo)
        if ano:
            projetos = projetos.filter(inicio_execucao__year=ano)
        if edital:
            projetos = projetos.filter(edital=edital)
        if campus:
            projetos = projetos.filter(uo=campus)
        if form.cleaned_data.get('tipo_edital'):
            if form.cleaned_data.get('tipo_edital') == 'Edital de Campus':
                projetos = projetos.filter(edital__campus_especifico=True)
            elif form.cleaned_data.get('tipo_edital') == 'Edital Sistêmico':
                projetos = projetos.filter(edital__campus_especifico=False)
        if tipo_fomento:
            projetos = projetos.filter(edital__tipo_fomento=tipo_fomento)
        if cunho_social:
            projetos = projetos.filter(possui_cunho_social=True)
        if acoes_empreendedorismo:
            projetos = projetos.filter(possui_acoes_empreendedorismo=True)
        if vinculados_nepps:
            projetos = projetos.filter(nucleo_extensao__isnull=False)
        if executado_com_parceria:
            projetos = projetos.filter(id__in=TermoParceriaAdesao.objects.values_list('projeto', flat=True))
        if integracao_curricular:
            projetos = projetos.filter(atividade_integracao_curricular=True)

        hoje = datetime.datetime.now()
        enviados = projetos.filter(
            Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
        )

        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)

        if request.user.has_perm('projetos.pode_gerenciar_edital'):
            aprovados = enviados.filter(aprovado=True, pre_aprovado=True)
        else:
            aprovados = enviados.filter(aprovado=True, pre_aprovado=True, edital__divulgacao_selecao__lt=hoje)
        nao_concluidos = aprovados.filter(registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False)
        execucao = nao_concluidos.filter(edital__divulgacao_selecao__lt=hoje) | nao_concluidos.filter(edital__tipo_fomento=Edital.FOMENTO_EXTERNO)

        execucao = execucao.exclude(id__in=projetos_cancelados)
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
        for area in AreaTematica.objects.all():
            valor = aprovados.filter(area_tematica=area).count()
            if valor:
                dados2.append([area.descricao, valor])

        grafico2 = PieChart(
            'grafico2',
            title='Projetos por Área Temática',
            subtitle='Quantidade de projetos aprovados por área temática',
            minPointLength=0,
            data=dados2,
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
            Servidor.objects.filter(ativo=True, vinculos__id__in=bolsistas.values_list('vinculo_pessoa', flat=True), eh_docente=True)
            .distinct()
            .count()
        )
        docentes_voluntarios = (
            Servidor.objects.filter(ativo=True, vinculos__id__in=voluntarios.values_list('vinculo_pessoa', flat=True), eh_docente=True)
            .distinct()
            .count()
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

        dados6 = []
        dados6.append(['Executado com parceria', aprovados.filter(id__in=TermoParceriaAdesao.objects.values_list('projeto', flat=True)).count()])
        dados6.append(['Executado sem parceria', aprovados.exclude(id__in=TermoParceriaAdesao.objects.values_list('projeto', flat=True)).count()])

        grafico6 = ColumnChart(
            'grafico6',
            title='Execução com Parceria',
            subtitle='Quantidade de projetos executados com e sem parceria institucional',
            minPointLength=0,
            data=dados6,
        )

        grafico6.id = 'grafico6'

        dados7 = []
        dados7.append(['Quantidade de Parcerias', TermoParceriaAdesao.objects.filter(projeto__in=aprovados.values_list('id', flat=True)).count()])

        grafico7 = ColumnChart(
            'grafico7',
            title='Quantidade de Parcerias',
            subtitle='Quantidade de parcerias firmadas pelos projetos executados',
            minPointLength=0,
            data=dados7,
        )

        grafico7.id = 'grafico7'

        dados8 = []
        dados8.append(['Quantidade de projetos', aprovados.filter(atividade_integracao_curricular=True).count()])

        grafico8 = ColumnChart(
            'grafico8',
            title='Projetos com atividades da Integração Curricular da Extensão',
            subtitle='Quantidade de projetos com atividades da Integração Curricular da Extensão',
            minPointLength=0,
            data=dados8,
        )

        grafico8.id = 'grafico8'

        pie_chart_lists = [grafico, grafico2, grafico3, grafico4, grafico5, grafico6, grafico7, grafico8]

    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def inativar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    if not projeto.inativado and projeto.is_gerente_sistemico(usuario_logado):
        execucao_de_testes = running_tests()
        title = f'Inativar Projeto - {projeto.titulo}'
        form = InativarProjetoForm(request.POST or None, instance=projeto)
        if not execucao_de_testes:
            documentos = inlineformset_factory(
                Projeto,
                ArquivoInativacaoProjeto,
                fields=['descricao', 'arquivo'],
                can_delete=False,
                extra=0,
                form=ArquivoInativacaoProjetoForm,
                formset=TermoParceriaAdesaoInlineFormSet,
                min_num=0,
            )
            formset = documentos(request.POST or None, request.FILES or None)
        if request.method == 'POST':
            if execucao_de_testes:
                formset_valido = True
            else:
                formset_valido = formset.is_valid()
            if form.is_valid() and formset_valido:
                o = form.save(False)
                o.inativado = True
                o.inativado_em = datetime.datetime.now()
                o.inativado_por = request.user.get_relacionamento()
                o.save()
                if not execucao_de_testes:
                    formset.instance = form.instance
                    formset.save()
                historico = ProjetoHistoricoDeEnvio()
                historico.projeto = projeto
                historico.parecer_devolucao = 'Projeto inativado'
                historico.data_operacao = datetime.datetime.now()
                historico.operador = request.user.get_relacionamento()
                historico.save()
                return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto inativado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def clonar_projeto(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    pode_submeter_novo_projeto(request, edital)
    retorno = pode_submeter_novo_projeto(request, edital)
    if retorno:
        return httprr('/projetos/editais_abertos/', retorno, tag='error')
    title = f'Clonar Projeto no Edital: {edital}'
    form = ClonarProjetoForm(request.POST or None, request=request, edital=edital)
    if form.is_valid():
        projeto_clonado = form.processar()
        return httprr(f'/projetos/projeto/{projeto_clonado.id}/', 'Projeto clonado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def clonar_etapa(request, meta_id):
    title = 'Clonar Atividade'
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = ClonarEtapaForm(request.POST or None, projeto=projeto)
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
    else:
        raise PermissionDenied


# View que se conecta a view rh.views.servidor


@receiver(rh_servidor_view_tab)
def servidor_view_tab_visitas_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    visitas_tecnicas = VisitaTecnica.objects.filter(participantes=servidor).order_by('-data')

    if visitas_tecnicas and verificacao_propria:
        return render_to_string(
            template_name='projetos/templates/servidor_view_tab.html',
            context={'lps_context': {'nome_modulo': 'projetos'}, 'servidor': servidor, 'visitas_tecnicas': visitas_tecnicas},
            request=request,
        )
    return False


@receiver(rh_servidor_view_tab)
def servidor_view_tab_participacoes_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    participacoes_extensao = Participacao.objects.filter(
        vinculo_pessoa__id_relacionamento=servidor.id, vinculo_pessoa__tipo_relacionamento__model='servidor', projeto__aprovado=True
    ).select_related('projeto', 'projeto__edital', 'vinculo_pessoa')

    if participacoes_extensao.exists():
        return render_to_string(
            template_name='projetos/templates/servidor_view_tab.html',
            context={
                'lps_context': {'nome_modulo': 'projetos'},
                'servidor': servidor,
                'participacoes_extensao': participacoes_extensao,
                'verificacao_propria': verificacao_propria,
            },
            request=request,
        )
    return False


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def cancelar_pre_avaliacao_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    url = request.META.get('HTTP_REFERER', '.')
    if projeto.pode_cancelar_pre_avaliacao():
        projeto.pre_aprovado = False
        projeto.aprovado = False
        projeto.data_pre_avaliacao = None
        projeto.data_avaliacao = None
        projeto.save()
        ItemPreSelecao.objects.filter(avaliacao__projeto=projeto).delete()
        PreSelecao.objects.filter(projeto=projeto).delete()
        return httprr(url, 'Pré-avaliação cancelada com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
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
        coordenador = form.cleaned_data.get('coordenador')
        if request.user.has_group_cached(['Coordenador de Extensão', 'Visualizador de Projetos do Campus']):
            registros = CaracterizacaoBeneficiario.objects.filter(projeto__uo=get_uo(request.user), projeto__aprovado=True).order_by('-projeto')
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

        if coordenador:
            registros = registros.filter(projeto__vinculo_coordenador=coordenador)

        total_prevista = registros.aggregate(total=Sum('quantidade'))['total']
        total_atendida = registros.aggregate(total=Sum('quantidade_atendida'))['total']

        if 'xls' in request.GET:
            return tasks.relatorio_caracterizacao_beneficiarios_to_xls(registros)
    return locals()


@documento('Declaração de Participação', enumerar_paginas=False, validade=360, modelo='projetos.participacao', forcar_recriacao=True)
@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def emitir_declaracao_participacao_pdf(self, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_declaracao_de_participacao():
        return httprr('/', 'Você não tem permissão para ver isso.', 'error')
    carga_horaria = participacao.carga_horaria
    participante = participacao.get_participante()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
    fim_projeto = participacao.projeto.fim_execucao
    inicio_projeto = participacao.projeto.inicio_execucao
    historico = (
        HistoricoEquipe.objects.filter(ativo=True, participante=participacao)
        .order_by('id')
        .exclude(data_movimentacao__gte=F('data_movimentacao_saida'))
        .exclude(data_movimentacao_saida__lt=inicio_projeto)
        .exclude(data_movimentacao__gt=fim_projeto)
        .exclude(movimentacao='Ativado')
        .exclude(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)
    )

    eh_aluno = False
    eh_estrangeiro = False
    possui_bolsa = False
    if participacao.vinculo == TipoVinculo.BOLSISTA:
        possui_bolsa = True

    eh_coordenador = False
    if participacao.responsavel:
        eh_coordenador = True

    if participacao.is_servidor():
        nome = participante.pessoa_fisica.nome
        cpf = participante.pessoa_fisica.cpf and anonimizar_cpf(participante.pessoa_fisica.cpf)
        rg = participante.pessoa_fisica.rg
        rg_orgao = participante.pessoa_fisica.rg_orgao
        rg_uf = participante.pessoa_fisica.rg_uf
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
        cpf = participante.pessoa_fisica.cpf and anonimizar_cpf(participante.pessoa_fisica.cpf)
        rg = participante.pessoa_fisica.rg
        rg_orgao = participante.pessoa_fisica.rg_orgao
        rg_uf = participante.pessoa_fisica.rg_uf
        logradouro = participante.logradouro
        bairro = participante.bairro
        cidade = participante.cidade
    else:
        nome = participante.nome
        if participante.prestador.pessoa_fisica.cpf:
            cpf = participante.prestador.pessoa_fisica.cpf and anonimizar_cpf(participante.prestador.pessoa_fisica.cpf)
            rg = participante.prestador.pessoa_fisica.rg
            rg_orgao = participante.prestador.pessoa_fisica.rg_orgao
            rg_uf = participante.prestador.pessoa_fisica.rg_uf
        else:
            eh_estrangeiro = True
            cpf = participante.prestador.matricula
        logradouro = participante.prestador.pessoa_fisica.endereco_logradouro
        bairro = participante.prestador.pessoa_fisica.endereco_bairro
        cidade = participante.prestador.pessoa_fisica.endereco_municipio
        vinculo = 'membro'
    if historico.exists():
        if historico.last().data_movimentacao > participacao.projeto.inicio_execucao:
            data_inicio_vinculo = historico.last().data_movimentacao
        else:
            data_inicio_vinculo = participacao.projeto.inicio_execucao

        if not participacao.ativo and participacao.data_inativacao:
            data_fim_vinculo = participacao.data_inativacao
        elif not participacao.ativo and participacao.historicoequipe_set.filter(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE).exists():
            data_fim_vinculo = participacao.historicoequipe_set.filter(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)[
                0
            ].data_movimentacao
        else:
            if historico.last().data_movimentacao_saida:
                if historico.last().data_movimentacao_saida < participacao.projeto.fim_execucao:
                    data_fim_vinculo = historico.last().data_movimentacao_saida
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
    tipo_vinculo = TipoVinculo()
    data_fim_execucao_expirada = hoje.date() > participacao.projeto.fim_execucao
    return locals()


@rtr()
@permission_required('projetos.change_projeto')
def reativar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    if projeto.inativado and projeto.is_gerente_sistemico(usuario_logado):
        projeto.inativado = False
        projeto.inativado_em = None
        projeto.inativado_por = None
        projeto.save()
        historico = ProjetoHistoricoDeEnvio()
        historico.projeto = projeto
        historico.parecer_devolucao = 'Projeto reativado'
        historico.data_operacao = datetime.datetime.now()
        historico.operador = request.user.get_relacionamento()
        historico.save()
        return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto reativado com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_desembolsos(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.POST.get('action') == 'Remover':
            deletar = request.POST.getlist('registros')
            if deletar:
                for item in deletar:
                    desembolso = get_object_or_404(Desembolso, pk=int(item))
                    if desembolso.projeto.id == projeto.id:
                        desembolso.delete()
                return httprr(f'/projetos/projeto/{projeto.id}/?tab=plano_desembolso', 'Desembolso(s) excluído(s) com sucesso.')
            else:
                return httprr(f'/projetos/projeto/{projeto.id}/?tab=plano_desembolso', 'Nenhum desembolso selecionado.', tag='error')
        else:
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=plano_desembolso', 'Nenhum desembolso selecionado.', tag='error')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
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

            return httprr(f'/projetos/projeto/{projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária cadastrada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
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
@permission_required('projetos.pode_visualizar_projeto')
def gerar_lista_frequencia(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_participante = projeto.eh_participante(request.user)
    usuario_logado = request.user
    is_gerente_sistemico = projeto.is_gerente_sistemico(usuario_logado)
    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Extensão').exists() and mesmo_campus
    eh_visualizador = usuario_logado.groups.filter(name='Visualizador de Projetos').exists()
    eh_visualizador_campus = usuario_logado.groups.filter(name='Visualizador de Projetos do Campus').exists() and mesmo_campus
    eh_coordenador = projeto.is_responsavel(usuario_logado)
    pode_ver_frequencias = eh_coordenador or is_gerente_sistemico or is_pre_avaliador or eh_visualizador or eh_visualizador_campus
    title = 'Gerar Lista de Frequência/Atividade Diária'
    if eh_participante or pode_ver_frequencias:
        form = GerarListaFrequenciaForm(request.POST or None, projeto=projeto)
        if form.is_valid():
            registros = RegistroFrequencia.objects.filter(projeto=projeto).order_by('data')
            data_inicio = form.cleaned_data.get('data_inicio')
            data_termino = form.cleaned_data.get('data_termino')
            participante = form.cleaned_data.get('participante')
            situacao = form.cleaned_data.get('situacao')
            if data_inicio:
                registros = registros.filter(data__gte=data_inicio)
            if data_termino:
                registros = registros.filter(data__lte=data_termino)
            if participante:
                registros = registros.filter(cadastrada_por=participante)
            if situacao:
                if situacao == 'Pendentes':
                    registros = registros.filter(validada_por=None)
                else:
                    registros = registros.exclude(validada_por=None)
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
@permission_required('projetos.pode_visualizar_projeto')
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
                    if (not registro.validada_em and registro.cadastrada_por == vinculo_usuario) or projeto.is_responsavel(request.user):
                        registro.delete()
                return httprr(url_origem, 'Os Registros de Frequência/Atividade diária não validados foram excluídos com sucesso.')
            return httprr(url_origem, 'Nenhum registro selecionado.', tag='error')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def editar_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if not registro.validada_em and registro.cadastrada_por == request.user.get_vinculo():
        title = 'Editar Frequência/Atividade Diária'
        form = EditarFrequenciaForm(request.POST or None, instance=registro)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos/projeto/{registro.projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária editada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def excluir_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if not registro.validada_em and registro.cadastrada_por == request.user.get_vinculo():
        projeto = registro.projeto
        registro.delete()
        return httprr(f'/projetos/projeto/{projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária excluída com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def aceitar_termo_compromisso(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.vinculo_pessoa == request.user.get_vinculo():
        title = 'Aceitar Termo de Compromisso'
        form = AceiteTermoForm(request.POST or None, participacao=participacao, request=request)
        if form.is_valid():
            participacao.termo_aceito_em = datetime.datetime.now()
            participacao.save()
            return httprr(f'/projetos/projeto/{participacao.projeto.id}/?tab=equipe', 'Termo de compromisso aceito com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def alterar_chefia_imediata_participacao(request, participacao_id):
    title = 'Alterar Responsável pela Anuência do Participante'
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    usuario_logado = request.user
    is_gerente_sistemico = request.user.has_perm('projetos.pode_gerenciar_edital')
    is_coex = usuario_logado.groups.filter(name='Coordenador de Extensão').exists()
    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    is_pre_avaliador = is_coex and mesmo_campus
    if (is_pre_avaliador or is_gerente_sistemico) and participacao.exige_anuencia() and not participacao.anuencia_registrada_em:
        form = AlterarChefiaParticipanteForm(request.POST or None, instance=participacao)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos/projeto/{participacao.projeto.id}/?tab=equipe', 'Chefia imediata alterada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def participacoes_pendentes_anuencia(request):
    title = 'Participações Pendentes da Sua Anuência'
    servidor = vinculo = request.user.get_relacionamento()
    agora = datetime.datetime.now()
    participacoes = Participacao.objects.filter(
        responsavel_anuencia=servidor,
        projeto__projetocancelado__isnull=True,
        anuencia_registrada_em__isnull=True,
    )
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def registrar_anuencia_participacao(request: HttpRequest, participacao_id: int, opcao: str) -> HttpResponse:
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    agora = datetime.datetime.now()
    if request.user.get_relacionamento() == participacao.responsavel_anuencia:
        if opcao == '1':
            participacao.anuencia = True
        elif opcao == '2':
            participacao.anuencia = False
        else:
            raise Http404
        participacao.anuencia_registrada_em = agora
        participacao.save()
        return httprr('/projetos/participacoes_pendentes_anuencia/', 'Anuência registrada com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def cancelar_anuencia(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.exige_anuencia() and participacao.projeto.get_status() in (Projeto.STATUS_EM_INSCRICAO, Projeto.STATUS_EM_EXECUCAO):
        participacao.responsavel_anuencia = None
        participacao.anuencia = None
        participacao.anuencia_registrada_em = None
        participacao.save()
        return httprr(f'/projetos/projeto/{participacao.projeto.id}/?tab=equipe', 'Anuência cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr(two_factor_authentication=True)
@permission_required('projetos.pode_visualizar_projeto')
def cadastrar_dados_bancarios(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.vinculo_pessoa == request.user.get_vinculo() and not participacao.projeto.eh_somente_leitura():
        title = 'Cadastrar/Atualizar Dados Bancários'
        form = DadosBancariosParticipanteForm(request.POST or None, instance=participacao)
        if form.is_valid():
            form.save()
            titulo = '[SUAP] Extensão: Dados bancários atualizados'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Dados bancários atualizados</h2>'
                f"<p>Seus dados bancários cadastrados no projeto '{participacao.projeto.titulo}' foram atualizados. Se você não realizou esta alteração, procure o coordenador do projeto e o gerente de extensão do seu campus.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.vinculo_pessoa])
            return httprr(f'/projetos/projeto/{participacao.projeto.id}/?tab=equipe', 'Dados bancários atualizados com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('projetos.pode_gerenciar_edital')
def autorizar_edital(request: HttpRequest, edital_id: int, opcao: str) -> HttpResponse:
    edital = get_object_or_404(Edital, pk=edital_id)
    if edital.autorizado is None:
        if opcao == '1':
            edital.autorizado = True
        elif opcao == '2':
            edital.autorizado = False
        else:
            # opção inválida gravava quem autorizou e quando, com `autorizado` vazio (#17551)
            raise Http404
        edital.autorizado_por = request.user.get_vinculo()
        edital.autorizado_em = datetime.datetime.now()
        edital.save()
        return httprr('/admin/projetos/edital/', 'Edital avaliado com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def indicar_auxiliar_projeto(request, projeto_id):
    title = 'Indicar Membro Auxiliar do Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = IndicarAuxiliarForm(request.POST or None, instance=projeto)
        if form.is_valid():
            form.save()
            titulo = '[SUAP] Extensão: Indicação como Membro Auxiliar'
            url = f'{settings.SITE_URL}/projetos/projeto/{projeto.id}/'
            texto = (
                '<h1>Extensão</h1>'
                '<h2> Indicação como Membro Auxiliar</h2>'
                f'<p>Você foi indicado(a) como membro auxiliar da equipe do projeto <a href="{url}"> \'{projeto.titulo}\'</a>. Assim, você tem a permissão de gerenciar os dados do projeto. Acesse o SUAP para mais detalhes.</p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('auxiliar')])

            return httprr('..', 'Membro auxiliar indicado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def lista_todos_os_projetos(request):
    if (
        request.user.has_perm('projetos.pode_avaliar_projeto')
        or request.user.has_perm('projetos.pode_pre_avaliar_projeto')
        or request.user.has_group_cached('Visualizador de Projetos')
    ):
        return httprr('/admin/projetos/projeto/')
    else:
        uo = get_uo(request.user)
        if uo:
            return httprr(f'/admin/projetos/projeto/?uo={uo.id}&tab=tab_any_data')
        return httprr('/admin/projetos/projeto/')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_termo(request, projeto_id):
    title = 'Adicionar Comprovante de Parceria/Adesão do Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = TermoParceriaAdesaoForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            o.save()
            return httprr('..', 'Comprovante de Parceria/Adesão cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_termo(request, termo_id):
    title = 'Editar Comprovante de Parceria/Adesão do Projeto'
    termo = get_object_or_404(TermoParceriaAdesao, pk=termo_id)
    projeto = termo.projeto
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = TermoParceriaAdesaoForm(request.POST or None, request.FILES or None, instance=termo)
        if form.is_valid():
            form.save()
            return httprr('..', 'Comprovante de Parceria/Adesão editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_termo(request, termo_id):
    termo = get_object_or_404(TermoParceriaAdesao, pk=termo_id)
    projeto = termo.projeto
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        termo.delete()
        return httprr(f'/projetos/projeto/{projeto.id}/', 'Comprovante de Parceria/Adesão excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def lista_nepp(request):
    title = 'Núcleos de Extensão e Prática Profissional - NEPP'
    nucleos = NucleoExtensao.objects.filter(ativo=True)
    form = FiltrarNEPPForm(request.POST or None)
    if form.is_valid():
        uo = form.cleaned_data.get('uo')
        if uo:
            nucleos = nucleos.filter(uo=uo)
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def visualizar_nepp(request, nepp_id):
    nucleo = get_object_or_404(NucleoExtensao, pk=nepp_id)
    title = f'Visualizar NEPP - {nucleo!s}'
    pode_gerenciar = request.user.has_perm('projetos.pode_gerenciar_edital') or nucleo.coordenador == request.user.get_vinculo()
    hoje = datetime.datetime.now()
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    nao_concluidos = Projeto.objects.filter(
        pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False
    ).exclude(id__in=projetos_cancelados)
    nao_concluidos.filter(edital__divulgacao_selecao__lt=hoje) | nao_concluidos.filter(edital__tipo_fomento=Edital.FOMENTO_EXTERNO)
    projetos_nepp = nao_concluidos.filter(nucleo_extensao=nucleo)
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def cadastrar_membro_nepp(request, nepp_id):
    nucleo = get_object_or_404(NucleoExtensao, pk=nepp_id)
    title = f'Cadastrar Membro da Equipe - {nucleo!s}'
    pode_gerenciar = request.user.has_perm('projetos.pode_gerenciar_edital') or nucleo.coordenador == request.user.get_vinculo()
    if pode_gerenciar:
        form = MembroNEPPForm(request.POST or None)
        if form.is_valid():
            o = form.save(False)
            o.nepp = nucleo
            o.save()
            return httprr(f'/projetos/visualizar_nepp/{nucleo.id}/', 'Membro da equipe cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_membro_nepp(request, membro_id):
    membro = get_object_or_404(MembroNEPP, pk=membro_id)
    nepp = membro.nepp
    pode_gerenciar = request.user.has_perm('projetos.pode_gerenciar_edital') or nepp.coordenador == request.user.get_vinculo()
    if pode_gerenciar:
        membro.delete()
        return httprr(f'/projetos/visualizar_nepp/{nepp.id}/', 'Membro excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def cadastrar_foto_nepp(request, nepp_id):
    nucleo = get_object_or_404(NucleoExtensao, pk=nepp_id)
    title = f'Cadastrar Foto - {nucleo!s}'
    pode_gerenciar = request.user.has_perm('projetos.pode_gerenciar_edital') or nucleo.coordenador == request.user.get_vinculo()
    if pode_gerenciar:
        form = FotoNEPPForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.nepp = nucleo
            o.save()
            return httprr(f'/projetos/visualizar_nepp/{nucleo.id}/?tab=fotos', 'Foto cadastrada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def excluir_foto_nepp(request, foto_id):
    foto = get_object_or_404(FotoNEPP, pk=foto_id)
    nepp = foto.nepp
    pode_gerenciar = request.user.has_perm('projetos.pode_gerenciar_edital') or nepp.coordenador == request.user.get_vinculo()
    if pode_gerenciar:
        foto.delete()
        return httprr(f'/projetos/visualizar_nepp/{nepp.id}/?tab=fotos', 'Foto excluída com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_visualizar_relatorios_extensao')
def relatorio_financeiro(request: HttpRequest) -> dict | HttpResponse:
    title = 'Relatório Financeiro'
    campus_restrito = campus_do_coordenador_extensao(request.user)

    form = RelatorioFinanceiroExtensaoForm(request.GET or None, edital=request.GET.get('edital'), ano=request.GET.get('ano'))
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        recurso = form.cleaned_data.get('recurso')
        uo = form.cleaned_data.get('uo')
        projeto = form.cleaned_data.get('projeto')
        area_conhecimento = form.cleaned_data.get('area_conhecimento')
        area_tematica = form.cleaned_data.get('area_tematica')
        tema = form.cleaned_data.get('tema')
        projetos = Projeto.objects.filter(aprovado=True, edital=form.cleaned_data.get('edital'))
        recurso = get_object_or_404(Recurso, pk=form.cleaned_data.get('recurso').id)
        if campus_restrito:
            projetos = projetos.filter(uo=campus_restrito)
        if uo:
            projetos = projetos.filter(uo=uo)
        if projeto:
            projetos = projetos.filter(id=projeto.id)
        if area_conhecimento:
            projetos = projetos.filter(area_conhecimento=area_conhecimento)
        if area_tematica:
            projetos = projetos.filter(area_tematica=area_tematica)
        if tema:
            projetos = projetos.filter(tema=tema)
        projetos = projetos.filter(
            id__in=ItemMemoriaCalculo.objects.filter(origem=recurso.origem, despesa=recurso.despesa).only('projeto').values_list('projeto', flat=True)
        )
        valor_total = 0
        for projeto in projetos:
            projeto.valor = (
                ItemMemoriaCalculo.objects.filter(projeto=projeto, origem=recurso.origem, despesa=recurso.despesa)
                .only('qtd', 'valor_unitario')
                .annotate(total=ExpressionWrapper(F('qtd') * F('valor_unitario'), output_field=FloatField()))
                .aggregate(valor=Sum('total'))['valor']
            )
            valor_total += projeto.valor
        if 'xls' in request.GET:
            texto = f'Origem do Recurso: {recurso.origem} / Natureza de Despesa: {recurso.despesa.codigo} ({recurso.despesa.nome})'
            return tasks.relatorio_financeiro_to_xls(projetos, texto, valor_total, recurso)

    return locals()


@permission_required('projetos.pode_interagir_com_projeto')
def filtrar_recursos_por_edital(request):
    data = '[]'
    if request.method == 'GET':
        edital = request.GET.get('edital')
        if edital and edital != 'Selecione um edital':
            registro = Recurso.objects.filter(edital=edital)
            if registro.exists():
                import json

                json_data = json.dumps([{'titulo': reporter.__str__(), 'id': reporter.id} for reporter in registro])
                return HttpResponse(json_data, content_type='application/json')
    return HttpResponse(data, content_type='application/json')


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def adicionar_participante_alunos_em_lote(request, projeto_id):
    title = 'Adicionar Alunos em Lote'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        from edu.models import ComponenteCurricular, CursoCampus, Diario, NivelEnsino, PeriodoLetivoAtual, Professor, ProfessorDiario

        professor = get_object_or_404(Professor, vinculo__user=request.user)

        periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, professor)
        professores_diario = ProfessorDiario.objects.filter(professor__vinculo__user=request.user, ativo=True)
        professores_diario_anual = professores_diario.filter(
            diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, diario__ano_letivo__ano=periodo_letivo_atual.ano
        )

        # excluíndo os diários semestrais em cursos anuais
        if periodo_letivo_atual.periodo == 1:
            professores_diario_anual = professores_diario_anual.exclude(diario__segundo_semestre=True)
        else:
            professores_diario_anual = professores_diario_anual.exclude(
                diario__segundo_semestre=False, diario__componente_curricular__qtd_avaliacoes=2
            )

        professores_diario_semestral = professores_diario.filter(
            diario__turma__curso_campus__periodicidade__in=[CursoCampus.PERIODICIDADE_SEMESTRAL, CursoCampus.PERIODICIDADE_LIVRE],
            diario__ano_letivo__ano=periodo_letivo_atual.ano,
            diario__periodo_letivo=periodo_letivo_atual.periodo,
        )
        registros = professores_diario_anual | professores_diario_semestral
        diarios = Diario.objects.filter(
            turma__curso_campus__modalidade__nivel_ensino__in=[NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO],
            id__in=registros.values_list('diario', flat=True),
        ).filter(Q(componente_curricular__ch_extensao__isnull=False) | Q(componente_curricular__tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO))
        form = AdicionarAlunosEmLoteForm(request.POST or None, meus_diarios=diarios)
        if form.is_valid():
            for aluno in form.cleaned_data.get('alunos'):
                participacao = Participacao()
                participacao.projeto = projeto
                participacao.vinculo = form.cleaned_data.get('vinculo')
                participacao.carga_horaria = form.cleaned_data.get('carga_horaria')
                participacao.ch_extensao = form.cleaned_data.get('ch_extensao')
                descricao_vinculo = 'não bolsista'
                if participacao.vinculo == TipoVinculo.BOLSISTA:
                    participacao.bolsa_concedida = True
                    descricao_vinculo = 'bolsista'
                participacao.pessoa = aluno.pessoa_fisica
                if Vinculo.objects.filter(id_relacionamento=aluno.id, tipo_relacionamento__model='aluno'):
                    participacao.vinculo_pessoa = Vinculo.objects.filter(id_relacionamento=aluno.id, tipo_relacionamento__model='aluno')[0]
                if Participacao.objects.filter(projeto=participacao.projeto, vinculo_pessoa=participacao.vinculo_pessoa).exists():
                    return httprr('.', f'{aluno} já pertence ao projeto.', tag='error')
                participacao.save()
                participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=form.cleaned_data.get('data'))
                Participacao.gerar_anexos_do_participante(participacao)
                if form.cleaned_data.get('integracao_curricular'):
                    participacao.termo_aceito_em = datetime.datetime.now()
                    participacao.atividade_integracao_curricular = True
                    participacao.save()
                    titulo = '[SUAP] Extensão: Inclusão na equipe de projeto de extensão'
                    texto = (
                        '<h1>Extensão</h1>'
                        '<h2>Inclusão na equipe de projeto de extensão</h2>'
                        "<p>Você foi cadastrado(a) como membro {0} da equipe do projeto '{1}'. De acordo com o edital, são deveres dos alunos (bolsistas e não bolsistas):</p>"
                        '<p>a) Dedicar-se às atividades do projeto, cumprindo os horários para cada atividade;</p>'
                        '<p>b) Se bolsista, dedicar a carga horária prevista às atividades do projeto, em horário acordado com o Coordenador e registrar frequência diária no SUAP;</p>'
                        '<p>c) Se não bolsista, definir junto ao coordenador o quantitativo de horas semanais dedicadas às atividades do projeto, não podendo ultrapassar o limite de 20 (vinte) horas semanais;</p>'
                        '<p>d) Não estar matriculado em outra instituição de ensino público;</p>'
                        '<p>e) Se bolsista, comprovar desempenho acadêmico satisfatório comprovado por histórico escolar;</p>'
                        '<p>f) Se bolsista, não possuir vínculo empregatício e/ou ser beneficiário de outro tipo de bolsa do {2} ou de qualquer outra Instituição.</p>'
                        '<p>Para mais informações acesse o projeto <a href="{3}/projetos/projeto/{4}/">{3}/projetos/projeto/{4}/</a></p>'.format(
                            descricao_vinculo,
                            projeto.titulo,
                            Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                            settings.SITE_URL,
                            projeto.id,
                        )
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.vinculo_pessoa])
                elif projeto.edital.exige_termo_aluno():
                    titulo = '[SUAP] Extensão: Termo de Compromisso do Aluno'
                    texto = (
                        '<h1>Extensão</h1>'
                        '<h2>Termo de Compromisso do Aluno</h2>'
                        f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [aluno.get_vinculo()])
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=equipe', 'Alunos cadastrados com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def encerrar_participacoes_em_lote(request, projeto_id):
    title = 'Encerrar participações dos alunos em Lote'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = EncerrarAlunosEmLoteForm(request.POST or None, projeto=projeto)
        if form.is_valid():
            data_escolhida = form.cleaned_data.get('data')
            for participacao in form.cleaned_data.get('participacoes'):
                HistoricoOrientacaoProjeto.objects.filter(orientador=participacao, data_termino__isnull=True).update(data_termino=data_escolhida)
                HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_termino__isnull=True).update(data_termino=data_escolhida)
                for registro in HistoricoOrientacaoProjeto.objects.filter(orientador=participacao):
                    registro_participacao = get_object_or_404(Participacao, pk=registro.orientado.id)
                    registro_participacao.orientador = None
                    registro_participacao.save()
                participacao.ativo = False
                participacao.orientador = None
                participacao.data_inativacao = data_escolhida
                participacao.save()
                participacao.adicionar_registro_historico_equipe(
                    HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_evento=data_escolhida, obs=form.cleaned_data.get('justificativa')
                )
                if projeto.auxiliar and projeto.auxiliar == participacao.vinculo_pessoa:
                    projeto.auxiliar = None
                    projeto.save()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=equipe', 'Participações encerradas com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('projetos.add_visitatecnica')
def get_json_dados_empresa(request):
    dados_concedente = {
        'endereco': {
            'nome': '',
            'nome_contato': '',
            'telefone_contato': '',
            'email_contato': '',
            'cidade_id': '',
            'cidade_nome': '',
            'estado_sigla': '',
            'logradouro': '',
            'numero': '',
            'complemento': '',
            'bairro': '',
            'cep': '',
        }
    }
    cnpj = request.GET.get('cnpj')
    if cnpj:
        empresa = PessoaJuridica.objects.filter(cnpj=cnpj).first()
        if empresa:
            dados_concedente['nome'] = empresa.nome_fantasia or empresa.nome
            if empresa.pessoaendereco_set.exists():
                endereco = empresa.pessoaendereco_set.latest('id')
                dados_concedente['cidade_id'] = endereco.municipio.id
                dados_concedente['cidade_nome'] = endereco.municipio.nome
                dados_concedente['estado_sigla'] = endereco.municipio.uf
                dados_concedente['logradouro'] = endereco.logradouro
                dados_concedente['numero'] = endereco.numero
                dados_concedente['complemento'] = endereco.complemento
                dados_concedente['bairro'] = endereco.bairro
                dados_concedente['cep'] = endereco.cep
        if VisitaTecnica.objects.filter(cnpj=cnpj).exists():
            registro = VisitaTecnica.objects.filter(cnpj=cnpj).last()
            dados_concedente['nome_contato'] = registro.nome_contato
            dados_concedente['telefone_contato'] = registro.telefone_contato
            dados_concedente['email_contato'] = registro.email_contato
            if not empresa:
                dados_concedente['nome'] = registro.instituicao_visitada
                dados_concedente['cidade_id'] = registro.municipio.id
                dados_concedente['cidade_nome'] = registro.municipio.nome
                dados_concedente['estado_sigla'] = registro.municipio.uf
                dados_concedente['logradouro'] = registro.logradouro
                dados_concedente['numero'] = registro.numero
                dados_concedente['complemento'] = registro.complemento
                dados_concedente['bairro'] = registro.bairro
                dados_concedente['cep'] = registro.cep

    return JsonResponse(dados_concedente)


@rtr()
@permission_required('projetos.add_edital')
def clonar_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Clonar Edital: {edital}'
    form = ClonarEditalForm(request.POST or None, request=request, edital=edital)
    if form.is_valid():
        edital_clonado = form.processar()
        return httprr(f'/projetos/edital/{edital_clonado.id}/', 'Edital clonado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.view_visitatecnica')
def visualizar_visita_tecnica(request: HttpRequest, visita_id: int) -> dict:
    visita = get_object_or_404(VisitaTecnica, pk=visita_id)
    campus_restrito = campus_do_coordenador_extensao(request.user)
    if campus_restrito and visita.campus != campus_restrito:
        raise PermissionDenied
    title = f'{visita}'
    return locals()


def projetos_aprovaveis_sem_fomento(request: HttpRequest, edital: Edital) -> QuerySet[Projeto]:
    """Projetos do edital que a tela "Aprovar projetos sem fomento" oferece ao usuário (fora do campus, só para o gerente)."""
    projetos = (
        Projeto.objects.filter(pre_aprovado=True, aprovado=False, edital=edital, autorizada_sem_fomento_em=None)
        .exclude(data_avaliacao=None)
        .order_by('uo', '-pontuacao')
    )
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        projetos = projetos.filter(uo=get_uo(request.user))
    return projetos


@rtr()
@permission_required('projetos.add_edital')
def aprovar_projetos_sem_fomento(request: HttpRequest, edital_id: int) -> dict:
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Aprovar projetos sem fomento: {edital}'
    projetos = projetos_aprovaveis_sem_fomento(request, edital)
    return locals()


@rtr()
@permission_required('projetos.add_edital')
def autorizar_projetos_sem_fomento(request: HttpRequest, edital_id: int) -> HttpResponse | None:
    edital = get_object_or_404(Edital, pk=edital_id)
    registros = request.POST.getlist('registros')
    if registros:
        # ids fora da lista da tela (outro edital, campus ou estado) são ignorados
        for projeto in projetos_aprovaveis_sem_fomento(request, edital).filter(id__in=[item for item in registros if item]):
            projeto.autorizada_sem_fomento = True
            projeto.autorizada_sem_fomento_por = request.user.get_vinculo()
            projeto.autorizada_sem_fomento_em = datetime.datetime.now()
            projeto.save()
            titulo = '[SUAP] Extensão: Autorização de execução de projeto sem fomento'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Autorização de execução de projeto sem fomento</h2>'
                f"<p>O projeto '{projeto.titulo}' poderá ser executado sem fomento. Acesse o SUAP para registrar se deseja executar o projeto.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
        return httprr(f'/projetos/aprovar_projetos_sem_fomento/{edital.id}/', 'Projetos autorizados com sucesso.')


def projetos_autorizados_sem_fomento(vinculo: Vinculo) -> QuerySet[Projeto]:
    """Projetos que aguardam o coordenador ``vinculo`` aceitar ou rejeitar executar sem fomento."""
    return Projeto.objects.filter(
        avaliacao_aceite_sem_fomento_em=None,
        pre_aprovado=True,
        aprovado=False,
        autorizada_sem_fomento=True,
        vinculo_coordenador=vinculo,
    )


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def meus_projetos_autorizados_sem_fomento(request: HttpRequest) -> dict:
    title = 'Projetos autorizados a entrar em execução sem fomento'
    projetos = projetos_autorizados_sem_fomento(request.user.get_vinculo())
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def avaliar_executar_projeto(request: HttpRequest, projeto_id: int, opcao_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, id=projeto_id)
    if projetos_autorizados_sem_fomento(request.user.get_vinculo()).filter(pk=projeto.pk).exists():
        if opcao_id == 1:
            projeto.aceita_sem_fomento = True
            projeto.aprovado = True
            desc = 'aceitou'
        else:
            projeto.aceita_sem_fomento = False
            desc = 'rejeitou'
        projeto.avaliacao_aceite_sem_fomento_por = request.user.get_vinculo()
        projeto.avaliacao_aceite_sem_fomento_em = datetime.datetime.now()
        projeto.save()

        titulo = '[SUAP] Extensão: Execução de projeto sem fomento'
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Execução de projeto sem fomento</h2>'
            f"<p>O coordenador do projeto '{projeto.titulo}' {desc} executar o projeto sem fomento.</p>"
        )
        lista_integrantes = []
        for membro in UsuarioGrupo.objects.filter(group__name='Coordenador de Extensão'):
            if get_uo(membro.user) == projeto.uo:
                lista_integrantes.append(membro.user.get_vinculo())
        if lista_integrantes:
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, lista_integrantes)
        return httprr('/projetos/meus_projetos_autorizados_sem_fomento/', 'Manifestação registrada com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.view_edital')
def lista_mensal_bolsistas(request: HttpRequest) -> dict | HttpResponse:
    title = 'Lista Mensal de Bolsistas'
    campus_restrito = campus_do_coordenador_extensao(request.user)
    form = ListaMensalBolsistaForm(request.GET or None)
    if form.is_valid():
        ano = form.cleaned_data.get('ano')
        mes = form.cleaned_data.get('mes')
        edital = form.cleaned_data.get('edital')
        registros = ProjetoAnexo.objects.filter(
            vinculo_membro_equipe__isnull=False, ano=ano, mes=mes, desembolso__despesa__nome__unaccent__icontains='financeiro a estudantes'
        ).order_by('projeto__edital', 'projeto')
        if edital:
            registros = registros.filter(projeto__edital=edital)
        if campus_restrito:
            registros = registros.filter(projeto__uo=campus_restrito)
        if 'xls' in request.GET and registros.count():
            return tasks.lista_mensal_bolsistas_to_xls(registros, ano, registros[0].get_mes())
    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def visualizar_projetos_avaliador(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Projetos avaliados - {edital.titulo}'
    avaliacoes = Avaliacao.objects.filter(projeto__edital=edital, vinculo=request.user.get_vinculo())
    return locals()


@rtr()
@permission_required('projetos.view_edital')
def adicionar_oferta_projeto_em_lote(request, edital_id):
    title = 'Adicionar Oferta de Projeto'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    form = OfertaProjetoEmLoteForm(request.POST or None, edital=edital)
    if form.is_valid():
        campi = form.cleaned_data.get('campi')
        for campus in campi:
            qs = OfertaProjeto.objects.filter(edital=edital, uo=campus)
            if qs.exists():
                oferta = qs[0]
            else:
                oferta = OfertaProjeto()
            oferta.edital = edital
            oferta.uo = campus
            if form.cleaned_data.get('qtd_aprovados'):
                oferta.qtd_aprovados = form.cleaned_data.get('qtd_aprovados')
            else:
                oferta.qtd_aprovados = 0
            if form.cleaned_data.get('qtd_selecionados'):
                oferta.qtd_selecionados = form.cleaned_data.get('qtd_selecionados')
            else:
                oferta.qtd_selecionados = 0
            oferta.save()
        return httprr(f'/projetos/edital/{edital.id}/?tab=oferta_por_campus', 'Campi adicionados com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.view_comissaoedital')
def ver_membros_comissao(request, comissao_id):
    comissao = get_object_or_404(ComissaoEdital, pk=comissao_id)
    title = f'Membros da {comissao}'
    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def relatorio_alunos_por_projetos(request):
    title = 'Relatório - Projetos executados x Alunos matriculados'
    form = RelatorioAlunoPorProjetoForm(request.POST or None)
    if form.is_valid():
        campi = UnidadeOrganizacional.objects.uo()
        if form.cleaned_data.get('campus'):
            campi = campi.filter(id=form.cleaned_data.get('campus').id)
        lista = []
        ano = form.cleaned_data.get('ano')
        ordenacao = form.cleaned_data.get('ordenacao')
        for campus in campi:
            projetos = Projeto.objects.filter(uo=campus, edital__inicio_inscricoes__year=ano, pre_aprovado=True, aprovado=True).count()
            alunos = (
                Aluno.objects.filter(curso_campus__diretoria__setor__uo=campus, ano_letivo__ano__lte=ano)
                .filter(Q(situacao__ativo=True) | Q(situacao__ativo=False, ano_conclusao__gte=ano))
                .count()
            )
            lista.append({'nome': campus.sigla, 'projetos': projetos, 'alunos': alunos, 'razao': alunos / projetos if projetos > 0 else 0})
        if ordenacao:
            if ordenacao == '1':
                lista = sorted(lista, key=lambda d: d['razao'])
            else:
                lista = sorted(lista, reverse=True, key=lambda d: d['razao'])
    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def classificacao_projetos(request):
    title = 'Editais com classificação disponível'
    hoje = datetime.datetime.now()
    editais = Edital.objects.filter(fim_selecao__lt=hoje).order_by('-divulgacao_selecao')
    form = AnoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            ano = int(form.cleaned_data['ano'])
            editais = editais.filter(inicio_inscricoes__year=ano)
    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def classificacao_projetos_edital(self, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tabela = {}
    resultado = {}
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'
    if edital.eh_fomento_interno():
        if edital.forma_selecao == Edital.GERAL:
            projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('-pontuacao')
            tabela['Geral'] = []
            for projeto in projetos:
                tabela['Geral'].append(projeto)
        else:
            projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('uo__sigla', '-pontuacao')
            campi = projetos.values('uo__sigla', 'uo__nome').distinct()
            for campus in campi:
                chave = str(campus['uo__nome'])
                tabela[chave] = []

            for projeto in projetos:
                chave = f'{projeto.uo.nome}'
                tabela[chave].append(projeto)

        resultado = collections.OrderedDict(sorted(tabela.items()))

    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def editar_ch_extensao(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    pode_editar_ch_extensao = (
        projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura() or projeto.is_gerente_sistemico(request.user)
    )
    if not participacao.ativo and pode_editar_ch_extensao and participacao.is_aluno_extensao():
        title = f'Editar CH total de atividade de extensão - {participacao}'
        form = EditarChExtensaoForm(request.POST or None, instance=participacao)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=equipe', 'Carga horária editada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def autorizar_fomento(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    mesmo_campus = projeto.uo == get_uo(usuario_logado)
    is_pre_avaliador = request.user.groups.filter(name='Coordenador de Extensão').exists() and mesmo_campus
    is_gerente_sistemico = projeto.is_gerente_sistemico(usuario_logado)
    if projeto.autorizada_sem_fomento and not projeto.fomento_autorizado_em and (is_gerente_sistemico or is_pre_avaliador):
        projeto.fomento_autorizado_em = datetime.datetime.now()
        projeto.fomento_autorizado_por = usuario_logado.get_vinculo()
        projeto.save()
        return httprr(f'/projetos/projeto/{projeto.id}/', 'Fomento autorizado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def notificar_servidores_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if edital.pode_notificar_servidores():
        return tasks.notificar_servidores_edital(edital)
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def avaliar_alteracao_datas(request, alteracao_id, opcao):
    registro = get_object_or_404(HistoricoAlteracaoPeriodoProjeto, pk=alteracao_id)
    projeto = registro.projeto
    mesmo_campus = projeto.uo == get_uo(request.user) or request.user.has_perm('projetos.view_historicoalteracaoperiodoprojeto')
    if mesmo_campus and registro.aceito is None:
        title = 'Avaliar solicitação de alteração das datas do projeto'
        if opcao == 1:
            registro.aceito = True
            registro.validado_em = datetime.datetime.now()
            registro.validado_por = request.user.get_vinculo()
            registro.save()
            projeto.inicio_execucao = registro.novo_inicio_execucao
            projeto.fim_execucao = registro.novo_fim_execucao
            projeto.save()
            return httprr(f'/projetos/ver_alteracoes_data/{projeto.id}/', 'Alteração deferida com sucesso.')
        elif opcao == 2:
            form = IndefereAlteracaoDataForm(request.POST or None)
            if form.is_valid():
                registro.aceito = False
                registro.justificativa_validacao = form.cleaned_data.get('justificativa_validacao')
                registro.validado_em = datetime.datetime.now()
                registro.validado_por = request.user.get_vinculo()
                registro.save()
                return httprr(f'/projetos/ver_alteracoes_data/{projeto.id}/', 'Alteração indeferida com sucesso.')
            return locals()
        else:
            raise PermissionDenied

    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def relatorio_pareceres_emitidos(request):
    title = 'Relatório de Pareceres Emitidos'

    form = RelatorioPareceresEmitidosForm(request.GET or None)
    if form.is_valid():
        projetos = Projeto.objects.filter(id__in=Avaliacao.objects.values_list('projeto', flat=True)).order_by('uo', 'edital')
        edital = form.cleaned_data.get('edital')
        uo = form.cleaned_data.get('uo')
        ano_inicial = form.cleaned_data.get('ano_inicial')
        ano_final = form.cleaned_data.get('ano_final')
        if uo:
            projetos = projetos.filter(uo=uo)
        if edital:
            projetos = projetos.filter(edital=edital)
        if ano_inicial:
            projetos = projetos.filter(edital__inicio_inscricoes__year__gte=ano_inicial)
        if ano_final:
            projetos = projetos.filter(edital__inicio_inscricoes__year__lte=ano_final)
        if projetos.exists():
            return tasks.relatorio_pareceres_emitidos_to_xls(projetos)

    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def executar_rotina_classificacao_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if edital.is_periodo_selecao_e_pre_divulgacao():
        return tasks.executa_rotina_classificacao_projetos_edital(edital)
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def registros_bolsistas(request):
    title = 'Registros de Bolsistas'
    if 'ae' in settings.INSTALLED_APPS:
        from ae.models import ParticipacaoBolsa

        form = RegistrosBolsistasForm(request.GET or None)
        if form.is_valid():
            hoje = datetime.date.today()
            campus = form.cleaned_data.get('campus')
            categoria = form.cleaned_data.get('categoria')
            query = form.cleaned_data.get('query')
            participantes = ParticipacaoBolsa.abertas.all()
            futuros_participantes = ParticipacaoBolsa.futuras.all()

            if categoria:
                participantes = participantes.filter(categoria=categoria)
                futuros_participantes = futuros_participantes.filter(categoria=categoria)
            if campus:
                participantes = participantes.filter(aluno__curso_campus__diretoria__setor__uo=campus)
                futuros_participantes = futuros_participantes.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            if query:
                participantes = participantes.filter(Q(aluno__matricula__icontains=query) | Q(aluno__pessoa_fisica__nome__icontains=query))
                futuros_participantes = futuros_participantes.filter(
                    Q(aluno__matricula__icontains=query) | Q(aluno__pessoa_fisica__nome__icontains=query)
                )
    return locals()


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def editar_registro_bolsista(request, registro_id):
    if 'ae' in settings.INSTALLED_APPS:
        from ae.forms import ParticipacaoBolsaModelForm
        from ae.models import CategoriaBolsa, ParticipacaoBolsa

        registro = get_object_or_404(ParticipacaoBolsa, pk=registro_id)
        if registro.categoria.tipo_bolsa == CategoriaBolsa.TIPO_EXTENSAO and registro.aluno_participante_projeto:
            title = f'Editar Registro - {registro.aluno.__str__()} - Projeto: {registro.aluno_participante_projeto.projeto.titulo}'
            form = ParticipacaoBolsaModelForm(request.POST or None, instance=registro, request=request, eh_extensao=True)
            if form.is_valid():
                form.save()
                return httprr('..', 'Registro editado com sucesso.')
            return locals()
        else:
            raise PermissionDenied
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def excluir_registro_bolsista(request, registro_id):
    if 'ae' in settings.INSTALLED_APPS:
        from ae.models import CategoriaBolsa, ParticipacaoBolsa

        registro = get_object_or_404(ParticipacaoBolsa, pk=registro_id)
        if registro.categoria.tipo_bolsa == CategoriaBolsa.TIPO_EXTENSAO and registro.aluno_participante_projeto:
            registro.delete()
            return httprr('..', 'Registro excluído com sucesso.')
        else:
            raise PermissionDenied
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def registrar_ocorrencia(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    is_pre_avaliador = usuario_logado.groups.filter(name='Coordenador de Extensão').exists() and projeto.uo == get_uo(usuario_logado)
    if is_pre_avaliador or usuario_logado.has_perm('projetos.pode_gerenciar_edital'):
        title = f'Registrar Ocorrência - Projeto: {projeto.titulo}'
        form = RegistrarOcorrenciaForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            o.cadastrada_por = usuario_logado.get_vinculo()
            o.save()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=ocorrencias', 'Ocorrência registrada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def editar_ocorrencia(request, ocorrencia_id):
    registro = get_object_or_404(OcorrenciaProjeto, pk=ocorrencia_id)
    projeto = registro.projeto
    if registro.cadastrada_por == request.user.get_vinculo():
        title = f'Editar Ocorrência - Projeto: {projeto.titulo}'
        form = RegistrarOcorrenciaForm(request.POST or None, request.FILES or None, instance=registro)
        if form.is_valid():
            form.save()
            return httprr(f'/projetos/projeto/{projeto.id}/?tab=ocorrencias', 'Ocorrência editada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_avaliar_cancelamento_projeto')
def excluir_ocorrencia(request, ocorrencia_id):
    registro = get_object_or_404(OcorrenciaProjeto, pk=ocorrencia_id)
    projeto = registro.projeto
    if registro.cadastrada_por == request.user.get_vinculo():
        registro.delete()
        return httprr(f'/projetos/projeto/{projeto.id}/?tab=ocorrencias', 'Ocorrência excluída com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def avaliar_historico_custeio(request, solicitacao_id):
    registro = get_object_or_404(HistoricoInteresseCusteioProjeto, pk=solicitacao_id)
    projeto = registro.projeto
    if not registro.avaliado_em:
        title = 'Avaliar Solicitação - Interesse por Custeio'
        form = AvaliarInteresseCusteioForm(request.POST or None, instance=registro)
        if form.is_valid():
            o = form.save(False)
            o.avaliado_em = datetime.datetime.now()
            o.avaliado_por = request.user.get_vinculo()
            o.save()
            situacao = 'indeferida'
            if form.cleaned_data.get('aceito') == 'True':
                projeto.tem_interesse_cartao_pesquisador = registro.tem_interesse
                projeto.save()
                situacao = 'deferida'

            titulo = '[SUAP] Extensão: Alteração no Interesse por Custeio'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Alteração no Interesse por Custeio</h2>'
                f"<p>Sua solicitação para alteração no interesse por custeio do projeto '{projeto.titulo}' foi {situacao}. Justificativa: {form.cleaned_data.get('justificativa_avaliacao')}.</p><p>Acesse o SUAP para mais detalhes."
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
            return httprr('..', 'Solicitação avaliada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def ver_alteracoes_interesse_custeio(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_imprimir(request.user):
        raise PermissionDenied
    title = 'Alterações no Interesse por Custeio'
    registros = HistoricoInteresseCusteioProjeto.objects.filter(projeto=projeto)

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def adicionar_oferta_por_grupo(request, edital_id):
    title = 'Adicionar Oferta por Grupo'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    form = OfertaProjetoGrupoForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.edital = edital
        o.save()
        return httprr('..', 'Oferta adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.view_edital')
def editar_oferta_projeto_por_grupo(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    title = 'Editar Plano de Oferta por Grupo'
    oferta = get_object_or_404(OfertaProjetoPorGrupo, pk=oferta_projeto_id, edital=edital)
    form = OfertaProjetoGrupoForm(request.POST or None, instance=oferta)
    if form.is_valid():
        form.save()
        return httprr('..', 'Oferta editada com sucesso.')

    return locals()


@rtr()
@permission_required('projetos.view_edital')
def remover_oferta_projeto_por_grupo(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    oferta = get_object_or_404(OfertaProjetoPorGrupo, pk=oferta_projeto_id, edital=edital)
    oferta.delete()
    return httprr(f'/projetos/edital/{edital.id}/?tab=oferta_por_grupo', 'Oferta removida com sucesso.')


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def reprovar_manualmente(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.pode_reprovar_manualmente(request.user):
        title = f'Reprovar projeto manualmente - {projeto.titulo}'
        form = ReprovarManualmenteForm(request.POST or None, instance=projeto)
        if form.is_valid():
            o = form.save(False)
            o.reprovacao_manual_em = datetime.datetime.now()
            o.reprovacao_manual_por = request.user.get_vinculo()
            o.save()
            projeto.aprovado = False
            projeto.save()
            return httprr(f'/projetos/executar_rotina_classificacao_edital/{projeto.edital.id}/', 'Reprovação registrada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def reverter_reprovacao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.pode_reverter_reprovacao(request.user):
        projeto.justificativa_reprovacao_manual = None
        projeto.reprovacao_manual_em = None
        projeto.reprovacao_manual_por = None
        projeto.save()
        return httprr(f'/projetos/executar_rotina_classificacao_edital/{projeto.edital.id}/', 'Reprovação registrada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def meus_recursos(request):
    title = 'Projetos em período de interposição de recursos'
    editais = Edital.objects.all().em_recurso()
    vinculo = request.user.get_vinculo()
    ids_permitidos = []
    projetos = Projeto.objects.filter(vinculo_coordenador_id=vinculo.id, edital__in=editais.values_list('id', flat=True))
    for projeto in projetos:
        if projeto.pode_enviar_recurso():
            ids_permitidos.append(projeto.id)
    projetos = projetos.filter(id__in=ids_permitidos).select_related('edital').order_by('titulo', 'edital__titulo')
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def interpor_recurso(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if not projeto.pode_enviar_recurso():
        raise PermissionDenied
    title = f'Interpor Recurso - {projeto.titulo} - {projeto.edital.titulo}'
    itens = ItemAvaliacao.objects.filter(avaliacao__projeto=projeto).order_by('criterio_avaliacao')
    return locals()


@rtr()
@permission_required('projetos.pode_interagir_com_projeto')
def itens_selecionados_para_recursos(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if not projeto.pode_enviar_recurso():
        raise PermissionDenied
    title = f'Interpor Recurso - {projeto.titulo} - {projeto.edital.titulo}'
    ids_avaliacoes = request.GET.getlist('registros')
    # id não numérico estourava ValueError no filter (500, #17553)
    if not all(i.isdigit() for i in ids_avaliacoes):
        raise PermissionDenied
    if ItemAvaliacao.objects.filter(pk__in=ids_avaliacoes, avaliacao__projeto=projeto).count() != len(set(ids_avaliacoes)):
        raise PermissionDenied
    if request.POST:
        form = InterporRecursoExtensaoForm(request.POST or None, ids_avaliacoes=ids_avaliacoes)
        if form.is_valid():
            for item_id in ids_avaliacoes:
                registro = ItemAvaliacao.objects.get(id=item_id)
                tem_permissao(request, registro.avaliacao.projeto, pode_auxiliar=True)
                registro.texto_recurso = form.cleaned_data.get(f'{item_id}')
                registro.recurso_em = datetime.datetime.now()
                registro.recurso_por = request.user.get_vinculo()
                registro.save()
                titulo = '[SUAP] Extensão: Recurso Interposto pendente de avaliação'
                texto = (
                    '<h1>Extensão</h1>'
                    '<h2>Recurso Interposto pendente de avaliação</h2>'
                    "<p>O(a) coordenador(a) do projeto '{}', avaliado por você, interpôs recurso. </p>"
                    '<p>Período para avaliação dos recursos interpostos: {} - {}</p>'
                    'Acesse o SUAP para mais detalhes.</p>'.format(
                        projeto.titulo,
                        projeto.edital.data_recurso.strftime('%d/%m/%Y %H:%M'),
                        projeto.edital.divulgacao_selecao.strftime('%d/%m/%Y %H:%M'),
                    )
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [registro.avaliacao.vinculo])

            return httprr(f'/projetos/projeto/{projeto.id}', 'Recurso encaminhado para análise.')
    else:
        form = InterporRecursoExtensaoForm(request.POST or None, ids_avaliacoes=ids_avaliacoes)
    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def avaliar_recursos(request):
    title = 'Lista de recursos interpostos contra as notas'
    editais = Edital.objects.all()
    vinculo_avaliador = request.user.get_vinculo()
    queryset = ItemAvaliacao.objects.filter(avaliacao__projeto__edital__in=editais.values_list('id', flat=True)).exclude(texto_recurso=None)
    eh_sistemico = request.user.has_perm('projetos.pode_gerenciar_edital')
    form = AvaliarRecursosExtensaoForm(request.POST or None, eh_sistemico=eh_sistemico)
    recursos = (
        queryset.filter(avaliacao__vinculo_id=vinculo_avaliador.id)
        .select_related('avaliacao', 'avaliacao__projeto', 'avaliacao__projeto__edital')
        .order_by('avaliacao__projeto__titulo', 'avaliacao__projeto__edital__titulo')
    )
    if form.is_valid():
        if form.cleaned_data.get('uo'):
            queryset = queryset.filter(avaliacao__projeto__uo=form.cleaned_data.get('uo'))
        if form.cleaned_data.get('edital'):
            queryset = queryset.filter(avaliacao__projeto__edital=form.cleaned_data.get('edital'))
        if form.cleaned_data.get('situacao') and form.cleaned_data.get('situacao') == 'Pendentes de avaliação':
            queryset = queryset.filter(recurso_avaliado_em=None)
        if form.cleaned_data.get('avaliador'):
            queryset = queryset.filter(
                Q(avaliacao__vinculo__pessoa__nome__icontains=form.cleaned_data.get('avaliador'))
                | Q(avaliacao__vinculo__in=Servidor.objects.filter(matricula=form.cleaned_data.get('avaliador')).values_list('vinculos', flat=True))
            )

        if form.cleaned_data.get('ver_todos'):
            recursos = queryset.select_related('avaliacao', 'avaliacao__projeto', 'avaliacao__projeto__edital').order_by(
                'avaliacao__projeto__titulo', 'avaliacao__projeto__edital__titulo'
            )
        else:
            recursos = (
                queryset.filter(avaliacao__vinculo_id=vinculo_avaliador.id)
                .select_related('avaliacao', 'avaliacao__projeto', 'avaliacao__projeto__edital')
                .order_by('avaliacao__projeto__titulo', 'avaliacao__projeto__edital__titulo')
            )

    return locals()


@rtr()
@permission_required('projetos.pode_se_tornar_avaliador')
def avaliar_recurso(request, itemavaliacao_id):
    item = get_object_or_404(ItemAvaliacao, pk=itemavaliacao_id)
    projeto = item.avaliacao.projeto
    vinculo_avaliador = request.user.get_vinculo()
    editais = Edital.objects.all().em_avaliacao_recursos()
    if (
        item.texto_recurso
        and (request.user.has_perm('projetos.pode_gerenciar_edital') or item.avaliacao.vinculo == vinculo_avaliador)
        and projeto.edital.id in editais.values_list('id', flat=True)
    ):
        title = 'Avaliar Recurso'
        form = AvaliarRecursoExtensaoForm(request.POST or None, instance=item)
        if form.is_valid():
            with transaction.atomic():
                o = form.save(False)
                o.recurso_avaliado_em = datetime.datetime.now()
                o.recurso_avaliado_por = vinculo_avaliador
                if form.cleaned_data.get('recurso_aceito'):
                    if not o.pontuacao_original:
                        o.pontuacao_original = o.pontuacao
                    o.pontuacao = form.cleaned_data.get('nova_pontuacao')
                o.save()
                item.avaliacao.save()

            return httprr('/projetos/avaliar_recursos/', 'Recurso avaliado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.view_edital')
def remover_arquivo_retificacao(request, retificacao_id):
    arquivo = get_object_or_404(EditalArquivo, pk=retificacao_id)
    edital = arquivo.edital
    tem_permissao_acesso_edital(request, edital)
    arquivo.delete()

    return httprr(f'/projetos/edital/{edital.id}/', 'Retificação removida com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def adicionar_criterio_pre_selecao(request, edital_id):
    title = 'Adicionar Critério para Pré-seleção'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    form = CriterioPreSelecaoForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.edital = edital
        o.save()
        return httprr('..', 'Critério adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.view_edital')
def remover_criterio_pre_selecao(request, criterio_id):
    criterio = get_object_or_404(CriterioPreSelecao, pk=criterio_id)
    edital = criterio.edital
    tem_permissao_acesso_edital(request, edital)
    criterio.delete()
    return httprr(f'/projetos/edital/{edital.id:d}/?tab=criterios_pre_selecao', 'Critério removido com sucesso.')


@rtr()
@permission_required('projetos.view_edital')
def editar_criterio_pre_selecao(request, criterio_id):
    title = 'Editar critério para pré-seleção'
    criterio = get_object_or_404(CriterioPreSelecao, pk=criterio_id)
    edital = criterio.edital
    tem_permissao_acesso_edital(request, edital)
    form = CriterioPreSelecaoForm(request.POST or None, request.FILES or None, instance=criterio)
    if form.is_valid():
        o = form.save(False)
        o.save()
        return httprr('..', 'Critério editado com sucesso.')
    return locals()


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def ficha_pre_selecao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.edital.is_periodo_pre_selecao():
        raise PermissionDenied
    vinculo_logado = request.user.get_vinculo()
    if (
        request.user.has_group_cached('Gerente Sistêmico de Extensão')
        or projeto.vinculo_autor_pre_avaliacao == vinculo_logado
        or (request.user.has_group_cached('Coordenador de Extensão') and projeto.uo == get_uo(request.user))
    ):
        title = f'Ficha da pré-seleção - {projeto.titulo}'
        avaliacao = projeto.preselecao_set.first()
        itens = avaliacao.itempreselecao_set.all() if avaliacao else []
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.add_edital')
def autorizar_sem_fomento(request: HttpRequest, projeto_id: int) -> HttpResponse:
    """Autoriza execução de projeto sem fomento e notifica o coordenador.

    Registra a autorização e o responsável, limpa avaliações de aceite
    anteriores, e envia notificação ao coordenador do projeto.

    Args:
        request: objeto HttpRequest da view.
        projeto_id: ID do projeto a ser autorizado.

    Returns:
        HttpResponseRedirect para a página de detalhes do projeto.
    """
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    # mesmas condições do botão "Autorizar execução sem fomento" (projeto.html)
    prazo_execucao_expirou = datetime.date.today() > projeto.fim_execucao
    if projeto.aceita_sem_fomento is False and projeto.is_gerente_sistemico(request.user) and not prazo_execucao_expirou:
        projeto.autorizada_sem_fomento = True
        projeto.autorizada_sem_fomento_por = request.user.get_vinculo()
        projeto.autorizada_sem_fomento_em = datetime.datetime.now()
        projeto.aceita_sem_fomento = None
        projeto.avaliacao_aceite_sem_fomento_por = None
        projeto.avaliacao_aceite_sem_fomento_em = None
        projeto.save()
        titulo = '[SUAP] Extensão: Autorização de execução de projeto sem fomento'
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Autorização de execução de projeto sem fomento</h2>'
            f"<p>O projeto '{projeto.titulo}' poderá ser executado sem fomento. Acesse o SUAP para registrar se deseja executar o projeto.</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
        return httprr(f'/projetos/projeto/{projeto_id}/', 'Projeto autorizado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def reenviar_convite_avaliador(request: HttpRequest, avaliador_id: int) -> HttpResponse:
    url = request.META.get('HTTP_REFERER', '.')
    novo_avaliador = get_object_or_404(AvaliadorIndicado, pk=avaliador_id)
    projeto = novo_avaliador.projeto
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        if not projeto.uo == get_uo(request.user) or not projeto.edital.campus_especifico:
            raise PermissionDenied
    if projeto.edital.prazo_aceite_indicacao:
        prazo_aceite = datetime.datetime.now() + relativedelta(days=projeto.edital.prazo_aceite_indicacao)
        novo_avaliador.prazo_para_aceite = prazo_aceite
        if projeto.edital.prazo_avaliacao:
            prazo_avaliacao = prazo_aceite + relativedelta(days=projeto.edital.prazo_avaliacao)
            novo_avaliador.prazo_para_avaliacao = prazo_avaliacao
    novo_avaliador.rejeitado_automaticamente = False
    novo_avaliador.rejeitado = False
    novo_avaliador.rejeitado_em = None
    novo_avaliador.convidado_em = datetime.datetime.now()
    novo_avaliador.save()

    fim_selecao = projeto.edital.fim_selecao
    if projeto.edital.eh_edital_continuo():
        fim_selecao = projeto.edital.fim_inscricoes
    titulo = '[SUAP] Avaliação de Projeto de Extensão'
    if projeto.edital.prazo_aceite_indicacao:
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Avaliação de Projeto</h2>'
            f'<p>Foi solicitada sua avaliação do projeto de extensão: {projeto.titulo}.</p>'
            f'<p>Prazo para registrar que aceita a indicação: {format_(novo_avaliador.prazo_para_aceite)}.</p>'
            f'<p>Prazo para realizar a avaliação: {format_(novo_avaliador.prazo_para_avaliacao)}.</p>'
            '<p>Caso os prazos não sejam cumpridos, a indicação será cancelada automaticamente.</p>'
            f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
            f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(fim_selecao)}</strong>.</p>'
        )
    else:
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Avaliação de Projeto</h2>'
            f'<p>Foi solicitada sua avaliação do projeto de extensão: {projeto.titulo}.</p>'
            f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
            f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(fim_selecao)}</strong>.</p>'
        )
    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [novo_avaliador.vinculo])
    return httprr(url, 'Convite reenviado com sucesso.')


@rtr()
@permission_required('projetos.pode_pre_avaliar_projeto')
def remover_indicacoes_rejeitadas(request: HttpRequest, edital_id: int) -> HttpResponse:
    url = request.META.get('HTTP_REFERER', '.')
    edital = get_object_or_404(Edital, pk=edital_id)
    avaliacoes = AvaliadorIndicado.objects.filter(rejeitado=True, projeto__edital=edital)
    if not request.user.has_perm('projetos.pode_gerenciar_edital'):
        campus_logado_user = get_uo(request.user)
        if not edital.campus_especifico or not OfertaProjeto.objects.filter(edital=edital, uo=campus_logado_user).exists():
            raise PermissionDenied
        avaliacoes = avaliacoes.filter(projeto__uo=campus_logado_user)
    grupo = Group.objects.get(name='Avaliador de Projetos de Extensão')
    for avaliador in avaliacoes:
        vinculo = avaliador.vinculo
        avaliador.delete()
        if vinculo and vinculo.user and not AvaliadorIndicado.objects.filter(vinculo=vinculo).exists():
            vinculo.user.groups.remove(grupo)
    return httprr(url, 'Indicações removidas com sucesso.')


@rtr()
@permission_required('projetos.pode_avaliar_projeto')
def aceitar_indicacao(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    # Mesmo estado em que projetos_pre_aprovados.html oferece "Aceitar Indicação".
    if projeto.pendente_avaliacao() and projeto.pode_aceitar_indicacao():
        AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=request.user.get_vinculo()).update(aceito_em=datetime.datetime.now())
        return httprr(f'/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/', 'Indicação aceita com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_avaliar_projeto')
def rejeitar_indicacao(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    # Mesmo estado em que projetos_pre_aprovados.html oferece "Rejeitar Indicação": quem já avaliou vê "Editar Avaliação".
    if projeto.pendente_avaliacao():
        AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=request.user.get_vinculo()).update(
            rejeitado=True, rejeitado_em=datetime.datetime.now()
        )
        return httprr(f'/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/', 'Indicação rejeitada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('projetos.pode_gerenciar_edital')
def finalizar_projeto_forma_sistemica(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    if projeto.get_status() == Projeto.STATUS_EM_EXECUCAO:
        execucao_de_testes = running_tests()
        title = f'Finalizar projeto de forma sistêmica - {projeto.titulo}'
        form = FinalizacaoSistemicaForm(request.POST or None, instance=projeto)
        if not execucao_de_testes:
            documentos = inlineformset_factory(
                Projeto,
                ArquivoFinalizacaoProjeto,
                fields=['descricao', 'arquivo'],
                can_delete=False,
                extra=0,
                form=ArquivoFinalizacaoProjetoForm,
                formset=TermoParceriaAdesaoInlineFormSet,
                min_num=0,
            )
            formset = documentos(request.POST or None, request.FILES or None)
        if request.method == 'POST':
            if execucao_de_testes:
                formset_valido = True
            else:
                formset_valido = formset.is_valid()
            if form.is_valid() and formset_valido:
                with transaction.atomic():
                    o = form.save(False)
                    o.finalizacao_sistemica_em = datetime.datetime.now()
                    o.finalizacao_sistemica_por = request.user.get_relacionamento()
                    if not o.data_finalizacao_conclusao:
                        o.data_finalizacao_conclusao = datetime.datetime.now()
                    o.concluido = True
                    o.save()
                    if not execucao_de_testes:
                        formset.instance = form.instance
                        formset.save()
                    registro_conclusao, _ = RegistroConclusaoProjeto.objects.get_or_create(projeto=projeto)
                    registro_conclusao.dt_avaliacao = datetime.date.today()
                    registro_conclusao.avaliador = request.user.get_relacionamento()
                    registro_conclusao.obs_avaliador = form.cleaned_data.get('motivo_finalizacao_sistemica')
                    registro_conclusao.save()
                    historico = ProjetoHistoricoDeEnvio()
                    historico.projeto = projeto
                    historico.data_operacao = datetime.datetime.now()
                    historico.situacao = ProjetoHistoricoDeEnvio.FINALIZADO
                    historico.operador = request.user.get_relacionamento()
                    historico.parecer_devolucao = form.cleaned_data.get('motivo_finalizacao_sistemica')
                    historico.save()
                    movimentacoes_sem_data_saida = HistoricoEquipe.objects.filter(ativo=True, projeto=projeto, data_movimentacao_saida__isnull=True)
                    if movimentacoes_sem_data_saida:
                        for movimentacao in movimentacoes_sem_data_saida:
                            movimentacao.data_movimentacao_saida = datetime.datetime.today()
                            movimentacao.save()
                    if projeto.eh_fomento_interno():
                        projeto.concluir()
                    titulo = '[SUAP] Extensão: Finalização de Projeto'
                    texto = (
                        '<h1>Extensão</h1>'
                        '<h2>Finalização de Projeto</h2>'
                        f"<p>O Projeto '{projeto.titulo}' foi finalizado de forma sistêmica.</p>"
                        f"<p class='more-info'>Para mais informações, acesse o projeto: <a href='{settings.SITE_URL}/projetos/projeto/{projeto.id}/'>{projeto.titulo}</a></p>"
                    )

                    for membro in Participacao.objects.filter(projeto=projeto, ativo=True, vinculo_pessoa__isnull=False):
                        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [membro.vinculo_pessoa])
                        membro.gerar_atividade_curricular_extensao()
                    return httprr(f'/projetos/projeto/{projeto.id}/', 'Projeto finalizado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


def projetos_para_indicar_em_lote(vinculo: Vinculo, editais: QuerySet[Edital]) -> QuerySet[Projeto]:
    """Projetos pré-selecionados dos ``editais`` que o ``vinculo`` pode avaliar: fora a equipe, o próprio campus (edital não específico) e os temas que ele não cobre."""
    projetos = Projeto.objects.filter(edital__in=editais).filter(
        Q(edital__tipo_edital=Edital.EXTENSAO, pre_aprovado=True) | Q(pre_aprovado=True, aprovado=False)
    )
    projetos = projetos.exclude(id__in=Participacao.objects.filter(vinculo_pessoa=vinculo).values_list('projeto', flat=True))
    projetos = projetos.exclude(edital__campus_especifico=False, uo=get_uo(vinculo.user))
    return projetos.exclude(
        edital__in=editais.filter(temas__isnull=False),
        area_tematica__in=AreaTematica.objects.exclude(vinculo=vinculo).values_list('id', flat=True),
    )


def projetos_escolhidos_em_lote(request: HttpRequest, vinculo: Vinculo) -> list[Projeto]:
    """Os projetos de ``registros`` que a tela de indicação em lote ofereceria ao ``vinculo``; os demais ids são ignorados.

    Os editais escolhidos na tela não voltam no POST: vale o conjunto que o form oferece ao usuário
    (permissão, campus e período de seleção). A comissão do edital é a regra de ``IndicarAvaliadorEmLoteForm.clean``.
    """
    ids_escolhidos = [int(item) for item in request.POST.getlist('registros') if item.isdecimal()]
    editais = IndicarAvaliadorEmLoteForm(request=request).fields['editais'].queryset
    projetos = projetos_para_indicar_em_lote(vinculo, editais).filter(id__in=ids_escolhidos)
    return [projeto for projeto in projetos if membros_comissao_do_projeto(projeto).filter(id=vinculo.id).exists()]


@rtr()
@permission_required('projetos.change_projeto')
def indicar_avaliador_em_lote(request: HttpRequest) -> dict:
    title = 'Indicar avaliador em lote'
    form = IndicarAvaliadorEmLoteForm(request.POST or None, request=request)
    if form.is_valid():
        vinculo_avaliador = form.cleaned_data.get('vinculo')
        projetos = projetos_para_indicar_em_lote(vinculo_avaliador, form.cleaned_data.get('editais')).order_by('titulo')
        if form.cleaned_data.get('area_tematica'):
            projetos = projetos.filter(area_tematica=form.cleaned_data.get('area_tematica'))

    return locals()


@rtr()
@permission_required('projetos.change_projeto')
def salvar_indicacoes_em_lote(request: HttpRequest, vinculo_id: int) -> HttpResponse:
    # Só o avaliador e os projetos que a tela de lote oferece; o vínculo fora do campo "Avaliador" é 404.
    vinculo = get_object_or_404(IndicarAvaliadorEmLoteForm(request=request).fields['vinculo'].queryset, pk=vinculo_id)

    grupo = Group.objects.get(name='Avaliador de Projetos de Extensão')
    for projeto in projetos_escolhidos_em_lote(request, vinculo):
        if not request.user.has_perm('projetos.pode_gerenciar_edital'):
            if not projeto.uo == get_uo(request.user) or not projeto.edital.campus_especifico:
                raise PermissionDenied
        avaliadores_cadastrados = AvaliadorIndicado.objects.filter(projeto=projeto)
        if vinculo.user and vinculo.id not in avaliadores_cadastrados.values_list('vinculo', flat=True):
            novo_avaliador = AvaliadorIndicado()
            novo_avaliador.vinculo = vinculo
            novo_avaliador.projeto = projeto
            if projeto.edital.prazo_aceite_indicacao:
                prazo_aceite = datetime.datetime.now() + relativedelta(days=projeto.edital.prazo_aceite_indicacao)
                novo_avaliador.prazo_para_aceite = prazo_aceite
                if projeto.edital.prazo_avaliacao:
                    prazo_avaliacao = prazo_aceite + relativedelta(days=projeto.edital.prazo_avaliacao)
                    novo_avaliador.prazo_para_avaliacao = prazo_avaliacao
            novo_avaliador.save()
            novo_avaliador.vinculo.user.groups.add(grupo)

            titulo = '[SUAP] Avaliação de Projeto de Extensão'
            if projeto.edital.prazo_aceite_indicacao:
                texto = (
                    '<h1>Extensão</h1>'
                    '<h2>Avaliação de Projeto</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de extensão: {novo_avaliador.projeto.titulo}.</p>'
                    f'<p>Prazo para registrar que aceita a indicação: {format_(novo_avaliador.prazo_para_aceite)}.</p>'
                    f'<p>Prazo para realizar a avaliação: {format_(novo_avaliador.prazo_para_avaliacao)}.</p>'
                    '<p>Caso os prazos não sejam cumpridos, a indicação será cancelada automaticamente.</p>'
                    f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(projeto.edital.fim_selecao)}</strong>.</p>'
                )
            else:
                texto = (
                    '<h1>Extensão</h1>'
                    '<h2>Avaliação de Projeto</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de extensão: {novo_avaliador.projeto.titulo}.</p>'
                    f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/">{settings.SITE_URL}/projetos/projetos_pre_aprovados/{projeto.edital.id}/{projeto.uo.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital:  <strong>{format_(projeto.edital.inicio_selecao)} - {format_(projeto.edital.fim_selecao)}</strong>.</p>'
                )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo])
    return httprr('/projetos/indicar_avaliador_em_lote/', 'Avaliador cadastrado com sucesso.')


@rtr()
@permission_required('projetos.view_comunicador')
def nova_mensagem(request):
    title = 'Nova mensagem'
    form = NovaMensagemForm(request.POST or None)
    if form.is_valid():
        return tasks.enviar_msg_comunicador_extensao(
            form.cleaned_data.get('titulo'), form.cleaned_data.get('conteudo'), form.cleaned_data.get('vinculos'), request
        )
    return locals()


@rtr()
@permission_required('projetos.view_comunicador')
def ver_detalhes_mensagem(request, mensagem_id):
    msg = get_object_or_404(Comunicador, pk=mensagem_id)
    title = f'Mensagem enviada - {msg.titulo}'
    return locals()
