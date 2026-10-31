import collections
import datetime
from collections.abc import Iterable
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, OuterRef, Q, QuerySet, Subquery, Sum
from django.db.models.functions.datetime import ExtractYear
from django.db.utils import IntegrityError
from django.dispatch import receiver
from django.forms import inlineformset_factory
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.utils.safestring import mark_safe
from django.utils.text import get_valid_filename

from cnpq.models import CurriculoVittaeLattes, GrupoPesquisa
from cnpq.views import atualizar_grupos_pesquisa
from comum.forms import AdicionarUsuarioGrupoForm, ExcluirRegistroForm
from comum.models import Arquivo, Comentario, Configuracao, PrestadorServico, Raca, TrocarSenha, User, UsuarioGrupo, Vinculo
from comum.utils import get_uo
from djtools import documentos, layout
from djtools.html.calendarios import CalendarioPlus
from djtools.html.graficos import ColumnChart, GroupedColumnChart, PieChart
from djtools.templatetags.filters import format_
from djtools.utils import (
    Relatorio,
    anonimizar_cpf,
    documento,
    group_required,
    httprr,
    permission_required,
    render_to_string,
    rtr,
    send_mail,
    send_notification,
    sync_ldap_user,
)
from edu.models import Aluno, Modalidade
from pesquisa import tasks
from pesquisa.forms import (
    AceitarDoacaoForm,
    AceiteEditoraForm,
    AceiteTermoForm,
    AlterarAutorForm,
    AlterarChefiaForm,
    AlterarCoordenadorForm,
    AnaliseLiberacaoForm,
    AnexosDiversosProjetoForm,
    AnoForm,
    AreaConcentracaoProgramaPosForm,
    AreaConhecimentoPareceristaForm,
    ArquivarPIForm,
    ArquivoParceriaForm,
    AtividadesAvaliadoresForm,
    AutoCadastroPareceristaForm,
    AvaliacaoConselhoEditorialForm,
    AvaliacaoDiagramacaoForm,
    AvaliacaoFormFactory,
    AvaliacaoPareceristaObraForm,
    AvaliadoresAreaConhecimentoForm,
    AvaliarAlteracaoEquipeForm,
    AvaliarCancelamentoProjetoForm,
    AvaliarInclusaoEquipeForm,
    AvaliarLaboratorioMultiusuarioForm,
    AvaliarRecursoForm,
    AvaliarRecursoProjetoForm,
    AvaliarRecursosForm,
    AvaliarSolicitacaoLaboratorioForm,
    BuscaProjetoForm,
    CadastrarDiagramacaoObraForm,
    CadastrarISBNObraForm,
    CampusForm,
    CancelamentoObraForm,
    CancelarAvaliacaoEtapaForm,
    CancelarAvaliacaoGastoForm,
    CancelarProjetoForm,
    CartaoPesquisadorForm,
    CertificadoRegistroPIForm,
    ChecklistObraDiagramadorForm,
    ChecklistObraForm,
    ClassificacaoLocarnoForm,
    ClassificarTRLForm,
    ClonarEditalForm,
    ClonarEtapaForm,
    ClonarProjetoForm,
    ComissaoAvaliacaoForm,
    ComissaoAvaliacaoPorAreaForm,
    ConclusaoObraForm,
    CriterioAvaliacaoForm,
    CursoProgramaPosForm,
    DadosBancariosParticipanteForm,
    DashboardParceriaForm,
    DashboardPIForm,
    DataInativacaoForm,
    DesembolsoForm,
    DesfazerFinalizacaoForm,
    DocenteProgramaPosForm,
    DocumentoIncubadoraForm,
    DocumentoTransferenciaTecnologicaForm,
    EditaisForm,
    EditaisPesquisaForm,
    EditalAnexoAuxiliarForm,
    EditalAnexoForm,
    EditarFotoProjetoForm,
    EditarFrequenciaForm,
    EditarProjetoEmExecucaoForm,
    EmailCoordenadoresForm,
    EmitirParecerRevisaoObraForm,
    EmpreendimentoIncubadoraForm,
    EquipamentoLaboratorioForm,
    EquipeEtapaForm,
    EquipeProjetoForm,
    EstatisticasForm,
    EstatisticasLaboratoriosForm,
    EstatisticasporCampusForm,
    EtapaForm,
    EtapaParceriaForm,
    EventoIncubadoraForm,
    FichaCatalograficaForm,
    FiltrarLaboratorioPesquisaForm,
    FinalizarAssessorForm,
    FotoIncubadoraForm,
    FotoLaboratorioForm,
    FotoProjetoForm,
    GerarListaFrequenciaForm,
    GerenciarSupervisorForm,
    InativarProjetoForm,
    IndicadoresForm,
    IndicarAuxiliarForm,
    IndicarAvaliadoresForm,
    IndicarAvaliadorForm,
    IndicarConselheiroForm,
    IndicarCoorientadorForm,
    IndicarDiagramadorForm,
    IndicarOrientadorForm,
    IndicarPareceristaForm,
    IndicarRevisorForm,
    InformarPagamentoAnuidadeRPIForm,
    InformarResponsavelAnuidadeForm,
    InterporRecursoPesquisaForm,
    ItemMemoriaCalculoForm,
    JustificativaPreAvaliacaoForm,
    ListaMensalBolsistaForm,
    MaterialLaboratorioPesquisaForm,
    MembroIncubadoraForm,
    MembroObraForm,
    MembroParceriaForm,
    MetaForm,
    MeusProjetosForm,
    MinhasSolicitacoesServicosForm,
    OfertaProjetoPesquisaForm,
    OfertaProjetoPesquisaFormMultiplo,
    ParceiroForm,
    ParceriaForm,
    PareceristasObraForm,
    ParticipacaoAlunoForm,
    ParticipacaoColaboradorForm,
    ParticipacaoServidorForm,
    PiParceriaForm,
    ProjetoAvaliadorForm,
    ProjetoForm,
    ProjetoHistoricoDeEnvioForm,
    ProjetoLaboratorioForm,
    ProjetosAtrasadosForm,
    PublicacaoObraForm,
    QuesitoAutoavaliacaoForm,
    RecrutarAssessorForm,
    RecursoForm,
    RecursoPesquisaForm,
    RecursoTransferenciaTecnologicaForm,
    ReenviarObraForm,
    RegistrarFrequenciaForm,
    RegistroConclusaoProjetoForm,
    RegistroConclusaoProjetoObsForm,
    RegistroDiarioBordoForm,
    RegistroExecucaoEtapaForm,
    RegistroGastoForm,
    RelacionarProcessoAnuidadeRPIForm,
    RelacionarProcessoRPIForm,
    RelatorioDimensaoForm,
    RelatorioLaboratorioForm,
    RelatorioProjetoForm,
    ReprovarExecucaoEtapaForm,
    ReprovarExecucaoGastoForm,
    RevisarAutorForm,
    RevisarObraForm,
    SecretarioProgramaPosForm,
    ServicoLaboratorioForm,
    SituacaoObraForm,
    SolicitacoesAlteracaoForm,
    SolicitarAlteracaoEquipeForm,
    SolicitarInclusaoEquipeForm,
    SolicitarServicoLaboratorioForm,
    SubmeterObraForm,
    SubmeterPublicacaoEventoForm,
    SupervisorForm,
    TermoAssinadoForm,
    TermoCessaoRPIForm,
    TransferenciaTecnologicaForm,
    UploadArquivoForm,
    UploadProjetoAnexoForm,
    UploadTermosForm,
    ValidacaoConclusaoProjetoForm,
    ValidarCancelamentoProjetoForm,
    ValidarRecursoProjetoForm,
    VerificaAutenticidadeForm,
)
from pesquisa.models import (
    AnuidadeRegistroPropriedadeIntelectual,
    AreaConcentracaoProgramaPos,
    AreaConhecimentoParecerista,
    ArquivoParceria,
    AssessorIncubadora,
    AutoavaliacaoProgramaPos,
    Avaliacao,
    AvaliadorExterno,
    AvaliadorIndicado,
    BolsaDisponivel,
    ColaboradorExterno,
    ComissaoEditalPesquisa,
    CriterioAvaliacao,
    CriterioAvaliacaoObra,
    CursoProgramaPos,
    Desembolso,
    DoacaoEditora,
    DocenteProgramaPos,
    DocumentoIncubadora,
    DocumentoTransferencia,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    EditalSubmissaoObra,
    EmpreendimentoIncubadora,
    GRUPOS_PRE_SELECAO_INSTITUCIONAIS,
    EquipamentoLaboratorioPesquisa,
    Etapa,
    EtapaParceria,
    EventoIncubadora,
    FotoIncubadora,
    FotoLaboratorioPesquisa,
    FotoProjeto,
    HistoricoEquipe,
    Incubadora,
    IntegranteEquipeTecnica,
    ItemAvaliacao,
    ItemAvaliacaoObra,
    ItemMemoriaCalculo,
    LaboratorioPesquisa,
    MaterialConsumoPesquisa,
    MaterialLaboratorioPesquisa,
    MembroIncubadora,
    MembroObra,
    MembroParceria,
    Meta,
    Obra,
    Parceiro,
    ParceiroPiParceria,
    Parceria,
    ParecerObra,
    Participacao,
    PerguntaQuestionarioObra,
    PessoaExternaObra,
    PiParceria,
    ProgramaPosGraduacao,
    Projeto,
    ProjetoAnexo,
    ProjetoCancelado,
    ProjetoHistoricoDeEnvio,
    ProjetoLaboratorioPesquisa,
    PropriedadeIntelectual,
    PublicacaoPropriedadeIntelectual,
    QuesitoAutoavaliacao,
    RecrutamentoAssessor,
    Recurso,
    RecursoProjeto,
    RecursoTransferencia,
    RegistroConclusaoProjeto,
    RegistroDiarioBordo,
    RegistroExecucaoEtapa,
    RegistroFrequencia,
    RegistroGasto,
    RegistroPropriedadeIntelectual,
    RelatorioProjeto,
    SecretarioProgramaPos,
    ServicoLaboratorioPesquisa,
    ServicoRegistroPropriedadeIntelectual,
    SolicitacaoAlteracaoEquipe,
    SolicitacaoInclusaoEquipe,
    SolicitacaoServicoLaboratorio,
    TipoParceria,
    TipoTransferenciaTecnologica,
    TipoVinculo,
    TransferenciaTecnologica,
)
from rh.models import AreaConhecimento, Servidor, UnidadeOrganizacional
from rh.views import rh_servidor_view_tab


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    participacoes = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), ativo=True, projeto__aprovado=True)
    for participacao in participacoes:
        data.append(
            (
                'Pesquisa',
                'Projeto de Pesquisa',
                'Comprovante de Participação',
                participacao.projeto,
                f'/pesquisa/emitir_declaracao_participacao_pdf/{participacao.pk}/',
            )
        )


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []
    servicos_anonimos.append(
        {'categoria': 'Pesquisa', 'url': '/pesquisa/autocadastro_parecerista/', 'icone': 'file-alt', 'titulo': 'Seja um Parecerista'}
    )
    return servicos_anonimos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Reúne pendências de Pesquisa atribuídas ao usuário logado.

    Considera projetos, editais, planos de trabalho, frequências, relatórios,
    avaliações e demais ações nas quais o usuário é responsável conforme seu
    papel (coordenador, orientador, avaliador, gestor de edital, etc.).

    Args:
        request: requisição HTTP usada para identificar usuário, vínculo e relacionamento.

    Returns:
        list[dict]: cartões de pendência específicos do módulo de Pesquisa;
        lista vazia quando o usuário não tem ações pendentes.
    """
    pendencias = []
    usuario = request.user
    vinculo = usuario.get_vinculo()
    relacionamento = usuario.get_relacionamento()
    agora = datetime.datetime.now()

    if usuario.eh_servidor:
        projetos = Projeto.objects.filter(
            pre_aprovado=False,
            aprovado=False,
            responsavel_anuencia=relacionamento,
            projetocancelado__isnull=True,
            anuencia_registrada_em__isnull=True,
        )
        projetos_sem_anuencia = (
            projetos.filter(
                edital__formato=Edital.FORMATO_COMPLETO,
                edital__inicio_pre_selecao__gt=agora,
                edital__tipo_edital__in=[Edital.PESQUISA, Edital.INOVACAO],
            ).count()
            + projetos.filter(edital__tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO, edital__fim_inscricoes__gt=agora).count()
            + projetos.filter(edital__fim_inscricoes__gt=agora, edital__formato=Edital.FORMATO_SIMPLIFICADO).count()
        )
        if projetos_sem_anuencia:
            pendencias.append(
                {
                    'titulo': f'Projeto{pluralize(projetos_sem_anuencia)} de Pesquisa',
                    'subtitulo': 'aguardando anuência',
                    'qtd': projetos_sem_anuencia,
                    'url': '/pesquisa/projetos_pendentes_anuencia/',
                }
            )

        projetos_em_execucao = Projeto.objects.filter(
            pre_aprovado=True,
            aprovado=True,
            inativado=False,
            projetocancelado__isnull=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            vinculo_coordenador=vinculo,
        )
        hoje_date = datetime.date.today()
        # `tem_data_fim_execucao_em(dias=15)` é `hoje <= fim_execucao <= hoje+15`; `()` é `fim_execucao == hoje`.
        # Filtragem direta via SQL elimina a iteração N+1 desses dois alertas.
        projeto_fim_quinze = (
            projetos_em_execucao.filter(fim_execucao__gte=hoje_date, fim_execucao__lte=hoje_date + relativedelta(days=15))
            .only('id', 'titulo')
            .first()
        )
        if projeto_fim_quinze:
            pendencias.append(
                {
                    'url': f'/pesquisa/projeto/{projeto_fim_quinze.id}/',
                    'titulo': f'A finalização do projeto {projeto_fim_quinze.titulo}, sob sua coordenação, está prevista para ocorrer nos próximos <strong>quinze dias</strong>.',
                }
            )
        projeto_fim_hoje = projetos_em_execucao.filter(fim_execucao=hoje_date).only('id', 'titulo').first()
        if projeto_fim_hoje:
            pendencias.append(
                {
                    'url': f'/pesquisa/projeto/{projeto_fim_hoje.id}/',
                    'titulo': f'A finalização do projeto {projeto_fim_hoje.titulo}, sob sua coordenação, está prevista para <strong>hoje</strong>.',
                }
            )
        # `tem_metas_vencendo_em` ainda exige iteração (depende de `meta.get_data_final_meta()` que não é simples
        # de traduzir para SQL); usamos `iterator()` + early break para parar assim que os dois alertas saírem.
        alerta_vence_meta_sete_dias = False
        alerta_vence_meta_hoje = False
        for projeto in projetos_em_execucao.only('id', 'titulo').iterator():
            if not alerta_vence_meta_sete_dias and projeto.tem_metas_vencendo_em(dias=7):
                pendencias.append(
                    {
                        'url': f'/pesquisa/projeto/{projeto.id}/',
                        'titulo': f'O projeto <strong>{projeto.titulo}</strong>, sob sua coordenação, possui meta com prazo de expiração nos próximos <strong>sete dias</strong>.',
                    }
                )
                alerta_vence_meta_sete_dias = True
            if not alerta_vence_meta_hoje and projeto.tem_metas_vencendo_em():
                pendencias.append(
                    {
                        'url': f'/pesquisa/projeto/{projeto.id}/',
                        'titulo': f'O projeto <strong>{projeto.titulo}</strong>, sob sua coordenação, possui meta com prazo expirando <strong>hoje</strong>.',
                    }
                )
                alerta_vence_meta_hoje = True
            if alerta_vence_meta_sete_dias and alerta_vence_meta_hoje:
                break

        projeto_simplificado_pendente_conclusao = Projeto.objects.filter(
            data_finalizacao_conclusao__isnull=True,
            registroconclusaoprojeto__isnull=False,
            edital__formato=Edital.FORMATO_SIMPLIFICADO,
            vinculo_supervisor=vinculo,
        )
        gerou_alerta_finalizacao = False
        if projeto_simplificado_pendente_conclusao.exists():
            for projeto in projeto_simplificado_pendente_conclusao:
                if not gerou_alerta_finalizacao and not projeto.tem_pendencias():
                    pendencias.append(
                        {
                            'url': f'/pesquisa/projeto/{projeto_simplificado_pendente_conclusao[0].id}/?tab=conclusao',
                            'titulo': '<strong>Projeto{plural} de Pesquisa</strong> simplificado pendente{plural} de finalização.'.format(
                                plural=pluralize(projeto_simplificado_pendente_conclusao)
                            ),
                        }
                    )
                    gerou_alerta_finalizacao = True
        doacao_pendente_aceite = DoacaoEditora.objects.filter(servidor=relacionamento, aceite_em=None)
        if doacao_pendente_aceite.exists():
            pendencias.append(
                {
                    'url': f'/pesquisa/aceitar_doacao_editora/{doacao_pendente_aceite[0].id}/',
                    'titulo': '<strong>Existe uma doação realizada pela Editora</strong> pendente do seu aceite.',
                }
            )

    if usuario.has_perm('pesquisa.pode_avaliar_obra', ignore_superuser=True):
        obras_pendentes_parecer = ParecerObra.objects.filter(
            parecer_realizado_por_vinculo=vinculo, situacao=ParecerObra.EM_ANALISE, recusou_indicacao=False
        )
        qtd_obras_pendentes_parecer = obras_pendentes_parecer.count()
        if qtd_obras_pendentes_parecer:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_parecer)}',
                    'subtitulo': 'aguardando parecer',
                    'qtd': qtd_obras_pendentes_parecer,
                    'url': f'/pesquisa/obra/{obras_pendentes_parecer[0].id}/',
                }
            )

        parecer = ParecerObra.objects.filter(nota__isnull=False, obra__situacao=Obra.ACEITA)
        obras_pendentes_parecer = Obra.objects.filter(
            id__in=parecer.values_list('obra', flat=True),
            julgamento_conselho_realizado_por_vinculo=vinculo,
            julgamento_conselho_realizado_em__isnull=True,
        )
        qtd_obras_pendentes_parecer = obras_pendentes_parecer.count()
        if qtd_obras_pendentes_parecer:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_parecer)}',
                    'subtitulo': 'aguardando validação',
                    'qtd': qtd_obras_pendentes_parecer,
                    'url': f'/pesquisa/obra/{obras_pendentes_parecer[0].id}/',
                }
            )

        obras_pendentes_indicacao_parecerista = Obra.objects.filter(
            situacao=Obra.ACEITA, julgamento_conselho_realizado_por_vinculo=vinculo, julgamento_conselho_realizado_em__isnull=True
        ).exclude(id__in=ParecerObra.objects.all().values_list('obra', flat=True))
        qtd_obras_pendentes_indicacao_parecerista = obras_pendentes_indicacao_parecerista.count()
        if qtd_obras_pendentes_indicacao_parecerista:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_indicacao_parecerista)}',
                    'subtitulo': 'aguardando indicação de parecerista',
                    'qtd': qtd_obras_pendentes_indicacao_parecerista,
                    'url': f'/pesquisa/obra/{obras_pendentes_indicacao_parecerista[0].id}/',
                }
            )

        obras_pendentes_parecer = Obra.objects.filter(situacao=Obra.CATALOGADA, julgamento_conselho_realizado_por_vinculo=vinculo)
        qtd_obras_pendentes_parecer = obras_pendentes_parecer.count()
        if qtd_obras_pendentes_parecer:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_parecer)}',
                    'subtitulo': 'aguardando análise de liberação',
                    'qtd': qtd_obras_pendentes_parecer,
                    'url': f'/pesquisa/obra/{obras_pendentes_parecer[0].id}/',
                }
            )

    if request.user.has_perm('pesquisa.pode_diagramar_obra', ignore_superuser=True):
        obras_pendentes_diagramacao = Obra.objects.filter(situacao=Obra.REVISADA, diagramacao_realizada_por_vinculo=vinculo)
        qtd_obras_pendentes_diagramacao = obras_pendentes_diagramacao.count()
        if qtd_obras_pendentes_diagramacao:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_diagramacao)}',
                    'subtitulo': 'aguardando diagramação',
                    'qtd': qtd_obras_pendentes_diagramacao,
                    'url': f'/pesquisa/obra/{obras_pendentes_diagramacao[0].id}/',
                }
            )

        obras_pendentes_diagramacao_final = Obra.objects.filter(
            situacao=Obra.DIAGRAMADA, diagramacao_realizada_por_vinculo=vinculo, diagramacao_avaliada_em__isnull=False
        )
        qtd_obras_pendentes_diagramacao_final = obras_pendentes_diagramacao_final.count()
        if qtd_obras_pendentes_diagramacao_final:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_diagramacao_final)}',
                    'subtitulo': 'aguardando versão final da diagramação',
                    'qtd': qtd_obras_pendentes_diagramacao_final,
                    'url': f'/pesquisa/obra/{obras_pendentes_diagramacao_final[0].id}/',
                }
            )

    if request.user.has_perm('pesquisa.pode_revisar_obra', ignore_superuser=True):
        obras_pendentes_revisao = Obra.objects.filter(
            situacao__in=[Obra.VALIDADA, Obra.ASSINADA], revisao_realizada_por_vinculo=vinculo, revisao_realizada_em__isnull=True
        )
        qtd_obras_pendentes_revisao = obras_pendentes_revisao.count()
        if qtd_obras_pendentes_revisao:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_revisao)}',
                    'subtitulo': 'aguardando revisão',
                    'qtd': qtd_obras_pendentes_revisao,
                    'url': f'/pesquisa/obra/{obras_pendentes_revisao[0].id}/',
                }
            )

        obras_pendentes_parecer = Obra.objects.filter(
            revisao_realizada_por_vinculo=vinculo,
            revisao_realizada_em__isnull=False,
            correcoes_enviadas_em__isnull=False,
            parecer_revisor__isnull=True,
        )
        qtd_obras_pendentes_parecer = obras_pendentes_parecer.count()
        if qtd_obras_pendentes_parecer:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_parecer)}',
                    'subtitulo': 'aguardando parecer final da revisão',
                    'qtd': qtd_obras_pendentes_parecer,
                    'url': f'/pesquisa/obra/{obras_pendentes_parecer[0].id}/',
                }
            )
    if request.user.has_group_cached('Diretor de Pesquisa', ignore_groups_if_superuser=False):
        laboratorio_pendentes = LaboratorioPesquisa.objects.filter(aprovado=None).count()
        if laboratorio_pendentes:
            pendencias.append(
                {
                    'titulo': f'Laboratório{pluralize(laboratorio_pendentes)}',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': laboratorio_pendentes,
                    'url': '/admin/pesquisa/laboratoriopesquisa/?tab=tab_aguardando_avaliacao',
                }
            )
        propriedade_com_despacho_pendente = len(
            set(PublicacaoPropriedadeIntelectual.objects.filter(lida=False).values_list('propriedadeintelectual', flat=True))
        )
        if propriedade_com_despacho_pendente:
            pendencias.append(
                {
                    'titulo': f'Registro{pluralize(propriedade_com_despacho_pendente)} de Patente{pluralize(propriedade_com_despacho_pendente)}',
                    'subtitulo': 'com despacho(s) pendente(s) de leitura',
                    'qtd': propriedade_com_despacho_pendente,
                    'url': '/admin/pesquisa/registropropriedadeintelectual/?nao_lido=1',
                }
            )
        hoje = agora.date()
        pendentes = AnuidadeRegistroPropriedadeIntelectual.objects.filter(
            propriedadeintelectual__ativo=True, situacao=AnuidadeRegistroPropriedadeIntelectual.PENDENTE, inicio_ordinario__lte=hoje
        )
        if pendentes.exists():
            total = pendentes.count()
            pendencias.append(
                {
                    'titulo': f'Anuidade{pluralize(total)}',
                    'subtitulo': f'pendente{pluralize(total)} de pagamento',
                    'qtd': total,
                    'url': '/admin/pesquisa/registropropriedadeintelectual/?pagamento_pendente=1',
                }
            )
    editais = Edital.objects.all().em_avaliacao_recursos()
    if editais.exists():
        recursos_pendentes = ItemAvaliacao.objects.exclude(recurso=None).filter(
            avaliacao__projeto__edital__in=editais.values_list('id', flat=True), avaliacao__vinculo=vinculo, recurso_avaliado_em=None
        )
        if recursos_pendentes.exists():
            total = recursos_pendentes.count()
            pendencias.append(
                {
                    'titulo': f'Recurso{pluralize(total)} de Projeto{pluralize(total)}',
                    'subtitulo': 'pendentes de avaliação',
                    'qtd': total,
                    'url': '/pesquisa/avaliar_recursos/',
                }
            )
    recrutamento = RecrutamentoAssessor.objects.filter(vinculo=vinculo, avaliado_em=None)
    if recrutamento.exists():
        pendencias.append(
            {
                'titulo': f'Você possui um convite para participar como Assessor(a) Técnico(a) da {recrutamento[0].incubadora.sigla}',
                'url': f'/pesquisa/avaliar_recrutamento/{recrutamento[0].id}/',
            }
        )

    projetos_em_execucao_minha_supervisao = Projeto.objects.filter(
        pre_aprovado=True,
        aprovado=True,
        inativado=False,
        projetocancelado__isnull=True,
        registroconclusaoprojeto__dt_avaliacao__isnull=True,
        vinculo_supervisor=vinculo,
    )
    relatorio_para_avaliar = (
        RelatorioProjeto.objects.filter(avaliado_em=None, projeto__in=projetos_em_execucao_minha_supervisao.values_list('id', flat=True))
        .select_related('projeto')
        .only('id', 'projeto__id')
        .first()
    )
    if relatorio_para_avaliar:
        pendencias.append(
            {
                'url': f'/pesquisa/validar_execucao_etapa/{relatorio_para_avaliar.projeto.id}/?tab=relatorios',
                'titulo': '<strong>Existe novo relatório</strong> pendente da sua avaliação.',
            }
        )

    finalizacao_para_avaliar = (
        Projeto.objects.exclude(data_finalizacao_conclusao=None)
        .filter(registroconclusaoprojeto__dt_avaliacao__isnull=True, id__in=projetos_em_execucao_minha_supervisao.values_list('id', flat=True))
        .only('id')
        .first()
    )
    if finalizacao_para_avaliar:
        pendencias.append(
            {
                'url': f'/pesquisa/validar_execucao_etapa/{finalizacao_para_avaliar.id}/?tab=conclusao',
                'titulo': '<strong>Existe novo projeto com solicitação de finalização</strong> pendente da sua avaliação.',
            }
        )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    vinculo = request.user.get_vinculo()
    relacionamento = request.user.get_relacionamento()

    if request.user.eh_servidor:
        servidor = relacionamento
        uo = servidor.setor and servidor.setor.uo

        pendencia_aceite_termo = Participacao.objects.filter(
            ativo=True,
            responsavel=False,
            projeto__edital__termo_compromisso_servidor__isnull=False,
            vinculo_pessoa=vinculo,
            termo_aceito_em__isnull=True,
        ).exclude(projeto__edital__termo_compromisso_servidor='')
        if pendencia_aceite_termo.exists():
            for registro in pendencia_aceite_termo:
                if registro.projeto.get_status() not in [Projeto.STATUS_NAO_ENVIADO, Projeto.STATUS_INATIVADO, Projeto.STATUS_CANCELADO]:
                    pendencias.append(
                        {
                            'url': f'/pesquisa/projeto/{registro.projeto.id}/?tab=equipe',
                            'titulo': f'Você <strong>precisa aceitar o Termo de Compromisso</strong> do projeto <strong>{registro.projeto.titulo}</strong>.',
                        }
                    )

        if request.user.has_group_cached('Coordenador de Pesquisa', ignore_groups_if_superuser=False):
            tem_solicitacoes_alteracoes = False
            solicitacoes_alteracoes = SolicitacaoAlteracaoEquipe.objects.filter(atendida=None, projeto__uo_id=uo.pk)
            if solicitacoes_alteracoes.exists():
                for pedido in solicitacoes_alteracoes:
                    if (
                        not tem_solicitacoes_alteracoes
                        and pedido.projeto.pode_editar_inscricao_execucao()
                        and not pedido.projeto.eh_somente_leitura()
                    ):
                        pendencias.append(
                            {
                                'url': f'/pesquisa/solicitar_alteracao_equipe/{pedido.projeto_id}/',
                                'titulo': f'Pedido de <strong>alteração na equipe</strong> do projeto de pesquisa <strong>{pedido.projeto.titulo}</strong> não avaliado.',
                            }
                        )
                        tem_solicitacoes_alteracoes = True

            tem_solicitacoes_inclusao = False
            solicitacoes_inclusao = SolicitacaoInclusaoEquipe.objects.filter(atendida=None, projeto__uo_id=uo.pk)
            if solicitacoes_inclusao.exists():
                for pedido in solicitacoes_inclusao:
                    if not tem_solicitacoes_inclusao and pedido.projeto.pode_editar_inscricao_execucao() and not pedido.projeto.eh_somente_leitura():
                        pendencias.append(
                            {
                                'url': f'/pesquisa/projeto/{pedido.projeto_id}/?tab=equipe',
                                'titulo': f'Pedido de <strong>inclusão na equipe</strong> do projeto de pesquisa <strong>{pedido.projeto.titulo}</strong> não avaliado.',
                            }
                        )
                        tem_solicitacoes_inclusao = True

            projeto_simplificado_pendente_deferimento = Projeto.objects.filter(
                uo=uo,
                edital__formato=Edital.FORMATO_SIMPLIFICADO,
                data_conclusao_planejamento__isnull=False,
                data_pre_avaliacao__isnull=True,
                vinculo_supervisor__isnull=True,
            ).exclude(id__in=ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True))
            if projeto_simplificado_pendente_deferimento.exists():
                qtd = projeto_simplificado_pendente_deferimento.count()
                pendencias.append(
                    {
                        'url': '/admin/pesquisa/projeto/?pendente_validacao=Sim&tab=tab_any_data',
                        'titulo': f'<strong>Projeto{pluralize(qtd)} de Pesquisa</strong> de edital simplificado pendente{pluralize(qtd)} de validação.',
                        'qtd': qtd,
                    }
                )

        if request.user.has_group_cached('Diretor de Pesquisa', ignore_groups_if_superuser=False):
            edital_pendente_autorizacao = Edital.objects.filter(autorizado__isnull=True)
            if edital_pendente_autorizacao.exists():
                pendencias.append(
                    {
                        'url': '/admin/pesquisa/edital/',
                        'titulo': f'O Edital <strong>{edital_pendente_autorizacao[0].titulo}</strong> está pendente de autorização.',
                    }
                )

        if request.user.has_group_cached('Integrante da Editora', ignore_groups_if_superuser=False):
            obras_pendentes_indicar_parecer = ParecerObra.objects.filter(
                recusou_indicacao=True, obra__edital__data_termino_analise_especialista__gte=datetime.datetime.now()
            )
            if obras_pendentes_indicar_parecer.exists():
                pendencias.append(
                    {
                        'url': f'/pesquisa/obra/{obras_pendentes_indicar_parecer[0].obra.id}/?tab=analise_parecerista',
                        'titulo': 'Um parecerista <strong>rejeitou a indicação</strong> e precisa ser substituído.',
                    }
                )

    if request.user.eh_servidor and relacionamento.setor:
        uo = relacionamento.setor.uo

        if relacionamento.areas_de_conhecimento.all().exists():
            edital_pesquisa_para_avaliar = Edital.objects.em_selecao()
            if edital_pesquisa_para_avaliar.exists():
                ids_editais = edital_pesquisa_para_avaliar.values_list('id', flat=True)
                indicacoes = AvaliadorIndicado.objects.filter(
                    projeto__aprovado=False, vinculo=vinculo, projeto__edital_id__in=ids_editais, rejeitado=False
                ).count()
                avaliacoes = Avaliacao.objects.filter(projeto__aprovado=False, vinculo=vinculo, projeto__edital_id__in=ids_editais).count()
                if indicacoes > avaliacoes:
                    qtd = indicacoes - avaliacoes
                    pendencias.append(
                        {
                            'titulo': f'Projeto{pluralize(qtd)} de Pesquisa',
                            'subtitulo': 'a avaliar',
                            'qtd': qtd,
                            'url': '/pesquisa/avaliacao/',
                        }
                    )

        if request.user.has_group_cached('Coordenador de Pesquisa', ignore_groups_if_superuser=False):
            qtd_recursos_projetos = RecursoProjeto.objects.filter(data_avaliacao__isnull=True, projeto__uo_id=uo.pk).count()
            if qtd_recursos_projetos:
                pendencias.append(
                    {
                        'titulo': f'Recurso{pluralize(qtd_recursos_projetos)} de Projetos de Pesquisa',
                        'subtitulo': 'a avaliar',
                        'qtd': qtd_recursos_projetos,
                        'url': '/pesquisa/solicitacoes_de_recurso/',
                    }
                )

            qtd_projetos_cancelados = ProjetoCancelado.objects.filter(
                projeto__data_conclusao_planejamento__isnull=False, data_avaliacao__isnull=True, projeto__uo_id=uo.id
            ).count()
            if qtd_projetos_cancelados:
                pendencias.append(
                    {
                        'titulo': f'Pedido{pluralize(qtd_projetos_cancelados)} de Cancelamento de Projeto{pluralize(qtd_projetos_cancelados)} de Pesquisa',
                        'subtitulo': 'a avaliar',
                        'qtd': qtd_projetos_cancelados,
                        'url': '/pesquisa/solicitacoes_de_cancelamento/',
                    }
                )

        if request.user.has_group_cached('Diretor de Pesquisa', ignore_groups_if_superuser=False):
            qtd_recursos_aceitos = RecursoProjeto.objects.filter(data_validacao__isnull=True, parecer_favoravel=True).count()
            if qtd_recursos_aceitos:
                pendencias.append(
                    {
                        'titulo': f'Recurso{pluralize(qtd_recursos_aceitos)} de Projeto{pluralize(qtd_recursos_aceitos)} de Pesquisa',
                        'subtitulo': 'a avaliar',
                        'qtd': qtd_recursos_aceitos,
                        'url': '/pesquisa/solicitacoes_de_recurso/',
                    }
                )

            qtd_projetos_cancelados = ProjetoCancelado.objects.filter(
                projeto__data_conclusao_planejamento__isnull=False, data_validacao__isnull=True, parecer_favoravel=True
            ).count()
            if qtd_projetos_cancelados:
                pendencias.append(
                    {
                        'titulo': f'Pedido{pluralize(qtd_projetos_cancelados)} de Cancelamento de Projeto{pluralize(qtd_projetos_cancelados)} de Pesquisa',
                        'subtitulo': 'a validar',
                        'qtd': qtd_projetos_cancelados,
                        'url': '/pesquisa/solicitacoes_de_cancelamento/?edital=&situacao=Pendentes+de+Validação&editaispesquisa_form=Aguarde...',
                    }
                )

        if request.user.has_group_cached(['Coordenador de Pesquisa', 'Supervisor de Projetos de Pesquisa'], ignore_groups_if_superuser=False):
            if request.user.has_perm('pesquisa.pode_pre_avaliar_projeto', ignore_superuser=True):
                projetos_para_pre_avaliar = Projeto.objects.filter(
                    pre_aprovado=False,
                    aprovado=False,
                    data_conclusao_planejamento__isnull=False,
                    projetocancelado__isnull=True,
                    uo=uo,
                    edital__in=Edital.objects.em_pre_avaliacao().values_list('id', flat=True),
                ).count()
                if projetos_para_pre_avaliar:
                    pendencias.append(
                        {
                            'titulo': f'Projeto{pluralize(projetos_para_pre_avaliar)} de Pesquisa',
                            'subtitulo': 'a pré-avaliar',
                            'qtd': projetos_para_pre_avaliar,
                            'url': '/pesquisa/pre_avaliacao/pesquisa/',
                        }
                    )

    if request.user.eh_servidor or request.user.eh_prestador:
        obras_pendentes_envio_correcao = Obra.objects.filter(
            submetido_por_vinculo=vinculo, situacao=Obra.ACEITA, situacao_conselho_editorial=Obra.FAVORAVEL_COM_RESSALVAS
        )
        if obras_pendentes_envio_correcao.exists():
            obras_pendentes_envio_correcao = obras_pendentes_envio_correcao[0]
            pendencias.append(
                {
                    'url': f'/pesquisa/obra/{obras_pendentes_envio_correcao.id}/?tab=validacao_conselho',
                    'titulo': 'Você precisa enviar sua obra corrigida.',
                }
            )

        obras_pendentes_envio_correcao = Obra.objects.filter(
            submetido_por_vinculo=vinculo, situacao=Obra.ASSINADA, arquivo_obra_revisada__isnull=False, revisada_pelo_autor__isnull=True
        )
        if obras_pendentes_envio_correcao.exists():
            obras_pendentes_envio_correcao = obras_pendentes_envio_correcao[0]
            pendencias.append(
                {
                    'url': f'/pesquisa/obra/{obras_pendentes_envio_correcao.id}/?tab=revisao_textual',
                    'titulo': 'Você precisa enviar sua obra revisada.',
                }
            )

        obras_pendentes_avaliacao_diagramacao = Obra.objects.filter(
            submetido_por_vinculo=vinculo, situacao=Obra.DIAGRAMADA, diagramacao_avaliada_em__isnull=True
        )
        if obras_pendentes_avaliacao_diagramacao.exists():
            obras_pendentes_avaliacao_diagramacao = obras_pendentes_avaliacao_diagramacao[0]
            pendencias.append(
                {
                    'url': f'/pesquisa/obra/{obras_pendentes_avaliacao_diagramacao.id}/?tab=diagramacao',
                    'titulo': 'Você precisa avaliar a diagramação da sua obra.',
                }
            )

        obras_pendentes_termos = Obra.objects.filter(submetido_por_vinculo=vinculo, situacao=Obra.VALIDADA, termo_autorizacao_publicacao='')
        if obras_pendentes_termos.exists():
            obras_pendentes_termos = obras_pendentes_termos[0]
            pendencias.append(
                {'url': f'/pesquisa/obra/{obras_pendentes_termos.id}/?tab=termos', 'titulo': 'Você precisa enviar os termos assinados da sua obra.'}
            )

    if request.user.has_group_cached('Integrante da Editora', ignore_groups_if_superuser=False):
        nova_obra_submetida = Obra.objects.filter(situacao=Obra.SUBMETIDA)
        qtd_nova_obra_submetida = nova_obra_submetida.count()
        if qtd_nova_obra_submetida:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_nova_obra_submetida)}',
                    'subtitulo': 'a iniciar',
                    'qtd': qtd_nova_obra_submetida,
                    'url': f'/pesquisa/obra/{nova_obra_submetida[0].id}/',
                }
            )

        pendentes_aceite = Obra.objects.filter(situacao=Obra.AUTENTICA, aceita_editora_realizada_por_vinculo__isnull=True)
        qtd_pendentes_aceite = pendentes_aceite.count()
        if qtd_pendentes_aceite:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_pendentes_aceite)}',
                    'subtitulo': 'a aceitar',
                    'qtd': qtd_pendentes_aceite,
                    'url': f'/pesquisa/obra/{pendentes_aceite[0].id}/',
                }
            )

        obras_pendentes_termos = Obra.objects.filter(
            situacao=Obra.VALIDADA, termos_assinados_realizado_por_vinculo__isnull=True, revisao_realizada_em__isnull=True
        ).exclude(termo_autorizacao_publicacao='')
        qtd_obras_pendentes_termos = obras_pendentes_termos.count()
        if qtd_obras_pendentes_termos:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_termos)}',
                    'subtitulo': 'com termos assinados',
                    'qtd': qtd_obras_pendentes_termos,
                    'url': f'/pesquisa/obra/{obras_pendentes_termos[0].id}',
                }
            )

        obras_pendentes_conselheiro = Obra.objects.filter(situacao=Obra.ACEITA, julgamento_conselho_realizado_por_vinculo__isnull=True)
        qtd_obras_pendentes_conselheiro = obras_pendentes_conselheiro.count()
        if qtd_obras_pendentes_conselheiro:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_conselheiro)}',
                    'subtitulo': 'a indicar conselheiro',
                    'qtd': qtd_obras_pendentes_conselheiro,
                    'url': f'/pesquisa/obra/{obras_pendentes_conselheiro[0].id}/',
                }
            )

        nova_obra_submetida = Obra.objects.filter(situacao=Obra.REVISADA, diagramacao_realizada_por_vinculo__isnull=True)
        qtd_nova_obra_submetida = nova_obra_submetida.count()
        if qtd_nova_obra_submetida:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_nova_obra_submetida)}',
                    'subtitulo': 'a indicar diagramador',
                    'qtd': qtd_nova_obra_submetida,
                    'url': f'/pesquisa/obra/{nova_obra_submetida[0].id}/',
                }
            )

        nova_obra_submetida = Obra.objects.filter(situacao=Obra.CORRIGIDA, isbn__isnull=True)
        qtd_nova_obra_submetida = nova_obra_submetida.count()
        if qtd_nova_obra_submetida:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_nova_obra_submetida)}',
                    'subtitulo': 'a cadastrar ISBN',
                    'qtd': qtd_nova_obra_submetida,
                    'url': f'/pesquisa/obra/{nova_obra_submetida[0].id}/',
                }
            )

        nova_obra_submetida = Obra.objects.filter(situacao=Obra.LIBERADA, situacao_publicacao=Obra.NAO_INICIADA)
        qtd_nova_obra_submetida = nova_obra_submetida.count()
        if qtd_nova_obra_submetida:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_nova_obra_submetida)}',
                    'subtitulo': 'a publicar',
                    'qtd': qtd_nova_obra_submetida,
                    'url': f'/pesquisa/obra/{nova_obra_submetida[0].id}/',
                }
            )

        nova_obra_submetida = Obra.objects.filter(situacao=Obra.LIBERADA).exclude(situacao_publicacao=Obra.NAO_INICIADA)
        qtd_nova_obra_submetida = nova_obra_submetida.count()
        if qtd_nova_obra_submetida:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_nova_obra_submetida)}',
                    'subtitulo': 'a concluir',
                    'qtd': nova_obra_submetida,
                    'url': f'/pesquisa/obra/{nova_obra_submetida[0].id}/',
                }
            )

    if request.user.has_perm('pesquisa.pode_gerar_ficha_catalografica', ignore_superuser=True):
        obras_pendentes_ficha = Obra.objects.filter(situacao=Obra.REGISTRADA_ISBN)
        qtd_obras_pendentes_ficha = obras_pendentes_ficha.count()
        if qtd_obras_pendentes_ficha:
            pendencias.append(
                {
                    'titulo': f'Obra{pluralize(qtd_obras_pendentes_ficha)}',
                    'subtitulo': 'a anexar ficha catalográfica',
                    'qtd': qtd_obras_pendentes_ficha,
                    'url': f'/pesquisa/obra/{obras_pendentes_ficha[0].id}/',
                }
            )

    return pendencias


@layout.quadro('Projetos de Pesquisa', icone='globe', pode_esconder=True)
def index_quadros(quadro, request):
    vinculo = request.user.get_vinculo()
    if request.user.eh_aluno or request.user.eh_prestador:
        projetos_do_usuario = Projeto.objects.filter(participacao__vinculo_pessoa=vinculo, aprovado=True)
        if projetos_do_usuario.exists():
            for projeto in projetos_do_usuario:
                quadro.add_item(layout.ItemGrupo(titulo=projeto.titulo, grupo='Meus Projetos', url=f'/pesquisa/projeto/{projeto.pk:d}/'))

    if request.user.has_group_cached(['Servidor', 'Aposentado']):
        hoje = datetime.datetime.now()
        editais_pesquisa = Edital.objects.filter(inicio_inscricoes__lte=hoje, fim_inscricoes__gte=hoje)
        for edital in editais_pesquisa:
            quadro.add_item(
                layout.ItemNoticia(
                    grupo='Inscrições abertas',
                    titulo=edital.titulo,
                    url='/pesquisa/editais_abertos/',
                    chapeu=f'Até {edital.fim_inscricoes.strftime("%d/%m/%Y %H:%M")}',
                )
            )

    if request.user.has_group_cached(['Coordenador de Pesquisa', 'Supervisor de Projetos de Pesquisa']):
        relacionamento = request.user.get_relacionamento()
        uo = relacionamento.setor.uo
        if request.user.has_perm('pesquisa.pode_pre_avaliar_projeto'):
            projetos_para_pre_avaliar = Projeto.objects.filter(
                pre_aprovado=False,
                aprovado=False,
                data_conclusao_planejamento__isnull=False,
                projetocancelado__isnull=True,
                uo=uo,
                edital__in=Edital.objects.em_pre_avaliacao().values_list('id', flat=True),
            )

            if projetos_para_pre_avaliar.exists():
                valor = projetos_para_pre_avaliar.count()
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Projeto{pluralize(valor)}',
                        subtitulo=f'Pendente{pluralize(valor)} de pré-avaliação',
                        qtd=valor,
                        url='/pesquisa/pre_avaliacao/pesquisa/',
                    )
                )

        projetos_em_execucao = Projeto.objects.filter(
            pre_aprovado=True, aprovado=True, projetocancelado__isnull=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, uo=uo
        )
        if not request.user.has_group_cached('Coordenador de Pesquisa'):
            projetos_em_execucao = projetos_em_execucao.filter(vinculo_supervisor=vinculo)
        if projetos_em_execucao.exists():
            contador_meta_expira_7_dias = []
            contador_meta_expira_hoje = []
            contador_projeto_finaliza_15_dias = []
            contador_projeto_finaliza_hoje = []
            for projeto in projetos_em_execucao:
                if projeto.tem_metas_vencendo_em(dias=7):
                    contador_meta_expira_7_dias.append(projeto.id)
                if projeto.tem_metas_vencendo_em():
                    contador_meta_expira_hoje.append(projeto.id)
                if projeto.tem_data_fim_execucao_em(dias=15):
                    contador_projeto_finaliza_15_dias.append(projeto.id)
                if projeto.tem_data_fim_execucao_em():
                    contador_projeto_finaliza_hoje.append(projeto.id)

            if contador_meta_expira_7_dias:
                valor = len(contador_meta_expira_7_dias)
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Projeto{pluralize(valor)}',
                        subtitulo=f'Com Meta{pluralize(valor)} expirando nos próximos 7 dias',
                        qtd=valor,
                        url=f'/pesquisa/projetos_em_execucao/?ids={contador_meta_expira_7_dias}',
                    )
                )
            if contador_meta_expira_hoje:
                valor = len(contador_meta_expira_hoje)
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Projeto{pluralize(valor)}',
                        subtitulo=f'Com Meta{pluralize(valor)} expirando hoje',
                        qtd=valor,
                        url=f'/pesquisa/projetos_em_execucao/?ids={contador_meta_expira_hoje}',
                    )
                )
            if contador_projeto_finaliza_15_dias:
                valor = len(contador_projeto_finaliza_15_dias)
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Projeto{pluralize(valor)}',
                        subtitulo='Com data de finalização expirando nos próximos 15 dias',
                        qtd=valor,
                        url=f'/pesquisa/projetos_em_execucao/?ids={contador_projeto_finaliza_15_dias}',
                    )
                )
            if contador_projeto_finaliza_hoje:
                valor = len(contador_projeto_finaliza_hoje)
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Projeto{pluralize(valor)}',
                        subtitulo='Com data de finalização prevista para hoje',
                        qtd=valor,
                        url=f'/pesquisa/projetos_em_execucao/?ids={contador_projeto_finaliza_hoje}',
                    )
                )

    return quadro


@rtr()
@permission_required('pesquisa.view_edital')
def edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    tem_formato_completo = edital.tem_formato_completo()

    if edital.tipo_edital == edital.PESQUISA:
        title = f'{edital.titulo} - Edital de Pesquisa'
    elif edital.tipo_edital == edital.INOVACAO:
        title = f'{edital.titulo} - Edital de Inovação'
    elif edital.tipo_edital == edital.PESQUISA_INOVACAO_CONTINUO:
        title = f'{edital.titulo} - Edital de Pesquisa e Inovação - Fluxo Contínuo'

    if edital.forma_selecao == Edital.GERAL:
        titulo_box_plano_oferta_por_campus = 'Campi Participantes'
    else:
        titulo_box_plano_oferta_por_campus = 'Plano de Oferta por Campus'

    FormClass = edital.get_form()
    form = FormClass(request.POST or None)
    if form.is_valid() and not request.user.has_perm('pesquisa.pode_ver_config_edital', ignore_superuser=True):
        form.save()
        return httprr(f'/pesquisa/edital/{edital.id}/?tab=4', 'Critérios adicionados com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def meus_projetos(request):
    title = 'Meus Projetos'
    vinculo = request.user.get_vinculo()
    participacoes = Participacao.objects.filter(vinculo_pessoa=vinculo, ativo=True).order_by('-projeto__id', 'projeto__vinculo_coordenador')
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
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def pre_avaliacao(request, tipo_edital):
    selecionar_avaliadores = None
    title = 'Editais em Avaliação'
    if tipo_edital == 'selecionar_avaliadores':
        selecionar_avaliadores = True
        hoje = datetime.datetime.now()
        editais = Edital.objects.filter(divulgacao_selecao__gt=hoje) | Edital.objects.filter(
            tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO, fim_inscricoes__gt=hoje
        )
        editais = editais.exclude(formato=Edital.FORMATO_SIMPLIFICADO)
        if not request.user.has_group_cached('Diretor de Pesquisa'):
            if request.user.has_group_cached('Coordenador de Pesquisa') and not request.user.has_group_cached(
                'Pré-Avaliador Sistêmico de Projetos de Pesquisa'
            ):
                editais = editais.exclude(forma_selecao=Edital.GERAL)
            elif request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Pesquisa') and not request.user.has_group_cached(
                'Coordenador de Pesquisa'
            ):
                editais = editais.exclude(forma_selecao=Edital.CAMPUS)
    else:
        editais = Edital.objects.em_pre_avaliacao()
        if not request.user.has_group_cached('Diretor de Pesquisa'):
            if request.user.has_group_cached('Coordenador de Pesquisa') and not request.user.has_group_cached(
                'Pré-Avaliador Sistêmico de Projetos de Pesquisa'
            ):
                editais = editais.exclude(forma_selecao=Edital.GERAL)
            elif request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Pesquisa') and not request.user.has_group_cached(
                'Coordenador de Pesquisa'
            ):
                editais = editais.exclude(forma_selecao=Edital.CAMPUS)
    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_projeto')
def avaliacao(request):
    title = 'Editais em Avaliação'
    editais_com_indicacao = AvaliadorIndicado.objects.filter(vinculo=request.user.get_vinculo())
    editais = Edital.objects.em_selecao().filter(pk__in=editais_com_indicacao.values_list('projeto__edital', flat=True))
    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_projeto')
def projetos_especial_pre_aprovados(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if not edital.is_periodo_selecao():
        raise PermissionDenied('O edital está fora do período de avaliação.')
    title = f'Seleção de Projetos - {edital.titulo}'
    vinculo = request.user.get_vinculo()
    projetos = Projeto.objects.filter(avaliadorindicado__vinculo=vinculo, edital=edital, pre_aprovado=True).order_by(
        '-pontuacao_total', '-pontuacao_curriculo'
    )
    lista_projetos = []
    for projeto in projetos:
        if AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=vinculo, rejeitado=True).exists():
            automaticamente = AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=vinculo, rejeitado=True)[0].rejeitado_automaticamente
            lista_projetos.append([projeto, True, automaticamente])
        else:
            lista_projetos.append([projeto, False, False])
    if request.user.eh_servidor:
        servidor_apto = edital.servidor_pode_avaliar_projeto(request.user)
    else:
        servidor_apto = True
    is_gerente_sistemico = request.user.has_group_cached('Diretor de Pesquisa')

    return locals()


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def projetos_nao_avaliados(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)

    if not edital.is_periodo_pre_selecao():
        raise PermissionDenied
    # O Coordenador de Pesquisa é local, inclusive o lotado na Reitoria; o mesmo recorte vale em pre_selecionar (#17570).
    institucional = request.user.has_group_cached(GRUPOS_PRE_SELECAO_INSTITUCIONAIS)
    if edital.forma_selecao == Edital.GERAL and request.user.has_group_cached('Coordenador de Pesquisa') and not institucional:
        raise PermissionDenied
    projetos = Projeto.objects.filter(edital=edital, data_conclusao_planejamento__isnull=False).order_by('titulo')

    uos = edital.get_uos_edital_pesquisa()
    if not institucional:
        uo = get_uo(request.user)
        projetos = projetos.filter(uo=uo)
        uos = [uo]
    for uo in uos:
        tem_oferta = edital.bolsadisponivel_set.filter(uo=uo).count()
        if tem_oferta:
            oferta = edital.bolsadisponivel_set.get(uo=uo)
            uo.qtd_enviados = edital.num_total_projetos_enviados(uo)
            uo.qtd_pre_aprovados = edital.num_total_projetos_pre_aprovados(uo)
            uo.qtd_nao_pre_aprovados = uo.qtd_enviados - uo.qtd_pre_aprovados
            uo.num_maximo_ic = oferta.num_maximo_ic
            uo.num_maximo_pesquisador = oferta.num_maximo_pesquisador

    if edital.forma_selecao == Edital.GERAL:
        enviados = edital.num_total_projetos_enviados()
        pre_aprovados = edital.num_total_projetos_pre_aprovados()
        nao_pre_aprovados = enviados - pre_aprovados
        num_maximo_ic = edital.qtd_bolsa_alunos
        num_maximo_pesquisador = edital.qtd_bolsa_servidores

    form = CampusForm(request.POST or None)
    if form.is_valid():
        if form.cleaned_data.get('uo'):
            uo_selecionado = form.cleaned_data.get('uo')
            projetos = projetos.filter(uo=uo_selecionado)

    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editais_abertos(request):
    title = 'Editais de Pesquisa e de Inovação com Inscrições Abertas'
    tem_lattes = True
    pode_clonar_projeto = False
    editais = Edital.disponiveis_para_inscricoes()
    instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    vinculo = request.user.get_vinculo()
    if request.user.has_group_cached('Diretor de Pesquisa'):
        gerente_especial_sistemico = True
    eh_servidor = None
    if vinculo.eh_servidor():
        eh_servidor = True
    if not CurriculoVittaeLattes.objects.filter(vinculo=vinculo).exists():
        tem_lattes = False
    if eh_servidor and tem_lattes:
        pode_clonar_projeto = Projeto.objects.filter(vinculo_coordenador=vinculo).exists()

    return locals()


def _papeis_pesquisa_no_projeto(user: User, projeto: Projeto) -> tuple[bool, bool]:
    """`(is_pre_avaliador, is_coordenador_pesquisa)` das telas do projeto, com o recorte de campus.

    O Pré-Avaliador Sistêmico e o Diretor de Pesquisa valem para qualquer campus; o Coordenador de Pesquisa só
    para o próprio (#17571). O Assessor de Pesquisa fica de fora: entra por `is_assessor_pesquisa`, sem dados bancários.
    """
    do_campus = projeto.is_coordenador_pesquisa_campus_projeto(user)
    is_pre_avaliador = do_campus or user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Pesquisa')
    return is_pre_avaliador, is_pre_avaliador or user.has_group_cached('Diretor de Pesquisa')


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto, pesquisa.pode_acessar_lista_projetos')
def projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    uo_do_usuario = get_uo(usuario_logado)
    tem_movimentacao = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).exists()
    title = f'Projeto de {projeto.edital.get_tipo_edital_display()}'
    participantes = projeto.participacao_set.all().select_related('vinculo_pessoa')
    registro_conclusao = projeto.get_registro_conclusao()
    periodo = projeto.get_periodo(registro_conclusao)
    status = projeto.get_status(periodo, registro_conclusao)
    status_pre_selecao = projeto.get_pre_selecionado()
    status_selecao = projeto.get_selecionado()
    tem_formato_completo = projeto.edital.tem_formato_completo()
    vinculo = usuario_logado.get_vinculo()
    coordenador_eh_aluno = vinculo.eh_aluno()
    is_gerente_sistemico = usuario_logado.has_perm('pesquisa.tem_acesso_sistemico')
    is_coordenador = projeto.is_responsavel(usuario_logado)
    is_gerenciador_projeto = projeto.is_gerenciador_projeto(usuario_logado)
    mesmo_campus = projeto.uo == uo_do_usuario
    is_pre_avaliador, is_coordenador_pesquisa = _papeis_pesquisa_no_projeto(usuario_logado, projeto)
    pode_inativar_projeto = status == Projeto.STATUS_EM_EXECUCAO and (
        (usuario_logado.has_perm('pesquisa.pode_gerenciar_edital') and (mesmo_campus)) or projeto.is_gerente_sistemico(usuario_logado)
    )
    pode_reativar_projeto = projeto.inativado and (
        (usuario_logado.has_perm('pesquisa.pode_gerenciar_edital') and (mesmo_campus)) or projeto.is_gerente_sistemico(usuario_logado)
    )
    eh_somente_leitura = projeto.eh_somente_leitura()
    eh_participante = projeto.eh_participante(usuario_logado)
    tem_atividades_cadastradas = projeto.tem_atividades_cadastradas()
    pode_editar_equipe_propi = projeto.pode_editar_equipe_propi(usuario_logado)

    eh_supervisor = (is_coordenador_pesquisa and mesmo_campus) or is_gerente_sistemico
    is_coordenador_edu = usuario_logado.has_perm('pesquisa.pode_acessar_lista_projetos')
    is_assessor_pesquisa = usuario_logado.has_group_cached('Assessor de Pesquisa')
    pode_acessar_certificado = status in (Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO)
    pode_ver_dados_bancarios = is_gerente_sistemico or is_coordenador or is_pre_avaliador
    divulgado = Projeto.objects.filter(id=projeto_id, edital__divulgacao_selecao__lte=datetime.datetime.now())
    edital_projeto = Edital.objects.get(pk=projeto.edital.id)
    is_avaliador_do_projeto = projeto.is_avaliador(usuario_logado)
    eh_avaliador_em_tempo_avaliacao = is_avaliador_do_projeto and projeto.projeto_em_avaliacao()

    tem_cancelamento = ProjetoCancelado.objects.filter(projeto=projeto)
    tem_cancelamento_aceito = tem_cancelamento.filter(parecer_favoravel=True).exists()
    eh_coordenador_servidor = projeto.vinculo_coordenador.eh_servidor()
    eh_responsavel_anuencia = projeto.responsavel_anuencia and vinculo.eh_servidor() and vinculo.relacionamento == projeto.responsavel_anuencia
    if not (
        is_coordenador_edu
        or is_coordenador_pesquisa
        or is_coordenador
        or is_gerente_sistemico
        or eh_avaliador_em_tempo_avaliacao
        or is_assessor_pesquisa
        or (is_pre_avaliador and mesmo_campus)
        or eh_participante
        or projeto.vinculo_supervisor == vinculo
        or eh_responsavel_anuencia
    ):
        raise PermissionDenied

    if is_coordenador_edu and not request.user.has_perm('pesquisa.pode_visualizar_projeto') and get_uo(request.user) != projeto.uo:
        raise PermissionDenied

    edicao_inscricao = False
    if is_gerente_sistemico or (is_coordenador and status == Projeto.STATUS_EM_INSCRICAO):
        edicao_inscricao = True

    edicao_inscricao_execucao = False
    if is_gerente_sistemico or (is_coordenador and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO)):
        edicao_inscricao_execucao = True

    if eh_participante and not is_coordenador:
        pode_editar = False
        edicao_inscricao = False
        edicao_inscricao_execucao = False

    itens_com_recurso = ItemAvaliacao.objects.filter(avaliacao__projeto=projeto).exclude(recurso=None).order_by('criterio_avaliacao')
    resumo_recursos, geral_planejado, geral_executado = _resumo_recursos_projeto(projeto)

    devolucao = None
    if (
        ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).exists()
        and status == projeto.STATUS_EM_INSCRICAO
        and ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).latest('id').situacao == ProjetoHistoricoDeEnvio.DEVOLVIDO
    ):
        devolucao = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto).latest('id')

    parametros_pontuacao = projeto.parametroprojeto_set.filter(parametro_edital__valor_parametro__gt=0.0).order_by(
        'parametro_edital__parametro__codigo'
    )
    memorias_de_calculo = projeto.itemmemoriacalculo_set.all().select_related('despesa')
    tem_pendencias = projeto.tem_pendencias() or not registro_conclusao or (registro_conclusao and not registro_conclusao.dt_avaliacao)
    pode_avaliar_projeto = projeto.pode_avaliar_projeto(vinculo)
    edital_exige_anuencia = edital_projeto.exige_anuencia
    dentro_prazo_anuencia = projeto.edital.get_data_limite_anuencia() > datetime.datetime.now()
    anuencia_em = projeto.anuencia_registrada_em
    pode_alterar_responsavel_anuencia = projeto.pode_alterar_chefia_imediata(usuario_logado)
    pode_ver_membros_nos_anexos = not (projeto.is_avaliador() and projeto.projeto_em_avaliacao())
    registros_frequencia = (
        RegistroFrequencia.objects.filter(projeto=projeto)
        .select_related('cadastrada_por', 'cadastrada_por__user', 'validada_por', 'validada_por__user')
        .order_by('-data', 'cadastrada_por')
    )
    form_frequencias = GerarListaFrequenciaForm(request.POST or None, projeto=projeto)
    tem_participante_afastado = projeto.tem_participante_afastado()
    pode_classificar_trl = projeto.edital.utiliza_metodologia_trl and (is_coordenador or is_gerente_sistemico)
    registros_diario = projeto.registrodiariobordo_set.all()
    if form_frequencias.is_valid():
        registros_frequencia = _filtrar_registros_frequencia(registros_frequencia, form_frequencias.cleaned_data)
    return locals()


def _resumo_recursos_projeto(projeto: Projeto) -> tuple[list[dict[str, object]], Decimal, Decimal]:
    """Resumo do plano de aplicação por despesa do edital, com o total distribuído e o executado."""
    resumo_recursos = []
    geral_planejado = Decimal(0)
    geral_executado = Decimal(0)
    for recurso in projeto.edital.recurso_set.filter():
        despesa = recurso.despesa
        valor_reservado = recurso.valor
        valor_distribuido = Decimal(0)
        valor_executado = Decimal(0)
        for item in projeto.itemmemoriacalculo_set.filter(despesa=despesa):
            valor_distribuido += item.get_subtotal()
            valor_executado += item.get_total_executado()
        valor_planejado = sum(projeto.desembolso_set.filter(item__despesa=despesa).values_list('valor', flat=True))
        valor_disponivel_orcamento = valor_distribuido - valor_planejado

        geral_planejado = geral_planejado + valor_distribuido
        geral_executado = geral_executado + valor_executado

        resumo_recursos.append(
            {
                'valor_reservado': valor_reservado,
                'despesa': despesa,
                'valor_distribuido': valor_distribuido,
                'valor_planejado': valor_planejado,
                'valor_disponivel_orcamento': valor_disponivel_orcamento,
                'valor_executado': valor_executado,
                'valor_disponivel_execucao': valor_planejado - valor_executado,
                'cor_valor_distribuido': 'false' if valor_distribuido > valor_reservado else 'true',
                'cor_valor_disponivel_orcamento': 'False' if valor_disponivel_orcamento < 0 else 'True',
            }
        )
    return resumo_recursos, geral_planejado, geral_executado


def _filtrar_registros_frequencia(registros_frequencia: QuerySet, filtros: dict[str, object]) -> QuerySet:
    """Aplica os filtros do formulário de frequências da aba do projeto."""
    if filtros.get('data_inicio'):
        registros_frequencia = registros_frequencia.filter(data__gte=filtros['data_inicio'])
    if filtros.get('data_termino'):
        registros_frequencia = registros_frequencia.filter(data__lte=filtros['data_termino'])
    if filtros.get('participante'):
        registros_frequencia = registros_frequencia.filter(cadastrada_por=filtros['participante'])
    if filtros.get('situacao') == 'Pendentes':
        return registros_frequencia.filter(validada_por=None)
    if filtros.get('situacao'):
        return registros_frequencia.exclude(validada_por=None)
    return registros_frequencia


@documento(enumerar_paginas=False)
@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def imprimir_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    is_gerenciador_projeto = projeto.is_gerenciador_projeto(usuario_logado)
    is_pre_avaliador = projeto.pode_pre_selecionar(usuario_logado)  # Coordenador de Pesquisa só do próprio campus (#17571)
    is_avaliador = projeto.is_avaliador(usuario_logado)
    avaliador_pode_imprimir = is_avaliador and projeto.projeto_em_avaliacao()
    pode_visualizar_equipe = projeto.avaliador_pode_visualizar()

    if is_gerenciador_projeto or is_pre_avaliador or avaliador_pode_imprimir or usuario_logado.has_group_cached('Diretor de Pesquisa'):
        cronograma = projeto.get_cronograma_desembolso_como_lista()
        plano_aplicacao = projeto.get_plano_aplicacao_como_dict()
        edital_projeto = Edital.objects.get(pk=projeto.edital.id)
        tem_formato_completo = edital_projeto.tem_formato_completo()

        total_geral = projeto.itemmemoriacalculo_set.extra({'total': 'SUM(valor_unitario*qtd)'}).values('total')[0]['total']
        metas = projeto.get_metas()
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
        html = 'html' in request.GET
        return locals()
    else:
        raise PermissionDenied


@documento(enumerar_paginas=False)
@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def relatorio_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    is_gerenciador_projeto = projeto.is_gerenciador_projeto(usuario_logado)
    is_pre_avaliador = projeto.pode_pre_selecionar(usuario_logado)  # Coordenador de Pesquisa só do próprio campus (#17571)
    is_avaliador = projeto.is_avaliador(usuario_logado)
    avaliador_pode_imprimir = is_avaliador and projeto.projeto_em_avaliacao()
    pode_visualizar_equipe = projeto.avaliador_pode_visualizar()
    if is_gerenciador_projeto or is_pre_avaliador or avaliador_pode_imprimir or usuario_logado.has_group_cached('Diretor de Pesquisa'):
        cronograma = projeto.get_cronograma_desembolso_como_lista()
        valor_financiamento_projeto = (
            RegistroGasto.objects.filter(item__projeto__id=projeto_id)
            .extra(select={'total': 'SUM(pesquisa_registrogasto.qtd*pesquisa_registrogasto.valor_unitario)'})
            .values('total')[0]['total']
        )
        tem_formato_completo = projeto.edital.tem_formato_completo()
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
        html = 'html' in request.GET
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def memoria_calculo(request, projeto_id):
    title = 'Memória de Cálculo'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    url = f'/pesquisa/projeto/{projeto.id:d}/?tab=plano_aplicacao'
    tem_permissao(request, projeto, pode_auxiliar=True, pode_copein=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        editavel = not projeto.data_pre_avaliacao and request.user.has_group_cached(['Servidor', 'Aposentado'])
        if editavel:
            editavel = Participacao.objects.filter(vinculo_pessoa=request.user.get_vinculo(), responsavel=True).count() > 0
        if request.user.has_group_cached('Diretor de Pesquisa'):
            editavel = True

        is_operador = True

        item = None
        is_coordenador = projeto.is_coordenador(request.user)
        is_avaliador = projeto.is_avaliador(request.user)

        if 'edit_id' in request.GET:
            item = get_object_or_404(ItemMemoriaCalculo, pk=request.GET['edit_id'], projeto=projeto)
            if not (item.pode_editar_e_remover_memoria_calculo() and not projeto.eh_somente_leitura()):
                raise PermissionDenied

        if 'del_id' in request.GET:
            item = get_object_or_404(ItemMemoriaCalculo, pk=request.GET['del_id'], projeto=projeto)
            if not (item.pode_editar_e_remover_memoria_calculo() and not projeto.eh_somente_leitura()):
                raise PermissionDenied
            item.delete()
            item = None
            return httprr(url, 'Item removido com sucesso.')

        if request.method == 'POST':
            form = ItemMemoriaCalculoForm(data=request.POST, instance=item)
            if form.is_valid():
                o = form.save(False)
                o.projeto = projeto
                o.save()
                if item:
                    return httprr(url, 'Item editado com sucesso.')
                else:
                    return httprr('..', 'Item adicionado com sucesso.')
        else:
            form = ItemMemoriaCalculoForm(instance=item)
        form.fields['despesa'].queryset = projeto.edital.get_elementos_despesa()

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def registro_conclusao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_registrar_conclusao():
        title = 'Conclusão do Projeto'
        registro = projeto.get_registro_conclusao()
        form = RegistroConclusaoProjetoForm(data=request.POST or None, instance=registro)
        if form.is_valid():
            registro = form.save(False)
            registro.projeto = projeto
            registro.save()
            return httprr('..', 'Conclusão do projeto registrada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


def _pode_gravar_gasto(projeto: Projeto) -> bool:
    """Mesma condição do botão "Gerenciar Gasto" (projeto.html) e do ``registro_gasto`` do projetos (#17577)."""
    return bool((projeto.pode_editar_gasto() and not projeto.eh_somente_leitura()) or projeto.is_gerente_sistemico())


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def registro_gasto(request: HttpRequest, item_id: int) -> dict | HttpResponse:
    title = 'Gastos Registrados'
    desembolso = get_object_or_404(Desembolso, pk=item_id)
    projeto = desembolso.projeto
    # Coordenador de Pesquisa e avaliador só visualizam; quem grava é a equipe ou o Diretor (#17577).
    is_coordenador = _pode_gravar_gasto(projeto)
    pode_visualizar = (
        is_coordenador
        or projeto.is_coordenador(request.user)
        or projeto.is_coordenador_pesquisa_campus_projeto(request.user)
        or projeto.is_avaliador(request.user)
    )

    registro = None
    edicao = False
    if not pode_visualizar:
        return httprr('..', 'Apenas o Coordenador do Projeto e o Coordenador de Pesquisa do campus tem acesso a essa página.', 'alert')
    if not is_coordenador and (request.method == 'POST' or 'registro_id' in request.GET or 'editar_registro_id' in request.GET):
        raise PermissionDenied

    if request.method == 'GET' and 'registro_id' in request.GET:
        registro = get_object_or_404(RegistroGasto, pk=request.GET['registro_id'], desembolso=desembolso)
        if not registro.pode_editar_remover_registro_gasto():
            return httprr(
                f'/pesquisa/projeto/{desembolso.projeto.id}/?tab=plano_desembolso', 'Não é possível excluir um registro de gasto avaliado.', 'alert'
            )
        else:
            registro.delete()
            return httprr('.', 'Registro excluído com sucesso.')

    if 'editar_registro_id' in request.GET:
        edicao = True
        registro = get_object_or_404(RegistroGasto, pk=request.GET['editar_registro_id'], desembolso=desembolso)
        if not registro.pode_editar_remover_registro_gasto():
            return httprr(
                f'/pesquisa/projeto/{desembolso.projeto.id}/?tab=plano_desembolso', 'Não é possível editar um registro de gasto avaliado.', 'alert'
            )

    if request.method == 'POST':
        form = RegistroGastoForm(request.POST, request.FILES, instance=registro)
        if form.is_valid():
            registro_gasto = form.save(False)
            registro_gasto.desembolso = desembolso
            registro_gasto.dt_avaliacao = None
            registro_gasto.avaliador = None
            registro_gasto.justificativa_reprovacao = None
            registro_gasto.save()
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def registro_execucao_etapa(request, etapa_id):
    title = 'Registro de  Execução de Atividade'
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    instance = etapa.get_registro_execucao()
    if instance and instance.aprovado:
        raise PermissionDenied
    if not projeto.eh_somente_leitura() and etapa.pode_registrar_execucao():
        if request.method == 'POST':
            form = RegistroExecucaoEtapaForm(request.POST, request.FILES, instance=instance, etapa=etapa)
            if form.is_valid():
                try:
                    registro_execucao_etapa = form.save(False)
                    registro_execucao_etapa.etapa = etapa
                    registro_execucao_etapa.dt_avaliacao = None
                    registro_execucao_etapa.avaliador = None
                    registro_execucao_etapa.justificativa_reprovacao = None
                    registro_execucao_etapa.save()
                    return httprr('..', 'Execução registrada com sucesso.')
                except IntegrityError:
                    return httprr('..', 'O registro da execução já foi cadastrado.', tag='error', close_popup=True)
        else:
            if instance:
                form = RegistroExecucaoEtapaForm(instance=instance)
            else:
                initial = {'inicio_execucao': etapa.inicio_execucao, 'fim_execucao': etapa.fim_execucao, 'etapa': etapa}
                form = RegistroExecucaoEtapaForm(initial=initial)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projetos_em_monitoramento')
def validar_execucao_etapa(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Validar Execução'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    status = projeto.get_status()
    vinculo = request.user.get_vinculo()
    pode_validar = False
    eh_membro = projeto.eh_participante(request.user)
    eh_avaliador = request.user.has_group_cached(['Coordenador de Pesquisa', 'Supervisor de Projetos de Pesquisa'])
    eh_o_supervisor = projeto.vinculo_supervisor == vinculo
    if not eh_membro and eh_avaliador and eh_o_supervisor:
        pode_validar = True
    is_gerente_sistemico = request.user.has_group_cached('Diretor de Pesquisa')
    is_coordenador = Participacao.objects.filter(projeto__id=projeto_id, vinculo_pessoa=vinculo, responsavel=True).exists() or is_gerente_sistemico
    if pode_validar:
        if request.method == 'GET' and 'registro_id' in request.GET:
            registro = get_object_or_404(RegistroExecucaoEtapa, pk=request.GET['registro_id'], etapa__meta__projeto=projeto)
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = True
            registro.save()
            return httprr(f'/pesquisa/validar_execucao_etapa/{projeto.pk:d}/?tab=metas', 'Execução de atividade validada com sucesso.')

        elif request.method == 'GET' and 'item_id' in request.GET:
            registro = get_object_or_404(RegistroGasto, pk=request.GET['item_id'], item__projeto=projeto)
            registro.dt_avaliacao = datetime.date.today()
            registro.avaliador = request.user.get_relacionamento()
            registro.aprovado = True
            registro.save()
            return httprr(f'/pesquisa/validar_execucao_etapa/{projeto.pk:d}/?tab=gastos', 'Gasto validado com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.pode_realizar_monitoramento_projeto')
def reprovar_execucao_etapa(request, registroetapa_id):
    title = 'Justificar Não Aprovação da Atividade'
    registro = get_object_or_404(RegistroExecucaoEtapa, pk=registroetapa_id)
    projeto = registro.etapa.meta.projeto
    if projeto.vinculo_supervisor == request.user.get_vinculo() or request.user.has_group_cached('Diretor de Pesquisa'):
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
@permission_required('pesquisa.pode_realizar_monitoramento_projeto')
def reprovar_execucao_gasto(request, gasto_id):
    title = 'Justificar Não Aprovação do Gasto'
    registro = get_object_or_404(RegistroGasto, pk=gasto_id)
    projeto = registro.desembolso.projeto
    if projeto.vinculo_supervisor == request.user.get_vinculo() or request.user.has_group_cached('Diretor de Pesquisa'):
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_participante_servidor(request, projeto_id):
    title = 'Adicionar Participante'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_group_cached('Coordenador de Pesquisa'):
        tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
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
                if projeto.edital.termo_compromisso_servidor:
                    titulo = '[SUAP] Pesquisa: Termo de Compromisso do Servidor'
                    texto = (
                        '<h1>Pesquisa</h1>'
                        '<h2>Termo de Compromisso do Servidor</h2>'
                        f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('servidor').get_vinculo()])

                return httprr('..', 'Participante adicionado com sucesso.')
        else:
            form = ParticipacaoServidorForm()
            form.projeto = projeto

        return locals()
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_participante_servidor(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_group_cached('Coordenador de Pesquisa'):
        tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        participacao = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
        title = f'Editar Participação de {participacao.vinculo_pessoa.pessoa.nome}'
        alterou = False
        form = ParticipacaoServidorForm(request.POST or None, instance=participacao)
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
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_participante_aluno(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_group_cached('Coordenador de Pesquisa'):
        tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        participacao = get_object_or_404(Participacao, pk=participacao_id, projeto=projeto)
        title = f'Editar Participação: {participacao.get_nome()}'
        form = ParticipacaoAlunoForm(request.POST or None, instance=participacao, projeto=projeto)
        alterou = False
        adicionou_evento = False
        if form.is_valid():
            o = form.save(False)
            if participacao.vinculo == TipoVinculo.BOLSISTA:
                participacao.bolsa_concedida = True

            if not participacao.vinculo_pessoa and not form.cleaned_data.get('indicar_pessoa_posteriormente') and form.cleaned_data.get('aluno'):
                participacao.pessoa = form.cleaned_data.get('aluno').pessoa_fisica
                participacao.vinculo_pessoa = Vinculo.objects.get(
                    id_relacionamento=form.cleaned_data.get('aluno').id, tipo_relacionamento__model='aluno'
                )
                participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=form.cleaned_data.get('data'))
                adicionou_evento = True
            elif participacao.vinculo_pessoa and not HistoricoEquipe.objects.filter(participante=participacao, projeto=projeto).exists():
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def alterar_coordenador(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    title = 'Alterar Coordenador'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_alterar_coordenador(request.user):
        raise PermissionDenied
    participacao_anterior = Participacao.objects.get(projeto__id=projeto.pk, responsavel=True)
    participacoes = Participacao.objects.filter(projeto__id=projeto.pk, responsavel=False, ativo=True)
    form = AlterarCoordenadorForm(data=request.POST or None, projeto=projeto)
    if form.is_valid():
        participacao = form.cleaned_data['participacao']
        participacao_anterior.responsavel = False
        participacao_anterior.save()
        participacao_anterior.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_DESISTITUIDO)
        participacao.responsavel = True
        participacao.save()
        participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_SUBSTITUIDO)
        projeto.vinculo_coordenador = participacao.vinculo_pessoa
        projeto.save()
        return httprr('..', 'Coordenador alterado com sucesso.')
    return locals()


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_participante_aluno(request, projeto_id):
    title = 'Adicionar Aluno'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_group_cached('Coordenador de Pesquisa'):
        tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = ParticipacaoAlunoForm(data=request.POST, projeto=projeto)
            form.projeto = projeto
            if form.is_valid():
                participacao = form.save(False)
                participacao.projeto = projeto
                if participacao.vinculo == TipoVinculo.BOLSISTA:
                    participacao.bolsa_concedida = True
                if form.cleaned_data.get('aluno'):
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
                if projeto.edital.termo_compromisso_aluno and form.cleaned_data.get('aluno'):
                    titulo = '[SUAP] Pesquisa: Termo de Compromisso do Aluno'
                    texto = (
                        '<h1>Pesquisa</h1>'
                        '<h2>Termo de Compromisso do Aluno</h2>'
                        f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('aluno').get_vinculo()])

                return httprr('..', 'Participante adicionado com sucesso.')
        else:
            form = ParticipacaoAlunoForm(projeto=projeto)
            form.projeto = projeto

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def pre_aprovar(request, projeto_id):
    return pre_selecionar(request, projeto_id, rejeitar=False)


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def pre_rejeitar(request, projeto_id):
    return pre_selecionar(request, projeto_id, rejeitar=True)


@rtr()
@permission_required('pesquisa.pode_avaliar_projeto')
def avaliar(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Avaliar Projeto - {projeto.titulo}'
    vinculo = request.user.get_vinculo()
    if projeto.pode_avaliar_projeto(vinculo):
        avaliador = request.user.get_profile().pessoafisica
        # Atualiza a pontuação do currículo lattes, este normaliza e atualiza a pontuação total do projeto.
        if not projeto.pontuacao_curriculo_normalizado and projeto.edital.peso_avaliacao_lattes_coordenador:
            projeto.atualizar_pontuacao_curriculo_lattes()
        if not projeto.pontuacao_grupo_pesquisa_normalizado and projeto.edital.peso_avaliacao_grupo_pesquisa:
            projeto.atualizar_pontuacao_grupo_pesquisa()

        try:
            avaliacao = Avaliacao.objects.get(projeto=projeto, vinculo=vinculo)
        except Exception:
            avaliacao = None
        form = AvaliacaoFormFactory(request, avaliacao, projeto, avaliador, vinculo)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/', 'Projeto avaliado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def visualizar_ficha_avaliacao(request, avaliacao_id):
    title = 'Detalhamento da Avaliação do Projeto '
    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    itens_avaliacao = ItemAvaliacao.objects.filter(avaliacao=avaliacao).order_by('-pontuacao')

    return locals()


@rtr()
@permission_required('pesquisa.pode_visualizar_projetos_em_monitoramento')
def projetos_em_execucao(request):
    title = 'Monitoramento'
    hoje = datetime.datetime.now()
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos = (
        Projeto.objects.filter(aprovado=True, inativado=False, registroconclusaoprojeto__dt_avaliacao__isnull=True)
        .filter(Q(edital__divulgacao_selecao__lte=hoje) | Q(edital__formato=Edital.FORMATO_SIMPLIFICADO))
        .exclude(id__in=projetos_cancelados)
        .order_by('-edital__divulgacao_selecao')
    )

    if not request.user.has_group_cached(['Diretor de Pesquisa', 'Supervisor de Projetos de Pesquisa', 'Auditor']):
        projetos = projetos.exclude(~Q(uo=get_uo(request.user)))
    ano = request.GET.get('ano')
    num_page = 20
    form = BuscaProjetoForm(data=request.GET or None, request=request, ano=ano)
    if 'ids' in request.GET:
        try:
            projetos = projetos.filter(id__in=str(request.GET.get('ids')).strip('[]').split(','))
        except Exception:
            pass

    if form.is_valid():
        if form.cleaned_data.get('uo'):
            projetos = projetos.filter(uo=form.cleaned_data['uo'])

        if form.cleaned_data.get('ano'):
            projetos = projetos.filter(edital__inicio_inscricoes__year=form.cleaned_data['ano'])

        if form.cleaned_data.get('edital'):
            projetos = projetos.filter(edital=form.cleaned_data['edital'])

        if form.cleaned_data.get('por_mim'):
            projetos = projetos.filter(vinculo_supervisor=request.user.get_vinculo())

        if form.cleaned_data.get('paginacao'):
            num_page = form.cleaned_data.get('paginacao')

        if form.cleaned_data.get('palavra_chave'):
            projetos = projetos.filter(
                Q(titulo__icontains=form.cleaned_data['palavra_chave']) | Q(edital__titulo__icontains=form.cleaned_data['palavra_chave'])
            )

    vinculo = request.user.get_vinculo()
    if request.user.has_group_cached('Supervisor de Projetos de Pesquisa') and not request.user.has_group_cached(
        ['Diretor de Pesquisa', 'Coordenador de Pesquisa']
    ):
        projetos = projetos.filter(vinculo_supervisor=vinculo)
    else:
        projetos = projetos | projetos.filter(vinculo_supervisor=vinculo)

    if list(request.GET.keys()) and len(list(request.GET.keys())) == 1:
        projetos = projetos.filter(uo=get_uo(request.user))

    return locals()


def _exigir_gerencia_participacao(request: HttpRequest, projeto: Projeto) -> None:
    """Exige o que a aba "Equipe" exige para Encerrar/Ativar participante (``projeto.html``).

    O Coordenador de Pesquisa só gerencia projeto do próprio campus; o Diretor, qualquer um.
    """
    if not (
        projeto.pode_editar_equipe_propi(request.user)
        and projeto.pode_editar_inscricao_execucao()
        and not projeto.eh_somente_leitura()
        and projeto.pode_gerenciar_participacao()
    ):
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_gerenciar_equipe_projeto')
def remover_participante(request, participacao_id):
    title = 'Inativar Participante'
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    _exigir_gerencia_participacao(request, projeto)
    form = DataInativacaoForm(request.POST or None, projeto=projeto, participacao=participacao)
    if form.is_valid():
        data_escolhida = form.cleaned_data.get('data')
        participacao.ativo = False
        participacao.data_inativacao = data_escolhida
        participacao.save()
        participacao.adicionar_registro_historico_equipe(
            HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_evento=data_escolhida, obs=form.cleaned_data.get('justificativa')
        )
        if projeto.auxiliar and projeto.auxiliar == participacao.vinculo_pessoa:
            projeto.auxiliar = None
            projeto.save()
        return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=equipe', 'Participação encerrada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_equipe_projeto')
def ativar_participante(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participacao.projeto
    _exigir_gerencia_participacao(request, projeto)

    if participacao.vinculo == TipoVinculo.BOLSISTA:
        mensagem_alerta = projeto.mensagem_restricao_adicionar_membro(categoria=Participacao.SERVIDOR, bolsista=True)
        if participacao.is_servidor() and mensagem_alerta:
            return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=equipe', mensagem_alerta, tag='error')
        mensagem_alerta = projeto.mensagem_restricao_adicionar_membro(categoria=Participacao.ALUNO, bolsista=True)
        if not participacao.is_servidor() and mensagem_alerta:
            return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=equipe', mensagem_alerta, tag='error')

    mensagem_alerta = projeto.mensagem_restricao_adicionar_membro(categoria=Participacao.SERVIDOR, bolsista=False)
    if participacao.is_servidor() and mensagem_alerta:
        return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=equipe', mensagem_alerta, tag='error')

    mensagem_alerta = projeto.mensagem_restricao_adicionar_membro(categoria=Participacao.ALUNO, bolsista=False)
    if participacao.eh_aluno() and mensagem_alerta:
        return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=equipe', mensagem_alerta, tag='error')

    participacao.ativo = True
    participacao.data_inativacao = None
    participacao.save()
    participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ATIVAR_PARTICIPANTE)

    return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=equipe', 'Participante ativado com sucesso.')


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
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
@permission_required('pesquisa.pode_interagir_com_projeto')
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def remover_meta(request, meta_id):
    meta = get_object_or_404(Meta, pk=meta_id)
    projeto = meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        meta.delete()
        return httprr(f'/pesquisa/projeto/{projeto.pk:d}/?tab=metas', 'Meta removida com sucesso.')
    else:
        raise PermissionDenied


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
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
                return httprr('..', 'Etapa adicionada com sucesso.')
        else:
            form = EtapaForm(proj=projeto)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def remover_etapa(request, etapa_id):
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    projeto = etapa.meta.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        etapa.delete()
        return httprr(f'/pesquisa/projeto/{projeto.pk:d}/?tab=metas', 'Etapa removida com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
                return httprr('..', 'Etapa editada com sucesso.')
        else:
            form = EtapaForm(instance=etapa, proj=projeto)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
                return httprr('..', 'Etapa editada com sucesso.')
        else:
            form = EquipeEtapaForm(instance=etapa, proj=projeto)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def adicionar_recurso(request, edital_id):
    title = 'Adicionar Recurso'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = RecursoForm(data=request.POST or None)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.origem = form.cleaned_data.get('origem_recurso').descricao
            o.save()
            return httprr('..', 'Recurso adicionado com sucesso.')
    else:
        form = RecursoForm()
    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def remover_recurso(request, recurso_id):
    recurso = get_object_or_404(Recurso, pk=recurso_id)
    edital = recurso.edital
    tem_permissao_acesso_edital(request, edital)
    recurso.delete()
    return httprr(f'/pesquisa/edital/{edital.id:d}/', 'Recurso removido com sucesso.')


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def editar_recurso(request, recurso_id):
    recurso = get_object_or_404(Recurso, pk=recurso_id)
    edital = recurso.edital
    tem_permissao_acesso_edital(request, edital)
    title = 'Editar Recurso do Edital'
    if request.method == 'POST':
        form = RecursoForm(data=request.POST, instance=recurso)
        if form.is_valid():
            o = form.save(False)
            o.origem = form.cleaned_data.get('origem_recurso').descricao
            o.save()
            return httprr('..', 'Recurso editado com sucesso.')
    else:
        form = RecursoForm(instance=recurso)
    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
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
@permission_required('pesquisa.pode_gerenciar_edital')
def remover_criterio_avaliacao(request, pk):
    criterio = get_object_or_404(CriterioAvaliacao, pk=pk)
    if not criterio.pode_ser_removido():
        return httprr('..', 'Critério de avaliação não pode ser removido, pois existem avaliações feitas para esse critério.', tag='error')
    edital = criterio.edital
    tem_permissao_acesso_edital(request, edital)
    criterio.delete()
    return httprr(f'/pesquisa/edital/{edital.id:d}/', 'Critério de avaliação removido com sucesso.')


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
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
@permission_required('pesquisa.pode_gerenciar_edital')
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
@permission_required('pesquisa.pode_gerenciar_edital')
def adicionar_anexo(request, edital_id):
    title = 'Adicionar Anexo'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = EditalAnexoForm(data=request.POST)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.save()
            return httprr('..', 'Anexo adicionado com sucesso.')
    else:
        form = EditalAnexoForm()
    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def remover_anexo(request, anexo_id):
    anexo = get_object_or_404(EditalAnexo, pk=anexo_id)
    edital = anexo.edital
    tem_permissao_acesso_edital(request, edital)
    anexo.delete()
    return httprr(f'/pesquisa/edital/{edital.id:d}/', 'Anexo removido com sucesso.')


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def remover_anexo_auxiliar(request, anexo_id):
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    edital = anexo.edital
    tem_permissao_acesso_edital(request, edital)
    anexo.delete()
    return httprr(f'/pesquisa/edital/{edital.id:d}/', 'Anexo removido com sucesso.')


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def editar_anexo(request, anexo_id):
    anexo = get_object_or_404(EditalAnexo, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
    if request.method == 'POST':
        form = EditalAnexoForm(data=request.POST, instance=anexo)
        if form.is_valid():
            o = form.save(False)
            o.save()
            return httprr('..', 'Anexo editado com sucesso.')
    else:
        form = EditalAnexoForm(instance=anexo)
    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def editar_anexo_auxiliar(request, anexo_id):
    anexo = get_object_or_404(EditalAnexoAuxiliar, pk=anexo_id)
    tem_permissao_acesso_edital(request, anexo.edital)
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
@permission_required('pesquisa.pode_gerenciar_edital')
def adicionar_oferta_projeto(request, edital_id):
    title = 'Adicionar Oferta de Projeto'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if edital.forma_selecao == Edital.GERAL:
        title = 'Adicionar Campi Participantes'

    if request.method == 'POST':
        form = OfertaProjetoPesquisaFormMultiplo(data=request.POST, edital=edital, request=request)
        if form.is_valid():
            campi = form.cleaned_data['campi']
            num_maximo_ic = form.cleaned_data['num_maximo_ic']
            num_maximo_pesquisador = form.cleaned_data['num_maximo_pesquisador']
            for campus in campi:
                qs = BolsaDisponivel.objects.filter(edital=edital, uo=campus)
                if qs.exists():
                    bolsa_disponivel = qs[0]
                else:
                    bolsa_disponivel = BolsaDisponivel()
                bolsa_disponivel.edital = edital
                bolsa_disponivel.uo = campus
                bolsa_disponivel.num_maximo_ic = num_maximo_ic
                bolsa_disponivel.num_maximo_pesquisador = num_maximo_pesquisador
                bolsa_disponivel.save()
            return httprr('..', 'Oferta(s) adicionada(s) com sucesso.')
    else:
        form = OfertaProjetoPesquisaFormMultiplo(edital=edital, request=request)
    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def remover_oferta_projeto(request, oferta_projeto_id):
    oferta = get_object_or_404(BolsaDisponivel, pk=oferta_projeto_id)
    edital = oferta.edital
    tem_permissao_acesso_edital(request, edital)
    oferta.delete()
    return httprr(f'/pesquisa/edital/{edital.id:d}/', 'Oferta removida com sucesso.')


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def editar_oferta_projeto(request, oferta_projeto_id, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    title = 'Editar Plano de Oferta'
    oferta = get_object_or_404(BolsaDisponivel, pk=oferta_projeto_id, edital=edital)
    if request.method == 'POST':
        form = OfertaProjetoPesquisaForm(data=request.POST, instance=oferta)
        if form.is_valid():
            o = form.save(False)
            o.save()
            form.save_m2m()
            return httprr('..', 'Oferta editada com sucesso.')
    else:
        form = OfertaProjetoPesquisaForm(instance=oferta)
    return locals()


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
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


def tem_permissao(request, projeto, pode_auxiliar=True, pode_copein=False):
    eh_auxiliar = False
    eh_copein = False
    user = request.user
    if pode_auxiliar:
        eh_auxiliar = projeto.auxiliar and projeto.auxiliar == request.user.get_vinculo()
    if pode_copein:
        eh_copein = projeto.is_coordenador_pesquisa_campus_projeto(user) and projeto.get_status() == Projeto.STATUS_EM_EXECUCAO
    is_responsavel = projeto.is_responsavel(user) or projeto.is_gerente_sistemico()
    if not is_responsavel and not eh_auxiliar and not eh_copein:
        raise PermissionDenied('Apenas os auxiliares, coordenador ou gerente sistêmico podem executar esta ação.')


def tem_permissao_acesso_edital(request, edital):
    if (
        request.user.has_perm('pesquisa.tem_acesso_sistemico')
        or request.user.has_perm('pesquisa.pode_ver_config_edital')
        or request.user.has_perm('pesquisa.pode_gerenciar_edital')
        and (
            (edital.cadastrado_por_vinculo and edital.cadastrado_por_vinculo.setor.uo == get_uo(request.user))
            or (edital.autorizado_em and BolsaDisponivel.objects.filter(edital=edital, uo=get_uo(request.user)).exists())
        )
    ):
        return True
    raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_desembolso(request, desembolso_id):
    title = 'Editar Desembolso'
    desembolso = get_object_or_404(Desembolso, pk=desembolso_id)
    projeto = desembolso.projeto
    tem_permissao(request, projeto, pode_auxiliar=True, pode_copein=True)
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def remover_desembolso(request, desembolso_id):
    desembolso = get_object_or_404(Desembolso, pk=desembolso_id)
    projeto = desembolso.projeto
    tem_permissao(request, projeto, pode_auxiliar=True, pode_copein=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        projeto = desembolso.projeto
        url = f'/pesquisa/projeto/{projeto.id:d}/?tab=plano_desembolso'
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def upload_anexo(request, anexo_id):
    title = 'Upload de Arquivo'
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    projeto = anexo.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        origem = request.GET.get('origem')
        if request.method == 'POST':
            form = UploadProjetoAnexoForm(request.POST, request.FILES)
            if form.is_valid():
                arquivo_up = request.FILES['arquivo']
                if not (arquivo_up.name.lower().endswith('.pdf')):
                    return httprr('.', 'Apenas arquivos com o formato PDF são permitidos.', tag='error')
                vinculo = request.user.get_vinculo()
                salvar_arquivo(anexo, arquivo_up, vinculo, request)
                if form.cleaned_data.get('origem'):
                    return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=anexos', 'Arquivo enviado com sucesso.')
                else:
                    return httprr('..', 'Arquivo enviado com sucesso.')
        else:
            form = UploadProjetoAnexoForm(origem=origem)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_anexo_do_projeto(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    projeto = get_object_or_404(Projeto, pk=participacao.projeto.id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        title = 'Anexos do Participante  '
        Participacao.gerar_anexos_do_participante(participacao)

        anexos = ProjetoAnexo.objects.filter(projeto=participacao.projeto, vinculo_membro_equipe=participacao.vinculo_pessoa)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
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
            return httprr(f'/pesquisa/edital/{anexo.edital.id:d}/', 'Arquivo enviado com sucesso.')
    else:
        form = UploadArquivoForm()
    return locals()


@rtr()
@permission_required('pesquisa.pode_gerenciar_edital')
def upload_edital(request, edital_id):
    title = 'Adicionar Edital'
    edital = get_object_or_404(Edital, pk=edital_id)
    tem_permissao_acesso_edital(request, edital)
    if request.method == 'POST':
        form = UploadArquivoForm(request.POST, request.FILES)
        if form.is_valid():
            o = form.save(False)
            o.edital = edital
            o.data_cadastro = datetime.datetime.now()
            o.vinculo_autor = request.user.get_vinculo()
            o.save()
            return httprr(f'/pesquisa/edital/{edital.id:d}/', 'Arquivo enviado com sucesso.')
    else:
        form = UploadArquivoForm()
    return locals()


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def visualizar_arquivo(request, arquivo_id):
    arquivo = get_object_or_404(Arquivo, pk=arquivo_id)
    content = arquivo.load(request.user)
    if content:
        response = HttpResponse(content, content_type=arquivo.get_content_type(content))
        response['Content-Disposition'] = f'inline; filename={get_valid_filename(arquivo.nome)}'
        return response
    else:
        return HttpResponse('O arquivo solicitado foi adulterado ou não existe.')


@rtr()
@permission_required('pesquisa.pode_realizar_monitoramento_projeto')
def avaliar_conclusao_projeto(request: HttpRequest, registro_id: int) -> dict | HttpResponse:
    title = 'Validação da Conclusão do Projeto'
    registro = get_object_or_404(RegistroConclusaoProjeto, pk=registro_id)
    # mesmo estado em que a aba oferece "Emitir parecer" (Projeto.pode_emitir_parecer): finalizado e ainda sem parecer
    aguardando_parecer = registro.projeto.data_finalizacao_conclusao and not registro.dt_avaliacao
    eh_supervisor_ou_diretor = registro.projeto.vinculo_supervisor == request.user.get_vinculo() or request.user.has_group_cached(
        'Diretor de Pesquisa'
    )
    if aguardando_parecer and eh_supervisor_ou_diretor:
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
    else:
        raise PermissionDenied
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_foto(request, projeto_id):
    title = 'Adicionar Foto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = FotoProjetoForm(data=request.POST, files=request.FILES)
            if form.is_valid():
                for imagem in request.FILES.getlist('fotos'):
                    nova_imagem = FotoProjeto()
                    nova_imagem.projeto = projeto
                    nova_imagem.legenda = form.cleaned_data.get('legenda')
                    nova_imagem.imagem = imagem
                    try:
                        nova_imagem.save()
                    except Exception:
                        return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=fotos', 'O arquivo é inválido.', tag='error')
                return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=fotos', 'Foto adicionada com sucesso.')
        else:
            form = FotoProjetoForm()
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def remover_foto(request, foto_id):
    foto = get_object_or_404(FotoProjeto, pk=foto_id)
    projeto = foto.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        projeto_id = projeto.id
        foto.delete()
        return httprr(f'/pesquisa/projeto/{projeto_id:d}/?tab=fotos', 'Foto removida com sucesso.')
    else:
        raise PermissionDenied


def get_uos(request):
    setores = ()
    vinculo = request.user.get_vinculo()
    if vinculo.eh_servidor():
        if request.user.get_relacionamento().setor_lotacao:
            setores += (request.user.get_relacionamento().setor_lotacao.uo,)
        if request.user.get_relacionamento().setor_exercicio:
            setores += (request.user.get_relacionamento().setor_exercicio.uo,)
        if request.user.get_relacionamento().setor:
            setores += (request.user.get_relacionamento().setor.uo,)
    elif vinculo.eh_prestador():
        if request.user.get_relacionamento().setor_lotacao:
            setores += (request.user.get_relacionamento().setor_lotacao.uo,)
        if request.user.get_relacionamento().setor:
            setores += (request.user.get_relacionamento().setor.uo,)
    elif vinculo.eh_aluno():
        setores += (request.user.get_relacionamento().curso_campus.diretoria.setor.uo,)
    return setores


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_projeto(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    vinculo = request.user.get_vinculo()
    if not edital.pode_submeter_projeto(vinculo):
        raise PermissionDenied
    eh_servidor = vinculo.eh_servidor()
    if eh_servidor and not request.user.get_vinculo().relacionamento.areas_de_conhecimento.exists():
        return httprr(
            '/pesquisa/tornar_avaliador/', 'Você precisa se cadastrar como avaliador interno para poder submeter um projeto de pesquisa.', tag='error'
        )
    hoje = datetime.datetime.now().date()
    if edital.exigir_participacao_como_avaliador:
        ano = hoje.year - edital.anos_avaliacoes_considerar
        avaliacoes_realizadas = Avaliacao.objects.filter(vinculo=vinculo, data__year__gte=ano).count()
        recursos_avaliados = ItemAvaliacao.objects.filter(recurso_avaliado_por=vinculo, recurso_avaliado_em__year__gte=ano).count()
        total_avaliacoes = avaliacoes_realizadas + recursos_avaliados
        if total_avaliacoes < edital.quantidade_avaliacoes:
            return httprr(
                '/pesquisa/editais_abertos/',
                f'Só pode submeter projeto quem realizou, pelo menos, {edital.quantidade_avaliacoes} avaliações entre {ano} e {hoje.year}. Você realizou {total_avaliacoes} avaliações.',
                tag='error',
            )

    if (
        edital.impedir_coordenador_com_pendencia
        and Projeto.objects.exclude(edital=edital)
        .filter(
            pre_aprovado=True,
            aprovado=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            inativado=False,
            fim_execucao__lt=hoje,
            vinculo_coordenador=vinculo,
        )
        .exclude(projetocancelado__cancelado=True, projetocancelado__data_avaliacao__isnull=False)
        .exists()
    ):
        return httprr(
            '/pesquisa/editais_abertos/',
            'Este edital não permite a submissão de projeto de coordenadores que possuem projetos com conclusão em atraso.',
            tag='error',
        )
    hoje = datetime.datetime.now().date()
    if eh_servidor:
        curriculo = CurriculoVittaeLattes.objects.filter(vinculo=vinculo)[0]
        if curriculo.datahora_atualizacao and curriculo.datahora_atualizacao.date() < (
            hoje - relativedelta(months=+edital.tempo_maximo_meses_curriculo_desatualizado)
        ):
            return httprr(
                '/pesquisa/editais_abertos/',
                f'Seu currículo lattes não foi atualizado nos últimos {edital.tempo_maximo_meses_curriculo_desatualizado} meses. Acesse a Plataforma Lattes para '
                'atualizá-lo.',
                tag='error',
            )
        if not edital.permite_afastado_submeter:
            afastamento = vinculo.relacionamento.estah_afastado_ateh(datetime.date.today())
            if afastamento:
                return httprr(
                    '/pesquisa/editais_abertos/',
                    f'Não é permitido submeter projeto durante o período de afastamento. (Seu afastamento termina em: {afastamento.data_termino.strftime("%d/%m/%Y")})',
                    tag='error',
                )

    title = 'Adicionar Projeto'
    grupo_pesquisa_online = True

    uos = get_uos(request)
    setores = [uo.id for uo in uos]

    if not BolsaDisponivel.objects.filter(edital=edital, uo_id__in=setores).exists():
        return httprr('/pesquisa/editais_abertos/', 'Este edital não possui oferta para o seu campus.', tag='error')

    if eh_servidor:
        instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        try:
            status = atualizar_grupos_pesquisa(curriculo.id)
            if status == 0 and edital.exige_grupo_pesquisa:
                return httprr(
                    '/pesquisa/editais_abertos/',
                    f'O SUAP não encontrou nenhum Grupo de Pesquisa do {instituicao_sigla} ao qual você esteja vinculado. '
                    'Solicitamos que atualize seu Currículo Lattes e aguarde a disponibilização pública na base '
                    'CNPQ para então iniciar a submissão do seu projeto.',
                    tag='error',
                )
            if status == 3:
                erro_grupo_pesquisa_offline = True
        except Exception:
            grupo_pesquisa_online = False
    else:
        grupo_pesquisa_online = False

    instance = Projeto()
    instance.edital = edital
    instance.coordenador = request.user.get_profile()
    instance.vinculo_coordenador = vinculo
    form = ProjetoForm(
        request.POST or None,
        instance=instance,
        user=request.user,
        request=request,
        edital=edital,
        grupo_pesquisa_online=grupo_pesquisa_online,
        edicao=False,
    )
    if request.method == 'POST':
        if form.is_valid():
            if form.cleaned_data['deseja_receber_bolsa']:
                instance.bolsa_coordenador = form.cleaned_data['deseja_receber_bolsa']
            else:
                instance.bolsa_coordenador = False
            if form.cleaned_data.get('ppg') and form.cleaned_data.get('ppg').nivel == ProgramaPosGraduacao.STRICTO_SENSU:
                instance.uo = form.cleaned_data.get('ppg').campus_sede
            form.save()
            part_coord = Participacao.objects.filter(projeto__edital__id=edital_id, vinculo_pessoa=vinculo, responsavel=True).order_by('-id')[0]
            if edital.termo_compromisso_coordenador:
                part_coord.termo_aceito_em = datetime.datetime.now()
            part_coord.save()
            Participacao.gerar_anexos_do_participante(part_coord)
            projeto_id = part_coord.projeto.id
            return httprr(f'/pesquisa/projeto/{projeto_id:d}/', 'Projeto cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_projeto(request, projeto_id):
    title = 'Editar Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.get_periodo() == Projeto.PERIODO_EXECUCAO:
        form = EditarProjetoEmExecucaoForm(request.POST or None, instance=projeto, request=request)
        alterou = False
        texto = ''
        if form.is_valid():
            registro_atual = Projeto.objects.get(id=projeto_id)
            if form.cleaned_data.get('titulo') != registro_atual.titulo:
                alterou = True
                texto += f'Título atual: {form.cleaned_data.get("titulo")} (anterior: {registro_atual.titulo}); '
            if form.cleaned_data.get('inicio_execucao') != registro_atual.inicio_execucao:
                alterou = True
                texto += f'Data de ínicio atual: {form.cleaned_data.get("inicio_execucao").strftime("%d/%m/%Y")} (anterior: {registro_atual.inicio_execucao.strftime("%d/%m/%Y")}); '
            if form.cleaned_data.get('fim_execucao') != registro_atual.fim_execucao:
                alterou = True
                texto += f'Data de término atual: {form.cleaned_data.get("fim_execucao").strftime("%d/%m/%Y")} (anterior: {registro_atual.fim_execucao.strftime("%d/%m/%Y")}); '
            if form.cleaned_data.get('valor_global_projeto') and form.cleaned_data.get('valor_global_projeto') != registro_atual.valor_global_projeto:
                alterou = True
                texto += f'Valor global atual: {form.cleaned_data.get("valor_global_projeto")} (anterior: {registro_atual.valor_global_projeto}); '
            form.save()
            if alterou:
                historico = ProjetoHistoricoDeEnvio()
                historico.projeto = projeto
                historico.data_operacao = datetime.datetime.now()
                historico.parecer_devolucao = f'Alterações no projeto: {texto}'
                if request.user.get_vinculo().eh_servidor():
                    historico.operador = request.user.get_relacionamento()
                historico.vinculo_operador = request.user.get_vinculo()
                historico.save()
                titulo = '[SUAP] Pesquisa: Edição nos Dados de Projeto de Pesquisa'
                texto = (
                    '<h1>Pesquisa</h1>'
                    '<h2>Edição nos Dados de Projeto de Pesquisa</h2>'
                    f'<p>O coordenador do projeto {projeto.titulo} realizou alterações nos dados do projeto.</p>'
                    f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/gerenciar_historico_projeto/{projeto.id}/">{settings.SITE_URL}/pesquisa/gerenciar_historico_projeto/{projeto.id}/</a></p>'
                )
                vinculos = list(
                    Vinculo.objects.filter(
                        user__in=UsuarioGrupo.objects.filter(group__name='Coordenador de Pesquisa').only('user').values_list('user_id', flat=True)
                    ).filter(
                        tipo_relacionamento__model='servidor',
                        id_relacionamento__in=Servidor.objects.filter(ativo=True, setor__uo=projeto.uo).values_list('id', flat=True),
                    )
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)
            return httprr(f'/pesquisa/projeto/{projeto.id:d}/', 'Projeto editado com sucesso.')
    elif projeto.get_periodo() == Projeto.PERIODO_INSCRICAO:
        grupo_pesquisa_online = True
        try:
            curriculo = CurriculoVittaeLattes.objects.filter(vinculo=request.user.get_vinculo())[0]
            status = atualizar_grupos_pesquisa(curriculo.id)
        except Exception:
            grupo_pesquisa_online = False

        form = ProjetoForm(
            request.POST or None,
            instance=projeto,
            request=request,
            user=request.user,
            grupo_pesquisa_online=grupo_pesquisa_online,
            edital=projeto.edital,
            edicao=True,
        )

        if request.method == 'POST':
            if form.is_valid():
                registro_do_coordenador = Participacao.objects.get(projeto=projeto, responsavel=True)
                if not form.cleaned_data['deseja_receber_bolsa']:
                    registro_do_coordenador.vinculo = TipoVinculo.VOLUNTARIO
                    registro_do_coordenador.bolsa_concedida = False
                else:
                    registro_do_coordenador.vinculo = TipoVinculo.BOLSISTA
                    registro_do_coordenador.bolsa_concedida = True
                registro_do_coordenador.save()

                form.save()
                return httprr(f'/pesquisa/projeto/{projeto.id:d}/', 'Projeto editado com sucesso.')
    else:
        raise PermissionDenied

    return locals()


def _pendencia_pre_avaliacao(projeto: Projeto) -> str | None:
    """Mensagem da pendência que impede a pré-avaliação, na ordem em que a lista as mostra."""
    if projeto.edital.impedir_projeto_sem_anexo and projeto.tem_registro_anexos_pendente():
        return 'Este projeto possui anexos pendentes e não pode ser pré-avaliado.'
    if projeto.edital.exige_anuencia and projeto.pendente_anuencia():
        return 'Este projeto não foi deferido pela chefia imediata e não pode ser pré-avaliado.'
    if projeto.tem_aceite_pendente():
        return 'Este projeto possui aceite de termo de compromisso pendente.'
    return None


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def pre_selecionar(request: HttpRequest, projeto_id: int, rejeitar: bool | None = None, url: str | None = None) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Justificativa da Pré-Avaliação - {projeto.titulo}'

    if not url:
        url = request.META.get('HTTP_REFERER', '.')

    if not projeto.edital.is_periodo_pre_selecao():
        raise PermissionDenied

    if projeto.data_conclusao_planejamento is None:
        return httprr(url, 'Impossível realizar essa operação, projeto não foi enviado.', tag='error')

    pendencia = _pendencia_pre_avaliacao(projeto)
    if pendencia:
        return httprr(f'/pesquisa/projetos_nao_avaliados/{projeto.edital.id}/', pendencia, tag='error')

    # Sem isso, o Coordenador de outro campus pré-avaliava pela URL e pre_aprovar invertia projeto já aprovado (#17570).
    if not projeto.pode_receber_pre_avaliacao(rejeitar, request.user):
        raise PermissionDenied

    form = JustificativaPreAvaliacaoForm(request.POST or None, instance=projeto)
    if form.is_valid():
        projeto.vinculo_autor_pre_avaliacao = request.user.get_vinculo()
        projeto.data_pre_avaliacao = datetime.date.today()

        if projeto.pre_aprovado or rejeitar:
            projeto.pre_aprovado = False
            projeto.save()
        else:
            projeto.pre_aprovado = True
            projeto.vinculo_supervisor = request.user.get_vinculo()
            projeto.save()
            # Atualiza a pontuação do currículo lattes, este normaliza e atualiza a pontuação total do projeto.
            projeto.atualizar_pontuacao_curriculo_lattes()
            if projeto.edital.peso_avaliacao_grupo_pesquisa:
                projeto.atualizar_pontuacao_grupo_pesquisa()
        return httprr(f'/pesquisa/projetos_nao_avaliados/{projeto.edital.id}/', 'Projeto pré-avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def historico_equipe(request, participacao_id):
    title = 'Histórico da Participação'
    eh_sistemico = request.user.has_perm('pesquisa.add_origemrecursoedital')
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    historico = HistoricoEquipe.objects.filter(participante=participacao_id).order_by('id').exclude(movimentacao='Ativado')
    como_coordenador = historico.filter(categoria=HistoricoEquipe.COORDENADOR)
    como_membro = historico.filter(categoria=HistoricoEquipe.MEMBRO)
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def concluir_planejamento(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.edital.tem_formato_completo() and projeto.get_periodo() != Projeto.PERIODO_INSCRICAO:
        raise PermissionDenied

    if projeto.edital.permite_enviar_um_projeto:
        ja_enviou = (
            Projeto.objects.filter(edital=projeto.edital, vinculo_coordenador=request.user.get_vinculo(), data_conclusao_planejamento__isnull=False)
            .exclude(id=projeto.id)
            .first()
        )
        if ja_enviou:
            return httprr(
                f'/pesquisa/projeto/{projeto.id:d}/',
                mark_safe(
                    f'Este edital só permite o envio de um projeto por coordenador e você já enviou o projeto <strong>"{ja_enviou.titulo}"</strong>.'
                ),
                tag='error',
            )
    metas = Meta.objects.filter(projeto_id=projeto_id)

    tem_desembolso = True
    tem_plano_aplicacao = True
    mensagem_erro = ''
    if projeto.edital.tem_formato_completo():
        if projeto.edital.tem_fonte_recurso():
            qs_plano_de_aplicacao = ItemMemoriaCalculo.objects.filter(projeto_id=projeto_id)
            if qs_plano_de_aplicacao:
                for memoria_calculo in qs_plano_de_aplicacao:
                    if not Desembolso.objects.filter(item=memoria_calculo).exists():
                        tem_desembolso = False
            else:
                tem_plano_aplicacao = False

        if projeto.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            tem_desembolso = True
            tem_plano_aplicacao = True

        if projeto.edital.participa_aluno and not projeto.tem_aluno():
            if projeto.edital.permite_indicacao_tardia_equipe:
                mensagem_erro = (
                    mensagem_erro
                    + '* O projeto precisa da inclusão de um aluno na equipe ou da indicação de que haverá pelo menos um aluno na equipe.</br>'
                )
            else:
                mensagem_erro = mensagem_erro + '* O projeto deve ter pelo menos um aluno na equipe.</br>'

        if not projeto.grupo_pesquisa and projeto.edital.exige_grupo_pesquisa:
            mensagem_erro = mensagem_erro + '* Projeto sem grupo de pesquisa. Edite o projeto e informe o grupo de pesquisa.</br>'

        if not tem_desembolso:
            mensagem_erro = mensagem_erro + '* Cadastre o Plano de Desembolso para cada Item de Mémoria de Cálculo antes de enviar o Projeto.</br>'

        if not tem_plano_aplicacao:
            mensagem_erro = mensagem_erro + '* Cadastre o Plano de Aplicação antes de enviar o Projeto.</br>'

        if not metas:
            mensagem_erro = mensagem_erro + '* Cadastre as Metas/Atividades antes de enviar o Projeto.</br>'

        if projeto.edital.atividade_todo_mes and not projeto.tem_atividade_todo_mes():
            mensagem_erro = mensagem_erro + '* O projeto deve ter pelo menos uma atividade sendo executada em cada mês.</br>'

        else:
            tem_atividade = False
            for meta in metas:
                atividade = Etapa.objects.filter(meta_id=meta.id)
                if atividade:
                    tem_atividade = True
            if not tem_atividade:
                mensagem_erro = mensagem_erro + '* Cadastre as Atividades de cada Meta antes de enviar o Projeto.</br>'
    if mensagem_erro != '':
        return httprr(
            f'/pesquisa/projeto/{projeto.id:d}/',
            mark_safe('Atenção! O projeto não pode ser enviado. Resolva as pendências a seguir:<br>' + mensagem_erro),
            tag='error',
        )
    agora = datetime.datetime.now()
    projeto.data_conclusao_planejamento = agora
    if not projeto.vinculo_coordenador:
        projeto.vinculo_coordenador = Participacao.objects.filter(projeto=projeto, responsavel=True)[0].vinculo_pessoa
    projeto.save()
    historico_projeto = ProjetoHistoricoDeEnvio()
    historico_projeto.projeto = projeto
    historico_projeto.data_operacao = agora
    historico_projeto.situacao = ProjetoHistoricoDeEnvio.ENVIADO
    if request.user.get_vinculo().eh_servidor():
        historico_projeto.operador = request.user.get_relacionamento()
    historico_projeto.vinculo_operador = request.user.get_vinculo()
    historico_projeto.save()

    if projeto.edital.exige_anuencia and projeto.vinculo_coordenador.eh_servidor():
        chefes = request.user.get_relacionamento().chefes_na_data(agora.date()).order_by('funcao')
        if chefes and not projeto.responsavel_anuencia:
            chefe_servidor = chefes[0]
            projeto.responsavel_anuencia = chefe_servidor
            projeto.save()
            titulo = '[SUAP] Pesquisa: Anuência de Projeto de Pesquisa'
            texto = f'<h1>Pesquisa</h1><h2>Anuência de Projeto de Pesquisa</h2><p>Foi solicitada sua anuência no projeto de pesquisa: {projeto.titulo}. Acesse o SUAP para mais detalhes.</p>'
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [chefe_servidor.get_vinculo()])

    return httprr(f'/pesquisa/projeto/{projeto.id:d}/', 'Projeto enviado com sucesso.')


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def finalizar_conclusao(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not projeto.edital.tem_monitoramento_por_atividades():
        tem_permissao(request, projeto, pode_auxiliar=False)
        if (
            not projeto.data_finalizacao_conclusao
            and not projeto.relatorioprojeto_set.filter(avaliado_em__isnull=True).exists()
            and projeto.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL).exists()
        ):
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

            return httprr(f'/pesquisa/projeto/{projeto.id:d}/', 'Conclusão finalizada com sucesso.')
        else:
            mensagem_erro = 'Projeto não pode ser finalizado, pois não há registro de relatório final ou o relatório final não foi avaliado pelo supervisor do projeto.'
            return httprr(f'/pesquisa/projeto/{projeto.id:d}/', mensagem_erro, tag='error')

    if projeto.edital.tem_formato_completo():
        tem_permissao(request, projeto, pode_auxiliar=False)
        mensagem_erro = ''
        if projeto.tem_registro_execucao_etapa_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois não há registro de execução de atividades ou existe registro não avaliados pelo Diretor(a) ou Coordenador(a) de Pesquisa do Campus'
        if projeto.tem_registro_gasto_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois existem desembolsos sem o registro das despesas realizadas ou existe despesa não avaliada pelo Diretor(a) ou Coordenador(a) de Pesquisa do Campus.'
        if projeto.tem_registro_anexos_pendente():
            mensagem_erro = 'Projeto não pode ser finalizado, pois não há registro dos anexos do projeto.'

        if mensagem_erro != '':
            return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=conclusao', mensagem_erro, tag='error')
    else:
        if not (projeto.vinculo_supervisor == request.user.get_vinculo()):
            raise PermissionDenied

    registro = RegistroConclusaoProjeto.objects.filter(projeto=projeto).first()
    if registro is None:
        return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=conclusao', 'Registre a conclusão antes de finalizar.', tag='error')
    if not projeto.edital.tem_formato_completo():
        title = 'Finalizar Projeto'
        if request.method == 'POST':
            form = RegistroConclusaoProjetoObsForm(data=request.POST, instance=registro)
            if form.is_valid():
                registro = form.save(False)
                registro.projeto = projeto
                registro.dt_avaliacao = datetime.datetime.now()
                registro.avaliador = request.user.get_relacionamento()
                registro.save()
        else:
            form = RegistroConclusaoProjetoObsForm(instance=registro)

    if projeto.edital.tem_formato_completo() or registro.avaliador:
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

        return httprr(f'/pesquisa/projeto/{projeto.id:d}/', 'Conclusão finalizada com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def gerenciar_historico_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse | dict[str, object]:
    historico = ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto_id).order_by('data_operacao')
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Movimentação do Projeto: {projeto.titulo}'
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
        titulo = '[SUAP] Pesquisa: Devolução de Projeto'
        texto = f"<h1>Pesquisa</h1><h2>Devolução de Projeto</h2><p>O Projeto '{projeto.titulo}' foi devolvido pelo Gestor de Pesquisa e Inovação.</p>"
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])
        return httprr('.', 'Devolução do projeto registrada com sucesso.')
    else:
        form = ProjetoHistoricoDeEnvioForm()
    return locals()


@rtr()
@transaction.atomic
@permission_required('pesquisa.pode_se_tornar_avaliador')
def tornar_avaliador(request):
    title = 'Áreas de Conhecimento - Avaliação de Projetos de Pesquisa'
    pessoa = request.user.get_relacionamento()
    if not isinstance(pessoa, Servidor) and not isinstance(pessoa, PrestadorServico):
        return httprr('/', 'Apenas servidores/prestadores de serviço podem se tornar avaliadores', tag='error')
    areas_conhecimentos = pessoa.areas_de_conhecimento.all().order_by('superior')
    form = ProjetoAvaliadorForm(data=request.POST or None, request=request, pessoa=pessoa)
    if form.is_valid():
        ids_areas = []
        for area in form.cleaned_data.get('areas_de_conhecimento'):
            ids_areas.append(area.id)
            if area not in pessoa.areas_de_conhecimento.all():
                pessoa.areas_de_conhecimento.add(area)
        outras_areas = pessoa.areas_de_conhecimento.exclude(id__in=ids_areas)
        if outras_areas.exists():
            for area in outras_areas:
                pessoa.areas_de_conhecimento.remove(area)

        return httprr('.', 'Área de conhecimento cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.add_edital')
def distribuir_bolsas(request):
    title = 'Distribuição de Bolsas dos Projetos de Pesquisa'
    editais = Edital.objects.em_distribuicao_bolsa()
    uos = None

    if request.user.has_group_cached('Coordenador de Pesquisa') and not request.user.has_group_cached('Diretor de Pesquisa'):
        uos = get_uos(request)
        editais = editais.filter(forma_selecao=Edital.CAMPUS)
    edital_parcial = False
    return locals()


@rtr()
@permission_required('pesquisa.add_edital')
def gerenciar_bolsas(request, edital_id, campus_id=None):
    title = 'Gerenciamento de Bolsas dos Projetos de Pesquisa'
    qtd_bolsa_pesquisador_distribuida = 0
    qtd_bolsa_ic_distribuida = 0
    qtd_bolsa_pesquisador_solicitada = 0
    qtd_bolsa_ic_solicitada = 0
    edital = get_object_or_404(Edital, id=edital_id)
    campus = None
    if edital.forma_selecao == Edital.CAMPUS and campus_id:
        campus = get_object_or_404(UnidadeOrganizacional, id=campus_id)
        if request.user.has_group_cached('Coordenador de Pesquisa') and not request.user.has_group_cached('Diretor de Pesquisa'):
            campi = get_uos(request)
            if campus not in campi:
                raise PermissionDenied

    if not request.POST:
        edital.classifica_projetos_pesquisa(campus)

    if edital.forma_selecao == Edital.GERAL:
        projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('-pontuacao_total', '-pontuacao')
    else:
        projetos = Projeto.objects.filter(edital=edital, uo=campus, pre_aprovado=True).order_by('-pontuacao_total', '-pontuacao')
    if projetos:
        if edital.forma_selecao == Edital.CAMPUS and edital.bolsadisponivel_set.filter(uo=campus):
            qtd_bolsa_pesquisador = edital.bolsadisponivel_set.get(uo=campus).num_maximo_pesquisador
            qtd_bolsa_ic = edital.bolsadisponivel_set.get(uo=campus).num_maximo_ic
            participacoes = Participacao.objects.filter(projeto__in=projetos.values_list('id', flat=True)).order_by('vinculo')
        elif edital.forma_selecao == Edital.GERAL:
            qtd_bolsa_pesquisador = edital.qtd_bolsa_servidores
            qtd_bolsa_ic = edital.qtd_bolsa_alunos
            participacoes = Participacao.objects.filter(projeto__in=projetos.values_list('id', flat=True)).order_by('vinculo')
        for participacao in participacoes:
            if participacao.is_servidor():
                if participacao.vinculo == TipoVinculo.BOLSISTA:
                    qtd_bolsa_pesquisador_solicitada = qtd_bolsa_pesquisador_solicitada + 1
                if participacao.bolsa_concedida is True and participacao.vinculo == TipoVinculo.BOLSISTA:
                    qtd_bolsa_pesquisador_distribuida = qtd_bolsa_pesquisador_distribuida + 1
            else:
                if participacao.vinculo == TipoVinculo.BOLSISTA:
                    qtd_bolsa_ic_solicitada = qtd_bolsa_ic_solicitada + 1
                if participacao.bolsa_concedida is True and participacao.vinculo == TipoVinculo.BOLSISTA:
                    qtd_bolsa_ic_distribuida = qtd_bolsa_ic_distribuida + 1
        saldo_bolsa_pesquisador = qtd_bolsa_pesquisador - qtd_bolsa_pesquisador_distribuida
        saldo_bolsa_ic = qtd_bolsa_ic - qtd_bolsa_ic_distribuida

    if 'xls' in request.GET:
        return gerenciar_bolsas_export_to_xls(request, projetos)

    if request.POST:
        ids_participacao_de_servidor_bolsa_concedida = request.POST.getlist('participacoes_pesquisadores')
        ids_participacao_de_aluno_bolsa_concedidas = request.POST.getlist('participacoes_ic')
        ids_projetos_aprovados = request.POST.getlist('situacao')
        if campus:
            superou_cota_pesquisador, superou_cota_ic = edital.distribuir_bolsas(
                ids_participacao_de_servidor_bolsa_concedida, ids_participacao_de_aluno_bolsa_concedidas, ids_projetos_aprovados, id_uo=campus.id
            )
        else:
            superou_cota_pesquisador, superou_cota_ic = edital.distribuir_bolsas(
                ids_participacao_de_servidor_bolsa_concedida, ids_participacao_de_aluno_bolsa_concedidas, ids_projetos_aprovados
            )

        if not superou_cota_pesquisador and not superou_cota_ic and campus_id:
            return httprr(f'/pesquisa/gerenciar_bolsas/{edital_id}/{campus_id}/', 'Bolsas salvas com sucesso.')
        elif not superou_cota_pesquisador and not superou_cota_ic:
            return httprr(f'/pesquisa/gerenciar_bolsas/{edital_id}/', 'Bolsas salvas com sucesso.')
        elif superou_cota_pesquisador and campus_id:
            return httprr(
                f'/pesquisa/gerenciar_bolsas/{edital_id}/{campus_id}/',
                'A quantidade de bolsas distribuídas para pesquisadores superou a cota destinada para o campus.',
                tag='error',
            )
        else:
            return httprr(
                f'/pesquisa/gerenciar_bolsas/{edital_id}/',
                'A quantidade de bolsas distribuídas de iniciação científica superou a cota destinada para o campus.',
                tag='error',
            )
    return locals()


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def plano_trabalho_participante(request: HttpRequest, projeto_id: int, participacao_id: int) -> dict:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    participante = get_object_or_404(Participacao, id=participacao_id, projeto=projeto)
    if not participante.pode_emitir_plano_de_trabalho():
        raise PermissionDenied
    descricao_plano = []
    metas = projeto.get_metas()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
    for meta in metas:
        etapas = meta.etapa_set.filter(integrantes__in=[participante.id]).order_by('ordem')
        if etapas:
            descricao_plano.extend(etapas)

    return locals()


@rtr()
@permission_required('pesquisa.add_origemrecursoedital')
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
        titulo = '[SUAP] Pesquisa: Reabertura de Projeto'
        texto = f"<h1>Pesquisa</h1><h2>Reabertura de Projeto</h2><p>O Projeto '{projeto.titulo}' foi reaberto pelo gestor de pesquisa e inovação.</p>"
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])
        return httprr('..', 'Reabertura do projeto realizada com sucesso.')

    else:
        form = ProjetoHistoricoDeEnvioForm()
    return locals()


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def selecionar_avaliadores(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if edital.formato == Edital.FORMATO_SIMPLIFICADO:
        raise PermissionDenied('O formato deste edital é simplificado, portanto não requer a avaliação dos projetos.')
    title = f'Selecionar avaliadores dos Projetos do {edital.titulo}'
    if request.user.has_group_cached('Coordenador de Pesquisa'):
        projetos = Projeto.objects.filter(edital=edital, uo=get_uo(request.user), pre_aprovado=True).order_by('titulo')
    else:
        projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('titulo')

    form = IndicarAvaliadorForm(request.GET or None, request=request)
    if form.is_valid():
        status_avaliacao = form.cleaned_data['status_avaliacao']
        palavra_chave = form.cleaned_data['palavra_chave']
        uo = form.cleaned_data['uo']
        if uo:
            projetos = projetos.filter(uo__id=uo.id)
        if palavra_chave:
            projetos = projetos.filter(avaliadorindicado__vinculo__pessoa__nome__icontains=palavra_chave)
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

    return locals()


def projeto_fora_do_campus_do_coordenador(user: User, projeto: Projeto) -> bool:
    """O Coordenador de Pesquisa só indica avaliadores nos projetos do próprio campus, o recorte de ``selecionar_avaliadores`` (#17550)."""
    return user.has_group_cached('Coordenador de Pesquisa') and projeto.uo != get_uo(user)


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def selecionar_avaliadores_do_projeto(request: HttpRequest, projeto_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto_fora_do_campus_do_coordenador(request.user, projeto):
        raise PermissionDenied
    title = f'Indicar Avaliadores do Projeto {projeto.titulo}'
    try:
        url = request.get_full_path().split('url=')[1]
    except Exception:
        raise PermissionDenied('Endereço inválido')
    form = IndicarAvaliadoresForm(request.POST or None)
    if form.is_valid():
        avaliadores_cadastrados = AvaliadorIndicado.objects.filter(projeto=projeto)
        edital = projeto.edital
        if edital.exige_comissao:
            if request.user.has_group_cached('Coordenador de Pesquisa'):
                membros_comissao = Vinculo.objects.filter(
                    id__in=ComissaoEditalPesquisa.objects.filter(edital=projeto.edital, uo=get_uo(request.user)).values_list(
                        'vinculos_membros', flat=True
                    )
                )
            else:
                membros_comissao = Vinculo.objects.filter(
                    id__in=ComissaoEditalPesquisa.objects.filter(edital=projeto.edital).values_list('vinculos_membros', flat=True)
                )

        else:
            titulacoes = edital.titulacoes_avaliador.all().values_list('codigo', flat=True)
            ids_externos = set(
                AvaliadorExterno.objects.filter(
                    titulacao__codigo__in=titulacoes,
                    vinculo__in=PrestadorServico.objects.filter(areas_de_conhecimento__isnull=False).values_list('vinculos', flat=True),
                ).values_list('vinculo', flat=True)
            )

            ids_internos = set(
                Servidor.objects.filter(titulacao__codigo__in=titulacoes, areas_de_conhecimento__isnull=False).values_list('vinculos', flat=True)
            )
            union = set.union(ids_externos, ids_internos)
            membros_comissao = Vinculo.objects.filter(id__in=union)
        avaliadores_da_area = Servidor.objects.all()
        buscou = False
        if form.cleaned_data.get('nome'):
            membros_comissao = membros_comissao.filter(pessoa__nome__icontains=form.cleaned_data.get('nome'))
        if form.cleaned_data.get('matricula'):
            buscou = True
            avaliadores_da_area = avaliadores_da_area.filter(matricula=form.cleaned_data.get('matricula'))
        if form.cleaned_data.get('titulacao'):
            ids_externos = set(AvaliadorExterno.objects.filter(titulacao=form.cleaned_data.get('titulacao')).values_list('vinculo', flat=True))
            avaliadores_da_area = avaliadores_da_area.filter(titulacao=form.cleaned_data.get('titulacao'))
            ids_internos = set(avaliadores_da_area.values_list('vinculos', flat=True))
            union = set.union(ids_externos, ids_internos)
            membros_comissao = membros_comissao.filter(id__in=union)
        if form.cleaned_data.get('filtrar_por_area'):
            avaliadores_da_area = avaliadores_da_area.filter(areas_de_conhecimento=projeto.area_conhecimento)
            ids_externos = set(
                AvaliadorExterno.objects.filter(
                    vinculo__in=PrestadorServico.objects.filter(areas_de_conhecimento=projeto.area_conhecimento).values_list('vinculos', flat=True)
                ).values_list('vinculo', flat=True)
            )
            ids_internos = set(avaliadores_da_area.values_list('vinculos', flat=True))
            union = set.union(ids_externos, ids_internos)
            membros_comissao = membros_comissao.filter(id__in=union)
        if form.cleaned_data.get('area_conhecimento'):
            avaliadores_da_area = avaliadores_da_area.filter(areas_de_conhecimento=form.cleaned_data.get('area_conhecimento'))
            ids_externos = set(
                AvaliadorExterno.objects.filter(
                    vinculo__in=PrestadorServico.objects.filter(areas_de_conhecimento=form.cleaned_data.get('area_conhecimento')).values_list(
                        'vinculos', flat=True
                    )
                ).values_list('vinculo', flat=True)
            )
            ids_internos = set(avaliadores_da_area.values_list('vinculos', flat=True))
            union = set.union(ids_externos, ids_internos)
            membros_comissao = membros_comissao.filter(id__in=union)
        if form.cleaned_data.get('disciplina_ingresso'):
            buscou = True
            ids_pela_disciplina = []
            for servidor in avaliadores_da_area.filter(vinculos__professor__isnull=False):
                if servidor.get_vinculo().professor_set.first().disciplina == form.cleaned_data.get('disciplina_ingresso'):
                    ids_pela_disciplina.append(servidor.id)
            avaliadores_da_area = avaliadores_da_area.filter(id__in=ids_pela_disciplina)
        if buscou:
            membros_comissao = membros_comissao.filter(id__in=avaliadores_da_area.values_list('vinculos', flat=True))
        servidores_equipes = projeto.get_participacoes_servidores_ativos()
        ids_servidores = []
        for servidor in servidores_equipes:
            ids_servidores.append(servidor.vinculo_pessoa.id)

        if not projeto.edital.campus_especifico:
            membros_comissao = membros_comissao.exclude(id__in=ids_servidores).exclude(setor__uo=projeto.uo)
        else:
            membros_comissao = membros_comissao.exclude(id__in=ids_servidores)
        if projeto.edital.impedir_submissao_de_avaliador:
            membros_comissao = membros_comissao.exclude(
                id__in=Projeto.objects.filter(edital=projeto.edital).values_list('vinculo_coordenador', flat=True)
            )
        lista_avaliadores = []

        if request.GET.get('sorteio'):
            lista_qtd = []

            for pessoa in membros_comissao.order_by('pessoa__nome'):
                lista_qtd.append(
                    [
                        pessoa,
                        AvaliadorIndicado.objects.filter(vinculo=pessoa, projeto__edital=projeto.edital).count(),
                        AvaliadorIndicado.objects.filter(vinculo=pessoa).count(),
                    ]
                )
            lista_qtd.sort(key=lambda x: (x[1], x[2]))
            quantidade_indicada = 0
            total_indicacoes = AvaliadorIndicado.objects.filter(projeto=projeto, rejeitado=False).count()
            tamanho_da_lista = len(lista_qtd)
            for pessoa in membros_comissao.order_by('pessoa__nome'):
                if total_indicacoes < 3:
                    if quantidade_indicada < tamanho_da_lista:
                        prioridade = membros_comissao.get(id=lista_qtd[quantidade_indicada][0].id)
                        indicacoes_no_edital = AvaliadorIndicado.objects.filter(vinculo=prioridade, projeto__edital=projeto.edital).count()
                        indicacoes_total = AvaliadorIndicado.objects.filter(vinculo=prioridade).count()
                        avaliacoes_total = Avaliacao.objects.filter(vinculo=prioridade).count()
                        lista_avaliadores.append([prioridade, True, indicacoes_no_edital, indicacoes_total, avaliacoes_total])
                        quantidade_indicada += 1
                        total_indicacoes += 1
                else:
                    indicacoes_no_edital = AvaliadorIndicado.objects.filter(vinculo=pessoa, projeto__edital=projeto.edital).count()
                    indicacoes_total = AvaliadorIndicado.objects.filter(vinculo=pessoa).count()
                    avaliacoes_total = Avaliacao.objects.filter(vinculo=pessoa).count()
                    lista_avaliadores.append([pessoa, False, indicacoes_no_edital, indicacoes_total, avaliacoes_total])

        else:
            for pessoa in membros_comissao.order_by('pessoa__nome'):
                indicacoes_no_edital = AvaliadorIndicado.objects.filter(vinculo=pessoa, projeto__edital=projeto.edital).count()
                indicacoes_total = AvaliadorIndicado.objects.filter(vinculo=pessoa).count()
                avaliacoes_total = Avaliacao.objects.filter(vinculo=pessoa).count()
                if pessoa.id in avaliadores_cadastrados.values_list('vinculo', flat=True):
                    lista_avaliadores.append([pessoa, True, indicacoes_no_edital, indicacoes_total, avaliacoes_total])
                else:
                    lista_avaliadores.append([pessoa, False, indicacoes_no_edital, indicacoes_total, avaliacoes_total])

    return locals()


def membros_comissao_do_projeto(user: User, projeto: Projeto) -> QuerySet[Vinculo]:
    """Vínculos de onde sai a lista de avaliadores (``selecionar_avaliadores_do_projeto``), sem os filtros de busca da tela."""
    edital = projeto.edital
    if edital.exige_comissao:
        comissoes = ComissaoEditalPesquisa.objects.filter(edital=edital)
        if user.has_group_cached('Coordenador de Pesquisa'):
            comissoes = comissoes.filter(uo=get_uo(user))
        return Vinculo.objects.filter(id__in=comissoes.values_list('vinculos_membros', flat=True))
    titulacoes = edital.titulacoes_avaliador.all().values_list('codigo', flat=True)
    ids_externos = set(
        AvaliadorExterno.objects.filter(
            titulacao__codigo__in=titulacoes,
            vinculo__in=PrestadorServico.objects.filter(areas_de_conhecimento__isnull=False).values_list('vinculos', flat=True),
        ).values_list('vinculo', flat=True)
    )
    ids_internos = set(
        Servidor.objects.filter(titulacao__codigo__in=titulacoes, areas_de_conhecimento__isnull=False).values_list('vinculos', flat=True)
    )
    return Vinculo.objects.filter(id__in=ids_externos | ids_internos)


def excluir_impedidos_de_avaliar(projeto: Projeto, membros: QuerySet[Vinculo]) -> QuerySet[Vinculo]:
    """Tira de ``membros`` a equipe do projeto, o próprio campus (edital não específico) e, se o edital impede, os coordenadores."""
    membros = membros.exclude(id__in=[servidor.vinculo_pessoa.id for servidor in projeto.get_participacoes_servidores_ativos()])
    if not projeto.edital.campus_especifico:
        membros = membros.exclude(setor__uo=projeto.uo)
    if projeto.edital.impedir_submissao_de_avaliador:
        membros = membros.exclude(id__in=Projeto.objects.filter(edital=projeto.edital).values_list('vinculo_coordenador', flat=True))
    return membros


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def salvar_avaliadores_do_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto_fora_do_campus_do_coordenador(request.user, projeto):
        raise PermissionDenied
    avaliadores_cadastrados = AvaliadorIndicado.objects.filter(projeto=projeto)
    grupo = Group.objects.get(name='Avaliador Sistêmico de Projetos de Pesquisa')
    escolhidos = request.POST.getlist('registros')
    url = request.get_full_path().split('url=')[1]
    ids_escolhidos = []
    if escolhidos:
        for item in escolhidos:
            ids_escolhidos.append(int(item))
    # Só quem a tela oferece: os ids do POST fora da lista são ignorados.
    escolhidos_validos = excluir_impedidos_de_avaliar(projeto, membros_comissao_do_projeto(request.user, projeto).filter(id__in=ids_escolhidos))
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

            fim_selecao = projeto.edital.fim_selecao
            if projeto.edital.eh_edital_continuo():
                fim_selecao = projeto.edital.fim_inscricoes
            titulo = '[SUAP] Avaliação de Projeto de Pesquisa'
            if projeto.edital.prazo_aceite_indicacao:
                texto = (
                    '<h1>Avaliação de Projeto de Pesquisa</h1>'
                    f'<h2>{projeto.titulo}</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de pesquisa: {projeto.titulo}.</p>'
                    f'<p>Prazo para registrar que aceita a indicação: {format_(novo_avaliador.prazo_para_aceite)}.</p>'
                    f'<p>Prazo para realizar a avaliação: {format_(novo_avaliador.prazo_para_avaliacao)}.</p>'
                    '<p>Caso os prazos não sejam cumpridos, a indicação será cancelada automaticamente.</p>'
                    f'<p>O registro de aceite e a avaliação poderão ser realizados através do seguinte endereço: <a href="{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/">{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital: {format_(projeto.edital.inicio_selecao)} - {format_(fim_selecao)}.</p>'
                )

            else:
                texto = (
                    '<h1>Avaliação de Projeto de Pesquisa</h1>'
                    f'<h2>{projeto.titulo}</h2>'
                    f'<p>Foi solicitada sua avaliação do projeto de pesquisa: {projeto.titulo}.</p>'
                    f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/">{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/</a></p>'
                    f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital: {format_(projeto.edital.inicio_selecao)} - {format_(fim_selecao)}.</p>'
                )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [avaliador])
    return httprr(url, 'Avaliadores cadastrados com sucesso.')


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def atualizar_pontuacao(request, projeto_id):
    """
    Esta ação é oriundo do botão atualizar pontuação que está disponível na aba pontuação do currículo lattes da tela de visualização de projetos
    :param request:
    :param projeto_id:
    :return:
    """
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.edital.is_periodo_antes_pre_selecao() and not projeto.data_avaliacao:
        url = request.META.get('HTTP_REFERER', '.')
        if projeto:
            # Atualiza a pontuação do currículo lattes, este normaliza e atualiza a pontuação total do projeto.
            projeto.atualizar_pontuacao_curriculo_lattes()
            if projeto.edital.peso_avaliacao_grupo_pesquisa:
                projeto.atualizar_pontuacao_grupo_pesquisa()
            return httprr(url, 'Atualização realizada com sucesso.')
    else:
        raise PermissionDenied


@permission_required('pesquisa.pode_interagir_com_projeto')
def atualizar_grupos_de_pesquisa(request):
    curriculo = get_object_or_404(CurriculoVittaeLattes, vinculo=request.user.get_vinculo())
    numero_identificador = curriculo.numero_identificador

    url = request.META.get('HTTP_REFERER', '.')

    instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')

    try:
        status = atualizar_grupos_pesquisa(curriculo.id)
        if status == 3:
            return httprr(url, 'Diretório dos grupos de pesquisa no Lattes em manutenção.', tag='error')

        if not curriculo.grupos_pesquisa.filter(instituicao=instituicao_sigla).exists():
            return httprr(
                url,
                mark_safe(
                    'Não há grupos de pesquisa vinculado ao {}. Consulte seu {}'.format(
                        instituicao_sigla,
                        f'<a href="http://dgp.cnpq.br/dgp/espelhorh/{numero_identificador}"> Diretório dos Grupos de Pesquisa do Lattes. </a>',
                    )
                ),
                tag='error',
            )
    except Exception:
        return httprr(url, 'Diretório dos grupos de pesquisa no Lattes indisponível (off-line).', tag='error')
    # http://dgp.cnpq.br/dgp/espelhorh/3571057110440770.
    return httprr(url)


@rtr()
@permission_required('pesquisa.view_avaliadorexterno')
def listar_avaliadores(request):
    title = 'Listar Avaliadores Internos'
    avaliadores = Servidor.objects.filter(areas_de_conhecimento__isnull=False)
    form = AvaliadoresAreaConhecimentoForm(request.GET or None)
    if form.is_valid():
        area_conhecimento = form.cleaned_data['area_conhecimento']
        palavra_chave = form.cleaned_data['palavra_chave']
        uo = form.cleaned_data['uo']
        titulacao = form.cleaned_data['titulacao']
        situacao = form.cleaned_data['situacao']
        if situacao:
            if situacao == 'Ativos':
                avaliadores = Servidor.objects.ativos().filter(areas_de_conhecimento__isnull=False, ativo=True)
            else:
                avaliadores = Servidor.objects.inativos().filter(areas_de_conhecimento__isnull=False) | Servidor.objects.filter(
                    areas_de_conhecimento__isnull=False, ativo=False
                )
        if area_conhecimento:
            area = AreaConhecimento.objects.filter(id=area_conhecimento.id)
            avaliadores = avaliadores.filter(areas_de_conhecimento__in=area.values_list('id', flat=True))
        if uo:
            avaliadores = avaliadores.filter(setor__uo__id=uo.id)
        if palavra_chave:
            avaliadores = avaliadores.filter(pessoa_fisica__nome__icontains=palavra_chave)
        if titulacao:
            avaliadores = avaliadores.filter(titulacao=titulacao)

    avaliadores = avaliadores.distinct()
    if 'xls' in request.GET:
        return tasks.listar_avaliadores_export_to_xls(avaliadores)
    return locals()


@rtr()
@permission_required('pesquisa.pode_ver_equipe_projeto')
def listar_equipes_dos_projetos(request):
    title = 'Lista de Equipes dos Projetos'
    form = EquipeProjetoForm(data=request.GET or None)
    tipo_exibicao = 0  # Detalhado
    dados_do_projeto = []
    participacoes = None
    tem_permissao_propi = request.user.has_perm('pesquisa.tem_acesso_sistemico')
    if form.is_valid():
        projetos = Projeto.objects.filter(aprovado=True)
        if request.GET.get('ano'):
            projetos = projetos.filter(edital__inicio_inscricoes__year=request.GET.get('ano'))
        if request.GET.get('edital'):
            projetos = projetos.filter(edital=request.GET.get('edital'))

        if request.GET.get('campus'):
            projetos = projetos.filter(uo=request.GET.get('campus'))

        if request.GET.get('pessoa'):
            participacoes = Participacao.objects.filter(vinculo_pessoa=request.GET.get('pessoa'), projeto__aprovado=True)
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
            participacoes = Participacao.objects.filter(projeto__in=projetos, ativo=True).order_by('vinculo_pessoa__pessoa__nome')
        else:
            participacoes = participacoes.filter(ativo=True).order_by('vinculo_pessoa__pessoa__nome')

        apenas_alunos_bolsistas = request.GET.get('apenas_bolsistas')
        if apenas_alunos_bolsistas:
            if apenas_alunos_bolsistas == '1':
                participacoes = participacoes.filter(vinculo=TipoVinculo.BOLSISTA, bolsa_concedida=True)
            elif apenas_alunos_bolsistas == '2':
                participacoes = participacoes.filter(
                    vinculo=TipoVinculo.BOLSISTA, bolsa_concedida=True, vinculo_pessoa__tipo_relacionamento__model='servidor'
                )
            elif apenas_alunos_bolsistas == '3':
                participacoes = participacoes.filter(
                    vinculo=TipoVinculo.BOLSISTA, bolsa_concedida=True, vinculo_pessoa__tipo_relacionamento__model='aluno'
                )
        dados_do_projeto = get_lista_de_equipes(participacoes)
        total_projetos_encontrados = len(set(participacoes.values_list('projeto', flat=True)))
        if 'xls' in request.GET:
            return tasks.listar_equipes_dos_projetos_export_to_xls(participacoes)

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
        orcid = ''
        cpf = ''
        if participacao.vinculo_pessoa and not participacao.vinculo_pessoa.eh_aluno():
            if participacao.is_servidor():
                nome = participante.pessoa_fisica.nome
                cpf = participante.pessoa_fisica.cpf
                orcid = participante.pessoa_fisica.orcid
            else:
                nome = participante.nome
                cpf = participante.prestador.pessoa_fisica.cpf
        else:
            nome = participacao.get_nome()
            if participante:
                lattes = participante.pessoa_fisica.lattes
                orcid = participante.pessoa_fisica.orcid
                curso = participante.curso_campus
                cpf = participante.pessoa_fisica.cpf
        if participacao.responsavel:
            vinculo = 'Coordenador'
        else:
            vinculo = 'Membro'
        if participacao.vinculo == 'Bolsista' and participacao.bolsa_concedida:
            vinculo = vinculo + ' Bolsista'
        else:
            vinculo = vinculo + ' Não Bolsista'

        item = {
            'idprojeto': participacao.projeto.id,
            'projeto': participacao.projeto.titulo,
            'nome': nome,
            'lattes': lattes,
            'orcid': orcid,
            'matricula': matricula,
            'vinculo': vinculo,
            'ativo': ativo,
            'titulacao': titulacao,
            'curso': curso,
            'cpf': cpf,
            'edital': participacao.projeto.edital.titulo,
            'campus': participacao.projeto.uo.sigla,
            'ehcoordenador': participacao.responsavel,
            'em_duplicidade': em_duplicidade,
        }
        lista.append(item)
        pessoa_id_anterior = participacao.vinculo_pessoa and participacao.vinculo_pessoa.id or 0
    return lista


@rtr()
@permission_required('pesquisa.view_comissaoeditalpesquisa')
def lista_emails_comissao(request, comissao_id):
    comissao = get_object_or_404(ComissaoEditalPesquisa, pk=comissao_id)
    title = 'Lista de Emails dos Membros da Comissão'

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


@permission_required('pesquisa.add_origemrecursoedital')
def atualizar_curriculo_lattes(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    url = request.META.get('HTTP_REFERER', '.')
    return tasks.atualizar_curriculo_lattes(url, edital)


@permission_required('pesquisa.add_edital')
def gerenciar_bolsas_export_to_xls(request, projetos):
    return tasks.exportar_bolsas_para_xls(projetos)


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def cancelar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_cancelar_projeto():
        raise PermissionDenied
    title = 'Cancelar Projeto'
    form = CancelarProjetoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.data_solicitacao = datetime.datetime.now()
        o.save()
        return httprr('..', 'Solicitação encaminhada para análise.')
    return locals()


@rtr()
@permission_required('pesquisa.view_edital')
def solicitacoes_de_cancelamento(request):
    title = 'Projetos com Solicitações de Cancelamento'
    projetos_cancelados = ProjetoCancelado.objects.filter(
        projeto__edital__tipo_edital__in=(Edital.PESQUISA, Edital.INOVACAO, Edital.PESQUISA_INOVACAO_CONTINUO),
        projeto__data_conclusao_planejamento__isnull=False,
    )
    if request.user.has_group_cached('Coordenador de Pesquisa'):
        projetos_cancelados = projetos_cancelados.filter(projeto__uo=get_uo(request.user))
    form = EditaisPesquisaForm(request.GET or None, request=request)
    if form.is_valid():
        if form.cleaned_data.get('edital'):
            projetos_cancelados = projetos_cancelados.filter(projeto__edital=form.cleaned_data['edital'])
        if form.cleaned_data.get('situacao'):
            if form.cleaned_data.get('situacao') == EditaisPesquisaForm.PENDENTES_ACEITE:
                projetos_cancelados = projetos_cancelados.filter(data_avaliacao__isnull=True)
            elif form.cleaned_data.get('situacao') == EditaisPesquisaForm.PENDENTES_VALIDACAO:
                projetos_cancelados = projetos_cancelados.filter(data_validacao__isnull=True, parecer_favoravel=True)
            elif form.cleaned_data.get('situacao') == EditaisPesquisaForm.PARECER_FAVORAVEL:
                projetos_cancelados = projetos_cancelados.filter(parecer_favoravel=True)
            elif form.cleaned_data.get('situacao') == EditaisPesquisaForm.VALIDADO:
                projetos_cancelados = projetos_cancelados.filter(cancelado=True, parecer_favoravel=True, data_validacao__isnull=False)
    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_cancelamento_projeto')
def avaliar_cancelamento_projeto(request: HttpRequest, cancelamento_id: int) -> dict | HttpResponse:
    pedido_cancelamento = get_object_or_404(ProjetoCancelado, pk=cancelamento_id)
    # mesmo recorte da lista (`solicitacoes_de_cancelamento`): o Coordenador de Pesquisa só avalia o do campus dele (#17520)
    if request.user.has_group_cached('Coordenador de Pesquisa') and pedido_cancelamento.projeto.uo != get_uo(request.user):
        raise PermissionDenied
    title = 'Avaliar Cancelamento do Projeto'

    form = AvaliarCancelamentoProjetoForm(request.POST or None, instance=pedido_cancelamento)
    if form.is_valid():
        o = form.save(False)
        o.projeto = pedido_cancelamento.projeto
        o.data_avaliacao = datetime.datetime.now()
        o.avaliador = request.user.get_relacionamento()
        o.save()
        if o.cancelado is True:
            participantes = Participacao.ativos.filter(projeto=pedido_cancelamento.projeto, vinculo='Bolsista')
            for participante in participantes:
                if not participante.is_servidor():
                    participante.gerencia_bolsa_ae()

        return httprr('/pesquisa/solicitacoes_de_cancelamento/', 'Cancelamento avaliado com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def enviar_recurso(request, projeto_id):
    title = 'Enviar Recurso'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if not projeto.pode_enviar_recurso():
        raise PermissionDenied

    form = RecursoPesquisaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto
        o.data_solicitacao = datetime.datetime.now()
        o.save()
        return httprr(f'/pesquisa/projeto/{projeto.id}', 'Recurso encaminhado para análise.')
    return locals()


def _verificar_campus_recurso(request: HttpRequest, recurso: RecursoProjeto) -> None:
    # mesmo recorte da lista (`solicitacoes_de_recurso`): fora Diretor de Pesquisa e Auditor, só o campus do projeto (#17563)
    if not request.user.has_group_cached(['Diretor de Pesquisa', 'Auditor']) and recurso.projeto.uo != get_uo(request.user):
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_edital')
def avaliar_recurso_projeto(request: HttpRequest, recurso_id: int) -> dict | HttpResponse:
    projeto = get_object_or_404(RecursoProjeto, pk=recurso_id)
    _verificar_campus_recurso(request, projeto)
    # validado, a lista não oferece mais "Editar Avaliação" (`RecursoProjeto.get_opcoes`)
    if projeto.data_validacao:
        raise PermissionDenied
    title = 'Avaliar Recurso'
    form = AvaliarRecursoProjetoForm(request.POST or None, instance=projeto)
    if form.is_valid():
        o = form.save(False)
        o.projeto = projeto.projeto
        o.data_avaliacao = datetime.datetime.now()
        o.avaliador = request.user.get_relacionamento()
        o.save()

        return httprr('/pesquisa/solicitacoes_de_recurso/', 'Recurso avaliado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_origemrecursoedital')
def validar_recurso_projeto(request, recurso_id):
    projeto = get_object_or_404(RecursoProjeto, pk=recurso_id)
    title = 'Validar Recurso'
    form = ValidarRecursoProjetoForm(request.POST or None, instance=projeto)
    if form.is_valid():
        o = form.save(False)
        o.data_validacao = datetime.datetime.now()
        o.validador = request.user.get_relacionamento()
        o.save()
        if form.cleaned_data['aprovar_projeto'] is True:
            projeto.aprovado = True
            projeto.save()
        return httprr('/pesquisa/solicitacoes_de_recurso/', 'Recurso validado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.view_edital')
def solicitacoes_de_recurso(request):
    title = 'Projetos com Solicitações de Recurso'
    if request.user.has_group_cached(['Diretor de Pesquisa', 'Auditor']):
        projetos_com_recurso = RecursoProjeto.objects.filter(
            projeto__edital__tipo_edital__in=(Edital.PESQUISA, Edital.INOVACAO, Edital.PESQUISA_INOVACAO_CONTINUO),
            projeto__data_conclusao_planejamento__isnull=False,
        )
    else:
        projetos_com_recurso = RecursoProjeto.objects.filter(
            projeto__uo=get_uo(request.user), projeto__edital__tipo_edital__in=(Edital.PESQUISA, Edital.INOVACAO, Edital.PESQUISA_INOVACAO_CONTINUO)
        )
    form = EditaisPesquisaForm(request.GET or None, request=request)
    if form.is_valid():
        if form.is_valid():
            if form.cleaned_data.get('ano'):
                projetos_com_recurso = projetos_com_recurso.filter(data_solicitacao__year=form.cleaned_data['ano'])
            if form.cleaned_data.get('edital'):
                projetos_com_recurso = projetos_com_recurso.filter(projeto__edital=form.cleaned_data['edital'])
            if form.cleaned_data.get('situacao'):
                if form.cleaned_data.get('situacao') == EditaisPesquisaForm.PENDENTES_ACEITE:
                    projetos_com_recurso = projetos_com_recurso.filter(data_avaliacao__isnull=True)
                elif form.cleaned_data.get('situacao') == EditaisPesquisaForm.PENDENTES_VALIDACAO:
                    projetos_com_recurso = projetos_com_recurso.filter(data_validacao__isnull=True, parecer_favoravel=True)
                elif form.cleaned_data.get('situacao') == EditaisPesquisaForm.PARECER_FAVORAVEL:
                    projetos_com_recurso = projetos_com_recurso.filter(parecer_favoravel=True)
                elif form.cleaned_data.get('situacao') == EditaisPesquisaForm.VALIDADO:
                    projetos_com_recurso = projetos_com_recurso.filter(aceito=True, parecer_favoravel=True, data_validacao__isnull=False)

    return locals()


@rtr()
@permission_required('pesquisa.view_edital')
def recurso_projeto(request: HttpRequest, recurso_id: int) -> dict:
    recurso = get_object_or_404(RecursoProjeto, pk=recurso_id)
    _verificar_campus_recurso(request, recurso)
    return locals()


@rtr()
@permission_required('pesquisa.pode_se_tornar_avaliador')
def emitir_declaracao_avaliador(request):
    title = 'Declarações'
    projetos_avaliados = (
        Avaliacao.objects.filter(
            projeto__edital__tipo_edital__in=[Edital.PESQUISA, Edital.INOVACAO, Edital.PESQUISA_INOVACAO_CONTINUO], vinculo=request.user.get_vinculo()
        )
        .values('projeto__edital__titulo', 'projeto__edital')
        .annotate(total=Count('projeto'))
        .order_by('-projeto__edital')
    )

    return locals()


@documento('Declaração de Avaliador', forcar_recriacao=True, enumerar_paginas=False, modelo='pesquisa.edital')
@rtr()
@permission_required('pesquisa.pode_se_tornar_avaliador')
def emitir_declaracao_avaliador_pdf(request: HttpRequest, pk: int) -> dict:
    edital = get_object_or_404(Edital, pk=pk)
    vinculo = request.user.get_vinculo()
    nome = vinculo.pessoa.nome
    hoje = datetime.datetime.now()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
    meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    mes = meses[hoje.month - 1]
    ano = edital.inicio_inscricoes.year
    projetos = Avaliacao.objects.filter(projeto__edital=edital, vinculo=vinculo)
    if not projetos.exists():
        raise PermissionDenied
    cidade = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
    if edital.campus_especifico and projetos.exists():
        cidade = projetos[0].projeto.uo.municipio.nome
    projetos_avaliados = projetos.values('projeto__area_conhecimento', 'projeto__area_conhecimento__descricao').annotate(
        total=Count('projeto__area_conhecimento')
    )
    dados = []
    cpf = vinculo.relacionamento.pessoa_fisica.cpf and anonimizar_cpf(vinculo.relacionamento.pessoa_fisica.cpf)
    for projeto in projetos_avaliados:
        dados.append([projeto['projeto__area_conhecimento__descricao'], projeto['total']])

    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def resultado_edital(request):
    title = 'Editais com Resultados Disponíveis'
    hoje = datetime.datetime.now()
    editais = Edital.objects.filter(divulgacao_selecao__lt=hoje, data_avaliacao_classificacao__isnull=False).order_by('-divulgacao_selecao')
    form = AnoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            ano = int(form.cleaned_data['ano'])
            editais = editais.filter(inicio_inscricoes__year=ano)
    return locals()


@rtr('pesquisa/templates/distribuir_bolsas.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
def resultado_edital_parcial(request):
    title = 'Editais com Resultados Parciais Disponíveis'
    hoje = datetime.datetime.now()
    editais = Edital.objects.filter(divulgacao_selecao__gt=hoje, fim_selecao__lt=hoje).filter(fim_selecao__lt=F('data_avaliacao_classificacao'))
    edital_parcial = True
    return locals()


@rtr()
def divulgar_resultado_edital(self, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tabela = {}
    resultado = {}
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
    if edital.tem_formato_completo() and edital.pode_divulgar_resultado_pesquisa():
        if edital.forma_selecao == Edital.GERAL:
            projetos = Projeto.objects.filter(
                edital=edital, pre_aprovado=True, aprovado=True, aprovado_posteriormente=False, aceita_sem_fomento=None
            ).order_by('-pontuacao_total', '-pontuacao')
            tabela['Geral'] = []
            for projeto in projetos:
                tabela['Geral'].append(projeto)
        else:
            projetos = Projeto.objects.filter(
                edital=edital, pre_aprovado=True, aprovado=True, aprovado_posteriormente=False, aceita_sem_fomento=None
            ).order_by('uo__sigla', '-pontuacao_total', '-pontuacao')
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def divulgar_resultado_edital_parcial(request, edital_id, campus_id=None):
    title = 'Resultado Parcial'

    qtd_bolsa_pesquisador_distribuida = 0
    qtd_bolsa_ic_distribuida = 0
    qtd_bolsa_pesquisador_solicitada = 0
    qtd_bolsa_ic_solicitada = 0
    edital = get_object_or_404(Edital, pk=edital_id)
    titulo_box = edital.titulo
    hoje = datetime.datetime.now()
    if (
        edital.divulgacao_selecao > hoje
        and edital.fim_selecao < hoje
        and edital.data_avaliacao_classificacao
        and edital.fim_selecao < edital.data_avaliacao_classificacao
    ):
        if edital.tem_formato_completo():
            campus = None
            if edital.forma_selecao == Edital.GERAL:
                projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('-pontuacao_total')
            else:
                campus = get_object_or_404(UnidadeOrganizacional, id=campus_id)
                titulo_box += f' - Campus {campus}'
                projetos = Projeto.objects.filter(edital=edital, uo=campus, pre_aprovado=True).order_by('-pontuacao_total')
            if projetos:
                if edital.forma_selecao == Edital.CAMPUS and edital.bolsadisponivel_set.filter(uo=campus):
                    qtd_bolsa_pesquisador = edital.bolsadisponivel_set.get(uo=campus).num_maximo_pesquisador
                    qtd_bolsa_ic = edital.bolsadisponivel_set.get(uo=campus).num_maximo_ic
                    participacoes = Participacao.objects.filter(projeto__in=projetos.values_list('id', flat=True)).order_by('vinculo')
                elif edital.forma_selecao == Edital.GERAL:
                    qtd_bolsa_pesquisador = edital.qtd_bolsa_servidores
                    qtd_bolsa_ic = edital.qtd_bolsa_alunos
                    participacoes = Participacao.objects.filter(projeto__in=projetos.values_list('id', flat=True)).order_by('vinculo')
                for participacao in participacoes:
                    if participacao.is_servidor():
                        if participacao.vinculo == TipoVinculo.BOLSISTA:
                            qtd_bolsa_pesquisador_solicitada = qtd_bolsa_pesquisador_solicitada + 1
                        if participacao.bolsa_concedida is True and participacao.vinculo == TipoVinculo.BOLSISTA:
                            qtd_bolsa_pesquisador_distribuida = qtd_bolsa_pesquisador_distribuida + 1
                    else:
                        if participacao.vinculo == TipoVinculo.BOLSISTA:
                            qtd_bolsa_ic_solicitada = qtd_bolsa_ic_solicitada + 1
                        if participacao.bolsa_concedida is True and participacao.vinculo == TipoVinculo.BOLSISTA:
                            qtd_bolsa_ic_distribuida = qtd_bolsa_ic_distribuida + 1
                saldo_bolsa_pesquisador = qtd_bolsa_pesquisador - qtd_bolsa_pesquisador_distribuida
                saldo_bolsa_ic = qtd_bolsa_ic - qtd_bolsa_ic_distribuida
        return locals()
    else:
        raise PermissionDenied


@documento('Declaração de Participação', enumerar_paginas=False, modelo='pesquisa.participacao', forcar_recriacao=True)
@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def emitir_declaracao_participacao_pdf(self, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_declaracao_de_participacao():
        return httprr('/', 'Você não tem permissão para ver isso.', 'error')
    carga_horaria = participacao.carga_horaria
    participante = participacao.get_participante()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
    fim_projeto = participacao.projeto.fim_execucao
    inicio_projeto = participacao.projeto.inicio_execucao
    historico = (
        HistoricoEquipe.objects.filter(participante=participacao)
        .order_by('id')
        .exclude(data_movimentacao__gte=F('data_movimentacao_saida'))
        .exclude(movimentacao='Ativado')
        .exclude(data_movimentacao__gt=fim_projeto)
        .exclude(data_movimentacao_saida__lt=inicio_projeto)
        .exclude(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)
    )
    tipo_projeto = 'pesquisa'

    eh_aluno = False
    possui_bolsa = False
    if participacao.vinculo == TipoVinculo.BOLSISTA and participacao.bolsa_concedida:
        possui_bolsa = True

    eh_coordenador = False
    eh_externo = False
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
        logradouro = participante.pessoa_fisica.endereco_logradouro
        bairro = participante.pessoa_fisica.endereco_bairro
        cidade = participante.pessoa_fisica.endereco_municipio

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

        vinculo = 'membro'
    else:
        eh_externo = True
        nome = participante.nome
        cpf = participante.prestador.pessoa_fisica.cpf and anonimizar_cpf(participante.prestador.pessoa_fisica.cpf)
        rg = participante.prestador.pessoa_fisica.rg
        rg_orgao = participante.prestador.pessoa_fisica.rg_orgao
        rg_uf = participante.prestador.pessoa_fisica.rg_uf
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

    return locals()


@rtr()
@permission_required('pesquisa.add_origemrecursoedital')
def validar_cancelamento_projeto(request, projeto_id):
    pedido_cancelamento = get_object_or_404(ProjetoCancelado, pk=projeto_id)
    title = 'Validar Cancelamento'
    form = ValidarCancelamentoProjetoForm(request.POST or None, instance=pedido_cancelamento)
    if form.is_valid():
        o = form.save(False)
        o.data_validacao = datetime.datetime.now()
        o.validador = request.user.get_relacionamento()
        o.save()
        if o.cancelado is True:
            participantes = Participacao.ativos.filter(projeto=pedido_cancelamento.projeto, vinculo='Bolsista')
            for participante in participantes:
                if not participante.is_servidor():
                    participante.gerencia_bolsa_ae()

            if form.cleaned_data['aprova_proximo'] == 'True':
                if pedido_cancelamento.projeto.edital.forma_selecao == Edital.GERAL:
                    proximo_projeto = Projeto.objects.filter(edital=pedido_cancelamento.projeto.edital, aprovado=False).order_by('-pontuacao_total')
                else:
                    proximo_projeto = Projeto.objects.filter(
                        edital=pedido_cancelamento.projeto.edital, uo=pedido_cancelamento.projeto.uo, aprovado=False
                    ).order_by('-pontuacao_total')

                if proximo_projeto.exists():
                    o.proximo_projeto = proximo_projeto[0]
                    o.save()
                    projeto = proximo_projeto[0]
                    projeto.aprovado = True
                    projeto.save()

                    responsavel = Participacao.objects.get(projeto__id=projeto.id, responsavel=True)
                    titulo = '[SUAP] Pesquisa: Aprovação de Projeto'
                    texto = (
                        '<h1>Pesquisa</h1>'
                        '<h2>Aprovação de Projeto</h2>'
                        f"<p>O projeto '{projeto.titulo}' foi aprovado em decorrência de uma desistência.</p>"
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [responsavel.vinculo_pessoa])

        return httprr('/pesquisa/solicitacoes_de_cancelamento/', 'Solicitação de cancelamento validado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def deletar_participante(request, participacao_id):
    url = request.META.get('HTTP_REFERER', '.')
    participante = get_object_or_404(Participacao, pk=participacao_id)
    projeto = participante.projeto
    if not projeto.is_coordenador(request.user) or not participante.pode_remover_participacao():
        raise PermissionDenied
    eh_responsavel = Etapa.objects.filter(meta__projeto=projeto, responsavel=participante).first()
    if eh_responsavel:
        return httprr(
            url,
            f'O participante é o responsável por uma atividade e não pode ser removido. Meta: {eh_responsavel.meta.ordem} - Etapa: {eh_responsavel.ordem}',
            tag='error',
        )
    eh_integrante = Etapa.objects.filter(meta__projeto=projeto, integrantes__in=[participante.id]).first()
    if eh_integrante:
        return httprr(
            url,
            f'O participante está vinculado a uma atividade e não pode ser removido. Meta: {eh_integrante.meta.ordem} - Etapa: {eh_integrante.ordem}',
            tag='error',
        )
    ProjetoAnexo.objects.filter(projeto=projeto, vinculo_membro_equipe=participante.vinculo_pessoa).delete()
    if projeto.auxiliar and projeto.auxiliar == participante.vinculo_pessoa:
        projeto.auxiliar = None
        projeto.save()
    participante.delete()
    return httprr(url, 'Participante removido com sucesso.')


@rtr()
@permission_required('pesquisa.add_edital')
def gerenciar_supervisores(request):
    title = 'Gerenciar Supervisores'
    editais_com_projetos_nao_encerrados = Projeto.objects.filter(data_finalizacao_conclusao__isnull=True, aprovado=True).values_list(
        'edital__id', flat=True
    )
    editais = Edital.objects.filter(id__in=editais_com_projetos_nao_encerrados).order_by('-id')
    ano = request.GET.get('ano')
    form = GerenciarSupervisorForm(request.GET or None, ano=ano)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        ano = form.cleaned_data.get('ano')
        if ano:
            editais = editais.filter(inicio_inscricoes__year=ano)
        if edital:
            editais = editais.filter(id=edital.id)

    return locals()


@rtr()
@permission_required('pesquisa.add_edital')
def selecionar_supervisor(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Selecionar Supervisores - {edital.titulo}'
    if request.user.has_group_cached('Diretor de Pesquisa'):
        projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True)
    else:
        projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True, uo=get_uo(request.user))

    participacoes = Participacao.objects.filter(
        projeto__in=projetos.values_list('id', flat=True), projeto__vinculo_supervisor__id=F('vinculo_pessoa__id'), projeto__aprovado=True
    )
    com_avaliador_externo = projetos.filter(vinculo_supervisor__in=AvaliadorExterno.objects.all().values_list('vinculo', flat=True))
    com_conflito = projetos.filter(id__in=participacoes.values_list('projeto', flat=True)).order_by('uo', 'titulo')
    projetos = com_conflito | com_avaliador_externo

    form = SupervisorForm(request.POST or None)
    if form.is_valid():
        palavra_chave = form.cleaned_data['palavra_chave']
        uo = form.cleaned_data['uo']
        situacao = form.cleaned_data.get('situacao')
        if situacao:
            if int(situacao) == 0:
                if request.user.has_perm('pesquisa.tem_acesso_sistemico'):
                    projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True)
                else:
                    projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True, aprovado=True, uo=get_uo(request.user))
        if uo:
            projetos = projetos.filter(uo__id=uo.id)

        if palavra_chave:
            projetos = projetos.filter(vinculo_supervisor__pessoa__nome__icontains=palavra_chave)

    return locals()


@rtr()
@permission_required('pesquisa.add_edital')
def selecionar_supervisor_do_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.uo != get_uo(request.user) and not request.user.has_perm('pesquisa.tem_acesso_sistemico'):
        return httprr(
            f'/pesquisa/selecionar_supervisor/{projeto.edital_id}/', 'Você só pode indicar supervisores para projetos do seu campus.', tag='error'
        )

    title = 'Indicar Supervisor'
    grupo = Group.objects.get(name='Supervisor de Projetos de Pesquisa')

    form = AdicionarUsuarioGrupoForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            projeto.vinculo_supervisor = usuario.get_vinculo()
            usuario.groups.add(grupo)
            projeto.save()
        return httprr('..', 'Supervisor cadastrado com sucesso.')
    return locals()


@documento('Certificado de Participação', enumerar_paginas=False, modelo='pesquisa.participacao', forcar_recriacao=True)
@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def emitir_certificado_pdf(request, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_certificado_de_participacao():
        return httprr('/', 'Você não tem permissão para este acesso.', 'error')
    else:
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
        hoje = datetime.datetime.now()
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes = meses[hoje.month - 1]

        title = str(participacao.projeto)
        movimentacao = HistoricoEquipe.objects.filter(participante=pk).order_by('id')
        identificador = 'matrícula'
        if participacao.vinculo_pessoa.eh_prestador():
            if participacao.vinculo_pessoa.relacionamento.pessoa_fisica.cpf:
                identificador = 'CPF'
            else:
                identificador = 'Passaporte'
        if movimentacao:
            como_coordenador = movimentacao.filter(categoria=HistoricoEquipe.COORDENADOR)
            como_membro = movimentacao.filter(categoria=HistoricoEquipe.MEMBRO)
            if movimentacao.filter(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE).exists():
                data_inativacao = movimentacao.filter(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)[0].data_movimentacao
                como_coordenador = como_coordenador.exclude(data_movimentacao__gte=data_inativacao)
                como_membro = como_membro.exclude(data_movimentacao__gte=data_inativacao)

            if como_coordenador.exists() or como_membro.exists():
                return locals()
            else:
                return httprr(f'/pesquisa/projeto/{participacao.projeto_id}/', 'Não existe certificado disponível para este participante.', 'error')

        else:
            return httprr(f'/pesquisa/projeto/{participacao.projeto_id}/', 'Não existe movimentação para este participante.', 'error')


@documento('Declaração de Orientação', enumerar_paginas=False, modelo='pesquisa.participacao', forcar_recriacao=True)
@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def emitir_declaracao_orientacao_pdf(request, pk):
    participacao = get_object_or_404(Participacao, pk=pk)
    if not participacao.pode_emitir_declaracao_orientacao():
        return httprr('/', 'Você não tem permissão para este acesso.', 'error')
    else:
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
        hoje = datetime.datetime.now()
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes = meses[hoje.month - 1]

        title = str(participacao.projeto)
        participante = participacao.get_participante()
        nome = participacao.get_nome()
        eh_aluno = None
        eh_servidor = participacao.projeto.vinculo_coordenador.eh_servidor()
        if not eh_servidor:
            eh_aluno = participacao.projeto.vinculo_coordenador.eh_aluno()
        if eh_servidor:
            matricula = participante.matricula
            cpf = participante.pessoa_fisica.cpf and anonimizar_cpf(participante.pessoa_fisica.cpf)
            rg = participante.pessoa_fisica.rg
            rg_orgao = participante.pessoa_fisica.rg_orgao
            rg_uf = participante.pessoa_fisica.rg_uf
            logradouro = participante.pessoa_fisica.endereco_logradouro
            bairro = participante.pessoa_fisica.endereco_bairro
            cidade = participante.pessoa_fisica.endereco_municipio
        elif eh_aluno:
            matricula = participante.matricula
            cpf = participante.pessoa_fisica.cpf and anonimizar_cpf(participante.pessoa_fisica.cpf)
            rg = participante.numero_rg
            rg_orgao = participante.orgao_emissao_rg
            rg_uf = participante.uf_emissao_rg
            logradouro = participante.logradouro
            bairro = participante.bairro
            cidade = participante.cidade
        else:
            matricula = None
            cpf = participante.prestador.pessoa_fisica.cpf and anonimizar_cpf(participante.prestador.pessoa_fisica.cpf)
            rg = participante.prestador.pessoa_fisica.rg
            rg_orgao = participante.prestador.pessoa_fisica.rg_orgao
            rg_uf = participante.prestador.pessoa_fisica.rg_uf
            logradouro = participante.prestador.pessoa_fisica.endereco_logradouro
            bairro = participante.prestador.pessoa_fisica.endereco_bairro
            cidade = participante.prestador.pessoa_fisica.endereco_municipio

        vinculo = 'coordenador(a)'
        alunos = participacao.projeto.get_participacoes_alunos()
        em_execucao = participacao.projeto.get_status() == Projeto.STATUS_EM_EXECUCAO
        if not alunos:
            return httprr('/', 'Não existem alunos neste projeto.', 'error')

    return locals()


@rtr()
@permission_required('pesquisa.view_edital')
def listar_projetos_em_atraso(request):
    title = 'Lista de Projetos em Atraso'
    form = ProjetosAtrasadosForm(request.GET or None, request=request)
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos = (
        Projeto.objects.filter(pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False)
        .exclude(id__in=projetos_cancelados)
        .order_by('fim_execucao')
    )
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
@permission_required('pesquisa.tem_acesso_sistemico')
def cancelar_avaliacao_execucao_etapa(request, registro_id):
    title = 'Cancelar Avaliação de Execução de Etapa'
    registro = get_object_or_404(RegistroExecucaoEtapa, pk=registro_id)
    form = CancelarAvaliacaoEtapaForm(request.POST or None, instance=registro)
    if form.is_valid():
        o = form.save(False)
        o.avaliacao_cancelada_em = datetime.datetime.now()
        o.avaliacao_cancelada_por = request.user.get_relacionamento()
        o.dt_avaliacao = None
        o.avaliador = None
        o.aprovado = False
        o.save()
        return httprr(f'/pesquisa/validar_execucao_etapa/{registro.etapa.meta.projeto_id}/?tab=metas', 'Avaliação cancelada com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
def cancelar_avaliacao_execucao_gasto(request, registro_id):
    title = 'Cancelar Avaliação de Registro de Gasto'
    registro = get_object_or_404(RegistroGasto, pk=registro_id)
    form = CancelarAvaliacaoGastoForm(request.POST or None, instance=registro)
    if form.is_valid():
        o = form.save(False)
        o.avaliacao_cancelada_em = datetime.datetime.now()
        o.avaliacao_cancelada_por = request.user.get_relacionamento()
        o.dt_avaliacao = None
        o.avaliador = None
        o.aprovado = False
        o.justificativa_reprovacao = None
        o.save()
        return httprr(f'/pesquisa/validar_execucao_etapa/{registro.desembolso.projeto_id}/?tab=gastos', 'Avaliação cancelada com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.add_origemrecursoedital, pesquisa.pode_ver_config_edital')
def relatorio_indicadores(request):
    title = 'Indicadores'
    form = IndicadoresForm(request.GET or None, request=request)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        indicador = form.cleaned_data.get('indicador')
        ano_inicio = form.cleaned_data.get('ano_inicio')
        ano_fim = form.cleaned_data.get('ano_fim')

        plot_options = {'series': {'dataLabels': {'enabled': True}}}
        grafico_opcao = {'plotOptions': plot_options}
        titulo_grafico = dict(form.INDICADORES_CHOICES)[indicador]

        titulo_box = []
        titulo_box.append(dict(form.INDICADORES_CHOICES)[indicador])
        if campus:
            titulo_box.append(str(campus))
        if ano_inicio and ano_fim:
            titulo_box.append(f'{ano_inicio} a {ano_fim}')
        elif ano_inicio:
            titulo_box.append(f'a partir de {ano_inicio}')
        elif ano_fim:
            titulo_box.append(f'até {ano_fim}')
        titulo_box = ' - '.join(titulo_box)

        dados_numero_de_participante = Participacao.get_dados_quantitativos_de_participantes(campus, ano_inicio, ano_fim)
        dados_numero_de_participante = Relatorio.ordernar(dados_numero_de_participante)

        graficos = []
        graficos.append(
            ColumnChart('grafico1', title='Quantidade de Participante', minPointLength=3, data=dados_numero_de_participante, **grafico_opcao)
        )

    return locals()


@rtr()
@permission_required('pesquisa.add_origemrecursoedital')
def refazer_distribuicao_bolsas(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    campus_id = request.GET.get('campus')

    if campus_id:
        oferta = get_object_or_404(BolsaDisponivel, uo=campus_id, edital=edital)
        oferta.data_avaliacao_classificacao = None
        oferta.save()
        Projeto.objects.filter(edital=edital, uo=campus_id, pre_aprovado=True).update(
            aprovado_posteriormente=False, aprovado_posteriormente_por=None, aprovado_posteriormente_em=None
        )
        return httprr(f'/pesquisa/gerenciar_bolsas/{edital_id}/{campus_id}/', 'Distribuição de Bolsas do campus refeita.')

    else:
        edital.data_avaliacao_classificacao = None
        edital.save()
        Projeto.objects.filter(edital=edital, pre_aprovado=True).update(
            aprovado_posteriormente=False, aprovado_posteriormente_por=None, aprovado_posteriormente_em=None
        )
        return httprr(f'/pesquisa/gerenciar_bolsas/{edital_id}/', 'Distribuição de Bolsas refeita.')


@rtr()
@permission_required('pesquisa.add_origemrecursoedital, pesquisa.pode_ver_config_edital, projetos.pode_gerenciar_edital')
def relatorio_quantitativo_docentes_por_campus(request):
    title = 'Quantitativo de Docentes por Campus'
    form = CampusForm(request.POST or None)
    tabela = {}
    uos = UnidadeOrganizacional.objects.uo().all().order_by('sigla')
    total = 0
    if form.is_valid():
        servidor = Servidor.objects.filter(data_exclusao_instituidor__isnull=True, ativo=True, eh_docente=True)
        if form.cleaned_data.get('uo'):
            uos = uos.filter(id=form.cleaned_data.get('uo').id)
        for uo in uos:
            chave = f'{uo.nome}'
            quantidade = servidor.filter(setor_lotacao__uo__equivalente=uo).count()
            tabela[chave] = quantidade
            total = total + quantidade

        resultado = collections.OrderedDict(sorted(tabela.items()))

    return locals()


@permission_required('pesquisa.pode_interagir_com_projeto')
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


@permission_required('pesquisa.pode_interagir_com_projeto')
def filtrar_editais_completos_por_ano(request):
    data = '[]'
    if request.method == 'GET':
        ano = request.GET.get('ano')
        if ano and ano != 'Selecione um ano':
            registro = Edital.objects.filter(formato=Edital.FORMATO_COMPLETO, inicio_inscricoes__year=ano).order_by('-inicio_inscricoes')
            if registro.exists():
                from django.core import serializers

                data = serializers.serialize('json', list(registro.all()), fields=('titulo', 'id'))
    return HttpResponse(data, content_type='application/json')


@permission_required('pesquisa.tem_acesso_sistemico')
def autorizar_edital(request: HttpRequest, edital_id: int, opcao: str) -> HttpResponse:
    edital = get_object_or_404(Edital, pk=edital_id)
    if request.user.has_group_cached('Diretor de Pesquisa') and edital.autorizado is None:
        if opcao == '1':
            edital.autorizado = True
        elif opcao == '2':
            edital.autorizado = False
        else:
            # opção inválida gravava quem autorizou e quando, com `autorizado` vazio (#17551)
            raise Http404
        edital.autorizado_por_vinculo = request.user.get_vinculo()
        edital.autorizado_em = datetime.datetime.now()
        edital.save()
        return httprr('/admin/pesquisa/edital/', 'Edital avaliado com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editais(request):
    title = 'Editais'
    editais = Edital.objects.filter(publicado=True).order_by('-inicio_inscricoes')
    form = EditaisForm(request.GET or None)
    if form.is_valid():
        ano = form.cleaned_data.get('ano')
        uo = form.cleaned_data.get('uo')
        if ano and ano != 'Selecione um ano':
            editais = editais.filter(inicio_inscricoes__year=ano)
        if uo:
            editais = editais.filter(id__in=BolsaDisponivel.objects.filter(uo=uo).values_list('edital', flat=True))
        periodo = form.cleaned_data.get('periodo')
        if periodo:
            if periodo == EditaisForm.INSCRICAO:
                editais = editais.em_inscricao()
            elif periodo == EditaisForm.PRE_SELECAO:
                editais = editais.em_pre_avaliacao()
            elif periodo == EditaisForm.SELECAO:
                editais = editais.em_selecao()
            elif periodo == EditaisForm.EXECUCAO:
                editais = editais.em_execucao()
            elif periodo == EditaisForm.CONCLUIDO:
                editais = editais.concluidos()
        editais = editais.order_by('-inicio_inscricoes')

    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def editais_abertos_submissao_obra(request):
    title = 'Editais Abertos para Submissão de Publicação'
    agora = datetime.datetime.now()
    editais = EditalSubmissaoObra.objects.filter(data_inicio_submissao__lte=agora, data_termino_submissao__gte=agora)

    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def submeter_obra(request, edital_id):
    edital = get_object_or_404(EditalSubmissaoObra, pk=edital_id)
    title = f'Submeter Publicação: {edital.titulo}'
    eh_publicacao_obra = edital.tipo == EditalSubmissaoObra.OBRA
    instance = Obra()
    instance.edital = edital
    if edital.tipo == EditalSubmissaoObra.OBRA:
        form = SubmeterObraForm(request.POST or None, request.FILES or None, instance=instance, request=request)
    else:
        instance.tipo_autor = Obra.ORGANIZADOR
        form = SubmeterPublicacaoEventoForm(request.POST or None, request.FILES or None, instance=instance, request=request)
    if form.is_valid():
        o = form.save(False)
        if request.user.is_authenticated:
            o.submetido_por_vinculo = request.user.get_vinculo()
            if form.cleaned_data.get('eh_autor_organizador'):
                o.responsavel_vinculo = request.user.get_vinculo()
        o.submetido_em = datetime.datetime.now()
        o.save()
        if not eh_publicacao_obra:
            MembroObra.objects.create(
                obra=o,
                tipo_autor=Obra.ORGANIZADOR,
                nome=form.cleaned_data.get('nome'),
                telefone=form.cleaned_data.get('telefone'),
                email=form.cleaned_data.get('email'),
            )

        titulo = '[SUAP] Editora: Nova publicação submetida'
        texto = (
            '<h1>Pesquisa</h1>'
            '<h2>Editora</h2>'
            f"<p>A publicação '{o.titulo}' acaba de ser submetida no SUAP.</p>"
            f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{o.id}/">{settings.SITE_URL}/pesquisa/obra/{o.id}/</a></p>'
        )
        lista_integrantes = []
        for membro in UsuarioGrupo.objects.filter(group__name='Integrante da Editora'):
            lista_integrantes.append(membro.user.get_vinculo())
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, lista_integrantes)

        return httprr(f'/pesquisa/obra/{form.instance.id}/', 'Publicação submetida com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    title = f'Publicação: {obra.titulo}'
    edital = obra.edital
    eh_publicacao_obra = edital.tipo == EditalSubmissaoObra.OBRA
    vinculo = request.user.get_vinculo()
    pessoa_fisica = request.user.get_profile()
    eh_autor = vinculo == obra.submetido_por_vinculo
    eh_sistemico = request.user.has_perm('pesquisa.add_linhaeditorial')
    eh_conselheiro = vinculo == obra.julgamento_conselho_realizado_por_vinculo
    eh_parecerista = ParecerObra.objects.filter(parecer_realizado_por_vinculo=vinculo, obra=obra, recusou_indicacao=False).exists()
    eh_revisor = vinculo == obra.revisao_realizada_por_vinculo
    eh_diagramador = vinculo == obra.diagramacao_realizada_por_vinculo
    eh_bibliotecario = request.user.has_group_cached('Bibliotecário da Pesquisa')
    pode_gerenciar_termos = (eh_autor and not obra.foi_assinada()) or request.user.has_perm('pesquisa.add_editalsubmissaoobra')
    autores = MembroObra.objects.filter(obra=obra)
    pode_ver_aba_conselho = eh_sistemico or eh_conselheiro or (eh_autor and obra.situacao_conselho_editorial == Obra.FAVORAVEL_COM_RESSALVAS)
    form = VerificaAutenticidadeForm(request.POST or None, instance=obra)
    aceiteform = AceiteEditoraForm(request.POST or None, instance=obra)
    uploadtermosform = UploadTermosForm(request.POST, request.FILES, instance=obra)
    publicacaoform = PublicacaoObraForm(request.POST or None, instance=obra, request=request)
    analiseliberacaoform = AnaliseLiberacaoForm(request.POST or None, instance=obra)
    aceitou_indicacao = ParecerObra.objects.filter(
        obra=obra, parecer_realizado_por_vinculo=request.user.get_vinculo(), aceitou_indicacao=True
    ).exists()
    if form.is_valid():
        o = form.save(False)
        o.autenticidade_verificada_por_vinculo = vinculo
        o.autenticidade_verificada_em = datetime.datetime.now()
        if form.cleaned_data.get('autentica') == obra.NAO:
            o.situacao = obra.CANCELADA
            o.cancelada_por_vinculo = vinculo
            o.cancelada_em = datetime.datetime.now()
        else:
            o.situacao = obra.AUTENTICA
        o.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=verificacao_autenticidade', 'Verificação de autenticidade realizada com sucesso.')

    if 'status_obra' in request.POST and aceiteform.is_valid():
        o = aceiteform.save(False)
        o.aceita_editora_realizada_por_vinculo = vinculo
        o.aceita_editora_realizada_em = datetime.datetime.now()
        if aceiteform.cleaned_data.get('status_obra') == Obra.HABILITADA:
            if eh_publicacao_obra:
                o.situacao = obra.ACEITA
            else:
                o.termo_autorizacao_publicacao_assinado = Obra.SIM
                o.termo_cessao_direitos_autorais_assinado = Obra.SIM
                o.situacao = obra.ASSINADA
        else:
            o.situacao = obra.CANCELADA
            o.cancelada_por_vinculo = vinculo
            o.cancelada_em = datetime.datetime.now()
        o.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=aceite', 'Avaliação da editora realizada com sucesso.')

    if (
        'termo_autorizacao_publicacao' in request.POST
        or 'termo_cessao_direitos_autorais' in request.POST
        or 'termo_uso_imagem' in request.POST
        or 'termo_nome_menor' in request.POST
        or 'contrato_cessao_direitos' in request.POST
        or 'termo_autorizacao_uso_imagem' in request.POST
    ) and uploadtermosform.is_valid():
        uploadtermosform.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=termos', 'Envio dos termos realizado com sucesso.')

    if ('situacao_publicacao' in request.POST or 'data_liberacao_repositorio_virtual' in request.POST) and publicacaoform.is_valid():
        o = publicacaoform.save(False)
        if o.situacao_publicacao == Obra.CATALOGADA:
            o.situacao = Obra.CORRIGIDA
        o.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=publicacao', 'Dados da publicação registrados com sucesso.')

    if 'aprovacao_liberacao_publicacao' in request.POST and analiseliberacaoform.is_valid():
        o = analiseliberacaoform.save(False)
        if analiseliberacaoform.cleaned_data.get('aprovacao_liberacao_publicacao') == Obra.SIM:
            o.situacao = obra.LIBERADA
        o.save()
        return httprr(f'/pesquisa/obra/{obra.id}/', 'Análise da liberação da obra realizada com sucesso.')
    tem_ficha_avaliacao = ItemAvaliacaoObra.objects.filter(parecer__obra=obra).exists()
    registro_avaliacao = ParecerObra.objects.filter(aceitou_indicacao=True, parecer_realizado_por_vinculo=vinculo, obra=obra)
    ja_aceitou_indicacao = registro_avaliacao.exists()
    ja_avaliou = registro_avaliacao.filter(parecer_realizado_em__isnull=False).exists()
    tem_coautores = MembroObra.objects.filter(obra=obra).exists()
    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def minhas_obras(request):
    title = 'Minhas Submissões'
    obras = Obra.objects.filter(submetido_por_vinculo=request.user.get_vinculo())
    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def adicionar_autor_obra(request, obra_id, vinculo_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.submetido_por_vinculo and obra.pode_cadastrar_autores():
        if vinculo_id == 1:
            titulo = 'Autor'
        elif vinculo_id == 2:
            titulo = 'Organizador'
        else:
            titulo = 'Coautor'
        title = f'Adicionar {titulo} - {obra.titulo}'
        form = MembroObraForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.obra = obra
            if vinculo_id == 1:
                o.tipo_autor = MembroObra.AUTOR
            elif vinculo_id == 2:
                o.tipo_autor = MembroObra.ORGANIZADOR
            else:
                o.tipo_autor = MembroObra.COAUTOR
            o.save()
            return httprr(f'/pesquisa/obra/{obra.id}', 'Autor/Coautor cadastrado com sucesso.')

        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_validar_obra, pesquisa.add_linhaeditorial')
def indicar_parecerista_obra(request, obra_id):
    title = 'Indicar Parecerista'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = IndicarPareceristaForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            if not ParecerObra.objects.filter(obra=obra, parecer_realizado_por_vinculo=usuario.get_vinculo()).exists():
                vinculo = usuario.get_vinculo()
                novo_parecerista = ParecerObra()
                novo_parecerista.obra = obra
                novo_parecerista.parecer_realizado_por_vinculo = vinculo
                novo_parecerista.indicado_em = datetime.datetime.now()
                novo_parecerista.save()

                titulo = '[SUAP] Pesquisa: Indicação de Parecerista de Obra'
                texto = (
                    '<h1>Pesquisa</h1>'
                    '<h2>Parecerista de Obra</h2>'
                    f"<p>Você foi indicado como parecerista da Obra '{obra.titulo}'.</p>"
                    f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo])
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=analise_parecerista', 'Parecerista indicado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_obra')
def parecerista_avaliar_obra(request, obra_id):
    title = 'Avaliar Obra'
    vinculo = request.user.get_vinculo()
    if vinculo.eh_servidor() and not request.user.get_relacionamento().areas_de_conhecimento.exists():
        return httprr('/pesquisa/tornar_avaliador/', 'Cadastre suas áreas de conhecimento antes de poder emitir parecer.')

    if vinculo.eh_prestador() and not AreaConhecimentoParecerista.objects.filter(parecerista=request.user.get_relacionamento()).exists():
        return httprr('/pesquisa/indicar_areas_conhecimento_de_interesse/', 'Cadastre suas áreas de conhecimento antes de poder emitir parecer.')

    if not ParecerObra.objects.filter(aceitou_indicacao=True, parecer_realizado_por_vinculo=vinculo, obra_id=obra_id).exists():
        return httprr(f'/pesquisa/obra/{obra_id}', 'Não é possível avaliar a obra antes de aceitar a indicação como parecerista.', tag='error')

    obra = get_object_or_404(Obra, pk=obra_id)
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    parecer = ParecerObra.objects.filter(parecer_realizado_por_vinculo=request.user.get_vinculo(), obra=obra)
    if parecer.exists() and obra.dentro_prazo_avaliar_obra() and not obra.julgamento_conselho_realizado_em:
        perguntas = PerguntaQuestionarioObra.objects.filter(ativo=True, tipo_questionario=obra.linha_editorial.tipo_questionario)
        form = AvaliacaoPareceristaObraForm(
            request.POST or None, request.FILES or None, perguntas=perguntas, instance=parecer[0], initial={'nota': parecer[0].nota}
        )
        if form.is_valid():
            o = form.save(False)
            o.parecer_realizado_em = datetime.datetime.now()
            o.save()
            if perguntas:
                nota = Decimal(0)
                ItemAvaliacaoObra.objects.filter(parecer=parecer[0]).delete()
                for pergunta in perguntas:
                    criterio = CriterioAvaliacaoObra.objects.get(id=int(form.cleaned_data.get(f'{pergunta.pk}')))
                    nota_atribuida = criterio.nota
                    nota += nota_atribuida
                    novo_item = ItemAvaliacaoObra()
                    novo_item.parecer = parecer[0]
                    novo_item.pergunta = pergunta
                    novo_item.criterio_avaliacao = criterio
                    novo_item.nota = nota_atribuida
                    novo_item.comentarios = form.cleaned_data.get(f'comentarios_{int(pergunta.pk)}')
                    novo_item.save()
                o.nota = nota
                if nota < 7:
                    o.situacao = ParecerObra.REPROVADA
                elif nota > 9:
                    o.situacao = ParecerObra.APROVADA
                else:
                    o.situacao = ParecerObra.APROVADA_RESSALVA
                o.save()

            titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
            texto = f"""<h1>Pesquisa</h1>'
                        <h2>Submissão de Obra</h2>
                        <p>Prezado autor, Sua obra recebeu avaliação de um parecerista no SUAP. Ressaltamos que a avaliação de um parecerista não corresponde à avaliação geral da obra,
                        já que a Editora {instituicao} juntamente com o seu Conselho Editorial se responsabilizam pela publicação do resultado final,
                        após reunir todos as notas emitidas por, pelo menos, 02 pareceristas sobre sua obra,
                        sendo publicado no portal do {instituicao} em data estabelecida em edital quando todas as obras submetidas para análise forem avaliadas.
                        Caso a obra tenha sido aprovada com ressalvas pelo parecerista, será necessário o reenvio da obra contemplando as sugestões do parecerista.</p>
                        <p class="more-info">Para mais informações, acesse: <a href="{0}/pesquisa/obra/{1}/">{0}/pesquisa/obra/{1}/</a></p>""".format(
                settings.SITE_URL, obra.id
            )

            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=analise_parecerista', 'Parecer salvo com sucesso.')

        return locals()

    raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_obra')
def reenviar_obra(request, obra_id):
    title = 'Reenviar Obra'
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.submetido_por_vinculo:
        form = ReenviarObraForm(request.POST or None, request.FILES or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.situacao_conselho_editorial = None
            o.obs_conselho_editorial = None
            o.julgamento_conselho_realizado_em = None
            o.save()
            titulo = '[SUAP] Pesquisa: Conselheiro Editorial'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Conselheiro Editorial</h2>'
                f"<p>O autor da Obra '{obra.titulo}' enviou a versão corrigida para receber seu parecer. Acesse o SUAP para mais detalhes.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )

            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.julgamento_conselho_realizado_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=validacao_conselho', 'Obra reenviada com sucesso.')
        return locals()
    raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def indicar_conselheiro_obra(request, obra_id):
    title = 'Indicar Conselheiro'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = IndicarConselheiroForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            obra.julgamento_conselho_realizado_por_vinculo = usuario.get_vinculo()
            obra.conselheiro_indicado_em = datetime.datetime.now()
        obra.save()

        titulo = '[SUAP] Pesquisa: Indicação de Conselheiro Editorial'
        texto = (
            '<h1>Pesquisa</h1>'
            '<h2>Conselheiro Editorial de obra</h2>'
            f"<p>Você foi indicado como conselheiro editorial da Obra '{obra.titulo}'.</p>"
            f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.julgamento_conselho_realizado_por_vinculo])

        return httprr(f'/pesquisa/obra/{obra.id}/?tab=validacao_conselho', 'Conselheiro indicado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.pode_validar_obra, pesquisa.add_linhaeditorial')
def registrar_posicao_conselho_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    title = 'Emitir Parecer'
    if request.user.get_vinculo() == obra.julgamento_conselho_realizado_por_vinculo or request.user.has_perm('pesquisa.add_linhaeditorial'):
        form = AvaliacaoConselhoEditorialForm(request.POST or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.julgamento_conselho_realizado_em = datetime.datetime.now()
            if o.situacao_conselho_editorial == Obra.FAVORAVEL:
                situacao = 'foi aceita'
                o.situacao = Obra.VALIDADA
            elif o.situacao_conselho_editorial == Obra.FAVORAVEL_COM_RESSALVAS:
                situacao = 'foi aceita com ressalvas'
            else:
                situacao = 'não foi aceita'
                o.situacao = Obra.CANCELADA
                o.cancelada_por_vinculo = request.user.get_vinculo()
                o.cancelada_em = datetime.datetime.now()
            o.save()
            titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
            texto = (
                f"<h1>Pesquisa</h1><h2>Submissão de Obra</h2><p>O pedido de publicação da obra '{obra.titulo}' {situacao} pelo conselho editorial. Caso tenha sido aprovada com ressalvas, é necessário o reenvio da obra corrigida.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=validacao_conselho', 'Parecer registrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def indicar_revisor_obra(request, obra_id):
    title = 'Indicar Revisor'
    obra = get_object_or_404(Obra, pk=obra_id)
    if obra.dentro_prazo_revisao():
        form = IndicarRevisorForm(request.POST or None)
        if form.is_valid():
            for usuario in form.cleaned_data['user']:
                obra.revisao_realizada_por_vinculo = usuario.get_vinculo()
                obra.revisor_indicado_em = datetime.datetime.now()
            obra.save()

            titulo = '[SUAP] Pesquisa: Indicação de Revisor de Obra'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Revisor de obra</h2>'
                f"<p>Você foi indicado como revisor da Obra '{obra.titulo}'.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.revisao_realizada_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=revisao_textual', 'Revisor indicado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_revisar_obra')
def revisar_obra(request, obra_id):
    title = 'Revisar Obra'
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.revisao_realizada_por_vinculo and obra.dentro_prazo_revisao():
        form = RevisarObraForm(request.POST or None, request.FILES or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.revisao_realizada_em = datetime.datetime.now()
            o.save()
            titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
            texto = (
                f"<h1>Pesquisa</h1><h2>Submissão de Obra</h2><p>O pedido de publicação da obra '{obra.titulo}' foi revisada.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=revisao_textual', 'Revisão salva com sucesso.')
        return locals()
    raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_obra')
def enviar_arquivo_corrigido(request, obra_id):
    title = 'Enviar Revisão do Autor'
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.submetido_por_vinculo and obra.dentro_prazo_revisao():
        form = RevisarAutorForm(request.POST or None, request.FILES or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.correcoes_enviadas_em = datetime.datetime.now()
            o.save()
            titulo = '[SUAP] Pesquisa: Versão Revisada de Obra'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Revisor de obra</h2>'
                f"<p>O autor da Obra '{obra.titulo}' enviou a versão revisada.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.revisao_realizada_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=revisao_textual', 'Correções enviadas com sucesso.')
        return locals()
    raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_revisar_obra')
def revisor_emitir_parecer(request, obra_id):
    title = 'Emitir Parecer da Revisão'
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.revisao_realizada_por_vinculo and obra.dentro_prazo_revisao():
        form = EmitirParecerRevisaoObraForm(request.POST or None, request.FILES or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.situacao = Obra.REVISADA
            o.versao_final_revisao_em = datetime.datetime.now()
            o.save()
            titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
            texto = (
                f"<h1>Pesquisa</h1><h2>Submissão de Obra</h2><p>O parecer final do revisor da obra '{obra.titulo}' foi cadastrado.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=revisao_textual', 'Parecer salvo com sucesso.')
        return locals()


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def indicar_diagramador_obra(request, obra_id):
    title = 'Indicar Diagramador'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = IndicarDiagramadorForm(request.POST or None)
    if form.is_valid():
        for usuario in form.cleaned_data['user']:
            obra.diagramacao_realizada_por_vinculo = usuario.get_vinculo()
            obra.diagramador_indicado_em = datetime.datetime.now()
        obra.save()

        titulo = '[SUAP] Pesquisa: Indicação de Diagramador de obra'
        texto = (
            '<h1>Pesquisa</h1>'
            '<h2>Diagramador de obra</h2>'
            f"<p>Você foi indicado como diagramador da Obra '{obra.titulo}'</p>."
            f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.diagramacao_realizada_por_vinculo])
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=diagramacao', 'Diagramador indicado com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def avaliar_diagramacao(request, obra_id):
    title = 'Avaliar Diagramação'
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.submetido_por_vinculo:
        form = AvaliacaoDiagramacaoForm(request.POST or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.diagramacao_avaliada_em = datetime.datetime.now()
            o.save()
            titulo = '[SUAP] Notificação sobre Diagramação de Obra'
            texto = (
                f"<h1>Pesquisa</h1><h2>Diagramação de Obra</h2><p>A diagramação da obra '{obra.titulo}' foi avaliada pelo autor.</p>"
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.diagramacao_realizada_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=diagramacao', 'Diagramação avaliada com sucesso.')
        return locals()
    raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_diagramar_obra')
def cadastrar_diagramacao(request, obra_id):
    title = 'Cadastrar Diagramação'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = CadastrarDiagramacaoObraForm(request.POST or None, request.FILES or None, instance=obra)
    if form.is_valid():
        o = form.save(False)
        if obra.diagramacao_avaliada_em:
            obra.situacao = Obra.CORRIGIDA
            obra.diagramacao_concluida = True
            obra.diagramacao_final_em = datetime.datetime.now()
        else:
            obra.situacao = Obra.DIAGRAMADA
        o.save()
        titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
        texto = f"<h1>Pesquisa</h1><h2>Submissão de Obra</h2><p>A diagramação da obra '{obra.titulo}' foi cadastrada. Por favor, acesse o SUAP para mais detalhes.</p>"
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=diagramacao', 'Diagramação cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def cadastrar_isbn(request, obra_id):
    title = 'Cadastrar ISBN'
    obra = get_object_or_404(Obra, pk=obra_id)
    if obra.eh_periodo_pedido_isbn():
        form = CadastrarISBNObraForm(request.POST or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.situacao = Obra.REGISTRADA_ISBN
            o.isbn_cadastrado_em = datetime.datetime.now()
            o.save()
            titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
            texto = f"<h1>Pesquisa</h1><h2>Submissão de Obra</h2><p>O ISBN da obra '{obra.titulo}' foi cadastrado. Por favor, acesse o SUAP para mais detalhes.</p>"
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=cadastro_isbn', 'ISBN cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_obra')
def registrar_conclusao_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    if request.user.get_vinculo() == obra.submetido_por_vinculo:
        obra.situacao = Obra.CONCLUIDA
        obra.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=publicacao', 'Publicação de obra concluída com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def cancelar_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    if obra.situacao != obra.CONCLUIDA:
        if obra.situacao != obra.CANCELADA:
            title = f'Justificar Cancelamento - {obra}'
            form = CancelamentoObraForm(request.POST or None, instance=obra)
            if form.is_valid():
                o = form.save(False)
                o.situacao = obra.CANCELADA
                o.cancelada_por_vinculo = request.user.get_vinculo()
                o.cancelada_em = datetime.datetime.now()
                o.save()
                ParecerObra.objects.filter(obra=obra).update(
                    situacao=ParecerObra.REPROVADA,
                    parecer_realizado_em=datetime.datetime.now(),
                    comentario='Parecer reprovado automaticamente devido ao cancelamento da obra',
                )
                return httprr(f'/pesquisa/obra/{obra.id}/', 'Obra cancelada com sucesso.')
        else:
            obra.situacao = obra.SUBMETIDA
            obra.cancelada_por_vinculo = None
            obra.cancelada_em = None
            obra.justificativa_cancelamento = None
            obra.save()
            ParecerObra.objects.filter(obra=obra).update(situacao=ParecerObra.EM_ANALISE, parecer_realizado_em=None, comentario='')
            return httprr(f'/pesquisa/obra/{obra.id}/', 'Cancelamento revertido com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_gerar_ficha_catalografica')
def cadastrar_ficha_catalografica(request, obra_id):
    title = 'Cadastrar Ficha Catalográfica'
    obra = get_object_or_404(Obra, pk=obra_id)
    if obra.eh_ativa():
        form = FichaCatalograficaForm(request.POST or None, request.FILES or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.situacao = Obra.CATALOGADA
            o.ficha_catalografica_cadastrada_em = datetime.datetime.now()
            o.save()
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=ficha_catalografica', 'Ficha catalográfica cadastrada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def concluir_obra(request, obra_id):
    title = 'Concluir Publicação de Obra'
    obra = get_object_or_404(Obra, pk=obra_id)
    if obra.situacao == obra.LIBERADA:
        form = ConclusaoObraForm(request.POST or None, request.FILES or None, instance=obra)
        if form.is_valid():
            o = form.save(False)
            o.situacao = Obra.CONCLUIDA
            o.obra_concluida_em = datetime.datetime.now()
            o.save()
            return httprr(f'/pesquisa/obra/{obra.id}/?tab=conclusao', 'Obra concluída com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def checklist_obra(request, obra_id):
    title = 'Checklist'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = ChecklistObraForm(request.POST or None, instance=obra)
    if form.is_valid():
        form.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=conclusao', 'Checklist salvo com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def checklist_obra_diagramador(request, obra_id):
    title = 'Checklist'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = ChecklistObraDiagramadorForm(request.POST or None, instance=obra)
    if form.is_valid():
        form.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=diagramacao', 'Checklist salvo com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def validar_termos(request, obra_id):
    title = 'Validar os Termos'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = TermoAssinadoForm(request.POST or None, instance=obra)
    if form.is_valid():
        o = form.save(False)
        o.termos_assinados_realizado_por_vinculo = request.user.get_vinculo()
        o.termos_assinados_realizado_em = datetime.datetime.now()
        o.save()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=termos', 'Termos validados com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.view_edital')
def estatisticas(request):
    projetos = Projeto.objects.all()
    if not request.user.has_perm('pesquisa.add_origemrecursoedital') and not request.user.has_perm('pesquisa.pode_ver_config_edital'):
        campus_do_usuario = get_uo(request.user)
        projetos = projetos.filter(uo=campus_do_usuario)
        title = f'Estatísticas dos Projetos de Pesquisa - Campus {campus_do_usuario}'
    else:
        title = 'Estatísticas dos Projetos de Pesquisa'
    ano = request.GET.get('ano')
    form = EstatisticasForm(request.GET or None, ano=ano, request=request)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        formato_edital = form.cleaned_data.get('formato_edital')
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')
        grupo_pesquisa = form.cleaned_data.get('grupo_pesquisa')
        situacao = form.cleaned_data.get('situacao')

        if ano:
            projetos = projetos.filter(edital__inicio_inscricoes__year=ano)
        if edital:
            projetos = projetos.filter(edital=edital)
        if campus:
            projetos = projetos.filter(uo=campus)
        if grupo_pesquisa:
            projetos = projetos.filter(grupo_pesquisa=grupo_pesquisa)

        if formato_edital:
            projetos = projetos.filter(edital__formato=formato_edital)

        hoje = datetime.datetime.now()
        enviados = projetos.filter(
            Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
        )
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)
        aprovados = enviados.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje) | enviados.filter(
            aprovado=True, edital__formato=Edital.FORMATO_SIMPLIFICADO
        )
        execucao = aprovados.filter(
            pre_aprovado=True,
            aprovado=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            edital__divulgacao_selecao__lt=hoje,
            inativado=False,
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

        if situacao != 'Todos':
            titulo = situacao
            if situacao == EstatisticasForm.PROJETOS_ENVIADOS:
                queryset_para_graficos = enviados
            elif situacao == EstatisticasForm.PROJETOS_PRE_SELECIONADOS:
                queryset_para_graficos = enviados.filter(pre_aprovado=True)
            elif situacao == EstatisticasForm.PROJETOS_APROVADOS:
                queryset_para_graficos = aprovados
            elif situacao == EstatisticasForm.PROJETOS_EM_EXECUCAO:
                queryset_para_graficos = execucao
            elif situacao == EstatisticasForm.PROJETOS_CONCLUIDOS:
                queryset_para_graficos = concluidos
            elif situacao == EstatisticasForm.PROJETOS_CANCELADOS:
                queryset_para_graficos = cancelados
            elif situacao == EstatisticasForm.PROJETOS_INATIVADOS:
                queryset_para_graficos = inativados
        else:
            queryset_para_graficos = enviados
            titulo = 'Projetos Enviados'

        dados2 = []
        for area in AreaConhecimento.objects.filter(superior__isnull=False):
            valor = queryset_para_graficos.filter(area_conhecimento=area).count()
            if valor:
                dados2.append([area.descricao, valor])

        grafico2 = ColumnChart(
            'grafico2',
            title=f'{titulo} por Área de Conhecimento',
            subtitle='Quantidade de projetos por área de conhecimento',
            minPointLength=0,
            data=dados2,
        )

        grafico2.id = 'grafico2'

        dados3 = []
        participacoes = Participacao.objects.filter(projeto__in=queryset_para_graficos.values_list('id')).distinct()
        alunos = Aluno.objects.filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id')).distinct()
        docentes = Servidor.objects.filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id'), eh_docente=True).distinct()
        tecnicos_adm = Servidor.objects.filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id'), eh_tecnico_administrativo=True).distinct()
        dados3.append(['Discentes', alunos.count()])
        dados3.append(['Docentes', docentes.count()])
        dados3.append(['Técnicos Administrativos', tecnicos_adm.count()])
        grafico3 = PieChart(
            'grafico3',
            title=f'Participantes em {titulo} por Categoria',
            subtitle='Quantidade de discentes, téc. administrativos e docentes únicos envolvidos',
            minPointLength=0,
            data=dados3,
        )

        grafico3.id = 'grafico3'

        bolsistas = Participacao.objects.filter(vinculo='Bolsista', projeto__in=queryset_para_graficos.values_list('id')).distinct()
        voluntarios = Participacao.objects.filter(vinculo='Voluntário', projeto__in=queryset_para_graficos.values_list('id')).distinct()

        alunos_bolsistas = Aluno.objects.filter(vinculos__in=bolsistas.values_list('vinculo_pessoa_id')).distinct()
        alunos_voluntarios = Aluno.objects.filter(vinculos__in=voluntarios.values_list('vinculo_pessoa_id')).distinct()
        docentes_bolsistas = Servidor.objects.filter(ativo=True, vinculos__in=bolsistas.values_list('vinculo_pessoa_id'), eh_docente=True).distinct()
        docentes_voluntarios = Servidor.objects.filter(
            ativo=True, vinculos__in=voluntarios.values_list('vinculo_pessoa_id'), eh_docente=True
        ).distinct()
        tecnicos_adm_bolsistas = Servidor.objects.filter(
            ativo=True, vinculos__in=bolsistas.values_list('vinculo_pessoa_id'), eh_tecnico_administrativo=True
        ).distinct()
        tecnicos_adm_voluntarios = Servidor.objects.filter(
            ativo=True, vinculos__in=voluntarios.values_list('vinculo_pessoa_id'), eh_tecnico_administrativo=True
        ).distinct()

        series2 = []
        serie = ['Discentes']
        serie.append(alunos_bolsistas.count())
        serie.append(alunos_voluntarios.count())
        series2.append(serie)

        serie = ['Docentes']
        serie.append(docentes_bolsistas.count())
        serie.append(docentes_voluntarios.count())
        series2.append(serie)

        serie = ['Técnicos Administrativos']
        serie.append(tecnicos_adm_bolsistas.count())
        serie.append(tecnicos_adm_voluntarios.count())
        series2.append(serie)

        groups = ['Bolsistas', 'Voluntários']

        grafico4 = GroupedColumnChart(
            'grafico4',
            title=f'Tipo de Vínculo por Categoria em {titulo}',
            subtitle='Quantidade de bolsistas e voluntários por categoria',
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
            title=f'Discentes por Modalidade de Ensino em {titulo}',
            subtitle='Quantidade de discentes classificados por modalidade de ensino',
            minPointLength=0,
            data=dados5,
        )

        grafico5.id = 'grafico5'

        dados6 = []
        todos = Projeto.objects.filter(id__in=queryset_para_graficos.values_list('id'))

        dados6.append(['Projetos de Pesquisa aplicada', todos.filter(classificacao_trl=Projeto.TRL_2).count()])
        dados6.append(['Demais projetos', todos.exclude(classificacao_trl=Projeto.TRL_2).count()])

        grafico6 = PieChart(
            'grafico6',
            title='Porcentagem de projetos de pesquisa aplicada',
            subtitle='Quantidade de projetos de pesquisa aplicada em relação ao total de projetos',
            minPointLength=0,
            data=dados6,
        )

        grafico6.id = 'grafico6'

        dados7 = []
        for trl in Projeto.TRL_CHOICES:
            valor = queryset_para_graficos.filter(classificacao_trl=trl[0]).count()
            if valor:
                dados7.append([trl[0], valor])
        dados7.append(['Sem TRL informado', queryset_para_graficos.filter(classificacao_trl=None).count()])

        grafico7 = PieChart(
            'grafico7',
            title='Porcentagem de projetos por TRL',
            subtitle='Quantidade de projetos por TRL',
            minPointLength=0,
            data=dados7,
        )
        grafico7.id = 'grafico7'

        dados8 = []
        participacoes = Participacao.objects.filter(projeto__in=queryset_para_graficos.values_list('id'))
        participacoes_aplicada = Participacao.objects.filter(
            projeto__classificacao_trl=Projeto.TRL_2, projeto__in=queryset_para_graficos.values_list('id')
        )
        FORMA_INGRESSO_CHOICES = [
            'L10 - Renda <= 1,5 / Autodeclarados PPI / Deficiente',
            'L10 - Renda <= 1,5 / Autodeclarados PPI / Deficiente (SISU)',
            'L13 - Qualquer Renda / Qualquer Etnia / Deficiente',
            'L13 - Qualquer Renda / Qualquer Etnia / Deficiente (SISU)',
            'L14 - Qualquer Renda / Autodeclarado PPI / Deficiente',
            'L14 - Qualquer Renda / Autodeclarado PPI / Deficiente (SISU)',
            'L15 - Deficiente / Qualquer Escola de Origem',
            'L15 - Deficiente / Qualquer Escola de Origem (SISU)',
            'L1 - Renda <= 1,5 / Qualquer Etnia',
            'L1 - Renda <= 1,5 / Qualquer Etnia (SISU)',
            'L2 - Renda <= 1,5 / Autodeclarados PPI',
            'L2 - Renda <= 1,5 / Autodeclarados PPI (SISU)',
            'L5 - Qualquer Renda / Qualquer Etnia',
            'L5 - Qualquer Renda / Qualquer Etnia (SISU)',
            'L6 - Qualquer Renda / Autodeclarado PPI',
            'L6 - Qualquer Renda / Autodeclarado PPI (SISU)',
            'L9 - Renda <= 1,5 / Qualquer Etnia / Deficiente',
            'L9 - Renda <= 1,5 / Qualquer Etnia / Deficiente (SISU)',
            'Pessoas com Deficiência',
        ]
        alunos_forma_ingresso = Aluno.objects.filter(forma_ingresso__descricao__in=FORMA_INGRESSO_CHOICES)

        dados8.append(
            [
                'Alunos provenientes de ações afirmativas',
                alunos_forma_ingresso.filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id')).distinct().count(),
            ]
        )
        dados8.append(
            [
                'Demais alunos',
                Aluno.objects.exclude(forma_ingresso__descricao__in=FORMA_INGRESSO_CHOICES)
                .filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id'))
                .distinct()
                .count(),
            ]
        )

        grafico8 = PieChart(
            'grafico8',
            title='Porcentagem de alunos provenientes das ações afirmativas da instituição envolvidos em projetos de pesquisa',
            subtitle='Quantidade de alunos provenientes das ações afirmativas da instituição envolvidos em projetos de pesquisa',
            minPointLength=0,
            data=dados8,
        )
        grafico8.id = 'grafico8'

        dados9 = []
        participacoes = (
            Participacao.objects.filter(projeto__in=queryset_para_graficos.values_list('id'))
            .exclude(vinculo_pessoa=None)
            .exclude(vinculo_pessoa__pessoa__pessoafisica__in=ColaboradorExterno.objects.values_list('prestador__pessoa_fisica', flat=True))
        )
        masculino = participacoes.filter(vinculo_pessoa__pessoa__pessoafisica__sexo='M').distinct('vinculo_pessoa')
        feminino = participacoes.filter(vinculo_pessoa__pessoa__pessoafisica__sexo='F').distinct('vinculo_pessoa')

        dados9.append(['Masculino', masculino.count()])
        dados9.append(['Feminino', feminino.count()])

        grafico9 = PieChart(
            'grafico9',
            title=f'Participantes em {titulo} por Gênero',
            subtitle='Quantidade de participantes únicos envolvidos por gênero',
            minPointLength=0,
            data=dados9,
        )

        grafico9.id = 'grafico9'

        series10 = []
        serie = ['Discentes']
        serie.append(alunos.filter(pessoa_fisica__sexo='M').count())
        serie.append(alunos.filter(pessoa_fisica__sexo='F').count())
        series10.append(serie)

        serie = ['Docentes']
        serie.append(docentes.filter(pessoa_fisica__sexo='M').count())
        serie.append(docentes.filter(pessoa_fisica__sexo='F').count())
        series10.append(serie)

        serie = ['Técnicos Administrativos']
        serie.append(tecnicos_adm.filter(pessoa_fisica__sexo='M').count())
        serie.append(tecnicos_adm.filter(pessoa_fisica__sexo='F').count())
        series10.append(serie)

        groups = []
        for tipo in ['Masculino', 'Feminino']:
            groups.append(tipo)

        grafico10 = GroupedColumnChart(
            'grafico10',
            title=f'Tipo de Gênero por Categoria em {titulo}',
            subtitle='Quantidade de participantes por gênero e por categoria',
            data=series10,
            groups=groups,
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
        )

        grafico10.id = 'grafico10'

        series11 = []
        serie = ['Discentes']
        serie.append(alunos_bolsistas.filter(pessoa_fisica__sexo='M').count())
        serie.append(alunos_bolsistas.filter(pessoa_fisica__sexo='F').count())
        series11.append(serie)

        serie = ['Docentes']
        serie.append(docentes_bolsistas.filter(pessoa_fisica__sexo='M').count())
        serie.append(docentes_bolsistas.filter(pessoa_fisica__sexo='F').count())
        series11.append(serie)

        serie = ['Técnicos Administrativos']
        serie.append(tecnicos_adm_bolsistas.filter(pessoa_fisica__sexo='M').count())
        serie.append(tecnicos_adm_bolsistas.filter(pessoa_fisica__sexo='F').count())
        series11.append(serie)

        grafico11 = GroupedColumnChart(
            'grafico11',
            title=f'Bolsistas por Gênero e por Categoria em {titulo}',
            subtitle='Quantidade de participantes bolsistas por gênero e por categoria',
            data=series11,
            groups=groups,
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
        )

        grafico11.id = 'grafico11'

        series12 = []
        serie = ['Discentes']
        serie.append(alunos_voluntarios.filter(pessoa_fisica__sexo='M').count())
        serie.append(alunos_voluntarios.filter(pessoa_fisica__sexo='F').count())
        series12.append(serie)

        serie = ['Docentes']
        serie.append(docentes_voluntarios.filter(pessoa_fisica__sexo='M').count())
        serie.append(docentes_voluntarios.filter(pessoa_fisica__sexo='F').count())
        series12.append(serie)

        serie = ['Técnicos Administrativos']
        serie.append(tecnicos_adm_voluntarios.filter(pessoa_fisica__sexo='M').count())
        serie.append(tecnicos_adm_voluntarios.filter(pessoa_fisica__sexo='F').count())
        series12.append(serie)

        grafico12 = GroupedColumnChart(
            'grafico12',
            title=f'Voluntários por Tipo de Gênero por Categoria em {titulo}',
            subtitle='Quantidade de participantes voluntários por gênero e por categoria',
            data=series12,
            groups=groups,
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
        )

        grafico12.id = 'grafico12'

        dados13 = []
        participacoes = (
            Participacao.objects.filter(projeto__in=queryset_para_graficos.values_list('id'))
            .exclude(vinculo_pessoa=None)
            .exclude(vinculo_pessoa__pessoa__pessoafisica__in=ColaboradorExterno.objects.values_list('prestador__pessoa_fisica', flat=True))
        )

        for raca in Raca.objects.filter(id__in=participacoes.values_list('vinculo_pessoa__raca', flat=True)):
            dados13.append([raca.descricao, participacoes.filter(vinculo_pessoa__raca=raca).distinct('vinculo_pessoa').count()])

        grafico13 = PieChart(
            'grafico13',
            title=f'Participantes em {titulo} por Etnia',
            subtitle='Quantidade de participantes únicos envolvidos por etnia',
            minPointLength=0,
            data=dados13,
        )

        grafico13.id = 'grafico13'

        series14 = []
        serie = ['Discentes']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, alunos.filter(vinculos__raca=raca).count()])
        series14.append(serie)

        serie = ['Docentes']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, docentes.filter(vinculos__raca=raca).count()])
        series14.append(serie)

        serie = ['Técnicos Administrativos']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, tecnicos_adm.filter(vinculos__raca=raca).count()])
        series14.append(serie)

        groups = []
        for raca in Raca.objects.all():
            groups.append(raca.descricao)

        grafico14 = GroupedColumnChart(
            'grafico14',
            title=f'Tipo de Etnia por Categoria em {titulo}',
            subtitle='Quantidade de participantes por etnia e por categoria',
            data=series14,
            groups=groups,
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
        )

        grafico14.id = 'grafico14'

        series15 = []
        serie = ['Discentes']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, alunos_bolsistas.filter(vinculos__raca=raca).count()])
        series15.append(serie)

        serie = ['Docentes']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, docentes_bolsistas.filter(vinculos__raca=raca).count()])
        series15.append(serie)

        serie = ['Técnicos Administrativos']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, tecnicos_adm_bolsistas.filter(vinculos__raca=raca).count()])
        series15.append(serie)

        grafico15 = GroupedColumnChart(
            'grafico15',
            title=f'Bolsistas por Etnia e por Categoria em {titulo}',
            subtitle='Quantidade de participantes bolsistas por etnia e por categoria',
            data=series15,
            groups=groups,
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
        )

        grafico15.id = 'grafico15'

        series16 = []
        serie = ['Discentes']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, alunos_voluntarios.filter(vinculos__raca=raca).count()])
        series16.append(serie)

        serie = ['Docentes']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, docentes_voluntarios.filter(vinculos__raca=raca).count()])
        series16.append(serie)

        serie = ['Técnicos Administrativos']
        for raca in Raca.objects.all():
            serie.append([raca.descricao, tecnicos_adm_voluntarios.filter(vinculos__raca=raca).count()])
        series16.append(serie)

        grafico16 = GroupedColumnChart(
            'grafico16',
            title=f'Voluntários por Etnia e por Categoria em {titulo}',
            subtitle='Quantidade de participantes voluntários por etnia e por categoria',
            data=series16,
            groups=groups,
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
        )

        grafico16.id = 'grafico16'

        graficos_projetos = [grafico, grafico2, grafico6, grafico7]
        graficos_participacao = [grafico3, grafico9, grafico13]
        graficos_perfil = [grafico4, grafico10, grafico11, grafico12, grafico14, grafico15, grafico16]
        graficos_discentes = [grafico5, grafico8]

    return locals()


@rtr()
@permission_required('pesquisa.pode_validar_obra')
def remover_parecerista(request, parecerobra_id):
    parecer = get_object_or_404(ParecerObra, pk=parecerobra_id)
    obra = parecer.obra
    eh_conselheiro = request.user.get_vinculo() == obra.julgamento_conselho_realizado_por_vinculo
    eh_sistemico = request.user.has_perm('pesquisa.add_linhaeditorial')
    if not parecer.parecer_realizado_em and (eh_conselheiro or eh_sistemico):
        parecer.delete()
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=analise_parecerista', 'Parecerista removido com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.view_edital')
def relatorio_dimensao(request):
    # ----------------------------------------------------
    quantidade_projetos = []
    quantidade_participantes = []
    participantes_por_area_conhecimento = []
    # ----------------------------------------------------
    escolheu_ano = False
    form = RelatorioDimensaoForm(data=request.GET or None, request=request)
    soma_total = 0
    soma_aprovados = 0
    soma_concluidos = 0

    if request.user.has_group_cached('Coordenador de Pesquisa'):
        campus_relatorio = get_uo(request.user)
    else:
        campus_relatorio = None
    hoje = datetime.datetime.now()
    if form.is_valid():
        if form.cleaned_data.get('ano') and form.cleaned_data.get('ano') != 'Selecione um ano':
            ano = int(form.cleaned_data['ano'])
            escolheu_ano = True
            ppg = form.cleaned_data.get('ppg')
            formato = form.cleaned_data['formato_edital']
            if form.cleaned_data.get('campus'):
                campus_escolhido = form.cleaned_data.get('campus')
                campus_relatorio = get_object_or_404(UnidadeOrganizacional, pk=campus_escolhido.id)
            if campus_relatorio:
                editais_tem_oferta = BolsaDisponivel.objects.filter(uo=campus_relatorio).values_list('edital', flat=True)
                editais = Edital.objects.filter(inicio_inscricoes__year=ano, id__in=editais_tem_oferta)
                editais = editais.filter(
                    id__in=Projeto.objects.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    .filter(uo=campus_relatorio)
                    .values_list('edital', flat=True)
                ).order_by('inicio_inscricoes')
            else:
                editais = Edital.objects.filter(inicio_inscricoes__year=ano).order_by('inicio_inscricoes')

            if formato == Edital.FORMATO_COMPLETO:
                editais = editais.filter(formato=Edital.FORMATO_COMPLETO)
            elif formato == Edital.FORMATO_SIMPLIFICADO:
                editais = editais.filter(formato=Edital.FORMATO_SIMPLIFICADO)

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

            soma_areas_total = {}
            soma_areas_aprovados = {}
            lista_qtd = {}
            lista_total = []
            areas = []
            for area in AreaConhecimento.objects.filter(superior__isnull=False).order_by('descricao'):
                tem_a_area = Projeto.objects.filter(edital__in=editais.values_list('id', flat=True), area_conhecimento=area)
                if ppg:
                    tem_a_area = tem_a_area.filter(ppg=ppg)

                tem_a_area = tem_a_area.filter(
                    Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                )
                if campus_relatorio:
                    tem_a_area = tem_a_area.filter(uo=campus_relatorio)
                if tem_a_area.exists():
                    areas.append(area.descricao)

            for edital in editais.order_by('titulo'):
                areas_total = {}
                areas_aprovados = {}

                # ----------------------------------------------------
                if campus_relatorio:
                    projetos_por_edital_total = Projeto.objects.filter(edital=edital, uo=campus_relatorio)
                else:
                    projetos_por_edital_total = Projeto.objects.filter(edital=edital)
                if ppg:
                    projetos_por_edital_total = projetos_por_edital_total.filter(ppg=ppg)
                projetos_por_edital_total = projetos_por_edital_total.filter(
                    Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                )
                projetos_por_edital_aprovados = projetos_por_edital_total.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje)
                projetos_por_edital_concluidos = projetos_por_edital_aprovados.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False)
                soma_total = soma_total + projetos_por_edital_total.count()
                soma_aprovados = soma_aprovados + projetos_por_edital_aprovados.count()
                soma_concluidos = soma_concluidos + projetos_por_edital_concluidos.count()
                # ----------------------------------------------------
                lista_qtd[edital.titulo] = {'valores': []}
                for area in AreaConhecimento.objects.filter(superior__isnull=False).order_by('descricao'):
                    if area.descricao in areas:
                        lista_qtd[edital.titulo]['valores'].append(projetos_por_edital_total.filter(area_conhecimento=area).count())
                        lista_qtd[edital.titulo]['valores'].append(projetos_por_edital_aprovados.filter(area_conhecimento=area).count())
                lista_qtd = collections.OrderedDict(sorted(lista_qtd.items()))
                percentual = 0
                projetos_aprovados = projetos_por_edital_aprovados.count()
                if projetos_aprovados:
                    percentual = (
                        (Decimal(projetos_por_edital_concluidos.count()).quantize(10**2) / Decimal(projetos_aprovados).quantize(10**2)) * 100
                    ).quantize(10**2)

                quantidade_projetos.append(
                    {
                        'edital': edital,
                        'total': projetos_por_edital_total.count(),
                        'aprovados': projetos_aprovados,
                        'concluidos': projetos_por_edital_concluidos.count(),
                        'percentual': percentual,
                    }
                )
                # ----------------------------------------------------

                bolsistas = Participacao.objects.filter(
                    vinculo='Bolsista', bolsa_concedida=True, projeto__in=projetos_por_edital_aprovados.values_list('id')
                )
                voluntarios = Participacao.objects.filter(bolsa_concedida=False, projeto__in=projetos_por_edital_aprovados.values_list('id'))
                alunos_bolsistas = bolsistas.filter(vinculo_pessoa__tipo_relacionamento__model='aluno').count()
                alunos_voluntarios = voluntarios.filter(vinculo_pessoa__tipo_relacionamento__model='aluno').count()
                docentes_bolsistas = bolsistas.filter(
                    vinculo_pessoa__in=Servidor.objects.filter(eh_docente=True).values_list('vinculos', flat=True)
                ).count()
                docentes_voluntarios = voluntarios.filter(
                    vinculo_pessoa__in=Servidor.objects.filter(eh_docente=True).values_list('vinculos', flat=True)
                ).count()
                tecnicos_adm_bolsistas = bolsistas.filter(
                    vinculo_pessoa__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True)
                ).count()
                tecnicos_adm_voluntarios = voluntarios.filter(
                    vinculo_pessoa__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True)
                ).count()
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
            ids = 0
            while ids < len(areas) * 2:
                total = 0
                idx = 0
                while idx < editais.count():
                    if len(list(lista_qtd.items())) > idx:
                        total = total + list(lista_qtd.items())[idx][1]['valores'][ids]
                    idx += 1
                lista_total.append(total)
                ids += 1

            area_tematica_total_geral = 0
            area_tematica_total_docente_bols = 0
            area_tematica_total_docente_vol = 0
            area_tematica_total_tec_adm_bols = 0
            area_tematica_total_tec_adm_vol = 0
            area_tematica_total_aluno_bols = 0
            area_tematica_total_aluno_vol = 0

            if campus_relatorio:
                projetos_area_conhecimento = Projeto.objects.filter(uo=campus_relatorio, edital__in=editais.values_list('id'), aprovado=True)
            else:
                projetos_area_conhecimento = Projeto.objects.filter(edital__in=editais.values_list('id'), aprovado=True)
            if ppg:
                projetos_area_conhecimento = projetos_area_conhecimento.filter(ppg=ppg)
            for area in AreaConhecimento.objects.filter(descricao__in=areas).order_by('descricao'):
                if projetos_area_conhecimento.filter(area_conhecimento=area).exists():
                    bolsistas = Participacao.objects.filter(
                        vinculo=TipoVinculo.BOLSISTA,
                        projeto__in=projetos_area_conhecimento.values_list('id'),
                        bolsa_concedida=True,
                        projeto__area_conhecimento=area,
                    ).distinct()
                    voluntarios = Participacao.objects.filter(
                        bolsa_concedida=False, projeto__in=projetos_area_conhecimento.values_list('id'), projeto__area_conhecimento=area
                    ).distinct()

                    total_alunos_bolsistas = bolsistas.filter(vinculo_pessoa__tipo_relacionamento__model='aluno').count()
                    total_alunos_voluntarios = voluntarios.filter(vinculo_pessoa__tipo_relacionamento__model='aluno').count()

                    total_docentes_voluntarios = voluntarios.filter(
                        vinculo_pessoa__in=Servidor.objects.filter(eh_docente=True).values_list('vinculos', flat=True)
                    ).count()
                    total_docentes_bolsistas = bolsistas.filter(
                        vinculo_pessoa__in=Servidor.objects.filter(eh_docente=True).values_list('vinculos', flat=True)
                    ).count()

                    total_tec_adm_voluntarios = voluntarios.filter(
                        vinculo_pessoa__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True)
                    ).count()
                    total_tec_adm_bolsistas = bolsistas.filter(
                        vinculo_pessoa__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True)
                    ).count()

                    total = (
                        total_alunos_bolsistas
                        + total_alunos_voluntarios
                        + total_docentes_bolsistas
                        + total_docentes_voluntarios
                        + total_tec_adm_bolsistas
                        + total_tec_adm_voluntarios
                    )

                    participantes_por_area_conhecimento.append(
                        {
                            'area': area.descricao,
                            'alunos_bolsistas': total_alunos_bolsistas,
                            'alunos_voluntarios': total_alunos_voluntarios,
                            'docentes_bolsistas': total_docentes_bolsistas,
                            'docentes_voluntarios': total_docentes_voluntarios,
                            'tec_adm_bolsistas': total_tec_adm_bolsistas,
                            'tec_adm_voluntarios': total_tec_adm_voluntarios,
                            'total': total,
                        }
                    )
                    area_tematica_total_geral = area_tematica_total_geral + total
                    area_tematica_total_docente_bols = area_tematica_total_docente_bols + total_docentes_bolsistas
                    area_tematica_total_docente_vol = area_tematica_total_docente_vol + total_docentes_voluntarios
                    area_tematica_total_tec_adm_bols = area_tematica_total_tec_adm_bols + total_tec_adm_bolsistas
                    area_tematica_total_tec_adm_vol = area_tematica_total_tec_adm_vol + total_tec_adm_voluntarios
                    area_tematica_total_aluno_bols = area_tematica_total_aluno_bols + total_alunos_bolsistas
                    area_tematica_total_aluno_vol = area_tematica_total_aluno_vol + total_alunos_voluntarios

            lista_grupos_pesquisa = []
            ids_dos_grupos_pesquisa = projetos_area_conhecimento.values_list('grupo_pesquisa', flat=True)
            total_grupos_pesquisa = 0
            for grupo in GrupoPesquisa.objects.filter(id__in=ids_dos_grupos_pesquisa).order_by('descricao'):
                qtd = projetos_area_conhecimento.filter(grupo_pesquisa=grupo).count()
                lista_grupos_pesquisa.append([grupo.descricao, qtd])
                total_grupos_pesquisa = total_grupos_pesquisa + qtd

            if 'xls' in request.POST and escolheu_ano:
                return tasks.relatorio_dimensao_export_to_xls(
                    quantidade_projetos, areas, lista_qtd, quantidade_participantes, participantes_por_area_conhecimento, lista_grupos_pesquisa
                )

    if campus_relatorio:
        title = f'Relatório de Dimensão dos Projetos de Pesquisa - Campus {campus_relatorio}'
    else:
        title = 'Relatório de Dimensão dos Projetos de Pesquisa'

    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_projeto')
def rejeitar_indicacao(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    # Mesmo estado em que projetos_especial_pre_aprovados.html oferece "Rejeitar Indicação": quem já avaliou vê "Editar Avaliação".
    if projeto.edital.is_periodo_selecao() and projeto.pendente_avaliacao():
        AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=request.user.get_vinculo()).update(
            rejeitado=True, rejeitado_em=datetime.datetime.now()
        )
        return httprr(f'/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/', 'Indicação rejeitada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.view_laboratoriopesquisa')
def laboratorio_pesquisa(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    title = f'{laboratorio}'
    equipamentos = EquipamentoLaboratorioPesquisa.objects.filter(laboratorio=laboratorio)
    servicos = ServicoLaboratorioPesquisa.objects.filter(laboratorio=laboratorio)
    fotos = FotoLaboratorioPesquisa.objects.filter(laboratorio=laboratorio)
    materiais = MaterialLaboratorioPesquisa.objects.filter(laboratorio=laboratorio)
    solicitacoes = SolicitacaoServicoLaboratorio.objects.filter(laboratorio=laboratorio)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == laboratorio.coordenador
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos_execucao = Projeto.objects.filter(
        pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False
    ).exclude(id__in=projetos_cancelados)
    eh_coordenador_projeto = projetos_execucao.filter(vinculo_coordenador=request.user.get_vinculo()).exists()
    eh_diretor = request.user.has_group_cached('Diretor de Pesquisa', ignore_groups_if_superuser=False)
    servicos_comunidade_interna = SolicitacaoServicoLaboratorio.objects.filter(
        laboratorio=laboratorio, tipo_entidade_atendida=SolicitacaoServicoLaboratorio.INTERNA, situacao=SolicitacaoServicoLaboratorio.ATENDIDA
    )
    servicos_comunidade_externa = SolicitacaoServicoLaboratorio.objects.filter(
        laboratorio=laboratorio, tipo_entidade_atendida=SolicitacaoServicoLaboratorio.EXTERNA, situacao=SolicitacaoServicoLaboratorio.ATENDIDA
    )
    form = RelatorioLaboratorioForm(request.GET or None)
    if form.is_valid():
        ano = form.cleaned_data.get('ano')
        if ano:
            servicos_comunidade_interna = servicos_comunidade_interna.filter(data__year=ano)
            servicos_comunidade_externa = servicos_comunidade_externa.filter(data__year=ano)

    servicos_comunidade_interna = servicos_comunidade_interna.only('id').count()
    servicos_comunidade_externa = servicos_comunidade_externa.only('id').count()
    return locals()


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def cadastrar_equipamento_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == laboratorio.coordenador
    if pode_gerenciar:
        title = 'Cadastrar Equipamento'
        equipamento = EquipamentoLaboratorioPesquisa()
        equipamento.laboratorio = laboratorio
        form = EquipamentoLaboratorioForm(request.POST or None, request.FILES or None, instance=equipamento)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/cadastrar_equipamento_laboratorio/{laboratorio.id}/', 'Equipamento cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def cadastrar_servico_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == laboratorio.coordenador
    if pode_gerenciar:
        title = 'Cadastrar Serviço'
        servico = ServicoLaboratorioPesquisa()
        servico.laboratorio = laboratorio
        form = ServicoLaboratorioForm(request.POST or None, instance=servico)
        if form.is_valid():
            o = form.save(False)
            if form.cleaned_data.get('processo'):
                o.id_do_processo_eletronico = form.cleaned_data.get('processo').id
            o.save()
            o.equipamentos.set(form.cleaned_data.get('equipamentos'))
            return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=servicos', 'Serviço cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def cadastrar_material_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == laboratorio.coordenador
    if pode_gerenciar:
        title = 'Cadastrar Material'
        material = MaterialLaboratorioPesquisa()
        material.laboratorio = laboratorio
        form = MaterialLaboratorioPesquisaForm(request.POST or None, request.FILES or None, instance=material)
        if form.is_valid():
            o = form.save(False)
            if form.cleaned_data.get('adicionar_novo'):
                if MaterialConsumoPesquisa.objects.filter(descricao=form.cleaned_data.get('descricao')).exists():
                    novo_material = MaterialConsumoPesquisa.objects.filter(descricao=form.cleaned_data.get('descricao'))[0]
                else:
                    novo_material = MaterialConsumoPesquisa()
                    novo_material.descricao = form.cleaned_data.get('descricao')
                    novo_material.save()
                o.material = novo_material
            o.save()
            return httprr(f'/pesquisa/cadastrar_material_laboratorio/{laboratorio.id}/', 'Material cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
                content = arquivo_up.read()
                nome = arquivo_up.name
                vinculo = request.user.get_vinculo()
                arquivo = Arquivo()
                arquivo.save(nome, vinculo)
                o.arquivo = arquivo
                o.save()
                arquivo.store(request.user, content)

                return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=anexos', 'Anexo cadastrado com sucesso.')
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def excluir_outro_anexo(request, anexo_id):
    anexo = get_object_or_404(ProjetoAnexo, pk=anexo_id)
    projeto = anexo.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if not anexo.anexo_edital and not anexo.projeto.eh_somente_leitura():
            anexo.delete()
            return httprr(f'/pesquisa/projeto/{anexo.projeto.id}/?tab=anexos', 'Anexo removido com sucesso.')
        else:
            return httprr(f'/pesquisa/projeto/{anexo.projeto.id}/?tab=anexos', 'Anexo não pode ser removido.', tag='error')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.view_edital')
def lista_mensal_bolsistas(request):
    title = 'Lista Mensal de Bolsistas'
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
        if 'xls' in request.GET and registros.count():
            return tasks.lista_mensal_bolsistas_to_xls(registros, ano, registros[0].get_mes())
    return locals()


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def classificar_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    if obra.eh_ativa() and obra.situacao == obra.ACEITA:
        obra.situacao = obra.CLASSIFICADA
        obra.save()
        return httprr(f'/pesquisa/obra/{obra.id}/', 'Obra classificada com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def cadastrar_foto_laboratorio(request, laboratorio_id):
    title = 'Cadastrar Foto'
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == laboratorio.coordenador
    if pode_gerenciar:
        foto = FotoLaboratorioPesquisa()
        foto.laboratorio = laboratorio
        form = FotoLaboratorioForm(request.POST or None, request.FILES or None, instance=foto)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=fotos', 'Foto cadastrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def editar_servico(request, servico_id):
    servico = get_object_or_404(ServicoLaboratorioPesquisa, pk=servico_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == servico.laboratorio.coordenador
    if pode_gerenciar:
        title = 'Editar Serviço'
        form = ServicoLaboratorioForm(request.POST or None, request.FILES or None, instance=servico)
        if form.is_valid():
            o = form.save(False)
            if form.cleaned_data.get('processo'):
                o.id_do_processo_eletronico = form.cleaned_data.get('processo').id
            o.save()
            o.equipamentos.set(form.cleaned_data.get('equipamentos'))
            return httprr(f'/pesquisa/laboratorio_pesquisa/{servico.laboratorio.id}/?tab=servicos', 'Serviço editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def excluir_servico(request, servico_id):
    servico = get_object_or_404(ServicoLaboratorioPesquisa, pk=servico_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == servico.laboratorio.coordenador
    if pode_gerenciar:
        laboratorio = servico.laboratorio
        servico.delete()
        return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=servicos', 'Serviço excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def editar_equipamento(request, equipamento_id):
    equipamento = get_object_or_404(EquipamentoLaboratorioPesquisa, pk=equipamento_id)
    pode_gerenciar = (
        request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == equipamento.laboratorio.coordenador
    )
    if pode_gerenciar:
        title = 'Editar Equipamento'
        form = EquipamentoLaboratorioForm(request.POST or None, request.FILES or None, instance=equipamento)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/laboratorio_pesquisa/{equipamento.laboratorio.id}/?tab=equipamentos', 'Equipamento editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def excluir_equipamento(request, equipamento_id):
    equipamento = get_object_or_404(EquipamentoLaboratorioPesquisa, pk=equipamento_id)
    pode_gerenciar = (
        request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == equipamento.laboratorio.coordenador
    )
    if pode_gerenciar:
        laboratorio = equipamento.laboratorio
        equipamento.delete()
        return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=equipamentos', 'Equipamento excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def editar_material(request, material_id):
    material = get_object_or_404(MaterialLaboratorioPesquisa, pk=material_id)
    pode_gerenciar = (
        request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == material.laboratorio.coordenador
    )
    if pode_gerenciar:
        title = 'Editar Equipamento'
        form = MaterialLaboratorioPesquisaForm(request.POST or None, request.FILES or None, instance=material)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/laboratorio_pesquisa/{material.laboratorio.id}/?tab=materiais', 'Material editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def excluir_material(request, material_id):
    material = get_object_or_404(MaterialLaboratorioPesquisa, pk=material_id)
    pode_gerenciar = (
        request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == material.laboratorio.coordenador
    )
    if pode_gerenciar:
        laboratorio = material.laboratorio
        material.delete()
        return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=materiais', 'Material excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def excluir_foto_laboratorio(request, foto_id):
    foto = get_object_or_404(FotoLaboratorioPesquisa, pk=foto_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == foto.laboratorio.coordenador
    if pode_gerenciar:
        laboratorio = foto.laboratorio
        foto.delete()
        return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=fotos', 'Foto excluída com sucesso.')


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def alterar_situacao_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    title = 'Alterar Situação da Obra'
    if obra.eh_ativa():
        form = SituacaoObraForm(request.POST or None, instance=obra)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/obra/{obra.id}/', 'Situação da obra alterada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def editar_parecer(request, parecerobra_id):
    parecer = get_object_or_404(ParecerObra, pk=parecerobra_id)
    title = 'Editar Parecer'
    obra = parecer.obra
    perguntas = PerguntaQuestionarioObra.objects.filter(ativo=True, tipo_questionario=parecer.obra.linha_editorial.tipo_questionario)
    form = AvaliacaoPareceristaObraForm(request.POST or None, request.FILES or None, perguntas=perguntas, instance=parecer)
    if form.is_valid():
        o = form.save(False)
        o.parecer_realizado_em = datetime.datetime.now()
        o.save()
        titulo = '[SUAP] Pesquisa: Notificação sobre Submissão de Obra'
        texto = f"""<h1>Pesquisa</h1>'
                    <h2>Submissão de Obra</h2>
                    <p>O pedido de publicação da obra <strong>{obra.titulo}<strong> foi {form.instance.situacao} pelo parecerista. Caso tenha sido aprovada com ressalvas, será necessário o reenvio da obra.</p>
                    <p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>"""
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obra.submetido_por_vinculo])
        return httprr(f'/pesquisa/obra/{obra.id}/?tab=analise_parecerista', 'Parecer editado com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def validar_projeto_fluxo_simplificado(request, projeto_id, opcao):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    pode_validar = get_uo(request.user) == projeto.uo or request.user.has_perm('pesquisa.tem_acesso_sistemico')
    if (
        pode_validar
        and not projeto.edital.tem_formato_completo()
        and not projeto.aprovado
        and not projeto.data_avaliacao
        and projeto.data_conclusao_planejamento
    ):
        if projeto.edital.exige_anuencia and projeto.anuencia is not True:
            return httprr(f'/pesquisa/projeto/{projeto.id}/', 'O projeto não recebeu a anuência da chefia imediata.', tag='error')

        if opcao == '1':
            vinculo = request.user.get_vinculo()
            projeto.pre_aprovado = True
            projeto.aprovado = True
            projeto.data_pre_avaliacao = datetime.date.today()
            projeto.data_avaliacao = datetime.date.today()
            projeto.vinculo_autor_pre_avaliacao = vinculo
            projeto.vinculo_supervisor = vinculo
            projeto.save()
            return httprr(f'/pesquisa/projeto/{projeto.id}/', 'Projeto deferido com sucesso.')
        elif opcao == '2':
            projeto.pre_aprovado = False
            projeto.aprovado = False
            projeto.data_pre_avaliacao = datetime.date.today()
            projeto.data_avaliacao = datetime.date.today()
            projeto.vinculo_autor_pre_avaliacao = request.user.get_vinculo()

            projeto.save()
            return httprr(f'/pesquisa/projeto/{projeto.id}/', 'Projeto indeferido com sucesso.')

        else:
            raise PermissionDenied

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_avaliar_obra')
def rejeitar_indicacao_parecerista_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    if ParecerObra.objects.filter(obra=obra, parecer_realizado_por_vinculo=request.user.get_vinculo()).exists():
        ParecerObra.objects.filter(obra=obra, parecer_realizado_por_vinculo=request.user.get_vinculo()).update(
            analise_indicacao_em=datetime.datetime.now(), recusou_indicacao=True
        )

        return httprr('/', 'Recusa de indicação cadastrada com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_avaliar_obra')
def aceitar_indicacao_parecerista_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    if ParecerObra.objects.filter(obra=obra, parecer_realizado_por_vinculo=request.user.get_vinculo(), aceitou_indicacao=False).exists():
        ParecerObra.objects.filter(obra=obra, parecer_realizado_por_vinculo=request.user.get_vinculo()).update(
            analise_indicacao_em=datetime.datetime.now(), aceitou_indicacao=True
        )

        return httprr(f'/pesquisa/obra/{obra.id}/?tab=analise_parecerista', 'Aceite de indicação registrado com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_avaliar_obra')
def emitir_declaracao_parecerista_obra(request):
    title = 'Emitir Declaração de Parecerista'
    obras_avaliadas = (
        ParecerObra.objects.filter(
            parecer_realizado_em__isnull=False, recusou_indicacao=False, parecer_realizado_por_vinculo=request.user.get_vinculo()
        )
        .values('obra__edital__titulo', 'obra__edital')
        .annotate(total=Count('obra'))
        .order_by('-obra__edital')
    )

    return locals()


@documento('Declaração de Parecerista', enumerar_paginas=False, validade=360, modelo='pesquisa.editalsubmissaoobra', forcar_recriacao=True)
@rtr()
@permission_required('pesquisa.pode_avaliar_obra')
def emitir_declaracao_parecerista_pdf(request, pk):
    edital = get_object_or_404(EditalSubmissaoObra, pk=pk)
    vinculo = request.user.get_vinculo()
    nome = vinculo.pessoa.nome

    hoje = datetime.datetime.now()
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
    meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    mes = meses[hoje.month - 1]
    ano = edital.data_inicio_submissao.year
    pareceres = ParecerObra.objects.filter(
        obra__edital=edital, parecer_realizado_em__isnull=False, recusou_indicacao=False, parecer_realizado_por_vinculo=vinculo
    ).order_by('obra__titulo')

    cidade = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
    if pareceres.exists():
        uo = get_uo(pareceres[0].obra.submetido_por_vinculo.user)
        if uo:
            cidade = uo.municipio.nome

    return locals()


@rtr()
@permission_required('pesquisa.pode_validar_obra, pesquisa.add_editalsubmissaoobra')
def listar_pareceristas_obras(request):
    title = 'Cadastro de Pareceristas'
    form = PareceristasObraForm(request.GET or None)
    if form.is_valid():
        area_conhecimento = form.cleaned_data['area_conhecimento']
        palavra_chave = form.cleaned_data['palavra_chave']
        uo = form.cleaned_data['uo']
        todos = form.cleaned_data['incluir_todos']
        if todos:
            ids_usuarios = UsuarioGrupo.objects.filter(group__name='Parecerista de Obra').only('user').values_list('user_id', flat=True)
            pareceristas = Vinculo.objects.filter(user__is_active=True, user__id__in=ids_usuarios).order_by('pessoa__nome')
            if area_conhecimento:
                area = AreaConhecimento.objects.filter(id=area_conhecimento.id)
                ids_servidores = Servidor.objects.filter(areas_de_conhecimento__in=area.values_list('id', flat=True)).values_list('id', flat=True)
                ids_pessoas_externas = AreaConhecimentoParecerista.objects.filter(
                    areas_de_conhecimento__in=area.values_list('id', flat=True)
                ).values_list('parecerista__id', flat=True)
                ids = set([int(x) for x in ids_servidores] + [int(x) for x in ids_pessoas_externas])
                pareceristas = pareceristas.filter(pessoa__id__in=ids)
            if uo:
                pareceristas = pareceristas.filter(setor__uo=uo)
            if palavra_chave:
                pareceristas = pareceristas.filter(pessoa__nome__icontains=palavra_chave)

            for parecerista in pareceristas:
                if parecerista.eh_servidor():
                    parecerista.areas = parecerista.relacionamento.areas_de_conhecimento.all()
                else:
                    if AreaConhecimentoParecerista.objects.filter(parecerista=parecerista.relacionamento).exists():
                        parecerista.areas = AreaConhecimentoParecerista.objects.filter(parecerista=parecerista.relacionamento)[
                            0
                        ].areas_de_conhecimento.all()

                registros = ParecerObra.objects.filter(
                    parecer_realizado_por_vinculo=parecerista, indicado_em__isnull=False, parecer_realizado_em__isnull=False
                ).only('parecer_realizado_em', 'indicado_em')
                if not registros.exists():
                    parecerista.registro = 'Nenhum parecer emitido.'
                else:
                    tempo = 0
                    for registro in registros:
                        tempo += (registro.parecer_realizado_em - registro.indicado_em).total_seconds()
                    total_registros = registros.count()
                    em_minutos = int((tempo / total_registros) / 60)
                    em_horas = int(em_minutos / 60)
                    em_dias = int(em_horas / 24)
                    if em_dias:
                        parecerista.registro = mark_safe(
                            '<strong>{}</strong> parecer{} emitido{}. Tempo médio de avaliação: <strong>{} hora{}</strong> ({} dia{})'.format(
                                total_registros,
                                pluralize(total_registros, 'es'),
                                pluralize(total_registros),
                                em_horas,
                                pluralize(em_horas),
                                em_dias,
                                pluralize(em_dias),
                            )
                        )
                    elif em_horas:
                        parecerista.registro = mark_safe(
                            f'<strong>{total_registros}</strong> parecer(es) emitido(s). Tempo médio de avaliação: <strong>{em_horas} hora{pluralize(em_horas)}</strong>'
                        )
                    else:
                        parecerista.registro = mark_safe(
                            f'<strong>{total_registros}</strong> parecer(es) emitido(s). Tempo médio de avaliação: <strong>{em_minutos} minutos</strong>'
                        )

        else:
            pareceristas = ParecerObra.objects.filter(parecer_realizado_em__isnull=False, recusou_indicacao=False).order_by(
                'parecer_realizado_por_vinculo__pessoa__nome'
            )
            if area_conhecimento:
                area = AreaConhecimento.objects.filter(id=area_conhecimento.id)
                ids_servidores = Servidor.objects.filter(areas_de_conhecimento__in=area.values_list('id', flat=True)).values_list('id', flat=True)
                ids_pessoas_externas = AreaConhecimentoParecerista.objects.filter(
                    areas_de_conhecimento__in=area.values_list('id', flat=True)
                ).values_list('parecerista__id', flat=True)
                ids = set([int(x) for x in ids_servidores] + [int(x) for x in ids_pessoas_externas])
                pareceristas = pareceristas.filter(parecer_realizado_por_vinculo__pessoa__id__in=ids)
            if uo:
                pareceristas = pareceristas.filter(parecer_realizado_por_vinculo__setor__uo=uo)
            if palavra_chave:
                pareceristas = pareceristas.filter(parecer_realizado_por_vinculo__pessoa__nome__icontains=palavra_chave)
            pareceristas = pareceristas.distinct('parecer_realizado_por_vinculo__pessoa__nome')
    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_obra')
def indicar_areas_conhecimento_de_interesse(request):
    title = 'Cadastrar Áreas de Conhecimento do seu Interesse'
    if request.user.get_vinculo().eh_prestador():
        pessoa = request.user.get_relacionamento()
        if AreaConhecimentoParecerista.objects.filter(parecerista=pessoa).exists():
            registro = AreaConhecimentoParecerista.objects.filter(parecerista=pessoa)[0]
            areas_conhecimentos = registro.areas_de_conhecimento.all().order_by('superior')
        else:
            registro = AreaConhecimentoParecerista()
            registro.parecerista = pessoa
            areas_conhecimentos = None
        form = AreaConhecimentoPareceristaForm(data=request.POST or None, request=request, instance=registro)
        if form.is_valid():
            form.save()

            return httprr('.', 'Áreas de conhecimento cadastradas com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_editalsubmissaoobra')
def alterar_autor(request, obra_id):
    title = 'Alterar Autor/Organizador'
    obra = get_object_or_404(Obra, pk=obra_id)
    form = AlterarAutorForm(request.POST or None, instance=obra)
    if form.is_valid():
        form.save()
        return httprr(f'/pesquisa/obra/{obra.id}/', 'Autor/Organizador editado com sucesso.')

    return locals()


# View que se conecta a view rh.views.servidor
@receiver(rh_servidor_view_tab)
def servidor_view_tab_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    participacoes_pesquisa = Participacao.objects.filter(vinculo_pessoa=servidor.get_vinculo(), ativo=True, projeto__aprovado=True)

    if participacoes_pesquisa.exists():
        return render_to_string(
            template_name='pesquisa/templates/servidor_view_tab.html',
            context={'lps_context': {'nome_modulo': 'pesquisa'}, 'servidor': servidor, 'participacoes_pesquisa': participacoes_pesquisa},
            request=request,
        )

    return False


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def clonar_projeto(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if not CurriculoVittaeLattes.objects.filter(vinculo=request.user.get_vinculo()).exists():
        raise PermissionDenied

    if not request.user.get_relacionamento().areas_de_conhecimento.exists():
        return httprr(
            '/pesquisa/tornar_avaliador/',
            'Você precisa se cadastrar como avaliador interno para poder submeter um projeto de pesquisa. Entre em contato com a Pró-Reitoria de Pesquisa para mais detalhes.',
            tag='error',
        )

    hoje = datetime.datetime.now().date()
    curriculo = CurriculoVittaeLattes.objects.filter(vinculo=request.user.get_vinculo())[0]
    if curriculo.datahora_atualizacao and curriculo.datahora_atualizacao.date() < (
        hoje - relativedelta(months=+edital.tempo_maximo_meses_curriculo_desatualizado)
    ):
        return httprr(
            '/pesquisa/editais_abertos/',
            f'Seu currículo lattes não foi atualizado nos últimos {edital.tempo_maximo_meses_curriculo_desatualizado} meses. Acesse a Plataforma Lattes para '
            'atualizá-lo. Entre em contato com a Pró-Reitoria de Pesquisa para mais detalhes.',
            tag='error',
        )

    grupo_pesquisa_online = True

    uos = get_uos(request)
    setores = [uo.sigla for uo in uos]

    if not BolsaDisponivel.objects.filter(edital=edital, uo__sigla__in=setores).exists():
        return httprr('/pesquisa/editais_abertos/', 'Este edital não possui oferta para o seu campus.', tag='error')

    instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    try:
        status = atualizar_grupos_pesquisa(curriculo.id)
        if status == 0 and edital.exige_grupo_pesquisa:
            return httprr(
                '/pesquisa/editais_abertos/',
                f'O SUAP não encontrou nenhum Grupo de Pesquisa do {instituicao_sigla} ao qual você esteja vinculado. '
                'Solicitamos que atualize seu Currículo Lattes e aguarde a disponibilização pública na base '
                'CNPQ para então iniciar a submissão do seu projeto.',
                tag='error',
            )
        if status == 3:
            erro_grupo_pesquisa_offline = True
    except Exception:
        grupo_pesquisa_online = False
    title = f'Clonar Projeto no Edital: {edital}'
    form = ClonarProjetoForm(request.POST or None, request=request, edital=edital)
    if form.is_valid():
        projeto_clonado = form.processar()
        return httprr(f'/pesquisa/projeto/{projeto_clonado.id}/', 'Projeto clonado com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.add_comissaoeditalpesquisa')
def adicionar_comissao(request):
    title = 'Adicionar Comissão de Avaliação'
    form = ComissaoAvaliacaoForm(request.POST or None, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/pesquisa/adicionar_comissao_por_area/{form.instance.id}/', 'Adicione os membros da comissão.')

    return locals()


@rtr()
@permission_required('pesquisa.add_comissaoeditalpesquisa')
def adicionar_comissao_por_area(request, comissao_id):
    title = 'Adicionar Comissão de Avaliação - Por Área de Conhecimento'
    comissao = get_object_or_404(ComissaoEditalPesquisa, pk=comissao_id)
    form = ComissaoAvaliacaoPorAreaForm(request.POST or None, request=request)
    internos = Servidor.objects.ativos().filter(areas_de_conhecimento__isnull=False).values_list('id', flat=True)
    avaliadores_internos = Vinculo.objects.filter(id_relacionamento__in=internos, tipo_relacionamento__model='servidor')
    externos = AvaliadorExterno.objects.all().values_list('vinculo', flat=True)
    avaliadores_externos = Vinculo.objects.filter(id__in=externos, tipo_relacionamento__model='prestadorservico').filter(
        id_relacionamento__in=PrestadorServico.objects.filter(areas_de_conhecimento__isnull=False).values_list('id', flat=True)
    )
    avaliadores_cadastrados = avaliadores_internos | avaliadores_externos
    titulacoes = comissao.edital.titulacoes_avaliador.all().values_list('codigo', flat=True)
    for pessoa in avaliadores_cadastrados.prefetch_related('user', 'pessoa'):
        if pessoa.eh_servidor():
            servidor = pessoa.relacionamento
            if (not servidor.titulacao) or servidor.titulacao.codigo not in titulacoes:
                avaliadores_cadastrados = avaliadores_cadastrados.exclude(id=pessoa.id)
        elif AvaliadorExterno.objects.filter(vinculo=pessoa).exists():
            avaliador_externo = AvaliadorExterno.objects.get(vinculo=pessoa)
            if avaliador_externo.titulacao.codigo not in titulacoes:
                avaliadores_cadastrados = avaliadores_cadastrados.exclude(id=avaliador_externo.vinculo.id)

    area_escolhida = None
    lista_avaliadores = []

    if form.is_valid():
        area_escolhida = form.cleaned_data.get('area_conhecimento')
        if area_escolhida:
            sevidores_da_area = Servidor.objects.filter(areas_de_conhecimento=area_escolhida)
            externos_da_area = PrestadorServico.objects.filter(areas_de_conhecimento=area_escolhida)
            avaliadores_cadastrados = avaliadores_cadastrados.filter(
                id_relacionamento__in=sevidores_da_area.values_list('id', flat=True), tipo_relacionamento__model='servidor'
            ) | avaliadores_cadastrados.filter(
                id_relacionamento__in=externos_da_area.values_list('id', flat=True), tipo_relacionamento__model='prestadorservico'
            )

    for pessoa in avaliadores_cadastrados.order_by('pessoa__nome'):
        if pessoa.id in comissao.vinculos_membros.all().values_list('id', flat=True):
            lista_avaliadores.append([pessoa, True])
        else:
            lista_avaliadores.append([pessoa, False])

    return locals()


@rtr()
@permission_required('pesquisa.add_comissaoeditalpesquisa')
def salvar_membros_da_comissao(request, comissao_id):
    comissao = get_object_or_404(ComissaoEditalPesquisa, pk=comissao_id)
    internos = Servidor.objects.ativos().filter(areas_de_conhecimento__isnull=False).values_list('id', flat=True)
    avaliadores_internos = Vinculo.objects.filter(id_relacionamento__in=internos, tipo_relacionamento__model='servidor')
    externos = AvaliadorExterno.objects.all().values_list('vinculo', flat=True)
    avaliadores_externos = Vinculo.objects.filter(id__in=externos, tipo_relacionamento__model='prestadorservico').filter(
        id_relacionamento__in=PrestadorServico.objects.filter(areas_de_conhecimento__isnull=False).values_list('id', flat=True)
    )

    avaliadores_cadastrados = avaliadores_internos | avaliadores_externos
    escolhidos = request.POST.getlist('registros')
    ids_escolhidos = []
    if escolhidos:
        for item in escolhidos:
            ids_escolhidos.append(int(item))

    for avaliador in avaliadores_cadastrados.filter(id__in=ids_escolhidos):
        comissao.vinculos_membros.add(avaliador)

    return httprr(f'/pesquisa/adicionar_comissao_por_area/{comissao.id}/', 'Avaliadores cadastrados com sucesso.')


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def projetos_pendentes_anuencia(request):
    title = 'Projetos Pendentes da Sua Anuência'
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        agora = datetime.datetime.now()
        projetos = (
            Projeto.objects.filter(
                pre_aprovado=False,
                aprovado=False,
                responsavel_anuencia=servidor,
                projetocancelado__isnull=True,
                anuencia_registrada_em__isnull=True,
                edital__formato=Edital.FORMATO_COMPLETO,
                edital__inicio_pre_selecao__gt=agora,
                edital__tipo_edital__in=[Edital.PESQUISA, Edital.INOVACAO],
            )
            | Projeto.objects.filter(
                pre_aprovado=False,
                aprovado=False,
                responsavel_anuencia=servidor,
                projetocancelado__isnull=True,
                anuencia_registrada_em__isnull=True,
                edital__formato=Edital.FORMATO_COMPLETO,
                edital__tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO,
                edital__fim_inscricoes__gt=agora,
            )
            | Projeto.objects.filter(
                pre_aprovado=False,
                aprovado=False,
                responsavel_anuencia=servidor,
                projetocancelado__isnull=True,
                edital__fim_inscricoes__gt=agora,
                edital__formato=Edital.FORMATO_SIMPLIFICADO,
            )
        )
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def registrar_anuencia(request: HttpRequest, projeto_id: int, opcao: str) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    agora = datetime.datetime.now()
    if request.user.get_relacionamento() == projeto.responsavel_anuencia and (projeto.edital.get_data_limite_anuencia() > agora):
        if opcao == '1':
            projeto.anuencia = True
            situacao = 'Anuência concedida'
        elif opcao == '2':
            projeto.anuencia = False
            situacao = 'Anuência negada'
        else:
            # opção inválida gravava `anuencia_registrada_em` sem decisão e dava 500 (#17551)
            raise Http404
        projeto.anuencia_registrada_em = agora
        projeto.save()
        historico = ProjetoHistoricoDeEnvio()
        historico.projeto = projeto
        historico.parecer_devolucao = situacao
        historico.data_operacao = datetime.datetime.now()
        historico.operador = request.user.get_relacionamento()
        historico.vinculo_operador = request.user.get_vinculo()
        historico.save()
        return httprr('/pesquisa/projetos_pendentes_anuencia/', 'Anuência registrada com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_edital')
def alterar_chefia_imediata(request, projeto_id):
    title = 'Alterar Responsável pela Anuência do Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.pode_alterar_chefia_imediata(request.user):
        form = AlterarChefiaForm(request.POST or None, instance=projeto)
        if form.is_valid():
            o = form.save(False)
            o.anuencia = None
            o.anuencia_registrada_em = None
            o.save()
            titulo = '[SUAP] Pesquisa: Anuência de Projeto de Pesquisa'
            texto = f'<h1>Pesquisa</h1><h2>Anuência de Projeto de Pesquisa</h2><p>Foi solicitada sua anuência no projeto de pesquisa: {projeto.titulo}. Acesse o SUAP para mais detalhes.</p>'
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('responsavel_anuencia').get_vinculo()])
            return httprr(f'/pesquisa/projeto/{projeto.id}/', 'Chefia imediata alterada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_edital')
def inativar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    if (usuario_logado.has_perm('pesquisa.pode_gerenciar_edital') and (get_uo(usuario_logado) == projeto.uo)) or projeto.is_gerente_sistemico(
        usuario_logado
    ):
        title = f'Inativar Projeto - {projeto.titulo}'
        form = InativarProjetoForm(request.POST or None, instance=projeto)
        if form.is_valid():
            o = form.save(False)
            o.inativado = True
            o.inativado_em = datetime.datetime.now()
            o.inativado_por = request.user.get_relacionamento()
            o.save()
            historico = ProjetoHistoricoDeEnvio()
            historico.projeto = projeto
            historico.parecer_devolucao = 'Projeto inativado'
            historico.data_operacao = datetime.datetime.now()
            historico.operador = request.user.get_relacionamento()
            historico.vinculo_operador = request.user.get_vinculo()
            historico.situacao = ProjetoHistoricoDeEnvio.FINALIZADO
            historico.save()
            return httprr(f'/pesquisa/projeto/{projeto.id}/', 'Projeto inativado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_ver_equipe_projeto')
def lista_email_coordenadores(request):
    title = 'Lista de Emails dos Coordenadores'
    form = EmailCoordenadoresForm(data=request.POST or None, request=request)
    if form.is_valid():
        hoje = datetime.datetime.now()
        emails = ''
        edital = form.cleaned_data['edital']
        situacao = form.cleaned_data['situacao']
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
        if situacao == EmailCoordenadoresForm.PROJETOS_EM_EDICAO:
            titulo_box = 'em Edição'
            title = 'Lista de Email dos Coordenadores - Projetos em Edição'
            projetos = Projeto.objects.filter(edital=edital)
            projetos = projetos.filter(data_conclusao_planejamento__isnull=True, edital__fim_inscricoes__gte=hoje).exclude(id__in=projetos_cancelados)

        elif situacao == EmailCoordenadoresForm.PROJETOS_ENVIADOS:
            titulo_box = 'Enviados'
            title = 'Lista de Email dos Coordenadores - Projetos Inscritos'
            projetos = Projeto.objects.filter(edital=edital)
            projetos = projetos.filter(
                Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
            ).exclude(id__in=projetos_cancelados)

        elif situacao == EmailCoordenadoresForm.PROJETOS_PRE_SELECIONADOS:
            titulo_box = 'Pré-Selecionados'
            title = 'Lista de Email dos Coordenadores - Projetos Pré-Selecionados'
            projetos = Projeto.objects.filter(edital=edital)
            projetos = projetos.filter(pre_aprovado=True, data_pre_avaliacao__isnull=False).exclude(id__in=projetos_cancelados)

        elif situacao == EmailCoordenadoresForm.PROJETOS_EM_EXECUCAO:
            titulo_box = 'em Execução'
            title = 'Lista de Email dos Coordenadores - Projetos em Execução'

            projetos = Projeto.objects.filter(
                edital=edital, pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False
            ).exclude(id__in=projetos_cancelados)

        elif situacao == EmailCoordenadoresForm.PROJETOS_EM_ATRASO:
            titulo_box = 'em Atraso'
            title = 'Lista de Email dos Coordenadores - Projetos em Atraso'
            projetos = Projeto.objects.filter(
                edital=edital, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, fim_execucao__lt=hoje.date()
            ).exclude(id__in=projetos_cancelados)

        elif situacao == EmailCoordenadoresForm.PROJETOS_CONCLUIDOS:
            titulo_box = 'Concluídos'
            title = 'Lista de Email dos Coordenadores - Concluídos'
            projetos = Projeto.objects.filter(edital=edital, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=False).distinct()

        if request.user.has_group_cached(['Coordenador de Extensão', 'Visualizador de Projetos do Campus']):
            projetos = projetos.filter(uo=get_uo(request.user))
        total = 0
        for projeto in projetos:
            if projeto.vinculo_coordenador.email_notificacao not in emails:
                emails = emails + projeto.vinculo_coordenador.email_notificacao + ';'
                total += 1
                if total % 10:
                    emails = emails + '\n'

    return locals()


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def desfazer_verificacao_antiplagio(request: HttpRequest, obra_id: int) -> HttpResponse:
    obra = get_object_or_404(Obra, pk=obra_id)
    if not obra.dentro_prazo_verifica_plagio():
        return httprr(
            f'/pesquisa/obra/{obra.id}/?tab=verificacao_autenticidade',
            'Não é possível desfazer a verificação antiplágio fora do prazo definido no edital.',
            tag='error',
        )
    verificacao_reprovou_obra = obra.situacao == Obra.CANCELADA and obra.autentica == Obra.NAO
    obra.autentica = None
    obra.autenticidade_obs = None
    obra.autenticidade_verificada_por_vinculo = None
    obra.autenticidade_verificada_em = None
    if verificacao_reprovou_obra:
        obra.situacao = Obra.SUBMETIDA
        obra.cancelada_por_vinculo = None
        obra.cancelada_em = None
        obra.justificativa_cancelamento = None
    elif obra.situacao == Obra.AUTENTICA:
        obra.situacao = Obra.SUBMETIDA
    obra.save()
    return httprr(f'/pesquisa/obra/{obra.id}/?tab=verificacao_autenticidade', 'Verificação antiplágio desfeita com sucesso.')


@rtr()
@permission_required('pesquisa.add_linhaeditorial')
def desfazer_validacao_conselho(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    obra.situacao_conselho_editorial = None
    obra.obs_conselho_editorial = None
    obra.julgamento_conselho_realizado_em = None
    obra.situacao = Obra.CLASSIFICADA
    obra.cancelada_por_vinculo = None
    obra.cancelada_em = None
    obra.save()
    return httprr(f'/pesquisa/obra/{obra.id}/?tab=validacao_conselho', 'Validação do conselho desfeita com sucesso.')


@rtr()
@permission_required('pesquisa.add_edital')
def reativar_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    if projeto.inativado and (
        (usuario_logado.has_perm('pesquisa.pode_gerenciar_edital') and (get_uo(usuario_logado) == projeto.uo))
        or projeto.is_gerente_sistemico(usuario_logado)
    ):
        projeto.inativado = False
        projeto.inativado_em = None
        projeto.inativado_por = None
        projeto.save()
        historico = ProjetoHistoricoDeEnvio()
        historico.projeto = projeto
        historico.parecer_devolucao = 'Projeto reativado'
        historico.data_operacao = datetime.datetime.now()
        historico.operador = request.user.get_relacionamento()
        historico.vinculo_operador = request.user.get_vinculo()
        historico.situacao = ProjetoHistoricoDeEnvio.REBAERTO
        historico.save()
        return httprr(f'/pesquisa/projeto/{projeto.id}/', 'Projeto reativado com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def solicitar_alteracao_equipe(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    title = 'Solicitar Alteração da Equipe'
    is_coordenador = projeto.is_gerenciador_projeto(usuario_logado)
    if (
        projeto.pode_editar_inscricao_execucao()
        and not projeto.eh_somente_leitura()
        and (is_coordenador or projeto.is_coordenador_pesquisa_campus_projeto(request.user))
    ):
        pode_avaliar_solicitacao = (
            request.user.has_perm('pesquisa.pode_gerenciar_edital') and (get_uo(request.user) == projeto.uo)
        ) or projeto.is_coordenador_pesquisa_campus_projeto(request.user)
        solicitacoes = SolicitacaoAlteracaoEquipe.objects.filter(projeto=projeto).order_by('-id')
        form = SolicitarAlteracaoEquipeForm(request.POST or None)
        if form.is_valid():
            o = form.save(False)
            o.projeto = projeto
            o.cadastrada_em = datetime.datetime.now()
            o.cadastrada_por = usuario_logado.get_vinculo()
            o.save()
            return httprr(f'/pesquisa/solicitar_alteracao_equipe/{projeto.id}/', 'Solicitação de alteração da equipe cadastrada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def avaliar_alteracao_equipe(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoAlteracaoEquipe, pk=solicitacao_id)
    projeto = solicitacao.projeto
    usuario_logado = request.user
    title = 'Avaliar Alteração da Equipe'
    pode_avaliar_solicitacao = projeto.is_coordenador_pesquisa_campus_projeto(request.user) or request.user.has_perm('pesquisa.tem_acesso_sistemico')
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura() and pode_avaliar_solicitacao:
        form = AvaliarAlteracaoEquipeForm(request.POST or None, instance=solicitacao)
        if form.is_valid():
            o = form.save(False)
            o.avaliada_em = datetime.datetime.now()
            o.avaliada_por = usuario_logado.get_vinculo()
            o.save()
            return httprr('..', 'Solicitação de alteração da equipe avaliada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def cadastrar_frequencia(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    eh_participante = projeto.eh_participante(request.user)
    title = 'Registrar Frequência/Atividade'
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

            return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade cadastrada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def validar_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if registro.projeto.is_responsavel(request.user):
        registro.validada_em = datetime.datetime.now()
        registro.validada_por = request.user.get_vinculo()
        registro.save()
        return httprr(f'/pesquisa/projeto/{registro.projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade validada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto, pesquisa.pode_acessar_lista_projetos')
def aceitar_termo_compromisso(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.vinculo_pessoa == request.user.get_vinculo():
        title = 'Aceitar Termo de Compromisso'
        form = AceiteTermoForm(request.POST or None, participacao=participacao, request=request)
        if form.is_valid():
            participacao.termo_aceito_em = datetime.datetime.now()
            participacao.save()
            return httprr(f'/pesquisa/projeto/{participacao.projeto.id}/?tab=equipe', 'Termo de compromisso aceito com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
                return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=plano_desembolso', 'Desembolso(s) excluído(s) com sucesso.')
            else:
                return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=plano_desembolso', 'Nenhum desembolso selecionado.', tag='error')
        else:
            return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=plano_desembolso', 'Nenhum desembolso selecionado.', tag='error')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.view_laboratoriopesquisa')
def solicitar_servico_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    title = f'Solicitar Serviço - {laboratorio}'
    form = SolicitarServicoLaboratorioForm(request.POST or None, request.FILES or None, laboratorio=laboratorio)
    cal_meses = []
    qs_solicitacoes = SolicitacaoServicoLaboratorio.objects.filter(
        laboratorio=laboratorio, situacao__in=[SolicitacaoServicoLaboratorio.DEFERIDA, SolicitacaoServicoLaboratorio.EM_ESPERA]
    )

    data_agora = datetime.datetime.now()
    ano_corrente = data_agora.year
    mes_corrente = data_agora.month
    if qs_solicitacoes.exists():
        data_fim = qs_solicitacoes.latest('data').data
        if (data_fim.year == ano_corrente and data_fim.month >= mes_corrente) or (data_fim.year > ano_corrente):
            ultimo_ano = data_fim.year
            ultimo_mes = data_fim.month
            cal = CalendarioPlus()
            cal.mostrar_mes_e_ano = True
            mes = mes_corrente
            for ano in range(ano_corrente, ultimo_ano + 1):
                mes_final = 12
                if ano == ultimo_ano:
                    mes_final = ultimo_mes
                for imes in range(mes, mes_final + 1):
                    for solicitacao in qs_solicitacoes.order_by('hora_inicio'):
                        solicitacao_conflito = False
                        for [agenda_data_inicio, agenda_data_fim] in [[solicitacao.data, solicitacao.data]]:
                            if agenda_data_inicio.year == ano and agenda_data_inicio.month == imes:
                                if solicitacao.situacao == SolicitacaoServicoLaboratorio.DEFERIDA:
                                    css = 'success'
                                else:
                                    css = 'alert'

                                horario = f'{solicitacao.hora_inicio} - {solicitacao.hora_termino}'
                                descricao = (
                                    f'<a href="" title="Serviço Agendado"><strong>{horario}</strong><br>{solicitacao.servico.descricao[:100]}</a>'
                                )

                                cal.adicionar_evento_calendario(agenda_data_inicio, agenda_data_fim, descricao, css)

                    cal_meses.append(cal.formato_mes(ano, imes))
                    # -------------------
                mes = 1

    if form.is_valid():
        o = form.save(False)
        o.laboratorio = laboratorio
        o.cadastrada_em = datetime.datetime.now()
        o.cadastrada_por = request.user.get_vinculo()
        o.save()
        titulo = '[SUAP] Laboratório: Solicitação de Serviço'
        texto = (
            '<h1>Pesquisa</h1>'
            '<h2>Laboratório - Solicitação de Serviço</h2>'
            f"<p>Foi realizada uma nova solicitação de serviço para o laboratório '{laboratorio.nome}'. Acesse o SUAP para mais detalhes.</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [laboratorio.coordenador.get_vinculo()])
        return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=servicos', 'Solicitação de serviço cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def avaliar_solicitacao(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoServicoLaboratorio, pk=solicitacao_id)
    pode_gerenciar = (
        request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == solicitacao.laboratorio.coordenador
    )
    if pode_gerenciar:
        opcao = request.GET.get('aprovar')
        title = 'Rejeitar Solicitação'
        if opcao:
            title = 'Aprovar Solicitação'

        form = AvaliarSolicitacaoLaboratorioForm(request.POST or None, request.FILES or None, instance=solicitacao, opcao=opcao)
        if form.is_valid():
            o = form.save(False)
            o.avaliada_em = datetime.datetime.now()
            if opcao:
                o.situacao = SolicitacaoServicoLaboratorio.DEFERIDA
            else:
                o.situacao = SolicitacaoServicoLaboratorio.INDEFERIDA
            o.save()
            titulo = '[SUAP] Avaliação: Solicitação de Serviço'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Avaliação - Solicitação de Serviço</h2>'
                f"<p>Sua solicitação de serviço para o laboratório '{solicitacao.laboratorio.nome}' foi avaliada. Acesse o SUAP para mais detalhes.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [solicitacao.cadastrada_por])
            return httprr('..', 'Solicitação avaliada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_laboratoriopesquisa')
def concluir_solicitacao(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoServicoLaboratorio, pk=solicitacao_id)
    pode_gerenciar = (
        request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == solicitacao.laboratorio.coordenador
    )
    if pode_gerenciar:
        solicitacao.situacao = SolicitacaoServicoLaboratorio.ATENDIDA
        solicitacao.save()
        titulo = '[SUAP] Conclusão do Serviço'
        texto = (
            '<h1>Pesquisa</h1>'
            '<h2>Conclusão do Serviço</h2>'
            f"<p>O serviço solicitado ao laboratório '{solicitacao.laboratorio.nome}' foi concluído. Acesse o SUAP para mais detalhes.</p>"
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [solicitacao.cadastrada_por])
        return httprr(f'/pesquisa/laboratorio_pesquisa/{solicitacao.laboratorio.id}/?tab=solicitacoes', 'Solicitação concluída com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.view_laboratoriopesquisa')
def minhas_solicitacoes_servicos(request):
    title = 'Minhas Solicitações de Serviço'
    solicitacoes = SolicitacaoServicoLaboratorio.objects.filter(cadastrada_por=request.user.get_vinculo())
    form = MinhasSolicitacoesServicosForm(request.POST or None)
    if form.is_valid():
        laboratorio = form.cleaned_data.get('laboratorio')
        situacao = form.cleaned_data.get('situacao')
        if laboratorio:
            solicitacoes = solicitacoes.filter(laboratorio=laboratorio)
        if situacao:
            solicitacoes = solicitacoes.filter(situacao=situacao)

    return locals()


@rtr()
@permission_required('pesquisa.view_laboratoriopesquisa')
def laboratorios_pesquisa(request):
    title = 'Laboratórios Multiusuários'
    laboratorios = LaboratorioPesquisa.objects.filter(aprovado=True)
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos_execucao = Projeto.objects.filter(
        pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False
    ).exclude(id__in=projetos_cancelados)
    eh_coordenador_projeto = projetos_execucao.filter(vinculo_coordenador=request.user.get_vinculo()).exists()
    form = FiltrarLaboratorioPesquisaForm(request.POST or None)
    if form.is_valid():
        uo = form.cleaned_data.get('uo')
        area_pesquisa = form.cleaned_data.get('area_pesquisa')
        tipo = form.cleaned_data.get('tipo')
        if uo:
            laboratorios = laboratorios.filter(uo=uo)
        if area_pesquisa:
            laboratorios = laboratorios.filter(area_pesquisa=area_pesquisa)
        if tipo:
            laboratorios = laboratorios.filter(tipo=tipo)

    return locals()


@rtr()
@permission_required('pesquisa.view_laboratoriopesquisa')
def acompanhar_solicitacao_servico(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoServicoLaboratorio, pk=solicitacao_id)
    if solicitacao.pode_acompanhar(request.user):
        title = 'Acompanhar Solicitação'
        qtd_comentarios = Comentario.objects.filter(
            content_type=ContentType.objects.get(app_label=solicitacao._meta.app_label, model=solicitacao._meta.model_name),
            object_id=solicitacao.pk,
            resposta=None,
        ).count()
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto, pesquisa.pode_acessar_lista_projetos')
def gerar_lista_frequencia(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    is_gerente_sistemico = request.user.has_perm('pesquisa.tem_acesso_sistemico')
    is_coordenador = projeto.is_responsavel(request.user)
    is_avaliador = request.user.has_group_cached('Avaliador Sistêmico de Projetos de Pesquisa')
    is_pre_avaliador, is_coordenador_pesquisa = _papeis_pesquisa_no_projeto(request.user, projeto)
    eh_participante = projeto.eh_participante(request.user)
    vinculo = request.user.get_vinculo()
    is_coordenador_edu = request.user.has_perm('pesquisa.pode_acessar_lista_projetos')
    is_assessor_pesquisa = request.user.has_group_cached('Assessor de Pesquisa')
    mesmo_campus = projeto.uo == get_uo(request.user)
    if not (
        is_coordenador_edu
        or is_coordenador_pesquisa
        or is_coordenador
        or is_gerente_sistemico
        or is_avaliador
        or is_assessor_pesquisa
        or (is_pre_avaliador and mesmo_campus)
        or eh_participante
        or projeto.vinculo_supervisor == vinculo
    ):
        raise PermissionDenied

    if is_coordenador_edu and not request.user.has_perm('pesquisa.pode_visualizar_projeto') and get_uo(request.user) != projeto.uo:
        raise PermissionDenied

    title = 'Lista de Frequência/Atividade'
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


@rtr()
def autocadastro_parecerista(request):
    title = 'Seja um Parecerista'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = AutoCadastroPareceristaForm(request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Cadastro realizado com sucesso. Você receberá um email com instruções quando seu cadastro for validado.')
    return locals()


@permission_required('pesquisa.add_pessoaexternaobra')
def validar_parecerista(request, pessoaexternaobra_id, opcao):
    pessoa = get_object_or_404(PessoaExternaObra, pk=pessoaexternaobra_id)
    validar = opcao == '1'
    invalidar = opcao == '2'
    if not pessoa.validado_em:
        if validar:
            if not pessoa.pessoa_fisica.email_pessoal:
                return httprr('..', 'Parecerista não tem e-mail pessoal cadastrado.', 'error')
            pessoa.ativo = True
        elif invalidar:
            pessoa.ativo = False

        pessoa.validado_por = request.user.get_vinculo()
        pessoa.validado_em = datetime.datetime.now()
        pessoa.save()

        if validar:
            grupo = Group.objects.get(name='Parecerista de Obra')
            pessoa.pessoa_fisica.get_user().groups.add(grupo)
            prestador = PrestadorServico.objects.filter(pessoa_fisica__cpf=pessoa.cpf)[0]
            sync_ldap_user(prestador.matricula)
            obj = TrocarSenha.objects.create(username=prestador.matricula)
            url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
            conteudo = f"""
            <h1>Pesquisa</h1>
            <h2>Validação do Cadastro de Parecerista</h2>
            <p>Prezado usuário,</p>
            <br />
            <p>Seu cadastro como parecerista acaba de ser validado.</p>
            <p>Caso ainda não tenha definido uma senha de acesso, por favor, acesse: {url}.</p>
            <br />
            <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf' ('usuário' tem que ser sem pontuação).</p>
            <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>
            """
            send_mail('[SUAP] Cadastro de Parecerista', conteudo, settings.DEFAULT_FROM_EMAIL, [prestador.email_pessoal])
        return httprr('..', 'Cadastrado avaliado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_pessoaexternaobra')
def ver_pessoa_externa(request, pessoaexternaobra_id):
    pessoa = get_object_or_404(PessoaExternaObra, pk=pessoaexternaobra_id)
    title = 'Visualizar Pessoa Externa'
    return locals()


@rtr('adicionar.html')
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_participante_colaborador(request, projeto_id):
    title = 'Adicionar Participante'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.edital.permite_colaborador_externo:
        raise PermissionDenied
    if not request.user.has_group_cached('Coordenador de Pesquisa'):
        tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        if request.method == 'POST':
            form = ParticipacaoColaboradorForm(data=request.POST, projeto=projeto)
            form.projeto = projeto
            if form.is_valid():
                participacao = form.save(False)
                participacao.projeto = projeto
                participacao.vinculo = TipoVinculo.VOLUNTARIO
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
                if projeto.edital.tem_termo_compromisso_colaborador_externo():
                    obj = TrocarSenha.objects.create(username=form.cleaned_data['prestador'].prestador.matricula)
                    url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
                    url_termo = f'{settings.SITE_URL}/pesquisa/aceitar_termo_compromisso/{participacao.id}/'
                    titulo = '[SUAP] Pesquisa: Termo de Compromisso do Colaborador Externo'
                    texto = f"""
                        <h1>Pesquisa</h1>
                        <h2>Termo de Compromisso do Colaborador Externo</h2>
                        <p>Você foi cadastrado(a) como membro da equipe do projeto \'{projeto.titulo}\'. Acesse o SUAP para aceitar o termo de compromisso <a href=\'{url_termo}\'>clicando aqui.</a></p>
                        <p>Ao acessar o SUAP, escolha a opção "Entrar com Gov.BR".</p>
                        <p>Caso não seja possível e ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
                        <br />
                        <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf' ('usuário' tem que ser sem pontuação).</p>
                        <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>'
                        """
                else:
                    obj = TrocarSenha.objects.create(username=form.cleaned_data['prestador'].prestador.matricula)
                    url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
                    titulo = '[SUAP] Pesquisa: Cadastro como Colaborador Externo'
                    texto = f"""
                        <h1>Pesquisa</h1>
                        <h2>Cadastro como Colaborador Externo</h2>
                        <p>Você foi cadastrado(a) como membro da equipe do projeto \'{projeto.titulo}\'.</p>
                        <p>Acesse o SUAP através do link {settings.SITE_URL} e escolha a opção "Entrar com Gov.BR".</p>
                        <p>Caso não seja possível e ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
                        <br />
                        <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf/passaporte' ('usuário' tem que ser sem pontuação).</p>
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_participante_colaborador(request, projeto_id, participacao_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not request.user.has_group_cached('Coordenador de Pesquisa'):
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
                historico = HistoricoEquipe.objects.filter(participante=participacao, projeto=projeto).order_by('id')
                if historico.exists():
                    registro = historico[0]
                    registro.data_movimentacao = form.cleaned_data.get('data')
                    registro.save()
            return httprr('..', 'Participante editado com sucesso.')

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
@permission_required('pesquisa.pode_visualizar_projeto')
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
@permission_required('pesquisa.pode_visualizar_projeto')
def editar_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if not registro.validada_em and registro.cadastrada_por == request.user.get_vinculo():
        title = 'Editar Frequência/Atividade Diária'
        form = EditarFrequenciaForm(request.POST or None, instance=registro)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/projeto/{registro.projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária editada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto')
def excluir_frequencia(request, registrofrequencia_id):
    registro = get_object_or_404(RegistroFrequencia, pk=registrofrequencia_id)
    if not registro.validada_em and registro.cadastrada_por == request.user.get_vinculo():
        projeto = registro.projeto
        registro.delete()
        return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=registro_frequencia', 'Frequência/Atividade diária excluída com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_foto(request, foto_id):
    foto = get_object_or_404(FotoProjeto, pk=foto_id)
    title = 'Editar Foto'
    projeto = foto.projeto
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = EditarFotoProjetoForm(request.POST or None, request.FILES or None, instance=foto)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/projeto/{projeto.id:d}/?tab=fotos', 'Foto editada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_avaliar_projeto')
def aceitar_indicacao(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    # Mesmo estado em que projetos_especial_pre_aprovados.html oferece "Aceitar Indicação".
    if projeto.edital.is_periodo_selecao() and projeto.pendente_avaliacao() and projeto.pode_aceitar_indicacao():
        AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=request.user.get_vinculo()).update(aceito_em=datetime.datetime.now())
        return httprr(f'/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/', 'Indicação aceita com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_relatorio(request, projeto_id):
    title = 'Adicionar Relatório'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = RelatorioProjetoForm(data=request.POST or None, files=request.FILES or None, projeto=projeto)
        if form.is_valid():
            o = form.save(False)
            o.cadastrado_em = datetime.datetime.now()
            o.projeto = projeto
            o.save()
            return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=relatorios', 'Relatório adicionado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_realizar_monitoramento_projeto')
def avaliar_relatorio(request, relatorio_id, situacao):
    title = 'Justificar da Não Aprovação do Relatório'
    relatorio = get_object_or_404(RelatorioProjeto, pk=relatorio_id)
    projeto = relatorio.projeto
    if (
        not projeto.eh_somente_leitura()
        and projeto.vinculo_supervisor == request.user.get_vinculo()
        or request.user.has_perm('pesquisa.tem_acesso_sistemico')
    ):
        if situacao == 1:
            relatorio.avaliado_em = datetime.datetime.now()
            relatorio.avaliado_por = request.user.get_vinculo()
            relatorio.aprovado = True
            relatorio.save()
            return httprr(f'/pesquisa/validar_execucao_etapa/{projeto.id}/', 'Relatório aprovado com sucesso.')
        elif situacao == 2:
            form = ReprovarExecucaoEtapaForm(request.POST or None)
            if form.is_valid():
                relatorio.avaliado_em = datetime.datetime.now()
                relatorio.avaliado_por = request.user.get_vinculo()
                relatorio.aprovado = False
                relatorio.justificativa_reprovacao = form.cleaned_data['obs']
                relatorio.save()
                return httprr('..', 'Justificativa de reprovação registrada com sucesso.')
    else:
        raise PermissionDenied

    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def avaliar_conclusao_projeto_por_relatorio(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.registroconclusaoprojeto_set.exclude(dt_avaliacao=None).exists() and (
        projeto.vinculo_supervisor == request.user.get_vinculo() or request.user.has_perm('pesquisa.tem_acesso_sistemico')
    ):
        title = 'Conclusão do Projeto'
        registro = projeto.get_registro_conclusao() or RegistroConclusaoProjeto()
        registro.projeto = projeto
        form = ValidacaoConclusaoProjetoForm(data=request.POST or None, registro=registro)
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
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def excluir_relatorio(request, relatorio_id):
    relatorio = get_object_or_404(RelatorioProjeto, pk=relatorio_id)
    tem_permissao(request, relatorio.projeto)
    if not relatorio.avaliado_em and relatorio.projeto.pode_editar_inscricao_execucao() and not relatorio.projeto.eh_somente_leitura():
        relatorio.delete()
        return httprr(f'/pesquisa/projeto/{relatorio.projeto.id}/?tab=relatorios', 'Relatório excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_relatorio(request, relatorio_id):
    relatorio = get_object_or_404(RelatorioProjeto, pk=relatorio_id)
    title = 'Editar Relatório'
    tem_permissao(request, relatorio.projeto)
    if not relatorio.avaliado_em and relatorio.projeto.pode_editar_inscricao_execucao() and not relatorio.projeto.eh_somente_leitura():
        form = RelatorioProjetoForm(request.POST or None, request.FILES or None, instance=relatorio, projeto=relatorio.projeto)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/projeto/{relatorio.projeto.id:d}/?tab=relatorios', 'Relatório com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_obra')
def ficha_avaliacao_obra(request, parecer_id):
    title = 'Detalhamento da Avaliação da Obra'
    avaliacao = get_object_or_404(ParecerObra, pk=parecer_id)
    if request.user.has_perm('pesquisa.add_pessoaexternaobra') or avaliacao.parecer_realizado_por_vinculo == request.user.get_vinculo():
        itens_avaliacao = ItemAvaliacaoObra.objects.filter(parecer=avaliacao).order_by('pergunta__ordem')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projeto, pesquisa.pode_acessar_lista_projetos')
def exportar_atividades_projeto_xls(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    vinculo = request.user.get_vinculo()
    is_gerente_sistemico = request.user.has_perm('pesquisa.tem_acesso_sistemico')
    is_coordenador = projeto.is_responsavel(request.user)
    is_avaliador = request.user.has_group_cached('Avaliador Sistêmico de Projetos de Pesquisa')
    is_pre_avaliador, is_coordenador_pesquisa = _papeis_pesquisa_no_projeto(request.user, projeto)
    eh_participante = projeto.eh_participante(request.user)
    is_coordenador_edu = request.user.has_perm('pesquisa.pode_acessar_lista_projetos')
    is_assessor_pesquisa = request.user.has_group_cached('Assessor de Pesquisa')
    mesmo_campus = projeto.uo == get_uo(request.user)
    eh_responsavel_anuencia = projeto.responsavel_anuencia and vinculo.eh_servidor() and vinculo.relacionamento == projeto.responsavel_anuencia
    if not (
        is_coordenador_edu
        or is_coordenador_pesquisa
        or is_coordenador
        or is_gerente_sistemico
        or is_avaliador
        or is_assessor_pesquisa
        or (is_pre_avaliador and mesmo_campus)
        or eh_participante
        or projeto.vinculo_supervisor == vinculo
        or eh_responsavel_anuencia
    ):
        raise PermissionDenied

    if is_coordenador_edu and not request.user.has_perm('pesquisa.pode_visualizar_projeto') and get_uo(request.user) != projeto.uo:
        raise PermissionDenied
    return tasks.exportar_atividades_projeto_xls(projeto)


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def indicar_auxiliar_projeto(request, projeto_id):
    title = 'Indicar Membro Auxiliar do Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=False)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = IndicarAuxiliarForm(request.POST or None, instance=projeto)
        if form.is_valid():
            form.save()
            titulo = '[SUAP] Pesquisa: Indicação como Membro Auxiliar'
            url = f'{settings.SITE_URL}/pesquisa/projeto/{projeto.id}/'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2> Indicação como Membro Auxiliar</h2>'
                f'<p>Você foi indicado(a) como membro auxiliar da equipe do projeto <a href="{url}"> \'{projeto.titulo}\'</a>. Assim, você tem a permissão de gerenciar os dados do projeto. Acesse o SUAP para mais detalhes.</p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [form.cleaned_data.get('auxiliar')])

            return httprr('..', 'Membro auxiliar indicado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required('Diretor de Pesquisa')
def avaliar_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    usuario_logado = request.user
    title = 'Avaliar Laboratório Multiusuário'
    if request.user.has_group_cached('Diretor de Pesquisa', ignore_groups_if_superuser=False):
        form = AvaliarLaboratorioMultiusuarioForm(request.POST or None, instance=laboratorio)
        if form.is_valid():
            o = form.save(False)
            o.avaliado_em = datetime.datetime.now()
            o.avaliado_por = usuario_logado.get_vinculo()
            o.aprovado = form.cleaned_data.get('aprovado')
            o.save()
            return httprr('..', 'Laboratório avaliado com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def programapos(request, pk):
    obj = get_object_or_404(ProgramaPosGraduacao, pk=pk)
    secretarios_programa = SecretarioProgramaPos.objects.filter(programa=obj).select_related('programa', 'secretario')
    docentes_programa = DocenteProgramaPos.objects.filter(programa=obj).select_related('programa', 'docente')
    areas_programa = AreaConcentracaoProgramaPos.objects.filter(programa=obj).select_related('programa', 'area_concentracao')
    cursos_programa = CursoProgramaPos.objects.filter(programa=obj).select_related('programa', 'curso')
    autoavaliacoes_programapos = AutoavaliacaoProgramaPos.objects.filter(programa=obj).select_related('programa')
    title = str(obj)

    return locals()


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def responder_autoavaliacao_programapos(request, pk):
    obj = get_object_or_404(AutoavaliacaoProgramaPos, pk=pk)
    title = f'Responder Autoavaliação do Programa {obj}'

    if not obj.pode_responder(request.user):
        return PermissionDenied('Você não tem permissão ou a autoavaliação não está em período de respostas.')

    QuesitoAutoavaliacaoFormSet = inlineformset_factory(
        AutoavaliacaoProgramaPos,
        QuesitoAutoavaliacao,
        form=QuesitoAutoavaliacaoForm,
        extra=0,
        can_delete=False,
        exclude=('respondido_por', 'respondido_em'),
    )
    formset = QuesitoAutoavaliacaoFormSet(request.POST or None, instance=obj)
    if request.method == 'POST':
        if formset.is_valid():
            for form in formset.forms:
                if request.user.get_vinculo():
                    quesito = form.cleaned_data.get('quesito')
                    QuesitoAutoavaliacao.objects.filter(quesito=quesito).update(
                        respondido_por=request.user.get_vinculo(), respondido_em=datetime.datetime.now()
                    )
            formset.save()
            return httprr('..', 'Respostas Atualizadas com Sucesso.')

    return locals()


@rtr('pesquisa/templates/respostas_autoavaliacao_programapos.html')
@permission_required('pesquisa.change_programaposgraduacao')
def respostas_autoavaliacao_programapos(request, pk):
    obj = get_object_or_404(AutoavaliacaoProgramaPos, pk=pk)
    title = f'Respostas da  Autoavaliação do Programa {obj}'

    if not request.user.has_group_cached(['Coordenador de Pós-Graduação', 'Diretor de Pesquisa']):
        raise PermissionDenied('Você não tem permissão visualizar respostas da autoavaliação')

    quesitos_da_autoavaliacao = QuesitoAutoavaliacao.objects.filter(autoavaliacao=obj).all().order_by('ordem')
    return locals()


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def vincular_secretario_programapos(request, pk):
    title = 'Vincular Secretário'
    obj = get_object_or_404(ProgramaPosGraduacao, pk=pk)

    form = SecretarioProgramaPosForm(obj=obj, data=request.POST or None)

    if form.is_valid():
        secretario = form.cleaned_data['secretario']
        secretario.get_vinculo().user.groups.add(Group.objects.filter(name='Secretário de Pós-Graduação').first())
        form.save(commit=True)
        redirect = '..'
        return httprr(redirect, 'Secretário vinculado com sucesso.')

    return locals()


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def desvincular_secretario_programapos(request, pk):
    title = 'Desvincular Secretário'
    obj = SecretarioProgramaPos.objects.filter(pk=pk).first()
    form = ExcluirRegistroForm(data=request.POST or None, request=request)
    if form.is_valid():
        try:
            sid = transaction.savepoint()
            obj.delete()
            obj.secretario.get_vinculo().user.groups.remove(Group.objects.filter(name='Secretário de Pós-Graduação').first())
            transaction.savepoint_commit(sid)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            return httprr('..', f'{e!s}', 'error')
        return httprr(request.GET.get('next', '..'), 'Registro(s) excluído(s) com sucesso.')
    return locals()


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def vincular_docente_programapos(request, pk):
    title = 'Vincular Docente'
    obj = get_object_or_404(ProgramaPosGraduacao, pk=pk)
    servidor = request.user.get_vinculo().relacionamento

    if (
        request.user.has_group_cached(['Diretor Acadêmico', 'Secretário Acadêmico', 'Coordenador de Pós-Graduação'])
        and servidor.setor_lotacao
        and servidor.setor_lotacao.uo == obj.campus_sede
    ):
        raise PermissionDenied

    form = DocenteProgramaPosForm(obj=obj, data=request.POST or None)

    if form.is_valid():
        form.save(commit=True)
        redirect = '..'
        return httprr(redirect, 'Docente vinculado com sucesso.')

    return locals()


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def vincular_area_concentracao_programapos(request, pk):
    title = 'Vincular Área de Concentração'
    obj = get_object_or_404(ProgramaPosGraduacao, pk=pk)

    form = AreaConcentracaoProgramaPosForm(obj=obj, data=request.POST or None)

    if form.is_valid():
        form.save(commit=True)
        redirect = '..'
        return httprr(redirect, 'Área de Concentração vinculada com sucesso.')

    return locals()


@permission_required('pesquisa.change_programaposgraduacao')
@rtr()
def vincular_curso_programapos(request, pk):
    title = 'Vincular Curso'
    obj = get_object_or_404(ProgramaPosGraduacao, pk=pk)

    form = CursoProgramaPosForm(obj=obj, data=request.POST or None)

    if form.is_valid():
        form.save(commit=True)
        redirect = '..'
        return httprr(redirect, 'Curso vinculado com sucesso.')

    return locals()


@permission_required('pesquisa.view_incubadora')
@rtr()
def incubadora(request, pk):
    incubadora = get_object_or_404(Incubadora, pk=pk)
    title = f'Incubadora Tecnológica - {incubadora}'
    pode_gerenciar_incubadora = incubadora.pode_gerenciar_incubadora(request.user)
    pode_editar_dados_incubadora = incubadora.pode_editar_dados_incubadora(request.user)

    return locals()


@permission_required('pesquisa.add_incubadora')
@rtr()
def cadastrar_membro_incubadora(request, pk):
    incubadora = get_object_or_404(Incubadora, pk=pk)
    title = f'Cadastrar Membro - Incubadora Tecnológica - {incubadora}'
    form = MembroIncubadoraForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.incubadora = incubadora
        o.save()
        return httprr('..', 'Membro cadastrado com sucesso.')
    return locals()


@permission_required('pesquisa.add_incubadora')
@rtr()
def editar_membro_incubadora(request, pk):
    membro = get_object_or_404(MembroIncubadora, pk=pk)
    title = f'Editar Membro - Incubadora Tecnológica - {incubadora}'
    form = MembroIncubadoraForm(request.POST or None, instance=membro)
    if form.is_valid():
        form.save()
        return httprr('..', 'Membro editado com sucesso.')
    return locals()


@permission_required('pesquisa.add_incubadora')
@rtr()
def excluir_membro_incubadora(request, pk):
    membro = get_object_or_404(MembroIncubadora, pk=pk)
    incubadora = membro.incubadora
    membro.delete()
    return httprr(f'/pesquisa/incubadora/{incubadora.id}/?tab=equipe', 'Membro excluído com sucesso.')


@permission_required('pesquisa.view_incubadora')
@rtr()
def cadastrar_empreendimento_incubadora(request, pk):
    incubadora = get_object_or_404(Incubadora, pk=pk)
    if incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Cadastrar Empreendimento - Incubadora Tecnológica - {incubadora}'
        form = EmpreendimentoIncubadoraForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.incubadora = incubadora
            o.cadastrado_por = request.user.get_vinculo()
            o.cadastrado_em = datetime.datetime.now()
            o.save()
            return httprr('..', 'Empreendimento cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def editar_empreendimento_incubadora(request, pk):
    empreendimento = get_object_or_404(EmpreendimentoIncubadora, pk=pk)
    if empreendimento.incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Editar Empreendimento - Incubadora Tecnológica - {empreendimento.incubadora}'
        form = EmpreendimentoIncubadoraForm(request.POST or None, request.FILES or None, instance=empreendimento)
        if form.is_valid():
            form.save()
            return httprr('..', 'Empreendimento editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def excluir_empreendimento_incubadora(request, pk):
    empreendimento = get_object_or_404(EmpreendimentoIncubadora, pk=pk)
    incubadora = empreendimento.incubadora
    if incubadora.pode_gerenciar_incubadora(request.user):
        empreendimento.delete()
        return httprr(f'/pesquisa/incubadora/{incubadora.id}/?tab=empreendimentos', 'Empreendimento excluído com sucesso.')
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def ver_empreendimento_incubadora(request, pk):
    empreendimento = get_object_or_404(EmpreendimentoIncubadora, pk=pk)
    title = f'{empreendimento}'
    return locals()


@permission_required('pesquisa.view_incubadora')
@rtr()
def cadastrar_documento_incubadora(request, pk):
    incubadora = get_object_or_404(Incubadora, pk=pk)
    if incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Cadastrar Documento - Incubadora Tecnológica - {incubadora}'
        form = DocumentoIncubadoraForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.incubadora = incubadora
            o.cadastrado_por = request.user.get_vinculo()
            o.cadastrado_em = datetime.datetime.now()
            o.save()
            return httprr('..', 'Documento cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def editar_documento_incubadora(request, pk):
    documento = get_object_or_404(DocumentoIncubadora, pk=pk)
    if documento.incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Editar Documento - Incubadora Tecnológica - {incubadora}'
        form = DocumentoIncubadoraForm(request.POST or None, instance=documento)
        if form.is_valid():
            form.save()
            return httprr('..', 'Documento editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def excluir_documento_incubadora(request, pk):
    documento = get_object_or_404(DocumentoIncubadora, pk=pk)
    incubadora = documento.incubadora
    if incubadora.pode_gerenciar_incubadora(request.user):
        documento.delete()
        return httprr(f'/pesquisa/incubadora/{incubadora.id}/?tab=documentos', 'Documento excluído com sucesso.')
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def cadastrar_foto_incubadora(request, pk):
    incubadora = get_object_or_404(Incubadora, pk=pk)
    if incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Cadastrar Foto - Incubadora Tecnológica - {incubadora}'
        form = FotoIncubadoraForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            o = form.save(False)
            o.incubadora = incubadora
            o.cadastrado_por = request.user.get_vinculo()
            o.cadastrado_em = datetime.datetime.now()
            o.save()
            return httprr('..', 'Foto cadastrada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def editar_foto_incubadora(request, pk):
    foto = get_object_or_404(FotoIncubadora, pk=pk)
    if foto.incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Editar Documento - Incubadora Tecnológica - {incubadora}'
        form = FotoIncubadoraForm(request.POST or None, instance=foto)
        if form.is_valid():
            form.save()
            return httprr('..', 'Foto editada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def excluir_foto_incubadora(request, pk):
    foto = get_object_or_404(FotoIncubadora, pk=pk)
    incubadora = foto.incubadora
    if incubadora.pode_gerenciar_incubadora(request.user):
        foto.delete()
        return httprr(f'/pesquisa/incubadora/{incubadora.id}/?tab=fotos', 'Foto excluída com sucesso.')
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def relatorio_empreendimentos_incubadora(request):
    title = 'Relatório de Empreendimentos Incubados'
    siglas = []
    incubadoras = Incubadora.objects.all()
    ano_atual = datetime.date.today().year
    tabela_ativos = {}
    tabela_graduados = {}
    tabela_desligados = {}
    somatorio_ativos = {}
    somatorio_graduados = {}
    somatorio_desligados = {}
    total_geral_ativos = 0
    total_geral_graduados = 0
    total_geral_desligados = 0

    ano = ano_atual
    for incubadora in incubadoras.order_by('sigla'):
        siglas.append(incubadora.sigla)
        somatorio_ativos[incubadora.sigla] = 0
        somatorio_graduados[incubadora.sigla] = 0
        somatorio_desligados[incubadora.sigla] = 0
    ano = ano_atual
    while ano > 2011:
        tabela_ativos[ano] = {'valores': []}
        tabela_graduados[ano] = {'valores': []}
        tabela_desligados[ano] = {'valores': []}
        total_ativos = total_graduados = total_desligados = 0
        for incubadora in incubadoras.order_by('sigla'):
            qtd_ativos = EmpreendimentoIncubadora.objects.filter(
                situacao=EmpreendimentoIncubadora.ATIVO, incubadora=incubadora, data_incubacao__year=ano
            ).count()
            tabela_ativos[ano]['valores'].append(qtd_ativos)
            total_ativos += qtd_ativos
            total_geral_ativos += qtd_ativos
            qtd_graduados = EmpreendimentoIncubadora.objects.filter(
                situacao=EmpreendimentoIncubadora.GRADUADO, incubadora=incubadora, data_incubacao__year=ano
            ).count()
            tabela_graduados[ano]['valores'].append(qtd_graduados)
            total_graduados += qtd_graduados
            total_geral_graduados += qtd_graduados
            qtd_desligados = EmpreendimentoIncubadora.objects.filter(
                situacao=EmpreendimentoIncubadora.DESLIGADO, incubadora=incubadora, data_incubacao__year=ano
            ).count()
            tabela_desligados[ano]['valores'].append(qtd_desligados)
            total_desligados += qtd_desligados
            total_geral_desligados += qtd_desligados
            somatorio_ativos[incubadora.sigla] += qtd_ativos
            somatorio_graduados[incubadora.sigla] += qtd_graduados
            somatorio_desligados[incubadora.sigla] += qtd_desligados
        tabela_ativos[ano]['valores'].append(total_ativos)
        tabela_graduados[ano]['valores'].append(total_graduados)
        tabela_desligados[ano]['valores'].append(total_desligados)
        ano = ano - 1
    return locals()


@rtr()
@permission_required('pesquisa.add_obra')
def editar_vinculo_membro_obra(request, membro_id):
    membro = get_object_or_404(MembroObra, pk=membro_id)
    obra = membro.obra
    vinculo = request.user.get_vinculo()
    eh_autor = vinculo == obra.submetido_por_vinculo
    if (eh_autor and obra.pode_cadastrar_autores() and obra.eh_ativa()) or request.user.has_perm('pesquisa.add_linhaeditorial'):
        title = f'Editar Cadastro - {membro}'
        form = MembroObraForm(request.POST or None, request.FILES or None, instance=membro, edicao=True)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/obra/{obra.id}', 'Cadastrado editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def metodologia_trl(request):
    title = 'Metodologia TRL'
    return locals()


@rtr()
@permission_required('pesquisa.add_registropropriedadeintelectual')
def pi_visualizar(request, pi_id):
    pi = get_object_or_404(RegistroPropriedadeIntelectual, pk=pi_id)
    title = pi.titulo and f'{pi.titulo} - {pi.tipo}' or f'{pi.tipo}'
    publicacoes = PublicacaoPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi).order_by('-data')
    servicos = ServicoRegistroPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi).order_by('-data')
    anuidades = AnuidadeRegistroPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi).order_by('inicio_ordinario')
    visualiza_anuidade = pi.eh_patente()
    visualiza_quinquenio = pi.eh_desenho_industrial()
    pode_relacionar_processo = 'processo_eletronico' in settings.INSTALLED_APPS
    if pode_relacionar_processo:
        from processo_eletronico.models import Processo

        ids = list(servicos.values_list('id_processo', flat=True)) + list(anuidades.values_list('id_processo', flat=True))
        processos = Processo.objects.filter(id__in=ids)
    return locals()


@rtr()
@permission_required('pesquisa.add_transferenciatecnologica')
def transferencia_visualizar(request, transferencia_id):
    transferencia = get_object_or_404(TransferenciaTecnologica, pk=transferencia_id)
    title = f'Transferência de Tecnologia - {transferencia.titulo}'
    recursos = RecursoTransferencia.objects.filter(transferencia=transferencia)
    documentos = DocumentoTransferencia.objects.filter(transferencia=transferencia)
    pode_relacionar_processo = 'processo_eletronico' in settings.INSTALLED_APPS
    if pode_relacionar_processo:
        from processo_eletronico.models import Processo

        ids = list(recursos.values_list('id_processo', flat=True))
        processos = Processo.objects.filter(Q(id__in=ids) | Q(id=transferencia.id_processo))
    return locals()


@rtr()
@permission_required('pesquisa.add_transferenciatecnologica')
def relatorio_transferencias(request):
    title = 'Relatório de Transferência Tecnológica'
    tipos_transferencia = TipoTransferenciaTecnologica.objects.all()
    transferencias = (
        TransferenciaTecnologica.objects.annotate(ano_dou=ExtractYear('data_dou'))
        .order_by('-ano_dou')
        .values('ano_dou', 'tipo__id')
        .annotate(count=Count('id'))
    )

    totais = {}
    for transferencia in transferencias:
        ano = transferencia['ano_dou']
        tipo_id = transferencia['tipo__id']
        count = transferencia['count']

        if ano not in totais:
            totais[ano] = {}

        totais[ano][tipo_id] = count
    return locals()


@rtr()
@permission_required('pesquisa.add_laboratoriopesquisa')
def tipo_laboratorio_multiusuario(request):
    title = 'Tipos de Laboratório Multiusuário'
    return locals()


@rtr()
@permission_required('pesquisa.add_registropropriedadeintelectual')
def relatorio_propriedades(request):
    title = 'Relatório de Propriedade Intelectual'
    tipos = PropriedadeIntelectual.objects.all().order_by('descricao')
    ano_atual = datetime.datetime.now().year
    primeiro_ano = RegistroPropriedadeIntelectual.objects.order_by('data').first()
    registros = []
    total = {}
    if primeiro_ano:
        ano = ano_atual
        while ano >= primeiro_ano.data.year:
            numeros = []
            numeros.append(ano)
            for tipo in tipos:
                quantidade = RegistroPropriedadeIntelectual.objects.filter(tipo=tipo, data__year=ano).count()
                numeros.append(quantidade)
                if f'{tipo.descricao}' in total:
                    total[f'{tipo.descricao}'] += quantidade
                else:
                    total[f'{tipo.descricao}'] = quantidade
            ano -= 1
            registros.append(numeros)
    return locals()


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
def relatorio_estatistica_laboratorios(request):
    title = 'Estatísticas dos Laboratórios'
    servicos_comunidade_interna = SolicitacaoServicoLaboratorio.objects.filter(
        tipo_entidade_atendida=SolicitacaoServicoLaboratorio.INTERNA, situacao=SolicitacaoServicoLaboratorio.ATENDIDA
    )
    servicos_comunidade_externa = SolicitacaoServicoLaboratorio.objects.filter(
        tipo_entidade_atendida=SolicitacaoServicoLaboratorio.EXTERNA, situacao=SolicitacaoServicoLaboratorio.ATENDIDA
    )
    form = EstatisticasLaboratoriosForm(request.POST or None)
    if form.is_valid():
        tipo = form.cleaned_data.get('tipo')
        ano = form.cleaned_data.get('ano')
        if tipo:
            servicos_comunidade_interna = servicos_comunidade_interna.filter(laboratorio__tipo=tipo)
            servicos_comunidade_externa = servicos_comunidade_externa.filter(laboratorio__tipo=tipo)
        if ano:
            servicos_comunidade_interna = servicos_comunidade_interna.filter(data__year=ano)
            servicos_comunidade_externa = servicos_comunidade_externa.filter(data__year=ano)
    servicos_comunidade_interna = servicos_comunidade_interna.only('id').count()
    servicos_comunidade_externa = servicos_comunidade_externa.only('id').count()
    return locals()


@rtr()
@permission_required('pesquisa.add_registropropriedadeintelectual')
def importar_rpi_mais_recente(request):
    from pesquisa.management.commands import importar_rpi, importar_rpi_software

    importar_rpi_command = importar_rpi.Command()
    rpi = importar_rpi_command.handle()
    importar_rpi_software_command = importar_rpi_software.Command()
    rpi_software = importar_rpi_software_command.handle()
    return httprr(
        '/admin/pesquisa/registropropriedadeintelectual/',
        f'Os despachos da RPI {rpi} (patente) e {rpi_software} (software) foram importados com sucesso.',
    )


@rtr()
@permission_required('pesquisa.add_registropropriedadeintelectual')
def visualizar_despachos_propriedade(request, propriedade_id):
    propriedade = get_object_or_404(RegistroPropriedadeIntelectual, pk=propriedade_id)
    title = f'Visualizar Despachos - {propriedade.numero_processo}'
    despachos = PublicacaoPropriedadeIntelectual.objects.filter(propriedadeintelectual=propriedade).order_by('-rpi')
    return locals()


@rtr()
@permission_required('pesquisa.add_registropropriedadeintelectual')
def despacho_lido(request, despacho_id):
    despacho = get_object_or_404(PublicacaoPropriedadeIntelectual, pk=despacho_id)
    despacho.lida = True
    despacho.lida_em = datetime.datetime.now()
    despacho.lida_por = request.user.get_vinculo()
    despacho.save()
    return httprr(f'/pesquisa/visualizar_despachos_propriedade/{despacho.propriedadeintelectual.id}/', 'Despacho lido com sucesso.')


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
@permission_required('pesquisa.pode_interagir_com_projeto')
def interpor_recurso(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if not projeto.pode_enviar_recurso():
        raise PermissionDenied
    if projeto.edital.inicio_selecao > datetime.datetime.now():
        return httprr(f'/pesquisa/enviar_recurso/{projeto.id}/')
    title = f'Interpor Recurso - {projeto.titulo} - {projeto.edital.titulo}'
    itens = ItemAvaliacao.objects.filter(avaliacao__projeto=projeto).order_by('criterio_avaliacao')
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
        form = InterporRecursoPesquisaForm(request.POST or None, ids_avaliacoes=ids_avaliacoes)
        if form.is_valid():
            for item_id in ids_avaliacoes:
                registro = ItemAvaliacao.objects.get(id=item_id)
                tem_permissao(request, registro.avaliacao.projeto, pode_auxiliar=True)
                registro.recurso = form.cleaned_data.get(f'{item_id}')
                registro.recurso_em = datetime.datetime.now()
                registro.recurso_por = request.user.get_vinculo()
                registro.save()
                titulo = '[SUAP] Pesquisa: Recurso Interposto pendente de avaliação'
                texto = (
                    '<h1>Pesquisa</h1>'
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

            return httprr(f'/pesquisa/projeto/{projeto.id}', 'Recurso encaminhado para análise.')
    else:
        form = InterporRecursoPesquisaForm(request.POST or None, ids_avaliacoes=ids_avaliacoes)
    return locals()


@rtr()
@permission_required('pesquisa.pode_avaliar_projeto')
def avaliar_recursos(request):
    title = 'Lista de recursos interpostos'
    editais = Edital.objects.all()
    vinculo_avaliador = request.user.get_vinculo()
    queryset = ItemAvaliacao.objects.filter(avaliacao__projeto__edital__in=editais.values_list('id', flat=True)).exclude(recurso=None)
    eh_sistemico = request.user.has_perm('pesquisa.pode_gerenciar_edital')
    form = AvaliarRecursosForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('uo'):
            queryset = queryset.filter(avaliacao__projeto__uo=form.cleaned_data.get('uo'))
        if form.cleaned_data.get('edital'):
            queryset = queryset.filter(avaliacao__projeto__edital=form.cleaned_data.get('edital'))
        if form.cleaned_data.get('situacao') and form.cleaned_data.get('situacao') == 'Pendentes de avaliação':
            queryset = queryset.filter(recurso_avaliado_em=None)
        if form.cleaned_data.get('vinculados_a_mim'):
            queryset = queryset.filter(avaliacao__vinculo_id=vinculo_avaliador)
    if eh_sistemico:
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
@permission_required('pesquisa.pode_avaliar_projeto')
def avaliar_recurso(request, itemavaliacao_id):
    item = get_object_or_404(ItemAvaliacao, pk=itemavaliacao_id)
    projeto = item.avaliacao.projeto
    vinculo_avaliador = request.user.get_vinculo()
    editais = Edital.objects.all().em_avaliacao_recursos()
    url = request.META.get('HTTP_REFERER', '.')
    if (
        item.recurso
        and (request.user.has_perm('pesquisa.pode_gerenciar_edital') or item.avaliacao.vinculo == vinculo_avaliador)
        and projeto.edital.id in editais.values_list('id', flat=True)
    ):
        title = 'Avaliar Recurso'
        form = AvaliarRecursoForm(request.POST or None, instance=item, url=url)
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

            return httprr(form.cleaned_data.get('url'), 'Recurso avaliado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.view_comissaoeditalpesquisa')
def ver_membros_comissao(request, comissao_id):
    comissao = get_object_or_404(ComissaoEditalPesquisa, pk=comissao_id)
    title = f'Membros da {comissao}'
    return locals()


@rtr(two_factor_authentication=True)
@permission_required('pesquisa.pode_visualizar_projeto')
def cadastrar_dados_bancarios(request, participacao_id):
    participacao = get_object_or_404(Participacao, pk=participacao_id)
    if participacao.vinculo_pessoa == request.user.get_vinculo() and not participacao.projeto.eh_somente_leitura():
        title = 'Cadastrar/Atualizar Dados Bancários'
        form = DadosBancariosParticipanteForm(request.POST or None, instance=participacao)
        if form.is_valid():
            form.save()
            titulo = '[SUAP] Pesquisa: Dados bancários atualizados'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Dados bancários atualizados</h2>'
                f"<p>Seus dados bancários cadastrados no projeto '{participacao.projeto.titulo}' foram atualizados. Se você não realizou esta alteração, procure o coordenador do projeto e o coordenador de pesquisa do seu campus.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.vinculo_pessoa])
            return httprr(f'/pesquisa/projeto/{participacao.projeto.id}/?tab=equipe', 'Dados bancários atualizados com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def remover_indicacao_avaliador(request, avaliador_id):
    avaliador = get_object_or_404(AvaliadorIndicado, pk=avaliador_id)
    avaliador.delete()
    url = request.META.get('HTTP_REFERER', '.')
    if not AvaliadorIndicado.objects.filter(vinculo=avaliador.vinculo).exists():
        grupo = Group.objects.get(name='Avaliador Sistêmico de Projetos de Pesquisa')
        avaliador.vinculo.user.groups.remove(grupo)
    return httprr(url, 'Indicação de avaliador removida com sucesso.')


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def adicionar_termo_cessao_pi(request, pi_id):
    pi = get_object_or_404(RegistroPropriedadeIntelectual, pk=pi_id)
    title = f'Adicionar termo de cessão - {pi}'
    form = TermoCessaoRPIForm(request.POST or None, request.FILES or None, instance=pi)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('documento'):
            o.id_documento_termo_cessao = form.cleaned_data.get('documento').id
        o.save()
        return httprr(f'/pesquisa/pi_visualizar/{pi.id}', 'Termo de cessão cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def relacionar_processo_pi(request, servico_id):
    servico = get_object_or_404(ServicoRegistroPropriedadeIntelectual, pk=servico_id)
    title = f'Relacionar Processo - {servico}'
    form = RelacionarProcessoRPIForm(request.POST or None, servico=servico)
    if form.is_valid():
        servico.id_processo = form.cleaned_data.get('processo').id
        servico.save()
        return httprr(f'/pesquisa/pi_visualizar/{servico.propriedadeintelectual.id}/?tab=servicos', 'Processo relacionado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def relacionar_processo_pi_anuidade(request, anuidade_id):
    anuidade = get_object_or_404(AnuidadeRegistroPropriedadeIntelectual, pk=anuidade_id)
    title = f'Relacionar Processo - {anuidade}'
    form = RelacionarProcessoAnuidadeRPIForm(request.POST or None, anuidade=anuidade)
    if form.is_valid():
        anuidade.id_processo = form.cleaned_data.get('processo').id
        anuidade.save()
        return httprr(f'/pesquisa/pi_visualizar/{anuidade.propriedadeintelectual.id}/?tab=anuidades', 'Processo relacionado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def informar_pagamento_anuidade(request, anuidade_id):
    anuidade = get_object_or_404(AnuidadeRegistroPropriedadeIntelectual, pk=anuidade_id)
    if anuidade.estah_pendente():
        title = f'Informar pagamento - {anuidade}'
        form = InformarPagamentoAnuidadeRPIForm(request.POST or None, instance=anuidade)
        if form.is_valid():
            o = form.save(False)
            o.pagamento_informado_por = request.user.get_vinculo()
            o.pagamento_informado_em = datetime.datetime.now()
            o.situacao = AnuidadeRegistroPropriedadeIntelectual.PAGO
            o.save()
            return httprr(f'/pesquisa/pi_visualizar/{anuidade.propriedadeintelectual.id}/?tab=anuidades', 'Pagamento registrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def arquivar_pi(request, propriedade_id):
    registro = get_object_or_404(RegistroPropriedadeIntelectual, pk=propriedade_id)
    title = f'Arquivar - {registro}'
    if registro.ativo:
        form = ArquivarPIForm(request.POST or None, instance=registro)
        if form.is_valid():
            o = form.save(False)
            o.arquivado_em = datetime.datetime.now()
            o.arquivado_por = request.user.get_vinculo()
            o.ativo = False
            o.save()
            termo = 'Arquivado'
            return httprr(f'/pesquisa/pi_visualizar/{registro.id}/', f'Registro {termo} com sucesso.')
        return locals()
    else:
        registro.ativo = True
        registro.arquivado_em = datetime.datetime.now()
        registro.arquivado_por = request.user.get_vinculo()
        registro.motivo_arquivamento = None
        registro.save()
        termo = 'Desarquivado'
        return httprr(f'/pesquisa/pi_visualizar/{registro.id}/', f'Registro {termo} com sucesso.')


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def indicar_orientador_projeto(request, projeto_id):
    title = 'Indicar Orientador do Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = IndicarOrientadorForm(request.POST or None, instance=projeto)
        if form.is_valid():
            form.save()
            return httprr('..', 'Orientador indicado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def indicar_coorientador_projeto(request, projeto_id):
    title = 'Indicar Coorientador do Projeto'
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    tem_permissao(request, projeto, pode_auxiliar=True)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura():
        form = IndicarCoorientadorForm(request.POST or None, instance=projeto)
        if form.is_valid():
            form.save()
            return httprr('..', 'Coorientador indicado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def classificar_trl(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    is_gerente_sistemico = request.user.has_perm('pesquisa.tem_acesso_sistemico')
    is_coordenador = projeto.is_responsavel(request.user)
    if projeto.edital.utiliza_metodologia_trl and (is_coordenador or is_gerente_sistemico):
        title = f'Classificar TRL do Projeto - {projeto.titulo}'
        form = ClassificarTRLForm(request.POST or None, instance=projeto)
        if form.is_valid():
            form.save()
            return httprr('..', 'Classificação TRL realizada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_registropropriedadeintelectual')
def importar_rpi_especifica(request, numero_rpi):
    args = ()
    options = {'numero_da_rpi': numero_rpi}
    from pesquisa.management.commands import importar_rpi, importar_rpi_software

    importar_rpi_command = importar_rpi.Command()
    rpi = importar_rpi_command.handle(*args, **options)
    importar_rpi_software_command = importar_rpi_software.Command()
    rpi_software = importar_rpi_software_command.handle(*args, **options)
    return httprr(
        '/admin/pesquisa/registropropriedadeintelectual/',
        f'Os despachos da RPI {rpi} (patente) e {rpi_software} (software) foram importados com sucesso.',
    )


@rtr()
def cadastrar_evento_incubadora(request, pk):
    incubadora = get_object_or_404(Incubadora, pk=pk)
    if incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Cadastrar Evento - Incubadora Tecnológica - {incubadora}'
        form = EventoIncubadoraForm(request.POST or None)
        if form.is_valid():
            o = form.save(False)
            o.incubadora = incubadora
            o.cadastrado_por = request.user.get_vinculo()
            o.cadastrado_em = datetime.datetime.now()
            o.save()
            return httprr('..', 'Evento cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def editar_evento_incubadora(request, pk):
    evento = get_object_or_404(EventoIncubadora, pk=pk)
    if evento.incubadora.pode_gerenciar_incubadora(request.user):
        title = f'Editar Evento - Incubadora Tecnológica - {incubadora}'
        form = EventoIncubadoraForm(request.POST or None, instance=evento)
        if form.is_valid():
            form.save()
            return httprr('..', 'Evento editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@permission_required('pesquisa.view_incubadora')
@rtr()
def excluir_evento_incubadora(request, pk):
    evento = get_object_or_404(EventoIncubadora, pk=pk)
    incubadora = evento.incubadora
    if incubadora.pode_gerenciar_incubadora(request.user):
        evento.delete()
        return httprr(f'/pesquisa/incubadora/{incubadora.id}/?tab=eventos', 'Evento excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
def vincular_projeto_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(LaboratorioPesquisa, pk=laboratorio_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == laboratorio.coordenador
    if pode_gerenciar:
        title = 'Vincular Projeto'
        projeto = ProjetoLaboratorioPesquisa()
        projeto.laboratorio = laboratorio
        form = ProjetoLaboratorioForm(request.POST or None, instance=projeto)
        if form.is_valid():
            o = form.save(False)
            if form.cleaned_data.get('tipo') == 'Pesquisa':
                o.id_do_projeto = form.cleaned_data.get('projeto_pesquisa').id
            else:
                o.id_do_projeto = form.cleaned_data.get('projeto_extensao').id
            o.cadastrado_por = request.user.get_vinculo()
            o.cadastrado_em = datetime.datetime.now()
            o.save()
            return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=projetos', 'Projeto vinculado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
def excluir_projeto_laboratorio(request, projetolaboratorio_id):
    projeto = get_object_or_404(ProjetoLaboratorioPesquisa, pk=projetolaboratorio_id)
    pode_gerenciar = request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.get_relacionamento() == projeto.laboratorio.coordenador
    if pode_gerenciar:
        laboratorio = projeto.laboratorio
        projeto.delete()
        return httprr(f'/pesquisa/laboratorio_pesquisa/{laboratorio.id}/?tab=projetos', 'Projeto desvinculado com sucesso.')
    else:
        raise PermissionDenied


@permission_required('pesquisa.tem_acesso_sistemico')
@rtr()
def solicitacoes_alteracao_equipe(request):
    title = 'Solicitações de Alteração da Equipe'
    solicitacoes = SolicitacaoAlteracaoEquipe.objects.all().order_by('-id')
    ano = request.GET.get('ano')
    num_page = 20
    form = SolicitacoesAlteracaoForm(request.GET or None, request=request, ano=ano)
    if form.is_valid():
        if form.cleaned_data.get('uo'):
            solicitacoes = solicitacoes.filter(projeto__uo=form.cleaned_data['uo'])

        if form.cleaned_data.get('ano'):
            solicitacoes = solicitacoes.filter(projeto__edital__inicio_inscricoes__year=form.cleaned_data['ano'])

        if form.cleaned_data.get('edital'):
            solicitacoes = solicitacoes.filter(projeto__edital=form.cleaned_data['edital'])

        if form.cleaned_data.get('situacao'):
            if form.cleaned_data.get('situacao') == '1':
                solicitacoes = solicitacoes.filter(atendida=True)
            elif form.cleaned_data.get('situacao') == '2':
                solicitacoes = solicitacoes.filter(atendida=False)
            else:
                solicitacoes = solicitacoes.filter(atendida=None)

        if form.cleaned_data.get('paginacao'):
            num_page = form.cleaned_data.get('paginacao')

        if form.cleaned_data.get('palavra_chave'):
            solicitacoes = solicitacoes.filter(
                Q(projeto__titulo__icontains=form.cleaned_data['palavra_chave'])
                | Q(projeto__edital__titulo__icontains=form.cleaned_data['palavra_chave'])
            )
    return locals()


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def classificacao_locarno(request, pi_id):
    pi = get_object_or_404(RegistroPropriedadeIntelectual, pk=pi_id)
    title = f'Classificação Locarno - {pi}'
    form = ClassificacaoLocarnoForm(request.POST or None, instance=pi)
    if form.is_valid():
        form.save()
        return httprr(f'/pesquisa/pi_visualizar/{pi.id}', 'Classificação Locarno cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def importar_dados_di_inpi(request, pi_id):
    pi = get_object_or_404(RegistroPropriedadeIntelectual, pk=pi_id)
    args = ()
    options = {'numero_processo': pi.numero_processo, 'origem_view': True, 'pythonpath': None, 'verbosity': '1', 'traceback': None, 'settings': None}
    from pesquisa.management.commands import importar_servicos_rpi_di

    di_command = importar_servicos_rpi_di.Command()
    di_command.handle(*args, **options)
    return httprr(f'/pesquisa/pi_visualizar/{pi.id}', 'Dados importados com sucesso.')


@rtr()
@permission_required('pesquisa.pode_se_tornar_avaliador')
def visualizar_projetos_avaliador(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Projetos avaliados - {edital.titulo}'
    avaliacoes = Avaliacao.objects.filter(projeto__edital=edital, vinculo=request.user.get_vinculo())
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def solicitar_inclusao_equipe(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    usuario_logado = request.user
    title = 'Solicitar Inclusão na Equipe'
    is_coordenador = projeto.is_gerenciador_projeto(usuario_logado)
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura() and is_coordenador:
        form = SolicitarInclusaoEquipeForm(request.POST or None, projeto=projeto)
        if form.is_valid():
            vinculo_pessoa = form.cleaned_data.get('vinculo_pessoa')
            solicitacao = SolicitacaoInclusaoEquipe()
            solicitacao.projeto = projeto
            solicitacao.cadastrada_por = request.user.get_vinculo()
            solicitacao.cadastrada_em = datetime.datetime.now()
            solicitacao.vinculo_pessoa = vinculo_pessoa
            solicitacao.vinculo = form.cleaned_data.get('vinculo')
            solicitacao.carga_horaria = form.cleaned_data.get('carga_horaria')
            solicitacao.data = form.cleaned_data.get('data')
            solicitacao.obs = form.cleaned_data.get('obs')
            if Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo_pessoa).exists():
                return httprr('.', f'{vinculo_pessoa} já pertence ao projeto.', tag='error')
            if vinculo_pessoa.eh_servidor():
                servidor = vinculo_pessoa.relacionamento
                if servidor.eh_docente:
                    solicitacao.titulacao = 'DOCENTE ({})'.format(servidor.titulacao or '-')
                if servidor.eh_tecnico_administrativo:
                    solicitacao.titulacao = 'TÉCNICO-ADMINISTRATIVO ({})'.format(servidor.titulacao or '-')
                if servidor.eh_aposentado:
                    solicitacao.titulacao = 'APOSENTADO ({})'.format(servidor.titulacao or '-')
                if servidor.eh_estagiario:
                    solicitacao.titulacao = 'ESTAGIÁRIO ({})'.format(servidor.titulacao or '-')
            elif vinculo_pessoa.eh_aluno():
                solicitacao.titulacao = 'DISCENTE'
            else:
                solicitacao.titulacao = 'COLABORADOR EXTERNO'
            solicitacao.save()

            return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=equipe', 'Solicitação de inclusão na equipe cadastrada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def avaliar_inclusao_equipe(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoInclusaoEquipe, pk=solicitacao_id)
    projeto = solicitacao.projeto
    usuario_logado = request.user
    vinculo_pessoa = solicitacao.vinculo_pessoa
    title = 'Avaliar Inclusão na Equipe'
    pode_avaliar_solicitacao = projeto.is_coordenador_pesquisa_campus_projeto(request.user) or request.user.has_perm('pesquisa.tem_acesso_sistemico')
    if projeto.pode_editar_inscricao_execucao() and not projeto.eh_somente_leitura() and pode_avaliar_solicitacao:
        form = AvaliarInclusaoEquipeForm(request.POST or None, instance=solicitacao)
        if form.is_valid():
            o = form.save(False)
            o.avaliada_em = datetime.datetime.now()
            o.avaliada_por = usuario_logado.get_vinculo()
            o.save()
            if form.cleaned_data.get('atendida'):
                participacao = Participacao()
                participacao.projeto = projeto
                participacao.vinculo = solicitacao.vinculo
                participacao.carga_horaria = solicitacao.carga_horaria
                if solicitacao.vinculo == TipoVinculo.BOLSISTA:
                    participacao.bolsa_concedida = True
                participacao.vinculo_pessoa = vinculo_pessoa
                participacao.save()
                Participacao.gerar_anexos_do_participante(participacao)
                if vinculo_pessoa.eh_servidor():
                    participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR, data_evento=solicitacao.data)
                    if projeto.edital.termo_compromisso_servidor:
                        titulo = '[SUAP] Pesquisa: Termo de Compromisso do Servidor'
                        texto = (
                            '<h1>Pesquisa</h1>'
                            '<h2>Termo de Compromisso do Servidor</h2>'
                            f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                        )
                        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo_pessoa])
                elif vinculo_pessoa.eh_aluno():
                    participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=solicitacao.data)

                    if projeto.edital.termo_compromisso_aluno and form.cleaned_data.get('aluno'):
                        titulo = '[SUAP] Pesquisa: Termo de Compromisso do Aluno'
                        texto = (
                            '<h1>Pesquisa</h1>'
                            '<h2>Termo de Compromisso do Aluno</h2>'
                            f"<p>Você foi cadastrado(a) como membro da equipe do projeto '{projeto.titulo}'. Acesse o SUAP para aceitar o termo de compromisso.</p>"
                        )
                        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo_pessoa])
                else:
                    participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_COLABORADOR, data_evento=solicitacao.data)
                    if projeto.edital.tem_termo_compromisso_colaborador_externo():
                        obj = TrocarSenha.objects.create(username=vinculo_pessoa.relacionamento.matricula)
                        url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
                        url_termo = f'{settings.SITE_URL}/pesquisa/aceitar_termo_compromisso/{participacao.id}/'
                        titulo = '[SUAP] Pesquisa: Termo de Compromisso do Colaborador Externo'
                        texto = f"""
                            <h1>Pesquisa</h1>
                            <h2>Termo de Compromisso do Colaborador Externo</h2>
                            <p>Você foi cadastrado(a) como membro da equipe do projeto \'{projeto.titulo}\'. Acesse o SUAP para aceitar o termo de compromisso <a href=\'{url_termo}\'>clicando aqui.</a></p>
                            <p>Caso ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
                            <br />
                            <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf' ('usuário' tem que ser sem pontuação).</p>
                            <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>'
                            """
                    else:
                        obj = TrocarSenha.objects.create(username=vinculo_pessoa.relacionamento.matricula)
                        url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
                        titulo = '[SUAP] Pesquisa: Cadastro como Colaborador Externo'
                        texto = f"""
                            <h1>Pesquisa</h1>
                            <h2>Cadastro como Colaborador Externo</h2>
                            <p>Você foi cadastrado(a) como membro da equipe do projeto \'{projeto.titulo}\'. Acesse o SUAP para mais detalhes.</p>
                            <p>Caso ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
                            <br />
                            <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf/passaporte' ('usuário' tem que ser sem pontuação).</p>
                            <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>'
                            """

                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo_pessoa])

            return httprr('..', 'Inclusão de alteração da equipe avaliada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@permission_required('pesquisa.tem_acesso_sistemico')
@rtr()
def solicitacoes_inclusao_equipe(request):
    title = 'Solicitações de Inclusão na Equipe'
    solicitacoes = SolicitacaoInclusaoEquipe.objects.all().order_by('-id')
    ano = request.GET.get('ano')
    num_page = 20
    form = SolicitacoesAlteracaoForm(request.GET or None, request=request, ano=ano)
    if form.is_valid():
        if form.cleaned_data.get('uo'):
            solicitacoes = solicitacoes.filter(projeto__uo=form.cleaned_data['uo'])

        if form.cleaned_data.get('ano'):
            solicitacoes = solicitacoes.filter(projeto__edital__inicio_inscricoes__year=form.cleaned_data['ano'])

        if form.cleaned_data.get('edital'):
            solicitacoes = solicitacoes.filter(projeto__edital=form.cleaned_data['edital'])

        if form.cleaned_data.get('situacao'):
            if form.cleaned_data.get('situacao') == '1':
                solicitacoes = solicitacoes.filter(atendida=True)
            elif form.cleaned_data.get('situacao') == '2':
                solicitacoes = solicitacoes.filter(atendida=False)
            else:
                solicitacoes = solicitacoes.filter(atendida=None)

        if form.cleaned_data.get('paginacao'):
            num_page = form.cleaned_data.get('paginacao')

        if form.cleaned_data.get('palavra_chave'):
            solicitacoes = solicitacoes.filter(
                Q(projeto__titulo__icontains=form.cleaned_data['palavra_chave'])
                | Q(projeto__edital__titulo__icontains=form.cleaned_data['palavra_chave'])
            )
    return locals()


def projetos_aprovaveis_sem_fomento(request: HttpRequest, edital: Edital) -> QuerySet[Projeto]:
    """Projetos do edital que a tela "Aprovar projetos sem fomento" oferece ao usuário (fora do campus, só com acesso sistêmico)."""
    projetos = (
        Projeto.objects.filter(pre_aprovado=True, aprovado=False, edital=edital, autorizada_sem_fomento_em=None)
        .exclude(data_avaliacao=None)
        .order_by('uo', '-pontuacao')
    )
    if not request.user.has_perm('pesquisa.tem_acesso_sistemico'):
        projetos = projetos.filter(uo=get_uo(request.user))
    return projetos


@rtr()
@permission_required('pesquisa.add_edital')
def aprovar_projetos_sem_fomento(request: HttpRequest, edital_id: int) -> dict:
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Aprovar projetos sem fomento: {edital}'
    projetos = projetos_aprovaveis_sem_fomento(request, edital)
    return locals()


@rtr()
@permission_required('pesquisa.add_edital')
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
            titulo = '[SUAP] Pesquisa: Autorização de execução de projeto sem fomento'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Autorização de execução de projeto sem fomento</h2>'
                f"<p>O projeto '{projeto.titulo}' poderá ser executado sem fomento. Acesse o SUAP para registrar se deseja executar o projeto.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
        return httprr(f'/pesquisa/aprovar_projetos_sem_fomento/{edital.id}/', 'Projetos autorizados com sucesso.')


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
@permission_required('pesquisa.pode_interagir_com_projeto')
def meus_projetos_autorizados_sem_fomento(request: HttpRequest) -> dict:
    title = 'Projetos autorizados a entrar em execução sem fomento'
    projetos = projetos_autorizados_sem_fomento(request.user.get_vinculo())
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
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
        if projeto.aceita_sem_fomento:
            for participacao in Participacao.objects.filter(projeto=projeto):
                participacao.vinculo = TipoVinculo.VOLUNTARIO
                participacao.bolsa_concedida = False
                participacao.save()
                HistoricoEquipe.objects.filter(participante=participacao, projeto=projeto).update(vinculo=TipoVinculo.VOLUNTARIO)

        titulo = '[SUAP] Pesquisa: Execução de projeto sem fomento'
        texto = (
            '<h1>Pesquisa</h1>'
            '<h2>Execução de projeto sem fomento</h2>'
            f"<p>O coordenador do projeto '{projeto.titulo}' {desc} executar o projeto sem fomento.</p>"
        )
        lista_integrantes = []
        for membro in UsuarioGrupo.objects.filter(group__name='Coordenador de Pesquisa'):
            if get_uo(membro.user) == projeto.uo:
                lista_integrantes.append(membro.user.get_vinculo())
        if lista_integrantes:
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, lista_integrantes)
        return httprr('/pesquisa/meus_projetos_autorizados_sem_fomento/', 'Manifestação registrada com sucesso.')

    else:
        raise PermissionDenied


def _uos_do_coordenador_de_pesquisa(request: HttpRequest) -> tuple | None:
    """Campi a que o Coordenador de Pesquisa (papel de campus) se restringe; ``None`` para quem não tem restrição, como o Diretor de Pesquisa."""
    if request.user.has_group_cached('Coordenador de Pesquisa') and not request.user.has_group_cached('Diretor de Pesquisa'):
        return get_uos(request)
    return None


def _campus_da_lista_espera(request: HttpRequest, edital: Edital, campus_id: int | None) -> UnidadeOrganizacional | None:
    """Campus da lista de espera de um edital por campus, recusando ao Coordenador de Pesquisa os campi que não são seus."""
    if edital.forma_selecao != Edital.CAMPUS or not campus_id:
        return None
    campus = get_object_or_404(UnidadeOrganizacional, id=campus_id)
    uos = _uos_do_coordenador_de_pesquisa(request)
    if uos is not None and campus not in uos:
        raise PermissionDenied
    return campus


def _projetos_lista_espera(edital: Edital, campus: UnidadeOrganizacional | None) -> tuple[QuerySet, QuerySet]:
    """Projetos pré-aprovados do edital (do campus, no edital por campus): os da lista de espera e os já aprovados."""
    pre_aprovados = Projeto.objects.filter(edital=edital, pre_aprovado=True)
    if edital.forma_selecao != Edital.GERAL:
        pre_aprovados = pre_aprovados.filter(uo=campus)
    projetos = pre_aprovados.filter(aprovado=False).order_by('-pontuacao_total', '-pontuacao')
    aprovados_previamente = pre_aprovados.filter(aprovado=True).exclude(
        projetocancelado__cancelado=True, projetocancelado__data_avaliacao__isnull=False
    )
    return projetos, aprovados_previamente


def _contar_bolsas(participacoes: Iterable[Participacao]) -> tuple[int, int, int, int]:
    """Bolsas solicitadas e concedidas entre os bolsistas: (pesquisador solicitada, pesquisador concedida, IC solicitada, IC concedida)."""
    pesquisador_solicitada = pesquisador_concedida = ic_solicitada = ic_concedida = 0
    for participacao in participacoes:
        if participacao.vinculo != TipoVinculo.BOLSISTA:
            continue
        concedida = int(participacao.bolsa_concedida is True)
        if participacao.is_servidor():
            pesquisador_solicitada += 1
            pesquisador_concedida += concedida
        else:
            ic_solicitada += 1
            ic_concedida += concedida
    return pesquisador_solicitada, pesquisador_concedida, ic_solicitada, ic_concedida


@rtr()
@permission_required('pesquisa.add_edital')
def projetos_lista_espera(request: HttpRequest, edital_id: int) -> dict:
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Projetos na lista de espera - {edital}'
    uos = _uos_do_coordenador_de_pesquisa(request)
    return locals()


@rtr()
@permission_required('pesquisa.add_edital')
def aprovar_projetos_com_bolsa(request: HttpRequest, edital_id: int, campus_id: int | None = None) -> dict | HttpResponse:
    title = 'Aprovar projetos da lista de espera'
    qtd_bolsa_pesquisador_distribuida = 0
    qtd_bolsa_ic_distribuida = 0
    qtd_bolsa_pesquisador_solicitada = 0
    qtd_bolsa_ic_solicitada = 0
    # Lista de espera vazia ou campus sem oferta de bolsa: saldo zero, sem 500 (#17572).
    qtd_bolsa_pesquisador = qtd_bolsa_ic = saldo_bolsa_pesquisador = saldo_bolsa_ic = 0
    participacoes = Participacao.objects.none()
    edital = get_object_or_404(Edital, id=edital_id)
    campus = _campus_da_lista_espera(request, edital, campus_id)
    projetos, aprovados_previamente = _projetos_lista_espera(edital, campus)
    if projetos:
        if edital.forma_selecao == Edital.CAMPUS and edital.bolsadisponivel_set.filter(uo=campus):
            qtd_bolsa_pesquisador = edital.bolsadisponivel_set.get(uo=campus).num_maximo_pesquisador
            qtd_bolsa_ic = edital.bolsadisponivel_set.get(uo=campus).num_maximo_ic
            participacoes = Participacao.objects.filter(projeto__in=aprovados_previamente.values_list('id', flat=True)).order_by('vinculo')
        elif edital.forma_selecao == Edital.GERAL:
            qtd_bolsa_pesquisador = edital.qtd_bolsa_servidores
            qtd_bolsa_ic = edital.qtd_bolsa_alunos
            participacoes = Participacao.objects.filter(projeto__in=aprovados_previamente.values_list('id', flat=True)).order_by('vinculo')
        qtd_bolsa_pesquisador_solicitada, qtd_bolsa_pesquisador_distribuida, qtd_bolsa_ic_solicitada, qtd_bolsa_ic_distribuida = _contar_bolsas(
            participacoes
        )
        saldo_bolsa_pesquisador = qtd_bolsa_pesquisador - qtd_bolsa_pesquisador_distribuida
        saldo_bolsa_ic = qtd_bolsa_ic - qtd_bolsa_ic_distribuida

    if request.POST:
        ids_participacao_de_servidor_bolsa_concedida = request.POST.getlist('participacoes_pesquisadores')
        ids_participacao_de_aluno_bolsa_concedidas = request.POST.getlist('participacoes_ic')
        ids_projetos_aprovados = request.POST.getlist('situacao')
        superou_cota_pesquisador = len(ids_participacao_de_servidor_bolsa_concedida) > saldo_bolsa_pesquisador
        superou_cota_ic = len(ids_participacao_de_aluno_bolsa_concedidas) > saldo_bolsa_ic
        url_retorno = f'/pesquisa/aprovar_projetos_com_bolsa/{edital_id}/'
        desc = 'edital'
        if campus_id:
            url_retorno = f'/pesquisa/aprovar_projetos_com_bolsa/{edital_id}/{campus_id}/'
            desc = 'campus'
        if superou_cota_pesquisador:
            return httprr(
                url_retorno,
                f'A quantidade de bolsas distribuídas para pesquisadores superou a cota destinada para o {desc}.',
                tag='error',
            )
        elif superou_cota_ic:
            return httprr(
                url_retorno,
                f'A quantidade de bolsas distribuídas de iniciação científica superou a cota destinada para o {desc}.',
                tag='error',
            )
        elif not ids_projetos_aprovados:
            return httprr(
                url_retorno,
                'Nenhum projeto foi selecionado para aprovação.',
                tag='error',
            )
        else:
            # Só as participações dos projetos em exibição; ids de fora são ignorados (#17556).
            Participacao.objects.filter(
                projeto__in=projetos, id__in=ids_participacao_de_servidor_bolsa_concedida + ids_participacao_de_aluno_bolsa_concedidas
            ).update(bolsa_concedida=True)
            for projeto_id in ids_projetos_aprovados:
                projeto = projetos.get(id=projeto_id)
                projeto.aprovado = True
                projeto.aprovado_posteriormente = True
                projeto.aprovado_posteriormente_em = datetime.datetime.now()
                projeto.aprovado_posteriormente_por = request.user.get_vinculo()
                projeto.save()
                projeto.atualizar_cotas_bolsa()
                titulo = '[SUAP] Pesquisa: Autorização para execução de projeto'
                texto = (
                    '<h1>Pesquisa</h1>'
                    '<h2>Autorização para execução de projeto</h2>'
                    f"<p>A execução do projeto '{projeto.titulo}' foi autorizada. Acesse o SUAP para mais detalhes.</p>"
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
            return httprr(url_retorno, 'Bolsas salvas com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
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
@permission_required('pesquisa.tem_acesso_sistemico')
def classificacao_projetos_edital(self, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    tabela = {}
    resultado = {}
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
    if edital.tem_formato_completo():
        if edital.forma_selecao == Edital.GERAL:
            projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('-pontuacao_total', '-pontuacao')
            tabela['Geral'] = []
            for projeto in projetos:
                tabela['Geral'].append(projeto)
        else:
            projetos = Projeto.objects.filter(edital=edital, pre_aprovado=True).order_by('uo__sigla', '-pontuacao_total', '-pontuacao')
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
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def reenviar_convite_avaliador(request: HttpRequest, avaliador_id: int) -> HttpResponse:
    url = request.META.get('HTTP_REFERER', '.')
    novo_avaliador = get_object_or_404(AvaliadorIndicado, pk=avaliador_id)
    projeto = novo_avaliador.projeto
    if request.user.has_group_cached('Coordenador de Pesquisa') and projeto.uo != get_uo(request.user):
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
    titulo = '[SUAP] Avaliação de Projeto de Pesquisa'
    if projeto.edital.prazo_aceite_indicacao:
        texto = (
            '<h1>Avaliação de Projeto de Pesquisa</h1>'
            f'<h2>{projeto.titulo}</h2>'
            f'<p>Foi solicitada sua avaliação do projeto de pesquisa: {projeto.titulo}.</p>'
            f'<p>Prazo para registrar que aceita a indicação: {format_(novo_avaliador.prazo_para_aceite)}.</p>'
            f'<p>Prazo para realizar a avaliação: {format_(novo_avaliador.prazo_para_avaliacao)}.</p>'
            '<p>Caso os prazos não sejam cumpridos, a indicação será cancelada automaticamente.</p>'
            f'<p>O registro de aceite e a avaliação poderão ser realizados através do seguinte endereço: <a href="{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/">{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/</a></p>'
            f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital: {format_(projeto.edital.inicio_selecao)} - {format_(fim_selecao)}.</p>'
        )

    else:
        texto = (
            '<h1>Avaliação de Projeto de Pesquisa</h1>'
            f'<h2>{projeto.titulo}</h2>'
            f'<p>Foi solicitada sua avaliação do projeto de pesquisa: {projeto.titulo}.</p>'
            f'<p>A avaliação poderá ser realizada através do seguinte endereço: <a href="{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/">{settings.SITE_URL}/pesquisa/projetos_especial_pre_aprovados/{projeto.edital.id}/</a></p>'
            f'<p>Seu acesso ao projeto estará disponível no SUAP durante o período de avaliação do edital: {format_(projeto.edital.inicio_selecao)} - {format_(fim_selecao)}.</p>'
        )
    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [novo_avaliador.vinculo])
    return httprr(url, 'Convite reenviado com sucesso.')


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def remover_indicacoes_rejeitadas(request: HttpRequest, edital_id: int) -> HttpResponse:
    url = request.META.get('HTTP_REFERER', '.')
    avaliacoes = AvaliadorIndicado.objects.filter(rejeitado=True, projeto__edital_id=edital_id)
    if request.user.has_group_cached('Coordenador de Pesquisa'):  # a tela de seleção só lista os projetos do campus dele
        avaliacoes = avaliacoes.filter(projeto__uo=get_uo(request.user))
    for avaliador in avaliacoes:
        vinculo = avaliador.vinculo
        avaliador.delete()
        if not AvaliadorIndicado.objects.filter(vinculo=vinculo).exists():
            grupo = Group.objects.get(name='Avaliador Sistêmico de Projetos de Pesquisa')
            avaliador.vinculo.user.groups.remove(grupo)
    return httprr(url, 'Indicações removidas com sucesso.')


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def atividades_dos_avaliadores(request):
    title = 'Atividades dos Avaliadores'
    ano = request.GET.get('ano')
    form = AtividadesAvaliadoresForm(request.GET or None, ano=ano)
    if form.is_valid():
        indicacoes = AvaliadorIndicado.objects.all().order_by('vinculo__pessoa__nome')
        if form.cleaned_data.get('ano'):
            indicacoes = indicacoes.filter(projeto__edital__inicio_inscricoes__year=form.cleaned_data.get('ano'))
        if form.cleaned_data.get('edital'):
            indicacoes = indicacoes.filter(projeto__edital=form.cleaned_data.get('edital'))
        if form.cleaned_data.get('nome'):
            indicacoes = indicacoes.filter(vinculo__pessoa__nome__icontains=form.cleaned_data.get('nome'))

        dados = []
        indicacoes = indicacoes.annotate(
            avaliacao=Subquery(Avaliacao.objects.filter(vinculo=OuterRef('vinculo'), projeto=OuterRef('projeto')).values('id')[:1])
        )
        dados.append(
            ['Indicações aceitas e não avaliadas', indicacoes.filter(rejeitado_em=None).exclude(aceito_em=None).filter(avaliacao=None).count()]
        )
        dados.append(
            ['Indicações aceitas e realizadas', indicacoes.filter(rejeitado_em=None).exclude(aceito_em=None).exclude(avaliacao=None).count()]
        )
        dados.append(['Realizadas sem aceite', indicacoes.filter(aceito_em=None, rejeitado_em=None).exclude(avaliacao=None).count()])
        dados.append(['Indicações rejeitadas', indicacoes.filter(rejeitado=True, rejeitado_automaticamente=False).count()])
        dados.append(['Indicações rejeitadas automaticamente', indicacoes.filter(rejeitado_automaticamente=True).count()])
        grafico = PieChart(
            'grafico',
            title='Situações das Indicações dos Avaliadores',
            subtitle='Quantidade de indicações aceitas, avaliadas e rejeitadas',
            minPointLength=0,
            data=dados,
        )

        grafico.id = 'grafico'
        pie_chart_lists = [
            grafico,
        ]
    return locals()


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
def notificar_servidores_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if edital.pode_notificar_servidores():
        return tasks.notificar_servidores_edital(edital)
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_origemrecursoedital, pesquisa.pode_ver_config_edital, projetos.pode_gerenciar_edital')
def relatorio_quantitativo_taes_por_campus(request):
    title = 'Quantitativo de TAEs por Campus'
    form = CampusForm(request.POST or None)
    tabela = {}
    uos = UnidadeOrganizacional.objects.uo().all().order_by('sigla')
    total = 0
    if form.is_valid():
        servidor = Servidor.objects.filter(data_exclusao_instituidor__isnull=True, ativo=True, eh_tecnico_administrativo=True)
        if form.cleaned_data.get('uo'):
            uos = uos.filter(id=form.cleaned_data.get('uo').id)
        for uo in uos:
            chave = f'{uo.nome}'
            quantidade = servidor.filter(setor_lotacao__uo__equivalente=uo).count()
            tabela[chave] = quantidade
            total = total + quantidade

        resultado = collections.OrderedDict(sorted(tabela.items()))

    return locals()


@rtr()
@permission_required('pesquisa.pode_visualizar_projetos_em_monitoramento')
def cancelar_avaliacao_etapa(request, registroexecucao_id):
    registro = get_object_or_404(RegistroExecucaoEtapa, pk=registroexecucao_id)
    is_gerente_sistemico = request.user.has_perm('pesquisa.tem_acesso_sistemico')
    projeto = registro.etapa.meta.projeto
    pode_validar = (projeto.vinculo_supervisor == request.user.get_vinculo()) or is_gerente_sistemico
    if pode_validar and not projeto.eh_somente_leitura():
        registro.justificativa_reprovacao = ''
        registro.dt_avaliacao = None
        registro.avaliador = None
        registro.aprovado = False
        registro.save()
        return httprr(f'/pesquisa/validar_execucao_etapa/{projeto.pk}/?tab=metas', 'Avaliação da atividade cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_visualizar_projetos_em_monitoramento')
def cancelar_avaliacao_gasto(request, registrogasto_id):
    registro = get_object_or_404(RegistroGasto, pk=registrogasto_id)
    is_gerente_sistemico = request.user.has_perm('pesquisa.tem_acesso_sistemico')
    projeto = registro.desembolso.projeto
    pode_validar = (projeto.vinculo_supervisor == request.user.get_vinculo()) or is_gerente_sistemico
    if pode_validar and not projeto.eh_somente_leitura():
        registro.justificativa_reprovacao = None
        registro.dt_avaliacao = None
        registro.avaliador = None
        registro.aprovado = False
        registro.save()
        return httprr(f'/pesquisa/validar_execucao_etapa/{projeto.pk}/?tab=gastos', 'Avaliação do gasto cancelada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def adicionar_certificado_registro_pi(request, pi_id):
    pi = get_object_or_404(RegistroPropriedadeIntelectual, pk=pi_id)
    title = f'Adicionar Certificado de Registro - {pi}'
    form = CertificadoRegistroPIForm(request.POST or None, request.FILES or None, instance=pi)
    if form.is_valid():
        form.save()
        return httprr(f'/pesquisa/pi_visualizar/{pi.id}', 'Certificado de registro cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def aceitar_doacao_editora(request, doacao_id):
    doacao = get_object_or_404(DoacaoEditora, pk=doacao_id)
    if not doacao.aceite_em and doacao.servidor and doacao.servidor == request.user.get_relacionamento():
        title = 'Registar aceite de doação da Editora'
        form = AceitarDoacaoForm(request.POST or None)
        if form.is_valid():
            doacao.aceite_em = datetime.datetime.now()
            doacao.save()
            return httprr('/', 'Aceite de doação registrado com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
def estatistica_projetos_por_campus(request):
    projetos = Projeto.objects.all()
    title = 'Estatística dos Projetos de Pesquisa por Campus'
    form = EstatisticasporCampusForm(request.GET or None, request=request)
    if form.is_valid():
        edital = form.cleaned_data.get('edital')
        formato_edital = form.cleaned_data.get('formato_edital')
        campus = form.cleaned_data.get('campus')
        anos = form.cleaned_data.get('ano')
        grupo_pesquisa = form.cleaned_data.get('grupo_pesquisa')
        situacao = form.cleaned_data.get('situacao')

        if anos:
            projetos = projetos.filter(edital__inicio_inscricoes__year__in=anos.values_list('ano', flat=True))
        if edital:
            projetos = projetos.filter(edital=edital)
        if campus:
            projetos = projetos.filter(uo__in=campus)
        if grupo_pesquisa:
            projetos = projetos.filter(grupo_pesquisa=grupo_pesquisa)

        if formato_edital:
            projetos = projetos.filter(edital__formato=formato_edital)
        cabecalho = []
        for ano in anos:
            cabecalho.append(ano.ano)

        hoje = datetime.datetime.now()
        enviados = projetos.filter(
            Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
        )
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)
        aprovados = enviados.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje) | enviados.filter(
            aprovado=True, edital__formato=Edital.FORMATO_SIMPLIFICADO
        )
        execucao = aprovados.filter(
            pre_aprovado=True,
            aprovado=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            edital__divulgacao_selecao__lt=hoje,
            inativado=False,
        ).exclude(id__in=projetos_cancelados)
        concluidos = aprovados.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False)
        cancelados = aprovados.filter(id__in=projetos_cancelados)
        inativados = aprovados.filter(inativado=True)
        queryset = projetos
        if situacao != 'Todos':
            titulo = situacao
            if situacao == EstatisticasForm.PROJETOS_ENVIADOS:
                queryset = enviados
            elif situacao == EstatisticasForm.PROJETOS_PRE_SELECIONADOS:
                queryset = enviados.filter(pre_aprovado=True)
            elif situacao == EstatisticasForm.PROJETOS_APROVADOS:
                queryset = aprovados
            elif situacao == EstatisticasForm.PROJETOS_EM_EXECUCAO:
                queryset = execucao
            elif situacao == EstatisticasForm.PROJETOS_CONCLUIDOS:
                queryset = concluidos
            elif situacao == EstatisticasForm.PROJETOS_CANCELADOS:
                queryset = cancelados
            elif situacao == EstatisticasForm.PROJETOS_INATIVADOS:
                queryset = inativados

        campi = UnidadeOrganizacional.objects.filter(id__in=queryset.values_list('uo', flat=True)).order_by('sigla')
        dict_retorno = {}
        total = {}
        for campus in campi:
            dict_retorno[f'{campus.sigla}'] = []
            soma = 0
            for ano in anos:
                contador = queryset.filter(uo=campus, edital__inicio_inscricoes__year=ano.ano).count()
                dict_retorno[f'{campus.sigla}'].append(contador)
                if f'{ano.ano}' in total:
                    total[f'{ano.ano}'] += contador
                else:
                    total[f'{ano.ano}'] = contador
        if 'xls' in request.GET:
            return tasks.estatisticas_por_campus_to_xls(cabecalho, dict_retorno, total)
    return locals()


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
def relatorio_dados_cartao_pesquisador(request):
    title = 'Dados para Solicitação do Cartão Pesquisador'
    form = CartaoPesquisadorForm(request.POST or None)
    if form.is_valid():
        projetos = (
            Projeto.objects.filter(aprovado=True, pre_aprovado=True, inativado=False)
            .exclude(data_avaliacao=None)
            .exclude(id__in=ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True))
        )
        if form.cleaned_data.get('edital'):
            projetos = projetos.filter(edital=form.cleaned_data.get('edital'))
        filtro_interesse = form.cleaned_data.get('com_interesse')
        if form.cleaned_data.get('uo'):
            projetos = projetos.filter(uo=form.cleaned_data.get('uo'))
        if filtro_interesse:
            if filtro_interesse == 'Sim':
                projetos = projetos.filter(tem_interesse_cartao_pesquisador=True)
            else:
                projetos = projetos.filter(tem_interesse_cartao_pesquisador=False)

        return tasks.relatorio_dados_cartao_pesquisador_to_xls(projetos)
    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_assessor(request, assessor_id):
    if Incubadora.tem_permissao_gerenciar_incubadora(request.user.get_vinculo()):
        assessor = get_object_or_404(IntegranteEquipeTecnica, pk=assessor_id)
        servidor = assessor.vinculo.relacionamento
        title = 'Visualizar Assessor'
        pode_excluir = request.user.has_perm('pesquisa.tem_acesso_sistemico')
        historico = AssessorIncubadora.objects.filter(vinculo=assessor.vinculo).order_by('-id')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.tem_acesso_sistemico')
def excluir_integrante_equipe_tecnica(request, assessor_id):
    assessor = get_object_or_404(IntegranteEquipeTecnica, pk=assessor_id)
    assessor.delete()
    return httprr('/admin/pesquisa/integranteequipetecnica/', 'Assessor excluído com sucesso.')


@rtr()
@permission_required('rh.eh_servidor')
def recrutar_assessor(request, assessor_id):
    if Incubadora.tem_permissao_gerenciar_incubadora(request.user.get_vinculo()):
        assessor = get_object_or_404(IntegranteEquipeTecnica, pk=assessor_id)
        title = f'Recrutar Assessor - {assessor.vinculo.__str__()}'
        novo_recrutamento = RecrutamentoAssessor()
        novo_recrutamento.vinculo = assessor.vinculo
        novo_recrutamento.recrutado_por = request.user.get_vinculo()
        form = RecrutarAssessorForm(data=request.POST or None, request=request, instance=novo_recrutamento)
        if form.is_valid():
            form.save()
            titulo = f'[SUAP] Incubadora Tecnológica: Convite para ser um Assessor Técnico da {form.cleaned_data.get("incubadora").sigla}'
            texto = (
                '<h1>Incubadora Tecnológica</h1>'
                '<h2>Convite para ser um Assessor Técnico</h2>'
                f'<p>Você recebeu um convite para participar como Assessor(a) Técnico(a) da {form.cleaned_data.get("incubadora").sigla}. Acesse o SUAP para mais detalhes.</p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [novo_recrutamento.vinculo])
            return httprr('/admin/pesquisa/integranteequipetecnica/', 'Assessor recrutado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('comum.view_manutencaoprogramada')
def avaliar_recrutamento(request, recrutamento_id):
    recrutamento = get_object_or_404(RecrutamentoAssessor, pk=recrutamento_id)
    if not recrutamento.avaliado_em and recrutamento.vinculo == request.user.get_vinculo():
        title = 'Avaliar Convite para atuar como Assessor(a) Técnico(a)'
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('comum.view_manutencaoprogramada')
@transaction.atomic
def avaliar_convite_recrutamento(request, recrutamento_id, opcao):
    recrutamento = get_object_or_404(RecrutamentoAssessor, pk=recrutamento_id)
    if not recrutamento.avaliado_em and recrutamento.vinculo == request.user.get_vinculo():
        if opcao == 1:
            recrutamento.aceito = True
            recrutamento.avaliado_em = datetime.datetime.now()
            recrutamento.save()
            AssessorIncubadora.objects.get_or_create(
                vinculo=recrutamento.vinculo, incubadora=recrutamento.incubadora, recrutamento=recrutamento, data_inicio=datetime.date.today()
            )
            return httprr(f'/pesquisa/incubadora/{recrutamento.incubadora.id}/?tab=assessores', 'Convite avaliado com sucesso.')
        elif opcao == 2:
            recrutamento.aceito = False
            recrutamento.avaliado_em = datetime.datetime.now()
            recrutamento.save()
            return httprr(f'/pesquisa/incubadora/{recrutamento.incubadora.id}/?tab=assessores', 'Convite avaliado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('comum.view_manutencaoprogramada')
def finalizar_vinculo_assessor(request, assessorincubadora_id):
    assessor = get_object_or_404(AssessorIncubadora, pk=assessorincubadora_id)
    if not assessor.data_termino and assessor.incubadora.pode_gerenciar_incubadora(request.user):
        title = 'Finalizar participação do assessor'
        form = FinalizarAssessorForm(request.POST or None, instance=assessor)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/incubadora/{assessor.incubadora.id}/?tab=assessores', 'Participação finalizada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@documento('Certificado de Assessor Técnico', forcar_recriacao=True, enumerar_paginas=False, modelo='pesquisa.assessorincubadora')
@rtr()
@permission_required('comum.view_manutencaoprogramada')
def emitir_certificado_assessor(request, pk):
    registro = get_object_or_404(AssessorIncubadora, pk=pk)
    if registro.data_termino:
        vinculo = registro.vinculo
        nome = vinculo.pessoa.nome
        hoje = datetime.datetime.now()
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes = meses[hoje.month - 1]

        cidade = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
        cpf = vinculo.relacionamento.pessoa_fisica.cpf and anonimizar_cpf(vinculo.relacionamento.pessoa_fisica.cpf)

        return locals()
    else:
        raise PermissionDenied


@documento('Declaração de Assessor Técnico', forcar_recriacao=True, enumerar_paginas=False, modelo='pesquisa.assessorincubadora')
@rtr()
@permission_required('comum.view_manutencaoprogramada')
def emitir_declaracao_assessor(request, pk):
    registro = get_object_or_404(AssessorIncubadora, pk=pk)
    if not registro.data_termino:
        vinculo = registro.vinculo
        nome = vinculo.pessoa.nome
        hoje = datetime.datetime.now()
        nome_instituicao = (
            Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
        )
        nome_pro_reitoria = Configuracao.get_valor_por_chave('pesquisa', 'nome_propi') or 'Pró-Reitoria de Pesquisa e Inovação'
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes = meses[hoje.month - 1]

        cidade = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
        cpf = vinculo.relacionamento.pessoa_fisica.cpf and anonimizar_cpf(vinculo.relacionamento.pessoa_fisica.cpf)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def informar_responsavel_anuidade(request, anuidade_id):
    anuidade = get_object_or_404(AnuidadeRegistroPropriedadeIntelectual, pk=anuidade_id)
    if anuidade.estah_pendente():
        title = f'Informar responsável pelo pagamento - {anuidade}'
        form = InformarResponsavelAnuidadeForm(request.POST or None, instance=anuidade)
        if form.is_valid():
            o = form.save(False)
            o.pagamento_informado_por = request.user.get_vinculo()
            o.pagamento_informado_em = datetime.datetime.now()
            o.situacao = AnuidadeRegistroPropriedadeIntelectual.TERCEIROS
            o.save()
            return httprr(f'/pesquisa/pi_visualizar/{anuidade.propriedadeintelectual.id}/?tab=anuidades', 'Responsável registrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.change_registropropriedadeintelectual')
def pi_dashboard(request):
    title = 'Dashboard - Propriedades Intelectuais'
    queryset = AnuidadeRegistroPropriedadeIntelectual.objects.all()
    form = DashboardPIForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('tipo_pi'):
            queryset = queryset.filter(propriedadeintelectual__tipo=form.cleaned_data.get('tipo_pi'))
    hoje = datetime.date.today()
    pendentes = queryset.filter(
        propriedadeintelectual__ativo=True, situacao=AnuidadeRegistroPropriedadeIntelectual.PENDENTE, inicio_ordinario__lte=hoje
    ).values_list('propriedadeintelectual', flat=True)
    pi_pendentes = RegistroPropriedadeIntelectual.objects.filter(id__in=pendentes)
    dados = []
    dados.append(['Em dia', RegistroPropriedadeIntelectual.objects.exclude(id__in=pendentes).count()])
    dados.append(['Com anuidade pendente', pi_pendentes.count()])
    grafico = PieChart(
        'grafico',
        title='Situação das anuidades das Propriedades Intelectuais',
        subtitle='Quantidade de Propriedades Intelectuais com anuidades pendentes ou em dia',
        minPointLength=0,
        data=dados,
    )

    grafico.id = 'grafico'
    pie_chart_lists = [
        grafico,
    ]
    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def cadastrar_parceria(request):
    title = 'Cadastrar Parceria'
    form = ParceriaForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('processo'):
            o.id_processo = form.cleaned_data.get('processo').id
        o.save()
        return httprr(f'/pesquisa/parceria/{o.id}/', 'Parceria cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_parceria')
def editar_parceria(request, parceria_id):
    title = 'Editar Parceria'
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    form = ParceriaForm(request.POST or None, instance=parceria)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('processo'):
            o.id_processo = form.cleaned_data.get('processo').id
        o.save()
        return httprr(f'/pesquisa/parceria/{o.id}/', 'Parceria editada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.view_parceria')
def parceria(request, parceria_id):
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    parceiros = parceria.parceiro_set.all()
    title = 'Visualizar Parceria'
    equipe = parceria.membroparceria_set.all().order_by('nome')
    propriedades = parceria.piparceria_set.all()
    documentos = parceria.arquivoparceria_set.all()
    situacoes = parceria.etapaparceria_set.all()
    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def adicionar_parceiro(request, parceria_id):
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    title = f'Adicionar Parceiro - {parceria.titulo}'
    form = ParceiroForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.parceria = parceria
        o.save()
        return httprr('..', 'Parceiro adicionado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def editar_parceiro(request, parceiro_id):
    parceiro = get_object_or_404(Parceiro, pk=parceiro_id)
    title = f'Editar Parceiro - {parceiro.nome}'
    form = ParceiroForm(request.POST or None, instance=parceiro)
    if form.is_valid():
        form.save()
        return httprr('..', 'Parceiro editado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def adicionar_membro_parceria(request, parceria_id):
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    title = f'Adicionar Membro da Parceria - {parceria.titulo}'
    form = MembroParceriaForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.parceria = parceria
        if form.cleaned_data.get('vinculo'):
            o.nome = str(o.vinculo)
            o.instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        o.save()
        return httprr('..', 'Membro adicionado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def editar_membro(request, membro_id):
    parceiro = get_object_or_404(MembroParceria, pk=membro_id)
    title = f'Editar Membro - {parceiro.nome}'
    form = MembroParceriaForm(request.POST or None, instance=parceiro)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('vinculo'):
            o.nome = str(o.vinculo)
            o.instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        o.save()
        return httprr('..', 'Membro editado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def excluir_membro(request, membro_id):
    parceiro = get_object_or_404(MembroParceria, pk=membro_id)
    parceria_id = parceiro.parceria_id
    parceiro.delete()
    return httprr(f'/pesquisa/parceria/{parceria_id}/?tab=equipe', 'Membro excluído com sucesso.')


@rtr()
@permission_required('pesquisa.add_parceria')
def adicionar_pi_parceria(request, parceria_id):
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    title = f'Adicionar Propriedade Intelectual da Parceria - {parceria.titulo}'
    total = parceria.parceiro_set.all().count()
    form = PiParceriaForm(request.POST or None, parceria=parceria, total=total)
    if form.is_valid():
        o = form.save(False)
        o.parceria = parceria
        o.save()
        if form.cleaned_data.get('titularidade').id == 2:
            novo = ParceiroPiParceria()
            novo.pi = o
            novo.parceiro = form.cleaned_data.get('0_parceiro')
            novo.percentual_lucro = 100
            novo.save()
        else:
            contador = 0
            while contador < total:
                novo = ParceiroPiParceria()
                novo.pi = o
                novo.parceiro = form.cleaned_data.get(f'{contador}_parceiro')
                novo.percentual_lucro = form.cleaned_data.get(f'{contador}')
                novo.save()
                contador += 1
        return httprr('..', 'Propriedade intelectual adicionada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def editar_pi_parceira(request, pi_id):
    pi = get_object_or_404(PiParceria, pk=pi_id)
    title = f'Editar Propriedade Intelectual - {pi.titulo}'
    total = pi.parceria.parceiro_set.all().count()
    form = PiParceriaForm(request.POST or None, instance=pi, parceria=pi.parceria, total=total)
    if form.is_valid():
        form.save()
        if form.cleaned_data.get('titularidade').id == 2:
            ParceiroPiParceria.objects.filter(pi=pi).delete()
            novo = ParceiroPiParceria()
            novo.pi = form.instance
            novo.parceiro = form.cleaned_data.get('0_parceiro')
            novo.percentual_lucro = 100
            novo.save()
        else:
            contador = 0
            ParceiroPiParceria.objects.filter(pi=pi).delete()
            while contador < total:
                novo = ParceiroPiParceria()
                novo.pi = form.instance
                novo.parceiro = form.cleaned_data.get(f'{contador}_parceiro')
                novo.percentual_lucro = form.cleaned_data.get(f'{contador}')
                novo.save()
                contador += 1

        return httprr('..', 'Membro editado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def adicionar_documento_parceria(request, parceria_id, tipo):
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    instance = None
    if tipo == 1:
        tipo_arquivo = ArquivoParceria.TipoArquivo.ATA
    elif tipo == 2:
        tipo_arquivo = ArquivoParceria.TipoArquivo.INSTRUMENTO_JURIDICO
    elif tipo == 3:
        tipo_arquivo = ArquivoParceria.TipoArquivo.PLANO_TRABALHO
    else:
        tipo_arquivo = ArquivoParceria.TipoArquivo.OUTRO

    if tipo_arquivo != ArquivoParceria.TipoArquivo.OUTRO:
        instance = parceria.arquivoparceria_set.filter(tipo=tipo_arquivo).first()
    title = f'Adicionar/Editar Documento da Parceria - {parceria.titulo} ({tipo_arquivo})'
    form = ArquivoParceriaForm(request.POST or None, request.FILES or None, instance=instance)
    if form.is_valid():
        o = form.save(False)
        o.parceria = parceria
        if form.cleaned_data.get('documento'):
            o.id_documento = form.cleaned_data.get('documento').id
        o.tipo = tipo_arquivo
        o.save()
        return httprr('..', 'Documento adicionado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def excluir_arquivo_parceria(request, arquivo_id):
    arquivo = get_object_or_404(ArquivoParceria, pk=arquivo_id)
    parceria_id = arquivo.parceria_id
    arquivo.delete()
    return httprr(f'/pesquisa/parceria/{parceria_id}/?tab=documentos', 'Arquivo excluído com sucesso.')


@rtr()
@permission_required('pesquisa.add_parceria')
def adicionar_etapa_parceria(request, parceria_id):
    parceria = get_object_or_404(Parceria, pk=parceria_id)
    title = f'Adicionar Etapa - {parceria.titulo}'
    form = EtapaParceriaForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.parceria = parceria
        o.save()
        return httprr('..', 'Etapa adicionada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def editar_etapa_parceira(request, etapa_id):
    etapa = get_object_or_404(EtapaParceria, pk=etapa_id)
    title = f'Editar Etapa - {etapa.situacao}'
    form = EtapaParceriaForm(request.POST or None, instance=etapa)
    if form.is_valid():
        form.save()
        return httprr('..', 'Etapa editada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.add_parceria')
def parcerias_dashboard(request):
    title = 'Dashboard das Parcerias'
    parcerias = Parceria.objects.all()
    form = DashboardParceriaForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            parcerias = parcerias.filter(data_inicio__year=form.cleaned_data.get('ano'))
        if form.cleaned_data.get('situacao'):
            parcerias = parcerias.filter(situacao=form.cleaned_data.get('situacao'))
        if form.cleaned_data.get('tipo'):
            parcerias = parcerias.filter(tipo=form.cleaned_data.get('tipo'))

    dados = []
    for tipo in TipoParceria.objects.all():
        dados.append([tipo.descricao, parcerias.filter(tipo=tipo).count()])

    grafico = PieChart(
        'grafico',
        title='Quantidade de Parcerias por Tipo',
        subtitle='Quantidade de parcerias por tipo',
        minPointLength=0,
        data=dados,
    )

    grafico.id = 'grafico'

    dados2 = []
    fin = Parceiro.objects.filter(parceria__in=parcerias.values_list('id', flat=True)).aggregate(total=Sum('recurso_financeiro'))['total'] or 0
    eco = Parceiro.objects.filter(parceria__in=parcerias.values_list('id', flat=True)).aggregate(total=Sum('recurso_economico'))['total'] or 0
    dados2.append(['Recursos Financeiros', float(fin)])
    dados2.append(['Recursos Econômicos', float(eco)])

    grafico2 = ColumnChart(
        'grafico2',
        title='Total de recursos financeiros e econômicos (R$)',
        subtitle='Total de recursos financeiros e econômicos, em reais',
        minPointLength=0,
        data=dados2,
    )

    grafico2.id = 'grafico2'

    pie_chart_lists = [grafico, grafico2]
    tipos = TipoTransferenciaTecnologica.objects.all().order_by('descricao')
    ano_atual = datetime.datetime.now().year
    primeiro_ano = PiParceria.objects.order_by('parceria__data_inicio').first()
    registros = []
    total = {}
    if primeiro_ano:
        ano = ano_atual
        while ano >= primeiro_ano.parceria.data_inicio.year:
            numeros = []
            numeros.append(ano)
            for tipo in tipos:
                quantidade = PiParceria.objects.filter(tipo_transferencia=tipo, parceria__data_inicio__year=ano).count()
                numeros.append(quantidade)
                if f'{tipo.descricao}' in total:
                    total[f'{tipo.descricao}'] += quantidade
                else:
                    total[f'{tipo.descricao}'] = quantidade
            ano -= 1
            registros.append(numeros)
    return locals()


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def adicionar_registro_diario_bordo(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.pode_adicionar_registro_diario_bordo():
        title = 'Adicionar Registro no Diário de Bordo'
        form = RegistroDiarioBordoForm(request.POST or None)
        if form.is_valid():
            o = form.save(False)
            o.cadastrado_por = request.user.get_vinculo()
            o.projeto = projeto
            o.save()
            return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=diario_bordo', 'Registro cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def editar_registro_diario_bordo(request, registro_id):
    registro = get_object_or_404(RegistroDiarioBordo, pk=registro_id)
    projeto = registro.projeto
    if registro.posso_alterar(request.user.get_vinculo()):
        title = 'Editar Registro do Diário de Bordo'
        form = RegistroDiarioBordoForm(request.POST or None, instance=registro)
        if form.is_valid():
            form.save()
            return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=diario_bordo', 'Registro editado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def finalizar_registro_diario_bordo(request, registro_id):
    registro = get_object_or_404(RegistroDiarioBordo, pk=registro_id)
    projeto = registro.projeto
    if registro.posso_alterar(request.user.get_vinculo()):
        registro.situacao = RegistroDiarioBordo.SituacaoChoices.FINALIZADO
        registro.save()
        return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=diario_bordo', 'Registro finalizado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def excluir_registro_diario_bordo(request, registro_id):
    registro = get_object_or_404(RegistroDiarioBordo, pk=registro_id)
    projeto = registro.projeto
    if registro.posso_alterar(request.user.get_vinculo()):
        registro.delete()
        return httprr(f'/pesquisa/projeto/{projeto.id}/?tab=diario_bordo', 'Registro excluído com sucesso.')
    else:
        raise PermissionDenied


@documento('Registro de Diário de Bordo', forcar_recriacao=True, enumerar_paginas=True, modelo='pesquisa.registrodiariobordo')
@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def visualizar_registro_diario_bordo(request, pk):
    registro = get_object_or_404(RegistroDiarioBordo, pk=pk)
    return locals()


@documento('Diário de Bordo', forcar_recriacao=True, enumerar_paginas=True, modelo='pesquisa.projeto')
@rtr()
@permission_required('pesquisa.pode_interagir_com_projeto')
def imprimir_diario_bordo(request, pk):
    registros = RegistroDiarioBordo.objects.filter(projeto_id=pk, situacao=RegistroDiarioBordo.SituacaoChoices.FINALIZADO).order_by('id')
    return locals()


@rtr()
@permission_required('pesquisa.pode_pre_avaliar_projeto')
def desfazer_finalizacao_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if projeto.pode_reverter_finalizacao_projeto():
        title = f'Reverter Finalização do Projeto - {projeto.titulo}'
        form = DesfazerFinalizacaoForm(request.POST or None)
        if form.is_valid():
            movimentacoes_sem_data_saida = HistoricoEquipe.objects.filter(
                projeto=projeto, data_movimentacao_saida=projeto.data_finalizacao_conclusao.date()
            )
            if movimentacoes_sem_data_saida:
                for movimentacao in movimentacoes_sem_data_saida:
                    movimentacao.data_movimentacao_saida = None
                    movimentacao.save()
            projeto.data_finalizacao_conclusao = None
            projeto.save()
            historico = ProjetoHistoricoDeEnvio()
            historico.projeto = projeto
            historico.parecer_devolucao = form.cleaned_data.get('justificativa')
            historico.data_operacao = datetime.datetime.now()
            historico.situacao = ProjetoHistoricoDeEnvio.DEVOLVIDO
            if request.user.get_vinculo().eh_servidor():
                historico.operador = request.user.get_relacionamento()
            historico.vinculo_operador = request.user.get_vinculo()
            historico.save()
            titulo = '[SUAP] Pesquisa: Finalização do projeto revertida'
            texto = (
                '<h1>Pesquisa</h1>'
                '<h2>Finalização do projeto revertida</h2>'
                f"<p>O projeto '{projeto.titulo}' teve seu registro de finalização revertida. Justificativa: {form.cleaned_data.get('justificativa')}. Acesse o SUAP para mais detalhes.</p>"
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [projeto.vinculo_coordenador])
            return httprr(f'/pesquisa/projeto/{projeto.id}/', 'Finalização desfeita com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('pesquisa.add_edital')
def clonar_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Clonar Edital: {edital}'
    form = ClonarEditalForm(request.POST or None, request=request, edital=edital)
    if form.is_valid():
        edital_clonado = form.processar()
        return httprr(f'/pesquisa/edital/{edital_clonado.id}/', 'Edital clonado com sucesso.')
    return locals()


@rtr()
@permission_required('pesquisa.add_transferenciatecnologica')
def cadastrar_transferencia(request):
    title = 'Cadastrar Licenciamento/ transferência de tecnologia'
    form = TransferenciaTecnologicaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('processo'):
            o.id_processo = form.cleaned_data.get('processo').id
        o.save()
        return httprr(f'/pesquisa/transferencia_visualizar/{o.id}/', 'Transferência cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def editar_transferencia(request, transferencia_id):
    title = 'Editar Licenciamento/ transferência de tecnologia'
    transf = get_object_or_404(TransferenciaTecnologica, pk=transferencia_id)
    form = TransferenciaTecnologicaForm(request.POST or None, request.FILES or None, instance=transf)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('processo'):
            o.id_processo = form.cleaned_data.get('processo').id
        o.save()
        return httprr(f'/pesquisa/transferencia_visualizar/{o.id}/', 'Transferência editada com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def cadastrar_recurso_transferencia(request, transferencia_id):
    title = 'Cadastrar recurso recebido'
    transf = get_object_or_404(TransferenciaTecnologica, pk=transferencia_id)
    form = RecursoTransferenciaTecnologicaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.transferencia = transf
        if form.cleaned_data.get('processo'):
            o.id_processo = form.cleaned_data.get('processo').id
        o.save()
        return httprr('..', 'Recurso cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def editar_recurso_transferencia(request, recurso_id):
    title = 'Editar recurso recebido'
    recurso = get_object_or_404(RecursoTransferencia, pk=recurso_id)
    form = RecursoTransferenciaTecnologicaForm(request.POST or None, request.FILES or None, instance=recurso)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('processo'):
            o.id_processo = form.cleaned_data.get('processo').id
        else:
            o.id_processo = None
        o.save()
        return httprr('..', 'Recurso editado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def excluir_recurso_transferencia(request, recurso_id):
    recurso = get_object_or_404(RecursoTransferencia, pk=recurso_id)
    transf = recurso.transferencia
    recurso.delete()
    return httprr(f'/pesquisa/transferencia_visualizar/{transf.id}/', 'Recurso excluído com sucesso.')


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def cadastrar_documento_transferencia(request, transferencia_id):
    title = 'Cadastrar documento'
    transf = get_object_or_404(TransferenciaTecnologica, pk=transferencia_id)
    form = DocumentoTransferenciaTecnologicaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.transferencia = transf
        if form.cleaned_data.get('documento_eletronico'):
            o.id_documento = form.cleaned_data.get('documento_eletronico').id
        o.save()
        return httprr('..', 'Documento cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def editar_documento_transferencia(request, documento_id):
    title = 'Editar documento'
    documento = get_object_or_404(DocumentoTransferencia, pk=documento_id)
    form = DocumentoTransferenciaTecnologicaForm(request.POST or None, request.FILES or None, instance=documento)
    if form.is_valid():
        o = form.save(False)
        if form.cleaned_data.get('documento_eletronico'):
            o.id_documento = form.cleaned_data.get('documento_eletronico').id
        else:
            o.id_documento = None
        o.save()
        return httprr('..', 'Documento editado com sucesso.')

    return locals()


@rtr()
@permission_required('pesquisa.change_transferenciatecnologica')
def excluir_documento_transferencia(request, documento_id):
    documento = get_object_or_404(DocumentoTransferencia, pk=documento_id)
    transf = documento.transferencia
    documento.delete()
    return httprr(f'/pesquisa/transferencia_visualizar/{transf.id}/', 'Documento excluído com sucesso.')
