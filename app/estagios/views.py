import datetime
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db.models.aggregates import Max
from django.db.transaction import atomic
from django.forms import model_to_dict, modelform_factory
from django.http import FileResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils import timezone

from comum.forms import ConfirmarComSenhaForm
from comum.models import Configuracao, Vinculo
from comum.utils import get_setor, get_uo
from djtools import documentos, layout
from djtools.choices import Meses
from djtools.forms import ModelFormPlus
from djtools.signals import minhas_acoes
from djtools.templatetags.filters import in_group
from djtools.utils import JsonResponse, documento, get_datetime_now, group_required, httprr, permission_required, rtr
from documento_eletronico.models import Documento, DocumentoTexto, HipoteseLegal, ModeloDocumento, TipoVinculoDocumento, VinculoDocumentoTexto
from documento_eletronico.utils import EstagioProcessamentoVariavel, get_variaveis, processar_template_ckeditor
from edu.models import Aluno, Cidade, Estado, Professor
from estagios import tasks
from estagios.forms import (
    AditivoContratualAprendizagemForm,
    AnexoAprendizagemForm,
    AnexoPraticaProfissionalForm,
    AvaliarRelatorioSemestralForm,
    CadastrarCancelamentoAtividadeProfissionalEfetivaForm,
    CadastrarTermoRealizacaoEstagioForm,
    EditarContratoAprendizagemForm,
    EncerrarAprendizagemAbandonoMatriculaIrregularForm,
    EncerrarAprendizagemForm,
    EncerrarAtividadeProfissionalEfetivaForm,
    EncerrarEstagioAbandonoMatriculaIrregularForm,
    EncerrarPraticaProfissionalForm,
    EncontrarAprendizagemForm,
    EncontrarEstagioForm,
    EstagioAditivoContratualForm,
    IniciarSessaoAssinaturaSenhaForm,
    JustificativaVisitaEstagioForm,
    JustificativaVisitaModuloAprendizagemForm,
    NotificacoesAprendizagemForm,
    NotificacoesEstagioForm,
    OrientacaoAprendizagemForm,
    OrientacaoAtividadeProfissionalEfetivaForm,
    OrientacaoEstagioForm,
    RelatorioAtividadeProfissionalEfetivaForm,
    RelatorioModuloAprendizagemForm,
    RelatorioSemestralEstagioForm,
    ResolverDivergenciasRelatoriosForm,
    SolicitacaoCancelamentoEncerramentoAprendizagemForm,
    SolicitacaoCancelamentoEncerramentoAtividadeProfissionalEfetivaForm,
    SolicitacaoCancelamentoEncerramentoEstagioForm,
    VisitaAprendizagemForm,
    VisitaPraticaProfissionalForm,
)
from estagios.models import (
    AditivoContratualAprendizagem,
    AnexoAprendizagem,
    AnexoPraticaProfissionalGenerica,
    Aprendizagem,
    AssinaturaEletronica,
    AtividadeProfissionalEfetiva,
    EstagioAditivoContratual,
    JustificativaVisitaEstagio,
    JustificativaVisitaModuloAprendizagem,
    ModuloAprendizagem,
    OfertaPraticaProfissional,
    OrientacaoAprendizagem,
    OrientacaoAtividadeProfissionalEfetiva,
    OrientacaoEstagio,
    PraticaProfissional,
    RelatorioModuloAprendizagem,
    RelatorioSemestralEstagio,
    SolicitacaoCancelamentoEncerramentoEstagio,
    TermoRealizacaoEstagio,
    VisitaAprendizagem,
    VisitaPraticaProfissional,
)
from estagios.utils import (
    get_divergencias_relatorios_estagio,
    get_divergencias_relatorios_modulo_aprendizagem,
    get_situacoes_irregulares,
    por_extenso,
    tem_permissao_de_coordenador,
)
from rh.models import PessoaJuridica


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    pass


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = [
        {
            'categoria': 'Extensão',
            'url': '/estagios/avaliar_aprendizagem_monitor/',
            'icone': 'chart-line',
            'titulo': 'Avaliação de Aprendizagem',
        },
        {
            'categoria': 'Extensão',
            'url': '/estagios/avaliar_pratica_profissional_supervisor/',
            'icone': 'chart-line',
            'titulo': 'Avaliação de Estágio',
        },
    ]

    return servicos_anonimos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Reúne pendências do módulo Estágios atribuídas ao usuário logado.

    Cobre justificativas e relatórios assinados/aguardando assinatura,
    práticas profissionais sob orientação, supervisão ou coordenação,
    e demais itens em revisão por perfil (orientador, supervisor,
    coordenador de extensão/estágio).

    Args:
        request: requisição HTTP usada para identificar o vínculo do usuário.

    Returns:
        list[dict]: cartões de pendência; lista vazia quando não há nenhuma
        ou o usuário não tem papéis relacionados a estágios.
    """
    pendencias = []
    vinculo_usuario = request.user.get_vinculo()
    campus_usuario = get_uo(request.user)

    # JUSTIFICATIVAS DE DECURSO DE PRAZO PARA VISITA DE ESTÁGIO

    # Queryset base (justificativas de estágios não encerrados).
    qs_justificativas_estagios_nao_encerrados = JustificativaVisitaEstagio.objects.exclude(
        pratica_profissional__status__in=[PraticaProfissional.STATUS_CONCLUIDO, PraticaProfissional.STATUS_RESCINDIDO]
    )

    # Assinatura do Orientador
    if request.user.eh_docente:
        professor = Professor.objects.filter(vinculo=vinculo_usuario).only('id').first()

        qtd_visitas_nao_assinadas = (
            VisitaAprendizagem.objects.filter(orientador__vinculo__user=request.user, assinatura_orientador__isnull=True)
            .exclude(aprendizagem__data_encerramento__isnull=False)
            .count()
        )
        if qtd_visitas_nao_assinadas:
            pendencias.append(
                {
                    'titulo': 'Visitas de Aprendizage{}'.format(pluralize(qtd_visitas_nao_assinadas, 'm,ns')),
                    'subtitulo': 'aguardando assinatura',
                    'qtd': qtd_visitas_nao_assinadas,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )

        qtd_justificativa_visitas_nao_assinadas = (
            qs_justificativas_estagios_nao_encerrados.filter(
                pratica_profissional__orientador__vinculo__user=request.user, assinatura_orientador__isnull=True
            )
            .distinct()
            .count()
        )
        if qtd_justificativa_visitas_nao_assinadas:
            pendencias.append(
                {
                    'titulo': 'Justificativas de Visitas de Estagio{}'.format(pluralize(qtd_justificativa_visitas_nao_assinadas, ',s')),
                    'subtitulo': 'aguardando assinatura como Orientador',
                    'qtd': qtd_justificativa_visitas_nao_assinadas,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )

    # Queryset base para outros signatários (requer que orientador já tenha assinado).
    qs_justificativas_assinadas_pelo_orientador = qs_justificativas_estagios_nao_encerrados.filter(assinatura_orientador__isnull=False)

    # Assinatura do Estagiário
    qtd_justificativa_visitas_nao_assinadas = (
        qs_justificativas_assinadas_pelo_orientador.filter(
            pratica_profissional__aluno__vinculos__user=request.user, assinatura_estagiario__isnull=True
        )
        .distinct()
        .count()
    )
    if qtd_justificativa_visitas_nao_assinadas:
        aluno = Aluno.objects.get(vinculos__user=request.user)
        pendencias.append(
            {
                'titulo': 'Justificativas de Visitas de Estágio{}'.format(pluralize(qtd_justificativa_visitas_nao_assinadas, ',s')),
                'subtitulo': 'aguardando assinatura como Aluno',
                'qtd': qtd_justificativa_visitas_nao_assinadas,
                'url': f'{aluno.get_absolute_url()}?tab=estagios',
            }
        )

    # Assinatura do Coordenador de Extensão
    if in_group(request.user, 'Coordenador de Extensão'):
        qtd_justificativa_visitas_nao_assinadas = (
            qs_justificativas_assinadas_pelo_orientador.filter(
                pratica_profissional__aluno__curso_campus__diretoria__setor__uo=campus_usuario, assinatura_coordenador_extensao__isnull=True
            )
            .distinct()
            .count()
        )
        if qtd_justificativa_visitas_nao_assinadas:
            url_admin_estagios = reverse('admin:estagios_praticaprofissional_changelist')
            pendencias.append(
                {
                    'titulo': 'Justificativas de Visitas de Estágio{}'.format(pluralize(qtd_justificativa_visitas_nao_assinadas, ',s')),
                    'subtitulo': 'aguardando assinatura como Coordenador de Extensão',
                    'qtd': qtd_justificativa_visitas_nao_assinadas,
                    'url': f'{url_admin_estagios}?aguardando_assinatura_coord=1&aluno__curso_campus__diretoria__setor__uo={campus_usuario.id}',
                }
            )

    # RELATÓRIOS SEMESTRAIS DE ESTÁGIO
    qs_relatorios_eletronicos_estagios = RelatorioSemestralEstagio.objects.filter(relatorio='').exclude(
        pratica_profissional__status__in=[PraticaProfissional.STATUS_CONCLUIDO, PraticaProfissional.STATUS_RESCINDIDO]
    )

    # Pendência de assinaturas
    qtd_relatorios_estagio_nao_assinados = 0
    for relatorio in qs_relatorios_eletronicos_estagios.filter(
        pratica_profissional__aluno__vinculos__user=vinculo_usuario.user, assinatura_estagiario=None
    ):
        # A assinatura só será requerida se ambos os relatórios estiverem preenchidos e não forem divergentes.
        if relatorio.relatorio_contraparte and not relatorio.possui_divergencias_com_contraparte():
            qtd_relatorios_estagio_nao_assinados += 1
    if qtd_relatorios_estagio_nao_assinados:
        aluno = Aluno.objects.get(vinculos__user=vinculo_usuario.user)
        pendencias.append(
            {
                'titulo': f'Relatório{pluralize(qtd_relatorios_estagio_nao_assinados)} de Atividades de Estágio',
                'subtitulo': 'aguardando assinatura',
                'qtd': qtd_relatorios_estagio_nao_assinados,
                'url': f'{aluno.get_absolute_url()}?tab=estagios',
            }
        )

    # Antes: 1 query base + 1 query PraticaProfissional.filter(pk__in=ids) + N queries relatoriosemestralestagio_set por estágio.
    # Agora: 1 query única com select_related (aluno) — agrupa contagens por pratica_profissional em memória.
    # N+1 residual: `relatorio_contraparte` e `possui_divergencias_com_contraparte` continuam fazendo queries por iteração.
    relatorios_pendentes_supervisor = qs_relatorios_eletronicos_estagios.filter(
        pratica_profissional__supervisor=vinculo_usuario, assinatura_supervisor=None
    ).select_related('pratica_profissional__aluno')
    contagens_por_estagio = {}
    for relatorio in relatorios_pendentes_supervisor.iterator():
        if relatorio.relatorio_contraparte and not relatorio.possui_divergencias_com_contraparte():
            entry = contagens_por_estagio.setdefault(relatorio.pratica_profissional_id, {'estagio': relatorio.pratica_profissional, 'qtd': 0})
            entry['qtd'] += 1
    for info in contagens_por_estagio.values():
        if info['qtd']:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(info["qtd"])} de Atividades do Estágio de {info["estagio"].aluno}',
                    'subtitulo': 'aguardando assinatura',
                    'qtd': info['qtd'],
                    'url': info['estagio'].get_absolute_url(),
                }
            )

    # RELATÓRIO DE ATIVIDADES DO MÓDULO DA APRENDIZAGEM
    qs_relatorios_eletronicos_aprendizagem = RelatorioModuloAprendizagem.objects.filter(relatorio='').exclude(
        modulo_aprendizagem__aprendizagem__data_encerramento__isnull=False
    )

    # Pendências do Orientador
    if request.user.eh_docente:
        professor = Professor.objects.filter(vinculo=vinculo_usuario).only('id').first()

        # Pendência na resolução de divergências
        qs_docente_pratica = qs_relatorios_eletronicos_estagios.filter(pratica_profissional__orientador__vinculo=vinculo_usuario)
        qtd_relatorios_com_divergencia = 0
        for relatorio in qs_docente_pratica.filter(eh_relatorio_do_supervisor=True):
            if relatorio.possui_divergencias_com_contraparte():
                qtd_relatorios_com_divergencia += 1
        if qtd_relatorios_com_divergencia:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_relatorios_com_divergencia)} de Atividades de Estágio',
                    'subtitulo': 'com divergências pendentes de resolução',
                    'qtd': qtd_relatorios_com_divergencia,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )

        qtd_relatorios_estagio_nao_assinados = 0
        for relatorio in qs_docente_pratica.filter(assinatura_orientador=None):
            # A assinatura só será requerida se ambos os relatórios estiverem preenchidos e não forem divergentes.
            if relatorio.relatorio_contraparte and not relatorio.possui_divergencias_com_contraparte():
                qtd_relatorios_estagio_nao_assinados += 1
        if qtd_relatorios_estagio_nao_assinados:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_relatorios_estagio_nao_assinados)} de Atividades de Estágio',
                    'subtitulo': 'aguardando assinatura',
                    'qtd': qtd_relatorios_estagio_nao_assinados,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )

        qs_docente_aprendizagem = qs_relatorios_eletronicos_aprendizagem.filter(
            modulo_aprendizagem__aprendizagem__orientador__vinculo=vinculo_usuario
        )
        qtd_relatorios_com_divergencia = 0
        qtd_relatorios_sem_revisao = qs_docente_aprendizagem.filter(requer_revisao_orientador=True).count()
        for relatorio in qs_docente_aprendizagem.filter(eh_relatorio_do_empregado_monitor=True):
            if relatorio.possui_divergencias_com_contraparte():
                qtd_relatorios_com_divergencia += 1
            if relatorio.requer_revisao_orientador:
                qtd_relatorios_sem_revisao += 1
            if relatorio.relatorio_contraparte and relatorio.relatorio_contraparte.requer_revisao_orientador:
                qtd_relatorios_sem_revisao += 1
        if qtd_relatorios_com_divergencia:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_relatorios_com_divergencia)} de Atividades de Aprendizagem',
                    'subtitulo': 'com divergências pendentes de resolução',
                    'qtd': qtd_relatorios_com_divergencia,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )
        if qtd_relatorios_sem_revisao:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_relatorios_sem_revisao)} de Atividades de Aprendizagem',
                    'subtitulo': f'pendente{pluralize(qtd_relatorios_sem_revisao)} de revisão',
                    'qtd': qtd_relatorios_sem_revisao,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )

        qtd_relatorios_aprendizagem_nao_assinados = 0
        for relatorio in qs_docente_aprendizagem.exclude(requer_revisao_orientador=True).filter(assinatura_orientador=None):
            # A assinatura só será requerida se ambos os relatórios estiverem preenchidos e não forem divergentes.
            if relatorio.relatorio_contraparte and not relatorio.possui_divergencias_com_contraparte():
                qtd_relatorios_aprendizagem_nao_assinados += 1
        if qtd_relatorios_aprendizagem_nao_assinados:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_relatorios_aprendizagem_nao_assinados)} de Atividades de Aprendizagem',
                    'subtitulo': 'aguardando assinatura',
                    'qtd': qtd_relatorios_aprendizagem_nao_assinados,
                    'url': f'{professor.get_absolute_url()}?tab=estagios',
                }
            )

    # Pendências de assinaturas
    qtd_relatorios_aprendizagem_nao_assinados = 0
    for relatorio in qs_relatorios_eletronicos_aprendizagem.exclude(requer_revisao_orientador=True).filter(
        modulo_aprendizagem__aprendizagem__aprendiz__vinculos__user=vinculo_usuario.user,
        assinatura_aprendiz=None,
    ):
        # A assinatura só será requerida se ambos os relatórios estiverem preenchidos e não forem divergentes.
        if relatorio.relatorio_contraparte and not relatorio.possui_divergencias_com_contraparte():
            qtd_relatorios_aprendizagem_nao_assinados += 1
    if qtd_relatorios_aprendizagem_nao_assinados:
        aluno = Aluno.objects.get(vinculos__user=vinculo_usuario.user)
        pendencias.append(
            {
                'titulo': f'Relatório{pluralize(qtd_relatorios_aprendizagem_nao_assinados)} de Atividades de Aprendizagem',
                'subtitulo': 'aguardando assinatura',
                'qtd': qtd_relatorios_aprendizagem_nao_assinados,
                'url': f'{aluno.get_absolute_url()}?tab=estagios',
            }
        )

    qs_relatorios_aprendizagem_nao_assinados = qs_relatorios_eletronicos_aprendizagem.exclude(requer_revisao_orientador=True).filter(
        modulo_aprendizagem__aprendizagem__monitor=vinculo_usuario, assinatura_monitor=None
    )
    if qs_relatorios_aprendizagem_nao_assinados.exists():
        ids_aprendizagens = qs_relatorios_aprendizagem_nao_assinados.values_list('modulo_aprendizagem__aprendizagem_id', flat=True)
        for aprendizagem in Aprendizagem.objects.filter(pk__in=ids_aprendizagens):
            qtd_relatorios = 0
            for relatorio in qs_relatorios_eletronicos_aprendizagem.filter(modulo_aprendizagem__aprendizagem=aprendizagem, assinatura_monitor=None):
                # A assinatura só será requerida se ambos os relatórios estiverem preenchidos e não forem divergentes.
                if relatorio.relatorio_contraparte and not relatorio.possui_divergencias_com_contraparte():
                    qtd_relatorios += 1
            if qtd_relatorios:
                pendencias.append(
                    {
                        'titulo': f'Relatório{pluralize(qtd_relatorios)} de Atividades da Aprendizagem de {aprendizagem.aprendiz}',
                        'subtitulo': 'aguardando assinatura',
                        'qtd': qtd_relatorios,
                        'url': aprendizagem.get_absolute_url(),
                    }
                )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_group_cached('Coordenador de Estágio Sistêmico', ignore_groups_if_superuser=False):
        qtd_solicitacoes_cancelamento_encerramento_estagio = (
            SolicitacaoCancelamentoEncerramentoEstagio.objects.filter(situacao=SolicitacaoCancelamentoEncerramentoEstagio.AGUARDANDO_RESPOSTA)
            .distinct()
            .count()
        )
        if qtd_solicitacoes_cancelamento_encerramento_estagio:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd_solicitacoes_cancelamento_encerramento_estagio, "ão,ões")} de Cancelamento de Encerramento de Estágio',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_solicitacoes_cancelamento_encerramento_estagio,
                    'url': '/admin/estagios/solicitacaocancelamentoencerramentoestagio/?tab=tab_aguardando_resposta',
                }
            )

    return pendencias


@layout.quadro('Estágios', icone='pencil-alt')
def index_quadros(quadro, request):
    if request.user.has_group_cached(['Coordenador de Estágio Sistêmico', 'Coordenador de Estágio'], ignore_groups_if_superuser=False):
        qs_estagiarios_situacao_matricula_irregular = (
            PraticaProfissional.objects.filter(data_fim__isnull=True, data_prevista_fim__gte=datetime.date.today())
            .filter(aluno__situacao__in=get_situacoes_irregulares())
            .distinct()
            .order_by('-prazo_final_regularizacao_matricula_irregular')
        )
        if not request.user.has_group_cached('Coordenador de Estágio Sistêmico'):
            qs_estagiarios_situacao_matricula_irregular = qs_estagiarios_situacao_matricula_irregular.filter(
                aluno__curso_campus__diretoria__setor__uo=get_uo(request.user)
            )

        qs_estagiarios_situacao_matricula_irregular = qs_estagiarios_situacao_matricula_irregular.count()
        if qs_estagiarios_situacao_matricula_irregular:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Estagiário{pluralize(qs_estagiarios_situacao_matricula_irregular)}',
                    subtitulo='Em situação de matrícula irregular',
                    qtd=qs_estagiarios_situacao_matricula_irregular,
                    url='/admin/estagios/praticaprofissional/?tab=tab_matriculas_irregulares',
                )
            )

        qs_aprendizes_situacao_matricula_irregular = (
            Aprendizagem.objects.filter(data_encerramento__isnull=True)
            .annotate(fim=Max('moduloaprendizagem__fim'))
            .exclude(fim__lt=datetime.date.today())
            .filter(aprendiz__situacao__in=get_situacoes_irregulares())
        )
        if not request.user.has_group_cached('Coordenador de Estágio Sistêmico', ignore_groups_if_superuser=False):
            qs_aprendizes_situacao_matricula_irregular = qs_aprendizes_situacao_matricula_irregular.filter(
                aprendiz__curso_campus__diretoria__setor__uo=get_uo(request.user)
            )

        qs_aprendizes_situacao_matricula_irregular = qs_aprendizes_situacao_matricula_irregular.count()
        if qs_aprendizes_situacao_matricula_irregular:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Aprendiz{}'.format(pluralize(qs_aprendizes_situacao_matricula_irregular, ',es')),
                    subtitulo='Em situação de matrícula irregular',
                    qtd=qs_aprendizes_situacao_matricula_irregular,
                    url='/admin/estagios/aprendizagem/?tab=tab_matriculas_irregulares',
                )
            )

        qs_atividades_profissionais_efetivas_situacao_matricula_irregular = (
            AtividadeProfissionalEfetiva.objects.filter(situacao=AtividadeProfissionalEfetiva.EM_ANDAMENTO)
            .filter(data_prevista_encerramento__gte=datetime.date.today())
            .filter(aluno__situacao__in=get_situacoes_irregulares())
        )
        if not request.user.has_group_cached('Coordenador de Estágio Sistêmico', ignore_groups_if_superuser=False):
            qs_atividades_profissionais_efetivas_situacao_matricula_irregular = (
                qs_atividades_profissionais_efetivas_situacao_matricula_irregular.filter(
                    aluno__curso_campus__diretoria__setor__uo=get_uo(request.user)
                )
            )

        qs_atividades_profissionais_efetivas_situacao_matricula_irregular = qs_atividades_profissionais_efetivas_situacao_matricula_irregular.count()
        if qs_atividades_profissionais_efetivas_situacao_matricula_irregular:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Aluno{pluralize(qs_atividades_profissionais_efetivas_situacao_matricula_irregular)} de Atividades Profissionais Efetivas',
                    subtitulo='Com situação de matrícula irregular',
                    qtd=qs_atividades_profissionais_efetivas_situacao_matricula_irregular,
                    url='/admin/estagios/atividadeprofissionalefetiva/?tab=tab_matriculas_irregulares',
                )
            )

    return quadro


def pode_ver_pratica_profissional(user, pratica_profissional):
    if user.has_perm('estagios.view_praticaprofissional'):
        return True

    uo_logado = get_uo(user)
    return (
        # Permissões com base na relação do usuário com o estágio
        pratica_profissional.eh_orientador(user)
        or pratica_profissional.eh_estagiario(user)
        or pratica_profissional.aluno.curso_campus.coordenador.user == user
        or pratica_profissional.eh_supervisor(user)
        or pratica_profissional.eh_representante_concedente(user)
        # Permissões com base nos grupos do usuário
        or user.has_group_cached('Diretor Acadêmico Sistêmico')
        or (user.has_group_cached('Diretor Acadêmico') and pratica_profissional.aluno.campus == uo_logado)
        or user.has_group_cached('Auditor')
    )


@rtr()
@login_required()
def pratica_profissional(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)
    if not pode_ver_pratica_profissional(request.user, obj):
        raise PermissionDenied
    title = str(obj)
    is_do_mesmo_campus = obj.aluno.campus == (request.user.get_vinculo().setor and request.user.get_vinculo().setor.uo)
    is_administrador = request.user.has_group_cached('estagios Administrador')
    is_coordenador = tem_permissao_de_coordenador(request.user, obj.aluno.campus)
    is_orientador = obj.eh_orientador(request.user)

    hoje = datetime.date.today()
    pode_registrar_relatorio_estagiario = obj.pode_registrar_relatorio(user=request.user, eh_relatorio_do_supervisor=False)
    pode_registrar_relatorio_supervisor = obj.pode_registrar_relatorio(user=request.user, eh_relatorio_do_supervisor=True)
    pode_anexar_arquivos = obj.pode_anexar_arquivos(request.user)
    pode_editar_visita_orientador = is_administrador or is_coordenador
    pode_excluir_visita_orientador = is_administrador or is_coordenador or is_orientador

    return locals()


@rtr()
@permission_required(['estagios.change_praticaprofissional', 'projetos.change_projeto'])
def adicionar_anexo_pratica_profissional(request, pratica_profissional_pk, anexo_pk=None):
    pratica_profissional = get_object_or_404(PraticaProfissional, pk=pratica_profissional_pk)
    title = f'Anexar Arquivo - {pratica_profissional}'
    instance = None
    if anexo_pk:
        instance = get_object_or_404(AnexoPraticaProfissionalGenerica, pk=anexo_pk)
    form = AnexoPraticaProfissionalForm(
        request=request, instance=instance, data=request.POST or None, pratica_profissional=pratica_profissional, files=request.FILES or None
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Arquivo anexado com sucesso.', get_params='tab=documentacao')
    return locals()


@rtr()
@login_required()
def atividade_profissional_efetiva(request, pk):
    obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)
    if not request.user.has_perm('estagios.view_atividadeprofissionalefetiva'):
        if (
            not obj.orientador.vinculo.user == request.user
            and not obj.aluno.get_user() == request.user
            and not obj.aluno.curso_campus.coordenador.user == request.user
            and not request.user.has_group_cached('Auditor')
        ):
            raise PermissionDenied
    title = str(obj)
    is_administrador = request.user.has_group_cached(['Coordenador de Estágio Sistêmico', 'estagios Administrador'])
    is_coordenador = request.user.has_group_cached(['Coordenador de Curso', 'Coordenador de Estágio'])
    if request.GET.get('tab', default=None) == 'relatorio':
        pode_submeter_declaracao = is_administrador or is_coordenador or request.user == obj.aluno.get_user()
    return locals()


@rtr()
@group_required('Coordenador de Estágio Sistêmico, estagios Administrador')
def cancelar_encerramento_estagio(request, pk):
    if request.GET.get('scee_pk'):
        scee = get_object_or_404(SolicitacaoCancelamentoEncerramentoEstagio, pk=request.GET.get('scee_pk'))
        if scee.estagio:
            obj = get_object_or_404(PraticaProfissional, pk=pk)
            obj.movito_encerramento = None
            obj.motivacao_desligamento_encerramento = None
            obj.motivo_rescisao = None
            obj.data_fim = None
            obj.ch_final = 0
            obj.termo_encerramento = None
            obj.ficha_frequencia = None
            obj.estagio_anterior_20161 = False
            obj.desvinculado_matricula_irregular = False
            if obj.tre_eletronico_foi_cadastrado:
                obj.termo_realizacao_eletronico.delete()
            obj.atualizar_situacoes(salvar=True)
            obj.save(desfazer_encerramento=True)
        elif scee.aprendizagem:
            obj = get_object_or_404(Aprendizagem, pk=pk)
            obj.encerramento_por = None
            obj.motivo_encerramento = None
            obj.motivacao_rescisao = None
            obj.data_encerramento = None
            obj.ch_final = None
            obj.comprovante_encerramento = None
            obj.laudo_avaliacao = None
            obj.save()
            obj.notificar()
        elif scee.atividade_profissional_efetiva:
            obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)
            obj.anterior_20171 = None
            obj.encerramento = None
            obj.ch_final = None
            obj.relatorio_final_aluno = None
            obj.observacoes = None
            obj.situacao = obj.EM_ANDAMENTO

            # cancelamento
            obj.cancelamento = None
            obj.motivo_cancelamento = None
            obj.descricao_cancelamento = None
            obj.prazo_final_regularizacao_matricula_irregular = None
            obj.save()
            obj.notificar()
        scee.situacao = SolicitacaoCancelamentoEncerramentoEstagio.DEFERIDA
        scee.save()

    return httprr(
        '/admin/estagios/solicitacaocancelamentoencerramentoestagio/', 'O cancelamento do encerramento do estágio ou afim foi realizado com sucesso.'
    )


@rtr()
@group_required('Coordenador de Estágio Sistêmico, estagios Administrador')
def indeferir_cancelar_encerramento_estagio(request, pk):
    obj = get_object_or_404(SolicitacaoCancelamentoEncerramentoEstagio, pk=pk)
    obj.situacao = SolicitacaoCancelamentoEncerramentoEstagio.INDEFERIDA
    obj.save()
    return httprr('/admin/estagios/solicitacaocancelamentoencerramentoestagio/', 'O indeferimento foi realizado com sucesso.')


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def solicitar_cancelar_encerramento_estagio(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)
    title = f'Solicitar Desfazimento do Encerramento do {obj}'
    form = SolicitacaoCancelamentoEncerramentoEstagioForm(
        request=request,
        data=request.POST or None,
        instance=SolicitacaoCancelamentoEncerramentoEstagio(
            user=request.user, estagio=obj, situacao=SolicitacaoCancelamentoEncerramentoEstagio.AGUARDANDO_RESPOSTA
        ),
    )
    if form.is_valid():
        form.save()
        return httprr(
            f'/estagios/pratica_profissional/{obj.pk}/?tab=informacoes',
            'A solicitação de cancelamento do encerramento do estágio foi realizada com sucesso e está aguardando a resposta da pro-reitoria.',
        )
    return locals()


@rtr()
@group_required('Coordenador de Curso, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def solicitar_cancelar_encerramento_atividade_profissional_efetiva(request, pk):
    obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)
    title = f'Solicitar Desfazimento do Encerramento da Atividade Profissional Efetiva {obj}'
    form = SolicitacaoCancelamentoEncerramentoAtividadeProfissionalEfetivaForm(
        request=request,
        data=request.POST or None,
        instance=SolicitacaoCancelamentoEncerramentoEstagio(
            user=request.user, atividade_profissional_efetiva=obj, situacao=SolicitacaoCancelamentoEncerramentoEstagio.AGUARDANDO_RESPOSTA
        ),
    )
    if form.is_valid():
        form.save()
        return httprr(
            f'/estagios/atividade_profissional_efetiva/{obj.pk}/?tab=informacoes',
            'A solicitação de cancelamento do encerramento da atividade profissional efetiva foi realizada com sucesso e está aguardando a resposta da pro-reitoria.',
        )
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def solicitar_cancelar_encerramento_aprendizagem(request, pk):
    obj = get_object_or_404(Aprendizagem, pk=pk)
    title = f'Solicitar Desfazimento do Encerramento da {obj}'
    form = SolicitacaoCancelamentoEncerramentoAprendizagemForm(
        request=request,
        data=request.POST or None,
        instance=SolicitacaoCancelamentoEncerramentoEstagio(
            user=request.user, aprendizagem=obj, situacao=SolicitacaoCancelamentoEncerramentoEstagio.AGUARDANDO_RESPOSTA
        ),
    )
    if form.is_valid():
        form.save()
        return httprr(
            f'/estagios/aprendizagem/{obj.pk}/?tab=informacoes',
            'A solicitação de cancelamento do encerramento da aprendizagem foi realizada com sucesso e está aguardando a resposta da pro-reitoria.',
        )
    return locals()


def pode_ver_aprendizagem(user, aprendizagem):
    if not user.has_perm('estagios.view_aprendizagem'):
        uo_logado = get_uo(user)
        if not (
            aprendizagem.eh_orientador(user)
            or aprendizagem.eh_aprendiz(user)
            or aprendizagem.aprendiz.curso_campus.coordenador.user == user
            or aprendizagem.eh_monitor(user)
            or (user.has_group_cached('Diretor Acadêmico') and aprendizagem.aprendiz.curso_campus == uo_logado)
            or user.has_group_cached('Diretor Acadêmico Sistêmico')
            or user.has_group_cached('Auditor')
        ):
            return False
    return True


@rtr()
@login_required()
def aprendizagem(request, pk):
    obj = get_object_or_404(Aprendizagem, pk=pk)
    if not pode_ver_aprendizagem(request.user, obj):
        raise PermissionDenied
    title = str(obj)
    hoje = datetime.date.today()
    pode_anexar_arquivos = obj.pode_anexar_arquivos(request.user)
    pode_excluir_visita_orientador = request.user.has_group_cached(['Coordenador de Estágio', 'Coordenador de Estágio Sistêmico']) or (
        obj.orientador.vinculo == request.user.get_vinculo()
    )
    is_do_mesmo_campus = request.user.get_vinculo().setor and obj.aprendiz.campus == request.user.get_vinculo().setor.uo
    is_administrador = request.user.has_group_cached('estagios Administrador')
    is_coordenador = tem_permissao_de_coordenador(request.user, obj.aprendiz.campus)

    is_orientador = obj.eh_orientador(request.user)

    return locals()


@rtr()
@permission_required(['estagios.change_aprendizagem'])
def editar_contrato_aprendizagem(request, aprendizagem_pk):
    aprendizagem = get_object_or_404(Aprendizagem, pk=aprendizagem_pk)
    title = f'Editar contrato da {aprendizagem}'

    form = EditarContratoAprendizagemForm(data=request.POST or None, files=request.FILES or None, instance=aprendizagem, request=request)

    if form.is_valid():
        form.save()
        return httprr('..', 'Contrato editado com sucesso.')
    return locals()


@rtr()
@permission_required(['estagios.change_aprendizagem', 'projetos.change_projeto'])
def adicionar_anexo_aprendizagem(request, aprendizagem_pk, anexo_pk=None):
    aprendizagem = get_object_or_404(Aprendizagem, pk=aprendizagem_pk)
    title = f'Anexar Arquivo - {aprendizagem}'
    instance = None
    if anexo_pk:
        instance = get_object_or_404(AnexoAprendizagem, pk=anexo_pk)
    form = AnexoAprendizagemForm(
        request=request, instance=instance, data=request.POST or None, aprendizagem=aprendizagem, files=request.FILES or None
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Arquivo anexado com sucesso.', get_params='tab=documentacao')
    return locals()


@rtr()
def oferta_pratica_profissional(request, pk):
    obj = get_object_or_404(OfertaPraticaProfissional, pk=pk)
    title = str(obj)
    return locals()


@rtr()
@login_required()
def ofertas_pratica_profissional(request):
    if not request.user.eh_aluno:
        return HttpResponseForbidden('Seu vínculo atual não é de aluno e por isso você não pode acessar esta tela')
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    title = f'Ofertas de Prática Profissional para o Curso {aluno.curso_campus}'
    ofertas = aluno.get_ofertas_pratica_profissional()
    return locals()


@rtr()
@permission_required('estagios.add_praticaprofissional')
def encerrar_pratica_profissional(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)
    title = f'Encerrar Estágio - {obj}'
    form = EncerrarPraticaProfissionalForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        form.instance.aluno.atualizar_situacao('Encerramento de Prática Profissional')
        return httprr(f'/estagios/pratica_profissional/{pk}/?tab=encerramento', 'Estágio encerrado com sucesso.')
    return locals()


@rtr()
@login_required()
def cadastrar_termo_realizacao_eletronico(request, pk):
    estagio = get_object_or_404(PraticaProfissional, pk=pk)
    if not estagio.tem_permissao_escrita_tre_eletronico(request.user):
        return httprr(f'{estagio.get_absolute_url()}?tab=encerramento', 'Você não tem permissão para isto.', tag='error', close_popup=True)

    if estagio.tre_eletronico_foi_cadastrado:
        termo_realizacao = estagio.termo_realizacao_eletronico
        eh_criacao = False
    else:
        termo_realizacao = TermoRealizacaoEstagio(pratica_profissional_id=pk)
        eh_criacao = True
    title = f'{"Cadastrar" if eh_criacao else "Editar"} Termo de Realização do {estagio}'

    form = CadastrarTermoRealizacaoEstagioForm(data=request.POST or None, instance=termo_realizacao, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'{estagio.get_absolute_url()}?tab=encerramento', 'Termo registrado com sucesso.', close_popup=True)
    return locals()


@login_required()
def visualizar_termo_realizacao_estagio(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)

    resposta = None
    if obj.termo_encerramento:
        resposta = FileResponse(obj.termo_encerramento.open('rb'), content_type='application/pdf')

    elif obj.tre_eletronico_foi_cadastrado:
        if obj.termo_realizacao_eletronico.arquivo_interno:
            resposta = FileResponse(obj.termo_realizacao_eletronico.arquivo_interno.open('rb'), content_type='application/pdf')
        else:
            opcoes_documento = {'tipo_para_verificacao': None}
            if obj.termo_realizacao_eletronico.possui_assinatura:
                opcoes_documento = {'tipo_para_verificacao': 'Termo de Realização de Estágio', 'forcar_recriacao': True}
            gerar_termo_realizacao_eletronico_decorated = documento(**opcoes_documento)(gerar_termo_realizacao_eletronico)
            resposta = gerar_termo_realizacao_eletronico_decorated(request, pk=obj.termo_realizacao_eletronico.pk)
            obj.termo_realizacao_eletronico.arquivo_interno.save(f'{obj.termo_realizacao_eletronico.pk}.pdf', ContentFile(resposta.content))
    return resposta


@rtr()
def gerar_termo_realizacao_eletronico(request, pk):
    obj = get_object_or_404(TermoRealizacaoEstagio, pk=pk)
    uo = obj.pratica_profissional.aluno.campus
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')

    dados_assinatura = []
    for assinatura in (obj.assinatura_supervisor, obj.assinatura_estagiario, obj.assinatura_representante_concedente):
        if assinatura:
            dados_assinatura.append(
                {
                    'nome': assinatura.vinculo.nome,
                    'matricula': assinatura.vinculo.user.username,
                    'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                    'chave': assinatura.chave,
                }
            )
    request.GET._mutable = True
    request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
    request.GET._mutable = False
    return locals()


@rtr()
@login_required()
def assinar_termo_realizacao_eletronico(request, pk):
    obj = get_object_or_404(TermoRealizacaoEstagio, pk=pk)
    title = 'Assinar Termo de Realização de Estágio'
    if not obj.pode_assinar(request.user):
        return httprr(f'{obj.pratica_profissional.get_absolute_url()}?tab=encerramento', 'Você não tem permissão para isso.', tag='error')

    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj.assinar(request.user)
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_termo_realizacao_eletronico(request, pk):
    obj = get_object_or_404(TermoRealizacaoEstagio, pk=pk)
    estagio = obj.pratica_profissional
    obj.delete()
    return httprr(f'{estagio.get_absolute_url()}?tab=encerramento', 'Termo de Realização de Estágio removido com sucesso.')


@rtr()
@permission_required('estagios.add_praticaprofissional')
def encerrar_estagio_abandono_matricula_irregular(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)
    title = f'Encerrar Estágio - {obj}'
    form = EncerrarEstagioAbandonoMatriculaIrregularForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr(f'/estagios/pratica_profissional/{pk}/?tab=encerramento', 'Estágio encerrado com sucesso.')
    return locals()


@rtr()
@permission_required('estagios.add_praticaprofissional')
def notificar_pendencias_estagio(request, pk):
    title = 'Notificar pendências do estágio'
    estagio = get_object_or_404(PraticaProfissional, pk=pk)
    if estagio.data_fim or not tem_permissao_de_coordenador(user=request.user, campus=estagio.aluno.campus):
        raise PermissionDenied

    form = NotificacoesEstagioForm(data=request.POST or None, request=request, pratica_profissional=estagio)
    if form.is_valid():
        form.processar()
        return httprr(f'{estagio.get_absolute_url()}?tab=notificacoes', 'As notificações selecionadas foram enviadas.', close_popup=True)
    return locals()


@rtr()
@permission_required('estagios.add_aprendizagem')
def notificar_pendencias_aprendizagem(request, pk):
    title = 'Notificar pendências da aprendizagem'
    aprendizagem = get_object_or_404(Aprendizagem, pk=pk)
    if aprendizagem.data_encerramento or not tem_permissao_de_coordenador(user=request.user, campus=aprendizagem.aprendiz.campus):
        raise PermissionDenied

    form = NotificacoesAprendizagemForm(data=request.POST or None, request=request, aprendizagem=aprendizagem)
    if form.is_valid():
        form.processar()
        return httprr(f'{aprendizagem.get_absolute_url()}?tab=notificacoes', 'As notificações selecionadas foram enviadas.', close_popup=True)
    return locals()


@rtr()
@permission_required('estagios.add_aprendizagem')
def encerrar_aprendizagem(request, pk):
    obj = get_object_or_404(Aprendizagem, pk=pk)
    title = f'Encerrar aprendizagem - {obj}'
    form = EncerrarAprendizagemForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        form.instance.aprendiz.atualizar_situacao('Encerramento de Aprendizagem')
        return httprr('..', 'Aprendizagem encerrada com sucesso.')
    return locals()


@rtr()
@permission_required('estagios.add_aprendizagem')
def encerrar_aprendizagem_abandono_matricula_irregular(request, pk):
    obj = get_object_or_404(Aprendizagem, pk=pk)
    title = f'Encerrar Aprendizagem - {obj}'
    form = EncerrarAprendizagemAbandonoMatriculaIrregularForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Aprendizagem encerrada com sucesso.')
    return locals()


@rtr()
@permission_required('estagios.add_atividadeprofissionalefetiva')
def encerrar_atividade_profissional_efetiva(request, pk):
    obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)
    title = f'Encerrar Atividade Profissional Efetiva - {obj}'
    form = EncerrarAtividadeProfissionalEfetivaForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        form.instance.aluno.atualizar_situacao('Encerramento de Atividade Profissional Efetiva')
        return httprr('..', 'Atividade Profissional Efetiva encerrada com sucesso.')
    return locals()


@rtr()
@permission_required('estagios.add_atividadeprofissionalefetiva')
def cadastrar_cancelamento_atividade_profissional_efetiva(request, pk):
    obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)
    title = f'Adicionar Cancelamento - {obj}'
    form = CadastrarCancelamentoAtividadeProfissionalEfetivaForm(
        request=request, data=request.POST or None, files=request.FILES or None, instance=obj
    )
    if form.is_valid():
        form.save()
        return httprr('..', 'Cancelamento da Atividade Profissional Efetiva registrado com sucesso.')
    return locals()


@rtr()
def avaliar_aprendizagem_monitor(request):
    title = 'Avaliar Aprendizagem'
    category = 'Avaliações'
    icon = 'chart-line'

    if request.method == 'POST':
        form = EncontrarAprendizagemForm(data=request.POST or None, request=request)
        if form.is_valid():
            modulo_aprendizagem = get_object_or_404(ModuloAprendizagem, **form.get_lookups())
            # adicionando flag para indicar que o usuário preencheu corretamente o formulário de consulta
            request.session['consulta_validada'] = True
            # diminuindo o tempo de sessão para 15min, reduzindo o tempo de exposição da view de preenchimento
            request.session.set_expiry(15 * 60)
            return httprr(reverse('preencher_avaliacao_aprendizagem_monitor', kwargs={'modulo_pk': modulo_aprendizagem.pk}))
    else:
        # Apenas preencher formulário de busca com dados que vieram na URL.
        dados_iniciais = request.GET.dict()
        form = EncontrarAprendizagemForm(initial=dados_iniciais, request=request)

    return locals()


@rtr('submeter_relatorio_monitor.html')
def preencher_avaliacao_aprendizagem_monitor(request, modulo_pk):
    modulo_aprendizagem = get_object_or_404(ModuloAprendizagem, pk=modulo_pk)
    if not request.session.get('consulta_validada'):
        raise PermissionDenied

    title = f'Submeter Relatório de Módulo de Aprendizagem de {modulo_aprendizagem.aprendizagem.aprendiz}'
    relatorio = modulo_aprendizagem.relatorio_monitor or RelatorioModuloAprendizagem(
        modulo_aprendizagem=modulo_aprendizagem, eh_relatorio_do_empregado_monitor=True
    )
    form = RelatorioModuloAprendizagemForm(
        request=request,
        instance=relatorio,
        data=request.POST or None,
        files=request.FILES or None,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        # Preenchimento bem-sucedido. Revogando permissão de acesso à view.
        del request.session['consulta_validada']
        return httprr('/', 'Avaliação do monitor registrada com sucesso.')
    return locals()


@rtr()
def avaliar_pratica_profissional_supervisor(request):
    title = 'Avaliar Estágio'
    category = 'Avaliações'
    icon = 'chart-line'

    if request.method == 'POST':
        form = EncontrarEstagioForm(data=request.POST or None, request=request)
        if form.is_valid():
            estagio = get_object_or_404(PraticaProfissional, **form.get_lookups())
            # adicionando flag para indicar que o usuário preencheu corretamente o formulário de consulta
            request.session['consulta_validada'] = True
            # diminuindo o tempo de sessão para 15min, reduzindo o tempo de exposição da view de preenchimento
            request.session.set_expiry(15 * 60)
            return httprr(reverse('preencher_avaliacao_pratica_profissional_supervisor', kwargs={'pk': estagio.pk}))
    else:
        # Apenas preencher formulário de busca com dados que vieram na URL.
        dados_iniciais = request.GET.dict()
        form = EncontrarEstagioForm(initial=dados_iniciais, request=request)

    return locals()


@rtr()
def preencher_avaliacao_pratica_profissional_supervisor(request, pk):
    estagio = get_object_or_404(PraticaProfissional, pk=pk)
    if not request.session.get('consulta_validada'):
        raise PermissionDenied

    title = f'Submeter Relatório Semestral do estágio de {estagio.aluno}'
    form = RelatorioSemestralEstagioForm(
        request=request,
        instance=RelatorioSemestralEstagio(pratica_profissional=estagio, eh_relatorio_do_supervisor=True),
        data=request.POST or None,
        files=request.FILES or None,
    )

    if not estagio.ha_pendencia_relatorio_supervisor():
        return httprr(
            '/',
            'Todas as avaliações demandadas do supervisor já foram enviadas ou o estágio já se encontra encerrado. Em caso de dúvidas procurar a coordenação responsável por estágios no campus do aluno.',
        )

    if request.POST and form.is_valid():
        form.save()
        # Preenchimento bem-sucedido. Revogando permissão de acesso à view.
        del request.session['consulta_validada']
        return httprr('/', 'Avaliação do supervisor registrada com sucesso.')

    return locals()


@rtr()
@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def cadastrar_visitapraticaprofissional(request, pk, visita_pk=None):
    obj = get_object_or_404(PraticaProfissional, pk=pk, data_fim__isnull=True)
    title = f'Adicionar Visita Trimestral ao Estágio de {obj.aluno}'
    if visita_pk:
        instance = get_object_or_404(VisitaPraticaProfissional, pk=visita_pk)

    if (
        not request.user.has_group_cached(['Coordenador de Estágio', 'Coordenador de Estágio Sistêmico'])
        and not request.user == obj.orientador.vinculo.user
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    form = VisitaPraticaProfissionalForm(
        request.POST or None,
        instance=visita_pk and instance or VisitaPraticaProfissional(ultimo_editor=request.user, pratica_profissional=obj, orientador=obj.orientador),
        initial={'pratica_profissional': obj.pk},
        files=request.FILES or None,
    )
    if form.is_valid():
        form.save()
        return httprr(f'/estagios/pratica_profissional/{obj.pk}/?tab=visitas', 'Visita adicionada com sucesso.')
    close_popup = True
    return locals()


@rtr()
@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def cadastrar_visita_aprendizagem(request, pk, visita_pk=None):
    obj = get_object_or_404(Aprendizagem, pk=pk)
    title = f'Adicionar Visita da Aprendizagem de {obj.aprendiz}'
    instance = VisitaAprendizagem(ultimo_editor=request.user, aprendizagem=obj, orientador=obj.orientador)
    if visita_pk:
        instance = get_object_or_404(VisitaAprendizagem, pk=visita_pk)

    if (
        not request.user.has_group_cached(['Coordenador de Estágio', 'Coordenador de Estágio Sistêmico'])
        and not request.user == obj.orientador.vinculo.user
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    form = VisitaAprendizagemForm(request.POST or None, instance=instance, files=request.FILES or None, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/estagios/aprendizagem/{obj.pk}/?tab=visitas', 'Visita adicionada com sucesso.', close_popup=True)
    close_popup = True
    return locals()


@rtr()
@group_required('Professor')
def agendar_orientacao_atividade_profissional_efetiva(request, pk, orientacao_pk=None):
    obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk, orientador__vinculo__user=request.user)
    title = 'Registro/Agendamento de Orientação de Atividade Profissional Efetiva'
    instance = None
    if orientacao_pk:
        instance = get_object_or_404(
            OrientacaoAtividadeProfissionalEfetiva, pk=orientacao_pk, atividade_profissional_efetiva__orientador__vinculo__user=request.user
        )
    form = OrientacaoAtividadeProfissionalEfetivaForm(
        request=request, instance=instance, data=request.POST or None, atividade_profissional_efetiva=obj
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Registro/Agendamento de orientação adicionado com sucesso.')
    return locals()


@rtr()
@group_required('Professor')
def agendar_orientacao_estagio(request, pk, orientacao_pk=None):
    obj = get_object_or_404(PraticaProfissional, pk=pk, orientador__vinculo__user=request.user)
    title = 'Agendamento de Orientação de Estágio'
    instance = None
    if orientacao_pk:
        instance = get_object_or_404(OrientacaoEstagio, pk=orientacao_pk, pratica_profissional__orientador__vinculo__user=request.user)
    form = OrientacaoEstagioForm(request=request, instance=instance, data=request.POST or None, pratica_profissional=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Agendamento de orientação adicionado com sucesso.')
    return locals()


@rtr()
@group_required('Professor')
def agendar_orientacao_aprendizagem(request, pk, orientacao_pk=None):
    obj = get_object_or_404(Aprendizagem, pk=pk, orientador__vinculo__user=request.user)
    title = 'Agendamento de Orientação de Aprendizagem'
    instance = None
    if orientacao_pk:
        instance = get_object_or_404(OrientacaoAprendizagem, pk=orientacao_pk, aprendizagem__orientador__vinculo__user=request.user)
    form = OrientacaoAprendizagemForm(request=request, instance=instance, data=request.POST or None, aprendizagem=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Agendamento de orientação adicionado com sucesso.')
    return locals()


@rtr()
@group_required('Professor, Aluno, Coordenador de Estágio, Coordenador de Estágio Sistêmico, Coordenador de Estágio Docente, estagios Administrador')
def visualizar_dados_visita(request, pk):
    obj = get_object_or_404(VisitaPraticaProfissional, pk=pk)
    title = 'Registro de Visita do Orientador ao Estagiário'
    return locals()


@rtr()
@group_required('Professor, Aluno, Coordenador de Estágio, Coordenador de Estágio Sistêmico, Coordenador de Estágio Docente, estagios Administrador')
def visualizar_dados_visita_aprendizagem(request, pk):
    obj = get_object_or_404(VisitaAprendizagem, pk=pk)
    title = 'Registro da Visita do Orientador ao Aprendiz na Concedente.'
    return locals()


@rtr()
@permission_required('estagios.add_praticaprofissional')
def adicionar_estagio_aditivo_contratual(request, pk, aditivo_pk=None):
    pratica_profissional = get_object_or_404(PraticaProfissional, pk=pk)
    title = f'Adicionar Aditivo - {pratica_profissional}'
    instance = None
    if aditivo_pk:
        instance = get_object_or_404(EstagioAditivoContratual, pk=aditivo_pk)
    form = EstagioAditivoContratualForm(
        request=request, instance=instance, data=request.POST or None, pratica_profissional=pratica_profissional, files=request.FILES or None
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr(f'/estagios/pratica_profissional/{pratica_profissional.pk}/?tab=documentacao', 'Aditivo adicionado com sucesso.')
    return locals()


@rtr()
@group_required('Aluno, Coordenador de Curso, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def submeter_relatorio_atividade_profissional_efetiva(request, pk):
    atividade_profissional_efetiva = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)

    if (
        not request.user.has_group_cached(['Coordenador de Curso', 'Coordenador de Estágio', 'Coordenador de Estágio Sistêmico'])
        and not request.user == atividade_profissional_efetiva.aluno.get_user()
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    title = 'Submeter Declaração de Realização de Atividade Profissional Efetiva'

    form = RelatorioAtividadeProfissionalEfetivaForm(
        request=request, instance=atividade_profissional_efetiva, data=request.POST or None, files=request.FILES or None
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Declaração de realização de atividade profissional efetiva registrada com sucesso.')
    return locals()


@rtr()
@group_required('Aluno, Coordenador de Curso, Coordenador de Estágio, Coordenador de Estágio Sistêmico, Servidor')
def submeter_relatorio_semestral(request, pk, relatorio_pk=None):
    pratica_profissional = get_object_or_404(PraticaProfissional, pk=pk)
    title = 'Submeter Relatório Semestral do Aluno'
    if relatorio_pk:
        relatorio_semestral_estagio = get_object_or_404(RelatorioSemestralEstagio, pk=relatorio_pk)

    if not pratica_profissional.pode_registrar_relatorio(user=request.user, eh_relatorio_do_supervisor=False, exclude_relatorio_pk=relatorio_pk):
        return httprr(f'{pratica_profissional.get_absolute_url()}?tab=relatorios', 'Você não pode registrar o relatório no momento.', tag='error')

    form = RelatorioSemestralEstagioForm(
        request=request,
        instance=relatorio_pk
        and relatorio_semestral_estagio
        or RelatorioSemestralEstagio(pratica_profissional=pratica_profissional, eh_relatorio_do_supervisor=False, ultimo_editor=request.user),
        data=request.POST or None,
        files=request.FILES or None,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr(f'{pratica_profissional.get_absolute_url()}?tab=relatorios', 'Avaliação registrada com sucesso.')
    return locals()


@rtr()
def registrar_avaliacao_supervisor_pratica_profissional(request, pk, relatorio_pk=None):
    pratica_profissional = get_object_or_404(PraticaProfissional, pk=pk)
    title = f'Registro da Avaliação do Supervisor - {pratica_profissional}'
    if relatorio_pk:
        relatorio_semestral_estagio = get_object_or_404(RelatorioSemestralEstagio, pk=relatorio_pk)

    if not pratica_profissional.pode_registrar_relatorio(user=request.user, eh_relatorio_do_supervisor=True, exclude_relatorio_pk=relatorio_pk):
        return httprr(
            f'{pratica_profissional.get_absolute_url()}?tab=avaliacaosupervisor', 'Você não pode registrar o relatório no momento.', tag='error'
        )

    form = RelatorioSemestralEstagioForm(
        request=request,
        instance=relatorio_pk
        and relatorio_semestral_estagio
        or RelatorioSemestralEstagio(pratica_profissional=pratica_profissional, eh_relatorio_do_supervisor=True, ultimo_editor=request.user),
        data=request.POST or None,
        files=request.FILES or None,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr(f'{pratica_profissional.get_absolute_url()}?tab=avaliacaosupervisor', 'Avaliação do supervisor registrada com sucesso.')
    return locals()


@group_required(
    'Professor, Aluno, Coordenador de Estágio, Coordenador de Estágio Sistêmico, Coordenador de Estágio Docente, estagios Administrador, Usuário Externo'
)
def visualizar_relatorio_semestral_estagio(request, pk):
    obj = get_object_or_404(RelatorioSemestralEstagio, pk=pk)
    if obj.relatorio_interno:
        response = FileResponse(obj.relatorio_interno.open('rb'), content_type='application/pdf')
        return response

    gerar_relatorio_semestral_estagio_decorated = documento(tipo_para_verificacao=None)(gerar_relatorio_semestral_estagio)
    retorno = gerar_relatorio_semestral_estagio_decorated(request, pk=pk)
    obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
    return retorno


@rtr()
def gerar_relatorio_semestral_estagio(request, pk):
    obj = get_object_or_404(RelatorioSemestralEstagio, pk=pk)
    uo = obj.pratica_profissional.aluno.campus

    dados_assinatura = []
    for assinatura in (obj.assinatura_estagiario, obj.assinatura_supervisor, obj.assinatura_orientador):
        if assinatura:
            dados_assinatura.append(
                {
                    'nome': assinatura.vinculo.pessoa.nome,
                    'matricula': assinatura.vinculo.user.username,
                    'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                    'chave': assinatura.chave,
                }
            )
    request.GET._mutable = True
    request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
    request.GET._mutable = False
    return locals()


@login_required()
@rtr()
@atomic()
def assinar_relatorio_semestral_estagio(request, pk):
    obj = get_object_or_404(RelatorioSemestralEstagio, pk=pk)
    title = f'Assinar Relatório do {"Supervisor" if obj.eh_relatorio_do_supervisor else "Estagiário"}'
    if not obj.pode_assinar(request.user):
        return HttpResponseForbidden()

    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj.assinar(request.user)
        gerar_relatorio_semestral_estagio_decorated = documento(tipo_para_verificacao='Relatório das Atividades de Estágio', forcar_recriacao=True)(
            gerar_relatorio_semestral_estagio
        )
        retorno = gerar_relatorio_semestral_estagio_decorated(request, pk=pk)
        if obj.relatorio_interno:
            obj.relatorio_interno.delete()
        obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico, Professor')
def anexar_relatorio_digitalizado_estagio(request, pk):
    relatorio = get_object_or_404(RelatorioSemestralEstagio, pk=pk)
    title = 'Anexar relatório digitalizado'

    if not relatorio.pode_editar(request.user):
        raise PermissionDenied

    form = modelform_factory(model=RelatorioSemestralEstagio, form=ModelFormPlus, fields=('relatorio',))(
        request=request,
        instance=relatorio,
        data=request.POST or None,
        files=request.FILES or None,
    )
    form.fields['relatorio'].required = True

    if request.POST and form.is_valid():
        instance = form.save()
        instance.resetar_relatorio_eletronico()
        return httprr('..', 'Arquivo anexado com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico, Professor')
def remover_relatorio_digitalizado_estagio(request, pk):
    relatorio = get_object_or_404(RelatorioSemestralEstagio, pk=pk)
    if (
        not in_group(request.user, 'Coordenador de Estágio Sistêmico')
        and relatorio.pratica_profissional.aluno.campus != request.user.get_vinculo().setor.uo
    ):
        raise PermissionDenied

    relatorio.relatorio.delete()
    tasks.notificar_pendencia_assinatura_relatorio_semestral_estagio(relatorio)
    return httprr('..', 'Arquivo removido com sucesso.')


@rtr()
@group_required('Professor')
def resolver_divergencias_relatorio_estagio(request, pk):
    title = 'Resolver divergências entre relatórios de estágio'
    relatorio = get_object_or_404(RelatorioSemestralEstagio, pk=pk)
    if not relatorio.pode_resolver_divergencias(request.user):
        raise PermissionDenied

    rel_aluno = relatorio if not relatorio.eh_relatorio_do_supervisor else relatorio.relatorio_contraparte
    rel_supervisor = relatorio if relatorio.eh_relatorio_do_supervisor else relatorio.relatorio_contraparte
    divergencias = get_divergencias_relatorios_estagio(rel_aluno, rel_supervisor)

    form = ResolverDivergenciasRelatoriosForm(
        data=request.POST or None,
        eh_relatorio_estagio=True,
        rel_aluno=rel_aluno,
        rel_supervisor_monitor=rel_supervisor,
        divergencias=divergencias,
    )
    if form.is_valid():
        form.processar()

        # Se a versão do aluno foi escolhida pelo menos uma vez, significa que o relatório do supervisor
        # foi alterado (e vice-versa), e precisa ser resetado para solicitar novas assinaturas eletrônicas.
        if ResolverDivergenciasRelatoriosForm.VERSAO_SUPERVISOR_MONITOR in form.cleaned_data.values():
            rel_aluno.resetar_relatorio_eletronico()
            tasks.notificar_pendencia_assinatura_relatorio_semestral_estagio(rel_aluno)
        if ResolverDivergenciasRelatoriosForm.VERSAO_ALUNO in form.cleaned_data.values():
            rel_supervisor.resetar_relatorio_eletronico()
            tasks.notificar_pendencia_assinatura_relatorio_semestral_estagio(rel_supervisor)
        return httprr('..', 'Relatórios atualizados com sucesso.')

    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico, Professor, Aluno')
def submeter_relatorio_modulo_aprendizagem(request, pk, modulo_pk=None):
    aprendizagem = get_object_or_404(Aprendizagem, pk=pk)
    if not aprendizagem.pode_cadastrar_relatorio_aprendiz(request.user):
        raise PermissionDenied
    title = 'Submeter Relatório do Módulo - Aluno'
    if modulo_pk:
        modulo_aprendizagem = get_object_or_404(ModuloAprendizagem, pk=modulo_pk)
        title = f'Submeter Relatório do {modulo_aprendizagem} - Aprendiz'

    form = RelatorioModuloAprendizagemForm(
        request=request,
        instance=modulo_aprendizagem.relatorio_aprendiz
        or RelatorioModuloAprendizagem(modulo_aprendizagem=modulo_aprendizagem, eh_relatorio_do_empregado_monitor=False, ultimo_editor=request.user),
        data=request.POST or None,
        files=request.FILES or None,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Avaliação registrada com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico, Professor, Usuário Externo')
def submeter_relatorio_monitor(request, pk, modulo_pk=None):
    aprendizagem = get_object_or_404(Aprendizagem, pk=pk)
    if not aprendizagem.pode_cadastrar_relatorio_monitor(request.user):
        raise PermissionDenied

    if modulo_pk:
        modulo_aprendizagem = get_object_or_404(ModuloAprendizagem, pk=modulo_pk)
        title = f'Submeter Relatório do {modulo_aprendizagem} - Empregado Monitor'

    form = RelatorioModuloAprendizagemForm(
        request=request,
        instance=modulo_aprendizagem.tem_relatorio_monitor()
        and modulo_aprendizagem.relatorio_monitor
        or RelatorioModuloAprendizagem(modulo_aprendizagem=modulo_aprendizagem, eh_relatorio_do_empregado_monitor=True, ultimo_editor=request.user),
        data=request.POST or None,
        files=request.FILES or None,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Avaliação registrada com sucesso.')
    return locals()


@rtr()
@group_required(
    'Professor, Aluno, Coordenador de Estágio, Coordenador de Estágio Sistêmico, Coordenador de Estágio Docente, estagios Administrador, Usuário Externo'
)
def visualizar_relatorio_aprendizagem(request, pk):
    obj = get_object_or_404(RelatorioModuloAprendizagem, pk=pk)

    pode_editar = obj.pode_editar(request.user)

    if obj.eh_relatorio_do_empregado_monitor:
        title = 'Registro do Relatório do Empregado Monitor'
    else:
        title = 'Registro do Relatório do Aprendiz'
    return locals()


@group_required(
    'Professor, Aluno, Coordenador de Estágio, Coordenador de Estágio Sistêmico, Coordenador de Estágio Docente, estagios Administrador, Usuário Externo'
)
def visualizar_relatorio_eletronico_modulo_aprendizagem(request, pk):
    obj = get_object_or_404(RelatorioModuloAprendizagem, pk=pk)
    if obj.relatorio_interno:
        response = FileResponse(obj.relatorio_interno.open('rb'), content_type='application/pdf')
        return response

    if obj.relatorio:
        return HttpResponseRedirect(obj.relatorio.get_url_publica())

    gerar_relatorio_modulo_aprendizagem_decorated = documento(tipo_para_verificacao=None)(gerar_relatorio_modulo_aprendizagem)
    retorno = gerar_relatorio_modulo_aprendizagem_decorated(request, pk=pk)
    obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
    return retorno


@rtr()
def gerar_relatorio_modulo_aprendizagem(request, pk):
    obj = get_object_or_404(RelatorioModuloAprendizagem, pk=pk)
    uo = obj.modulo_aprendizagem.aprendizagem.aprendiz.campus

    dados_assinatura = []
    for assinatura in (obj.assinatura_aprendiz, obj.assinatura_orientador, obj.assinatura_monitor):
        if assinatura:
            dados_assinatura.append(
                {
                    'nome': assinatura.vinculo.pessoa.nome,
                    'matricula': assinatura.vinculo.user.username,
                    'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                    'chave': assinatura.chave,
                }
            )
    request.GET._mutable = True
    request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
    request.GET._mutable = False
    return locals()


@login_required()
@rtr()
@atomic()
def assinar_relatorio_modulo_aprendizagem(request, pk):
    obj = get_object_or_404(RelatorioModuloAprendizagem, pk=pk)
    title = f'Assinar Relatório do {"Empregado Monitor" if obj.eh_relatorio_do_empregado_monitor else "Aprendiz"}'
    if not obj.pode_assinar(request.user):
        return HttpResponseForbidden()

    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj.assinar(request.user)
        gerar_relatorio_modulo_aprendizagem_decorated = documento(
            tipo_para_verificacao='Relatório das Atividades da Aprendizagem', forcar_recriacao=True
        )(gerar_relatorio_modulo_aprendizagem)
        retorno = gerar_relatorio_modulo_aprendizagem_decorated(request, pk=pk)
        if obj.relatorio_interno:
            obj.relatorio_interno.delete()
        obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico, Professor')
def anexar_relatorio_digitalizado_aprendizagem(request, pk):
    relatorio = get_object_or_404(RelatorioModuloAprendizagem, pk=pk)
    title = 'Anexar relatório digitalizado'

    if not relatorio.pode_editar(request.user):
        raise PermissionDenied

    form = modelform_factory(model=RelatorioModuloAprendizagem, form=ModelFormPlus, fields=('relatorio',))(
        request=request,
        instance=relatorio,
        data=request.POST or None,
        files=request.FILES or None,
    )
    form.fields['relatorio'].required = True

    if request.POST and form.is_valid():
        instance = form.save()
        instance.resetar_relatorio_eletronico()
        return httprr('..', 'Arquivo anexado com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico, Professor')
def remover_relatorio_digitalizado_aprendizagem(request, pk):
    relatorio = get_object_or_404(RelatorioModuloAprendizagem, pk=pk)

    if not relatorio.pode_editar(request.user):
        raise PermissionDenied

    relatorio.relatorio.delete()
    tasks.notificar_pendencia_assinatura_relatorio_modulo_aprendizagem(relatorio)
    return httprr('..', 'Arquivo removido com sucesso.')


@rtr()
@group_required('Professor')
def resolver_divergencias_relatorio_modulo_aprendizagem(request, pk):
    title = 'Resolver divergências entre relatórios de atividades'
    modulo = get_object_or_404(ModuloAprendizagem, pk=pk)
    if not modulo.relatorio_aprendiz.pode_resolver_divergencias(request.user):
        return PermissionDenied

    rel_aprendiz = modulo.relatorio_aprendiz
    rel_monitor = modulo.relatorio_monitor
    divergencias = get_divergencias_relatorios_modulo_aprendizagem(rel_aprendiz, rel_monitor)

    form = ResolverDivergenciasRelatoriosForm(
        data=request.POST or None,
        eh_relatorio_estagio=False,
        rel_aluno=modulo.relatorio_aprendiz,
        rel_supervisor_monitor=modulo.relatorio_monitor,
        divergencias=divergencias,
    )
    if form.is_valid():
        form.processar()

        # Se a versão do aprendiz foi escolhida pelo menos uma vez, significa que o relatório do monitor
        # foi alterado (e vice-versa), e precisa ser resetado para solicitar novas assinaturas eletrônicas.
        if ResolverDivergenciasRelatoriosForm.VERSAO_SUPERVISOR_MONITOR in form.cleaned_data.values():
            rel_aprendiz.resetar_relatorio_eletronico()
            tasks.notificar_pendencia_assinatura_relatorio_modulo_aprendizagem(rel_aprendiz)
        if ResolverDivergenciasRelatoriosForm.VERSAO_ALUNO in form.cleaned_data.values():
            rel_monitor.resetar_relatorio_eletronico()
            tasks.notificar_pendencia_assinatura_relatorio_modulo_aprendizagem(rel_monitor)
        return httprr('..', 'Relatórios atualizados com sucesso.')

    return locals()


@rtr()
@group_required('Professor')
def revisar_relatorios_modulo_aprendizagem(request, pk):
    modulo = get_object_or_404(ModuloAprendizagem, pk=pk)
    if request.user.get_vinculo() != modulo.aprendizagem.orientador.get_vinculo():
        return httprr(modulo.aprendizagem.get_absolute_url(), 'Você não tem permissão para isso.', tag='error')

    title = f'Revisar relatórios do {modulo}'

    form = ConfirmarComSenhaForm(data=request.POST or None, request=request)
    form.SUBMIT_LABEL = 'Aprovar'

    relatorio_aprendiz = modulo.relatorio_aprendiz
    relatorio_monitor = modulo.relatorio_monitor

    if form.is_valid():
        relatorio_aprendiz.requer_revisao_orientador = False
        relatorio_monitor.requer_revisao_orientador = False
        relatorio_aprendiz.save()
        relatorio_monitor.save()
        return httprr('..', 'Relatórios revisados com sucesso.')

    return locals()


@rtr()
def avaliar_relatorio_semestral(request, pk):
    instance = get_object_or_404(RelatorioSemestralEstagio, pk=pk, orientador__vinculo__user=request.user)
    title = 'Avaliar Relatório Semestral'

    form = AvaliarRelatorioSemestralForm(request=request, instance=instance, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Observações do relatório semestral atualizadas com sucesso.')
    return locals()


@rtr()
@permission_required('estagios.add_aprendizagem')
def adicionar_aditivo_contratual_aprendizagem(request, pk, aditivo_pk=None):
    aprendizagem = get_object_or_404(Aprendizagem, pk=pk)
    title = f'Adicionar Aditivo - {aprendizagem}'
    instance = None
    if aditivo_pk:
        instance = get_object_or_404(AditivoContratualAprendizagem, pk=aditivo_pk)
    form = AditivoContratualAprendizagemForm(
        request=request, instance=instance, data=request.POST or None, aprendizagem=aprendizagem, files=request.FILES or None
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Aditivo adicionado com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Curso, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def enviar_notificacoes_atividade_profissional_efetiva(request, pk):
    obj = get_object_or_404(AtividadeProfissionalEfetiva, pk=pk)
    obj.notificar()
    return httprr(f'/estagios/atividade_profissional_efetiva/{obj.pk}/?tab=notificacoes', f'Notificações da {obj} enviadas com sucesso.')


@rtr()
@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def justificar_visita_estagio(request, pk):
    inicio = request.GET.get('inicio', default=None)
    fim = request.GET.get('fim', default=None)
    instance = None
    pratica_profissional = None
    if not inicio and not fim:
        instance = get_object_or_404(JustificativaVisitaEstagio, pk=pk)
    else:
        pratica_profissional = get_object_or_404(PraticaProfissional, pk=pk)
        inicio = datetime.datetime.strptime(inicio, '%d/%m/%Y').date()
        fim = datetime.datetime.strptime(fim, '%d/%m/%Y').date()

        erro = True
        for trimestre in pratica_profissional.get_periodos_trimestrais():
            if trimestre['inicio'] == inicio and trimestre['fim'] == fim:
                erro = False
                break
        if erro:
            raise PermissionDenied

        instance = JustificativaVisitaEstagio(inicio=inicio, fim=fim, pratica_profissional=pratica_profissional)

    form = JustificativaVisitaEstagioForm(request=request, instance=instance, data=request.POST or None, files=request.FILES or None)
    title = 'Justificar Decurso de Prazo'
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr(f'/estagios/pratica_profissional/{instance.pratica_profissional_id}/?tab=visitas', 'Justificativa adicionada com sucesso.')
    return locals()


@login_required()
def ver_justificativa_visita_estagio(request, pk):
    obj = get_object_or_404(JustificativaVisitaEstagio, pk=pk)
    if not pode_ver_pratica_profissional(request.user, obj.pratica_profissional):
        raise PermissionDenied

    if obj.relatorio_interno:
        try:
            response = FileResponse(obj.relatorio_interno.open('rb'), content_type='application/pdf')
            return response
        except Exception:
            return httprr(
                f'/estagios/pratica_profissional/{obj.pratica_profissional_id}/?tab=visitas',
                'Erro ao tentar visualizar a justificativa de visita de estágio. Edite a justificativa de visita de estágio e tente novamente.',
                'error',
            )

    gerar_justificativa_visita_estagio_decorated = documento(tipo_para_verificacao=None)(gerar_justificativa_visita_estagio)
    retorno = gerar_justificativa_visita_estagio_decorated(request, pk=pk)
    obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
    return retorno


@login_required()
@rtr()
@atomic()
def assinar_justificativa_visita_estagio(request, pk, papel):
    obj = get_object_or_404(JustificativaVisitaEstagio, pk=pk)
    title = 'Assinar Justificar Decurso de Prazo'
    if not obj.pode_assinar(request.user):
        return HttpResponseForbidden()

    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj.assinar(request.user, papel)
        gerar_justificativa_visita_estagio_decorated = documento(tipo_para_verificacao='Justificar Decurso de Prazo', forcar_recriacao=True)(
            gerar_justificativa_visita_estagio
        )
        retorno = gerar_justificativa_visita_estagio_decorated(request, pk=pk)
        if obj.relatorio_interno:
            obj.relatorio_interno.delete()
        obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@rtr()
def gerar_justificativa_visita_estagio(request, pk):
    obj = get_object_or_404(JustificativaVisitaEstagio, pk=pk)
    uo = obj.pratica_profissional.aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()

    if obj.assinatura_orientador:
        papeis_e_assinaturas = [
            ('Orientador', obj.assinatura_orientador),
            ('Estagiário', obj.assinatura_estagiario),
            ('Coordenador de Curso', obj.assinatura_coordenador_curso),
            ('Coordenador de Extensão', obj.assinatura_coordenador_extensao),
            ('Diretor Acadêmico', obj.assinatura_diretor_academico),
        ]

        dados_assinatura = [
            {
                'nome': assinatura.vinculo.pessoa.nome,
                'matricula': assinatura.vinculo.user.username,
                'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                'chave': assinatura.chave,
                'papel': papel,
            }
            for papel, assinatura in papeis_e_assinaturas
            if assinatura is not None
        ]

        request.GET._mutable = True
        request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
        request.GET._mutable = False
    return locals()


@rtr()
@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def justificar_visita_modulo_aprendizagem(request, pk):
    modulo = get_object_or_404(ModuloAprendizagem, pk=pk)
    if not modulo.aprendizagem.pode_justificar_decurso_prazo_visita(request.user, modulo):
        return httprr('..', 'Você não tem permissão para isso.', tag='error')

    justificativa = modulo.justificativa_visita or JustificativaVisitaModuloAprendizagem(modulo=modulo)

    form = JustificativaVisitaModuloAprendizagemForm(request=request, instance=justificativa, data=request.POST or None, files=request.FILES or None)
    title = 'Justificar Decurso de Prazo'
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr(f'{modulo.aprendizagem.get_absolute_url()}/?tab=visitas', 'Justificativa adicionada com sucesso.', close_popup=True)
    return locals()


@login_required()
def ver_justificativa_visita_modulo_aprendizagem(request, pk):
    obj = get_object_or_404(JustificativaVisitaModuloAprendizagem, pk=pk)
    if not pode_ver_aprendizagem(request.user, obj.aprendizagem):
        raise PermissionDenied

    if obj.relatorio_interno:
        try:
            response = FileResponse(obj.relatorio_interno.open('rb'), content_type='application/pdf')
            return response
        except Exception:
            return httprr(
                f'{obj.aprendizagem.get_absolute_url()}/?tab=visitas',
                'Erro ao tentar visualizar a justificativa de visita de aprendizagem. Edite a justificativa e tente novamente.',
                'error',
            )

    gerar_justificativa_visita_modulo_aprendizagem_decorated = documento(tipo_para_verificacao=None)(gerar_justificativa_visita_modulo_aprendizagem)
    retorno = gerar_justificativa_visita_modulo_aprendizagem_decorated(request, pk=pk)
    obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
    return retorno


@rtr()
def gerar_justificativa_visita_modulo_aprendizagem(request, pk):
    obj = get_object_or_404(JustificativaVisitaModuloAprendizagem, pk=pk)
    uo = obj.aprendizagem.aprendiz.curso_campus.diretoria.setor.uo
    hoje = timezone.now().date()

    if obj.assinatura_orientador:
        papeis_e_assinaturas = [
            ('Orientador', obj.assinatura_orientador),
            ('Aprendiz', obj.assinatura_aprendiz),
            ('Coordenador de Curso', obj.assinatura_coordenador_curso),
            ('Coordenador de Extensão', obj.assinatura_coordenador_extensao),
            ('Diretor Acadêmico', obj.assinatura_diretor_academico),
        ]

        dados_assinatura = [
            {
                'nome': assinatura.vinculo.pessoa.nome,
                'matricula': assinatura.vinculo.user.username,
                'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                'chave': assinatura.chave,
                'papel': papel,
            }
            for papel, assinatura in papeis_e_assinaturas
            if assinatura is not None
        ]

        request.GET._mutable = True
        request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
        request.GET._mutable = False
    return locals()


@login_required()
@rtr()
@atomic()
def assinar_justificativa_visita_modulo_aprendizagem(request, pk, papel):
    obj = get_object_or_404(JustificativaVisitaModuloAprendizagem, pk=pk)
    title = 'Assinar justificativa de decurso de prazo'
    if not obj.pode_assinar(request.user):
        return HttpResponseForbidden()

    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj.assinar(request.user, papel)
        gerar_justificativa_visita_modulo_aprendizagem_decorated = documento(
            tipo_para_verificacao='Justificativa de Decurso de Prazo de Visita de Aprendizagem', forcar_recriacao=True
        )(gerar_justificativa_visita_modulo_aprendizagem)
        retorno = gerar_justificativa_visita_modulo_aprendizagem_decorated(request, pk=pk)
        if obj.relatorio_interno:
            obj.relatorio_interno.delete()
        obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.', close_popup=True)
    return locals()


@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def visualizar_relatorio_visita_estagio(request, pk):
    obj = get_object_or_404(VisitaPraticaProfissional, pk=pk)
    if obj.relatorio_interno:
        response = FileResponse(obj.relatorio_interno.open('rb'), content_type='application/pdf')
        return response

    gerar_relatorio_visita_estagio_decorated = documento(tipo_para_verificacao=None)(gerar_relatorio_visita_estagio)
    retorno = gerar_relatorio_visita_estagio_decorated(request, pk=pk)
    obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
    return retorno


@login_required()
@rtr()
@atomic()
def assinar_relatorio_visita_estagio(request, pk):
    obj = get_object_or_404(VisitaPraticaProfissional, pk=pk)
    title = 'Assinar Relatório de Visita a Organização Concedente'
    if obj.assinatura_orientador:
        return HttpResponseForbidden()
    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        assinatura = AssinaturaEletronica(vinculo=obj.orientador.vinculo)
        assinatura.assinar()
        obj.assinatura_orientador = assinatura
        obj.save()

        gerar_relatorio_visita_estagio_decorated = documento(
            tipo_para_verificacao='Relatório de Visita a Organização Concedente', forcar_recriacao=True
        )(gerar_relatorio_visita_estagio)
        retorno = gerar_relatorio_visita_estagio_decorated(request, pk=pk)
        if obj.relatorio_interno:
            obj.relatorio_interno.delete()
        obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@rtr()
@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def gerar_relatorio_visita_estagio(request, pk):
    obj = get_object_or_404(VisitaPraticaProfissional, pk=pk)
    title = 'Relatório de Visita a Organização Concedente'
    uo = obj.pratica_profissional.aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()
    if obj.assinatura_orientador:
        assinatura = obj.assinatura_orientador
        dados_assinatura = []
        dados_assinatura.append(
            {
                'nome': assinatura.vinculo.pessoa.nome,
                'matricula': assinatura.vinculo.user.username,
                'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                'chave': assinatura.chave,
            }
        )
        request.GET._mutable = True
        request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
        request.GET._mutable = False
    return locals()


@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def visualizar_relatorio_visita_aprendizagem(request, pk):
    obj = get_object_or_404(VisitaAprendizagem, pk=pk)
    if obj.relatorio_interno:
        response = FileResponse(obj.relatorio_interno.open('rb'), content_type='application/pdf')
        return response

    gerar_relatorio_visita_aprendizagem_decorated = documento(tipo_para_verificacao=None)(gerar_relatorio_visita_aprendizagem)
    retorno = gerar_relatorio_visita_aprendizagem_decorated(request, pk=pk)
    obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
    return retorno


@login_required()
@rtr()
@atomic()
def assinar_relatorio_visita_aprendizagem(request, pk):
    obj = get_object_or_404(VisitaAprendizagem, pk=pk)
    title = 'Assinar Relatório de Visita a Organização Concedente'
    if obj.assinatura_orientador:
        return HttpResponseForbidden()

    form = IniciarSessaoAssinaturaSenhaForm(data=request.POST or None, request=request)
    if form.is_valid():
        assinatura = AssinaturaEletronica(vinculo=obj.aprendizagem.orientador.vinculo)
        assinatura.assinar()
        obj.assinatura_orientador = assinatura
        obj.save()

        gerar_relatorio_visita_aprendizagem_decorated = documento(
            tipo_para_verificacao='Relatório de Visita a Organização Concedente', forcar_recriacao=True
        )(gerar_relatorio_visita_aprendizagem)
        retorno = gerar_relatorio_visita_aprendizagem_decorated(request, pk=pk)
        if obj.relatorio_interno:
            obj.relatorio_interno.delete()
        obj.relatorio_interno.save(f'{obj.pk}.pdf', ContentFile(retorno.content))
        return httprr('..', 'Assinatura eletrônica realizada com sucesso.')
    return locals()


@rtr()
@group_required('Professor, Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def gerar_relatorio_visita_aprendizagem(request, pk):
    obj = get_object_or_404(VisitaAprendizagem, pk=pk)
    title = 'Relatório de Visita a Organização Concedente'
    uo = obj.aprendizagem.aprendiz.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()
    if obj.assinatura_orientador:
        assinatura = obj.assinatura_orientador
        dados_assinatura = []
        dados_assinatura.append(
            {
                'nome': assinatura.vinculo.pessoa.nome,
                'matricula': assinatura.vinculo.user.username,
                'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                'chave': assinatura.chave,
            }
        )
        request.GET._mutable = True
        request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
        request.GET._mutable = False
    return locals()


@documento(enumerar_paginas=True)
@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def gerar_termo_compromisso(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)
    title = 'Termo de Compromisso e Plano de Atividades'
    uo = obj.aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    return locals()


@rtr()
@group_required('Coordenador de Estágio, Coordenador de Estágio Sistêmico')
def gerar_termo_compromisso_documentotexto(request, pk):
    obj = get_object_or_404(PraticaProfissional, pk=pk)
    title = 'Termo de Compromisso e Plano de Atividades'

    uo = obj.aluno.curso_campus.diretoria.setor.uo  # uo do aluno

    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')

    # Se não possui supervisor, representante da concedente na PraticaProfissional então retorna mensagem
    if not obj.representante_concedente or not obj.supervisor:
        return httprr(
            obj.get_absolute_url(),
            'Para gerar o termo de compromisso no SUAP é necessário incluir os campos: Representante da Concedente e Supervisor.',
            'warning',
        )

    # Instanciar modelo de documento texto
    modelo = None
    try:
        modelo = ModeloDocumento.objects.get(nome='Termo de Compromisso de Estágio')
    except Exception:
        raise Exception('Não existe o modelo de documento texto com nome de "Termo de Compromisso de Estágio".')

    # Criar documento texto - passa objetos para replace de tags no modelo
    user = request.user

    assunto = title

    setor_dono = get_setor(user)

    # Representante
    if obj.servidor_representante:
        funcao = obj.servidor_representante.funcao_atividade.nome if obj.servidor_representante.funcao_atividade else None
        cargo = obj.servidor_representante.cargo_emprego.nome if obj.servidor_representante.cargo_emprego else None
        representante_cargo = funcao or cargo or 'Cargo não informado'
    else:
        representante_cargo = 'Cargo não informado'

    # Supervisor
    if obj.supervisor:
        supervisor_nome = obj.supervisor.nome
    else:
        supervisor_nome = obj.nome_supervisor

    # Telefone Orientador
    if obj.orientador.vinculo.pessoa.telefones:
        telefone_orientador = obj.orientador.vinculo.pessoa.telefones
    else:
        telefone_orientador = obj.orientador.vinculo.setor.telefones

    def xstr(s):
        if s is not None:
            return str(s)
        return ''

    # Tags do modelo
    # instituição
    variaveis = {}
    variaveis['instituicao_nome'] = xstr(instituicao)
    variaveis['instituicao_endereco'] = xstr(uo.endereco)
    variaveis['unidade_municipio'] = xstr(uo.municipio.nome)
    variaveis['unidade_uf'] = xstr(uo.municipio.uf)
    variaveis['unidade_cep'] = xstr(uo.cep)
    variaveis['unidade_cnpj'] = xstr(uo.cnpj)
    variaveis['unidade_telefone'] = xstr(uo.telefone)
    variaveis['representante_nome'] = xstr(obj.servidor_representante.nome) if obj.servidor_representante else 'Não Informado'
    variaveis['representante_cargo'] = representante_cargo

    # Orientador
    variaveis['orientador_nome'] = xstr(obj.orientador.vinculo.pessoa.nome)
    variaveis['orientador_cpf'] = obj.orientador.vinculo.pessoa.pessoafisica.cpf
    variaveis['orientador_telefone'] = telefone_orientador
    variaveis['orientador_email'] = xstr(obj.orientador.vinculo.email_notificacao)

    if obj.empresa.eh_pessoajuridica():
        # Empresa - Concedente Pessoa Juridica
        variaveis['label_pessoa'] = 'ÓRGÃO OU EMPRESA'
        variaveis['label_pessoa_documento'] = 'CNPJ'
        variaveis['label_razao_social'] = 'RAZÃO SOCIAL'
        variaveis['label_nome_fantasia'] = 'NOME FANTASIA:'
        variaveis['empresa_razao_social'] = xstr(obj.empresa.pessoa.nome)
        variaveis['empresa_nome_fantasia'] = (
            xstr(obj.empresa.pessoa.pessoajuridica.nome_fantasia) if obj.empresa.eh_pessoajuridica() else obj.empresa.pessoa.pessoafisica.nome
        )
        variaveis['empresa_cnpj'] = xstr(obj.empresa.pessoa.pessoajuridica.cnpj) if obj.empresa.eh_pessoajuridica() else ' '
        variaveis['empresa_endereco'] = xstr(obj.logradouro)
        variaveis['empresa_endereco_numero'] = xstr(obj.numero)
        variaveis['empresa_endereco_complemento'] = xstr(obj.complemento)
        variaveis['empresa_bairro'] = xstr(obj.bairro)
        variaveis['empresa_telefone'] = xstr(obj.telefone_supervisor)
        variaveis['empresa_cidade'] = xstr(obj.cidade)
        variaveis['empresa_cep'] = xstr(obj.cep)
        variaveis['empresa_representante'] = (
            obj.representante_concedente.pessoa.nome if obj.representante_concedente else xstr(obj.nome_representante_concedente)
        )
        variaveis['empresa_representante_cargo'] = xstr(obj.cargo_representante_concedente)
        variaveis['empresa_supervisor'] = supervisor_nome
        variaveis['empresa_supervisor_cargo'] = xstr(obj.cargo_supervisor)
        variaveis['empresa_supervisor_email'] = xstr(obj.email_supervisor)
        variaveis['empresa_supervisor_telefone'] = xstr(obj.telefone_supervisor)
        variaveis['empresa_ramo_atividade'] = xstr(obj.ramo_atividade)
    else:
        variaveis['label_pessoa'] = 'PESSOA FÍSICA'
        variaveis['label_razao_social'] = 'NOME'
        variaveis['label_pessoa_documento'] = 'CPF'
        variaveis['label_nome_fantasia'] = ''
        variaveis['empresa_razao_social'] = xstr(obj.empresa.pessoa.pessoafisica.nome)
        variaveis['empresa_nome_fantasia'] = ''
        variaveis['empresa_cnpj'] = obj.empresa.pessoa.pessoafisica.cpf
        variaveis['empresa_endereco'] = xstr(obj.logradouro)
        variaveis['empresa_endereco_numero'] = xstr(obj.numero)
        variaveis['empresa_endereco_complemento'] = xstr(obj.complemento)

    # Estagiario - variáveis
    variaveis['estagiario_nome'] = xstr(obj.aluno.pessoa_fisica.nome)
    variaveis['estagiario_cpf'] = xstr(obj.aluno.pessoa_fisica.cpf)
    variaveis['estagiario_rg'] = xstr(obj.aluno.numero_rg)
    variaveis['estagiario_orgaoexpedidor'] = xstr(obj.aluno.orgao_emissao_rg)
    variaveis['estagiario_endereco'] = xstr(obj.aluno.logradouro)
    variaveis['estagiario_numero'] = xstr(obj.aluno.numero)
    variaveis['estagiario_complemento'] = xstr(obj.aluno.complemento)
    variaveis['estagiario_bairro'] = xstr(obj.aluno.bairro)
    variaveis['estagiario_cidade'] = xstr(obj.aluno.cidade)
    variaveis['estagiario_cep'] = xstr(obj.aluno.cep)
    variaveis['estagiario_data_nascimento'] = xstr(obj.aluno.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y'))
    variaveis['estagiario_telefone'] = xstr(obj.aluno.telefone_principal)
    variaveis['estagiario_email'] = xstr(obj.get_email_aluno())
    variaveis['estagiario_curso'] = xstr(obj.aluno.curso_campus.descricao)
    variaveis['estagiario_periodo'] = xstr(obj.aluno.periodo_atual)
    variaveis['estagiario_nivel'] = xstr(obj.aluno.matriz.nivel_ensino)
    variaveis['estagiario_tem_necessidade_especial'] = 'Sim' if obj.aluno.is_pcd() else 'Não'

    # outras variaveis
    variaveis['duracao_meses'] = obj.get_qtd_meses_e_dias().months
    variaveis['duracao_dias'] = obj.get_qtd_meses_e_dias().days
    variaveis['estagio_data_inicio'] = obj.data_inicio.strftime('%d/%m/%Y')
    variaveis['estagio_data_fim'] = obj.data_prevista_fim.strftime('%d/%m/%Y')
    variaveis['estagio_jornada_dia'] = xstr(obj.ch_diaria)
    variaveis['estagio_jornada_semana'] = xstr(obj.ch_semanal)
    variaveis['estagio_horario'] = xstr(obj.horario)
    variaveis['estagio_valor'] = xstr(obj.valor)
    variaveis['estagio_valor_por_extenso'] = por_extenso(obj.valor)
    variaveis['estagio_auxilio_transporte'] = xstr(obj.auxilio_transporte)
    variaveis['estagio_auxilio_transporte_por_extenso'] = por_extenso(obj.auxilio_transporte)
    variaveis['estagio_outros_beneficios'] = xstr(obj.descricao_outros_beneficios)
    variaveis['estagio_numero_seguro'] = xstr(obj.numero_seguro)
    variaveis['estagio_nome_da_seguradora'] = xstr(obj.nome_da_seguradora)
    variaveis['estagio_cnpj_da_seguradora'] = xstr(obj.cnpj_da_seguradora)
    variaveis['estagio_plano_atividades'] = obj.get_atividades
    variaveis['estagio_testemunha1'] = obj.testemunha1.pessoa.nome if obj.testemunha1 else xstr(obj.testemunha_1)
    variaveis['estagio_testemunha1_cpf'] = obj.testemunha1.pessoa.get_cpf_ou_cnpj() if obj.testemunha1 else ''
    variaveis['estagio_testemunha2'] = obj.testemunha2.pessoa.nome if obj.testemunha2 else xstr(obj.testemunha_2)
    variaveis['estagio_testemunha2_cpf'] = obj.testemunha2.pessoa.get_cpf_ou_cnpj() if obj.testemunha2 else ''
    variaveis['estagio_obrigatorio'] = 'Sim' if obj.obrigatorio else 'Não'

    # Se documento ja existe e é rascunho ou concluido cria novamente
    # Se o documento está assinado ou finalizado já mostra documento e exibe uma mensagem que para gerar um novo deve cancelar o antigo
    # Se o documento está cancelado no momento de criar o novo deve adicionar o vinculo do antigo como retifica e depois adicionar a referencia para o novo

    variaveis_correntes = get_variaveis(
        documento_identificador=None,
        estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
        usuario=user,
        setor_dono=setor_dono,
    )

    def gerar_termo_compromisso():
        try:
            documento_novo = DocumentoTexto()
            documento_novo.setor_dono = setor_dono
            documento_novo.usuario_criacao = user
            documento_novo.assunto = assunto
            documento_novo.data_ultima_modificacao = get_datetime_now()
            documento_novo.usuario_ultima_modificacao = user
            documento_novo.modelo = modelo
            documento_novo.nivel_acesso = Documento.NIVEL_ACESSO_RESTRITO
            documento_novo.hipotese_legal = HipoteseLegal.objects.get(descricao='Informação Pessoal')
            documento_novo.save()

            variaveis_correntes.update(variaveis)
            documento_novo.corpo = processar_template_ckeditor(texto=modelo.corpo_padrao, variaveis=variaveis_correntes)

            documento_novo.save()

            obj.termo_compromisso_documentotexto = documento_novo
            obj.save()

            return documento_novo
        except Exception as e:
            raise e

    if not obj.termo_compromisso_documentotexto:
        documento_novo = gerar_termo_compromisso()
        url = documento_novo.get_absolute_url()
        msg = 'Termo de compromisso gerado com sucesso!'
    elif obj.termo_compromisso_documentotexto.estah_em_rascunho or obj.termo_compromisso_documentotexto.estah_concluido:
        documento_novo = obj.termo_compromisso_documentotexto
        url = documento_novo.get_absolute_url()
        variaveis_correntes.update(variaveis)
        documento_novo.corpo = processar_template_ckeditor(texto=modelo.corpo_padrao, variaveis=variaveis_correntes)
        if obj.termo_compromisso_documentotexto.estah_concluido:
            documento_novo.editar_documento()
        documento_novo.save()
        msg = 'Termo de compromisso atualizado com sucesso!'
    elif obj.termo_compromisso_documentotexto.estah_assinado or obj.termo_compromisso_documentotexto.estah_finalizado:
        documento_novo = obj.termo_compromisso_documentotexto
        url = documento_novo.get_absolute_url()
        msg = f'Este documento está na situação {documento_novo.get_status()} que não permite edição. Para gerar um novo termo favor cancelar este documento: {documento_novo.identificador}'
    elif obj.termo_compromisso_documentotexto.estah_cancelado:
        documento_antigo = obj.termo_compromisso_documentotexto
        documento_novo = gerar_termo_compromisso()
        url = documento_novo.get_absolute_url()
        # tipo vinculo - retificação
        tipo_vinculo = TipoVinculoDocumento.objects.get(descricao='Retificação')
        # Vincula documentos
        vinculo_documentos = VinculoDocumentoTexto()
        vinculo_documentos.tipo_vinculo_documento = tipo_vinculo
        vinculo_documentos.documento_texto_base = documento_novo
        vinculo_documentos.documento_texto_alvo = documento_antigo
        vinculo_documentos.usuario_criacao = user
        vinculo_documentos.save()
        # Atualiza referencia do obj PraticaProfissional
        obj.termo_compromisso_documentotexto = documento_novo
        obj.save()
        msg = 'Termo de compromisso substituído com sucesso!'
    else:
        url = f'/estagios/pratica_profissional/{obj.pk}/'
        msg = 'A situação atual do estágio não permite a geração do termo de compromisso'

    return httprr(url, msg)


@login_required()
def get_json_dados_concedente(request, id_concedente):
    vinculo = get_object_or_404(Vinculo, pk=id_concedente)
    concedente = vinculo.pessoa

    dados_concedente = {
        'endereco': {
            'cidade': '',
            'logradouro': '',
            'numero': '',
            'complemento': '',
            'bairro': '',
            'cep': '',
        }
    }

    if concedente.pessoaendereco:
        cidade = Cidade.get_cidade_by_municipio(concedente.pessoaendereco.municipio)

        if cidade:
            estado = Estado.objects.get(pk=cidade.estado_id)
            cidade = model_to_dict(cidade, fields=['id', 'nome'])
            cidade['estado'] = model_to_dict(estado)
            cidade['estado']['sigla'] = estado.get_sigla()

        dados_concedente['endereco']['cidade'] = cidade
        dados_concedente['endereco']['logradouro'] = concedente.pessoaendereco.logradouro
        dados_concedente['endereco']['numero'] = concedente.pessoaendereco.numero
        dados_concedente['endereco']['complemento'] = concedente.pessoaendereco.complemento
        dados_concedente['endereco']['bairro'] = concedente.pessoaendereco.bairro
        dados_concedente['endereco']['cep'] = concedente.pessoaendereco.cep

    return JsonResponse(dados_concedente)


@login_required()
def get_json_dados_empresa(request, empresa_id):
    concedente = get_object_or_404(PessoaJuridica, pk=empresa_id)

    dados_concedente = {
        'endereco': {
            'cidade': '',
            'logradouro': '',
            'numero': '',
            'complemento': '',
            'bairro': '',
            'cep': '',
        }
    }

    if concedente.pessoaendereco:
        cidade = Cidade.get_cidade_by_municipio(concedente.pessoaendereco.municipio)

        if cidade:
            estado = Estado.objects.get(pk=cidade.estado_id)
            cidade = model_to_dict(cidade, fields=['id', 'nome'])
            cidade['estado'] = model_to_dict(estado)
            cidade['estado']['sigla'] = estado.get_sigla()

        dados_concedente['endereco']['cidade'] = cidade
        dados_concedente['endereco']['logradouro'] = concedente.pessoaendereco.logradouro
        dados_concedente['endereco']['numero'] = concedente.pessoaendereco.numero
        dados_concedente['endereco']['complemento'] = concedente.pessoaendereco.complemento
        dados_concedente['endereco']['bairro'] = concedente.pessoaendereco.bairro
        dados_concedente['endereco']['cep'] = concedente.pessoaendereco.cep

    return JsonResponse(dados_concedente)


@documento('Declaração de Estágio', enumerar_paginas=False, modelo='estagios.praticaprofissional')
@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def emitir_declaracao_participacao_estagio_pdf(self, pk):
    participacao = get_object_or_404(PraticaProfissional, pk=pk)
    if not participacao.pode_emitir_declaracao_de_participacao():
        return httprr('/', 'Você não tem permissão para ver isso.', 'error')
    participante = participacao.aluno
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'

    cpf = participante.pessoa_fisica.cpf
    rg = participante.pessoa_fisica.rg
    rg_orgao = participante.pessoa_fisica.rg_orgao
    rg_uf = participante.pessoa_fisica.rg_uf
    logradouro = participante.logradouro
    bairro = participante.bairro
    cidade = participante.cidade
    nome_empresa = (
        hasattr(participacao.empresa.relacionamento, 'nome_fantasia')
        and participacao.empresa.relacionamento.nome_fantasia
        or participacao.empresa.nome
    )
    hoje = datetime.datetime.now()
    meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    mes = meses[hoje.month - 1]
    return locals()


@documento('Declaração de Atividades de Aprendizagem', enumerar_paginas=False, modelo='estagios.aprendizagem')
@rtr()
@permission_required('projetos.pode_visualizar_projeto')
def emitir_declaracao_participacao_aprendizagem_pdf(self, pk):
    participacao = get_object_or_404(Aprendizagem, pk=pk)
    if not participacao.pode_emitir_declaracao_de_participacao():
        return httprr('/', 'Você não tem permissão para ver isso.', 'error')
    participante = participacao.aprendiz
    nome_instituicao = (
        Configuracao.get_valor_por_chave('comum', 'instituicao') or 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'
    )
    nome_pro_reitoria = Configuracao.get_valor_por_chave('projetos', 'nome_proex') or 'Pró-Reitoria de Extensão'

    cpf = participante.pessoa_fisica.cpf
    rg = participante.pessoa_fisica.rg
    rg_orgao = participante.pessoa_fisica.rg_orgao
    rg_uf = participante.pessoa_fisica.rg_uf
    logradouro = participante.logradouro
    bairro = participante.bairro
    cidade = participante.cidade
    nome_empresa = participacao.empresa.nome_fantasia or participacao.empresa.nome
    ocupacao = participacao.ocupacao
    hoje = datetime.datetime.now()
    mes = Meses.get_mes(hoje.month)
    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_erros(request, data, datahora_inicio, datahora_fim):
    usuario_id = request.user.id

    filters_erros_abertos = {}
    if datahora_inicio:
        filters_erros_abertos['action_time__gte'] = datahora_inicio
    if datahora_fim:
        filters_erros_abertos['action_time__lte'] = datahora_fim
    from django.apps import apps
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    logs_estagios = LogEntry.objects.filter(
        user_id=usuario_id, content_type=ContentType.objects.get_for_model(apps.get_model('estagios.praticaprofissional')), **filters_erros_abertos
    )
    for log in logs_estagios.order_by('action_time'):
        estagio = PraticaProfissional.objects.filter(id=log.object_id).first()
        if estagio:
            data.append(
                (
                    'Estágios/Aprendizagens',
                    'Cadastro/Edição de Estágios',
                    estagio,
                    f'em {log.action_time.strftime("%d/%m/%Y %H:%M")}',
                    f'/estagios/pratica_profissional/{estagio.id}/',
                )
            )
    logs_aprendizagens = LogEntry.objects.filter(
        user_id=usuario_id, content_type=ContentType.objects.get_for_model(apps.get_model('estagios.aprendizagem')), **filters_erros_abertos
    )
    for log in logs_aprendizagens.order_by('action_time'):
        aprendizagem = Aprendizagem.objects.filter(id=log.object_id).first()
        if aprendizagem:
            data.append(
                (
                    'Estágios/Aprendizagens',
                    'Cadastro/Edição de Aprendizagens',
                    aprendizagem,
                    f'em {log.action_time.strftime("%d/%m/%Y %H:%M")}',
                    f'/estagios/aprendizagem/{aprendizagem.id}/',
                )
            )
