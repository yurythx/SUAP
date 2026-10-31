import collections
import datetime
import uuid
from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, DecimalField, Exists, ExpressionWrapper, F, Min, OuterRef, Q, QuerySet, Subquery, Sum
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django_tables2.columns.base import Column

from ae.models import Participacao
from comum.models import APIExterna, Configuracao, PrestadorServico, User
from comum.models import Vinculo as VinculoPessoa
from comum.utils import get_sigla_reitoria, get_uo
from djtools import layout
from djtools.html.calendarios import CalendarioPlus
from djtools.html.graficos import BarChart, Chart, GroupedColumnChart, PieChart
from djtools.tables import get_table
from djtools.templatetags.filters import format_, in_group
from djtools.utils import documento, group_required, httprr, ids_da_query, permission_required, rtr, send_notification
from edu.models import Aluno, CursoCampus, Modalidade, SituacaoMatricula
from ponto.models import Frequencia
from rh.models import Funcao, PessoaExterna, PessoaFisica, Servidor, UnidadeOrganizacional
from saude import tasks
from saude.forms import (
    AcuidadeVisualForm,
    AdicionarCartaoVacinalForm,
    AdicionarIntervencaoOdontoForm,
    AdicionarVacinaForm,
    AnamneseFisioterapiaForm,
    AnamneseForm,
    AnamnesePsicologiaForm,
    AnexoProntuarioForm,
    AnexoPsicologiaForm,
    AnotacaoInterdisciplinarForm,
    AntecedentesFamiliaresForm,
    AntropometriaForm,
    AtendimentoMultidisciplinarForm,
    AtendimentoNutricaoAvalGastroForm,
    AtendimentoNutricaoCategoriaTrabalhoForm,
    AtendimentoNutricaoCondutaForm,
    AtendimentoNutricaoConsumoForm,
    AtendimentoNutricaoDadosAlimentacaoForm,
    AtendimentoNutricaoDiagnosticoForm,
    AtendimentoNutricaoMotivoForm,
    AtendimentoNutricaoRestricaoAlimentarForm,
    AtendimentoPsicologicoForm,
    AtividadeGrupoForm,
    AvaliarAtendimentoFisioterapiaForm,
    BuscaProntuarioForm,
    CadastroCartaoVacinalCovidForm,
    CancelarAtendimentoForm,
    CartaoSUSAlunoForm,
    CartaoVacinalForm,
    CondutaFisioterapiaForm,
    CondutaMedicaForm,
    DataHoraAtendimentoPsicologicoForm,
    DesenvolvimentoPessoalForm,
    EditarExameLaboratorialForm,
    EncaminhamentoFisioterapiaForm,
    EnviarMensagemForm,
    EstatisticasAtendimentosForm,
    ExameEstomatologicoForm,
    ExameFisicoForm,
    ExameImagemForm,
    ExameLaboratorialForm,
    ExamePeriodontalForm,
    FecharAtendimentoForm,
    FiltrarAtendimentosForm,
    FiltroEstatisticaGeralForm,
    GetConfirmarHorarioAtendimentoForm,
    HabitosDeVidaForm,
    HipoteseDiagnosticaForm,
    HipoteseDiagnosticaModelForm,
    HipoteseFisioterapiaForm,
    HorarioAtendimentoForm,
    IndicarProcedimentoForm,
    InformacaoAdicionalForm,
    IntervencaoEnfermagemForm,
    IntervencaoFisioterapiaForm,
    JustificativaCancelamentoHorarioForm,
    JustificativaCancelamentoHorariosForm,
    JustificativaIndeferirPassaporteForm,
    ListaAlunosForm,
    MarcadorConsumoAlimentarForm,
    MensagemVacinaAtrasadaForm,
    MonitorarNotificacaoForm,
    MotivoForm,
    ObsRegistroExecucaoForm,
    OdontogramaForm,
    PacienteAgendamentoForm,
    PassaporteVacinalCovidForm,
    PercepcaoSaudeBucalForm,
    PessoaExternaForm,
    PlanoAlimentarForm,
    PreencherDocumentoForm,
    ProcedimentoAtendimentoFisioterapiaForm,
    ProcedimentoOdontologicoForm,
    ProcessoSaudeDoencaForm,
    RegistrarPrevisaoVacinacaoForm,
    RegistrarVacinacaoForm,
    RelatorioAtendimentoForm,
    RelatorioAvaliacaoBiomedicaForm,
    RelatorioNotificacaoCovidForm,
    RelatorioOdontologicoForm,
    RelatorioPassaporteCovidChefiaForm,
    RelatorioPassaporteCovidForm,
    RetornoFisioterapiaForm,
    SinaisVitaisForm,
    TipoConsultaForm,
    TipoDocumentoForm,
    TipoVacinaForm,
    ValoresExameLaboratorialForm,
    VerificaPassaporteForm,
    NutricaoAlimentacaoForm,
    EncaminhamentoPacienteForm,
    FinalizarEncaminhamentoPacienteForm,
    SaudeMentalForm,
    AcompanhamentoAnotacoesInterdisciplinaresForm,
)
from saude.models import (
    AcuidadeVisual,
    Anamnese,
    AnamnesePsicologia,
    AnexoProntuario,
    AnexoPsicologia,
    AnotacaoInterdisciplinar,
    AntecedentesFamiliares,
    Antropometria,
    Atendimento,
    AtendimentoEspecialidade,
    AtendimentoFisioterapia,
    AtendimentoMultidisciplinar,
    AtendimentoNutricao,
    AtendimentoPsicologia,
    AtividadeGrupo,
    BloqueioAtendimentoSaude,
    CartaoVacinal,
    CategoriaExameLaboratorial,
    CondutaMedica,
    ConsumoNutricao,
    DesenvolvimentoPessoal,
    DificuldadeOral,
    DocumentoProntuario,
    EncaminhamentoFisioterapia,
    Especialidades,
    ExameEstomatologico,
    ExameFisico,
    ExameImagem,
    ExameLaboratorial,
    ExamePeriodontal,
    FrequenciaAlimentarNutricao,
    FrequenciaPraticaAlimentar,
    HabitosDeVida,
    HipoteseDiagnostica,
    HistoricoCartaoVacinal,
    HistoricoImportacaoRNVacina,
    HistoricoValidacaoPassaporte,
    HorarioAtendimento,
    InformacaoAdicional,
    IntervencaoEnfermagem,
    IntervencaoFisioterapia,
    MetaAcaoEducativa,
    MonitoramentoCovid,
    Motivo,
    NotificacaoCovid,
    Odontograma,
    OpcaoRespostaMarcadorNutricao,
    PassaporteVacinalCovid,
    PercepcaoSaudeBucal,
    PerguntaMarcadorNutricao,
    PlanoAlimentar,
    PlanoTratamento,
    ProcedimentoAtendimentoFisioterapia,
    ProcedimentoOdontologia,
    ProcedimentoOdontologico,
    ProcessoSaudeDoenca,
    Prontuario,
    ReceitaNutricional,
    RegistroPresencaAtividadeGrupo,
    RespostaMarcadorNutricao,
    ResultadoProcedimento,
    ResultadoTesteCovid,
    SinaisVitais,
    SituacaoAtendimento,
    SituacaoClinica,
    TipoAtendimento,
    TipoConsultaOdontologia,
    TipoExameLaboratorial,
    Vacina,
    ValidadorIntercampi,
    ValorExameLaboratorial,
    Vinculo,
    NutricaoAlimentacao,
    SaudeMental,
    EncaminhamentoPaciente,
    InteressadoAnotacaoInterdisciplinar,
)
from saude.services.importacao_rnvacina import importar_vacinas_rnvacina


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if eh_do_grupo_medico_enf(request.user):
        prontuarios_encaminhados = Atendimento.objects.filter(
            condutamedica__encaminhado_enfermagem=True, condutamedica__atendido=False, usuario_aberto__vinculo__setor__uo=get_uo(request.user)
        ).count()
        if prontuarios_encaminhados:
            pendencias.append(
                {
                    'titulo': f'Atendimento{pluralize(prontuarios_encaminhados)} encaminhado{pluralize(prontuarios_encaminhados)} para Enfermagem',
                    'subtitulo': 'aguardando intervenção',
                    'qtd': prontuarios_encaminhados,
                    'url': '/saude/prontuarios/?tab=atendimento_encaminhado_enfermagem',
                }
            )

    if request.user.has_group_cached(Especialidades.GRUPOS, ignore_groups_if_superuser=False):
        hoje = datetime.datetime.now()
        acoes_educativas_pendentes = AtividadeGrupo.objects.filter(
            meta__isnull=False, tema__isnull=True, uo=get_uo(request.user), data_termino__lt=hoje
        )
        acoes_educativas_pendentes = acoes_educativas_pendentes.filter(Q(cadastrado_por=request.user) | Q(cadastrado_por__isnull=True))

        if acoes_educativas_pendentes.exists():
            qtd = acoes_educativas_pendentes.count()
            pendencias.append(
                {
                    'titulo': f'Aç{pluralize(qtd, "ão,ões")} Educativa{pluralize(qtd)}',
                    'subtitulo': 'a registrar execução',
                    'qtd': qtd,
                    'url': f'/saude/visualizar_acoes_educativas/{acoes_educativas_pendentes[0].meta_id}/',
                }
            )

    return pendencias


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    usuario_logado = request.user
    especialidade = Especialidades(request.user)
    eh_dentista = especialidade.is_odontologo()
    eh_psicologo = especialidade.is_psicologo()
    eh_nutricionista = especialidade.is_nutricionista()
    eh_fisioterapeuta = especialidade.is_fisioterapeuta()

    qtd_atendimentos_saude_abertos = 0
    if eh_do_grupo_medico_enf(request.user):
        qtd_atendimentos_saude_abertos = Atendimento.objects.filter(
            tipo=TipoAtendimento.ENFERMAGEM_MEDICO, usuario_aberto__vinculo__setor__uo=get_uo(usuario_logado), situacao=SituacaoAtendimento.ABERTO
        ).count()
    elif eh_dentista or eh_psicologo or eh_nutricionista or eh_fisioterapeuta:
        qtd_atendimentos_saude_abertos = Atendimento.objects.filter(
            tipo__in=[TipoAtendimento.ODONTOLOGICO, TipoAtendimento.PSICOLOGICO, TipoAtendimento.NUTRICIONAL, TipoAtendimento.FISIOTERAPIA],
            usuario_aberto=usuario_logado,
            situacao=SituacaoAtendimento.ABERTO,
        ).count()
    if qtd_atendimentos_saude_abertos:
        pendencias.append(
            {
                'titulo': f'Atendimento{pluralize(qtd_atendimentos_saude_abertos)} aberto{pluralize(qtd_atendimentos_saude_abertos)}',
                'subtitulo': 'a retomar',
                'qtd': qtd_atendimentos_saude_abertos,
                'url': '/saude/prontuarios/?tab=atendimentos_abertos',
            }
        )
    tem_anotacao_pendente = InteressadoAnotacaoInterdisciplinar.objects.filter(lido_em=None, interessado=usuario_logado.get_vinculo()).first()
    if tem_anotacao_pendente:
        pendencias.append(
            {
                'titulo': 'Anotação interdisciplinar',
                'subtitulo': 'pendente de registro de leitura',
                'url': '/saude/anotacoes_pendentes/',
            }
        )
    return pendencias


@layout.info()
def index_infos(request):
    """Alerta o usuário logado sobre vacinas atrasadas ou agendadas nos próximos 15 dias.

    Consulta uma única vez o ``CartaoVacinal`` do prontuário do vínculo,
    consolidando em um ``aggregate`` as contagens das duas situações.

    Args:
        request: requisição HTTP usada para obter o vínculo do usuário.

    Returns:
        list[dict]: avisos de vacinas atrasadas e/ou próximas do prazo;
        lista vazia quando não há prontuário ou nenhuma vacina nessas situações.
    """
    infos = []

    hoje = datetime.datetime.now()
    vinculo = request.user.get_vinculo()
    prontuario = Prontuario.objects.filter(vinculo=vinculo).first()
    if prontuario:
        agregados = CartaoVacinal.objects.filter(prontuario=prontuario.id, data_prevista__isnull=False, data_vacinacao__isnull=True).aggregate(
            qtd_atrasada=Count('id', filter=Q(data_prevista__lt=hoje)),
            qtd_agendada=Count('id', filter=Q(data_prevista__gt=hoje, data_prevista__lte=hoje + datetime.timedelta(days=15))),
        )
        qtd_vacina_atrasada = agregados['qtd_atrasada']
        qtd_vacina_agendada = agregados['qtd_agendada']
        if qtd_vacina_atrasada:
            infos.append(
                {
                    'titulo': 'Você possui vacina{plural} atrasada{plural}. Procure o Setor de Saúde do seu campus.'.format(
                        plural=pluralize(qtd_vacina_atrasada)
                    )
                }
            )
        if qtd_vacina_agendada:
            infos.append(
                {
                    'titulo': 'Você tem vacinaç{} agendada{} para os próximos 15 dias.'.format(
                        pluralize(qtd_vacina_agendada, 'ão,ões'), pluralize(qtd_vacina_agendada)
                    )
                }
            )

    return infos


@layout.quadro('Notificações de Síndromes Gripais e COVID-19', icone='heartbeat', pode_esconder=True)
def index_quadros_notificacoes_covid(quadro, request):
    if request.user.get_vinculo().eh_usuario_externo():
        return quadro
    utiliza_passaporte_vacinal = Configuracao.get_valor_por_chave('saude', 'utiliza_passaporte_vacinal')
    if utiliza_passaporte_vacinal:
        quadro.add_item(layout.ItemAcessoRapido(titulo='Notificar', url='/saude/notificar_caso_covid/', icone='plus', classe='success'))
        quadro.add_item(layout.ItemAcessoRapido(titulo='Monitoramento', url='/saude/relatorio_notificacao_covid/', icone='bars'))
    return quadro


@layout.quadro('Passaporte Vacinal', icone='heartbeat', pode_esconder=True)
def index_quadros_passaporte_vacinal(quadro, request):
    utiliza_passaporte_vacinal = Configuracao.get_valor_por_chave('saude', 'utiliza_passaporte_vacinal')
    if utiliza_passaporte_vacinal:
        if request.user.has_group_cached('Chefe de Setor'):
            historico_funcao = (
                request.user.get_relacionamento()
                .historico_funcao()
                .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False)
            )
            if historico_funcao.exists():
                setor = historico_funcao.latest('id').setor_suap
                servidores_do_setor = Servidor.objects.ativos().filter(setor_exercicio__in=setor.descendentes)
                qtd_aguardando_avaliacao = PassaporteVacinalCovid.objects.filter(
                    vinculo__in=servidores_do_setor.values_list('vinculos', flat=True), situacao_passaporte=PassaporteVacinalCovid.INVALIDO
                )
                if qtd_aguardando_avaliacao.exists():
                    qtd = qtd_aguardando_avaliacao.count()
                    quadro.add_item(
                        layout.ItemContador(
                            titulo='Servido{} sob a sua chefia'.format(pluralize(qtd, 'r,res')),
                            subtitulo='com Passaporte Vacinal inválido',
                            qtd=qtd,
                            url='/saude/relatorio_passaporte_vacinal_chefia/?situacao=Inválido&situacao_declaracao=&categoria=&uo=&faixa_etaria=&relatoriopassaportecovidchefia_form=Aguarde...',
                        )
                    )
                data_inicio_checagem_ponto = Configuracao.get_valor_por_chave('saude', 'data_checagem_ponto')
                if data_inicio_checagem_ponto:
                    registros_frequencia = Frequencia.objects.filter(
                        horario__gt=data_inicio_checagem_ponto, vinculo__in=qtd_aguardando_avaliacao.values_list('vinculo', flat=True)
                    ).distinct('vinculo')
                    if servidores_do_setor.exists() and registros_frequencia.exists():
                        qtd = registros_frequencia.count()
                        quadro.add_item(
                            layout.ItemContador(
                                titulo='Servido{} sob a sua chefia'.format(pluralize(qtd, 'r,res')),
                                subtitulo='registraram frequência com Passaporte Vacinal inválido',
                                qtd=qtd,
                                url='/saude/relatorio_passaporte_vacinal_chefia/?situacao=&situacao_declaracao=&categoria=&uo=&faixa_etaria=&registrou_frequencia=on&relatoriopassaportecovidchefia_form=Aguarde...',
                            )
                        )

        if request.user.has_group_cached('Coordenador de Curso'):
            cursos = CursoCampus.objects.filter(coordenador=request.user.get_vinculo()) | CursoCampus.objects.filter(
                coordenador_2=request.user.get_vinculo()
            )
            alunos = Aluno.ativos.filter(curso_campus__in=cursos.values_list('id', flat=True))
            qtd_aguardando_avaliacao = PassaporteVacinalCovid.objects.filter(
                vinculo__in=alunos.values_list('vinculos', flat=True), situacao_passaporte=PassaporteVacinalCovid.INVALIDO
            )
            if qtd_aguardando_avaliacao.exists():
                qtd = qtd_aguardando_avaliacao.count()
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Aluno{pluralize(qtd)} de cursos sob sua coordenação',
                        subtitulo='com Passaporte Vacinal inválido',
                        qtd=qtd,
                        url=f'/saude/relatorio_passaporte_vacinal/?situacao=Inválido&situacao_declaracao=&categoria=1&uo=14&curso={cursos[0].id}&turma=&faixa_etaria=&relatoriopassaportecovid_form=Aguarde...',
                    )
                )

        if request.user.has_group_cached(['Fiscal de Contrato', 'Gerenciador de Prestador de Serviço']):
            uo_user = get_uo(request.user)
            prestadores = PrestadorServico.objects.filter(
                setor__uo=uo_user, ativo=True, pessoa_fisica__cpf__isnull=False, ocupacaoprestador__isnull=False
            )
            qtd_aguardando_avaliacao = PassaporteVacinalCovid.objects.filter(
                vinculo__in=prestadores.values_list('vinculos', flat=True), situacao_passaporte=PassaporteVacinalCovid.INVALIDO
            )
            if uo_user and qtd_aguardando_avaliacao.exists():
                qtd = qtd_aguardando_avaliacao.count()
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Prestador{} de serviço'.format(pluralize(qtd, 'es')),
                        subtitulo='com Passaporte Vacinal inválido',
                        qtd=qtd,
                        url=f'/saude/relatorio_passaporte_vacinal/?situacao=Inválido&situacao_declaracao=&categoria=3&uo={uo_user.id}&curso=&turma=&faixa_etaria=&relatoriopassaportecovid_form=Aguarde...',
                    )
                )

    return quadro


@layout.quadro('Saúde', icone='heartbeat')
def index_quadros(quadro, request):
    if request.user.has_group_cached(Especialidades.GRUPOS, ignore_groups_if_superuser=False):
        hoje = datetime.datetime.now()
        prazo_vinte_dias = hoje + datetime.timedelta(days=20)
        acoes_educativas_em_aberto = AtividadeGrupo.objects.filter(
            meta__isnull=False, tema__isnull=True, uo=get_uo(request.user), data_inicio__gt=hoje, data_inicio__lte=prazo_vinte_dias
        )

        if acoes_educativas_em_aberto.exists():
            qtd = acoes_educativas_em_aberto.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo='Aç{} Educativa{}'.format(pluralize(qtd, 'ão,ões'), pluralize(qtd)),
                    subtitulo=f'Prevista{pluralize(qtd)} para os próximos 20 dias',
                    qtd=qtd,
                    url=f'/saude/visualizar_acoes_educativas/{acoes_educativas_em_aberto[0].meta_id}/',
                )
            )

    return quadro


def tem_permissao_acesso_atendimento_medico(user):
    if not user.has_group_cached(Especialidades.GRUPOS, ignore_groups_if_superuser=True):
        raise PermissionDenied


def tem_permissao(atendimento, request):
    if not (atendimento.usuario_aberto == request.user):
        raise PermissionDenied


def eh_do_grupo_medico_enf(user):
    return user.has_group_cached(Especialidades.GRUPOS_ATENDIMENTO_MEDICO_ENF, ignore_groups_if_superuser=False)


def eh_do_grupo_enf(user):
    return user.has_group_cached(Especialidades.GRUPOS_ATENDIMENTO_ENF, ignore_groups_if_superuser=False)


def nao_possui_dados_estatisticos(lista):
    return bool(len(lista) == 1 and lista[0]['qtd'] == 0)


def pode_alterar_atendimento(atendimento, request):
    pode_fechar = False
    if (
        atendimento.tipo == TipoAtendimento.ODONTOLOGICO
        and request.user.has_group_cached([Especialidades.ODONTOLOGO, Especialidades.TECNICO_SAUDE_BUCAL])
        or atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO
        and request.user.has_group_cached(Especialidades.GRUPOS_ATENDIMENTO_MEDICO_ENF)
        or atendimento.tipo == TipoAtendimento.AVALIACAO_BIOMEDICA
        and request.user.has_group_cached(Especialidades.GRUPOS)
        or atendimento.tipo == TipoAtendimento.PSICOLOGICO
        and atendimento.usuario_aberto == request.user
        or atendimento.tipo == TipoAtendimento.NUTRICIONAL
        and atendimento.usuario_aberto == request.user
        or atendimento.tipo == TipoAtendimento.FISIOTERAPIA
        and atendimento.usuario_aberto == request.user
        or atendimento.tipo == TipoAtendimento.MULTIDISCIPLINAR
        and atendimento.usuario_aberto == request.user
    ):
        pode_fechar = True
    return pode_fechar


def get_ids_uos(user):
    uo_ids = []
    if user.eh_aluno:
        aluno = user.get_relacionamento()
        if aluno.curso_campus.diretoria.ead and aluno.polo and aluno.polo.campus_atendimento:
            uo_ids.append(aluno.polo.campus_atendimento_id)
    else:
        if user.eh_servidor:
            servidor = user.get_relacionamento()
            setores = ()
            if servidor.setor_lotacao:
                if servidor.setor_lotacao.uo.equivalente:
                    setores += (servidor.setor_lotacao.uo.equivalente.id,)
                else:
                    setores += (servidor.setor_lotacao.uo_id,)
            if servidor.setor_exercicio:
                setores += (servidor.setor_exercicio.uo_id,)
            if servidor.setor:
                setores += (servidor.setor.uo_id,)
            for setor in servidor.setores_adicionais.all():
                setores += (setor.uo_id,)
            uos_atendimento = UnidadeOrganizacional.objects.filter(id__in=setores)
        else:
            uos_atendimento = UnidadeOrganizacional.objects.filter(
                id__in=HorarioAtendimento.objects.filter(cadastrado_por_vinculo=user.get_vinculo()).values_list('campus', flat=True)
            )
        for uo in uos_atendimento:
            uo_ids.append(uo.id)
    uo_ids.append(get_uo(user).id)
    return uo_ids


def pode_validar_passaporte(request, passaporte):
    eh_intercampi = ValidadorIntercampi.objects.filter(vinculo=request.user.get_vinculo(), ativo=True)
    return (
        (passaporte.uo == get_uo(request.user))
        or request.user.has_group_cached('Validador de Passaporte Vacinal Sistêmico')
        or (eh_intercampi.exists() and passaporte.uo.id in eh_intercampi.values_list('campi', flat=True))
    )


@rtr()
@group_required([*Especialidades.GRUPOS_PRONTUARIO, 'Assistente Social'])
def prontuarios(request):
    title = 'Prontuários'

    form = BuscaProntuarioForm(request.GET or None)

    pessoas = None
    vinculo = None
    uo_atual = get_uo(request.user)
    eh_assistente_social = request.user.has_group_cached('Assistente Social')

    atendimentos_multidisciplinares_abertos = Atendimento.objects.filter(
        tipo=TipoAtendimento.MULTIDISCIPLINAR, usuario_aberto__vinculo__setor__uo=uo_atual, situacao=SituacaoAtendimento.ABERTO
    ).order_by('prontuario__vinculo__pessoa__nome')

    prontuarios_encaminhados = Atendimento.objects.filter(
        condutamedica__encaminhado_enfermagem=True, condutamedica__atendido=False, usuario_aberto__vinculo__setor__uo=uo_atual
    ).order_by('prontuario__vinculo__pessoa__nome')

    prontuarios_encaminhados_fisioterapia = Atendimento.objects.filter(
        condutamedica__encaminhado_fisioterapia=True, condutamedica__atendido_fisioterapia=False, usuario_aberto__vinculo__setor__uo=uo_atual
    ).order_by('prontuario__vinculo__pessoa__nome')

    atendimentos_fisioterapia_encaminhados = Atendimento.objects.filter(
        id__in=AtendimentoFisioterapia.objects.filter(encaminhado_medico=True).values_list('atendimento', flat=True),
        usuario_aberto__vinculo__setor__uo=uo_atual,
    ).order_by('prontuario__vinculo__pessoa__nome')

    pode_criar_atendimento = eh_do_grupo_medico_enf(request.user)
    eh_enfermagem = eh_do_grupo_enf(request.user)
    especialidade = Especialidades(request.user)
    eh_medico = especialidade.is_medico()
    eh_dentista = especialidade.is_odontologo()
    eh_psicologo = especialidade.is_psicologo()
    eh_medico = especialidade.is_medico()
    eh_nutricionista = especialidade.is_nutricionista()
    eh_enfermeiro = especialidade.is_enfermeiro()
    eh_fisioterapeuta = especialidade.is_fisioterapeuta()

    atendimento_odonto_encaminhado = False
    if pode_criar_atendimento:
        prontuarios_abertos = Atendimento.objects.filter(
            tipo=TipoAtendimento.ENFERMAGEM_MEDICO, usuario_aberto__vinculo__setor__uo=uo_atual, situacao=SituacaoAtendimento.ABERTO
        ).order_by('prontuario__vinculo__pessoa__nome')
        if eh_enfermagem:
            atendimento_odonto_encaminhado = Atendimento.objects.filter(
                tipo=TipoAtendimento.ODONTOLOGICO,
                odontograma__encaminhado_enfermagem=True,
                odontograma__atendido=False,
                usuario_aberto__vinculo__setor__uo=uo_atual,
            ).order_by('prontuario__vinculo__pessoa__nome')
    elif eh_dentista:
        prontuarios_abertos = Atendimento.objects.filter(
            tipo=TipoAtendimento.ODONTOLOGICO, usuario_aberto=request.user, situacao=SituacaoAtendimento.ABERTO
        ).order_by('prontuario__vinculo__pessoa__nome')
    elif eh_psicologo:
        prontuarios_abertos = Atendimento.objects.filter(
            tipo=TipoAtendimento.PSICOLOGICO, usuario_aberto=request.user, situacao=SituacaoAtendimento.ABERTO
        ).order_by('prontuario__vinculo__pessoa__nome')
    elif eh_nutricionista:
        prontuarios_abertos = Atendimento.objects.filter(
            tipo=TipoAtendimento.NUTRICIONAL, usuario_aberto=request.user, situacao=SituacaoAtendimento.ABERTO
        ).order_by('prontuario__vinculo__pessoa__nome')
    elif eh_fisioterapeuta:
        prontuarios_abertos = Atendimento.objects.filter(
            tipo=TipoAtendimento.FISIOTERAPIA, usuario_aberto=request.user, situacao=SituacaoAtendimento.ABERTO
        ).order_by('prontuario__vinculo__pessoa__nome')

    avaliacoes_biomedicas_abertas = Atendimento.objects.filter(
        tipo=TipoAtendimento.AVALIACAO_BIOMEDICA, situacao=SituacaoAtendimento.ABERTO, aluno__curso_campus__diretoria__setor__uo=uo_atual
    )
    avaliacoes_biomedicas_preenchidas_abertas = avaliacoes_biomedicas_abertas.filter(
        examefisico__isnull=False, sinaisvitais__isnull=False, odontograma__salvo=True
    )

    avaliacoes_biomedicas_pendentes = avaliacoes_biomedicas_preenchidas_abertas

    if eh_dentista:
        avaliacoes_biomedicas_pendentes = avaliacoes_biomedicas_pendentes | avaliacoes_biomedicas_abertas.filter(odontograma__salvo=False)
    if eh_medico:
        avaliacoes_biomedicas_pendentes = avaliacoes_biomedicas_pendentes | avaliacoes_biomedicas_abertas.filter(examefisico__isnull=True)

    if eh_enfermeiro:
        avaliacoes_biomedicas_pendentes = avaliacoes_biomedicas_pendentes | avaliacoes_biomedicas_abertas.filter(sinaisvitais__isnull=True)

    if avaliacoes_biomedicas_pendentes.exists():
        avaliacoes_biomedicas_pendentes = avaliacoes_biomedicas_pendentes.distinct()

    if form.is_valid():
        # Busca feita em Aluno para ser o Aluno selecionado ser usado futuramente nos atendimentos de cada especialidade
        if int(form.cleaned_data['vinculo']) == Vinculo.ALUNO:
            vinculo = Vinculo.ALUNO
            pessoas = (
                Aluno.objects.exclude(pessoa_fisica__cpf='	. . -')
                .filter(
                    Q(pessoa_fisica__nome__icontains=form.cleaned_data['paciente'])
                    | Q(pessoa_fisica__cpf__icontains=form.cleaned_data['paciente'])
                    | Q(matricula=form.cleaned_data['paciente'])
                )
                .order_by('pessoa_fisica__nome')
            )
        elif int(form.cleaned_data['vinculo']) == Vinculo.SERVIDOR:
            vinculo = Vinculo.SERVIDOR
            pessoas = Servidor.objects.filter(
                Q(pessoa_fisica__nome__icontains=form.cleaned_data['paciente']) | Q(matricula=form.cleaned_data['paciente'])
            ).order_by('pessoa_fisica__nome')
        elif int(form.cleaned_data['vinculo']) == Vinculo.PRESTADOR_SERVICO:
            vinculo = Vinculo.PRESTADOR_SERVICO
            pessoas = PrestadorServico.objects.filter(
                Q(ativo=True), Q(pessoa_fisica__nome__icontains=form.cleaned_data['paciente']) | Q(pessoa_fisica__cpf=form.cleaned_data['paciente'])
            ).order_by('pessoa_fisica__nome')
        elif int(form.cleaned_data['vinculo']) == Vinculo.COMUNIDADE_EXTERNA:
            vinculo = Vinculo.COMUNIDADE_EXTERNA
            pessoas = (
                PessoaExterna.objects.exclude(cpf='	. . -')
                .filter(Q(nome__icontains=form.cleaned_data['paciente']) | Q(pessoa_fisica__cpf__icontains=form.cleaned_data['paciente']))
                .order_by('nome')
            )

    vinculos = Vinculo
    pode_ver_prontuarios = True
    if request.user.has_group_cached('Atendente'):
        pode_ver_prontuarios = False

    pode_gerenciar_atend_multidisciplinar = eh_dentista or eh_medico or eh_nutricionista or eh_psicologo
    atendimentos_encaminhados = EncaminhamentoPaciente.objects.filter(
        tipo=EncaminhamentoPaciente.TipoEncaminhamento.INTERNO, atendido_em=None
    ).filter(prontuario__vinculo__in=Aluno.objects.filter(curso_campus__diretoria__setor__uo=uo_atual).values_list('vinculos', flat=True))
    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Assistente Social'])
def prontuario(request, id_vinculo):
    vinculo = get_object_or_404(
        VinculoPessoa, id=id_vinculo, tipo_relacionamento__model__in=['servidor', 'aluno', 'prestadorservico', 'aluno', 'pessoaexterna']
    )
    vinculo_do_paciente = vinculo
    pessoa_fisica = vinculo.pessoa.pessoafisica
    if pessoa_fisica.cpf and '*' not in pessoa_fisica.cpf and not pessoa_fisica.cpf_ou_cnpj_valido():
        return httprr('/saude/prontuarios/', 'O usuário não possui CPF válido.', tag='error')

    eh_grupo_medico_enf = eh_do_grupo_medico_enf(request.user)
    eh_dentista = request.user.has_group_cached(Especialidades.ODONTOLOGO)
    eh_tecnico_bucal = request.user.has_group_cached(Especialidades.TECNICO_SAUDE_BUCAL)
    eh_assistente_social = request.user.has_group_cached('Assistente Social')
    situacao_atendimento = SituacaoAtendimento()
    vinculo_aluno = None
    vinculo_servidor = None
    tem_caracterizacao = None

    # Busca o prontuario da pessoa fisica
    prontuario = Prontuario.get_prontuario(vinculo)
    rnvacina_ativo = APIExterna.RNMAISVACINA.ativo

    # Lista os vinculos ativos de uma pessoa fisica
    vinculos = Vinculo.get_vinculos(pessoa_fisica)
    tem_vinculo_externo = False
    tem_outros_vinculos_ativos = False
    for vinculo in vinculos:
        if vinculo.vinculo == Vinculo.COMUNIDADE_EXTERNA:
            tem_vinculo_externo = True
        else:
            tem_outros_vinculos_ativos = True

        if vinculo.vinculo == Vinculo.ALUNO:
            vinculo_aluno = vinculo
        elif vinculo.vinculo == Vinculo.SERVIDOR:
            vinculo_servidor = vinculo
    telefone = None
    if vinculo_aluno:
        telefone = vinculo_aluno.telefone_principal
        endereco = vinculo_aluno.get_endereco()
        email_do_aluno = vinculo_aluno.email_notificacao or vinculo_aluno.email_academico
        nome_responsavel = vinculo_aluno.responsavel
        email_responsavel = vinculo_aluno.email_responsavel
        tel_responsavel = vinculo_aluno.telefone_adicional_1
        from ae.models import Caracterizacao

        caracterizacao = Caracterizacao.objects.filter(aluno=vinculo_aluno)

        horario_atual = f'{datetime.datetime.now().hour}:{datetime.datetime.now().minute}'
        estah_em_horario_de_aula = vinculo_aluno.em_horario_de_aula(datetime.datetime.now().date(), horario_atual)
        if caracterizacao.exists():
            tem_caracterizacao = True
            renda_familiar = caracterizacao[0].renda_bruta_familiar
            moradia = caracterizacao[0].tipo_imovel_residencial
            escolaridade_mae = caracterizacao[0].mae_nivel_escolaridade.descricao
            escolaridade_pai = caracterizacao[0].pai_nivel_escolaridade.descricao
            qtd_pessoas_domicilio = caracterizacao[0].qtd_pessoas_domicilio
        tem_cartao_vacinal_matricula_online = vinculo_aluno.alunoarquivo_set.filter(
            Q(descricao='Cópia da Carteira de Vacinação Atualizada') | Q(tipo=12)
        ).last()
        tipo_sanguineo = vinculo_aluno.tipo_sanguineo
    elif vinculo_servidor:
        telefone = vinculo_servidor.telefones_pessoais
        endereco = vinculo_servidor.endereco
    eh_externo = tem_vinculo_externo and not tem_outros_vinculos_ativos
    tem_vinculos_anteriores = False
    if not tem_outros_vinculos_ativos:
        tem_vinculos_anteriores = (
            Aluno.objects.filter(pessoa_fisica__cpf=pessoa_fisica.cpf).exists()
            or Servidor.objects.filter(pessoa_fisica__cpf=pessoa_fisica.cpf).exists()
            or PrestadorServico.objects.filter(pessoa_fisica__cpf=pessoa_fisica.cpf).exists()
        )
    mostra_abas = tem_outros_vinculos_ativos or tem_vinculos_anteriores or not eh_externo

    title = f'Prontuário #{prontuario.id}'

    todos_atendimentos = Atendimento.objects.filter(prontuario__vinculo__pessoa__pessoafisica__cpf=pessoa_fisica.cpf).order_by('-data_aberto')

    # Lista as avaliacoes biomedicas
    atendimentos_avaliacao_biomedica = todos_atendimentos.filter(tipo=TipoAtendimento.AVALIACAO_BIOMEDICA).order_by('-data_aberto')

    # Lista os atendimentos Enfermagem/Medicina
    atendimentos_medico_enfermagem = todos_atendimentos.filter(tipo=TipoAtendimento.ENFERMAGEM_MEDICO).order_by('-data_aberto')

    exames_laboratoriais = ExameLaboratorial.objects.filter(prontuario=prontuario).order_by('-data_realizado', 'categoria')
    exames_imagem = ExameImagem.objects.filter(prontuario=prontuario).order_by('-data_realizado', 'nome')

    # Lista os atendimentos Odontológicos
    atendimentos_odontologicos = todos_atendimentos.filter(tipo=TipoAtendimento.ODONTOLOGICO).order_by('-data_aberto')

    atendimentos_psicologicos = todos_atendimentos.filter(tipo=TipoAtendimento.PSICOLOGICO).order_by('-data_aberto')

    atendimentos_nutricionais = todos_atendimentos.filter(tipo=TipoAtendimento.NUTRICIONAL).order_by('-data_aberto')

    atendimentos_fisioterapia = todos_atendimentos.filter(tipo=TipoAtendimento.FISIOTERAPIA).order_by('-data_aberto')

    atendimentos_multidisciplinares = todos_atendimentos.filter(tipo=TipoAtendimento.MULTIDISCIPLINAR).order_by('-data_aberto')

    tem_alergia_alimentos = False
    tem_alergia_medicamentos = False
    tem_doenca_cronica = False
    tem_plano_odontologico = False
    eh_gestante = False
    usa_medicamentos = False
    hemorragia = False
    bebe = False
    fuma = False
    circunferencia_cintura = False
    imc = False
    processos_saude_doenca = ProcessoSaudeDoenca.objects.filter(atendimento__in=todos_atendimentos.values_list('id', flat=True))
    if processos_saude_doenca.exists():
        mais_recente = processos_saude_doenca.latest('id')
        tem_plano_odontologico = mais_recente.tem_plano_odontologico
        tem_alergia_alimentos = mais_recente.alergia_alimentos
        usa_medicamentos = mais_recente.usa_medicamentos
        if mais_recente.hemorragia:
            hemorragia = mais_recente.descricao_hemorragia
        if tem_alergia_alimentos:
            quais_alergias_alimentos = mais_recente.que_alimentos
        else:
            ultima_nutricao = NutricaoAlimentacao.objects.filter(atendimento__in=todos_atendimentos.values_list('id', flat=True))
            if ultima_nutricao.exists():
                nutricao = ultima_nutricao.latest('id')
                if nutricao and nutricao.tem_alergia_alimentos:
                    quais_alergias_alimentos = ', '.join([opcao.descricao for opcao in nutricao.alergia_alimentos.exclude(descricao='Outros')])
                    tem_alergia_alimentos = True
                    if nutricao.alergia_alimentos_outros:
                        quais_alergias_alimentos += f', {nutricao.alergia_alimentos_outros}'

        tem_alergia_medicamentos = mais_recente.alergia_medicamentos
        if tem_alergia_medicamentos:
            quais_alergias_medicamentos = mais_recente.que_medicamentos
        tem_doenca_cronica = mais_recente.doencas_cronicas.all()
        if tem_doenca_cronica.exists():
            quais_doencas_cronicas = ''
            for doenca in tem_doenca_cronica:
                quais_doencas_cronicas += doenca.nome + ', '
            quais_doencas_cronicas = quais_doencas_cronicas[:-2]
        if usa_medicamentos:
            quais_medicamentos = mais_recente.usa_que_medicamentos

        eh_gestante = mais_recente.gestante
    ultimos_habitos = HabitosDeVida.objects.filter(atendimento__in=todos_atendimentos.values_list('id', flat=True))
    if ultimos_habitos.exists():
        habitos = ultimos_habitos.latest('id')
        if habitos:
            bebe = habitos.frequencia_uso_bebida
            fuma = habitos.frequencia_uso_fumo
    ultima_antropometria = Antropometria.objects.filter(atendimento__in=todos_atendimentos.values_list('id', flat=True))
    if ultima_antropometria.exists():
        antropometria = ultima_antropometria.latest('id')
        if antropometria:
            circunferencia_cintura = antropometria.cintura
            tem_imc = antropometria.get_IMC()
            if tem_imc:
                imc = str(tem_imc)
                classificacao = antropometria.get_classificacao_IMC()
                if classificacao:
                    imc += f' - {classificacao}'

    # Agrupamento dos registros de Vacina
    vacinas = CartaoVacinal.objects.filter(prontuario__vinculo__pessoa__pessoafisica__cpf=pessoa_fisica.cpf).order_by('-id')
    grupo_vacina = Vacina.objects.filter(id__in=vacinas.values_list('vacina', flat=True)).order_by('-id')

    grupos = [[registro_vacina for registro_vacina in vacinas if registro_vacina.vacina_id == grupo.id] for grupo in grupo_vacina]

    # Verificando se existem vacinas em atraso ou próximas do prazo
    vacinas_atrasadas = False
    vacinas_proximas = False
    for registro_vacina in vacinas:
        if (
            registro_vacina.data_prevista
            and not registro_vacina.data_vacinacao
            and not registro_vacina.sem_data
            and datetime.date.today() > registro_vacina.data_prevista
        ):
            vacinas_atrasadas = True
        elif (
            registro_vacina.data_prevista
            and not registro_vacina.data_vacinacao
            and not registro_vacina.sem_data
            and datetime.date.today() + datetime.timedelta(days=15) >= registro_vacina.data_prevista
        ):
            vacinas_proximas = True

    anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(prontuario=prontuario).order_by('-data')
    eh_psicologo = request.user.has_group_cached(Especialidades.PSICOLOGO)
    tem_anamnese_psicologica = False
    anamnese_psicologia_responsavel = False

    if eh_psicologo:
        anamnese_psicologia = AnamnesePsicologia.objects.filter(prontuario=prontuario, profissional=request.user)
        if anamnese_psicologia.exists():
            anamnese_psicologia = anamnese_psicologia[0]
            anamnese_psicologia_responsavel = anamnese_psicologia.get_responsavel()

    dados_exames = {}

    categorias = CategoriaExameLaboratorial.objects.filter(
        tipoexamelaboratorial__isnull=False, id__in=ExameLaboratorial.objects.filter(prontuario=prontuario).values_list('categoria', flat=True)
    )

    for categoria in categorias:
        registros = {}
        for item in ValorExameLaboratorial.objects.filter(exame__prontuario=prontuario, tipo__categoria=categoria).order_by('tipo__nome'):
            if not item.exame.sigiloso or (item.exame.sigiloso and item.exame.profissional == request.user.get_relacionamento()):
                chave = f'{item.tipo.nome} ({item.tipo.unidade})'
                registros[chave] = {}
        meses = {}

        for exame in ExameLaboratorial.objects.filter(prontuario=prontuario, categoria=categoria).order_by('data_realizado'):
            if not exame.sigiloso or (exame.sigiloso and exame.profissional == request.user.get_relacionamento()):
                if str(format_(exame.data_realizado)) in meses:
                    index = 1
                    for indice in list(meses.keys()):
                        if str(format_(exame.data_realizado)) in indice:
                            index += 1
                    chave_exame = '{} ({})'.format(exame.data_realizado.strftime('%d/%m/%Y'), index)
                else:
                    chave_exame = exame.data_realizado.strftime('%d/%m/%Y')
                meses[chave_exame] = {}

            for item in ValorExameLaboratorial.objects.filter(exame=exame).order_by('tipo__nome'):
                if not item.exame.sigiloso or (item.exame.sigiloso and item.exame.profissional == request.user.get_relacionamento()):
                    chave = f'{item.tipo.nome} ({item.tipo.unidade})'
                    registros[chave][chave_exame] = f'{item.valor} {item.tipo.unidade}'

        meses_ordenados = collections.OrderedDict(sorted(meses.items(), reverse=True))
        registros_ordenados = collections.OrderedDict(sorted(registros.items(), key=lambda x: x[0]))
        dados_exames[categoria.nome] = {'meses': meses_ordenados, 'registros': registros_ordenados}
    anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(prontuario=prontuario).order_by('-data')
    especialidade = Especialidades(request.user)

    eh_nutricionista = especialidade.is_nutricionista()
    eh_fisioterapeuta = especialidade.is_fisioterapeuta()
    pode_gerenciar_atend_multidisciplinar = eh_dentista or especialidade.is_medico() or eh_nutricionista or eh_psicologo

    documentos = DocumentoProntuario.objects.filter(prontuario=prontuario).order_by('-data')
    notificacao_covid = NotificacaoCovid.objects.filter(vinculo=vinculo_do_paciente).order_by('-id')
    anexos = AnexoProntuario.objects.filter(prontuario=prontuario)
    encaminhamentos = EncaminhamentoPaciente.objects.filter(prontuario=prontuario).order_by('-cadastrado_em')
    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def abrir_atendimento(request, tipo_atendimento, prontuario_id, vinculo, vinculo_id):
    try:
        vinculo_obj = Vinculo.get_vinculo(vinculo, vinculo_id)
    except Exception:
        return HttpResponse(status=404)
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)

    try:
        if (isinstance(vinculo_obj, Aluno) and not vinculo_obj.situacao.ativo) or (
            isinstance(vinculo_obj, PrestadorServico) and not vinculo_obj.ativo
        ):
            return httprr('/saude/prontuarios/', 'O perfil deste usuário está inativo.', tag='error')

        eh_grupo_medico_enf = eh_do_grupo_medico_enf(request.user)
        eh_dentista = request.user.has_group_cached(Especialidades.ODONTOLOGO)
        eh_tecnico_bucal = request.user.has_group_cached(Especialidades.TECNICO_SAUDE_BUCAL)
        eh_psicologo = request.user.has_group_cached(Especialidades.PSICOLOGO)
        eh_nutricionista = request.user.has_group_cached(Especialidades.NUTRICIONISTA)
        eh_medico = request.user.has_group_cached(Especialidades.MEDICO)
        eh_fisioterapeuta = request.user.has_group_cached(Especialidades.FISIOTERAPEUTA)
        pode_gerenciar_atend_multidisciplinar = eh_dentista or eh_medico or eh_nutricionista or eh_psicologo

        tipo_atendimento = TipoAtendimento.TIPO_ATENDIMENTO.get(int(tipo_atendimento))

        pode_abrir_atendimento = True
        if (
            tipo_atendimento == TipoAtendimento.ENFERMAGEM_MEDICO
            and not eh_grupo_medico_enf
            or tipo_atendimento == TipoAtendimento.ODONTOLOGICO
            and not (eh_dentista or eh_tecnico_bucal)
            or tipo_atendimento == TipoAtendimento.PSICOLOGICO
            and not eh_psicologo
            or tipo_atendimento == TipoAtendimento.NUTRICIONAL
            and not eh_nutricionista
            or tipo_atendimento == TipoAtendimento.FISIOTERAPIA
            and not eh_fisioterapeuta
            or tipo_atendimento == TipoAtendimento.MULTIDISCIPLINAR
            and not pode_gerenciar_atend_multidisciplinar
        ):
            pode_abrir_atendimento = False

        if not pode_abrir_atendimento:
            return httprr('/saude/prontuarios/', 'Você não pode abrir este tipo de atendimento.', tag='error')

        if (
            tipo_atendimento == TipoAtendimento.ODONTOLOGICO
            and Atendimento.objects.filter(
                tipo=TipoAtendimento.ODONTOLOGICO, prontuario=prontuario, data_fechado__gte=(datetime.datetime.now() - relativedelta(hours=12))
            ).exists()
        ):
            return httprr(
                f'/saude/prontuario/{prontuario.vinculo_id}/',
                'Você não pode abrir novo atendimento de odontologia quando o último atendimento foi finalizado há menos de 12 horas. Reabra o atendimento mais recente.',
                tag='error',
            )
        atendimento = Atendimento.abrir(TipoAtendimento.TIPO_ATENDIMENTO.get(int(tipo_atendimento)), prontuario, vinculo_obj, request.user)

        if atendimento.is_atendimento_avaliacao_biomedica():
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/', 'Avaliação biomédica gerada com sucesso.')
        elif atendimento.is_atendimento_enfermagem_medico():
            return httprr(f'/saude/atendimento_medico_enfermagem/{atendimento.id}/', 'Atendimento Médico/Enfermagem gerado com sucesso.')
        elif atendimento.is_atendimento_odontologico():
            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/', 'Atendimento Odontológico gerado com sucesso.')
        elif atendimento.is_atendimento_psicologico():
            return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/', 'Atendimento Psicológico gerado com sucesso.')
        elif atendimento.is_atendimento_nutricional():
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/', 'Atendimento Nutricional gerado com sucesso.')
        elif atendimento.is_atendimento_fisioterapia():
            return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/', 'Atendimento de Fisioterapia gerado com sucesso.')

        elif atendimento.is_atendimento_multidisciplinar():
            return httprr(f'/saude/atendimento_multidisciplinar/{atendimento.id}/', 'Atendimento Multidisciplinar gerado com sucesso.')

    except ValidationError as e:
        return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/', ''.join(e.messages), tag='error')


@rtr()
@group_required(Especialidades.GRUPOS)
def fechar_atendimento(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Fechar atendimento - {atendimento.get_vinculo()}'

    pode_fechar = pode_alterar_atendimento(atendimento, request)
    if not pode_fechar:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/', 'Você não tem permissão para fechar este atendimento.', tag='error')

    msgs_erro = atendimento.tem_pendencia(request)
    if msgs_erro:
        for msg in msgs_erro:
            messages.add_message(request, messages.ERROR, msg)

    if msgs_erro:
        if atendimento.tipo == TipoAtendimento.AVALIACAO_BIOMEDICA:
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/')
        elif atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO:
            return httprr(f'/saude/atendimento_medico_enfermagem/{atendimento.id}/')
        elif atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/')
        elif atendimento.tipo == TipoAtendimento.PSICOLOGICO:
            return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/')
        elif atendimento.tipo == TipoAtendimento.NUTRICIONAL:
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/')
        elif atendimento.tipo == TipoAtendimento.FISIOTERAPIA:
            return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/')
        elif atendimento.tipo == TipoAtendimento.MULTIDISCIPLINAR:
            return httprr(f'/saude/atendimento_multidisciplinar/{atendimento.id}/')

    encerra_plano_tratamento = False
    if atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
        if ProcedimentoOdontologico.objects.filter(tipo_consulta=ProcedimentoOdontologico.CONCLUSAO_TRATAMENTO, atendimento=atendimento).exists():
            encerra_plano_tratamento = True

    nao_informou_tipo_consulta = Odontograma.objects.filter(atendimento=atendimento, tipo_consulta__isnull=True).exists()

    form = FecharAtendimentoForm(request.POST or None, instance=atendimento, request=request)
    if form.is_valid():
        atendimento.fechar(request)
        msg_sucesso = 'Atendimento fechado com sucesso.'
        if atendimento.tipo == TipoAtendimento.AVALIACAO_BIOMEDICA:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_avaliacao_biomedica', msg_sucesso)
        elif atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_medico_enfermagem', msg_sucesso)
        elif atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_odontologico', msg_sucesso)
        elif atendimento.tipo == TipoAtendimento.PSICOLOGICO:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_psicologico', msg_sucesso)
        elif atendimento.tipo == TipoAtendimento.NUTRICIONAL:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_nutricional', msg_sucesso)
        elif atendimento.tipo == TipoAtendimento.FISIOTERAPIA:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_fisioterapia', msg_sucesso)
        elif atendimento.tipo == TipoAtendimento.MULTIDISCIPLINAR:
            return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_multidisciplinar', msg_sucesso)

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def cancelar_atendimento(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    pode_fechar = pode_alterar_atendimento(atendimento, request)

    if not pode_fechar:
        return httprr(
            f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/', 'Você não tem permissão para cancelar este atendimento.', tag='error'
        )

    title = f'Fechar atendimento - {atendimento.get_vinculo()}'

    form = CancelarAtendimentoForm(request.POST or None, instance=atendimento, request=request)
    if form.is_valid():
        atendimento.cancelar(request)
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/', 'Atendimento cancelado com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def historico_ficha(request, atendimento_id, ficha):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    if atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO and not eh_do_grupo_medico_enf(request.user):
        raise PermissionDenied

    default_exclude = ('id', 'data_cadastro', 'atendimento_id', 'profissional_id')
    if ficha == '1':
        default_exclude = ('id', 'data_cadastro', 'atendimento_id', 'profissional_id', 'temperatura', 'respiracao')
    elif ficha == '4':
        default_exclude = ('id', 'data_cadastro', 'atendimento_id', 'profissional_id', 'outras_drogas')

    MODEL_LIST = (
        SinaisVitais,
        Antropometria,
        AcuidadeVisual,
        HabitosDeVida,
        DesenvolvimentoPessoal,
        ExameFisico,
        PercepcaoSaudeBucal,
        Motivo,
        Anamnese,
        HipoteseDiagnostica,
        CondutaMedica,
        NutricaoAlimentacao,
        SaudeMental,
    )

    MODEL_X = {
        1: {
            'modelo': SinaisVitais,
            'fields': [f.get_attname() for f in SinaisVitais._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Sinais Vitais',
        },
        2: {
            'modelo': Antropometria,
            'fields': [f.get_attname() for f in Antropometria._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Antropometria',
        },
        3: {
            'modelo': AcuidadeVisual,
            'fields': [f.get_attname() for f in AcuidadeVisual._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Acuidade Visual',
        },
        4: {
            'modelo': HabitosDeVida,
            'fields': [f.get_attname() for f in HabitosDeVida._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Hábitos de Vida',
        },
        5: {
            'modelo': DesenvolvimentoPessoal,
            'fields': [f.get_attname() for f in DesenvolvimentoPessoal._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Desenvolvimento Pessoal',
        },
        6: {
            'modelo': ExameFisico,
            'fields': [f.get_attname() for f in ExameFisico._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Exame Pessoal',
        },
        7: {
            'modelo': PercepcaoSaudeBucal,
            'fields': [f.get_attname() for f in PercepcaoSaudeBucal._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Percepção de Saúde Bucal',
        },
        8: {
            'modelo': Motivo,
            'fields': [f.get_attname() for f in Motivo._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Motivo do Atendimento',
        },
        9: {
            'modelo': Anamnese,
            'fields': [f.get_attname() for f in Anamnese._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Anamnese',
        },
        10: {
            'modelo': HipoteseDiagnostica,
            'fields': [f.get_attname() for f in HipoteseDiagnostica._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Hipótese Diagnóstica',
        },
        11: {
            'modelo': NutricaoAlimentacao,
            'fields': [f.get_attname() for f in NutricaoAlimentacao._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Nutrição e Alimentação',
        },
        12: {
            'modelo': SaudeMental,
            'fields': [f.get_attname() for f in SaudeMental._meta.get_fields() if f.get_attname() not in default_exclude],
            'titulo': 'Saúde Mental',
        },
    }

    # Seleciona o modelo de acordo com os parametros
    model_dict = MODEL_X.get(ficha)

    title = 'Histórico - {}'.format(model_dict.pop('titulo'))
    Klass = model_dict.pop('modelo')

    historico = Klass.objects.filter(atendimento=atendimento.pk).order_by('-id')

    # Campos básicos do histórico
    if 'custom_fields' not in model_dict:
        model_dict['custom_fields'] = {'get_cadastro_display': Column('Cadastrado por', accessor='get_cadastro_display')}
    if 'sequence' not in model_dict:
        model_dict['sequence'] = model_dict['fields'] + ['get_cadastro_display']

    # Monta a tabela
    table_historico = get_table(queryset=historico, **model_dict)

    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Assistente Social'])
def avaliacao_biomedica(request, atendimento_id):
    title = 'Avaliação de Saúde'

    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.AVALIACAO_BIOMEDICA)
    situacoes_atendimento = SituacaoAtendimento()
    ocultar_dobras = Configuracao.get_valor_por_chave('saude', 'ocultar_dobras_cutaneas')
    eh_assistente_social = request.user.has_group_cached('Assistente Social')
    pendencias = atendimento.tem_pendencia(request)

    if atendimento.aluno:
        programas = Participacao.objects.filter(aluno=atendimento.get_vinculo(), data_termino__isnull=True)

    # Avaliação Biomedica
    sinaisvitais = SinaisVitais.objects.filter(atendimento=atendimento)
    sinaisvitais_titulo = 'Sinais Vitais'
    sinaisvitais_count = sinaisvitais.count()
    sinaisvitais_responsavel = None
    if sinaisvitais.exists():
        sinaisvitais = sinaisvitais.latest('id')
        sinaisvitais_responsavel = sinaisvitais.get_responsavel()

    antropometria = Antropometria.objects.filter(atendimento=atendimento)
    antropometria_titulo = 'Antropometria'
    antropometria_count = antropometria.count()
    if antropometria.exists():
        antropometria = antropometria.latest('id')
        antropometria_responsavel = antropometria.get_responsavel()

    acuidadevisual = AcuidadeVisual.objects.filter(atendimento=atendimento)
    acuidadevisual_titulo = 'Acuidade Visual'
    acuidadevisual_count = acuidadevisual.count()
    if acuidadevisual.exists():
        acuidadevisual = acuidadevisual.latest('id')
        acuidadevisual_responsavel = acuidadevisual.get_responsavel()

    cadastrou_antecedentes = False
    cadastrou_processosaudedoenca = False
    antecedentesfamiliares = AntecedentesFamiliares.objects.filter(atendimento=atendimento)
    antecedentesfamiliares_titulo = 'Antecedentes'
    antecedentesfamiliares_count = antecedentesfamiliares.count()
    if antecedentesfamiliares.exists():
        cadastrou_antecedentes = True
        antecedentesfamiliares = antecedentesfamiliares.latest('id')
        antecedentesfamiliares_responsavel = antecedentesfamiliares.get_responsavel()

    processosaudedoenca = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento)
    processosaudedoenca_titulo = 'Processo Saúde-Doença'
    processosaudedoenca_count = processosaudedoenca.count()
    if processosaudedoenca.exists():
        cadastrou_processosaudedoenca = True
        processosaudedoenca = processosaudedoenca.latest('id')
        processosaudedoenca_responsavel = processosaudedoenca.get_responsavel()

    aba_antecedentes_preenchida = cadastrou_antecedentes and cadastrou_processosaudedoenca

    habitosdevida = HabitosDeVida.objects.filter(atendimento=atendimento)
    habitosdevida_titulo = 'Hábitos de Vida'
    habitosdevida_count = habitosdevida.count()
    if habitosdevida.exists():
        habitosdevida = habitosdevida.latest('id')
        habitosdevida_responsavel = habitosdevida.get_responsavel()

    desenvolvimentopessoal = DesenvolvimentoPessoal.objects.filter(atendimento=atendimento)
    desenvolvimentopessoal_titulo = 'Desenvolvimento Pessoal'
    desenvolvimentopessoal_count = desenvolvimentopessoal.count()
    if desenvolvimentopessoal.exists():
        desenvolvimentopessoal = desenvolvimentopessoal.latest('id')
        desenvolvimentopessoal_responsavel = desenvolvimentopessoal.get_responsavel()

    examefisico = ExameFisico.objects.filter(atendimento=atendimento)
    examefisico_titulo = 'Exame Físico'
    examefisico_count = examefisico.count()
    if examefisico.exists():
        examefisico = examefisico.latest('id')
        examefisico_responsavel = examefisico.get_responsavel()

    percepcaosaudebucal = PercepcaoSaudeBucal.objects.filter(atendimento=atendimento)
    percepcaosaudebucal_titulo = 'Percepção da Saúde Bucal'
    percepcaosaudebucal_count = percepcaosaudebucal.count()
    if percepcaosaudebucal.exists():
        percepcaosaudebucal = percepcaosaudebucal.latest('id')
        percepcaosaudebucal_responsavel = percepcaosaudebucal.get_responsavel()

    odontograma = Odontograma.objects.filter(atendimento=atendimento)
    odontograma_titulo = 'Odontograma'
    odontograma_count = odontograma.count()
    if odontograma.exists():
        odontograma = odontograma.latest('id')
        odontograma_responsavel = odontograma.get_responsavel()
        situacoes = SituacaoClinica.objects.all()
        alteracoes = []
        controla_itens = []

        for item in odontograma.dentes_alterados_lista():
            id_situacao = item[7:]

            if int(id_situacao) in [
                SituacaoClinica.EXODONTIA_POR_OUTROS_MOTIVOS,
                SituacaoClinica.EXODONTIA_POR_CARIE,
                SituacaoClinica.DENTE_AUSENTE_EXTRAIDO_OUTRAS_RAZOES,
                SituacaoClinica.DENTE_EXTRAIDO_CARIE,
            ]:
                dente = item[4:6]

                if item[4:8] not in controla_itens:
                    if '_V_' in item[:-3]:
                        face = 'Vestibular'

                    elif '_P_' in item[:-3]:
                        face = 'Palatal/Lingual'

                    elif '_M_' in item[:-3]:
                        face = 'Mesial'

                    elif '_D_' in item[:-3]:
                        face = 'Distal'

                    elif '_O_' in item[:-3]:
                        face = 'Oclusal/Incisal'

                    elif '_C_' in item[:-3]:
                        face = 'Cervical'

                    elif '_R_' in item[:-3]:
                        face = 'Raiz'

                    for outro in odontograma.dentes_alterados_lista():
                        if outro[:-3] != item[:-3] and outro[4:8] == item[4:8]:
                            if '_V_' in outro[:-3]:
                                face += ', Vestibular'

                            elif '_P_' in outro[:-3]:
                                face += ', Palatal/Lingual'

                            elif '_M_' in outro[:-3]:
                                face += ', Mesial'

                            elif '_D_' in outro[:-3]:
                                face += ', Distal'

                            elif '_O_' in outro[:-3]:
                                face += ', Oclusal/Incisal'

                            elif '_C_' in outro[:-3]:
                                face += ', Cervical'

                            elif '_R_' in outro[:-3]:
                                face += ', Raiz'

                    controla_itens.append(item[4:8])
                    situacao = SituacaoClinica.objects.get(id=id_situacao)
                    alteracoes.append({'dente': dente, 'situacao': situacao, 'face': face})
            else:
                dente = item[4:6]
                if '_V_' in item[:-3]:
                    face = 'Vestibular'
                if '_P_' in item[:-3]:
                    face = 'Palatal/Lingual'
                if '_M_' in item[:-3]:
                    face = 'Mesial'
                if '_D_' in item[:-3]:
                    face = 'Distal'
                if '_O_' in item[:-3]:
                    face = 'Oclusal/Incisal'
                if '_C_' in item[:-3]:
                    face = 'Cervical'
                if '_R_' in item[:-3]:
                    face = 'Raiz'

                situacao = SituacaoClinica.objects.get(id=id_situacao)
                alteracoes.append({'dente': dente, 'situacao': situacao, 'face': face})

    nutricao = NutricaoAlimentacao.objects.filter(atendimento=atendimento)
    nutricao_titulo = 'Nutrição e Alimentação'
    nutricao_count = nutricao.count()
    if nutricao.exists():
        nutricao = nutricao.latest('id')
        nutricao_responsavel = nutricao.get_responsavel()

    saudemental = SaudeMental.objects.filter(atendimento=atendimento)
    saudemental_titulo = 'Saúde Mental'
    saudemental_count = saudemental.count()
    if saudemental.exists():
        saudemental = saudemental.latest('id')
        saudemental_responsavel = saudemental.get_responsavel()

    informacoes_adicionais = InformacaoAdicional.objects.filter(atendimento=atendimento)
    informacoesadicionais_count = informacoes_adicionais.count()
    exames_periodontais = ExamePeriodontal.objects.filter(atendimento=atendimento).order_by('sextante')
    if exames_periodontais.exists():
        exames_periodontais_responsavel = exames_periodontais.latest('id').get_responsavel()
    avaliacoes_tecidos = ExameEstomatologico.objects.filter(atendimento=atendimento)
    if avaliacoes_tecidos.exists():
        avaliacoes_tecidos = avaliacoes_tecidos.latest('id')
        avaliacoes_tecidos_responsavel = avaliacoes_tecidos.get_responsavel()
    is_coordenador_sistemico = in_group(request.user, 'Coordenador de Saúde Sistêmico')
    especialidade = Especialidades(request.user)

    return locals()


@rtr()
@group_required(['Médico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Odontólogo'])
@permission_required('rh.eh_servidor')
def adicionar_sinaisvitais(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)

    title = f'Adicionar Sinais Vitais - {atendimento.get_vinculo()}'

    sinaisvitais = SinaisVitais()
    sinaisvitais.profissional = request.user
    sinaisvitais.data_cadastro = datetime.datetime.now()
    sinaisvitais.atendimento = atendimento

    form = SinaisVitaisForm(request.POST or None, instance=sinaisvitais, request=request, initial={'temperatura_categoria': '2'})

    if form.is_valid():
        form.save()
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_sinais_vitais', 'Sinais Vitais registrados com sucesso.')

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Técnico em Saúde Bucal',
        'Psicólogo',
    ]
)
@permission_required('rh.eh_servidor')
def adicionar_antropometria(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Antropometria - {atendimento.get_vinculo()}'
    antropometria = Antropometria.objects.filter(atendimento=atendimento.pk)
    if antropometria.exists():
        antropometria = antropometria.latest('id')
        antropometria.id = None
    else:
        antropometria = Antropometria()

    antropometria.profissional = request.user
    antropometria.data_cadastro = datetime.datetime.now()
    antropometria.atendimento = atendimento

    form = AntropometriaForm(request.POST or None, instance=antropometria, request=request)

    if form.is_valid():
        form.save()
        if atendimento.is_atendimento_avaliacao_biomedica():
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_antropometria', 'Antropometria registrada com sucesso.')
        elif atendimento.is_atendimento_nutricional():
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Antropometria registrada com sucesso.')

    return locals()


@rtr()
@group_required(['Médico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem'])
@permission_required('rh.eh_servidor')
def adicionar_acuidadevisual(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Acuidade Visual - {atendimento.get_vinculo()}'
    acuidadevisual = AcuidadeVisual.objects.filter(atendimento=atendimento.pk)

    if acuidadevisual.exists():
        acuidadevisual = acuidadevisual.latest('id')
        acuidadevisual.id = None
    else:
        acuidadevisual = AcuidadeVisual()

    acuidadevisual.profissional = request.user
    acuidadevisual.data_cadastro = datetime.datetime.now()
    acuidadevisual.atendimento = atendimento

    form = AcuidadeVisualForm(request.POST or None, instance=acuidadevisual, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_acuidade_visual', 'Acuidade visual registrada com sucesso.')

    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_antecedentesfamiliares(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)

    especialidade = Especialidades(request.user)
    is_acesso_avaliacao_biomedica = atendimento.is_atendimento_avaliacao_biomedica() and (
        especialidade.is_medico()
        or especialidade.is_enfermeiro()
        or especialidade.is_tecnico_enfermagem()
        or especialidade.is_odontologo()
        or especialidade.is_fisioterapeuta()
        or especialidade.is_nutricionista()
        or especialidade.is_auxiliar_enfermagem()
    )
    is_acesso_atendimento_enfermagem_medico = atendimento.is_atendimento_enfermagem_medico() and especialidade.is_medico()
    is_acesso_atendimento_odontologico = atendimento.is_atendimento_odontologico() and especialidade.is_odontologo()
    is_acesso_atendimento_nutricional = atendimento.is_atendimento_nutricional() and especialidade.is_nutricionista()
    is_acesso_atendimento_fisioterapia = atendimento.is_atendimento_fisioterapia() and especialidade.is_fisioterapeuta()
    if (
        not is_acesso_avaliacao_biomedica
        and not is_acesso_atendimento_enfermagem_medico
        and not is_acesso_atendimento_odontologico
        and not is_acesso_atendimento_nutricional
        and not is_acesso_atendimento_fisioterapia
        and not atendimento.is_atendimento_multidisciplinar()
    ):
        return HttpResponseForbidden()

    title = f'Adicionar Antecedentes Familiares - {atendimento.get_vinculo()}'
    antecedentesfamiliares = AntecedentesFamiliares.objects.filter(atendimento=atendimento.pk)

    if antecedentesfamiliares.exists():
        antecedentesfamiliares = antecedentesfamiliares.latest('id')
    else:
        antecedentesfamiliares = AntecedentesFamiliares()

    antecedentesfamiliares.atendimento = atendimento
    antecedentesfamiliares.profissional = request.user
    antecedentesfamiliares.data_cadastro = datetime.datetime.now()

    form = AntecedentesFamiliaresForm(request.POST or None, instance=antecedentesfamiliares, request=request)

    if form.is_valid():
        form.save()
        if atendimento.is_atendimento_avaliacao_biomedica():
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_antecedentes', 'Antecedentes familiares registrados com sucesso.')
        elif atendimento.is_atendimento_enfermagem_medico():
            return httprr(
                f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_antecedentes', 'Antecedentes familiares registrados com sucesso.'
            )
        elif atendimento.is_atendimento_odontologico():
            return httprr(
                f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_antecedentes', 'Antecedentes familiares registrados com sucesso.'
            )
        elif atendimento.is_atendimento_nutricional():
            return httprr(
                f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_dados_clinicos', 'Antecedentes familiares registrados com sucesso.'
            )
        elif atendimento.is_atendimento_fisioterapia():
            return httprr(
                f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_antecedentes', 'Antecedentes familiares registrados com sucesso.'
            )
        elif atendimento.is_atendimento_multidisciplinar():
            return httprr(
                f'/saude/atendimento_multidisciplinar/{atendimento.id}/?tab=aba_antecedentes', 'Antecedentes familiares registrados com sucesso.'
            )

    return locals()


def _saude_doenca_para_preencher(atendimento: Atendimento, copiar_do_anterior: bool) -> ProcessoSaudeDoenca:
    """Ficha mais recente do próprio atendimento; senão, a do atendimento anterior de abertura mais recente (se ``copiar_do_anterior``); senão, uma em branco."""
    atual = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento.pk).order_by('-id').first()
    if atual:
        return atual
    if copiar_do_anterior:
        anterior = Atendimento.atendimento_anterior_com_ficha(atendimento.prontuario, 'processosaudedoenca', atendimento)
        if anterior:
            return anterior.processosaudedoenca_set.order_by('-id').first()
    return ProcessoSaudeDoenca()


@rtr()
@group_required(
    ['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista', 'Psicólogo']
)
@permission_required('rh.eh_servidor')
def adicionar_processosaudedoenca(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)

    especialidade = Especialidades(request.user)
    is_acesso_avaliacao_biomedica = atendimento.is_atendimento_avaliacao_biomedica() and (
        especialidade.is_medico()
        or especialidade.is_enfermeiro()
        or especialidade.is_tecnico_enfermagem()
        or especialidade.is_odontologo()
        or especialidade.is_fisioterapeuta()
        or especialidade.is_nutricionista()
    )
    is_acesso_atendimento_enfermagem_medico = atendimento.is_atendimento_enfermagem_medico() and (
        especialidade.is_medico() or especialidade.is_enfermeiro() or especialidade.is_tecnico_enfermagem() or especialidade.is_auxiliar_enfermagem()
    )
    is_acesso_atendimento_odontologico = atendimento.is_atendimento_odontologico() and especialidade.is_odontologo()
    is_acesso_atendimento_nutricional = atendimento.is_atendimento_nutricional() and especialidade.is_nutricionista()
    is_acesso_atendimento_fisioterapia = atendimento.is_atendimento_fisioterapia() and especialidade.is_fisioterapeuta()
    if (
        not is_acesso_avaliacao_biomedica
        and not is_acesso_atendimento_enfermagem_medico
        and not is_acesso_atendimento_odontologico
        and not is_acesso_atendimento_nutricional
        and not is_acesso_atendimento_fisioterapia
        and not atendimento.is_atendimento_multidisciplinar()
    ):
        return HttpResponseForbidden()

    title = f'Processo Saúde-Doença - {atendimento.get_vinculo()}'
    processosaudedoenca = _saude_doenca_para_preencher(atendimento, is_acesso_avaliacao_biomedica)

    processosaudedoenca.profissional = request.user
    processosaudedoenca.data_cadastro = datetime.datetime.now()
    processosaudedoenca.atendimento = atendimento

    form = ProcessoSaudeDoencaForm(
        request.POST or None, instance=processosaudedoenca, sexo=atendimento.get_pessoa_fisica_vinculo().sexo, request=request
    )

    if form.is_valid():
        form.save()
        if atendimento.is_atendimento_avaliacao_biomedica():
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_antecedentes', 'Processo Saúde-Doença registrado com sucesso.')
        elif atendimento.is_atendimento_enfermagem_medico():
            return httprr(
                f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_antecedentes', 'Processo Saúde-Doença registrado com sucesso.'
            )
        elif atendimento.is_atendimento_odontologico():
            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_antecedentes', 'Processo Saúde-Doença registrado com sucesso.')
        elif atendimento.is_atendimento_nutricional():
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_dados_clinicos', 'Processo Saúde-Doença registrado com sucesso.')
        elif atendimento.is_atendimento_fisioterapia():
            return httprr(
                f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_antecedentes', 'Antecedentes familiares registrados com sucesso.'
            )
        elif atendimento.is_atendimento_multidisciplinar():
            return httprr(
                f'/saude/atendimento_multidisciplinar/{atendimento.id}/?tab=aba_antecedentes', 'Processo Saúde-Doença registrado com sucesso.'
            )
    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_habitosdevida(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Hábitos de Vida - {atendimento.get_vinculo()}'
    habitosdevida = HabitosDeVida.objects.filter(atendimento=atendimento.pk)

    if habitosdevida.exists():
        habitosdevida = habitosdevida.latest('id')
    else:
        habitosdevida = HabitosDeVida()

    habitosdevida.profissional = request.user
    habitosdevida.data_cadastro = datetime.datetime.now()
    habitosdevida.atendimento = atendimento

    form = HabitosDeVidaForm(request.POST or None, instance=habitosdevida, request=request)

    if form.is_valid():
        form.save()
        if atendimento.is_atendimento_avaliacao_biomedica():
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_habitosdevida', 'Hábitos de Vida registrados com sucesso.')
        elif atendimento.is_atendimento_nutricional():
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Hábitos de Vida registrados com sucesso.')

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Técnico em Saúde Bucal',
        'Psicólogo',
    ]
)
@permission_required('rh.eh_servidor')
def adicionar_percepcaosaudebucal(request, atendimento_id, origem):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Percepção Bucal - {atendimento.get_vinculo()}'
    percepcaosaudebucal = PercepcaoSaudeBucal.objects.filter(atendimento=atendimento.pk)

    if percepcaosaudebucal.exists():
        percepcaosaudebucal = percepcaosaudebucal.latest('id')
        percepcaosaudebucal.id = None
    else:
        percepcaosaudebucal = PercepcaoSaudeBucal()

    percepcaosaudebucal.profissional = request.user
    percepcaosaudebucal.data_cadastro = datetime.datetime.now()
    percepcaosaudebucal.atendimento = atendimento
    form = PercepcaoSaudeBucalForm(request.POST or None, instance=percepcaosaudebucal, request=request)

    if form.is_valid():
        form.save()
        if origem == 2:
            return httprr(
                f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_percepcaosaudebucal', 'Percepção de Saúde Bucal registrada com sucesso.'
            )
        else:
            return httprr(
                f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_percepcaosaudebucal', 'Percepção de Saúde Bucal registrada com sucesso.'
            )

    return locals()


@rtr()
@group_required(
    ['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista', 'Psicólogo']
)
@permission_required('rh.eh_servidor')
def adicionar_desenvolvimentopessoal(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Desenvolvimento Pessoal - {atendimento.get_vinculo()}'
    desenvolvimentopessoal = DesenvolvimentoPessoal.objects.filter(atendimento=atendimento.pk)

    if desenvolvimentopessoal.exists():
        desenvolvimentopessoal = desenvolvimentopessoal.latest('id')
        desenvolvimentopessoal.id = None
    else:
        desenvolvimentopessoal = DesenvolvimentoPessoal()

    desenvolvimentopessoal.profissional = request.user
    desenvolvimentopessoal.data_cadastro = datetime.datetime.now()
    desenvolvimentopessoal.atendimento = atendimento

    form = DesenvolvimentoPessoalForm(request.POST or None, instance=desenvolvimentopessoal, request=request)

    if form.is_valid():
        form.save()
        return httprr(
            f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_desenvolvimentopessoal', 'Desenvolvimento Pessoal registrado com sucesso.'
        )

    return locals()


@rtr()
@group_required('Médico')
@permission_required('rh.eh_servidor')
def adicionar_examefisico(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Exame Físico - {atendimento.get_vinculo()}'
    examefisico = ExameFisico.objects.filter(atendimento=atendimento.pk)

    if examefisico.exists():
        examefisico = examefisico.latest('id')
        examefisico.id = None
    else:
        examefisico = ExameFisico()

    examefisico.profissional = request.user
    examefisico.data_cadastro = datetime.datetime.now()
    examefisico.atendimento = atendimento

    especialidade = Especialidades(request.user)
    form = ExameFisicoForm(request.POST or None, instance=examefisico, medico=especialidade.is_medico(), request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_examefisico', 'Exame Físico registrado com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def antropometria_valores_referencia(request):
    title = 'Valores de Referência'

    return locals()


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def registrar_vacinacao(request, vacinacao_id):
    vacinacao = get_object_or_404(CartaoVacinal, pk=vacinacao_id)

    title = 'Registro de Vacinação'

    form = RegistrarVacinacaoForm(request.POST or None, instance=vacinacao)
    if form.is_valid():
        vinculo_pessoa = request.user.get_vinculo()
        if not vacinacao.profissional and vinculo_pessoa.eh_servidor():
            vacinacao.profissional = Servidor.objects.get(id=vinculo_pessoa.id_relacionamento)
        else:
            # Valida se a pessoa que está alterando a vacina foi a mesma pessoa que a registrou originalmente
            if not vacinacao.pode_alterar_registro_vacina(request.user):
                return httprr('.', 'Esse registro de vacina só pode ser alterado pelo usuário que o registrou.', tag='error')

        vacinacao.externo = form.cleaned_data['externo']
        vacinacao.sem_data = form.cleaned_data['sem_data']
        data_vacinacao = form.cleaned_data['data']
        obs = form.cleaned_data['obs']

        vacinacao_anterior = CartaoVacinal.objects.filter(
            vacina=vacinacao.vacina, prontuario=vacinacao.prontuario, data_vacinacao__isnull=False, id__lt=vacinacao.id
        ).exclude(pk=vacinacao.pk)
        if vacinacao_anterior:
            vacinacao_anterior = vacinacao_anterior.order_by('-data_vacinacao')[0]
            if data_vacinacao:
                if vacinacao_anterior.data_vacinacao and vacinacao_anterior.data_vacinacao > data_vacinacao:
                    return httprr(
                        '.',
                        'A data de aplicação deve ser maior ou igual a {}.'.format(vacinacao_anterior.data_vacinacao.strftime('%d/%m/%Y')),
                        tag='error',
                    )

        if not vacinacao.sem_data and not data_vacinacao:
            return httprr('.', 'Você deve informar uma data de vacinação.', tag='error')
        elif not vacinacao.sem_data and data_vacinacao:
            vacinacao.data_vacinacao = form.cleaned_data['data']

        vacinacao.obs = obs
        vacinacao.save()
        return httprr('..', 'Registro de vacinação adicionado com sucesso.')

    return locals()


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def registrar_previsao(request, vacinacao_id):
    title = 'Registro de Previsão de Vacinação'
    vacinacao = get_object_or_404(CartaoVacinal, pk=vacinacao_id)

    form = RegistrarPrevisaoVacinacaoForm(request.POST or None, instance=vacinacao)
    if form.is_valid():
        previsao = form.cleaned_data['previsao']
        vacinacao.data_prevista = previsao

        vacinacao_anterior = CartaoVacinal.objects.filter(
            vacina=vacinacao.vacina, prontuario=vacinacao.prontuario, data_prevista__isnull=False, id__lt=vacinacao.id
        ).exclude(pk=vacinacao.pk)
        if vacinacao_anterior:
            vacinacao_anterior = vacinacao_anterior.order_by('-data_prevista')[0]
            if vacinacao_anterior.data_prevista and vacinacao_anterior.data_prevista > previsao:
                return httprr(
                    '.', 'O aprazamento deve ter data maior ou igual a {}.'.format(vacinacao_anterior.data_prevista.strftime('%d/%m/%Y')), tag='error'
                )
            else:
                vacinacao.save()
        else:
            vacinacao.save()

        return httprr('..', 'Aprazamento adicionado com sucesso.')

    return locals()


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def adicionar_vacina(request, prontuario_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)

    title = f'Adicionar Vacina - {prontuario.vinculo}'

    form = AdicionarVacinaForm(request.POST or None, prontuario=prontuario)
    if form.is_valid():
        if form.cleaned_data['vacina']:
            vacina = get_object_or_404(Vacina, pk=form.cleaned_data['vacina'].id)

            if vacina not in prontuario.vacinas.all():
                cartaovacinal = CartaoVacinal()
                cartaovacinal.prontuario = prontuario
                cartaovacinal.vacina = vacina
                cartaovacinal.externo = False
                cartaovacinal.numero_dose = 1
                cartaovacinal.save()
            else:
                cartaovacinal = CartaoVacinal()
                cartaovacinal.prontuario = prontuario
                cartaovacinal.vacina = vacina
                cartaovacinal.externo = False
                cartaovacinal.eh_reforco = True
                cartaovacinal.numero_dose = proximo_numero_dose(prontuario, vacina, eh_reforco=True)
                cartaovacinal.save()

            return httprr(f'/saude/adicionar_vacina/{prontuario.id}/?tab=aba_cartao_vacinal', 'Vacina adicionada com sucesso.')

    return locals()


def montar_mensagem_base_resultado_importacao_rnvacina(resultado):
    if resultado.quantidade_importada:
        return f'{resultado.quantidade_importada} nova(s) dose(s) importada(s) do RN+Vacina.'
    return 'Nenhuma novidade encontrada no RN+Vacina.'


def montar_mensagem_resultado_importacao_rnvacina(resultado):
    msg = montar_mensagem_base_resultado_importacao_rnvacina(resultado)
    if resultado.nomes_vacinas_cadastradas:
        msg += ' Vacinas novas cadastradas automaticamente no catálogo (revise em Cadastros > Vacinas): ' + ', '.join(
            resultado.nomes_vacinas_cadastradas
        )
    if resultado.nomes_nao_mapeados:
        msg += ' Itens que não puderam ser processados: ' + ', '.join(resultado.nomes_nao_mapeados)
    return msg


@rtr()
@group_required(Especialidades.GRUPOS_ATENDIMENTO_MEDICO_ENF)
def importar_vacinas_rnvacina_profissional(request, prontuario_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    url_retorno = f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_cartao_vacinal'
    vinculo_solicitante = request.user.get_vinculo()
    if not vinculo_solicitante:
        return httprr(url_retorno, 'Seu usuário não possui um vínculo ativo para solicitar a importação.', tag='error')
    try:
        resultado = importar_vacinas_rnvacina(prontuario, vinculo_solicitante, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)
    except ValidationError as e:
        if settings.DEBUG:
            raise
        return httprr(url_retorno, str(e), tag='error')
    return httprr(url_retorno, montar_mensagem_resultado_importacao_rnvacina(resultado))


@rtr()
@group_required(Especialidades.GRUPOS)
def atendimento_medico_enfermagem(request, atendimento_id):
    title = 'Atendimento Médico/Enfermagem'
    tem_permissao_acesso_atendimento_medico(request.user)

    # Carrega dados do atendimento, cabecalho e do vinculo do usuario
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.ENFERMAGEM_MEDICO)
    atendimento_aberto = atendimento.is_aberto()
    if atendimento.aluno:
        programas = Participacao.objects.filter(aluno=atendimento.get_vinculo(), data_termino__isnull=True)

    pendencias = atendimento.tem_pendencia(request)

    is_coordenador_sistemico = in_group(request.user, 'Coordenador de Saúde Sistêmico')
    especialidade = Especialidades(request.user)
    is_medico = especialidade.is_medico()
    is_enfermagem = especialidade.is_enfermeiro() or especialidade.is_tecnico_enfermagem() or especialidade.is_auxiliar_enfermagem()
    is_fisioterapeuta = especialidade.is_fisioterapeuta()
    # Carrega as fichas do atendimento
    motivo = Motivo.objects.filter(atendimento=atendimento)
    motivo_titulo = motivo.model._meta.verbose_name
    motivo_count = motivo.count()
    motivo_responsavel = None
    if motivo.exists():
        motivo = motivo.latest('id')
        motivo_responsavel = motivo.get_responsavel()

    anamnese = Anamnese.objects.filter(atendimento=atendimento)
    anamnese_titulo = anamnese.model._meta.verbose_name
    anamnese_count = anamnese.count()
    anamnese_responsavel = None
    if anamnese.exists():
        anamnese = anamnese.latest('id')
        anamnese_responsavel = anamnese.get_responsavel()

    cadastrou_antecedentes = False
    cadastrou_processosaudedoenca = False

    antecedentesfamiliares = AntecedentesFamiliares.objects.filter(atendimento=atendimento)
    antecedentesfamiliares_titulo = 'Antecedentes'
    antecedentesfamiliares_count = antecedentesfamiliares.count()
    if antecedentesfamiliares.exists():
        cadastrou_antecedentes = True
        antecedentesfamiliares = antecedentesfamiliares.latest('id')
        antecedentesfamiliares_responsavel = antecedentesfamiliares.get_responsavel()

    processosaudedoenca = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento)
    processosaudedoenca_titulo = 'Processo Saúde-Doença'
    processosaudedoenca_count = processosaudedoenca.count()
    if processosaudedoenca.exists():
        cadastrou_processosaudedoenca = True
        processosaudedoenca = processosaudedoenca.latest('id')
        processosaudedoenca_responsavel = processosaudedoenca.get_responsavel()

    aba_antecedentes_preenchida = cadastrou_antecedentes and cadastrou_processosaudedoenca

    hipotesediagnostica = HipoteseDiagnostica.objects.filter(atendimento=atendimento)
    hipotesediagnostica_titulo = 'Hipótese Diagnóstica'
    hipotesediagnostica_count = hipotesediagnostica.count()

    condutamedica = CondutaMedica.objects.filter(atendimento=atendimento)
    condutamedica_titulo = 'Conduta Médica'
    condutamedica_count = condutamedica.count()

    aba_hipotese_preenchida = hipotesediagnostica.exists() and condutamedica.exists()

    encaminhados_odonto = Atendimento.objects.filter(
        tipo=TipoAtendimento.ODONTOLOGICO, prontuario=atendimento.prontuario, odontograma__encaminhado_enfermagem=True
    )

    intervencaoenfermagem = IntervencaoEnfermagem.objects.filter(atendimento=atendimento).order_by('-id')
    intervencaoenfermagem_titulo = 'Intervenção de Enfermagem'
    intervencaoenfermagem_count = intervencaoenfermagem.count()

    intervencaofisioterapia = IntervencaoFisioterapia.objects.filter(atendimento=atendimento).order_by('-id')
    intervencaofisioterapia_count = intervencaofisioterapia.count()

    tem_registro_intervencao = encaminhados_odonto.exists() or intervencaoenfermagem.exists()

    exclude_fields = ('id', 'data_cadastro', 'atendimento', 'profissional')
    custom_fields = {'get_cadastro_display': Column('Cadastrado por', accessor='get_cadastro_display')}
    campos = ('procedimento_enfermagem', 'descricao')
    sequence = ['procedimento_enfermagem', 'descricao', 'get_cadastro_display']
    table_intervencaoenfermagem = get_table(
        queryset=intervencaoenfermagem, sequence=sequence, custom_fields=custom_fields, fields=campos, exclude_fields=exclude_fields
    )

    return locals()


@rtr()
@group_required(Especialidades.ENFERMAGEM)
@permission_required('rh.eh_servidor')
def adicionar_motivo_atendimento(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Motivo do Atendimento - {atendimento.get_vinculo()}'
    obj = Motivo.objects.filter(atendimento=atendimento.pk)

    if obj.exists():
        obj = obj.latest('id')
        obj.id = None
    else:
        obj = Motivo()

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    obj.escala_dor = obj.escala_dor or 0

    form = MotivoForm(request.POST or None, instance=obj, request=request, initial={'escala_dor': '0', 'temperatura_categoria': '2'})

    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_motivo', 'Motivo do Atendimento registrado com sucesso.')

    return locals()


@rtr()
@group_required(['Médico'])
@permission_required('rh.eh_servidor')
def adicionar_anamnese(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Anamnese - {atendimento.get_vinculo()}'
    obj = Anamnese.objects.filter(atendimento=atendimento.pk)

    if obj.exists():
        obj = obj.latest('id')
        obj.id = None
    else:
        obj = Anamnese()

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = AnamneseForm(request.POST or None, instance=obj, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_anamnese', 'Anamnese registrada com sucesso.')

    return locals()


@rtr()
@group_required(['Médico'])
@permission_required('rh.eh_servidor')
def adicionar_hipotese_diagnostica(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Hipótese Diagnóstica - {atendimento.get_vinculo()}'

    form = HipoteseDiagnosticaForm(request.POST or None)

    if form.is_valid():
        cids = form.cleaned_data['cids']
        for cid in cids:
            novo_cid = HipoteseDiagnostica()
            novo_cid.cid = cid
            novo_cid.sigilo = form.cleaned_data.get('sigilo')
            novo_cid.atendimento = atendimento
            novo_cid.profissional = request.user
            novo_cid.data_cadastro = datetime.datetime.now()
            novo_cid.save()

        AtendimentoEspecialidade.cadastrar(atendimento, request)
        return httprr(
            f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_hipotesediagnostica', 'Hipótese Diagnóstica registrada com sucesso.'
        )

    return locals()


@rtr()
@group_required(['Médico'])
@permission_required('rh.eh_servidor')
def adicionar_conduta_medica(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Conduta Médica - {atendimento.get_vinculo()}'
    obj = CondutaMedica.objects.filter(atendimento=atendimento.pk)

    if obj.exists():
        obj = obj.latest('id')
        obj.id = None
        obj.atendido = False
    else:
        obj = CondutaMedica()

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = CondutaMedicaForm(request.POST or None, instance=obj, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_hipotesediagnostica', 'Conduta Médica registrada com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.ENFERMAGEM)
@permission_required('rh.eh_servidor')
def adicionar_intervencao_enfermagem(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Intervenção de Enfermagem - {atendimento.get_vinculo()}'

    condutas_medicas = CondutaMedica.objects.filter(atendimento=atendimento, encaminhado_enfermagem=True, atendido=False)

    form = IntervencaoEnfermagemForm(request.POST or None, request=request, atendimento=atendimento)

    if form.is_valid():
        for item in form.cleaned_data.get('procedimento_enfermagem'):
            obj = IntervencaoEnfermagem()
            obj.profissional = request.user
            obj.data_cadastro = datetime.datetime.now()
            obj.atendimento = atendimento
            obj.procedimento_enfermagem = item
            obj.conduta_medica = form.cleaned_data.get('conduta_medica')
            obj.descricao = form.cleaned_data.get('descricao')
            obj.save()

        if form.cleaned_data.get('conduta_medica'):
            CondutaMedica.objects.filter(id=form.cleaned_data.get('conduta_medica').id).update(atendido=True)

        AtendimentoEspecialidade.cadastrar(atendimento, request)
        return httprr(
            f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_intervencaoenfermagem',
            'Intervenção de enfermagem registrada com sucesso.',
        )

    return locals()


@rtr()
@group_required(
    [
        'Coordenador de Saúde Sistêmico',
        Especialidades.MEDICO,
        Especialidades.ODONTOLOGO,
        Especialidades.ENFERMEIRO,
        Especialidades.TECNICO_ENFERMAGEM,
        Especialidades.FISIOTERAPEUTA,
        Especialidades.PSICOLOGO,
        Especialidades.NUTRICIONISTA,
        Especialidades.AUXILIAR_DE_ENFERMAGEM,
        'Auditor',
        'Coordenador de Atividades Estudantis Sistêmico',
    ]
)
def estatisticas_atendimentos(request):
    title = 'Estatísticas de Atendimentos'

    atendimentos = Atendimento.objects.all()
    if not request.user.has_group_cached(Especialidades.GRUPOS_VE_GRAFICOS_TODOS):
        atendimento = atendimentos.filter(usuario_aberto__vinculo__setor__uo=get_uo(request.user))

    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    if form.is_valid():
        atendimentos = atendimentos.filter(data_aberto__gte=form.cleaned_data['data_inicio'], data_aberto__lte=form.cleaned_data['data_termino'])
        if form.cleaned_data.get('uo'):
            atendimento = atendimentos.filter(usuario_aberto__vinculo__setor__uo=form.cleaned_data.get('uo'))
    dados = []

    tipo = atendimentos.values('tipo').annotate(qtd=Count('tipo')).order_by('tipo')
    total = 0
    for registro in tipo:
        if registro['tipo'] == TipoAtendimento.AVALIACAO_BIOMEDICA:
            tipo = 'Avaliação Biomédica'
        elif registro['tipo'] == TipoAtendimento.ENFERMAGEM_MEDICO:
            tipo = 'Atendimento Médico/Enfermagem'
        else:
            tipo = 'Outros'
        dados.append([tipo, registro['qtd']])
        total = total + registro['qtd']

    grafico1 = PieChart(
        'grafico1', title='Atendimentos por Tipo', subtitle='Atendimentos contabilizados pelo tipo do atendimento', minPointLength=0, data=dados
    )
    grafico1.id = 'grafico1'

    dados2 = []
    alunos = atendimentos.filter(aluno__isnull=False).count()
    servidor = atendimentos.filter(servidor__isnull=False).count()
    prestador_servico = atendimentos.filter(prestador_servico__isnull=False).count()
    comunidade_externa = atendimentos.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    if alunos > 0:
        dados2.append(['Alunos', alunos])
    if servidor > 0:
        dados2.append(['Servidores', servidor])
    if prestador_servico > 0:
        dados2.append(['Prestadores de Serviço', prestador_servico])
    if comunidade_externa > 0:
        dados2.append(['Comunidade Externa', comunidade_externa])

    grafico2 = PieChart(
        'grafico2',
        title='Atendimentos por Categoria',
        subtitle='Atendimentos contabilizados pela categoria do paciente',
        minPointLength=0,
        data=dados2,
    )
    grafico2.id = 'grafico2'

    dados3 = []
    alunos_atendidos = atendimentos.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_atendidos = atendimentos.filter(servidor__isnull=False).distinct('servidor').count()
    prestador_servico_atendidos = atendimentos.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comunidade_externa_atendidos = (
        atendimentos.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True)
        .distinct('prontuario__vinculo__pessoa__nome')
        .count()
    )

    if alunos_atendidos > 0:
        dados3.append(['Alunos', alunos_atendidos])
    if servidor_atendidos > 0:
        dados3.append(['Servidores', servidor_atendidos])
    if prestador_servico_atendidos > 0:
        dados3.append(['Prestadores de Serviço', prestador_servico_atendidos])
    if comunidade_externa_atendidos > 0:
        dados3.append(['Comunidade Externa', comunidade_externa_atendidos])

    grafico3 = PieChart('grafico3', title='Atendidos por Categoria', subtitle='Pacientes únicos atendidos', minPointLength=0, data=dados3)
    grafico3.id = 'grafico3'

    pie_chart_lists = [grafico2, grafico3, grafico1]

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def atendimento_odontologico(request, atendimento_id):
    title = 'Atendimento Odontológico'

    # Carrega dados do atendimento, cabecalho e do vinculo do usuario
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.ODONTOLOGICO)

    eh_externo = False
    if atendimento.aluno:
        programas = Participacao.objects.filter(aluno=atendimento.get_vinculo(), data_termino__isnull=True)

    elif not atendimento.servidor and not atendimento.prestador_servico:
        eh_externo = True
    is_coordenador_sistemico = in_group(request.user, 'Coordenador de Saúde Sistêmico')

    pendencias = atendimento.tem_pendencia(request)

    especialidade = Especialidades(request.user)
    is_odontologo = especialidade.is_odontologo()
    eh_responsavel = atendimento.usuario_aberto == request.user
    pode_salvar_odontograma = atendimento.is_aberto() and eh_responsavel and is_odontologo
    pode_adicionar_procedimento = is_odontologo or especialidade.is_tecnico_saude_bucal()
    aba_antecedentes_preenchida = False
    processosaudedoenca = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento)
    processosaudedoenca_titulo = 'Processo Saúde-Doença'
    processosaudedoenca_count = processosaudedoenca.count()
    if processosaudedoenca.exists():
        aba_antecedentes_preenchida = True
        processosaudedoenca = processosaudedoenca.latest('id')
        processosaudedoenca_responsavel = processosaudedoenca.get_responsavel()

    # Carrega as fichas do atendimento
    procedimentos = ProcedimentoOdontologico.objects.filter(atendimento=atendimento).order_by('procedimento')
    if procedimentos.exists():
        tipo_consulta = procedimentos.latest('id')
    procedimento_titulo = procedimentos.model._meta.verbose_name_plural
    procedimento_count = procedimentos.count()

    if Odontograma.objects.filter(atendimento=atendimento).exists():
        odontograma = Odontograma.objects.filter(atendimento=atendimento).latest('id')
        odontograma_responsavel = odontograma.get_responsavel()
    else:
        odontograma = Odontograma()

    indice_cpod, indice_c, indice_p, indice_o = odontograma.get_indice_cpod()

    situacoes = SituacaoClinica.objects.exclude(id__in=[SituacaoClinica.CALCULO, SituacaoClinica.SANGRAMENTO])

    exames_periodontais = ExamePeriodontal.objects.filter(atendimento=atendimento).order_by('sextante')
    if exames_periodontais.exists():
        exames_periodontais_responsavel = exames_periodontais.latest('id').get_responsavel()
    avaliacoes_tecidos = ExameEstomatologico.objects.filter(atendimento=atendimento)
    if avaliacoes_tecidos.exists():
        avaliacoes_tecidos = avaliacoes_tecidos.latest('id')
        avaliacoes_tecidos_responsavel = avaliacoes_tecidos.get_responsavel()

    tem_plano_tratamento = False
    plano_tratamento = PlanoTratamento.objects.filter(atendimento=atendimento).order_by('ordem')
    if plano_tratamento.exists():
        tem_plano_tratamento = True
    percepcaosaudebucal = PercepcaoSaudeBucal.objects.filter(atendimento=atendimento)
    percepcaosaudebucal_titulo = 'Percepção da Saúde Bucal'
    percepcaosaudebucal_count = percepcaosaudebucal.count()
    if percepcaosaudebucal.exists():
        percepcaosaudebucal = percepcaosaudebucal.latest('id')
        percepcaosaudebucal_responsavel = percepcaosaudebucal.get_responsavel()
    form = OdontogramaForm(mostra_queixa=True, queixa_principal=odontograma.queixa_principal)
    if request.POST:
        form = OdontogramaForm(request.POST, mostra_queixa=True)
        if form.is_valid():
            if form.cleaned_data['faces']:
                odontograma.dentes_alterados = form.cleaned_data['faces']
                odontograma.atendimento = atendimento
                odontograma.profissional = request.user
                odontograma.data_cadastro = datetime.datetime.now()
            odontograma.queixa_principal = form.cleaned_data.get('queixa_principal')
            odontograma.salvo = True
            odontograma.save()

            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/', 'Odontograma atualizado com sucesso.')

    return locals()


@rtr()
@group_required(['Odontólogo', 'Técnico em Saúde Bucal'])
@permission_required('rh.eh_servidor')
def adicionar_procedimento_odontologico(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)

    title = f'Adicionar Procedimento Odontológico - {atendimento.get_vinculo()}'
    procedimentos = ProcedimentoOdontologico.objects.filter(atendimento=atendimento).order_by('procedimento')
    id_situacao_clinica = None
    odontograma = Odontograma.objects.filter(atendimento=atendimento)
    if odontograma:
        odontograma = odontograma.latest('id')
    else:
        return httprr(
            f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_procedimento',
            'Este paciente não possui um odontograma cadastrado.',
            tag='error',
        )

    especialidade = Especialidades(request.user)

    form = ProcedimentoOdontologicoForm(request.POST or None, eh_dentista=especialidade.is_odontologo())
    if form.is_valid():
        string_alteracoes = form.cleaned_data['faces_marcadas']
        lista_alteracoes = string_alteracoes.split('-')
        lista_alteracoes.remove('')
        for procedimento_escolhido in form.cleaned_data['procedimento']:
            registro_procedimento = ProcedimentoOdontologico()
            registro_procedimento.profissional = request.user
            registro_procedimento.data_cadastro = datetime.datetime.now()
            registro_procedimento.atendimento = atendimento
            registro_procedimento.faces_marcadas = string_alteracoes
            registro_procedimento.regiao_bucal = form.cleaned_data['regiao_bucal']
            registro_procedimento.observacao = form.cleaned_data['observacao']
            registro_procedimento.procedimento = procedimento_escolhido
            registro_procedimento.save()
            if ResultadoProcedimento.objects.filter(procedimento=procedimento_escolhido).exists():
                id_situacao_clinica = f'{ResultadoProcedimento.objects.filter(procedimento=procedimento_escolhido)[0].situacao_clinica_id}'

            for item in lista_alteracoes:
                dente = item[4:6]
                todas_as_faces = False
                if (
                    '_V_' + dente in string_alteracoes
                    and '_P_' + dente in string_alteracoes
                    and '_M_' + dente in string_alteracoes
                    and '_D_' + dente in string_alteracoes
                    and '_O_' + dente in string_alteracoes
                ):
                    todas_as_faces = True
                    if PlanoTratamento.objects.filter(
                        dente=dente, face__icontains='_T_', procedimento=procedimento_escolhido, atendimento=atendimento
                    ).exists():
                        plano_realizado = PlanoTratamento.objects.filter(
                            dente=dente, face__icontains='_T_', procedimento=procedimento_escolhido, atendimento=atendimento
                        )[0]
                        plano_realizado.realizado = True
                        plano_realizado.save()
                if PlanoTratamento.objects.filter(face=item, procedimento=procedimento_escolhido, atendimento=atendimento).exists():
                    plano_realizado = PlanoTratamento.objects.filter(face=item, procedimento=procedimento_escolhido, atendimento=atendimento)[0]
                    plano_realizado.realizado = True
                    plano_realizado.save()

                elif PlanoTratamento.objects.filter(dente=dente, procedimento=procedimento_escolhido, atendimento=atendimento).exists():
                    plano_realizado = PlanoTratamento.objects.filter(dente=dente, procedimento=procedimento_escolhido, atendimento=atendimento)[0]
                    plano_realizado.realizado = True
                    plano_realizado.save()

                if id_situacao_clinica:
                    novo_odontograma = odontograma.dentes_alterados
                    indice = novo_odontograma.find(item)
                    if indice != -1:
                        novo_odontograma = novo_odontograma[: indice + 7] + id_situacao_clinica + novo_odontograma[indice + 9 :]
                    else:
                        modificacao_odontograma = item + f'_{id_situacao_clinica}-'
                        novo_odontograma = novo_odontograma + modificacao_odontograma

                    odontograma.dentes_alterados = novo_odontograma
                    odontograma.save()

        return httprr(f'/saude/adicionar_procedimento_odontologico/{atendimento.id}/', 'Procedimento registrado com sucesso.')

    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def adicionar_odontograma(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)

    title = f'Adicionar Odontograma - {atendimento.get_vinculo()}'
    situacoes = SituacaoClinica.objects.all()
    odontograma = Odontograma.objects.filter(atendimento=atendimento.pk)
    if odontograma.exists():
        odontograma = odontograma.latest('id')
    else:
        odontograma = Odontograma()
    odontograma.profissional = request.user
    odontograma.data_cadastro = datetime.datetime.now()
    odontograma.atendimento = atendimento

    form = OdontogramaForm(request.POST or None, mostra_queixa=False)

    if form.is_valid():
        if form.cleaned_data['faces']:
            odontograma.dentes_alterados = form.cleaned_data['faces']
        odontograma.salvo = True
        odontograma.save()
        AtendimentoEspecialidade.cadastrar(atendimento, request)
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_odontograma', 'Odontograma registrado com sucesso.')

    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def adicionar_exame_periodontal(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    if atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
        tem_permissao(atendimento, request)
    else:
        especialidade = Especialidades(request.user)
        if not especialidade.is_odontologo():
            raise PermissionDenied

    title = f'Adicionar Ocorrência - {atendimento.get_vinculo()}'
    eh_avaliacao_biomedica = request.GET.get('origem')
    exame = ExamePeriodontal()
    exame.profissional = request.user
    exame.data_cadastro = datetime.datetime.now()
    exame.atendimento = atendimento
    exames_cadastrados = ExamePeriodontal.objects.filter(atendimento=atendimento)

    form = ExamePeriodontalForm(request.POST or None, instance=exame, atendimento=atendimento)

    if form.is_valid():
        o = form.save(False)
        texto = ''
        for item in form.cleaned_data.get('sextante'):
            texto = texto + item + '; '
        o.sextante = texto[:-2]
        o.save()
        if eh_avaliacao_biomedica:
            return httprr(f'/saude/adicionar_exame_periodontal/{atendimento.id}/?origem=1', 'Exame periodontal registrado com sucesso.')
        else:
            return httprr(f'/saude/adicionar_exame_periodontal/{atendimento.id}/', 'Exame periodontal registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def editar_exame_periodontal(request, exame_id):
    exame = get_object_or_404(ExamePeriodontal, pk=exame_id)
    atendimento = exame.atendimento
    if atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
        tem_permissao(atendimento, request)
    else:
        especialidade = Especialidades(request.user)
        if not especialidade.is_odontologo():
            raise PermissionDenied

    title = f'Editar Ocorrência - {atendimento.get_vinculo()}'
    exame.profissional = request.user
    exame.data_cadastro = datetime.datetime.now()
    exames_cadastrados = ExamePeriodontal.objects.filter(atendimento=atendimento)

    form = ExamePeriodontalForm(request.POST or None, instance=exame, atendimento=atendimento)

    if form.is_valid():
        o = form.save(False)
        texto = ''
        for item in form.cleaned_data.get('sextante'):
            texto = texto + item + '; '
        o.sextante = texto[:-2]
        o.save()
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_odontograma', 'Exame periodontal editado com sucesso.')
    return locals()


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def deletar_vacina(request, prontuario_id, vacina_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    vacina = get_object_or_404(Vacina, pk=vacina_id)
    vacinas = CartaoVacinal.objects.filter(vacina=vacina, prontuario=prontuario)
    vacinas.delete()
    return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_cartao_vacinal', 'Vacina removida com sucesso.')


def proximo_numero_dose(prontuario, vacina, eh_reforco):
    """Próximo número dentro da série (dose regular ou reforço) desta vacina/prontuário."""
    ultima_dose = CartaoVacinal.objects.filter(vacina=vacina, prontuario=prontuario, eh_reforco=eh_reforco).order_by('-numero_dose')
    if ultima_dose.exists():
        return ultima_dose[0].numero_dose + 1
    return 1


@rtr()
@group_required(['Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
@permission_required('rh.eh_servidor')
def adicionar_dose(request, prontuario_id, vacina_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    vacina = get_object_or_404(Vacina, pk=vacina_id)
    nova_dose = CartaoVacinal()
    nova_dose.vacina = vacina
    nova_dose.prontuario = prontuario
    nova_dose.externo = False
    nova_dose.numero_dose = proximo_numero_dose(prontuario, vacina, eh_reforco=False)
    nova_dose.save()

    return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_cartao_vacinal', 'Dose de Vacina adicionada com sucesso.')


@rtr()
@group_required(['Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
@permission_required('rh.eh_servidor')
def adicionar_reforco(request, prontuario_id, vacina_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    vacina = get_object_or_404(Vacina, pk=vacina_id)

    nova_dose = CartaoVacinal()
    nova_dose.vacina = vacina
    nova_dose.prontuario = prontuario
    nova_dose.externo = False
    nova_dose.eh_reforco = True
    nova_dose.numero_dose = proximo_numero_dose(prontuario, vacina, eh_reforco=True)
    nova_dose.save()

    return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_cartao_vacinal', 'Reforço de Vacina adicionado com sucesso.')


@rtr()
@group_required(Especialidades.GRUPOS)
def adicionar_informacao_adicional(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Informação Adicional - {atendimento.get_vinculo()}'

    obj = InformacaoAdicional()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = InformacaoAdicionalForm(request.POST or None, request=request, instance=obj)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_informacaoadicional', 'Informação adicional registrada com sucesso.')

    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def adicionar_exame_estomatologico(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    if atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
        tem_permissao(atendimento, request)
    else:
        especialidade = Especialidades(request.user)
        if not especialidade.is_odontologo():
            raise PermissionDenied
    title = f'Adicionar Exame Estomatológico - {atendimento.get_vinculo()}'
    avaliacao = ExameEstomatologico.objects.filter(atendimento=atendimento.pk)
    if avaliacao.exists():
        avaliacao = avaliacao.latest('id')
        nova_avaliacao = avaliacao
        nova_avaliacao.pk = None
    else:
        nova_avaliacao = ExameEstomatologico()
    nova_avaliacao.profissional = request.user
    nova_avaliacao.data_cadastro = datetime.datetime.now()
    nova_avaliacao.atendimento = atendimento

    form = ExameEstomatologicoForm(request.POST or None, instance=nova_avaliacao)
    if form.is_valid():
        form.save()
        if atendimento.tipo == TipoAtendimento.AVALIACAO_BIOMEDICA:
            return httprr(f'/saude/avaliacao_biomedica/{atendimento_id}/?tab=aba_odontograma', 'Exame Estomatológico registrado com sucesso.')

        return httprr(f'/saude/atendimento_odontologico/{atendimento_id}/?tab=aba_situacao_clinica', 'Exame Estomatológico registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def indicar_procedimento(request, plano_tratamento_id):
    plano = get_object_or_404(PlanoTratamento, pk=plano_tratamento_id)
    atendimento = plano.atendimento
    tem_permissao(atendimento, request)
    title = 'Indicar Procedimento'
    form = IndicarProcedimentoForm(request.POST or None, instance=plano, situacao_clinica=plano.situacao_clinica, edicao=True)
    if form.is_valid():
        form.save()
        return httprr('..', 'Procedimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def remover_dose(request, registro_id):
    dose = get_object_or_404(CartaoVacinal, pk=registro_id)
    id_retorno = dose.prontuario.vinculo_id
    if dose.pode_remover_dose(request.user):
        dose.delete()
        return httprr(f'/saude/prontuario/{id_retorno}/?tab=aba_cartao_vacinal', 'Dose de Vacina adicionada com sucesso.')
    else:
        return httprr(f'/saude/prontuario/{id_retorno}/?tab=aba_cartao_vacinal', 'Esta dose não pode ser excluída.', tag='error')


@rtr()
@permission_required('saude.view_atividadegrupo')
def estatistica_geral_atendimento(request):
    title = 'Estatísticas de Atendimentos por Curso'

    form = FiltroEstatisticaGeralForm(request.GET or None, request=request)

    titulo_qtd_aluno = 'Total de Alunos Ativos'

    if form.is_valid():
        lista = []
        cursos = CursoCampus.objects.filter(ativo=True, diretoria__setor__uo__sigla=form.cleaned_data['campus']).order_by(
            'diretoria__setor__uo__sigla', 'descricao'
        )

        totais = {
            'total_alunos_ativos': 0,
            'total_atendimentos_abertos': 0,
            'total_atendimentos_fechados': 0,
            'total_atendimentos_cancelados': 0,
            'total_avaliacao_biomedica_em_aberto': 0,
            'total_avaliacao_biomedica_fechado': 0,
            'total_avaliacao_biomedica_cancelado': 0,
            'total_medico_enfermagem_em_aberto': 0,
            'total_medico_enfermagem_fechado': 0,
            'total_medico_enfermagem_cancelado': 0,
            'total_odonto_em_aberto': 0,
            'total_odonto_fechado': 0,
            'total_odonto_cancelado': 0,
            'total_psicologia_em_aberto': 0,
            'total_psicologia_fechado': 0,
            'total_psicologia_cancelado': 0,
            'total_nutricao_em_aberto': 0,
            'total_nutricao_fechado': 0,
            'total_nutricao_cancelado': 0,
            'total_fisio_em_aberto': 0,
            'total_fisio_fechado': 0,
            'total_fisio_cancelado': 0,
            'total_multi_em_aberto': 0,
            'total_multi_fechado': 0,
            'total_multi_cancelado': 0,
        }

        titulo_qtd_aluno = (
            'Total de Alunos Ingressantes'
            if form.cleaned_data['ano_ingresso'] and int(form.cleaned_data['periodo_ingresso']) > 0
            else 'Total de Alunos Ativos'
        )
        if form.cleaned_data.get('modalidade'):
            cursos = cursos.filter(modalidade=form.cleaned_data.get('modalidade'))

        aluno = Aluno.ativos.filter(curso_campus__in=cursos)

        if form.cleaned_data.get('ano_ingresso'):
            aluno = aluno.filter(ano_letivo=form.cleaned_data.get('ano_ingresso'))
        if form.cleaned_data['ano_ingresso'] and int(form.cleaned_data['periodo_ingresso']) > 0:
            aluno = aluno.filter(ano_letivo=form.cleaned_data['ano_ingresso'], periodo_letivo=form.cleaned_data['periodo_ingresso'])
        if form.cleaned_data.get('modalidade'):
            aluno = aluno.filter(curso_campus__modalidade=form.cleaned_data.get('modalidade'))

        if aluno.exists():
            for curso in cursos:
                alunos_ativos_curso = aluno.filter(curso_campus=curso)

                atendimentos = Atendimento.objects.filter(aluno__in=alunos_ativos_curso)
                atendimentos_avaliacao_biomedica = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.AVALIACAO_BIOMEDICA)
                atendimentos_medico_enfermagem = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.ENFERMAGEM_MEDICO)
                atendimentos_odonto = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.ODONTOLOGICO)
                atendimentos_psicologia = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.PSICOLOGICO)
                atendimentos_nutricao = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.NUTRICIONAL)
                atendimentos_fisio = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.FISIOTERAPIA)
                atendimentos_multi = Atendimento.objects.filter(aluno__in=alunos_ativos_curso, tipo=TipoAtendimento.MULTIDISCIPLINAR)

                linha = {}
                linha['curso'] = curso
                linha['qtd_alunos_ativos'] = alunos_ativos_curso.count()
                linha['qtd_atendimentos_abertos'] = atendimentos.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['qtd_atendimentos_fechados'] = atendimentos.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['qtd_atendimentos_cancelados'] = atendimentos.filter(situacao=SituacaoAtendimento.CANCELADO).count()
                linha['avaliacao_biomedica_em_aberto'] = atendimentos_avaliacao_biomedica.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['avaliacao_biomedica_fechado'] = atendimentos_avaliacao_biomedica.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['avaliacao_biomedica_cancelado'] = atendimentos_avaliacao_biomedica.filter(situacao=SituacaoAtendimento.CANCELADO).count()
                linha['medico_enfermagem_em_aberto'] = atendimentos_medico_enfermagem.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['medico_enfermagem_fechado'] = atendimentos_medico_enfermagem.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['medico_enfermagem_cancelado'] = atendimentos_medico_enfermagem.filter(situacao=SituacaoAtendimento.CANCELADO).count()
                linha['odonto_em_aberto'] = atendimentos_odonto.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['odonto_fechado'] = atendimentos_odonto.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['odonto_cancelado'] = atendimentos_odonto.filter(situacao=SituacaoAtendimento.CANCELADO).count()
                linha['psicologia_em_aberto'] = atendimentos_psicologia.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['psicologia_fechado'] = atendimentos_psicologia.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['psicologia_cancelado'] = atendimentos_psicologia.filter(situacao=SituacaoAtendimento.CANCELADO).count()
                linha['nutricao_em_aberto'] = atendimentos_nutricao.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['nutricao_fechado'] = atendimentos_nutricao.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['nutricao_cancelado'] = atendimentos_nutricao.filter(situacao=SituacaoAtendimento.CANCELADO).count()

                linha['fisio_em_aberto'] = atendimentos_fisio.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['fisio_fechado'] = atendimentos_fisio.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['fisio_cancelado'] = atendimentos_fisio.filter(situacao=SituacaoAtendimento.CANCELADO).count()

                linha['multi_em_aberto'] = atendimentos_multi.filter(situacao=SituacaoAtendimento.ABERTO).count()
                linha['multi_fechado'] = atendimentos_multi.filter(situacao=SituacaoAtendimento.FECHADO).count()
                linha['multi_cancelado'] = atendimentos_multi.filter(situacao=SituacaoAtendimento.CANCELADO).count()

                totais['total_alunos_ativos'] += linha.get('qtd_alunos_ativos')
                totais['total_atendimentos_abertos'] += linha.get('qtd_atendimentos_abertos')
                totais['total_atendimentos_fechados'] += linha.get('qtd_atendimentos_fechados')
                totais['total_atendimentos_cancelados'] += linha.get('qtd_atendimentos_cancelados')
                totais['total_avaliacao_biomedica_em_aberto'] += linha.get('avaliacao_biomedica_em_aberto')
                totais['total_avaliacao_biomedica_fechado'] += linha.get('avaliacao_biomedica_fechado')
                totais['total_avaliacao_biomedica_cancelado'] += linha.get('avaliacao_biomedica_cancelado')
                totais['total_medico_enfermagem_em_aberto'] += linha.get('medico_enfermagem_em_aberto')
                totais['total_medico_enfermagem_fechado'] += linha.get('medico_enfermagem_fechado')
                totais['total_medico_enfermagem_cancelado'] += linha.get('medico_enfermagem_cancelado')
                totais['total_odonto_em_aberto'] += linha.get('odonto_em_aberto')
                totais['total_odonto_fechado'] += linha.get('odonto_fechado')
                totais['total_odonto_cancelado'] += linha.get('odonto_cancelado')
                totais['total_psicologia_em_aberto'] += linha.get('psicologia_em_aberto')
                totais['total_psicologia_fechado'] += linha.get('psicologia_fechado')
                totais['total_psicologia_cancelado'] += linha.get('psicologia_cancelado')
                totais['total_nutricao_em_aberto'] += linha.get('nutricao_em_aberto')
                totais['total_nutricao_fechado'] += linha.get('nutricao_fechado')
                totais['total_nutricao_cancelado'] += linha.get('nutricao_cancelado')
                totais['total_fisio_em_aberto'] += linha.get('fisio_em_aberto')
                totais['total_fisio_fechado'] += linha.get('fisio_fechado')
                totais['total_fisio_cancelado'] += linha.get('fisio_cancelado')
                totais['total_multi_em_aberto'] += linha.get('multi_em_aberto')
                totais['total_multi_fechado'] += linha.get('multi_fechado')
                totais['total_multi_cancelado'] += linha.get('multi_cancelado')

                lista.append(linha)

    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def registrar_execucao_plano(request, plano_tratamento_id):
    plano = get_object_or_404(PlanoTratamento, pk=plano_tratamento_id)
    atendimento = plano.atendimento
    tem_permissao(atendimento, request)
    plano.realizado = True
    plano.save()

    face = plano.face
    procedimento = ProcedimentoOdontologico()
    procedimento.profissional = request.user
    procedimento.data_cadastro = datetime.datetime.now()
    procedimento.atendimento = atendimento
    procedimento.procedimento = plano.procedimento
    if request.GET.get('obs'):
        procedimento.observacao = request.GET.get('obs')

    if plano.dente:
        if face:
            if '_T_' in face:
                texto_face = f'{face[0]}_V_{plano.dente}-'
                texto_face = texto_face + f'{face[0]}_P_{plano.dente}-'
                texto_face = texto_face + f'{face[0]}_M_{plano.dente}-'
                texto_face = texto_face + f'{face[0]}_D_{plano.dente}-'
                texto_face = texto_face + f'{face[0]}_O_{plano.dente}-'
                procedimento.faces_marcadas = texto_face
            else:
                procedimento.faces_marcadas = face + '-'
    else:
        procedimento.regiao_bucal = plano.sextante
    procedimento.save()
    odontograma = Odontograma.objects.filter(atendimento=atendimento)
    if odontograma:
        odontograma = odontograma.latest('id')

        if ResultadoProcedimento.objects.filter(procedimento=plano.procedimento).exists():
            id_situacao_clinica = f'{ResultadoProcedimento.objects.filter(procedimento=plano.procedimento)[0].situacao_clinica_id}'

            if id_situacao_clinica and face:
                novo_odontograma = odontograma.dentes_alterados

                string_alteracoes = procedimento.faces_marcadas
                lista_alteracoes = string_alteracoes.split('-')

                for item in lista_alteracoes:
                    if item != '':
                        indice = novo_odontograma.find(item)
                        if indice != -1:
                            novo_odontograma = novo_odontograma[: indice + 7] + id_situacao_clinica + novo_odontograma[indice + 9 :]
                        else:
                            modificacao_odontograma = item + f'_{id_situacao_clinica}-'
                            novo_odontograma = novo_odontograma + modificacao_odontograma

                        odontograma.dentes_alterados = novo_odontograma
                        odontograma.save()

    return httprr(f'/saude/atendimento_odontologico/{plano.atendimento_id}/?tab=aba_plano_tratamento', 'Execução registrada com sucesso.')


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def excluir_intervencao(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    tem_permissao(atendimento, request)
    if not request.POST.getlist('action'):
        raise PermissionDenied

    if request.POST.getlist('action')[0] == 'Remover':
        deletar = request.POST.getlist('registros')
        if deletar:
            for item in deletar:
                plano = get_object_or_404(PlanoTratamento, pk=int(item))
                plano.delete()
            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_plano_tratamento', 'Intervenção excluída com sucesso.')
        else:
            return httprr(
                f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_plano_tratamento', 'Nenhuma intervenção selecionada.', tag='error'
            )

    elif request.POST.getlist('action')[0] == 'Ordenar':
        ordenar = request.POST.getlist('ordens')
        if ordenar:
            lista = list(PlanoTratamento.objects.filter(atendimento=atendimento).order_by('ordem').values_list('id', flat=True))
            for idx, item in enumerate(ordenar, 0):
                if item:
                    plano = PlanoTratamento.objects.get(id=lista[idx])
                    plano.ordem = int(item)
                    plano.save()
            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_plano_tratamento', 'Ordenação alterada com sucesso.')

    elif request.POST.getlist('action')[0] == 'Agregar':
        registros = request.POST.getlist('registros')
        faces = None
        dente = None
        situacao = False
        procedimento = False
        descricao_sextante = []

        for registro in registros:
            plano = get_object_or_404(PlanoTratamento, pk=int(registro))
            if not dente:
                if plano.dente:
                    dente = plano.dente
                elif plano.sextante:
                    if (situacao and situacao == plano.situacao_clinica) or (not situacao and not descricao_sextante):
                        descricao_sextante.append(plano.sextante)
                situacao = plano.situacao_clinica
                procedimento = plano.procedimento
            if plano.dente == dente:
                if (situacao and situacao == plano.situacao_clinica) or not situacao:
                    if faces:
                        faces = faces + '-' + plano.face
                    else:
                        faces = plano.face

        if descricao_sextante or dente:
            registro_agregado = PlanoTratamento()
            if descricao_sextante:
                registro_agregado.sextante = ', '.join(descricao_sextante)
            elif dente:
                registro_agregado.dente = dente
            registro_agregado.atendimento = atendimento
            if situacao:
                registro_agregado.situacao_clinica = situacao
            if faces:
                registro_agregado.face = faces
            if procedimento:
                registro_agregado.procedimento = procedimento

            for registro in registros:
                plano = get_object_or_404(PlanoTratamento, pk=int(registro))
                if not descricao_sextante or plano.sextante in descricao_sextante:
                    plano.delete()

            registro_agregado.ordem = registro_agregado.get_ordem()
            registro_agregado.save()

            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_plano_tratamento', 'Agregação realizada com sucesso.')

        else:
            return httprr(
                f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_plano_tratamento',
                'Não é possível agregar registros de dentes ou sextantes distintos.',
                tag='error',
            )


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def adicionar_intervencao(request, atendimento_id):
    title = 'Adicionar Intervenção'
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    tem_permissao(atendimento, request)
    nova_intervencao = PlanoTratamento()
    nova_intervencao.profissional = request.user
    nova_intervencao.data_cadastro = datetime.datetime.now()
    nova_intervencao.atendimento = atendimento

    form = AdicionarIntervencaoOdontoForm(request.POST or None, instance=nova_intervencao)
    if form.is_valid():
        for proc in form.cleaned_data.get('procedimentos'):
            if form.cleaned_data.get('dente') != '0':
                if form.cleaned_data['dente'] in PlanoTratamento.ARCADA_INFANTIL:
                    texto_face = 'I_'
                else:
                    texto_face = 'A_'

                if form.cleaned_data['face'] != PlanoTratamento.TODAS_FACES:
                    if form.cleaned_data['face'] == PlanoTratamento.VESTIBULAR:
                        texto_face = texto_face + 'V_'
                    elif form.cleaned_data['face'] == PlanoTratamento.PALATAL:
                        texto_face = texto_face + 'P_'
                    elif form.cleaned_data['face'] == PlanoTratamento.MESSIAL:
                        texto_face = texto_face + 'M_'
                    elif form.cleaned_data['face'] == PlanoTratamento.DISTAL:
                        texto_face = texto_face + 'D_'
                    elif form.cleaned_data['face'] == PlanoTratamento.OCLUSAL:
                        texto_face = texto_face + 'O_'
                    elif form.cleaned_data['face'] == PlanoTratamento.CERVICAL:
                        texto_face = texto_face + 'C_'
                    elif form.cleaned_data['face'] == PlanoTratamento.RAIZ:
                        texto_face = texto_face + 'R_'

                    texto_face = texto_face + str(form.cleaned_data['dente'])

                    o = form.save(False)
                    o.face = texto_face
                    o.ordem = o.get_ordem()
                    o.sextante = None
                    o.procedimento = proc
                    o.save()
                else:
                    v = form.save(False)
                    v.face = texto_face + 'T_{}'.format(form.cleaned_data['dente'])
                    v.id = None
                    v.ordem = v.get_ordem()
                    v.sextante = None
                    v.procedimento = proc
                    v.save()
            else:
                o = form.save(False)
                o.dente = None
                o.ordem = o.get_ordem()
                o.face = None
                o.procedimento = proc
                o.save()
            if 'Exodontia ' in proc.denominacao:
                sutura = nova_intervencao
                sutura.id = None
                sutura.ordem = nova_intervencao.get_ordem()
                sutura.procedimento = ProcedimentoOdontologia.objects.get(denominacao='Sutura')
                sutura.save()

                remocao_sutura = nova_intervencao
                remocao_sutura.id = None
                remocao_sutura.ordem = nova_intervencao.get_ordem()
                remocao_sutura.procedimento = ProcedimentoOdontologia.objects.get(denominacao='Remoção de Sutura')
                remocao_sutura.save()
        return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_plano_tratamento', 'Intervenção cadastrada com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def cadastrar_pessoa_externa(request):
    title = 'Cadastrar Pessoa Externa'
    form = PessoaExternaForm(request.POST or None)
    if form.is_valid():
        registro = form.save()
        return httprr(f'/saude/prontuario/{registro.get_vinculo().id}/')

    return locals()


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def gerar_plano_tratamento(request, odontograma_id):
    odontograma = get_object_or_404(Odontograma, pk=odontograma_id)
    atendimento = odontograma.atendimento
    tem_permissao(atendimento, request)
    crior_plano = False
    exame_clinico = get_object_or_404(ProcedimentoOdontologia, pk=ProcedimentoOdontologia.EXAME_CLINICO)
    if not PlanoTratamento.objects.filter(atendimento=odontograma.atendimento, sextante=ExamePeriodontal.S1_S6, procedimento=exame_clinico).exists():
        novo_plano = PlanoTratamento()
        novo_plano.atendimento = odontograma.atendimento
        novo_plano.profissional = request.user
        novo_plano.data_cadastro = datetime.datetime.now()
        novo_plano.sextante = ExamePeriodontal.S1_S6
        novo_plano.procedimento = exame_clinico
        novo_plano.ordem = novo_plano.get_ordem()
        novo_plano.save()
        crior_plano = True

    orientacao_exame_bucal = get_object_or_404(ProcedimentoOdontologia, pk=ProcedimentoOdontologia.ORIENTACAO_HIGIENE_BUCAL)
    if not PlanoTratamento.objects.filter(
        atendimento=odontograma.atendimento, sextante=ExamePeriodontal.S1_S6, procedimento=orientacao_exame_bucal
    ).exists():
        novo_plano = PlanoTratamento()
        novo_plano.atendimento = odontograma.atendimento
        novo_plano.profissional = request.user
        novo_plano.data_cadastro = datetime.datetime.now()
        novo_plano.sextante = ExamePeriodontal.S1_S6
        novo_plano.procedimento = orientacao_exame_bucal
        novo_plano.ordem = novo_plano.get_ordem()
        novo_plano.save()
        crior_plano = True

    for item in odontograma.dentes_alterados_lista():
        dente = item[4:6]
        id_situacao = item[7:]
        situacao = SituacaoClinica.objects.get(id=id_situacao)
        if situacao.id not in [
            SituacaoClinica.DENTE_AUSENTE_EXTRAIDO_OUTRAS_RAZOES,
            SituacaoClinica.DENTE_EXTRAIDO_CARIE,
            SituacaoClinica.RESTAURACAO_COROA_SATISFATORIA,
            SituacaoClinica.TRAT_ENDODONTICO_CONCLUIDO,
            SituacaoClinica.DENTE_SELADO,
            SituacaoClinica.IMPLANTE,
            SituacaoClinica.PERMANENCIA_DECIDUO,
        ]:
            if situacao.id in [
                SituacaoClinica.TRAT_ENDODONTICO_INDICADO,
                SituacaoClinica.EXODONTIA_POR_CARIE,
                SituacaoClinica.EXODONTIA_POR_OUTROS_MOTIVOS,
            ]:
                face_marcada = item[0:1] + '_T_' + item[4:6]
                if not PlanoTratamento.objects.filter(
                    atendimento=odontograma.atendimento, dente=dente, face=face_marcada, situacao_clinica=situacao
                ).exists():
                    novo_plano = PlanoTratamento()
                    novo_plano.atendimento = odontograma.atendimento
                    novo_plano.profissional = request.user
                    novo_plano.data_cadastro = datetime.datetime.now()
                    novo_plano.dente = dente
                    novo_plano.face = face_marcada
                    novo_plano.situacao_clinica = situacao
                    novo_plano.ordem = novo_plano.get_ordem()
                    novo_plano.save()
                    crior_plano = True
            else:
                if not PlanoTratamento.objects.filter(
                    atendimento=odontograma.atendimento, dente=dente, face=item[:-3], situacao_clinica=situacao
                ).exists():
                    novo_plano = PlanoTratamento()
                    novo_plano.atendimento = odontograma.atendimento
                    novo_plano.profissional = request.user
                    novo_plano.data_cadastro = datetime.datetime.now()
                    novo_plano.dente = dente
                    novo_plano.face = item[:-3]
                    novo_plano.situacao_clinica = situacao
                    novo_plano.ordem = novo_plano.get_ordem()
                    novo_plano.save()
                    crior_plano = True

    for item in ExamePeriodontal.objects.filter(atendimento=odontograma.atendimento, resolvido=False):
        if item.ocorrencia == ExamePeriodontal.CALCULO:
            sextantes = item.sextante.split(';')
            for sextante in sextantes:
                situacao = get_object_or_404(SituacaoClinica, pk=SituacaoClinica.CALCULO)
                if not PlanoTratamento.objects.filter(atendimento=odontograma.atendimento, sextante=sextante, situacao_clinica=situacao).exists():
                    novo_plano = PlanoTratamento()
                    novo_plano.atendimento = odontograma.atendimento
                    novo_plano.profissional = request.user
                    novo_plano.data_cadastro = datetime.datetime.now()
                    novo_plano.sextante = f'{sextante}'
                    novo_plano.situacao_clinica = situacao
                    novo_plano.ordem = novo_plano.get_ordem()
                    novo_plano.save()
                    crior_plano = True
        elif item.ocorrencia == ExamePeriodontal.SANGRAMENTO:
            sextantes = item.sextante.split(';')
            for sextante in sextantes:
                situacao = get_object_or_404(SituacaoClinica, pk=SituacaoClinica.SANGRAMENTO)
                if not PlanoTratamento.objects.filter(atendimento=odontograma.atendimento, sextante=sextante, situacao_clinica=situacao).exists():
                    novo_plano = PlanoTratamento()
                    novo_plano.atendimento = odontograma.atendimento
                    novo_plano.profissional = request.user
                    novo_plano.data_cadastro = datetime.datetime.now()
                    novo_plano.sextante = f'{sextante}'
                    novo_plano.situacao_clinica = situacao
                    novo_plano.ordem = novo_plano.get_ordem()
                    novo_plano.save()
                    crior_plano = True

    aplicacao_topica_fluor = get_object_or_404(ProcedimentoOdontologia, pk=ProcedimentoOdontologia.APLICACAO_TOPICA_FLUOR)
    if not PlanoTratamento.objects.filter(
        atendimento=odontograma.atendimento, sextante=ExamePeriodontal.S1_S6, procedimento=aplicacao_topica_fluor
    ).exists():
        novo_plano = PlanoTratamento()
        novo_plano.atendimento = odontograma.atendimento
        novo_plano.profissional = request.user
        novo_plano.data_cadastro = datetime.datetime.now()
        novo_plano.sextante = ExamePeriodontal.S1_S6
        novo_plano.procedimento = aplicacao_topica_fluor
        novo_plano.ordem = novo_plano.get_ordem()
        novo_plano.save()
        crior_plano = True

    profilaxia = get_object_or_404(ProcedimentoOdontologia, pk=ProcedimentoOdontologia.PROFILAXIA)
    if not PlanoTratamento.objects.filter(atendimento=odontograma.atendimento, sextante=ExamePeriodontal.S1_S6, procedimento=profilaxia).exists():
        novo_plano = PlanoTratamento()
        novo_plano.atendimento = odontograma.atendimento
        novo_plano.profissional = request.user
        novo_plano.data_cadastro = datetime.datetime.now()
        novo_plano.sextante = ExamePeriodontal.S1_S6
        novo_plano.procedimento = profilaxia
        novo_plano.ordem = novo_plano.get_ordem()
        novo_plano.save()
        crior_plano = True

    if crior_plano:
        return httprr(
            f'/saude/atendimento_odontologico/{odontograma.atendimento_id}/?tab=aba_plano_tratamento', 'Plano de Tratamento criado com sucesso.'
        )
    else:
        return httprr(
            f'/saude/atendimento_odontologico/{odontograma.atendimento_id}/?tab=aba_plano_tratamento',
            'Não há nenhuma alteração no odontograma para gerar um plano de tratamento.',
            tag='error',
        )


@rtr()
@permission_required('saude.view_prontuario')
def indicadores(request: HttpRequest) -> dict:
    title = 'Indicadores'

    atendimentos = Atendimento.objects.all()

    if not request.user.has_group_cached(Especialidades.GRUPOS_RELATORIOS_SISTEMICO):
        atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=get_uo(request.user))

    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    if form.is_valid():
        atendimentos = _filtrar_atendimentos_por_periodo_e_campus(atendimentos, form.cleaned_data)

    avaliacao_biomedica = atendimentos.filter(tipo=TipoAtendimento.AVALIACAO_BIOMEDICA)
    atendimentos_medicos = atendimentos.filter(tipo=TipoAtendimento.ENFERMAGEM_MEDICO, condutamedica__isnull=False).distinct()
    atendimentos_enfermagem = atendimentos.filter(tipo=TipoAtendimento.ENFERMAGEM_MEDICO, intervencaoenfermagem__isnull=False).distinct()
    atendimentos_odontologico = atendimentos.filter(tipo=TipoAtendimento.ODONTOLOGICO).distinct()
    atendimentos_psicologico = atendimentos.filter(tipo=TipoAtendimento.PSICOLOGICO).distinct()
    atendimentos_nutricional = atendimentos.filter(tipo=TipoAtendimento.NUTRICIONAL).distinct()
    atendimentos_fisioterapia = atendimentos.filter(tipo=TipoAtendimento.FISIOTERAPIA).distinct()
    atendimentos_multidisciplinares = atendimentos.filter(tipo=TipoAtendimento.MULTIDISCIPLINAR).distinct()

    dados2 = []
    aluno_tipo_aval_bio = avaliacao_biomedica.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_aval_bio = avaliacao_biomedica.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_aval_bio = avaliacao_biomedica.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_aval_bio = avaliacao_biomedica.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_medico = atendimentos_medicos.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_medico = atendimentos_medicos.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_medico = atendimentos_medicos.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_medico = atendimentos_medicos.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_enf = atendimentos_enfermagem.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_enf = atendimentos_enfermagem.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_enf = atendimentos_enfermagem.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_enf = atendimentos_enfermagem.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_odonto = atendimentos_odontologico.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_odonto = atendimentos_odontologico.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_odonto = atendimentos_odontologico.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_odonto = atendimentos_odontologico.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_psicologia = atendimentos_psicologico.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_psicologia = atendimentos_psicologico.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_psicologia = atendimentos_psicologico.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_psicologia = atendimentos_psicologico.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_nutricao = atendimentos_nutricional.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_nutricao = atendimentos_nutricional.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_nutricao = atendimentos_nutricional.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_nutricao = atendimentos_nutricional.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_fisio = atendimentos_fisioterapia.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_fisio = atendimentos_fisioterapia.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_fisio = atendimentos_fisioterapia.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_fisio = atendimentos_fisioterapia.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    aluno_tipo_multi = atendimentos_multidisciplinares.filter(aluno__isnull=False).distinct('aluno').count()
    servidor_tipo_multi = atendimentos_multidisciplinares.filter(servidor__isnull=False).distinct('servidor').count()
    prest_serv_tipo_multi = atendimentos_multidisciplinares.filter(prestador_servico__isnull=False).distinct('prestador_servico').count()
    comun_ext_tipo_multi = atendimentos_multidisciplinares.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True).count()

    series2 = []

    serie = ['Alunos']
    serie.append(aluno_tipo_aval_bio)
    serie.append(aluno_tipo_medico)
    serie.append(aluno_tipo_enf)
    serie.append(aluno_tipo_odonto)
    serie.append(aluno_tipo_psicologia)
    serie.append(aluno_tipo_nutricao)
    serie.append(aluno_tipo_fisio)
    serie.append(aluno_tipo_multi)
    series2.append(serie)

    serie = ['Servidores']
    serie.append(servidor_tipo_aval_bio)
    serie.append(servidor_tipo_medico)
    serie.append(servidor_tipo_enf)
    serie.append(servidor_tipo_odonto)
    serie.append(servidor_tipo_psicologia)
    serie.append(servidor_tipo_nutricao)
    serie.append(servidor_tipo_fisio)
    serie.append(servidor_tipo_multi)
    series2.append(serie)

    serie = ['Prestadores de Serviço']
    serie.append(prest_serv_tipo_aval_bio)
    serie.append(prest_serv_tipo_medico)
    serie.append(prest_serv_tipo_enf)
    serie.append(prest_serv_tipo_odonto)
    serie.append(prest_serv_tipo_psicologia)
    serie.append(prest_serv_tipo_nutricao)
    serie.append(prest_serv_tipo_fisio)
    serie.append(prest_serv_tipo_multi)
    series2.append(serie)

    serie = ['Comunidade Externa']
    serie.append(comun_ext_tipo_aval_bio)
    serie.append(comun_ext_tipo_medico)
    serie.append(comun_ext_tipo_enf)
    serie.append(comun_ext_tipo_odonto)
    serie.append(comun_ext_tipo_psicologia)
    serie.append(comun_ext_tipo_nutricao)
    serie.append(comun_ext_tipo_fisio)
    serie.append(comun_ext_tipo_multi)
    series2.append(serie)

    groups = ['Avaliação Biomédica', 'Médico', 'Enfermagem', 'Odontologia', 'Psicologia', 'Nutrição', 'Fisioterapia', 'Multidisciplinar']

    grafico2 = GroupedColumnChart(
        'grafico2',
        title='Atendidos por Vínculo e Tipo de Atendimento',
        subtitle='Quantidade de pacientes únicos atendidos',
        data=series2,
        groups=groups,
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )
    grafico2.id = 'grafico2'

    alunos = atendimentos.filter(aluno__isnull=False)
    servidor = atendimentos.filter(servidor__isnull=False)
    prestador_servico = atendimentos.filter(prestador_servico__isnull=False)
    comunidade_externa = atendimentos.filter(aluno__isnull=True, servidor__isnull=True, prestador_servico__isnull=True)

    dados3 = _fatias_com_quantidade(
        [
            ('Alunos', alunos.count()),
            ('Servidores', servidor.count()),
            ('Prestadores de Serviço', prestador_servico.count()),
            ('Comunidade Externa', comunidade_externa.count()),
        ]
    )

    grafico3 = PieChart(
        'grafico3', title='Atendimentos por Vínculo', subtitle='Quantidade de atendimentos por vínculo do paciente', minPointLength=0, data=dados3
    )
    grafico3.id = 'grafico3'

    alunos_atendidos = alunos.distinct('aluno').count()
    servidor_atendidos = servidor.distinct('servidor').count()
    prestador_servico_atendidos = prestador_servico.distinct('prestador_servico').count()
    comunidade_externa_atendidos = comunidade_externa.distinct('prontuario__vinculo').count()

    dados4 = _fatias_com_quantidade(
        [
            ('Alunos', alunos_atendidos),
            ('Servidores', servidor_atendidos),
            ('Prestadores de Serviço', prestador_servico_atendidos),
            ('Comunidade Externa', comunidade_externa_atendidos),
        ]
    )

    grafico4 = PieChart(
        'grafico4',
        title='Atendidos por Vínculo',
        subtitle='Quantidade de pacientes únicos atendidos por vínculo do paciente',
        minPointLength=0,
        data=dados4,
    )
    grafico4.id = 'grafico4'

    dados5 = []

    alunos_aval_bio = avaliacao_biomedica.filter(aluno__isnull=False).distinct('aluno')
    alunos_tipo_medico = atendimentos_medicos.filter(aluno__isnull=False).distinct('aluno')
    alunos_tipo_enf = atendimentos_enfermagem.filter(aluno__isnull=False).distinct('aluno')
    alunos_tipo_odonto = atendimentos_odontologico.filter(aluno__isnull=False).distinct('aluno')
    alunos_tipo_psicologia = atendimentos_psicologico.filter(aluno__isnull=False).distinct('aluno')
    alunos_tipo_fisio = atendimentos_fisioterapia.filter(aluno__isnull=False).distinct('aluno')

    participantes = Participacao.abertas.all()
    alunos_aval_bio_part = alunos_aval_bio.filter(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_aval_bio_nao_part = alunos_aval_bio.exclude(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_medico_part = alunos_tipo_medico.filter(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_medico_nao_part = alunos_tipo_medico.exclude(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_enf_part = alunos_tipo_enf.filter(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_enf_nao_part = alunos_tipo_enf.exclude(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_odonto_part = alunos_tipo_odonto.filter(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_odonto_nao_part = alunos_tipo_odonto.exclude(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_psicologia_part = alunos_tipo_psicologia.filter(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_psicologia_nao_part = alunos_tipo_psicologia.exclude(aluno__in=participantes.values_list('aluno', flat=True)).count()

    alunos_tipo_fisio_part = alunos_tipo_fisio.filter(aluno__in=participantes.values_list('aluno', flat=True)).count()
    alunos_tipo_fisio_nao_part = alunos_tipo_fisio.exclude(aluno__in=participantes.values_list('aluno', flat=True)).count()
    series2 = []

    serie = ['Avaliação Biomédica']
    serie.append(alunos_aval_bio_part)
    serie.append(alunos_aval_bio_nao_part)
    series2.append(serie)

    serie = ['Médicos']
    serie.append(alunos_tipo_medico_part)
    serie.append(alunos_tipo_medico_nao_part)
    series2.append(serie)

    serie = ['Enfermagem']
    serie.append(alunos_tipo_enf_part)
    serie.append(alunos_tipo_enf_nao_part)
    series2.append(serie)

    serie = ['Odontologia']
    serie.append(alunos_tipo_odonto_part)
    serie.append(alunos_tipo_odonto_nao_part)
    series2.append(serie)

    serie = ['Psicologia']
    serie.append(alunos_tipo_psicologia_part)
    serie.append(alunos_tipo_psicologia_nao_part)
    series2.append(serie)

    serie = ['Fisioterapia']
    serie.append(alunos_tipo_fisio_part)
    serie.append(alunos_tipo_fisio_nao_part)
    series2.append(serie)

    groups = []
    for tipo in ['Participantes', 'Não Participantes']:
        groups.append(tipo)

    grafico5 = GroupedColumnChart(
        'grafico5',
        title='Atendidos por Categoria Profissional e Participação em Programa',
        subtitle='Quantidade de alunos únicos atendidos por categoria profissional, participantes ou não de programas',
        data=series2,
        groups=groups,
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )

    grafico5.id = 'grafico5'

    alunos_ensino_medio_integrado = avaliacao_biomedica.filter(aluno__curso_campus__modalidade=Modalidade.INTEGRADO)
    total_alunos = Aluno.objects.filter(curso_campus__modalidade=Modalidade.INTEGRADO)
    if not request.user.has_group_cached(Especialidades.GRUPOS_RELATORIOS_SISTEMICO):
        total_alunos = total_alunos.filter(curso_campus__diretoria__setor__uo=get_uo(request.user))

    if form.is_valid() and form.cleaned_data.get('uo'):
        total_alunos = total_alunos.filter(curso_campus__diretoria__setor__uo=form.cleaned_data.get('uo'))

    if form.is_valid() and form.cleaned_data.get('data_inicio'):
        alunos_ensino_medio_integrado = alunos_ensino_medio_integrado.filter(
            aluno__data_matricula__date__gte=form.cleaned_data['data_inicio'], aluno__data_matricula__date__lte=form.cleaned_data['data_termino']
        )
        total_alunos = total_alunos.filter(
            data_matricula__date__gte=form.cleaned_data['data_inicio'], data_matricula__date__lte=form.cleaned_data['data_termino']
        )
    else:
        alunos_ensino_medio_integrado = alunos_ensino_medio_integrado.filter(aluno__data_matricula__year=datetime.datetime.now().year)
        total_alunos = total_alunos.filter(data_matricula__year=datetime.datetime.now().year)

    groups = []
    for tipo in ['Alunos Ingressantes com Avaliação Biomédica', 'Total de Alunos Ingressantes']:
        groups.append(tipo)

    series2 = []
    serie = ['Alunos']
    serie.append(alunos_ensino_medio_integrado.distinct('aluno').count())
    serie.append(total_alunos.count())
    series2.append(serie)

    grafico6 = GroupedColumnChart(
        'grafico6',
        title='Percentual de alunos Ingressantes do Integrado com Avaliação Biomédica',
        subtitle='Percentual de alunos ingressantes do Integrado com Avaliação Biomédica em relação ao total de alunos ingressantes',
        minPointLength=0,
        data=series2,
        groups=groups,
    )
    grafico6.id = 'grafico6'

    pie_chart_lists = [grafico2, grafico3, grafico4, grafico5, grafico6]

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS_ATENDIMENTO_MEDICO_ENF)
@permission_required('rh.eh_servidor')
def remover_previsao(request, vacinacao_id):
    vacinacao = get_object_or_404(CartaoVacinal, pk=vacinacao_id)
    vacinacao.data_prevista = None
    vacinacao.save()
    return httprr(f'/saude/prontuario/{vacinacao.prontuario.vinculo_id}/?tab=aba_cartao_vacinal', 'Aprazamento removido com sucesso.')


@rtr()
@permission_required('saude.view_atividadegrupo')
def atividade_em_grupo(request, atividade_id):
    atividade = get_object_or_404(AtividadeGrupo, pk=atividade_id)
    title = f'Atividade em Grupo - {atividade.tipo} ({atividade.uo})'
    return locals()


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_antropometria(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Antropometria'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        contexto = _relatorio_antropometria(form.cleaned_data, request)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_acuidade_visual(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Acuidade Visual'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        registros = _filtrar_periodo_e_campus(AcuidadeVisual.objects.all(), form.cleaned_data)
        registros = _restringir_ao_campus_do_usuario(registros, request.user)
        contexto = _relatorio_fichas(registros, request, tasks.exportar_graficos_acuidade_visual_to_xls, _graficos_acuidade_visual)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_saude_doenca(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Processo Saúde-Doença'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request, exibe_vinculo=True)
    contexto = {}
    if form.is_valid():
        contexto = _relatorio_saude_doenca(form.cleaned_data, request)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@group_required([*Especialidades.GRUPOS, 'Assistente Social'])
def adicionar_anotacao_interdisciplinar(request, prontuario_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    title = 'Adicionar Anotação Interdisciplinar'
    anotacao = AnotacaoInterdisciplinar()
    url = request.META.get('HTTP_REFERER')
    form = AnotacaoInterdisciplinarForm(request.POST or None, url=url)
    if form.is_valid():
        interessados_indicados = []
        for pessoa in form.cleaned_data.get('interessados'):
            interessados_indicados.append(InteressadoAnotacaoInterdisciplinar(anotacao_interdisciplinar=anotacao, interessado=pessoa))
        with transaction.atomic():
            anotacao.profissional = request.user.get_relacionamento()
            anotacao.data = datetime.datetime.now()
            anotacao.prontuario = prontuario
            anotacao.anotacao = form.cleaned_data.get('anotacao')
            anotacao.save()
            if interessados_indicados:
                InteressadoAnotacaoInterdisciplinar.objects.bulk_create(
                    interessados_indicados,
                    update_conflicts=False,
                    unique_fields=['anotacao_interdisciplinar', 'interessado'],
                )
        return httprr(f'{form.cleaned_data.get("url")}', 'Anotação registrada com sucesso.')

    return locals()


@rtr()
@group_required(['Psicólogo'])
def atendimento_psicologico(request, atendimento_id):
    title = 'Atendimento Psicológico'
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.PSICOLOGICO)
    if not (atendimento.usuario_aberto == request.user):
        raise PermissionDenied

    pendencias = atendimento.tem_pendencia(request)

    pode_editar = False
    eh_psicologia = True
    if atendimento.aluno:
        programas = Participacao.objects.filter(aluno=atendimento.get_vinculo(), data_termino__isnull=True)
    is_coordenador_sistemico = in_group(request.user, 'Coordenador de Saúde Sistêmico')
    especialidade = Especialidades(request.user)
    is_medico = especialidade.is_medico()
    is_enfermagem = especialidade.is_enfermeiro() or especialidade.is_tecnico_enfermagem() or especialidade.is_auxiliar_enfermagem()
    atendimento_psicologia = AtendimentoPsicologia.objects.filter(atendimento=atendimento)
    atendimento_psicologia_responsavel = False
    if atendimento_psicologia.exists():
        atendimento_psicologia = atendimento_psicologia[0]
        atendimento_psicologia_responsavel = atendimento_psicologia.get_responsavel()
        if atendimento_psicologia.profissional != request.user:
            pode_editar = False
        else:
            pode_editar = True

    anexos = AnexoPsicologia.objects.filter(atendimento=atendimento)
    historicos = (
        AtendimentoPsicologia.objects.filter(atendimento__prontuario=atendimento.prontuario, atendimento__usuario_aberto=request.user)
        .exclude(atendimento__id=atendimento.id)
        .order_by('-id')
    )

    return locals()


@rtr()
@group_required(['Psicólogo'])
@permission_required('rh.eh_servidor')
def adicionar_anamnese_psicologica(request, vinculo_id):
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    prontuario = Prontuario.get_prontuario(vinculo)
    title = f'Adicionar Anamnese - {vinculo}'
    obj = AnamnesePsicologia.objects.filter(prontuario=prontuario, profissional=request.user)
    if obj.exists():
        obj = obj.latest('id')
    else:
        obj = AnamnesePsicologia()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.prontuario = prontuario
    form = AnamnesePsicologiaForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/prontuario/{vinculo_id}/?tab=aba_anamnese_psicologia', 'Anamnese registrada com sucesso.')
    return locals()


@rtr()
@group_required(['Odontólogo'])
def ordem_plano_tratamento(request, item_plano_tratamento, tipo):
    item_movido = get_object_or_404(PlanoTratamento, pk=item_plano_tratamento)
    atendimento = item_movido.atendimento

    tem_permissao(atendimento, request)

    if tipo == 1:
        # item movido pra cima
        if PlanoTratamento.objects.filter(atendimento=atendimento, ordem__lt=item_movido.ordem).exists():
            item_superior = PlanoTratamento.objects.filter(atendimento=atendimento, ordem__lt=item_movido.ordem).order_by('-ordem').first()
            item_movido.ordem = item_movido.ordem - 1
            item_movido.save()
            if item_superior:
                item_superior.ordem = item_superior.ordem + 1
                item_superior.save()
    elif tipo == 2:
        # item movido pra baixo
        if PlanoTratamento.objects.filter(atendimento=atendimento, ordem__lt=item_movido.ordem).exists():
            item_inferior = PlanoTratamento.objects.filter(atendimento=atendimento, ordem__gt=item_movido.ordem).order_by('ordem').first()
            item_movido.ordem = item_movido.ordem + 1
            item_movido.save()
            if item_inferior:
                item_inferior.ordem = item_inferior.ordem - 1
                item_inferior.save()

    return httprr(
        f'/saude/atendimento_odontologico/{item_movido.atendimento_id}/?tab=aba_plano_tratamento',
        'Ordem do plano de tratamento alterada com sucesso.',
    )


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def resolver_exame_periodontal(request, exame_id):
    exame = get_object_or_404(ExamePeriodontal, pk=exame_id)
    exame.resolvido = True
    exame.save()
    return httprr(f'/saude/atendimento_odontologico/{exame.atendimento_id}/?tab=aba_situacao_clinica', 'Exame periodontal alterado com sucesso.')


@rtr('historico_ficha.html')
@group_required(['Odontólogo'])
def historico_exame_estomatologico(request, atendimento_id):
    title = 'Histórico dos Exames Estomatológicos'
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    historico = ExameEstomatologico.objects.filter(atendimento=atendimento).order_by('-id')
    default_exclude = ('id', 'atendimento_id', 'profissional_id', 'data_cadastro')
    fields = [f.get_attname() for f in ExameEstomatologico._meta.get_fields() if f.get_attname() not in default_exclude]
    table_historico = get_table(queryset=historico, fields=fields)
    return locals()


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_habitos_vida(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Hábitos de Vida'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        registros = _filtrar_periodo_e_campus(HabitosDeVida.objects.order_by('-id'), form.cleaned_data)
        registros = _restringir_ao_campus_do_usuario(registros, request.user)
        contexto = _relatorio_fichas(registros, request, tasks.graficos_habitos_vida_to_xls, _graficos_habitos_vida)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@group_required(['Psicólogo'])
@permission_required('rh.eh_servidor')
def adicionar_motivo_psicologia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Motivo e Queixa Principal - {atendimento.get_vinculo()}'
    obj = AtendimentoPsicologia.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/?tab=aba_motivo', 'Você não pode editar este registro.', tag='error')
    else:
        obj = AtendimentoPsicologia()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoPsicologicoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/?tab=aba_motivo', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_desenvolvimento_pessoal(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Desenvolvimento Pessoal'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        registros = _filtrar_periodo_e_campus(DesenvolvimentoPessoal.objects.all(), form.cleaned_data)
        registros = _restringir_ao_campus_do_usuario(registros, request.user)
        contexto = _relatorio_fichas(registros, request, tasks.graficos_desenvolvimento_pessoal_to_xls, _graficos_desenvolvimento_pessoal)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_exame_fisico(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Exame Físico'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        registros = _filtrar_periodo_e_campus(ExameFisico.objects.all(), form.cleaned_data)
        registros = _restringir_ao_campus_do_usuario(registros, request.user)
        contexto = _relatorio_fichas(registros, request, tasks.graficos_exame_fisico_to_xls, _graficos_exame_fisico)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def alterar_tipo_consulta(request, atendimento_id):
    title = 'Alterar Tipo de Consulta'
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    odontograma = get_object_or_404(Odontograma, atendimento=atendimento)
    form = TipoConsultaForm(request.POST or None, instance=odontograma)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_procedimento', 'Tipo de consulta alterado com sucesso.')

    return locals()


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_percepcao_saude_bucal(request: HttpRequest) -> dict | HttpResponse:
    title = 'Gráficos - Percepção de Saúde Bucal'
    form = EstatisticasAtendimentosForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        registros = _filtrar_periodo_e_campus(PercepcaoSaudeBucal.objects.all(), form.cleaned_data)
        registros = _restringir_ao_campus_do_usuario(registros, request.user)
        contexto = _relatorio_fichas(registros, request, tasks.graficos_percepcao_saude_bucal_to_xls, _graficos_percepcao_saude_bucal)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@group_required([*Especialidades.GRUPOS, 'Auditor'])
def envia_mensagem_vacina_atrasada(request, registros):
    title = 'Enviar Mensagem - Vacinas Atrasadas'
    form = MensagemVacinaAtrasadaForm(request.POST or None)
    if form.is_valid():
        titulo = '[SUAP] {}'.format(form.cleaned_data.get('titulo'))
        mensagem = form.cleaned_data.get('mensagem')
        texto = f'<h1>Saúde</h1><h2>Notificação de Vacina Atrasada</h2>{mensagem}</p>'

        for item in registros:
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [item.prontuario.vinculo], categoria='Saúde: Vacina Atrasada')

        return httprr('/saude/graficos_vacinas/', 'Mensagem enviada com sucesso.')
    return locals()


@rtr()
@permission_required('saude.view_atividadegrupo')
def graficos_vacinas(request):
    title = 'Relatório de Vacinas dos Alunos'
    form = TipoVacinaForm(request.GET or None, request=request)
    if form.is_valid():
        hoje = datetime.datetime.today().date()
        registros = CartaoVacinal.objects.filter(prontuario__vinculo__user__eh_aluno=True)
        vacinas_atrasadas = registros.filter(data_vacinacao__isnull=True)
        alunos_com_cartoes = Aluno.objects.filter(
            situacao=SituacaoMatricula.MATRICULADO, vinculos__vinculo_paciente_prontuario__cartaovacinal__isnull=False
        )

        if form.cleaned_data.get('vacina'):
            alunos_com_cartoes = alunos_com_cartoes.filter(
                vinculos__vinculo_paciente_prontuario__cartaovacinal__vacina=form.cleaned_data.get('vacina')
            )
            vacinas_atrasadas = vacinas_atrasadas.filter(vacina=form.cleaned_data.get('vacina'))

        if not request.user.has_group_cached(Especialidades.GRUPOS_VE_GRAFICOS_TODOS):
            alunos_com_cartoes = alunos_com_cartoes.filter(curso_campus__diretoria__setor__uo=get_uo(request.user))

        if form.cleaned_data.get('turma'):
            alunos_turma = form.cleaned_data.get('turma').get_alunos_matriculados()
            alunos_com_cartoes = alunos_com_cartoes.filter(id__in=alunos_turma.values_list('aluno', flat=True))

        if form.cleaned_data.get('campus'):
            alunos_com_cartoes = alunos_com_cartoes.filter(
                situacao=SituacaoMatricula.MATRICULADO, curso_campus__diretoria__setor__uo=form.cleaned_data.get('campus')
            )

        buscou_data = False
        if form.cleaned_data.get('data_inicial'):
            vacinas_atrasadas = vacinas_atrasadas.filter(data_prevista__gte=form.cleaned_data.get('data_inicial'))
            buscou_data = True
        if form.cleaned_data.get('data_final'):
            vacinas_atrasadas = vacinas_atrasadas.filter(data_prevista__lte=form.cleaned_data.get('data_final'))
            buscou_data = True
        if not buscou_data:
            vacinas_atrasadas = vacinas_atrasadas.filter(data_prevista__lt=hoje)

        alunos_com_cartoes = alunos_com_cartoes.order_by('pessoa_fisica__nome').distinct()
        registros = registros.filter(prontuario__vinculo__pessoa__pessoafisica__in=alunos_com_cartoes.values_list('pessoa_fisica', flat=True))
        vacinas_atrasadas = vacinas_atrasadas.filter(
            prontuario__vinculo__pessoa__pessoafisica__in=alunos_com_cartoes.values_list('pessoa_fisica', flat=True)
        )

        dados = []
        vacinas = registros.values('vacina__nome').annotate(qtd=Count('vacina__nome')).order_by('vacina__nome')

        vacinas_atrasadas = vacinas_atrasadas.order_by('prontuario__vinculo__pessoa__nome').distinct()

        for registro in vacinas:
            dados.append([registro['vacina__nome'], registro['qtd']])

        grafico1 = PieChart(
            'grafico1',
            title='Classificação por Vacinas - Alunos',
            subtitle='Classificação por Vacinas Registradas para Alunos',
            minPointLength=0,
            data=dados,
        )
        grafico1.id = 'grafico1'

        pie_chart_lists = [grafico1]

        if request.GET.get('envia_mensagem'):
            return envia_mensagem_vacina_atrasada(request, vacinas_atrasadas)

    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_exame_laboratorial(request, prontuario_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    title = 'Adicionar Exame Laboratorial'
    tipos_exame = TipoExameLaboratorial.objects.filter(ativo=True)
    exame_anterior = None
    url = request.META.get('HTTP_REFERER', '.')
    if 'exame_anterior_id' in request.GET:
        exame_anterior = get_object_or_404(ExameLaboratorial, pk=request.GET.get('exame_anterior_id'))
    form = ExameLaboratorialForm(request.POST or None, exame_anterior=exame_anterior, url=url)
    if form.is_valid():
        o = form.save(False)
        o.prontuario = prontuario
        o.data_cadastro = datetime.datetime.now()
        o.profissional = request.user.get_relacionamento()
        o.save()
        url_origem = form.cleaned_data.get('url_origem')

        if TipoExameLaboratorial.objects.filter(categoria=o.categoria).exists():
            return httprr(
                f'/saude/adicionar_valores_exame_laboratorial/{form.instance.id}/?url={url_origem}',
                'Exame registrado com sucesso. Preencha os valores do exame.',
            )

        else:
            return httprr(f'{url_origem}', 'Exame registrado com sucesso.')

    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_valores_exame_laboratorial(request, exame_laboratorial_id):
    exame = get_object_or_404(ExameLaboratorial, pk=exame_laboratorial_id)
    title = 'Adicionar Valores do Exame Laboratorial'
    url = request.GET.get('url')
    form = ValoresExameLaboratorialForm(request.POST or None, exame=exame, url=url)

    if form.is_valid():
        url_origem = form.cleaned_data.get('url_origem')
        ids_valores = TipoExameLaboratorial.objects.values_list('id', flat=True)
        for item in list(request.POST.items()):
            try:
                int(item[0])
                if item[1] and int(item[0]) in ids_valores:
                    novo_exame = ValorExameLaboratorial()
                    novo_exame.exame = exame
                    novo_exame.tipo = get_object_or_404(TipoExameLaboratorial, pk=item[0])
                    novo_exame.valor = item[1]
                    novo_exame.save()
            except ValueError:
                pass
        if url_origem and 'atendimento_nutricional' in url_origem:
            return httprr(f'{url_origem}', 'Exame registrado com sucesso.')
        return httprr(f'/saude/adicionar_exame_laboratorial/{exame.prontuario_id}/?exame_anterior_id={exame.id}', 'Exame registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_exame_imagem(request, prontuario_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    title = 'Adicionar Exame de Imagem'
    form = ExameImagemForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.prontuario = prontuario
        o.data_cadastro = datetime.datetime.now()
        o.profissional = request.user.get_relacionamento()
        o.save()
        return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_exames_imagem', 'Exame registrado com sucesso.')

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Coordenador de Saúde Sistêmico',
    ]
)
def ver_exame_laboratorial(request, exame_id):
    exame = get_object_or_404(ExameLaboratorial, pk=exame_id)
    title = 'Exame Laboratorial'
    if exame.sigiloso and not exame.profissional == request.user.get_relacionamento():
        raise PermissionDenied
    valores = ValorExameLaboratorial.objects.filter(exame=exame)

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Coordenador de Saúde Sistêmico',
    ]
)
def ver_exame_imagem(request, exame_id):
    exame = get_object_or_404(ExameImagem, pk=exame_id)
    title = 'Exame de Imagem'
    if exame.sigiloso and not exame.profissional == request.user.get_relacionamento():
        raise PermissionDenied

    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Fisioterapeuta', 'Nutricionista'])
def exame_laboratorial_valores_referencia(request):
    title = 'Valores de Referência dos Exames Laboratoriais'
    exames = TipoExameLaboratorial.objects.filter(ativo=True)

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Coordenador de Saúde Sistêmico',
    ]
)
def editar_exame_laboratorial(request, exame_id):
    exame = get_object_or_404(ExameLaboratorial, pk=exame_id)
    title = 'Editar Exame Laboratorial'
    if not exame.profissional == request.user.get_relacionamento():
        raise PermissionDenied
    valores = ValorExameLaboratorial.objects.filter(exame=exame)

    form = EditarExameLaboratorialForm(request.POST or None, instance=exame, valores=valores)
    if form.is_valid():
        form.save()
        for item in valores:
            id_registro = item.id
            valor = request.POST.get(str(id_registro))
            registro = get_object_or_404(ValorExameLaboratorial, pk=id_registro)
            if valor:
                registro.valor = valor
                registro.save()
            else:
                registro.delete()

        return httprr(f'/saude/prontuario/{exame.prontuario.vinculo_id}/?tab=aba_exames_laboratoriais', 'Exame alterado com sucesso.')

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Coordenador de Saúde Sistêmico',
    ]
)
def editar_exame_imagem(request, exame_id):
    exame = get_object_or_404(ExameImagem, pk=exame_id)
    title = 'Editar Exame de Imagem'
    if not exame.profissional == request.user.get_relacionamento():
        raise PermissionDenied
    form = ExameImagemForm(request.POST or None, instance=exame)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/prontuario/{exame.prontuario.vinculo_id}/?tab=aba_exames_imagem', 'Exame alterado com sucesso.')

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Coordenador de Saúde Sistêmico',
    ]
)
def excluir_exame_laboratorial(request, exame_id):
    exame = get_object_or_404(ExameLaboratorial, pk=exame_id)
    prontuario = exame.prontuario
    if not exame.profissional == request.user.get_relacionamento():
        raise PermissionDenied
    exame.delete()
    return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_exames_laboratoriais', 'Exame alterado com sucesso.')


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Coordenador de Saúde Sistêmico',
    ]
)
def excluir_exame_imagem(request, exame_id):
    exame = get_object_or_404(ExameImagem, pk=exame_id)
    prontuario = exame.prontuario
    if not exame.profissional == request.user.get_relacionamento():
        raise PermissionDenied
    exame.delete()
    return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_exames_imagem', 'Exame alterado com sucesso.')


@rtr()
@group_required(['Médico'])
@permission_required('rh.eh_servidor')
def editar_hipotese_diagnostica(request, hipotese_diagnostica_id):
    title = 'Editar Hipótese Diagnóstica'
    hipotese = get_object_or_404(HipoteseDiagnostica, pk=hipotese_diagnostica_id)
    if hipotese.atendimento.is_aberto() and hipotese.profissional == request.user:
        form = HipoteseDiagnosticaModelForm(request.POST or None, instance=hipotese)
        if form.is_valid():
            form.save()
            return httprr(
                f'/saude/atendimento_medico_enfermagem/{hipotese.atendimento_id}/?tab=aba_hipotesediagnostica',
                'Hipótese Diagnóstica alterada com sucesso.',
            )

    else:
        raise PermissionDenied

    return locals()


@rtr()
@group_required(['Médico'])
@permission_required('rh.eh_servidor')
def editar_conduta_medica(request, conduta_medica_id):
    title = 'Editar Conduta Médica'
    conduta = get_object_or_404(CondutaMedica, pk=conduta_medica_id)
    if conduta.atendimento.is_aberto() and conduta.profissional == request.user:
        form = CondutaMedicaForm(request.POST or None, instance=conduta, request=request)
        if form.is_valid():
            form.save()
            return httprr(
                f'/saude/atendimento_medico_enfermagem/{conduta.atendimento_id}/?tab=aba_hipotesediagnostica', 'Conduta Médica alterada com sucesso.'
            )

    else:
        raise PermissionDenied

    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Auditor', 'Coordenador de Atividades Estudantis', 'Coordenador de Atividades Estudantis Sistêmico'])
def relatorio_cartoes_vacinais(request):
    title = 'Relatórios de Cartões Vacinais'

    registros = CartaoVacinal.objects.all()
    if not request.user.has_group_cached(Especialidades.GRUPOS_VE_GRAFICOS_TODOS):
        alunos_do_campus = Aluno.objects.filter(situacao=SituacaoMatricula.MATRICULADO, curso_campus__diretoria__setor__uo=get_uo(request.user))
        registros = registros.filter(prontuario__vinculo__pessoa__pessoafisica__in=alunos_do_campus.values_list('pessoa_fisica', flat=True))
    pode_ver_prontuario = request.user.has_group_cached(Especialidades.GRUPOS)
    form = CartaoVacinalForm(request.GET or None, request=request)
    if form.is_valid():
        if form.cleaned_data.get('ano_ingresso'):
            alunos = Aluno.objects.filter(situacao=SituacaoMatricula.MATRICULADO, ano_letivo=form.cleaned_data.get('ano_ingresso'))
            registros = registros.filter(prontuario__vinculo__pessoa__pessoafisica__in=alunos.values_list('pessoa_fisica', flat=True))
        if form.cleaned_data.get('modalidade'):
            alunos = Aluno.objects.filter(situacao=SituacaoMatricula.MATRICULADO, curso_campus__modalidade=form.cleaned_data.get('modalidade'))
            registros = registros.filter(prontuario__vinculo__pessoa__pessoafisica__in=alunos.values_list('pessoa_fisica', flat=True))
        if form.cleaned_data.get('turma'):
            alunos = form.cleaned_data.get('turma').get_alunos_matriculados()
            registros = registros.filter(prontuario__vinculo__pessoa__pessoafisica__in=alunos.values_list('aluno__pessoa_fisica', flat=True))

        categoria = form.cleaned_data.get('categoria')
        if categoria:
            if categoria == '1':
                registros = registros.filter(prontuario__vinculo__user__eh_aluno=True)
            elif categoria == '2':
                registros = registros.filter(prontuario__vinculo__user__eh_servidor=True)
            elif categoria == '3':
                registros = registros.filter(prontuario__vinculo__user__eh_prestador=True)
            elif categoria == '4':
                registros = registros.filter(
                    prontuario__vinculo__user__eh_aluno=False,
                    prontuario__vinculo__user__eh_servidor=False,
                    prontuario__vinculo__user__eh_prestador=False,
                )

        if form.cleaned_data.get('campus'):
            if categoria == '1':
                alunos_do_campus = Aluno.objects.filter(
                    situacao=SituacaoMatricula.MATRICULADO, curso_campus__diretoria__setor__uo=form.cleaned_data.get('campus')
                )
                registros = registros.filter(prontuario__vinculo__pessoa__pessoafisica__in=alunos_do_campus.values_list('pessoa_fisica', flat=True))
            else:
                registros = registros.filter(prontuario__vinculo__setor__uo=form.cleaned_data.get('campus'))

        registros_alunos_distintos = registros.distinct('prontuario__vinculo')
        registros = registros.filter(id__in=registros_alunos_distintos.values_list('id', flat=True)).order_by('prontuario__vinculo__pessoa__nome')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def atendimento_multidisciplinar(request, atendimento_id):
    title = 'Atendimento Multidisciplinar'
    especialidade = Especialidades(request.user)

    pode_gerenciar_atend_multidisciplinar = (
        especialidade.is_odontologo() or especialidade.is_medico() or especialidade.is_nutricionista() or especialidade.is_psicologo()
    )

    # Carrega dados do atendimento, cabecalho e do vinculo do usuario
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.MULTIDISCIPLINAR)

    pendencias = atendimento.tem_pendencia(request)

    cadastrou_processosaudedoenca = False
    processosaudedoenca = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento)
    processosaudedoenca_count = processosaudedoenca.count()
    if processosaudedoenca.exists():
        cadastrou_processosaudedoenca = True
        processosaudedoenca = processosaudedoenca.latest('id')
        processosaudedoenca_responsavel = processosaudedoenca.get_responsavel()

    procedimentos = AtendimentoMultidisciplinar.objects.filter(atendimento=atendimento).order_by('-id')
    procedimentos_titulo = 'Procedimentos'
    procedimentos_count = procedimentos.count()
    exclude_fields = ('id', 'data_cadastro', 'atendimento', 'profissional')
    custom_fields = {'get_cadastro_display': Column('Cadastrado por', accessor='get_cadastro_display')}
    campos = ('procedimentos', 'descricao')
    sequence = ['procedimentos', 'descricao', 'get_cadastro_display']
    table_procedimentos = get_table(
        queryset=procedimentos, sequence=sequence, custom_fields=custom_fields, fields=campos, exclude_fields=exclude_fields
    )

    return locals()


@rtr()
@group_required(['Médico', 'Odontólogo', 'Nutricionista', 'Psicólogo'])
@permission_required('rh.eh_servidor')
def adicionar_procedimento_multidisciplinar(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    if atendimento.usuario_aberto != request.user:
        raise PermissionDenied

    title = f'Adicionar Procedimento - {atendimento.get_vinculo()}'

    procedimento = AtendimentoMultidisciplinar.objects.filter(atendimento=atendimento.pk)

    if procedimento.exists():
        procedimento = procedimento.latest('id')
    else:
        procedimento = AtendimentoMultidisciplinar()

    procedimento.profissional = request.user
    procedimento.data_cadastro = datetime.datetime.now()
    procedimento.atendimento = atendimento

    especialidade = Especialidades(request.user)
    form = AtendimentoMultidisciplinarForm(request.POST or None, instance=procedimento, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_multidisciplinar/{atendimento.id}/', 'Atendimento multidisciplinar registrado com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def cancelar_atividade_grupo(request, atividade_id):
    atividade = get_object_or_404(AtividadeGrupo, pk=atividade_id)
    if get_uo(request.user) == atividade.uo:
        atividade.cancelada = True
        atividade.save()
        return httprr('/admin/saude/atividadegrupo/', 'Atendimento cancelado com sucesso.')

    raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def atendimento_nutricional(request, atendimento_id):
    title = 'Atendimento Nutricional'
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.NUTRICIONAL)

    pode_editar = (request.user == atendimento.usuario_aberto) and atendimento.situacao == SituacaoAtendimento.ABERTO

    especialidade = Especialidades(request.user)

    pendencias = atendimento.tem_pendencia(request)

    atendimento_nutricao = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    atendimento_nutricao_responsavel = False
    if atendimento_nutricao.exists():
        atendimento_nutricao = atendimento_nutricao[0]
        atendimento_nutricao_responsavel = atendimento_nutricao.get_responsavel()

    cadastrou_antecedentes = False
    cadastrou_processosaudedoenca = False

    antecedentesfamiliares = AntecedentesFamiliares.objects.filter(atendimento=atendimento)
    antecedentesfamiliares_titulo = 'Antecedentes'
    antecedentesfamiliares_count = antecedentesfamiliares.count()
    if antecedentesfamiliares.exists():
        cadastrou_antecedentes = True
        antecedentesfamiliares = antecedentesfamiliares.latest('id')
        antecedentesfamiliares_responsavel = antecedentesfamiliares.get_responsavel()

    processosaudedoenca = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento)
    processosaudedoenca_titulo = 'Processo Saúde-Doença'
    processosaudedoenca_count = processosaudedoenca.count()
    if processosaudedoenca.exists():
        cadastrou_processosaudedoenca = True
        processosaudedoenca = processosaudedoenca.latest('id')
        processosaudedoenca_responsavel = processosaudedoenca.get_responsavel()

    aba_antecedentes_preenchida = cadastrou_antecedentes or cadastrou_processosaudedoenca

    habitosdevida = HabitosDeVida.objects.filter(atendimento=atendimento)
    habitos_count = habitosdevida.count()
    if habitosdevida.exists():
        habitosdevida = habitosdevida.latest('id')
        habitosdevida_responsavel = habitosdevida.get_responsavel()

    antropometria = Antropometria.objects.filter(atendimento=atendimento)
    antropometria_count = antropometria.count()
    if antropometria.exists():
        cadastrou_antropometria = True
        antropometria = antropometria.latest('id')
        antropometria_responsavel = antropometria.get_responsavel()

    dados_gerais_alimentacao = atendimento_nutricao.tem_dados_gerais_alimentacao()
    dados_consumo = ConsumoNutricao.objects.filter(atendimento=atendimento).order_by('id')
    plano_alimentar = PlanoAlimentar.objects.filter(atendimento=atendimento)

    lista_respostas_marcadores = {}
    respostas_marcadores = RespostaMarcadorNutricao.objects.filter(atendimento=atendimento)
    respostas_marcadores_responsavel = None
    if respostas_marcadores.exists():
        respostas_marcadores_responsavel = respostas_marcadores.latest('id').get_responsavel()
    for pergunta in respostas_marcadores.distinct('pergunta'):
        chave = f'{pergunta.pergunta}'
        lista_respostas_marcadores[chave] = []

    for resposta in RespostaMarcadorNutricao.objects.filter(atendimento=atendimento):
        chave = f'{resposta.pergunta}'
        lista_respostas_marcadores[chave].append(resposta.resposta)

    frequencia_marcadores = FrequenciaAlimentarNutricao.objects.filter(atendimento=atendimento)
    aba_anamnese_preenchida = (
        habitos_count or antropometria_count or dados_gerais_alimentacao or dados_consumo or atendimento_nutricao.restricao_alimentar.exists()
    )
    prontuario = atendimento.prontuario
    exames_laboratoriais = ExameLaboratorial.objects.filter(prontuario=prontuario).order_by('-data_realizado', 'categoria')
    dados_exames = {}

    categorias = CategoriaExameLaboratorial.objects.filter(
        tipoexamelaboratorial__isnull=False, id__in=ExameLaboratorial.objects.filter(prontuario=prontuario).values_list('categoria', flat=True)
    )

    for categoria in categorias:
        registros = {}
        for item in ValorExameLaboratorial.objects.filter(exame__prontuario=prontuario, tipo__categoria=categoria).order_by('tipo__nome'):
            if not item.exame.sigiloso or (item.exame.sigiloso and item.exame.profissional == request.user.get_relacionamento()):
                chave = f'{item.tipo.nome} ({item.tipo.unidade})'
                registros[chave] = {}
        meses = {}

        for exame in ExameLaboratorial.objects.filter(prontuario=prontuario, categoria=categoria).order_by('data_realizado'):
            if not exame.sigiloso or (exame.sigiloso and exame.profissional == request.user.get_relacionamento()):
                if format_(exame.data_realizado) in meses:
                    index = 1
                    for indice in list(meses.keys()):
                        if format_(exame.data_realizado) in indice:
                            index += 1
                    chave_exame = f'{exame.data_realizado.strftime("%d/%m/%Y")} ({index})'
                else:
                    chave_exame = exame.data_realizado.strftime('%d/%m/%Y')
                meses[chave_exame] = {}

            for item in ValorExameLaboratorial.objects.filter(exame=exame).order_by('tipo__nome'):
                if not item.exame.sigiloso or (item.exame.sigiloso and item.exame.profissional == request.user.get_relacionamento()):
                    chave = f'{item.tipo.nome} ({item.tipo.unidade})'
                    registros[chave][chave_exame] = f'{item.valor} {item.tipo.unidade}'

        meses_ordenados = collections.OrderedDict(sorted(meses.items(), reverse=True))
        registros_ordenados = collections.OrderedDict(sorted(registros.items(), key=lambda x: x[0]))
        dados_exames[categoria.nome] = {'meses': meses_ordenados, 'registros': registros_ordenados}
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_motivo_nutricao(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Motivo do Atendimento - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_motivo', 'Você não pode editar este registro.', tag='error')
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoMotivoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_motivo', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_avaliacao_gastrointestinal(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Motivo do Atendimento - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Você não pode editar este registro.', tag='error')
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoAvalGastroForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_dados_alimentacao(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Dados gerais de Alimentação - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Você não pode editar este registro.', tag='error')
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoDadosAlimentacaoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_restricao_alimentar(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Restrição Alimentar - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Você não pode editar este registro.', tag='error')
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoRestricaoAlimentarForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_consumo_nutricao(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Recordatório Alimentar - {atendimento.get_vinculo()}'
    obj = ConsumoNutricao()
    obj.atendimento = atendimento
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    form = AtendimentoNutricaoConsumoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_diagnostico_nutricional(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Diagnóstico Nutricional - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(
                f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_diagnostico_nutricional',
                'Você não pode editar este registro.',
                tag='error',
            )
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoDiagnosticoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_diagnostico_nutricional', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
def adicionar_categoria_trabalho(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Diagnóstico Nutricional - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(
                f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_conduta_nutricional', 'Você não pode editar este registro.', tag='error'
            )
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoCategoriaTrabalhoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_conduta_nutricional', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_conduta_nutricao(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Diagnóstico Nutricional - {atendimento.get_vinculo()}'
    obj = AtendimentoNutricao.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(
                f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_conduta_nutricional', 'Você não pode editar este registro.', tag='error'
            )
    else:
        obj = AtendimentoNutricao()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = AtendimentoNutricaoCondutaForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_conduta_nutricional', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_plano_alimentar(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Plano Alimentar - {atendimento.get_vinculo()}'
    form = PlanoAlimentarForm(request.POST or None, request=request)
    if form.is_valid():
        o = form.save(False)
        o.profissional = request.user
        o.data_cadastro = datetime.datetime.now()
        o.atendimento = atendimento
        o.save()
        form.save_m2m()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_conduta_nutricional', 'Atendimento registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def editar_plano_alimentar(request, plano_id):
    plano = get_object_or_404(PlanoAlimentar, pk=plano_id)
    title = f'Editar Plano Alimentar - {plano.atendimento.get_vinculo()}'
    form = PlanoAlimentarForm(request.POST or None, request=request, instance=plano)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_nutricional/{plano.atendimento_id}/?tab=aba_conduta_nutricional', 'Plano alimentar editado com sucesso.')
    return locals()


@documento(enumerar_paginas=False, validade=360)
@rtr()
@group_required(['Nutricionista'])
def imprimir_plano_alimentar(request, plano_id):
    plano = get_object_or_404(PlanoAlimentar, pk=plano_id)
    atendimento = plano.atendimento
    especialidade = Especialidades(request.user)
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    if request.user == atendimento.usuario_aberto or (especialidade.is_nutricionista() and plano.plano_alimentar_liberado):
        hoje = datetime.datetime.now().date()
        if atendimento.aluno:
            campus = atendimento.aluno.curso_campus.diretoria.setor.uo
        else:
            campus = get_uo(request.user)

        registro = Antropometria.objects.filter(atendimento=atendimento).order_by('-id').first()
        if registro:
            peso = registro.get_peso_display()
            altura = registro.get_estatura_display()
            imc = registro.get_IMC()
        orientacoes = receitas = None

        orientacoes = plano.orientacao_nutricional.all()
        receitas = plano.receita_nutricional.all()

        if campus.sigla in ['NC', 'CN', 'PF']:
            titulo = 'Coordenação de Atividades Estudantis'
        elif campus.sigla == 'CNAT':
            titulo = 'Diretoria de Atividades Estudantis'
        elif campus.sigla == get_sigla_reitoria():
            titulo = 'Diretoria de Gestão de Atividades Estudantis'

        return locals()

    else:
        raise PermissionDenied


@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def remover_plano_alimentar(request, plano_id):
    plano = get_object_or_404(PlanoAlimentar, pk=plano_id)
    atendimento = plano.atendimento
    if request.user == plano.atendimento.usuario_aberto:
        plano.delete()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_conduta_nutricional', 'Plano Alimentar excluído com sucesso.')

    raise PermissionDenied


@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def remover_receita(request, atendimentonutricao_id, receita_id):
    atendimento_nutricao = get_object_or_404(AtendimentoNutricao, pk=atendimentonutricao_id)
    receita = get_object_or_404(ReceitaNutricional, pk=receita_id)
    if request.user == atendimento_nutricao.atendimento.usuario_aberto:
        atendimento_nutricao.receita_nutricional.remove(receita)
        return httprr(
            f'/saude/atendimento_nutricional/{atendimento_nutricao.atendimento_id}/?tab=aba_conduta_nutricional', 'Receita excluída com sucesso.'
        )

    raise PermissionDenied


@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def remover_conduta_nutricao(request, atendimentonutricao_id):
    atendimento_nutricao = get_object_or_404(AtendimentoNutricao, pk=atendimentonutricao_id)
    if request.user == atendimento_nutricao.atendimento.usuario_aberto:
        atendimento_nutricao.conduta = None
        atendimento_nutricao.save()
        return httprr(
            f'/saude/atendimento_nutricional/{atendimento_nutricao.atendimento_id}/?tab=aba_conduta_nutricional', 'Conduta excluída com sucesso.'
        )

    raise PermissionDenied


@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def remover_consumo(request, consumo_id):
    consumo = get_object_or_404(ConsumoNutricao, pk=consumo_id)
    if request.user == consumo.atendimento.usuario_aberto:
        atendimento = consumo.atendimento
        consumo.delete()
        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Registro de consumo excluído com sucesso.')

    raise PermissionDenied


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def editar_consumo(request, consumo_id):
    consumo = get_object_or_404(ConsumoNutricao, pk=consumo_id)
    title = 'Editar Consumo'
    if request.user == consumo.atendimento.usuario_aberto:
        form = AtendimentoNutricaoConsumoForm(request.POST or None, request=request, instance=consumo)
        if form.is_valid():
            form.save()
            return httprr(f'/saude/atendimento_nutricional/{consumo.atendimento_id}/?tab=aba_anamnese', 'Consumo editado com sucesso.')

        return locals()

    raise PermissionDenied


@rtr()
@group_required(
    [
        'Odontólogo',
        'Coordenador de Saúde Sistêmico',
        'Auditor',
        'Coordenador de Atividades Estudantis Sistêmico',
        'Coordenador de Atividades Estudantis',
        'Técnico em Saúde Bucal',
        'Coordenador de Saúde',
    ]
)
def relatorios_atendimentos_odontologicos(request: HttpRequest) -> dict | HttpResponse:
    title = 'Relatórios de Atendimentos Odontológicos'
    atendimentos = (
        Atendimento.objects.filter(tipo=TipoAtendimento.ODONTOLOGICO)
        .exclude(situacao=SituacaoAtendimento.CANCELADO)
        .order_by('prontuario__vinculo__pessoa__nome', '-id')
    )
    form = RelatorioOdontologicoForm(request.GET or None)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        categoria = form.cleaned_data.get('categoria')
        data_inicial = form.cleaned_data.get('data_inicial')
        data_final = form.cleaned_data.get('data_final')
        if campus:
            atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=campus)

        if categoria:
            if categoria == Atendimento.CATEGORIA_ALUNO:
                atendimentos = atendimentos.filter(aluno__isnull=False)
            elif categoria == Atendimento.CATEGORIA_SERVIDOR:
                atendimentos = atendimentos.filter(servidor__isnull=False)
            elif categoria == Atendimento.CATEGORIA_PRESTADOR_SERVICO:
                atendimentos = atendimentos.filter(prestador_servico__isnull=False)
            elif categoria == Atendimento.CATEGORIA_COMUNIDADE_EXTERNA:
                atendimentos = atendimentos.filter(pessoa_externa__isnull=False)

        atendimentos = _filtrar_aberturas_ate_o_fim_do_dia(atendimentos, data_inicial, data_final)

        if 'xls' in request.GET:
            return tasks.relatorios_atendimentos_odontologicos_to_xls(atendimentos)

    return locals()


@rtr()
@group_required('Odontólogo')
@permission_required('rh.eh_servidor')
def excluir_exame_periodontal(request, exame_id):
    exame = get_object_or_404(ExamePeriodontal, pk=exame_id)
    if request.user == exame.profissional:
        atendimento = exame.atendimento
        exame.delete()
        if atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
            return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/', 'Exame periodontal excluido com sucesso.')
        else:
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_odontograma', 'Exame periodontal excluido com sucesso.')

    raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def editar_cartao_sus(request, aluno_id):
    aluno = get_object_or_404(Aluno, pk=aluno_id)
    title = f'Editar Cartão SUS - {aluno}'
    form = CartaoSUSAlunoForm(request.POST or None, instance=aluno)
    if form.is_valid():
        form.save()
        return httprr('..', 'Número SUS cadastrado com sucesso.')

    return locals()


@rtr()
@group_required('Odontólogo')
@permission_required('rh.eh_servidor')
def excluir_procedimento_odontologico(request, procedimento_id):
    procedimento = get_object_or_404(ProcedimentoOdontologico, pk=procedimento_id)

    if procedimento.profissional == request.user:
        atendimento = procedimento.atendimento
        procedimento.delete()

        return httprr(
            f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_procedimento',
            'Procedimento excluído com sucesso. Atualize o odontograma e o plano de tratamento manualmente, caso seja necessário.',
        )

    raise PermissionDenied


@rtr()
@group_required(['Odontólogo'])
@permission_required('rh.eh_servidor')
def obs_registrar_execucao(request, plano_tratamento_id):
    title = 'Adicionar Observações'
    form = ObsRegistroExecucaoForm(request.POST or None)
    if form.is_valid():
        return httprr('/saude/registrar_execucao_plano/{}/?obs={}'.format(plano_tratamento_id, form.cleaned_data.get('obs')))
    return locals()


@rtr()
@group_required(['Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_marcadores_consumo_alimentar(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = 'Marcadores de Práticas e de Consumo Alimentar'
    if request.user == atendimento.usuario_aberto:
        form = MarcadorConsumoAlimentarForm(request.POST or None, request=request)
        if form.is_valid():
            chaves = list(request.POST.keys())
            for item in chaves:
                valores = request.POST.getlist(item)
                if 'pergunta_' in item:
                    id = item.split('_')[1]
                    for valor in valores:
                        if PerguntaMarcadorNutricao.objects.filter(id=id, ativo=True).exists():
                            o = RespostaMarcadorNutricao()
                            o.profissional = request.user
                            o.data_cadastro = datetime.datetime.now()
                            o.atendimento = atendimento
                            o.pergunta = get_object_or_404(PerguntaMarcadorNutricao, pk=id)
                            o.resposta = get_object_or_404(OpcaoRespostaMarcadorNutricao, pk=int(valor))
                            o.save()

                elif 'frequencia_' in item:
                    id = item.split('_')[1]
                    for valor in valores:
                        if FrequenciaPraticaAlimentar.objects.filter(id=id, ativo=True).exists():
                            o = FrequenciaAlimentarNutricao()
                            o.profissional = request.user
                            o.data_cadastro = datetime.datetime.now()
                            o.atendimento = atendimento
                            o.frequencia = get_object_or_404(FrequenciaPraticaAlimentar, pk=id)
                            o.valor = valor
                            o.save()

            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Marcadores alterados com sucesso.')

        return locals()

    raise PermissionDenied


def excluir_marcadores_consumo_alimentar(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)

    if request.user == atendimento.usuario_aberto:
        RespostaMarcadorNutricao.objects.filter(atendimento=atendimento).delete()
        FrequenciaAlimentarNutricao.objects.filter(atendimento=atendimento).delete()

        return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_anamnese', 'Marcadores removidos com sucesso.')

    raise PermissionDenied


@rtr()
@group_required(['Psicólogo'])
@permission_required('rh.eh_servidor')
def registrar_hora_atendimento(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Registrar Data/Hora do Atendimento - {atendimento.get_vinculo()}'
    obj = AtendimentoPsicologia.objects.filter(atendimento=atendimento)
    if obj.exists():
        obj = obj.latest('id')
        if obj.profissional != request.user:
            return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/?tab=aba_motivo', 'Você não pode editar este registro.', tag='error')
    else:
        obj = AtendimentoPsicologia()
    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento
    form = DataHoraAtendimentoPsicologicoForm(request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/?tab=aba_motivo', 'Data/hora do atendimento registrada com sucesso.')
    return locals()


@rtr()
@group_required(['Psicólogo'])
@permission_required('rh.eh_servidor')
def adicionar_anexo_psicologia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Anexo - {atendimento.get_vinculo()}'
    form = AnexoPsicologiaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.atendimento = atendimento
        o.cadastrado_por_vinculo = request.user.get_vinculo()
        o.save()
        return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/?tab=aba_anexos', 'Anexo registrado com sucesso.')
    return locals()


@rtr()
@group_required(['Psicólogo'])
@permission_required('rh.eh_servidor')
def editar_anexo_psicologia(request, anexo_id):
    anexo = get_object_or_404(AnexoPsicologia, pk=anexo_id)
    if request.user.get_vinculo() == anexo.cadastrado_por_vinculo:
        title = f'Editar Anexo - {anexo.atendimento.get_vinculo()}'
        form = AnexoPsicologiaForm(request.POST or None, request.FILES or None, instance=anexo)
        if form.is_valid():
            o = form.save(False)
            gera_string = str(uuid.uuid4())
            extensao = o.arquivo.url.split('.')
            if len(extensao) > 1:
                extensao = extensao[len(extensao) - 1]
                novo_nome = gera_string + '.' + extensao
            else:
                novo_nome = gera_string
            o.arquivo.name = novo_nome
            o.save()
            return httprr(f'/saude/atendimento_psicologico/{anexo.atendimento.id}/?tab=aba_anexos', 'Anexo editado com sucesso.')
    else:
        raise PermissionDenied
    return locals()


@rtr()
@group_required(['Psicólogo'])
@permission_required('rh.eh_servidor')
def remover_anexo_psicologia(request, anexo_id):
    anexo = get_object_or_404(AnexoPsicologia, pk=anexo_id)
    if request.user.get_vinculo() == anexo.cadastrado_por_vinculo:
        atendimento = anexo.atendimento
        anexo.delete()
        return httprr(f'/saude/atendimento_psicologico/{atendimento.id}/?tab=aba_anexos', 'Anexo removido com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('saude.view_atividadegrupo')
def relatorio_atendimento_odontologia(request: HttpRequest) -> dict | HttpResponse:
    title = 'Relatório de Atendimento de Odontologia'
    form = RelatorioAtendimentoForm(request.GET or None, request=request)
    if form.is_valid():
        atendimentos = Atendimento.objects.filter(tipo=TipoAtendimento.ODONTOLOGICO, aluno__isnull=False).exclude(
            situacao=SituacaoAtendimento.CANCELADO
        )
        data_inicial = form.cleaned_data.get('data_inicial')
        data_final = form.cleaned_data.get('data_final')
        campus = form.cleaned_data.get('campus')
        curso = form.cleaned_data.get('curso')
        turma = form.cleaned_data.get('turma')
        modalidade = form.cleaned_data.get('modalidade')
        sexo = form.cleaned_data.get('sexo')
        idade = form.cleaned_data.get('idade')
        participante = form.cleaned_data.get('participante')

        if data_inicial:
            atendimentos = atendimentos.filter(data_aberto__gte=datetime.datetime(data_inicial.year, data_inicial.month, data_inicial.day, 0, 0, 0))

        if data_final:
            atendimentos = atendimentos.filter(data_aberto__lte=datetime.datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59))

        if campus:
            atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=campus)

        if curso:
            atendimentos = atendimentos.filter(aluno__curso_campus=curso)

        if turma:
            alunos = turma.get_alunos_matriculados()
            atendimentos = atendimentos.filter(aluno__pessoa_fisica__in=alunos.values_list('aluno__pessoa_fisica', flat=True))

        if modalidade:
            atendimentos = atendimentos.filter(aluno__curso_campus__modalidade=modalidade)

        if sexo:
            atendimentos = atendimentos.filter(aluno__pessoa_fisica__sexo=sexo)

        if idade:
            try:
                int(idade)
                pessoas = PessoaFisica.objects.filter(id__in=atendimentos.values_list('aluno__pessoa_fisica', flat=True))
                ids = []
                for pessoa in pessoas:
                    if pessoa.idade == int(idade):
                        ids.append(pessoa.id)
                atendimentos = atendimentos.filter(aluno__pessoa_fisica__in=ids)
            except Exception:
                return httprr('/saude/relatorio_atendimento_odontologia/', 'Valor inválido para o campo "Idade".', tag='error')

        if participante:
            hoje = datetime.datetime.today()
            participantes = Participacao.objects.filter(Q(data_inicio__lte=hoje), Q(data_termino__gte=hoje) | Q(data_termino__isnull=True))
            atendimentos = atendimentos.filter(aluno__id__in=participantes.values_list('aluno', flat=True))

        if atendimentos.exists():
            media_cpo = media_c = media_p = media_o = 0
            total_alunos_atendidos = atendimentos.distinct('aluno').count()
            tabela = {}
            for indice in range(33):
                chave = f'{indice}'
                tabela[chave] = []

            for atendimento in atendimentos.distinct('aluno'):
                if atendimento.get_odontograma():
                    cpo, c, p, o = atendimento.get_odontograma().get_indice_cpod()

                    media_cpo += int(cpo)
                    media_c += int(c)
                    media_p += int(p)
                    media_o += int(o)
                    chave = f'{cpo}'
                    tabela[chave].append(atendimento.id)

            media_cpo = Decimal(float(media_cpo) / float(total_alunos_atendidos)).quantize(Decimal(10) ** -2)
            media_c = Decimal(float(media_c) / float(total_alunos_atendidos)).quantize(Decimal(10) ** -2)
            media_p = Decimal(float(media_p) / float(total_alunos_atendidos)).quantize(Decimal(10) ** -2)
            media_o = Decimal(float(media_o) / float(total_alunos_atendidos)).quantize(Decimal(10) ** -2)
            resultado = collections.OrderedDict(sorted(tabela.items(), reverse=True, key=lambda x: int(x[0])))
            dados = []
            for item in list(resultado.items()):
                qtd = len(item[1])
                if qtd:
                    dados.append([item[0], qtd])

            grafico1 = BarChart(
                'grafico1', title='Alunos por índice CPO-D ', subtitle='Número de alunos por índice CPO-D', minPointLength=0, data=dados
            )

            grafico1.id = 'grafico1'

            dados2 = []
            total = (
                ProcedimentoOdontologico.objects.filter(atendimento__in=atendimentos.values_list('id', flat=True))
                .values('procedimento__denominacao')
                .annotate(qtd=Count('procedimento__denominacao'))
                .order_by('procedimento__denominacao')
            )
            for registro in total:
                dados2.append([registro['procedimento__denominacao'], registro['qtd']])

            dados2.append(['Procedimentos Odontológicos', total.count()])

            grafico2 = BarChart(
                'grafico2',
                title='Procedimentos Odontológicos Realizados',
                subtitle='Quantitativo de Procedimentos Odontológicos Realizados',
                minPointLength=0,
                data=dados2,
            )

            grafico2.id = 'grafico2'

            dados3 = []
            total = Odontograma.objects.filter(atendimento__in=atendimentos.values_list('id', flat=True))
            for tipo in TipoConsultaOdontologia.objects.all():
                dados3.append([tipo.descricao, total.filter(tipo_consulta=tipo).count()])

            grafico3 = BarChart('grafico3', title='Quantitativo de Consultas', subtitle='Quantitativo de Consultas', minPointLength=0, data=dados3)

            grafico3.id = 'grafico3'

            pie_chart_lists = [grafico1, grafico2, grafico3, _grafico_gestantes_com_tratamento(atendimentos)]

    return locals()


def _grafico_gestantes_com_tratamento(atendimentos: QuerySet[Atendimento]) -> PieChart:
    """Tratamento odontológico dos atendimentos cuja versão mais recente do saúde-doença marca gestante (#17629)."""
    gravidas = _so_a_ficha_mais_recente(ProcessoSaudeDoenca.objects.filter(gestante=True))
    gravidas_atendidas = atendimentos.filter(id__in=gravidas.values_list('atendimento', flat=True))
    total = Odontograma.objects.filter(atendimento__in=gravidas_atendidas.values_list('id', flat=True))
    dados = [
        ['Tratamento Concluído', total.filter(tipo_consulta__id=TipoConsultaOdontologia.CONCLUIDO).count()],
        ['Tratamento em Andamento', total.exclude(tipo_consulta__id=TipoConsultaOdontologia.CONCLUIDO).count()],
    ]
    grafico = PieChart('grafico4', title='Gestantes com Tratamento Concluído', subtitle='Quantitativo de Consultas', minPointLength=0, data=dados)
    grafico.id = 'grafico4'
    return grafico


# Capítulos da CID-10: (título, primeiro código, último código).
CAPITULOS_CID10 = (
    ('Capítulo I - Algumas doenças infecciosas e parasitárias', 'A00', 'B99'),
    ('Capítulo II - Neoplasias [tumores]', 'C00', 'D48'),
    ('Capítulo III - Doenças do sangue e dos órgãos hematopoéticos e alguns transtornos imunitários', 'D50', 'D89'),
    ('Capítulo IV - Doenças endócrinas, nutricionais e metabólicas', 'E00', 'E90'),
    ('Capítulo V - Transtornos mentais e comportamentais', 'F00', 'F99'),
    ('Capítulo VI - Doenças do sistema nervoso', 'G00', 'G99'),
    ('Capítulo VII - Doenças do olho e anexos', 'H00', 'H59'),
    ('Capítulo VIII - Doenças do ouvido e da apófise mastóide', 'H60', 'H95'),
    ('Capítulo IX - Doenças do aparelho circulatório', 'I00', 'I99'),
    ('Capítulo X - Doenças do aparelho respiratório', 'J00', 'J99'),
    ('Capítulo XI - Doenças do aparelho digestivo', 'K00', 'K93'),
    ('Capítulo XII - Doenças da pele e do tecido subcutâneo', 'L00', 'L99'),
    ('Capítulo XIII - Doenças do sistema osteomuscular e do tecido conjuntivo', 'M00', 'M99'),
    ('Capítulo XIV - Doenças do aparelho geniturinário', 'N00', 'N99'),
    ('Capítulo XV - Gravidez, parto e puerpério', 'O00', 'O99'),
    ('Capítulo XVI - Algumas afecções originadas no período perinatal', 'P00', 'P96'),
    ('Capítulo XVII - Malformações congênitas, deformidades e anomalias cromossômicas', 'Q00', 'Q99'),
    ('Capítulo XVIII - Sintomas, sinais e achados anormais de exames clínicos e de laboratório, não classificados em outra parte', 'R00', 'R99'),
    ('Capítulo XIX - Lesões, envenenamento e algumas outras conseqüências de causas externas', 'S00', 'T98'),
    ('Capítulo XX - Causas externas de morbidade e de mortalidade', 'V01', 'Y98'),
    ('Capítulo XXI - Fatores que influenciam o estado de saúde e o contato com os serviços de saúde', 'Z00', 'Z99'),
    ('Capítulo XXII - Códigos para propósitos especiais', 'U04', 'U99'),
)


def _atendimentos_do_relatorio_medico_enfermagem(filtros: dict) -> QuerySet[Atendimento]:
    """Atendimentos médicos/enfermagem de alunos, não cancelados, segundo os filtros de ``RelatorioAtendimentoForm`` (menos a idade)."""
    atendimentos = Atendimento.objects.filter(tipo=TipoAtendimento.ENFERMAGEM_MEDICO, aluno__isnull=False).exclude(
        situacao=SituacaoAtendimento.CANCELADO
    )
    if data_inicial := filtros.get('data_inicial'):
        atendimentos = atendimentos.filter(data_aberto__gte=datetime.datetime(data_inicial.year, data_inicial.month, data_inicial.day, 0, 0, 0))
    if data_final := filtros.get('data_final'):
        atendimentos = atendimentos.filter(data_aberto__lte=datetime.datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59))
    if filtros.get('campus'):
        atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=filtros['campus'])
    if filtros.get('curso'):
        atendimentos = atendimentos.filter(aluno__curso_campus=filtros['curso'])
    if turma := filtros.get('turma'):
        alunos = turma.get_alunos_matriculados()
        atendimentos = atendimentos.filter(aluno__pessoa_fisica__in=alunos.values_list('aluno__pessoa_fisica', flat=True))
    if filtros.get('modalidade'):
        atendimentos = atendimentos.filter(aluno__curso_campus__modalidade=filtros['modalidade'])
    if filtros.get('sexo'):
        atendimentos = atendimentos.filter(aluno__pessoa_fisica__sexo=filtros['sexo'])
    if filtros.get('participante'):
        hoje = datetime.datetime.today()
        participantes = Participacao.objects.filter(Q(data_inicio__lte=hoje), Q(data_termino__gte=hoje) | Q(data_termino__isnull=True))
        atendimentos = atendimentos.filter(aluno__id__in=participantes.values_list('aluno', flat=True))
    return atendimentos


def _filtrar_por_idade(atendimentos: QuerySet[Atendimento], idade: str) -> QuerySet[Atendimento]:
    """Atendimentos de alunos com a idade informada; levanta ``ValueError`` quando ``idade`` não é um número."""
    idade_pedida = int(idade)
    pessoas = PessoaFisica.objects.filter(id__in=atendimentos.values_list('aluno__pessoa_fisica', flat=True))
    ids = [pessoa.id for pessoa in pessoas if pessoa.idade == idade_pedida]
    return atendimentos.filter(aluno__pessoa_fisica__in=ids)


def _grafico_cid10_por_capitulo(atendimentos: QuerySet[Atendimento]) -> BarChart:
    dados = [
        [titulo, atendimentos.filter(hipotesediagnostica__cid__codigo__gte=primeiro, hipotesediagnostica__cid__codigo__lte=ultimo).count()]
        for titulo, primeiro, ultimo in CAPITULOS_CID10
    ]
    grafico = BarChart(
        'grafico1',
        title='Diagnósticos do CID-10 por capítulo',
        subtitle='Quantidade de diagnósticos do CID-10 por capítulo',
        minPointLength=0,
        data=dados,
    )
    grafico.id = 'grafico1'
    return grafico


def _grafico_intervencoes_de_enfermagem(atendimentos: QuerySet[Atendimento]) -> BarChart:
    total = (
        IntervencaoEnfermagem.objects.filter(atendimento__in=atendimentos.values_list('id', flat=True))
        .values('procedimento_enfermagem__denominacao')
        .annotate(qtd=Count('procedimento_enfermagem__denominacao'))
        .order_by('procedimento_enfermagem__denominacao')
    )
    dados = [[registro['procedimento_enfermagem__denominacao'], registro['qtd']] for registro in total]
    grafico = BarChart(
        'grafico2', title='Intervenções de Enfermagem', subtitle='Quantitativo de Intervenções de Enfermagem', minPointLength=0, data=dados
    )
    grafico.id = 'grafico2'
    return grafico


def _grafico_alergias_alimentos_e_medicamentos(atendimentos: QuerySet[Atendimento]) -> BarChart:
    """Atendimentos com saúde-doença cuja última ficha declara alergia; a alimentar vale também pela nutrição mais recente do prontuário."""
    com_processo = atendimentos.filter(processosaudedoenca__isnull=False)
    dados = [
        ['Alunos com Alergias à Alimentos', _com_alergia_alimentos(com_processo).distinct().count()],
        ['Alunos com Alergias à Medicamentos', _com_alergia_medicamentos(com_processo).distinct().count()],
    ]
    grafico = BarChart(
        'grafico3',
        title='Alergias à Alimentos e Medicamentos',
        subtitle='Quantitativo de alunos com alergias à alimentos e medicamentos',
        minPointLength=0,
        data=dados,
    )
    grafico.id = 'grafico3'
    return grafico


@rtr()
@permission_required('saude.view_atividadegrupo')
def relatorio_atendimento_medico_enfermagem(request):
    title = 'Relatório de Atendimento Médico/Enfermagem'
    form = RelatorioAtendimentoForm(request.GET or None, request=request)
    if form.is_valid():
        atendimentos = _atendimentos_do_relatorio_medico_enfermagem(form.cleaned_data)
        if form.cleaned_data.get('idade'):
            try:
                atendimentos = _filtrar_por_idade(atendimentos, form.cleaned_data['idade'])
            except Exception:
                return httprr('/saude/relatorio_atendimento_medico_enfermagem/', 'Valor inválido para o campo "Idade".', tag='error')

        if 'xls' in request.GET:
            return tasks.relatorio_atendimento_medico_enfermagem_to_xls(atendimentos)
        if atendimentos.exists():
            pie_chart_lists = [
                _grafico_cid10_por_capitulo(atendimentos),
                _grafico_intervencoes_de_enfermagem(atendimentos),
                _grafico_alergias_alimentos_e_medicamentos(atendimentos),
            ]
    return locals()


@rtr()
@permission_required('saude.view_atividadegrupo')
def relatorio_atendimento_psicologia(request):
    title = 'Relatório de Atendimento de Psicologia'
    form = RelatorioAtendimentoForm(request.GET or None, request=request)
    if form.is_valid():
        data_inicial = form.cleaned_data.get('data_inicial')
        data_final = form.cleaned_data.get('data_final')
        campus = form.cleaned_data.get('campus')
        curso = form.cleaned_data.get('curso')
        turma = form.cleaned_data.get('turma')
        modalidade = form.cleaned_data.get('modalidade')
        sexo = form.cleaned_data.get('sexo')
        idade = form.cleaned_data.get('idade')
        participante = form.cleaned_data.get('participante')

        atendimentos = AtendimentoPsicologia.objects.filter(atendimento__aluno__isnull=False)

        if data_inicial:
            atendimentos = atendimentos.filter(
                data_atendimento__gte=datetime.datetime(data_inicial.year, data_inicial.month, data_inicial.day, 0, 0, 0)
            )

        if data_final:
            atendimentos = atendimentos.filter(data_atendimento__lte=datetime.datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59))

        if campus:
            atendimentos = atendimentos.filter(atendimento__usuario_aberto__vinculo__setor__uo=campus)

        if curso:
            atendimentos = atendimentos.filter(atendimento__aluno__curso_campus=curso)

        if turma:
            alunos = turma.get_alunos_matriculados()
            atendimentos = atendimentos.filter(atendimento__aluno__pessoa_fisica__in=alunos.values_list('aluno__pessoa_fisica', flat=True))

        if modalidade:
            atendimentos = atendimentos.filter(atendimento__aluno__curso_campus__modalidade=modalidade)

        if sexo:
            atendimentos = atendimentos.filter(atendimento__aluno__pessoa_fisica__sexo=sexo)

        if idade:
            try:
                int(idade)
                pessoas = PessoaFisica.objects.filter(id__in=atendimentos.values_list('aluno__pessoa_fisica', flat=True))
                ids = []
                for pessoa in pessoas:
                    if pessoa.idade == int(idade):
                        ids.append(pessoa.id)
                atendimentos = atendimentos.filter(atendimento__aluno__pessoa_fisica__in=ids)
            except Exception:
                return httprr('/saude/relatorio_atendimento_psicologia/', 'Valor inválido para o campo "Idade".', tag='error')

        if participante:
            hoje = datetime.datetime.today()
            participantes = Participacao.objects.filter(Q(data_inicio__lte=hoje), Q(data_termino__gte=hoje) | Q(data_termino__isnull=True))
            atendimentos = atendimentos.filter(atendimento__aluno__id__in=participantes.values_list('aluno', flat=True))

        dados = []
        total = (
            atendimentos.values('queixa_principal__descricao')
            .annotate(qtd=Count('queixa_principal__descricao'))
            .order_by('queixa_principal__descricao')
        )
        for registro in total:
            dados.append([registro['queixa_principal__descricao'], registro['qtd']])

        grafico1 = BarChart(
            'grafico1', title='Quantitativo por Queixa Principal', subtitle='Quantitativo por queixa principal', minPointLength=0, data=dados
        )

        grafico1.id = 'grafico1'

        dados2 = []
        total = (
            atendimentos.values('queixa_identificada__descricao')
            .annotate(qtd=Count('queixa_identificada__descricao'))
            .order_by('queixa_identificada__descricao')
        )
        for registro in total:
            dados2.append([registro['queixa_identificada__descricao'], registro['qtd']])

        grafico2 = BarChart(
            'grafico2', title='Quantitativo por Queixa Identificada', subtitle='Quantitativo por Queixa Identificada', minPointLength=0, data=dados2
        )

        grafico2.id = 'grafico2'

        dados3 = []
        total = (
            atendimentos.values('motivo_chegada__descricao').annotate(qtd=Count('motivo_chegada__descricao')).order_by('motivo_chegada__descricao')
        )
        for registro in total:
            dados3.append([registro['motivo_chegada__descricao'], registro['qtd']])

        grafico3 = BarChart(
            'grafico3', title='Quantitativo por Motivos de Busca', subtitle='Quantitativo por Motivos de Busca', minPointLength=0, data=dados3
        )

        grafico3.id = 'grafico3'
        pie_chart_lists = [grafico1, grafico2, grafico3]

    return locals()


@rtr()
@group_required('Odontólogo')
@permission_required('rh.eh_servidor')
def encaminhar_enfermagem_odonto(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    odontograma = atendimento.get_odontograma()
    if odontograma:
        odontograma.encaminhado_enfermagem = True
        odontograma.save()
        return httprr(f'/saude/atendimento_odontologico/{atendimento.id}/?tab=aba_procedimento', 'Atendimento encaminhado à enfermagem com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS_ATENDIMENTO_ENF)
@permission_required('rh.eh_servidor')
def registrar_intervencao_odonto(request, atendimento_id, atendimento_origem_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    odontograma = atendimento.get_odontograma()
    if odontograma and not odontograma.atendido:
        odontograma.atendido = True
        odontograma.atendido_por_vinculo = request.user.get_vinculo()
        odontograma.atendido_em = datetime.datetime.now()
        odontograma.save()
        return httprr(
            f'/saude/atendimento_medico_enfermagem/{atendimento_origem_id}/?tab=aba_intervencaoenfermagem',
            'A intervenção de enfermagem foi registrada com sucesso.',
        )
    else:
        raise PermissionDenied


@rtr()
@group_required([*Especialidades.GRUPOS, 'Aluno', 'Atendente', 'Assistente Social', 'Auditor'])
def agenda_atendimentos(request):
    title = 'Agenda de Atendimentos'
    especialidade = Especialidades(request.user)
    eh_profissional_saude = Especialidades.eh_profissional_saude(especialidade)
    eh_assistente_social = request.user.has_perm('ae.save_caracterizacao_do_campus')
    pode_cadastrar_horario = request.user.has_perm('saude.view_prontuario') or eh_assistente_social
    eh_aluno = False
    if request.user.eh_aluno:
        if request.user.get_relacionamento().situacao.ativo:
            eh_aluno = True
        else:
            return httprr('/', 'Apenas alunos com situação ativa podem agendar atendimentos.', tag='error')

    hoje = datetime.date.today()

    inicio_semana = hoje
    fim_semana = inicio_semana + datetime.timedelta(4)
    uo_ids = get_ids_uos(request.user)

    if 'campus' not in request.GET:
        if request.user.has_perm('ae.save_caracterizacao_do_campus'):
            return httprr(
                f'/saude/agenda_atendimentos/?campus=&especialidade=Assistente Social&data_inicio={inicio_semana}&data_final={fim_semana}&filtraratendimentos_form=Aguarde...'
            )

        elif not request.user.has_perm('saude.add_prontuario') and not eh_aluno:
            return httprr(
                f'/saude/agenda_atendimentos/?campus=&especialidade=Odontólogo&data_inicio={inicio_semana}&data_final={fim_semana}&filtraratendimentos_form=Aguarde...'
            )
        return httprr(
            f'/saude/agenda_atendimentos/?campus=&especialidade=Todos&disponivel=on&data_inicio={inicio_semana}&data_final={fim_semana}&filtraratendimentos_form=Aguarde...'
        )

    string = request.get_full_path()
    if '?' in string:
        string = string.split('?')[1]
    else:
        string = ''

    form = FiltrarAtendimentosForm(request.GET or None, request=request, eh_aluno=eh_aluno, uo_ids=uo_ids)
    if form.is_valid():
        especialidade = form.cleaned_data.get('especialidade')
        campus = form.cleaned_data.get('campus')
        data_inicial = form.cleaned_data.get('data_inicio') or inicio_semana
        data_final = form.cleaned_data.get('data_final') or fim_semana
        meus_agendamentos = form.cleaned_data.get('meus_agendamentos')
        disponivel = form.cleaned_data.get('disponivel')
        modalidade = form.cleaned_data.get('modalidade')

        horarios = HorarioAtendimento.objects.filter(data__gte=data_inicial, data__lte=data_final, cancelado=False).order_by('data', 'hora_termino')

        if campus:
            horarios = horarios.filter(campus=campus, cancelado=False).order_by('data', 'hora_termino')
        else:
            horarios = horarios.filter(campus__in=uo_ids, cancelado=False).order_by('data', 'hora_termino')

        if especialidade and especialidade != Especialidades.TODOS:
            horarios = horarios.filter(especialidade=especialidade)

        if meus_agendamentos:
            if pode_cadastrar_horario:
                horarios = horarios.filter(cadastrado_por_vinculo=request.user.get_vinculo())
            elif eh_aluno:
                horarios = horarios.filter(vinculo_paciente=request.user.get_vinculo())

        if disponivel:
            hoje = datetime.datetime.today().now()
            data_limite = hoje + datetime.timedelta(1)
            agora = datetime.datetime.today().now().time()

            horarios = horarios.filter(disponivel=True).exclude(data__lte=hoje).exclude(data=data_limite, hora_inicio__lt=agora)

        if modalidade:
            horarios = horarios.filter(modalidade=modalidade)

    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Atendente', 'Assistente Social'])
def adicionar_horario_atendimento_saude(request):
    especialidade = Especialidades(request.user)
    lista = []
    title = 'Adicionar Horário de Atendimento'
    especialidade = Especialidades(request.user)
    especialidade_professional = ''
    eh_atendente = not request.user.has_perm('saude.add_prontuario') and not request.user.has_perm('ae.save_caracterizacao_do_campus')
    if especialidade.is_odontologo() or eh_atendente:
        especialidade_professional = Especialidades.ODONTOLOGO
    elif especialidade.is_psicologo():
        especialidade_professional = Especialidades.PSICOLOGO
    elif especialidade.is_medico():
        especialidade_professional = Especialidades.MEDICO
    elif especialidade.is_nutricionista():
        especialidade_professional = Especialidades.NUTRICIONISTA
    elif especialidade.is_fisioterapeuta():
        especialidade_professional = Especialidades.FISIOTERAPEUTA
    elif especialidade.is_enfermeiro():
        especialidade_professional = Especialidades.ENFERMEIRO
    elif especialidade.is_tecnico_enfermagem():
        especialidade_professional = Especialidades.TECNICO_ENFERMAGEM
    elif especialidade.is_auxiliar_enfermagem():
        especialidade_professional = Especialidades.AUXILIAR_DE_ENFERMAGEM
    elif especialidade.is_tecnico_saude_bucal():
        especialidade_professional = Especialidades.TECNICO_SAUDE_BUCAL
    elif especialidade.is_assistente_social():
        especialidade_professional = Especialidades.ASSISTENTE_SOCIAL
    form = HorarioAtendimentoForm(
        request.GET or None, request=request, especialidade_professional=especialidade_professional, eh_atendente=eh_atendente
    )
    if form.is_valid():
        inicio = form.cleaned_data.get('hora_inicio_1')
        termino = form.cleaned_data.get('hora_termino_1')
        duracao = form.cleaned_data.get('duracao')
        data = form.cleaned_data.get('data')
        data_fim_periodo = form.cleaned_data.get('data_fim')
        especialidade_escolhida = form.cleaned_data.get('especialidade')
        campus_escolhido = form.cleaned_data.get('campus_escolhido')
        modalidade = form.cleaned_data.get('modalidade')
        campus_do_atendimento = campus_escolhido or get_uo(request.user)
        if data and inicio and termino and duracao and especialidade_escolhida:
            lista = []
            termino_atendimento = datetime.datetime.combine(data, inicio) + datetime.timedelta(minutes=duracao)
            horario_inicial = datetime.datetime.combine(data, inicio)
            while termino_atendimento <= datetime.datetime.combine(data, termino):
                hora_inicio = horario_inicial
                hora_termino = termino_atendimento
                string = f'{hora_inicio.time()} - {hora_termino.time()}'
                lista.append(string)
                horario_inicial = termino_atendimento
                termino_atendimento = termino_atendimento + datetime.timedelta(minutes=duracao)
            ConfirmarHorarioAtendimentoForm = GetConfirmarHorarioAtendimentoForm(lista=lista)
            form2 = ConfirmarHorarioAtendimentoForm()
            if request.GET.get('confirmado'):
                termino_atendimento = datetime.datetime.combine(data, inicio) + datetime.timedelta(minutes=duracao)
                while termino_atendimento <= datetime.datetime.combine(data, termino):
                    hora_inicio = horario_inicial
                    hora_termino = termino_atendimento
                    string = f'{hora_inicio.time()} - {hora_termino.time()}'
                    lista.append(string)
                    horario_inicial = termino_atendimento
                    termino_atendimento = termino_atendimento + datetime.timedelta(minutes=duracao)
                ConfirmarHorarioAtendimentoForm = GetConfirmarHorarioAtendimentoForm(lista=lista)
                form2 = ConfirmarHorarioAtendimentoForm()
                if request.GET.get('confirmado'):
                    if not data_fim_periodo:
                        data_fim_periodo = data
                    data_em_processamento = data
                    while data_em_processamento <= data_fim_periodo:
                        termino_atendimento = datetime.datetime.combine(data_em_processamento, inicio) + datetime.timedelta(minutes=duracao)
                        while termino_atendimento <= datetime.datetime.combine(data_em_processamento, termino):
                            if not HorarioAtendimento.objects.filter(
                                data=data_em_processamento,
                                hora_inicio=inicio,
                                hora_termino=termino_atendimento,
                                especialidade=especialidade_escolhida,
                                campus=campus_do_atendimento,
                                cadastrado_por_vinculo=request.user.get_vinculo(),
                                modalidade=modalidade,
                            ).exists():
                                novo_agendamento = HorarioAtendimento()
                                novo_agendamento.data = data_em_processamento
                                novo_agendamento.hora_inicio = inicio
                                novo_agendamento.hora_termino = termino_atendimento
                                novo_agendamento.cadastrado_em = datetime.datetime.now()
                                novo_agendamento.especialidade = especialidade_escolhida
                                novo_agendamento.modalidade = modalidade
                                if eh_atendente:
                                    novo_agendamento.cadastrado_por_vinculo = form.cleaned_data.get('profissional').get_vinculo()
                                    novo_agendamento.campus = get_uo(form.cleaned_data.get('profissional'))
                                else:
                                    novo_agendamento.cadastrado_por_vinculo = request.user.get_vinculo()
                                    novo_agendamento.campus = campus_do_atendimento
                                novo_agendamento.save()
                            else:
                                HorarioAtendimento.objects.filter(
                                    data=data_em_processamento,
                                    hora_inicio=inicio,
                                    hora_termino=termino_atendimento,
                                    especialidade=especialidade_escolhida,
                                    campus=campus_do_atendimento,
                                    cadastrado_por_vinculo=request.user.get_vinculo(),
                                    cancelado=True,
                                    modalidade=modalidade,
                                ).update(cancelado=False, disponivel=True, vinculo_paciente=None)
                            inicio = termino_atendimento
                            termino_atendimento = termino_atendimento + datetime.timedelta(minutes=duracao)
                        data_em_processamento = data_em_processamento + datetime.timedelta(days=1)
                        inicio = form.cleaned_data.get('hora_inicio_1')
                        termino = form.cleaned_data.get('hora_termino_1')

                return httprr('/saude/adicionar_horario_atendimento_saude/', 'Horário(s) de atendimento(s) registrado(s) com sucesso.')
    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Aluno'])
def reservar_horario_atendimento(request, horario_id):
    title = 'Agendar Horário'
    horario = get_object_or_404(HorarioAtendimento, pk=horario_id)
    uo_ids = get_ids_uos(request.user)
    url_origem = request.META.get('HTTP_REFERER', '.')
    if horario.campus_id not in uo_ids or not horario.dentro_prazo_agendamento():
        raise PermissionDenied
    if horario.disponivel:
        vinculo = request.user.get_vinculo()
        if vinculo.eh_aluno() and not vinculo.relacionamento.situacao.ativo:
            return httprr(url_origem, 'Alunos com situação de matrícula inativa não podem agendar atendimento.', tag='error')
        if horario.especialidade == Especialidades.AVALIACAO_BIOMEDICA:
            especialidade = Especialidades(request.user)
            eh_profissional_saude = Especialidades.eh_profissional_saude(especialidade)
            eh_paciente = not (eh_profissional_saude and (horario.campus == get_uo(request.user)))
        else:
            eh_paciente = vinculo != horario.cadastrado_por_vinculo
        form = PacienteAgendamentoForm(request.POST or None, url_origem=url_origem)
        if form.is_valid():
            vinculo = form.cleaned_data.get('pessoa')
            url_origem = form.cleaned_data.get('url_origem')
        if eh_paciente or form.is_valid():
            inicio_semana = horario.data - datetime.timedelta(horario.data.weekday())
            fim_semana = inicio_semana + datetime.timedelta(4)
            if HorarioAtendimento.objects.filter(
                especialidade=horario.especialidade,
                vinculo_paciente=vinculo,
                data__lte=fim_semana,
                data__gte=inicio_semana,
                cancelado=False,
                disponivel=False,
            ).exists():
                return httprr(url_origem, 'Você já possui atendimento marcado esta semana.', tag='error')
            if BloqueioAtendimentoSaude.objects.filter(
                vinculo_profissional=horario.cadastrado_por_vinculo, vinculo_paciente=vinculo, data__gt=horario.data
            ).exists():
                bloqueio = BloqueioAtendimentoSaude.objects.filter(
                    vinculo_profissional=horario.cadastrado_por_vinculo, vinculo_paciente=vinculo, data__gt=horario.data
                )[0]
                return httprr(
                    url_origem,
                    'Você só pode agendar atendimento com este profissional a partir de {}.'.format(bloqueio.data.strftime('%d/%m/%Y')),
                    tag='error',
                )
            horario.disponivel = False
            horario.vinculo_paciente = vinculo
            horario.save()
            titulo = '[SUAP] Agendamento de Atendimento de Saúde'
            texto = (
                '<h1>Saúde</h1>'
                '<h2>Agendamento de Atendimento de Saúde</h2>'
                '<p>Você possui um atendimento de saúde agendado. Data: {}, Horário: {}. Especialidade: {}</p>'
                '<p>Procure o setor de Saúde do seu campus para mais informações. Em caso de consulta de tele-atendimento, fique atento às informações no seu e-mail acadêmico.</p>'.format(
                    horario.data.strftime('%d/%m/%Y'), horario.hora_inicio.strftime('%H:%M'), horario.especialidade
                )
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [horario.vinculo_paciente])
            return httprr(url_origem, 'Horário de atendimento agendado com sucesso.')
    else:
        return httprr(url_origem, 'Horário de atendimento já agendado.', tag='error')

    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Aluno', 'Atendente', 'Assistente Social'])
def cancelar_horario_atendimento(request, horario_id):
    horario = get_object_or_404(HorarioAtendimento, pk=horario_id)
    if horario.pode_cancelar(request.user):
        if request.user.get_vinculo() == horario.cadastrado_por_vinculo or request.user.has_group_cached('Atendente'):
            if horario.vinculo_paciente:
                title = 'Justificativa do Cancelamento'
                form = JustificativaCancelamentoHorarioForm(request.POST or None, instance=horario)
                if form.is_valid():
                    o = form.save(False)
                    o.disponivel = False
                    o.cancelado = True
                    o.save()
                    titulo = '[SUAP] Cancelamento de Agendamento de Saúde'
                    texto = (
                        '<h1>Saúde</h1>'
                        '<h2>Cancelamento de Agendamento de Saúde</h2>'
                        f'<p>Seu agendamento com o(a) {horario.especialidade} foi cancelado pelo profissional responsável. Justificativa: {horario.motivo_cancelamento}</p>'
                        '<p>Procure o setor de Saúde do seu campus para mais informações.</p>'
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [horario.vinculo_paciente])
                    return httprr('/saude/agenda_atendimentos/', 'Horário de atendimento cancelado com sucesso.')
            else:
                horario.disponivel = False
                horario.cancelado = True
                horario.save()
                return httprr('/saude/agenda_atendimentos/', 'Horário de atendimento cancelado com sucesso.')

        else:
            horario.disponivel = True
            horario.vinculo_paciente = None
            horario.save()
            return httprr('/saude/agenda_atendimentos/', 'Horário de atendimento cancelado com sucesso.')

        return locals()

    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def bloquear_aluno_atendimento(request, horario_id):
    horario = get_object_or_404(HorarioAtendimento, pk=horario_id)
    if horario.pode_bloquear_aluno(request.user):
        bloqueado_ate = datetime.datetime.now().date() + datetime.timedelta(days=21)
        vinculo_paciente = horario.vinculo_paciente
        if not BloqueioAtendimentoSaude.objects.filter(
            vinculo_profissional=horario.cadastrado_por_vinculo, vinculo_paciente=vinculo_paciente, data=bloqueado_ate
        ).exists():
            novo_bloqueio = BloqueioAtendimentoSaude()
            novo_bloqueio.vinculo_profissional = horario.cadastrado_por_vinculo
            novo_bloqueio.vinculo_paciente = vinculo_paciente
            novo_bloqueio.data = bloqueado_ate
            novo_bloqueio.save()

            titulo = '[SUAP] Atendimento de Saúde'
            texto = (
                '<h1>Saúde</h1>'
                '<h2>Bloqueio de Paciente</h2>'
                'Você não poderá realizar agendamentos para atendimentos de saúde até o dia {}. Procure o setor de saúde do seu campus para mais detalhes.</p>'.format(
                    bloqueado_ate.strftime('%d/%m/%Y')
                )
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo_paciente])
            return httprr(
                '/saude/agenda_atendimentos/',
                f'{novo_bloqueio.vinculo_paciente.pessoa.nome} está bloqueado(a) até o dia {format_(novo_bloqueio.data)}.',
            )
        return httprr('/saude/agenda_atendimentos/', 'Aluno já bloqueado.')
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def desbloquear_aluno_atendimento(request, vinculo_paciente_id):
    vinculo_paciente = get_object_or_404(VinculoPessoa, pk=vinculo_paciente_id)
    if BloqueioAtendimentoSaude.objects.filter(vinculo_paciente=vinculo_paciente, data__gte=datetime.datetime.now().date()).exists():
        BloqueioAtendimentoSaude.objects.filter(vinculo_paciente=vinculo_paciente, data__gte=datetime.datetime.now().date()).update(
            data=datetime.datetime.now().date() + datetime.timedelta(days=-1)
        )
        titulo = '[SUAP] Atendimento de Saúde'
        texto = (
            '<h1>Saúde</h1>'
            '<h2>Desbloqueio de Paciente</h2>'
            'Você já pode realizar agendamentos para atendimentos de saúde. Procure o setor de saúde do seu campus para mais detalhes.</p>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo_paciente])
        return httprr('/saude/agenda_atendimentos/', f'{vinculo_paciente} está desbloqueado(a).')
    else:
        return httprr('/saude/agenda_atendimentos/', 'Aluno já está desbloqueado.')


@rtr()
@permission_required('saude.view_metaacaoeducativa')
def adicionar_acao_educativa(request, meta_id):
    title = 'Adicionar Ação Educativa'
    meta = get_object_or_404(MetaAcaoEducativa, pk=meta_id)
    if meta.ativo:
        if not meta.pode_adicionar_meta():
            return httprr(
                '/admin/saude/metaacaoeducativa/', 'Não é possível adicionar uma ação à uma meta de anos anteriores ao ano atual.', tag='error'
            )

        form = AtividadeGrupoForm(request.POST or None, eh_acao_educativa=True)
        if form.is_valid():
            o = form.save(False)
            o.uo = get_uo(request.user)
            o.meta = meta
            o.save()
            return httprr('/admin/saude/metaacaoeducativa/', 'Ação cadastrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('saude.view_metaacaoeducativa')
def adicionar_acao_educativa_sem_meta(request):
    title = 'Adicionar Ação Educativa'
    form = AtividadeGrupoForm(request.POST or None, eh_acao_educativa=True)
    if form.is_valid():
        o = form.save(False)
        o.uo = get_uo(request.user)
        o.save()
        return httprr('/admin/saude/metaacaoeducativa/', 'Ação cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('saude.view_metaacaoeducativa')
def visualizar_acoes_educativas(request, meta_id):
    title = 'Ações Educativas'
    meta = get_object_or_404(MetaAcaoEducativa, pk=meta_id)
    acoes = AtividadeGrupo.objects.filter(meta=meta)
    if not request.user.has_group_cached('Coordenador de Saúde Sistêmico'):
        acoes = acoes.filter(uo=get_uo(request.user))

    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Assistente Social'])
def registrar_execucao_acao_educativa(request, atividadegrupo_id):
    title = 'Registrar Execução da Ação Educativa'
    atividade = get_object_or_404(AtividadeGrupo, pk=atividadegrupo_id)
    if not atividade.tema and (atividade.cadastrado_por and atividade.cadastrado_por == request.user or not atividade.cadastrado_por):
        form = AtividadeGrupoForm(request.POST or None, eh_acao_educativa=True, instance=atividade)
        if form.is_valid():
            form.save()
            return httprr(f'/saude/visualizar_acoes_educativas/{atividade.meta_id}/', 'Execução da ação registrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required([*Especialidades.GRUPOS, 'Assistente Social'])
def visualizar_acao_educativa(request, atividadegrupo_id):
    atividade = get_object_or_404(AtividadeGrupo, pk=atividadegrupo_id)
    if (atividade.uo == get_uo(request.user)) or request.user.has_group_cached('Coordenador de Saúde Sistêmico'):
        title = 'Visualizar Ação Educativa'
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('saude.view_metaacaoeducativa')
def visualizar_meta_acao_educativa(request, meta_id):
    meta = get_object_or_404(MetaAcaoEducativa, pk=meta_id)
    pode_adicionar_indicador = request.user.has_group_cached('Coordenador de Saúde Sistêmico') and meta.ativo
    title = 'Visualizar Meta da Ação Educativa'
    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def cancelar_acao_educativa(request, atividadegrupo_id):
    atividade = get_object_or_404(AtividadeGrupo, pk=atividadegrupo_id)
    if (atividade.cadastrado_por and atividade.cadastrado_por == request.user) or not atividade.cadastrado_por:
        id_meta = atividade.meta_id
        atividade.delete()
        return httprr(f'/saude/visualizar_acoes_educativas/{id_meta}/', 'Ação cancelada com sucesso.')
    else:
        raise PermissionDenied


def _com_alergia_alimentos(atendimentos: QuerySet[Atendimento]) -> QuerySet[Atendimento]:
    """Atendimentos cuja ficha antiga de saúde-doença (a mais recente do atendimento) OU nutrição mais recente do prontuário declara alergia alimentar."""
    ultimo_processo = ProcessoSaudeDoenca.objects.filter(atendimento=OuterRef('pk')).order_by('-id')
    ultima_nutricao = NutricaoAlimentacao.objects.filter(atendimento__prontuario=OuterRef('prontuario')).order_by('-id')
    return atendimentos.annotate(
        ficha_alergia_alimentos=Subquery(ultimo_processo.values('alergia_alimentos')[:1]),
        nutricao_alergia_alimentos=Subquery(ultima_nutricao.values('tem_alergia_alimentos')[:1]),
    ).filter(Q(ficha_alergia_alimentos=True) | Q(nutricao_alergia_alimentos=True))


def _com_alergia_medicamentos(atendimentos: QuerySet[Atendimento]) -> QuerySet[Atendimento]:
    """Atendimentos cuja ficha de saúde-doença mais recente declara alergia a medicamentos."""
    ultimo_processo = ProcessoSaudeDoenca.objects.filter(atendimento=OuterRef('pk')).order_by('-id')
    return atendimentos.annotate(ficha_alergia_medicamentos=Subquery(ultimo_processo.values('alergia_medicamentos')[:1])).filter(
        ficha_alergia_medicamentos=True
    )


def _atendimentos_da_lista_de_alunos(filtros: dict) -> QuerySet[Atendimento]:
    """Atendimentos médicos/enfermagem com processo saúde-doença, um por aluno, segundo os filtros de ``ListaAlunosForm``.

    A alergia alimentar vale se a ficha antiga de saúde-doença do atendimento OU a nutrição mais recente do prontuário a declarar
    (o formulário atual só pergunta na Nutrição e Alimentação, como o prontuário já considera).
    """
    atendimentos = Atendimento.objects.filter(tipo=TipoAtendimento.ENFERMAGEM_MEDICO, processosaudedoenca__isnull=False, aluno__isnull=False)
    if filtros.get('campus'):
        atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=filtros['campus'])
    if filtros.get('curso'):
        atendimentos = atendimentos.filter(aluno__curso_campus=filtros['curso'])
    if filtros.get('turma'):
        atendimentos = atendimentos.filter(aluno__matriculaperiodo__matriculadiario__diario__turma=filtros['turma'])
    if filtros.get('situacao'):
        atendimentos = atendimentos.filter(aluno__situacao__ativo=filtros['situacao'])
    if filtros.get('alergia_alimentos'):
        atendimentos = _com_alergia_alimentos(atendimentos)
    if filtros.get('alergia_medicamentos'):
        atendimentos = _com_alergia_medicamentos(atendimentos)
    # Um por aluno (homônimos ficam separados), em ordem de nome; o ``DISTINCT ON`` exige as mesmas chaves à frente do ``order_by`` e
    # o ``-id`` final faz valer o atendimento mais recente do aluno (a ficha de alergia mostrada).
    return atendimentos.order_by('aluno__pessoa_fisica__nome', 'aluno_id', '-id').distinct('aluno__pessoa_fisica__nome', 'aluno_id')


@rtr()
@permission_required('saude.view_atividadegrupo')
def lista_alunos(request):
    title = 'Lista de Alunos'
    form = ListaAlunosForm(request.GET or None)
    if form.is_valid():
        ver_nome = form.cleaned_data['ver_nome']
        ver_matricula = form.cleaned_data['ver_matricula']
        ver_curso = form.cleaned_data['ver_curso']
        ver_turma = form.cleaned_data['ver_turma']
        ver_rg = form.cleaned_data['ver_rg']
        ver_cpf = form.cleaned_data['ver_cpf']
        ver_alergia_alimentos = bool(form.cleaned_data.get('alergia_alimentos'))
        ver_alergia_medicamentos = bool(form.cleaned_data.get('alergia_medicamentos'))
        atendimentos = _atendimentos_da_lista_de_alunos(form.cleaned_data)

        if 'xls' in request.GET:
            return tasks.lista_alunos_to_xls(
                atendimentos, ver_nome, ver_matricula, ver_curso, ver_turma, ver_rg, ver_cpf, ver_alergia_alimentos, ver_alergia_medicamentos
            )

    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Assistente Social'])
def cancelar_horarios_atendimentos(request):
    if request.POST and request.POST.getlist('action')[0] == 'Cancelar Horários':
        ids = request.POST.getlist('registros')
        if ids:
            if HorarioAtendimento.objects.filter(id__in=ids, vinculo_paciente__isnull=False).exists():
                return httprr('/saude/informar_motivo_cancelamento_horario/?ids={}'.format(','.join(ids)), 'Informe a justificativa de cancelamento')
            else:
                for horario in HorarioAtendimento.objects.filter(id__in=ids):
                    horario.disponivel = False
                    horario.cancelado = True
                    horario.save()
                return httprr('/saude/agenda_atendimentos/', 'Horários de atendimentos cancelados com sucesso.')
        else:
            return httprr('/saude/agenda_atendimentos/', 'Nenhum horário de atendimento selecionado.', tag='error')
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def adicionar_documento_prontuario(request, vinculo_id):
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    prontuario = Prontuario.get_prontuario(vinculo)
    title = f'Adicionar Documento - {prontuario.vinculo}'
    especialidade = Especialidades(request.user)
    eh_medico_ou_odontologo = especialidade.is_medico() or especialidade.is_odontologo()
    eh_medico = especialidade.is_medico()
    pode_requisicao_exames = eh_medico_ou_odontologo or especialidade.is_enfermeiro() or especialidade.is_fisioterapeuta()
    form = TipoDocumentoForm(
        request.POST or None, eh_medico_ou_odontologo=eh_medico_ou_odontologo, eh_medico=eh_medico, pode_requisicao_exames=pode_requisicao_exames
    )
    if form.is_valid():
        return httprr(
            '/saude/preencher_documento_prontuario/{}/{}/'.format(vinculo_id, form.cleaned_data.get('tipo')), 'Preencha os dados do documento.'
        )
    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def informar_motivo_cancelamento_horario(request: HttpRequest) -> HttpResponse | dict:
    title = 'Justificativa do Cancelamento'
    url_origem = request.META.get('HTTP_REFERER', '.')
    if request.POST:
        form = JustificativaCancelamentoHorariosForm(request.POST or None)
        if form.is_valid():
            motivo_cancelamento = form.cleaned_data.get('motivo_cancelamento')
            for item in ids_da_query(request):
                horario = get_object_or_404(HorarioAtendimento, pk=item)
                if horario.vinculo_paciente:
                    title = 'Justificativa do Cancelamento'
                    horario.disponivel = False
                    horario.cancelado = True
                    horario.motivo_cancelamento = motivo_cancelamento
                    horario.save()
                    titulo = '[SUAP] Cancelamento de Agendamento de Saúde'
                    texto = (
                        '<h1>Saúde</h1>'
                        '<h2>Cancelamento de Agendamento de Saúde</h2>'
                        f'<p>Seu agendamento com o(a) {horario.especialidade} foi cancelado pelo profissional responsável. Justificativa: {motivo_cancelamento}</p>'
                        '<p>Procure o setor de Saúde do seu campus para mais informações.</p>'
                    )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [horario.vinculo_paciente])
                else:
                    horario.disponivel = False
                    horario.cancelado = True
                    horario.motivo_cancelamento = motivo_cancelamento
                    horario.save()

            return httprr('/saude/agenda_atendimentos/', 'Horários de atendimentos cancelados com sucesso.')

    else:
        form = JustificativaCancelamentoHorariosForm(request.POST or None)
    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def preencher_documento_prontuario(request, vinculo_id, tipo):
    especialidade = Especialidades(request.user)
    eh_medico_ou_odontologo = especialidade.is_medico() or especialidade.is_odontologo()
    if not eh_medico_ou_odontologo and tipo != 1:
        raise PermissionDenied
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    prontuario = Prontuario.get_prontuario(vinculo)
    descricao_tipo_documento = DocumentoProntuario.TIPO_DOCUMENTO_CHOICES[int(tipo)][1]
    title = f'Preencher {descricao_tipo_documento} - {prontuario.vinculo}'
    vinculo_emissor_documento = request.user.get_vinculo()
    form = PreencherDocumentoForm(
        request.POST or None,
        tipo=tipo,
        nome_paciente=prontuario.vinculo.pessoa.nome,
        emissor_documento=vinculo_emissor_documento,
        vinculo_paciente=prontuario.vinculo,
    )
    if form.is_valid():
        o = form.save(False)
        o.prontuario = prontuario
        o.tipo = descricao_tipo_documento
        o.cadastrado_por_vinculo = vinculo_emissor_documento
        o.save()
        return httprr(f'/saude/prontuario/{vinculo_id}/?tab=aba_documentos', 'Documento cadastrado com sucesso.')
    return locals()


@documento(enumerar_paginas=False, validade=360)
@rtr()
@group_required(Especialidades.GRUPOS)
def imprimir_documento_prontuario(request, documento_id):
    documento = get_object_or_404(DocumentoProntuario, pk=documento_id)
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    hoje = documento.data
    campus = get_uo(documento.cadastrado_por_vinculo.user)
    tem_logo = Configuracao.get_valor_por_chave('comum', 'logo_instituicao')
    logo_if = tem_logo and default_storage.url(tem_logo) or '/static/comum/img/logo_instituicao.jpg'
    if campus.sigla == 'CNAT':
        titulo = 'Diretoria de Atividades Estudantis - DIAES'
    elif campus.sigla == get_sigla_reitoria():
        titulo = 'Diretoria de Gestão de Atividades Estudantis - DIGAE'
    else:
        titulo = 'Coordenação de Atividades Estudantis - COAES'

    if campus.sigla == 'CNAT':
        subtitulo = 'Coordenação de Saúde - CSAUDE'
    elif documento.tipo == DocumentoProntuario.RECEITUARIO:
        subtitulo = 'Serviço de Saúde'
    else:
        subtitulo = 'Setor de Saúde'
    reitoria = get_sigla_reitoria() and UnidadeOrganizacional.objects.get(equivalente=None, sigla=get_sigla_reitoria()) or ''
    return locals()


@documento(enumerar_paginas=False, validade=360)
@rtr('imprimir_documento_prontuario.html')
@group_required(Especialidades.GRUPOS)
def previsualizar_documento_prontuario(request):
    documento = DocumentoProntuario()
    documento.texto = request.POST.get('texto')
    documento.data = request.POST.get('data') or datetime.date.today().strftime('%Y-%m-%d')
    tipo = request.POST.get('tipo')
    try:
        documento.tipo = DocumentoProntuario.TIPO_DOCUMENTO_CHOICES[int(tipo)][1]
    except Exception:
        return httprr('/', 'É necessário selecionar um tipo válido.', 'error')
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    if documento.data:
        hoje = datetime.date.fromisoformat(documento.data)
    campus = get_uo(request.user)

    if campus.sigla == 'CNAT':
        titulo = 'Diretoria de Atividades Estudantis - DIAES'
    elif campus.sigla == get_sigla_reitoria():
        titulo = 'Diretoria de Gestão de Atividades Estudantis - DIGAE'
    else:
        titulo = 'Coordenação de Atividades Estudantis - COAES'

    if campus.sigla == 'CNAT':
        subtitulo = 'Coordenação de Saúde - CSAUDE'
    elif documento.tipo == DocumentoProntuario.RECEITUARIO:
        subtitulo = 'Serviço de Saúde'
    else:
        subtitulo = 'Setor de Saúde'
    return locals()


@rtr()
@group_required([*Especialidades.GRUPOS, 'Aluno', 'Atendente'])
def ver_calendario_agendamento(request):
    title = 'Calendário de Agendamento'
    eh_aluno = request.user.eh_aluno
    if eh_aluno and not request.user.get_relacionamento().situacao.ativo:
        return httprr('/', 'Apenas alunos com situação ativa podem agendar atendimentos.', tag='error')
    qs_solicitacoes = HorarioAtendimento.objects.all().order_by('data')
    cal_meses = []
    uo = ''
    uo_ids = get_ids_uos(request.user)
    if request.GET.get('campus'):
        uo = get_object_or_404(UnidadeOrganizacional, pk=request.GET.get('campus'))
        qs_solicitacoes = HorarioAtendimento.objects.filter(campus=uo)
    else:
        qs_solicitacoes = HorarioAtendimento.objects.filter(campus__in=uo_ids).order_by('data', 'hora_termino')

    data_agora = datetime.datetime.now()
    ano_corrente = data_agora.year
    mes_corrente = data_agora.month
    especialidade = Especialidades(request.user)
    pode_cadastrar_horario = Especialidades.eh_profissional_saude(especialidade)

    if request.GET.get('meus_agendamentos'):
        if pode_cadastrar_horario:
            qs_solicitacoes = qs_solicitacoes.filter(cadastrado_por_vinculo=request.user.get_vinculo())
        elif eh_aluno:
            qs_solicitacoes = qs_solicitacoes.filter(vinculo_paciente=request.user.get_vinculo())

    if request.GET.get('disponivel'):
        qs_solicitacoes = qs_solicitacoes.filter(disponivel=True)

    if request.GET.get('data_inicio'):
        try:
            data = datetime.datetime.strptime(request.GET.get('data_inicio'), '%Y-%m-%d')
        except Exception:
            return httprr('/saude/ver_calendario_agendamento/', 'Data inicial inválida.', tag='error')
        if data and data.year < 1900:
            return httprr('/saude/ver_calendario_agendamento/', 'O ano precisa ser maior do que 1900.', tag='error')

        qs_solicitacoes = qs_solicitacoes.filter(data__gte=data)
        ano_corrente = data.year
        mes_corrente = data.month

    if request.GET.get('data_final'):
        try:
            data_fim_informada = datetime.datetime.strptime(request.GET.get('data_final'), '%Y-%m-%d')
        except Exception:
            return httprr('/saude/ver_calendario_agendamento/', 'Data final inválida.', tag='error')
        if data_fim_informada and data_fim_informada.year < 1900:
            return httprr('/saude/ver_calendario_agendamento/', 'O ano precisa ser maior do que 1900.', tag='error')
        qs_solicitacoes = qs_solicitacoes.filter(data__lte=data_fim_informada)

    if request.GET.get('especialidade') and request.GET.get('especialidade') != Especialidades.TODOS:
        qs_solicitacoes = qs_solicitacoes.filter(especialidade=request.GET.get('especialidade'))

    if qs_solicitacoes.exists():
        data_fim = qs_solicitacoes.latest('data').data
        if (data_fim.year == ano_corrente and data_fim.month >= mes_corrente) or (data_fim.year > ano_corrente):
            ultimo_ano = data_fim.year
            ultimo_mes = data_fim.month
            cal = CalendarioPlus()
            cal.mostrar_mes_e_ano = True
            cal.destacar_hoje = False
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
                                if solicitacao.cancelado:
                                    css = 'error'
                                elif not solicitacao.vinculo_paciente and solicitacao.eh_disponivel():
                                    css = 'success'
                                elif solicitacao.vinculo_paciente:
                                    css = 'alert'
                                else:
                                    css = 'extra'
                                if eh_aluno:
                                    horario = f'{solicitacao.hora_inicio.strftime("%H:%M")}'
                                else:
                                    horario = f'{solicitacao.hora_inicio.strftime("%H:%M")} às {solicitacao.hora_termino.strftime("%H:%M")}'
                                descricao = f"""<strong>{horario}</strong>
                                <br>
                                    <dl>
                                        <dt>Especialidade:</dt><dd>{solicitacao.especialidade}</dd>
                                        <dt>Profissional:</dt><dd>{solicitacao.cadastrado_por_vinculo.pessoa.nome}</dd>"""

                                if solicitacao.vinculo_paciente and (
                                    pode_cadastrar_horario or solicitacao.vinculo_paciente == request.user.get_vinculo()
                                ):
                                    descricao += f'<dt>Paciente:</dt><dd>{solicitacao.vinculo_paciente.pessoa.nome}</dd>'

                                descricao += '</dl>'

                                cal.adicionar_evento_calendario(agenda_data_inicio, agenda_data_fim, descricao, css)
                    cal_meses.append(cal.formato_mes(ano, imes))

                mes = 1

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def excluir_documento_prontuario(request, documento_id):
    documento = get_object_or_404(DocumentoProntuario, pk=documento_id)
    if documento.cadastrado_por_vinculo == request.user.get_vinculo():
        prontuario = documento.prontuario
        documento.delete()
        return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_documentos', 'Documento excluído com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def adicionar_cartao_vacinal(request, vinculo_id):
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    prontuario = Prontuario.get_prontuario(vinculo)
    title = f'Adicionar Cartão Vacinal - {vinculo}'
    form = AdicionarCartaoVacinalForm(request.POST or None, request.FILES or None, instance=prontuario)
    if form.is_valid():
        with transaction.atomic():
            o = form.save(False)
            o.cadastrado_por_vinculo = request.user.get_vinculo()
            o.cadastrado_em = datetime.datetime.now()
            o.save()
            novo_registro = HistoricoCartaoVacinal()
            novo_registro.prontuario = prontuario
            novo_registro.vinculo = request.user.get_vinculo()
            novo_registro.cadastrado_em = datetime.datetime.now()
            novo_registro.save()
        return httprr(f'/saude/prontuario/{vinculo.id}/?tab=aba_cartao_vacinal', 'Cartão vacinal cadastrado com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def atendimento_fisioterapia(request, atendimento_id):
    title = 'Atendimento de Fisioterapia'
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id, tipo=TipoAtendimento.FISIOTERAPIA)
    pode_editar = (request.user == atendimento.usuario_aberto) and atendimento.situacao == SituacaoAtendimento.ABERTO

    pendencias = atendimento.tem_pendencia(request)

    especialidade = Especialidades(request.user)

    atendimento_fisioterapia = AtendimentoFisioterapia.objects.filter(atendimento=atendimento)
    atendimento_fisioterapia_responsavel = False
    if atendimento_fisioterapia.exists():
        atendimento_fisioterapia = atendimento_fisioterapia[0]
        atendimento_fisioterapia_responsavel = atendimento_fisioterapia.get_responsavel()

    cadastrou_antecedentes = False
    cadastrou_processosaudedoenca = False

    antecedentesfamiliares = AntecedentesFamiliares.objects.filter(atendimento=atendimento)
    antecedentesfamiliares_titulo = 'Antecedentes'
    antecedentesfamiliares_count = antecedentesfamiliares.count()
    if antecedentesfamiliares.exists():
        cadastrou_antecedentes = True
        antecedentesfamiliares = antecedentesfamiliares.latest('id')
        antecedentesfamiliares_responsavel = antecedentesfamiliares.get_responsavel()

    processosaudedoenca = ProcessoSaudeDoenca.objects.filter(atendimento=atendimento)
    processosaudedoenca_titulo = 'Processo Saúde-Doença'
    processosaudedoenca_count = processosaudedoenca.count()
    if processosaudedoenca.exists():
        cadastrou_processosaudedoenca = True
        processosaudedoenca = processosaudedoenca.latest('id')
        processosaudedoenca_responsavel = processosaudedoenca.get_responsavel()

    aba_antecedentes_preenchida = cadastrou_antecedentes or cadastrou_processosaudedoenca

    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_anamnese_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Anamnese - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = AnamneseFisioterapiaForm(request.POST or None, instance=obj, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_anamnese', 'Anamnese registrada com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_hipotese_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Hipótese Diagnóstica - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = HipoteseFisioterapiaForm(request.POST or None, instance=obj, request=request)

    if form.is_valid():
        form.save()
        return httprr(
            f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_hipotesediagnostica', 'Hipótese Diagnóstica registrada com sucesso.'
        )

    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_conduta_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Conduta de Fisioterapia - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = CondutaFisioterapiaForm(request.POST or None, instance=obj, request=request)

    if form.is_valid():
        form.save()
        return httprr(
            f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_hipotesediagnostica', 'Conduta de Fisioterapia registrada com sucesso.'
        )

    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_intervencao_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Intervenção de Fisioterapia - {atendimento.get_vinculo()}'

    condutas_medicas = CondutaMedica.objects.filter(atendimento=atendimento, encaminhado_fisioterapia=True, atendido_fisioterapia=False)

    form = IntervencaoFisioterapiaForm(request.POST or None, request=request, atendimento=atendimento)

    if form.is_valid():
        obj = IntervencaoFisioterapia()
        obj.profissional = request.user
        obj.data_cadastro = datetime.datetime.now()
        obj.atendimento = atendimento
        obj.conduta_medica = form.cleaned_data.get('conduta_medica')
        obj.descricao = form.cleaned_data.get('descricao')
        obj.save()

        if form.cleaned_data.get('conduta_medica'):
            CondutaMedica.objects.filter(id=form.cleaned_data.get('conduta_medica').id).update(atendido_fisioterapia=True)

        AtendimentoEspecialidade.cadastrar(atendimento, request)
        return httprr(
            f'/saude/atendimento_medico_enfermagem/{atendimento.id}/?tab=aba_intervencaofisioterapia',
            'Intervenção de fisioterapia registrada com sucesso.',
        )

    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_retorno_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Descrição da Evolução - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)

    obj.profissional = request.user
    obj.data_cadastro = datetime.datetime.now()
    obj.atendimento = atendimento

    form = RetornoFisioterapiaForm(request.POST or None, instance=obj, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_retorno', 'Evolução registrada com sucesso.')

    return locals()


@rtr()
@group_required(['Coordenador de Saúde Sistêmico'])
def reabrir_atendimento(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    atendimento.data_reaberto = datetime.datetime.today()
    atendimento.situacao = SituacaoAtendimento.REABERTO
    atendimento.usuario_reaberto = request.user
    atendimento.save()
    msg_sucesso = 'Atendimento reaberto com sucesso.'
    if atendimento.tipo == TipoAtendimento.AVALIACAO_BIOMEDICA:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_avaliacao_biomedica', msg_sucesso)
    elif atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_medico_enfermagem', msg_sucesso)
    elif atendimento.tipo == TipoAtendimento.ODONTOLOGICO:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_odontologico', msg_sucesso)
    elif atendimento.tipo == TipoAtendimento.PSICOLOGICO:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_psicologico', msg_sucesso)
    elif atendimento.tipo == TipoAtendimento.NUTRICIONAL:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_nutricional', msg_sucesso)
    elif atendimento.tipo == TipoAtendimento.FISIOTERAPIA:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_fisioterapia', msg_sucesso)
    elif atendimento.tipo == TipoAtendimento.MULTIDISCIPLINAR:
        return httprr(f'/saude/prontuario/{atendimento.prontuario.vinculo_id}/?tab=aba_atendimento_multidisciplinar', msg_sucesso)

    return locals()


@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def cartao_vacinal(request):
    vinculo_logado = request.user.get_vinculo()
    prontuario = Prontuario.get_prontuario(vinculo_logado)
    rnvacina_ativo = APIExterna.RNMAISVACINA.ativo
    title = f'Cartão Vacinal - {vinculo_logado}'
    pode_adicionar_cartao = not prontuario.cartao_vacinal or (
        HistoricoCartaoVacinal.objects.filter(prontuario=prontuario).exists()
        and HistoricoCartaoVacinal.objects.filter(prontuario=prontuario).latest('id').vinculo == vinculo_logado
    )
    vacinas = CartaoVacinal.objects.filter(prontuario=prontuario).order_by('id')
    grupo_vacina = Vacina.objects.filter(id__in=prontuario.vacinas.all().distinct()).order_by('-id')
    grupos = []
    for grupo in grupo_vacina:
        lista = []
        for registro_vacina in vacinas:
            if registro_vacina.vacina_id == grupo.id:
                lista.append(registro_vacina)
        grupos.append(lista)

    return locals()


@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def importar_vacinas_rnvacina_autoatendimento(request):
    vinculo_logado = request.user.get_vinculo()
    if not vinculo_logado:
        return httprr('/saude/cartao_vacinal/', 'Seu usuário não possui um vínculo ativo para solicitar a importação.', tag='error')
    prontuario = Prontuario.get_prontuario(vinculo_logado)
    try:
        resultado = importar_vacinas_rnvacina(prontuario, vinculo_logado, HistoricoImportacaoRNVacina.ORIGEM_AUTOATENDIMENTO)
    except ValidationError as e:
        if settings.DEBUG:
            raise
        return httprr('/saude/cartao_vacinal/', str(e), tag='error')
    return httprr('/saude/cartao_vacinal/', montar_mensagem_base_resultado_importacao_rnvacina(resultado))


@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def adicionar_cartao_vacinal_aluno(request):
    vinculo_logado = request.user.get_vinculo()
    prontuario = Prontuario.get_prontuario(vinculo_logado)
    title = f'Adicionar Cartão Vacinal - {vinculo_logado}'
    if not prontuario.cartao_vacinal or (
        HistoricoCartaoVacinal.objects.filter(prontuario=prontuario).exists()
        and HistoricoCartaoVacinal.objects.filter(prontuario=prontuario).latest('id').vinculo == vinculo_logado
    ):
        form = AdicionarCartaoVacinalForm(request.POST or None, request.FILES or None, instance=prontuario)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                novo_registro = HistoricoCartaoVacinal()
                novo_registro.prontuario = prontuario
                novo_registro.vinculo = vinculo_logado
                novo_registro.cadastrado_em = datetime.datetime.now()
                novo_registro.save()
            return httprr('/saude/cartao_vacinal/', 'Cartão vacinal cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(['Coordenador de Saúde Sistêmico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Médico'])
def historico_cartao_vacinal(request, vinculo_id):
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    prontuario = Prontuario.get_prontuario(vinculo)
    title = f'Histórico do Cartão Vacinal - {vinculo}'
    historico = HistoricoCartaoVacinal.objects.filter(prontuario=prontuario).order_by('-id')
    return locals()


@rtr(two_factor_authentication=True)
@group_required(Especialidades.GRUPOS)
def enviar_mensagem_aluno(request, vinculo_id, atendimento_id):
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    if atendimento.is_aberto():
        title = f'Enviar Mensagem - {vinculo}'
        form = EnviarMensagemForm(request.POST or None)
        if form.is_valid():
            titulo = '[SUAP] {}'.format(form.cleaned_data.get('titulo'))
            mensagem = form.cleaned_data.get('mensagem')
            enviada_por = '{}'
            texto = f'<h1>Saúde</h1><h2>Avaliação Biomédica</h2>{mensagem}</p><p>Mensagem enviada por: {request.user.get_vinculo().__str__()}</p>'
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo], categoria='Saúde: Avaliação Biomédica', salvar_no_banco=False)
            return httprr(f'/saude/avaliacao_biomedica/{atendimento_id}/', 'Mensagem enviada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def passaporte_vacinacao_covid(request):
    vinculo = request.user.get_vinculo()
    form = None
    title = 'Passaporte Vacinal da COVID'
    obj = None
    tem_teste = False
    if vinculo.eh_usuario_externo():
        return httprr('/', 'Usuários externos não tem vínculo com a instituição', 'error')
    if PassaporteVacinalCovid.objects.filter(vinculo=vinculo).exists():
        obj = PassaporteVacinalCovid.objects.filter(vinculo=vinculo).last()
        tem_teste = obj.resultadotestecovid_set.exists()
        cpf = obj.cpf
    else:
        cpf = vinculo.relacionamento.pessoa_fisica.cpf
    pode_cadastrar_teste = obj and obj.termo_aceito_em and not obj.atestado_medico and not obj.cartao_vacinal
    pode_adicionar_cartao_vacinal = not obj or obj.situacao_passaporte == PassaporteVacinalCovid.INVALIDO
    if (
        obj
        and obj.situacao_declaracao
        in (PassaporteVacinalCovid.AGUARDANDO_AUTODECLARACAO, PassaporteVacinalCovid.AGUARDANDO_VALIDACAO, PassaporteVacinalCovid.INDEFERIDA)
    ) or not obj:
        form = PassaporteVacinalCovidForm(request.POST or None, request.FILES or None, instance=obj, request=request)
        if form.is_valid():
            o = form.save(False)
            o.uo = get_uo(request.user)
            if cpf:
                o.cpf = cpf.replace('.', '').replace('-', '')
            o.recebeu_alguma_dose = False
            o.vinculo = vinculo
            if form.cleaned_data.get('tem_atestado_medico') == 'sim':
                o.possui_atestado_medico = True
                o.termo_aceito_em = None
            else:
                o.possui_atestado_medico = False
                o.atestado_medico = None
            o.atualizado_em = datetime.datetime.now()
            if form.cleaned_data.get('aceite_termo'):
                o.termo_aceito_em = datetime.datetime.now()
            o.situacao_declaracao = PassaporteVacinalCovid.AGUARDANDO_VALIDACAO
            o.save()
            return httprr('/saude/passaporte_vacinacao_covid/', 'Autodeclaração preenchida com sucesso.')
    return locals()


@transaction.atomic()
@rtr()
@permission_required('saude.view_passaportevacinalcovid')
def deferir_passaporte_vacinal(request, declaracao_id):
    url = request.META.get('HTTP_REFERER', '.')
    obj = get_object_or_404(PassaporteVacinalCovid, pk=declaracao_id)
    if pode_validar_passaporte(request, obj) and not obj.esquema_completo:
        obj.situacao_declaracao = PassaporteVacinalCovid.DEFERIDA
        if obj.possui_atestado_medico or obj.recebeu_alguma_dose or obj.cartao_vacinal:
            obj.situacao_passaporte = PassaporteVacinalCovid.VALIDO
        else:
            if obj.situacao_passaporte != PassaporteVacinalCovid.VALIDO:
                obj.situacao_passaporte = PassaporteVacinalCovid.INVALIDO
        obj.avaliada_por = request.user.get_vinculo()
        obj.avaliada_em = datetime.datetime.now()
        obj.justificativa_indeferimento = None
        obj.save()
        HistoricoValidacaoPassaporte.objects.create(
            passaporte=obj,
            possui_atestado_medico=obj.possui_atestado_medico,
            termo_aceito_em=obj.termo_aceito_em,
            avaliado_por=request.user.get_vinculo(),
            situacao_passaporte=obj.situacao_passaporte,
            situacao_declaracao=obj.situacao_declaracao,
        )
        titulo = '[SUAP] Saúde - Passaporte Vacinal da COVID'
        texto = (
            '<h1>Saúde</h1>'
            f'<h2>Passaporte Vacinal da COVID</h2><p>Sua declaração foi {obj.situacao_declaracao}.</p><p>Acesse o SUAP para mais detalhes.</p>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obj.vinculo], categoria='Saúde: Passaporte Vacinal', salvar_no_banco=True)
        return httprr(url, 'Passaporte vacinal avaliado com sucesso.')

    else:
        raise PermissionDenied


@transaction.atomic()
@rtr()
@permission_required('saude.view_passaportevacinalcovid')
def indeferir_passaporte_vacinal(request, declaracao_id):
    url = request.META.get('HTTP_REFERER', '.')
    obj = get_object_or_404(PassaporteVacinalCovid, pk=declaracao_id)
    if pode_validar_passaporte(request, obj) and not obj.esquema_completo:
        title = f'Indeferir Declaração - {obj}'
        form = JustificativaIndeferirPassaporteForm(request.POST or None, url_origem=url)
        if form.is_valid():
            obj.situacao_declaracao = PassaporteVacinalCovid.INDEFERIDA
            obj.situacao_passaporte = PassaporteVacinalCovid.INVALIDO
            obj.avaliada_por = request.user.get_vinculo()
            obj.avaliada_em = datetime.datetime.now()
            obj.justificativa_indeferimento = form.cleaned_data.get('justificativa')
            obj.save()
            HistoricoValidacaoPassaporte.objects.create(
                justificativa_indeferimento=form.cleaned_data.get('justificativa'),
                possui_atestado_medico=obj.possui_atestado_medico,
                termo_aceito_em=obj.termo_aceito_em,
                passaporte=obj,
                avaliado_por=request.user.get_vinculo(),
                situacao_passaporte=obj.situacao_passaporte,
                situacao_declaracao=obj.situacao_declaracao,
            )
            titulo = '[SUAP] Saúde - Passaporte Vacinal da COVID'
            texto = (
                '<h1>Saúde</h1>'
                f'<h2>Passaporte Vacinal da COVID</h2><p>Sua declaração foi {obj.situacao_declaracao}.</p><p>Acesse o SUAP para mais detalhes.</p>'
            )
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [obj.vinculo], categoria='Saúde: Passaporte Vacinal', salvar_no_banco=True)
            return httprr(form.cleaned_data.get('url_origem'), 'Passaporte vacinal avaliado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required(
    'saude.pode_ver_todos_passaportes, saude.pode_ver_passaportes_do_campus, saude.pode_ver_passaportes_dos_prestadores_do_campus, saude.pode_ver_passaportes_dos_alunos_do_curso'
)
def relatorio_passaporte_vacinal(request):
    title = 'Relatório de Passaporte Vacinal de COVID'
    campi_consulta = []
    campi_consulta.append(get_uo(request.user).id)
    if request.user.has_perm('saude.pode_ver_todos_passaportes'):
        registros = PassaporteVacinalCovid.objects.all().order_by('vinculo__pessoa__nome')
        todos_campi = True
    elif request.user.has_perm('saude.pode_ver_passaportes_do_campus'):
        eh_validador_intercampi = ValidadorIntercampi.objects.filter(vinculo=request.user.get_vinculo(), ativo=True)
        if eh_validador_intercampi.exists():
            campi_consulta += eh_validador_intercampi.values_list('campi', flat=True)
        registros = PassaporteVacinalCovid.objects.filter(uo__in=campi_consulta).order_by('vinculo__pessoa__nome')
        todos_campi = False
    elif request.user.has_perm('saude.pode_ver_passaportes_dos_prestadores_do_campus'):
        prestadores = PrestadorServico.objects.filter(
            setor__uo=get_uo(request.user), ativo=True, pessoa_fisica__cpf__isnull=False, ocupacaoprestador__isnull=False
        )
        registros = PassaporteVacinalCovid.objects.filter(
            vinculo__in=prestadores.values_list('vinculos', flat=True), uo=get_uo(request.user)
        ).order_by('vinculo__pessoa__nome')
        todos_campi = False
    if request.user.has_perm('saude.pode_ver_passaportes_dos_alunos_do_curso'):
        cursos = CursoCampus.objects.filter(coordenador=request.user.get_vinculo()) | CursoCampus.objects.filter(
            coordenador_2=request.user.get_vinculo()
        )
        alunos = Aluno.ativos.filter(curso_campus__in=cursos.values_list('id', flat=True))
        if (
            not request.user.has_perm('saude.pode_ver_passaportes_dos_prestadores_do_campus')
            and not request.user.has_perm('saude.pode_ver_todos_passaportes')
            and not request.user.has_perm('saude.pode_ver_passaportes_do_campus')
        ):
            registros = PassaporteVacinalCovid.objects.filter(
                vinculo__in=alunos.values_list('vinculos', flat=True), uo=get_uo(request.user)
            ).order_by('vinculo__pessoa__nome')
        else:
            registros = registros | PassaporteVacinalCovid.objects.filter(
                vinculo__in=alunos.values_list('vinculos', flat=True), uo=get_uo(request.user)
            ).order_by('vinculo__pessoa__nome')
        todos_campi = False

    form = RelatorioPassaporteCovidForm(request.GET or None, todos_campi=todos_campi, request=request, busca_nome=True, campi_consulta=campi_consulta)
    if form.is_valid():
        nome = form.cleaned_data.get('nome')
        situacao = form.cleaned_data.get('situacao')
        categoria = form.cleaned_data.get('categoria')
        uo = form.cleaned_data.get('uo')
        curso = form.cleaned_data.get('curso')
        turma = form.cleaned_data.get('turma')
        faixa_etaria = form.cleaned_data.get('faixa_etaria')
        situacao_declaracao = form.cleaned_data.get('situacao_declaracao')

        if nome:
            registros = registros.filter(Q(vinculo__pessoa__nome__icontains=nome) | Q(vinculo__user__username__icontains=nome))

        if situacao:
            registros = registros.filter(situacao_passaporte=situacao)

        if situacao_declaracao:
            registros = registros.filter(situacao_declaracao=situacao_declaracao)

        if categoria:
            if categoria == '1':
                registros = registros.filter(vinculo__user__eh_aluno=True)
            elif categoria == '2':
                registros = registros.filter(vinculo__user__eh_servidor=True)
            elif categoria == '3':
                registros = registros.filter(vinculo__user__eh_prestador=True)
            elif categoria == '4':
                registros = registros.filter(
                    vinculo__user__eh_servidor=True, vinculo__in=Servidor.objects.ativos().filter(eh_docente=True).values_list('vinculos', flat=True)
                )
            elif categoria == '5':
                registros = registros.filter(
                    vinculo__user__eh_servidor=True,
                    vinculo__in=Servidor.objects.ativos().filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True),
                )

        if uo:
            registros = registros.filter(uo=uo)

        if curso:
            registros = registros.filter(vinculo__in=Aluno.objects.filter(curso_campus=curso).values_list('vinculos', flat=True))

        if turma:
            alunos = turma.get_alunos_matriculados()
            registros = registros.filter(vinculo__in=alunos.values_list('aluno__vinculos', flat=True))

        if faixa_etaria:
            dezoito_anos = datetime.date.today() + relativedelta(years=-18)
            sessenta_anos = datetime.date.today() + relativedelta(years=-60)
            if faixa_etaria == '1':
                registros = registros.filter(vinculo__pessoa__pessoafisica__nascimento_data__gt=dezoito_anos)
            elif faixa_etaria == '2':
                registros = registros.filter(
                    vinculo__pessoa__pessoafisica__nascimento_data__lte=dezoito_anos, vinculo__pessoa__pessoafisica__nascimento_data__gt=sessenta_anos
                )
            elif faixa_etaria == '3':
                registros = registros.filter(vinculo__pessoa__pessoafisica__nascimento_data__lte=sessenta_anos)

    return locals()


@rtr()
@group_required('Chefe de Setor')
def relatorio_passaporte_vacinal_chefia(request):
    historico_funcao = (
        request.user.get_relacionamento().historico_funcao().filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False)
    )
    if historico_funcao.exists():
        setor = historico_funcao.latest('id').setor_suap
        title = f'Relatório de Passaporte Vacinal de COVID - Servidores sob sua chefia ({setor})'
        servidores_do_setor = Servidor.objects.ativos().filter(setor__in=setor.descendentes)

        registros = PassaporteVacinalCovid.objects.filter(vinculo__in=servidores_do_setor.values_list('vinculos', flat=True)).order_by(
            'vinculo__pessoa__nome'
        )
        form = RelatorioPassaporteCovidChefiaForm(request.GET or None)
        if form.is_valid():
            nome = form.cleaned_data.get('nome')
            situacao = form.cleaned_data.get('situacao')
            categoria = form.cleaned_data.get('categoria')
            uo = form.cleaned_data.get('uo')
            curso = form.cleaned_data.get('curso')
            turma = form.cleaned_data.get('turma')
            faixa_etaria = form.cleaned_data.get('faixa_etaria')
            situacao_declaracao = form.cleaned_data.get('situacao_declaracao')
            registrou_frequencia = form.cleaned_data.get('registrou_frequencia')

            if nome:
                registros = registros.filter(Q(vinculo__pessoa__nome__icontains=nome) | Q(vinculo__user__username__icontains=nome))

            if registrou_frequencia:
                data_inicio_checagem_ponto = Configuracao.get_valor_por_chave('saude', 'data_checagem_ponto')
                if data_inicio_checagem_ponto:
                    registros = registros.filter(
                        vinculo__in=Frequencia.objects.filter(
                            vinculo__in=servidores_do_setor.values_list('vinculo', flat=True), horario__gt=data_inicio_checagem_ponto
                        ).values_list('vinculo', flat=True)
                    )

            if situacao:
                registros = registros.filter(situacao_passaporte=situacao)

            if situacao_declaracao:
                registros = registros.filter(situacao_declaracao=situacao_declaracao)

            if categoria:
                if categoria == '1':
                    registros = registros.filter(vinculo__user__eh_aluno=True)
                elif categoria == '2':
                    registros = registros.filter(vinculo__user__eh_servidor=True)
                elif categoria == '3':
                    registros = registros.filter(vinculo__user__eh_prestador=True)
                elif categoria == '4':
                    registros = registros.filter(
                        vinculo__user__eh_servidor=True,
                        vinculo__in=Servidor.objects.ativos().filter(eh_docente=True).values_list('vinculos', flat=True),
                    )
                elif categoria == '5':
                    registros = registros.filter(
                        vinculo__user__eh_servidor=True,
                        vinculo__in=Servidor.objects.ativos().filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True),
                    )

            if uo:
                registros = registros.filter(uo=uo)

            if curso:
                registros = registros.filter(vinculo__in=Aluno.objects.filter(curso_campus=curso).values_list('vinculos', flat=True))

            if turma:
                alunos = turma.get_alunos_matriculados()
                registros = registros.filter(vinculo__in=alunos.values_list('aluno__vinculos', flat=True))

            if faixa_etaria:
                dezoito_anos = datetime.date.today() + relativedelta(years=-18)
                sessenta_anos = datetime.date.today() + relativedelta(years=-60)
                if faixa_etaria == '1':
                    registros = registros.filter(vinculo__pessoa__pessoafisica__nascimento_data__gt=dezoito_anos)
                elif faixa_etaria == '2':
                    registros = registros.filter(
                        vinculo__pessoa__pessoafisica__nascimento_data__lte=dezoito_anos,
                        vinculo__pessoa__pessoafisica__nascimento_data__gt=sessenta_anos,
                    )
                elif faixa_etaria == '3':
                    registros = registros.filter(vinculo__pessoa__pessoafisica__nascimento_data__lte=sessenta_anos)

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('saude.pode_ver_todos_passaportes, saude.pode_ver_passaportes_do_campus')
def relatorio_vacinacao_covid(request):
    title = 'Relatório de Vacinação da COVID'
    campi_consulta = []
    campi_consulta.append(get_uo(request.user).id)
    if request.user.has_perm('saude.pode_ver_todos_passaportes'):
        registros = PassaporteVacinalCovid.objects.all()
        todos_campi = True
    else:
        eh_validador_intercampi = ValidadorIntercampi.objects.filter(vinculo=request.user.get_vinculo(), ativo=True)
        if eh_validador_intercampi.exists():
            campi_consulta += eh_validador_intercampi.values_list('campi', flat=True)
        registros = PassaporteVacinalCovid.objects.filter(uo__in=campi_consulta).order_by('vinculo__pessoa__nome')
        todos_campi = False
    form = RelatorioPassaporteCovidForm(
        request.GET or None, todos_campi=todos_campi, request=request, busca_nome=False, campi_consulta=campi_consulta
    )
    if form.is_valid():
        situacao = form.cleaned_data.get('situacao')
        categoria = form.cleaned_data.get('categoria')
        uo = form.cleaned_data.get('uo')
        curso = form.cleaned_data.get('curso')
        turma = form.cleaned_data.get('turma')
        faixa_etaria = form.cleaned_data.get('faixa_etaria')
        situacao_declaracao = form.cleaned_data.get('situacao_declaracao')

        if situacao:
            registros = registros.filter(situacao_passaporte=situacao)

        if situacao_declaracao:
            registros = registros.filter(situacao_declaracao=situacao_declaracao)

        if categoria:
            if categoria == '1':
                registros = registros.filter(vinculo__user__eh_aluno=True)
            elif categoria == '2':
                registros = registros.filter(vinculo__user__eh_servidor=True)
            elif categoria == '3':
                registros = registros.filter(vinculo__user__eh_prestador=True)
            elif categoria == '4':
                registros = registros.filter(
                    vinculo__user__eh_servidor=True, vinculo__in=Servidor.objects.ativos().filter(eh_docente=True).values_list('vinculos', flat=True)
                )
            elif categoria == '5':
                registros = registros.filter(
                    vinculo__user__eh_servidor=True,
                    vinculo__in=Servidor.objects.ativos().filter(eh_tecnico_administrativo=True).values_list('vinculos', flat=True),
                )

        if uo:
            registros = registros.filter(uo=uo)

        if curso:
            registros = registros.filter(vinculo__in=Aluno.objects.filter(curso_campus=curso).values_list('vinculos', flat=True))

        if turma:
            alunos = turma.get_alunos_matriculados()
            registros = registros.filter(vinculo__in=alunos.values_list('aluno__vinculos', flat=True))

        if faixa_etaria:
            dezoito_anos = datetime.date.today() + relativedelta(years=-18)
            sessenta_anos = datetime.date.today() + relativedelta(years=-60)
            if faixa_etaria == '1':
                registros = registros.filter(vinculo__pessoa__pessoafisica__nascimento_data__gt=dezoito_anos)
            elif faixa_etaria == '2':
                registros = registros.filter(
                    vinculo__pessoa__pessoafisica__nascimento_data__lte=dezoito_anos, vinculo__pessoa__pessoafisica__nascimento_data__gt=sessenta_anos
                )
            elif faixa_etaria == '3':
                registros = registros.filter(vinculo__pessoa__pessoafisica__nascimento_data__lte=sessenta_anos)

        dados = []
        esquema_completo = registros.filter(esquema_completo=True)
        primeira_dose = registros.filter(data_primeira_dose__isnull=False, esquema_completo=False)
        dados.append(['Esquema Vacinal Completo', esquema_completo.count()])
        dados.append(['Primeira Dose', primeira_dose.count()])
        dados.append(['Sem registro de vacina no RN+Vacina', registros.filter(recebeu_alguma_dose=False, tem_cadastro=True).count()])
        dados.append(['Sem cadastro no RN+Vacina', registros.filter(recebeu_alguma_dose=False, tem_cadastro=False).count()])

        grafico = PieChart(
            'grafico',
            title='Percentuais de usuários com cada nível (dose) de vacinação.',
            subtitle='Quantitativo de usuários com esquema vacinal completo, com primeira dose ou sem registros de vacina no RN+Vacina',
            minPointLength=0,
            data=dados,
        )

        grafico.id = 'grafico'

        pie_chart_lists = [grafico]

    return locals()


@rtr()
@permission_required('saude.view_passaportevacinalcovid')
def ver_historico_validacao_passaporte(request, passaporte_id):
    passaporte = get_object_or_404(PassaporteVacinalCovid, pk=passaporte_id)
    if pode_validar_passaporte(request, passaporte):
        title = f'Histórico de Validação do Passaporte Vacinal: {passaporte}'
        historico = HistoricoValidacaoPassaporte.objects.filter(passaporte=passaporte).order_by('-avaliado_em')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def resultados_testes_covid(request, passaporte_id):
    passaporte = get_object_or_404(PassaporteVacinalCovid, pk=passaporte_id)
    if (
        (request.user.has_perm('saude.view_passaportevacinalcovid') and get_uo(request.user) == passaporte.uo)
        or request.user.has_group_cached('Validador de Passaporte Vacinal Sistêmico')
        or passaporte.vinculo == request.user.get_vinculo()
        or pode_validar_passaporte(request, passaporte)
    ):
        title = f'Resultados de Testes Covid: {passaporte}'
        pode_avaliar = request.user.has_perm('saude.view_passaportevacinalcovid')
        historico = ResultadoTesteCovid.objects.filter(passaporte=passaporte).order_by('-avaliado_em')
        return locals()
    else:
        raise PermissionDenied


@transaction.atomic()
@rtr()
@permission_required('saude.view_passaportevacinalcovid')
def deferir_teste_covid(request, resultado_id):
    url = request.META.get('HTTP_REFERER', '.')
    obj = get_object_or_404(ResultadoTesteCovid, pk=resultado_id)
    passaporte = obj.passaporte
    if pode_validar_passaporte(request, passaporte):
        obj.situacao = ResultadoTesteCovid.DEFERIDO
        obj.avaliado_por = request.user.get_vinculo()
        obj.avaliado_em = datetime.datetime.now()
        obj.save()
        if (obj.realizado_em + relativedelta(hours=72)) > datetime.datetime.now():
            passaporte.situacao_passaporte = PassaporteVacinalCovid.VALIDO
            passaporte.save()
        titulo = '[SUAP] Saúde - Validação do Resultado do Teste contra COVID'
        texto = (
            '<h1>Saúde</h1>'
            f'<h2>Validação do Resultado do Teste contra COVID</h2><p>O resultado do seu teste foi {obj.situacao}.</p><p>Acesse o SUAP para mais detalhes.</p>'
        )
        send_notification(
            titulo, texto, settings.DEFAULT_FROM_EMAIL, [passaporte.vinculo], categoria='Saúde: Resultado do Teste contra COVID', salvar_no_banco=True
        )
        return httprr(url, 'Resultado do teste avaliado com sucesso.')

    else:
        raise PermissionDenied


@transaction.atomic()
@rtr()
@permission_required('saude.view_passaportevacinalcovid')
def indeferir_teste_covid(request, resultado_id):
    url = request.META.get('HTTP_REFERER', '.')
    obj = get_object_or_404(ResultadoTesteCovid, pk=resultado_id)
    passaporte = obj.passaporte
    if pode_validar_passaporte(request, passaporte):
        title = f'Indeferir Resultado do Teste Covid - {passaporte}'
        form = JustificativaIndeferirPassaporteForm(request.POST or None, url_origem=url)
        if form.is_valid():
            obj.situacao = ResultadoTesteCovid.INDEFERIDO
            obj.avaliado_por = request.user.get_vinculo()
            obj.avaliado_em = datetime.datetime.now()
            obj.justificativa_indeferimento = form.cleaned_data.get('justificativa')
            obj.save()
            if (obj.realizado_em + relativedelta(hours=72)) > datetime.datetime.now():
                passaporte.situacao_passaporte = PassaporteVacinalCovid.INVALIDO
                passaporte.data_expiracao = None
                passaporte.save()
            titulo = '[SUAP] Saúde - Validação do Resultado do Teste contra COVID'
            texto = (
                '<h1>Saúde</h1>'
                f'<h2>Validação do Resultado do Teste contra COVID</h2><p>O resultado do seu teste foi {obj.situacao}.</p><p>Acesse o SUAP para mais detalhes.</p>'
            )
            send_notification(
                titulo,
                texto,
                settings.DEFAULT_FROM_EMAIL,
                [passaporte.vinculo],
                categoria='Saúde: Resultado do Teste contra COVID',
                salvar_no_banco=True,
            )
            return httprr(form.cleaned_data.get('url_origem'), 'Resultado do teste avaliado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@transaction.atomic()
@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def cadastrar_cartao_vacinal_covid(request):
    title = 'Cadastrar Cartão Vacinal Covid-19'
    obj = None
    tem_teste = False
    vinculo = request.user.get_vinculo()
    if PassaporteVacinalCovid.objects.filter(vinculo=vinculo).exists():
        obj = PassaporteVacinalCovid.objects.filter(vinculo=vinculo).last()
        cpf = obj.cpf
    else:
        if request.user.eh_aluno:
            cpf = vinculo.relacionamento.pessoa_fisica.cpf
        else:
            cpf = vinculo.relacionamento.cpf
    pode_adicionar_cartao_vacinal = not obj or obj.situacao_passaporte == PassaporteVacinalCovid.INVALIDO
    if pode_adicionar_cartao_vacinal:
        form = CadastroCartaoVacinalCovidForm(request.POST or None, request.FILES or None, instance=obj, request=request)
        if form.is_valid():
            o = form.save(False)
            o.cartao_vacinal_cadastrado_em = datetime.datetime.now()
            o.situacao_declaracao = PassaporteVacinalCovid.AGUARDANDO_VALIDACAO
            o.uo = get_uo(request.user)
            if cpf:
                o.cpf = cpf.replace('.', '').replace('-', '')
            o.vinculo = vinculo
            o.save()
            return httprr('/saude/passaporte_vacinacao_covid/', 'Cartão vacinal Covid-19 cadastrado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('saude.view_notificacaocovid')
def monitorar_notificacao_covid(request, notificacao_id):
    notificacao = get_object_or_404(NotificacaoCovid, pk=notificacao_id)
    if (notificacao.uo == get_uo(request.user) or request.user.has_perm('saude.add_sintoma')) and notificacao.pode_monitorar():
        title = f'Monitorar Notificação - {notificacao.vinculo}'
        url = request.META.get('HTTP_REFERER', '.')
        form = MonitorarNotificacaoForm(request.POST or None, url=url)
        if form.is_valid():
            o = form.save(False)
            o.notificacao = notificacao
            o.cadastrado_por = request.user.get_vinculo()
            o.save()
            notificacao.monitoramento = form.cleaned_data.get('situacao')
            notificacao.save()
            return httprr(form.cleaned_data.get('url_origem'), 'Notificação de Síndromes Gripais e Covid-19 monitorada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('saude.view_notificacaocovid')
def ver_monitoramentos_covid(request, notificacao_id):
    notificacao = get_object_or_404(NotificacaoCovid, pk=notificacao_id)
    if notificacao.uo == get_uo(request.user):
        title = f'Monitoramentos da Notificação - {notificacao.vinculo}'
        monitoramentos = MonitoramentoCovid.objects.filter(notificacao=notificacao).order_by('-cadastrado_em')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(['Servidor', 'Aluno', 'Prestador de Serviço'])
def relatorio_notificacao_covid(request):
    title = 'Relatório de Notificações da Covid-19'
    if request.user.get_vinculo().eh_usuario_externo():
        return httprr('/', 'Usuários externos não tem vínculo com a instituição', 'error')
    if request.user.has_group_cached(['Coordenador de Atividades Estudantis Sistêmico', 'Coordenador de Gestão de Pessoas Sistêmico']):
        registros = NotificacaoCovid.objects.all()
        todos_campi = True
    else:
        registros = NotificacaoCovid.objects.filter(uo=get_uo(request.user))
        todos_campi = False
    form = RelatorioNotificacaoCovidForm(request.GET or None, todos_campi=todos_campi, request=request)
    if form.is_valid():
        categoria = form.cleaned_data.get('categoria')
        uo = form.cleaned_data.get('uo')
        curso = form.cleaned_data.get('curso')
        turma = form.cleaned_data.get('turma')
        setor = form.cleaned_data.get('setor')

        if categoria:
            if categoria == '1':
                registros = registros.filter(vinculo__user__eh_aluno=True)
            elif categoria == '2':
                registros = registros.filter(vinculo__user__eh_servidor=True)
            elif categoria == '3':
                registros = registros.filter(vinculo__user__eh_prestador=True)
        if uo:
            registros = registros.filter(uo=uo)

        if setor:
            servidores_do_setor = Servidor.objects.ativos().filter(setor__in=setor.descendentes)
            registros = registros.filter(vinculo__in=servidores_do_setor.values_list('vinculos', flat=True))

        if curso:
            registros = registros.filter(vinculo__in=Aluno.objects.filter(curso_campus=curso).values_list('vinculos', flat=True))

        if turma:
            alunos = turma.get_alunos_matriculados()
            registros = registros.filter(vinculo__in=alunos.values_list('aluno__vinculos', flat=True))

        dados = []
        dados.append(['Sem monitoramento', registros.filter(monitoramento='Sem monitoramento').count()])
        dados.append(['Suspeito em monitoramento', registros.filter(monitoramento='Suspeito em monitoramento').count()])
        dados.append(['Confirmado em monitoramento', registros.filter(monitoramento='Confirmado em monitoramento').count()])
        dados.append(['Descartado', registros.filter(monitoramento='Descartado').count()])
        dados.append(['Recuperado', registros.filter(monitoramento='Recuperado').count()])
        dados.append(['Óbito', registros.filter(monitoramento='Óbito').count()])

        grafico = BarChart(
            'grafico',
            title='Quantidade de notificações por Situação',
            subtitle='Quantidade de notificações por Situação (aguardando monitoramento, suspeito em monitoramento, confirmado em monitoramento, descartado, recuperado ou óbito)',
            minPointLength=0,
            data=dados,
        )

        grafico.id = 'grafico'

        pie_chart_lists = [grafico]

    return locals()


@rtr()
@permission_required('saude.pode_verificar_passaportes')
def verificacao_passaporte_vacinal(request):
    title = 'Verificar Passaporte Vacinal'
    form = VerificaPassaporteForm(request.POST or None)
    if form.is_valid():
        nome = form.cleaned_data.get('nome')
        registros = PassaporteVacinalCovid.objects.filter(Q(vinculo__pessoa__nome__icontains=nome) | Q(vinculo__user__username__icontains=nome))
    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_encaminhamento_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Descrição do Encaminhamento - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)
    if not obj.encaminhado_medico:
        form = EncaminhamentoFisioterapiaForm(request.POST or None, request=request)
        if form.is_valid():
            o = form.save(False)
            o.atendimento = obj
            o.cadastrado_por = request.user.get_vinculo()
            o.save()
            obj.encaminhado_medico = True
            obj.save()

            return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_encaminhamento', 'Encaminhamento cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def editar_encaminhamento_fisioterapia(request, encaminhamento_id):
    encaminhamento = get_object_or_404(EncaminhamentoFisioterapia, pk=encaminhamento_id)
    if encaminhamento.cadastrado_por == request.user.get_vinculo() and not encaminhamento.avaliado_em:
        atendimento = encaminhamento.atendimento.atendimento
        title = f'Editar Encaminhamento - {atendimento.get_vinculo()}'
        form = EncaminhamentoFisioterapiaForm(request.POST or None, instance=encaminhamento, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_encaminhamento', 'Encaminhamento editado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def excluir_encaminhamento_fisioterapia(request, encaminhamento_id):
    encaminhamento = get_object_or_404(EncaminhamentoFisioterapia, pk=encaminhamento_id)
    if encaminhamento.cadastrado_por == request.user.get_vinculo() and not encaminhamento.avaliado_em:
        atendimento = encaminhamento.atendimento.atendimento
        fisio = encaminhamento.atendimento
        encaminhamento.delete()
        fisio.encaminhado_medico = False
        fisio.save()
        return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_encaminhamento', 'Encaminhamento excluído com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.MEDICO)
@permission_required('rh.eh_servidor')
def avaliar_encaminhamento_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Avaliação Médica de Fisioterapia - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)
    encaminhamento = EncaminhamentoFisioterapia.objects.get(atendimento=obj, avaliado_em=None)
    form = AvaliarAtendimentoFisioterapiaForm(request.POST or None, request=request, instance=encaminhamento)
    if form.is_valid():
        o = form.save(False)
        o.avaliado_em = datetime.datetime.now()
        o.avaliado_por = request.user.get_vinculo()
        o.save()
        fisio = encaminhamento.atendimento
        fisio.encaminhado_medico = False
        fisio.save()
        return httprr('/saude/prontuarios/', 'Encaminhamento de fisioterapia avaliado com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def adicionar_procedimento_fisioterapia(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Cadastrar procedimentos - {atendimento.get_vinculo()}'
    obj = get_object_or_404(AtendimentoFisioterapia, atendimento=atendimento)
    if not obj.encaminhado_medico:
        form = ProcedimentoAtendimentoFisioterapiaForm(request.POST or None, request=request)
        if form.is_valid():
            o = form.save(False)
            o.cadastrado_por = request.user.get_vinculo()
            o.atendimento = obj
            o.save()
            form.save_m2m()
            return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_procedimentos', 'Procedimentos cadastrados com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def editar_procedimento_fisioterapia(request, procedimento_id):
    procedimento = get_object_or_404(ProcedimentoAtendimentoFisioterapia, pk=procedimento_id)
    if procedimento.cadastrado_por == request.user.get_vinculo():
        atendimento = procedimento.atendimento.atendimento
        title = f'Editar Procedimentos - {atendimento.get_vinculo()}'
        form = ProcedimentoAtendimentoFisioterapiaForm(request.POST or None, instance=procedimento, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_procedimentos', 'Procedimentos editados com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.FISIOTERAPEUTA)
@permission_required('rh.eh_servidor')
def excluir_procedimento_fisioterapia(request, procedimento_id):
    procedimento = get_object_or_404(ProcedimentoAtendimentoFisioterapia, pk=procedimento_id)
    if procedimento.cadastrado_por == request.user.get_vinculo():
        atendimento = procedimento.atendimento.atendimento
        procedimento.delete()
        return httprr(f'/saude/atendimento_fisioterapia/{atendimento.id}/?tab=aba_procedimentos', 'Procedimentos excluídos com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def adicionar_anexo_prontuario(request, vinculo_id):
    vinculo = get_object_or_404(VinculoPessoa, id=vinculo_id)
    prontuario = Prontuario.get_prontuario(vinculo)
    title = f'Adicionar Anexo - {prontuario.vinculo}'
    especialidade = Especialidades(request.user)
    eh_medico_ou_odontologo = especialidade.is_medico() or especialidade.is_odontologo()
    eh_medico = especialidade.is_medico()
    form = AnexoProntuarioForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        o = form.save(False)
        o.cadastrado_por = request.user.get_vinculo()
        o.prontuario = prontuario
        o.save()
        return httprr(f'/saude/prontuario/{vinculo_id}/?tab=aba_anexos', 'Anexo cadastrado com sucesso.')
    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def editar_anexo_prontuario(request, anexo_id):
    anexo = get_object_or_404(AnexoProntuario, pk=anexo_id)
    if anexo.cadastrado_por == request.user.get_vinculo():
        title = f'Editar Anexo - {anexo}'
        form = AnexoProntuarioForm(request.POST or None, request.FILES or None, instance=anexo)
        if form.is_valid():
            form.save()
            return httprr(f'/saude/prontuario/{anexo.prontuario.vinculo.id}/?tab=aba_anexos', 'Anexo editado com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@group_required(Especialidades.GRUPOS)
def excluir_anexo_prontuario(request, anexo_id):
    anexo = get_object_or_404(AnexoProntuario, pk=anexo_id)
    if anexo.cadastrado_por == request.user.get_vinculo():
        prontuario = anexo.prontuario
        anexo.delete()
        return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_anexos', 'Anexo excluído com sucesso.')

    else:
        raise PermissionDenied


@rtr()
@group_required('Aluno')
def registrar_presenca_atividade_grupo(request, atividade_id):
    atividade = get_object_or_404(AtividadeGrupo, pk=atividade_id)
    if (
        atividade.turma
        and request.user.eh_aluno
        and request.user.get_relacionamento().id in atividade.turma.get_alunos_matriculados().values_list('aluno', flat=True)
    ):
        RegistroPresencaAtividadeGrupo.objects.get_or_create(atividade=atividade, aluno=request.user.get_relacionamento())
        return httprr('/', 'Presença registrada com sucesso.')
    else:
        raise PermissionDenied


def _grafico(classe: type[Chart], nome: str, titulo: str, subtitulo: str, dados: list, id_div: str | None = None) -> Chart:
    """Monta um gráfico do relatório de avaliação; o ``id`` é o da div que o recebe no template."""
    grafico = classe(nome, title=titulo, subtitle=subtitulo, minPointLength=0, data=dados)
    grafico.id = id_div or nome
    return grafico


# Rótulo da fatia de quem não respondeu a pergunta do gráfico.
NAO_INFORMADO = 'Não Informado'


def _fatias(grafico: Chart) -> list:
    """Pares (rótulo, valor) da série única: o PieChart guarda os pares; o BarChart, rótulos no eixo x e valores na série."""
    valores = grafico.series[0]['data']
    if isinstance(grafico, BarChart):
        return list(zip(grafico.xAxis['categories'], valores, strict=True))
    return valores


def _graficos_com_dado(graficos: list[Chart]) -> list[Chart]:
    """Esconde os gráficos sem dado no período (#17622).

    Um gráfico está "sem dado" quando a soma dos seus valores é 0, ou quando as únicas fatias com
    valor maior que 0 são ``NAO_INFORMADO``. É o caso das perguntas que saíram dos forms das fichas
    (Demanda 2301): as fichas novas nascem com o campo nulo. Períodos com fichas antigas preenchidas
    continuam mostrando o gráfico. Todos os gráficos montados aqui (``_grafico``) são PieChart ou
    BarChart de uma série só.
    """
    return [grafico for grafico in graficos if any(rotulo != NAO_INFORMADO and (valor or 0) > 0 for rotulo, valor in _fatias(grafico))]


def _contagem(registros: QuerySet, campo: str) -> QuerySet:
    """Quantidade de registros por valor de ``campo`` (linhas ``{campo: valor, 'qtd': n}``)."""
    return registros.values(campo).annotate(qtd=Count(campo)).order_by(campo)


def _rotular(contagem: Iterable[dict], campo: str, rotulos: Mapping, padrao: str | None = None) -> list:
    """Troca cada valor pelo seu rótulo; sem rótulo nem ``padrao``, a linha é descartada."""
    dados = []
    for registro in contagem:
        rotulo = rotulos.get(registro[campo], padrao)
        if rotulo is not None:
            dados.append([rotulo, registro['qtd']])
    return dados


def _rotular_sim_nao(contagem: Iterable[dict], campo: str, sim: str, nao: str) -> list:
    """Rótulo pela veracidade do valor: ``None`` cai em ``nao``."""
    return [[sim if registro[campo] else nao, registro['qtd']] for registro in contagem]


def _dados_sim_nao(registros: QuerySet, campo: str, sim: str, nao: str) -> list:
    return _rotular_sim_nao(_contagem(registros, campo), campo, sim, nao)


def _dados_por_nome(registros: QuerySet, campo: str) -> list:
    return [[registro[campo], registro['qtd']] for registro in _contagem(registros, campo)]


def _dados_por_opcao(registros: QuerySet, campo: str, opcoes: Iterable[tuple]) -> list:
    """Quantidade por opção de ``choices``, na ordem das opções; nulos e opções sem ocorrência ficam de fora."""
    contagem = {registro[campo]: registro['qtd'] for registro in _contagem(registros, campo)}
    return _fatias_com_quantidade((rotulo, contagem.get(valor, 0)) for valor, rotulo in opcoes)


def _sem_zero_no_fim(dados: list) -> list:
    if dados and dados[-1][1] == 0:
        dados.pop()
    return dados


def _so_a_ficha_mais_recente(registros: QuerySet) -> QuerySet:
    """Só a versão mais recente (maior id) da ficha em cada atendimento (#17628).

    Cada salvamento das views ``adicionar_*`` grava uma ficha nova no mesmo atendimento (histórico). A mais
    recente é procurada entre todas as fichas do model, não só entre ``registros``: se a última edição saiu de
    um filtro (ex.: peso apagado na antropometria), a versão anterior não volta a contar.
    """
    mais_nova = registros.model._default_manager.filter(atendimento=OuterRef('atendimento'), id__gt=OuterRef('id'))
    return registros.filter(~Exists(mais_nova))


def _filtrar_periodo_e_campus(registros: QuerySet, dados: Mapping) -> QuerySet:
    """Filtros do formulário comuns às fichas: só a mais recente de cada atendimento, período e campus do atendimento.

    O período é o da abertura do atendimento: `data_cadastro` é `auto_now` (muda a cada edição da ficha).
    """
    registros = _so_a_ficha_mais_recente(registros)
    if dados.get('data_inicio') and dados.get('data_termino'):
        registros = registros.filter(
            atendimento__data_aberto__date__gte=dados['data_inicio'], atendimento__data_aberto__date__lte=dados['data_termino']
        )
    if dados.get('uo'):
        registros = registros.filter(atendimento__usuario_aberto__vinculo__setor__uo=dados.get('uo'))
    return registros


def _filtrar_aberturas_ate_o_fim_do_dia(atendimentos: QuerySet, inicio: datetime.date | None, fim: datetime.date | None) -> QuerySet:
    """Período por data de abertura (`data_aberto` é datetime): o último dia entra inteiro."""
    if inicio:
        atendimentos = atendimentos.filter(data_aberto__date__gte=inicio)
    if fim:
        atendimentos = atendimentos.filter(data_aberto__date__lte=fim)
    return atendimentos


def _filtrar_atendimentos_por_periodo_e_campus(atendimentos: QuerySet, dados: Mapping) -> QuerySet:
    """Filtros do formulário de estatísticas: período de abertura (só se informado por inteiro) e campus de quem abriu."""
    if dados.get('data_inicio') and dados.get('data_termino'):
        atendimentos = _filtrar_aberturas_ate_o_fim_do_dia(atendimentos, dados['data_inicio'], dados['data_termino'])
    if dados.get('uo'):
        atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=dados['uo'])
    return atendimentos


def _fatias_com_quantidade(fatias: Iterable[tuple[str, int]]) -> list[list]:
    """Dados de pizza: só as categorias com quantidade maior que zero."""
    return [[rotulo, qtd] for rotulo, qtd in fatias if qtd > 0]


def _restringir_ao_campus_do_usuario(registros: QuerySet, user: User, prefixo: str = 'atendimento__') -> QuerySet:
    """Quem não vê os gráficos de todos os campi só vê os atendimentos abertos no próprio campus."""
    if not user.has_group_cached(Especialidades.GRUPOS_VE_GRAFICOS_TODOS):
        registros = registros.filter(**{f'{prefixo}usuario_aberto__vinculo__setor__uo': get_uo(user)})
    return registros


def _graficos_acuidade_visual(registros: QuerySet) -> list[Chart]:
    olho_esquerdo = _sem_zero_no_fim([[str(r['olho_esquerdo']), r['qtd']] for r in _contagem(registros, 'olho_esquerdo')])
    olho_direito = _sem_zero_no_fim([[str(r['olho_direito']), r['qtd']] for r in _contagem(registros, 'olho_direito')])
    # `com_correcao` saiu do formulário (Demanda 2301) e tem default False: só as fichas legadas, sem `teste_com_lente`, o respondem.
    correcao = _sem_zero_no_fim(_dados_sim_nao(registros.filter(teste_com_lente__isnull=True), 'com_correcao', 'Com correção', 'Sem correção'))
    lente = _dados_sim_nao(registros.filter(teste_com_lente__isnull=False), 'teste_com_lente', 'Com lentes corretivas', 'Sem lentes corretivas')
    subtitulo = 'Classificação por Acuidade Visual'
    return [
        _grafico(PieChart, 'grafico3', 'Acuidade Visual - Com ou Sem Correção', subtitulo, correcao),
        _grafico(PieChart, 'grafico1', 'Acuidade Visual - Olho Esquerdo', subtitulo, olho_esquerdo),
        _grafico(PieChart, 'grafico2', 'Acuidade Visual - Olho Direito', subtitulo, olho_direito),
        _grafico(PieChart, 'grafico4', 'Acuidade Visual - Teste com Lentes Corretivas', subtitulo, lente),
    ]


# Faixas da OMS, contínuas: cada IMC (inclusive fracionário) cai em exatamente uma.
_FAIXAS_IMC_ADULTOS = [
    ('Excesso de magreza', {'imc__lt': 18.5}),
    ('Peso normal', {'imc__gte': 18.5, 'imc__lt': 25}),
    ('Acima do peso', {'imc__gte': 25, 'imc__lt': 30}),
    ('Obesidade grau 1', {'imc__gte': 30, 'imc__lt': 35}),
    ('Obesidade grau 2', {'imc__gte': 35, 'imc__lt': 40}),
    ('Obesidade grau 3 ou mórbida', {'imc__gte': 40}),
]


def _dados_imc_adultos(registros: QuerySet) -> list:
    return [[rotulo, registros.filter(**filtro).count()] for rotulo, filtro in _FAIXAS_IMC_ADULTOS]


def _faixa_imc_jovens(indice_z: Decimal | None) -> str | None:
    """Classificação do escore-z do IMC; sem z (None) não há faixa."""
    if indice_z is None:
        return None
    if indice_z < -3:
        return 'Magreza acentuada'
    if indice_z < -2:
        return 'Magreza'
    if indice_z < 1:
        return 'Eutrofia'
    if indice_z < 2:
        return 'Sobrepeso'
    if indice_z < 3:
        return 'Obesidade'
    return 'Obesidade grave'


def _contar_imc_jovens(registros: QuerySet) -> dict[str, int]:
    """Conta por faixa de escore-z só quem tem idade conhecida entre 10 e 19 anos."""
    contagem = dict.fromkeys(['Magreza acentuada', 'Magreza', 'Eutrofia', 'Sobrepeso', 'Obesidade', 'Obesidade grave'], 0)
    for registro in registros:
        idade = registro.atendimento.prontuario.vinculo.pessoa.pessoafisica.idade
        try:
            idade = int(idade)
        except Exception:
            continue
        faixa = _faixa_imc_jovens(registro.get_imc_jovens()) if 10 <= idade <= 19 else None
        if faixa:
            contagem[faixa] += 1
    return contagem


def _faixa_iac(iac: float, minimo_normal: float, minimo_sobrepeso: float, maximo_sobrepeso: float) -> str:
    """Faixa contínua do IAC: abaixo do normal | normal [min, min_sobrepeso) | sobrepeso [min_sobrepeso, max_sobrepeso] | obesidade."""
    if iac < minimo_normal:
        return 'Abaixo do normal'
    if iac < minimo_sobrepeso:
        return 'Normal'
    if iac <= maximo_sobrepeso:
        return 'Sobrepeso'
    return 'Obesidade'


def _contar_iac(registros: QuerySet, minimo_normal: float, minimo_sobrepeso: float, maximo_sobrepeso: float) -> dict[str, int]:
    """Conta o IAC por faixa do sexo; só quem não tem IAC (sem quadril ou estatura) fica de fora."""
    contagem = dict.fromkeys(['Abaixo do normal', 'Normal', 'Sobrepeso', 'Obesidade'], 0)
    for registro in registros:
        iac = registro.get_IAC()
        if iac is not None:
            contagem[_faixa_iac(iac, minimo_normal, minimo_sobrepeso, maximo_sobrepeso)] += 1
    return contagem


def _contar_rcq(registros: QuerySet) -> dict[str, int]:
    """Conta pela classificação entre parênteses devolvida por ``get_RCQ``."""
    contagem = {'Baixo': 0, 'Moderado': 0, 'Alto': 0, 'Muito alto': 0}
    for registro in registros:
        rcq = registro.get_RCQ()
        if rcq:
            classificacao = rcq[rcq.index('(') + 1 : rcq.index(')')]
            contagem[classificacao] = contagem[classificacao] + 1
    return contagem


def _somar_contagens(*contagens: Mapping[str, int]) -> list:
    return [[rotulo, sum(contagem[rotulo] for contagem in contagens)] for rotulo in contagens[0]]


def _graficos_antropometria(registros: QuerySet) -> list[Chart]:
    mais_19_anos = datetime.datetime.today().date() - relativedelta(years=19)
    imc_adultos = registros.filter(atendimento__aluno__pessoa_fisica__nascimento_data__lte=mais_19_anos).annotate(
        imc=ExpressionWrapper(F('peso') / ((F('estatura') / 100.0) * (F('estatura') / 100.0)), output_field=DecimalField())
    )
    jovens = registros.filter(atendimento__aluno__pessoa_fisica__nascimento_data__gte=mais_19_anos)
    imc_jovens_homens = _contar_imc_jovens(jovens.filter(atendimento__aluno__pessoa_fisica__sexo='M'))
    imc_jovens_mulheres = _contar_imc_jovens(jovens.filter(atendimento__aluno__pessoa_fisica__sexo='F'))
    homens = registros.filter(atendimento__aluno__pessoa_fisica__sexo='M')
    mulheres = registros.filter(atendimento__aluno__pessoa_fisica__sexo='F')
    iac_homens = _contar_iac(homens, minimo_normal=8, minimo_sobrepeso=21, maximo_sobrepeso=25)
    iac_mulheres = _contar_iac(mulheres, minimo_normal=21, minimo_sobrepeso=33, maximo_sobrepeso=38)
    rcq_homens = _contar_rcq(homens)
    rcq_mulheres = _contar_rcq(mulheres)
    imc = 'Índice de Massa Corporal (IMC)'
    iac = 'Índice de Adiposidade Corporal'
    rcq = 'Razão Cintura-Quadril'
    return [
        _grafico(
            PieChart,
            'grafico1',
            f'{imc} - Alunos Maiores de 19 anos - Geral',
            'Classificação do IMC para alunos maiores de 19 anos - geral',
            _dados_imc_adultos(imc_adultos),
        ),
        _grafico(
            PieChart,
            'grafico2',
            f'{imc} - Alunos Maiores de 19 anos - Homens',
            'Classificação do IMC para alunos maiores de 19 anos - Homens',
            _dados_imc_adultos(imc_adultos.filter(atendimento__aluno__pessoa_fisica__sexo='M')),
        ),
        _grafico(
            PieChart,
            'grafico3',
            f'{imc} - Alunos Maiores de 19 anos - Mulheres',
            'Classificação do IMC para alunos maiores de 19 anos - Mulheres',
            _dados_imc_adultos(imc_adultos.filter(atendimento__aluno__pessoa_fisica__sexo='F')),
        ),
        _grafico(
            PieChart,
            'grafico4',
            f'{imc} - Alunos Menores de 19 anos - Geral',
            'Classificação do IMC para alunos menores de 19 anos - geral',
            _somar_contagens(imc_jovens_homens, imc_jovens_mulheres),
        ),
        _grafico(
            PieChart,
            'grafico5',
            f'{imc} - Alunos Menores de 19 anos - Homens',
            'Classificação do IMC para alunos menores de 19 anos - Homens',
            _somar_contagens(imc_jovens_homens),
        ),
        _grafico(
            PieChart,
            'grafico6',
            f'{imc} - Alunos Menores de 19 anos - Mulheres',
            'Classificação do IMC para alunos menores de 19 anos - Mulheres',
            _somar_contagens(imc_jovens_mulheres),
        ),
        _grafico(
            PieChart,
            'grafico7',
            f'Classificação do {iac} (IAC) - Geral',
            f'Classificação do {iac} de todos os alunos',
            _somar_contagens(iac_homens, iac_mulheres),
        ),
        _grafico(PieChart, 'grafico8', f'Classificação do {iac} (IAC) - Homens', f'Classificação do {iac} - Homens', _somar_contagens(iac_homens)),
        _grafico(
            PieChart, 'grafico9', f'Classificação do {iac} (IAC) - Mulheres', f'Classificação do {iac} - Mulheres', _somar_contagens(iac_mulheres)
        ),
        _grafico(PieChart, 'grafico10', f'{rcq} (RCQ) - Geral', f'Classificação da {rcq} dos alunos', _somar_contagens(rcq_homens, rcq_mulheres)),
        _grafico(PieChart, 'grafico11', f'{rcq} (RCQ) - Homens', f'Classificação da {rcq} dos alunos - Homens', _somar_contagens(rcq_homens)),
        _grafico(PieChart, 'grafico12', f'{rcq} (RCQ) - Mulheres', f'Classificação da {rcq} dos alunos - Mulheres', _somar_contagens(rcq_mulheres)),
    ]


def _graficos_desenvolvimento_pessoal(registros: QuerySet) -> list[Chart]:
    dados = _dados_sim_nao(registros, 'problema_aprendizado', 'Tem dificuldade de aprendizado', 'Não tem dificuldade de aprendizado')
    return [_grafico(PieChart, 'grafico1', 'Dificuldade de Aprendizado', 'Classificação por Dificuldade de Aprendizado', dados)]


# (campo, título do gráfico, alteração)
_ALTERACOES_EXAME_FISICO = [
    ('ectoscopia_alterada', 'Ectoscopia', 'Alteração na Ectoscopia'),
    ('acv_alterado', 'Aparelho Cardiovascular', 'Alteração no Aparelho Cardiovascular'),
    ('ar_alterado', 'Aparelho Respiratório', 'Alteração no Aparelho Respiratório'),
    ('abdome_alterado', 'Alteração Abdominal', 'Alteração Abdominal'),
    ('mmi_alterados', 'Alteração nos Membros Inferiores', 'Alteração nos Membros Inferiores'),
    ('mms_alterados', 'Alteração nos Membros Superiores', 'Alteração nos Membros Superiores'),
]


def _graficos_exame_fisico(registros: QuerySet) -> list[Chart]:
    return [
        _grafico(
            PieChart,
            f'grafico{numero}',
            titulo,
            f'Classificação por {alteracao}',
            _dados_sim_nao(registros, campo, f'Tem {alteracao}', f'Não tem {alteracao}'),
        )
        for numero, (campo, titulo, alteracao) in enumerate(_ALTERACOES_EXAME_FISICO, 1)
    ]


_OBJETIVOS_USO_INTERNET = ['Pesquisa relacionada a estudo', 'Jogos', 'Redes Sociais', 'Trabalho', 'Outros']


def _dados_objetivo_uso_internet(registros: QuerySet) -> list:
    """Conta por ficha: cada combinação de objetivos soma a sua quantidade (``qtd``) a cada objetivo que cita."""
    contagem = dict.fromkeys(_OBJETIVOS_USO_INTERNET, 0)
    for registro in _contagem(registros, 'objetivo_uso_internet'):
        objetivos = registro['objetivo_uso_internet'] or ''
        for objetivo in _OBJETIVOS_USO_INTERNET:
            if objetivo in objetivos:
                contagem[objetivo] += registro['qtd']
    return _somar_contagens(contagem)


def _dados_tipo_droga(registros: QuerySet) -> list:
    dados = [[r['que_drogas__nome'], r['qtd']] for r in _contagem(registros, 'que_drogas__nome') if r['que_drogas__nome']]
    nao_disseram_o_tipo = registros.filter(usa_drogas=True, que_drogas__isnull=True).count()
    if nao_disseram_o_tipo:
        dados.append([NAO_INFORMADO, nao_disseram_o_tipo])
    return _sem_zero_no_fim(dados)


def _graficos_habitos_vida(registros: QuerySet) -> list[Chart]:
    nao_informado = NAO_INFORMADO
    praticantes = registros.filter(atividade_fisica=True)
    # (título, subtítulo, dados) na ordem grafico1..grafico18
    graficos = [
        (
            'Prática de Atividade Física',
            'Classificação por Prática de Atividade Física',
            _dados_sim_nao(registros, 'atividade_fisica', 'Pratica Atividade Física', 'Não Pratica Atividade Física'),
        ),
        (
            'Prática de Atividade Física - Frequencia Semanal',
            'Classificação por Frequencia Semanal',
            _rotular(
                _contagem(praticantes, 'frequencia_semanal'), 'frequencia_semanal', {2: 'Menos de 3x/semana', 3: '3 ou mais x/semana'}, nao_informado
            ),
        ),
        (
            'Prática de Atividade Física - Duração',
            'Duração da Atividade Física',
            _rotular(
                _contagem(praticantes, 'duracao_atividade'), 'duracao_atividade', {2: 'Menos de 50 min/dia', 3: '50 min ou mais/dia'}, nao_informado
            ),
        ),
        ('Fumantes', 'Classificação por Fumante', _dados_sim_nao(registros, 'fuma', 'Fumante', 'Não Fumante')),
        (
            'Etilista',
            'Classificação por Consumo de Bebida Alcoólica',
            _dados_sim_nao(registros, 'bebe', 'Consome Bebida Alcoólica', 'Não Consome Bebida Alcoólica'),
        ),
        (
            'Frequencia do Consumo de Bebida Alcoólica',
            'Classificação por Frequencia do Consumo de Bebida Alcoólica',
            _rotular(
                _contagem(registros.filter(bebe=True), 'frequencia_bebida'),
                'frequencia_bebida',
                {2: '1x/dia', 3: '1x/semana', 4: '1x/mês', 5: '1x/ano'},
                nao_informado,
            ),
        ),
        (
            'Usuário de Drogas',
            'Classificação por Uso de Drogas',
            _dados_sim_nao(registros, 'usa_drogas', 'Usuário de Drogas', 'Não é Usuário de Drogas'),
        ),
        ('Tipo de Droga Utilizada', 'Classificação por Tipo de Droga Utilizada', _dados_tipo_droga(registros)),
        (
            'Dificuldade para Dormir',
            'Classificação por Dificuldade para Dormir',
            _dados_sim_nao(registros, 'dificuldade_dormir', 'Tem dificuldade para dormir', 'Não tem dificuldade para dormir'),
        ),
        (
            'Horas de Sono por Dia',
            'Classificação por Horas de Sono por Dia',
            _rotular(_contagem(registros, 'horas_sono'), 'horas_sono', {2: 'Menos de 8 horas/dia', 3: '8 ou mais horas/dia'}, nao_informado),
        ),
        (
            'Quantidade de Refeições por Dia',
            'Classificação por Quantidade de Refeições por Dia',
            _rotular(
                _contagem(registros, 'refeicoes_por_dia'),
                'refeicoes_por_dia',
                {2: '1 refeição', 3: '2 refeições', 4: '3 refeições', 5: '4 refeições', 6: '5 refeições', 7: '6 refeições', 8: 'Mais de 6 refeições'},
                nao_informado,
            ),
        ),
        (
            'Vida Sexual Ativa',
            'Classificação por Presença de Vida Sexual Ativa',
            _dados_sim_nao(registros, 'vida_sexual_ativa', 'Tem vida sexual ativa', 'Não tem vida sexual ativa'),
        ),
        (
            'Uso de Método Contraceptivo',
            'Classificação por Uso de Método Contraceptivo',
            _dados_sim_nao(
                registros.filter(vida_sexual_ativa=True), 'metodo_contraceptivo', 'Usa método contraceptivo', 'Não usa método contraceptivo'
            ),
        ),
        (
            'Tipo de Método Contraceptivo',
            'Classificação por Tipo de Método Contraceptivo',
            _sem_zero_no_fim(_dados_por_nome(registros.filter(metodo_contraceptivo=True), 'qual_metodo_contraceptivo__nome')),
        ),
        (
            'Tempo de Uso da Internet',
            'Classificação por Tempo de Uso da Internet',
            _rotular(
                _contagem(registros, 'tempo_uso_internet'),
                'tempo_uso_internet',
                {1: 'Menos de 2 horas/dia', 2: '2 a 3 horas/dia', 3: '3 a 4 horas/dia', 4: '4 ou mais horas/dia'},
            ),
        ),
        ('Objetivo de Uso da Internet', 'Classificação por Objetivo de Uso da Internet', _dados_objetivo_uso_internet(registros)),
        # Perguntas da Demanda 2301: a escala da bebida mudou e as refeições foram para a ficha de Nutrição e Alimentação.
        (
            'Frequência de Uso de Bebida Alcoólica',
            'Classificação por Frequência de Uso de Bebida Alcoólica',
            _dados_por_opcao(registros.filter(bebe=True), 'frequencia_uso_bebida', HabitosDeVida.FrequenciaUso.choices),
        ),
        (
            'Quantidade de Refeições por Dia - Nutrição e Alimentação',
            'Classificação por Quantidade de Refeições por Dia na Ficha de Nutrição e Alimentação',
            _dados_por_opcao(
                _so_a_ficha_mais_recente(NutricaoAlimentacao.objects.filter(atendimento__in=registros.values('atendimento'))),
                'refeicoes_por_dia',
                NutricaoAlimentacao.RefeicaoDia.choices,
            ),
        ),
    ]
    return [_grafico(PieChart, f'grafico{numero}', titulo, subtitulo, dados) for numero, (titulo, subtitulo, dados) in enumerate(graficos, 1)]


def _nao_informado_se_vazio(registros: QuerySet, contagem: QuerySet, dados: list) -> list:
    """Sem nenhum valor preenchido, o gráfico mostra o total de fichas como "Não Informado"."""
    if nao_possui_dados_estatisticos(contagem):
        return [[NAO_INFORMADO, registros.count()]]
    return dados


def _rotulo_vezes(quantidade: int) -> str:
    if quantidade == 0:
        return 'Nenhuma vez'
    if quantidade == 1:
        return f'{quantidade} vez'
    return f'{quantidade} vezes'


def _dados_vezes_na_semana(registros: QuerySet, campo: str) -> list:
    contagem = _contagem(registros.filter(**{f'{campo}__gte': 0}), campo)
    return _nao_informado_se_vazio(registros, contagem, [[_rotulo_vezes(r[campo]), r['qtd']] for r in contagem])


def _dados_uso_fio_dental(registros: QuerySet) -> list:
    """Quem não usou fio dental na última semana contra quem usou uma ou mais vezes."""
    campo = 'qtd_vezes_fio_dental_ultima_semana'
    contagem = _contagem(registros.filter(**{f'{campo}__gte': 0}), campo)
    if nao_possui_dados_estatisticos(contagem):
        return [['Nenhuma Vez', 0], ['Uma ou Mais Vezes', 0]]
    nenhuma_vez = sum(r['qtd'] for r in contagem if r[campo] == 0)
    return [['Nenhuma Vez', nenhuma_vez], ['Uma ou Mais Vezes', sum(r['qtd'] for r in contagem) - nenhuma_vez]]


# (sufixo do campo, preposição do título do grau, ação)
_DIFICULDADES_BUCAIS = [
    ('sorrir', 'para', 'Sorrir'),
    ('falar', 'para', 'Falar'),
    ('comer', 'para', 'Comer'),
    ('relacionar', 'para', 'se Relacionar'),
    ('manter_humor', 'para', 'Manter o Humor'),
    ('estudar', 'para', 'Estudar'),
    ('trabalhar', 'em', 'Trabalhar'),
    ('higienizar', 'em', 'Higienizar a Boca'),
    ('dormir', 'para', 'Dormir'),
]


def _graficos_dificuldade_bucal(registros: QuerySet, sufixo: str, preposicao: str, acao: str, numero: int) -> tuple[list[Chart], int | None]:
    """Gráficos de grau e de motivo de uma dificuldade, mais o total do grau para o quadro geral."""
    campo_grau = f'grau_dificuldade_{sufixo}'
    grau = _contagem(registros, campo_grau)
    total = grau.aggregate(total=Sum('qtd'))['total']
    campo_motivo = f'motivo_dificuldade_{sufixo}__dificuldade'
    motivo = _contagem(registros.filter(**{f'motivo_dificuldade_{sufixo}__isnull': False}), campo_motivo)
    titulo_grau = f'Grau de Dificuldade {preposicao} {acao}'
    titulo_motivo = f'Motivo de Dificuldade para {acao}'
    dados_grau = _nao_informado_se_vazio(registros, grau, _rotular(grau, campo_grau, {1: 'Alto', 2: 'Médio', 3: 'Baixo'}))
    dados_motivo = _nao_informado_se_vazio(registros, motivo, [[r[campo_motivo], r['qtd']] for r in motivo])
    graficos = [
        _grafico(BarChart, f'grafico{numero}', titulo_grau, f'Classificação por {titulo_grau}', dados_grau),
        _grafico(BarChart, f'grafico{numero + 1}', titulo_motivo, f'Classificação por {titulo_motivo}', dados_motivo),
    ]
    return graficos, total


def _dados_motivos_dificuldade(registros: QuerySet) -> list:
    """Total de cada motivo somando todas as dificuldades; motivos sem ocorrência ficam de fora.

    Estudar e trabalhar viraram uma pergunta só na Demanda 2301. Os motivos separados só contam nas fichas legadas
    (sem `usa_fio_dental`, obrigatório no formulário atual): a ficha nova é copiada da anterior e pode carregá-los.
    """
    legadas = registros.filter(usa_fio_dental__isnull=True)
    campos = [
        (registros, f'motivo_dificuldade_{sufixo}') for sufixo, _preposicao, _acao in _DIFICULDADES_BUCAIS if sufixo not in ('estudar', 'trabalhar')
    ]
    campos += [
        (legadas, 'motivo_dificuldade_estudar'),
        (legadas, 'motivo_dificuldade_trabalhar'),
        (registros, 'motivo_dificuldade_estudar_trabalhar'),
    ]
    dados = []
    for dificuldade in DificuldadeOral.objects.all():
        valor = sum(fichas.filter(**{campo: dificuldade}).count() for fichas, campo in campos)
        if valor:
            dados.append([dificuldade.dificuldade, valor])
    return dados


def _rotulo_dias(quantidade: int) -> str:
    return '1 dia' if quantidade == 1 else f'{quantidade} dias'


def _dados_dias_fio_dental(registros: QuerySet) -> list:
    """Quem não usa fio dental e, de quem usa, em quantos dos últimos 7 dias usou (pergunta da Demanda 2301)."""
    campo = 'qts_dias_fio_dental_ultima_semana'
    dias = _contagem(registros.filter(usa_fio_dental=True, **{f'{campo}__isnull': False}), campo)
    nao_usa = registros.filter(usa_fio_dental=False).count()
    return _fatias_com_quantidade([('Não usa', nao_usa), *((_rotulo_dias(registro[campo]), registro['qtd']) for registro in dias)])


def _graficos_percepcao_saude_bucal(registros: QuerySet) -> list[Chart]:
    foi_ao_dentista = _contagem(registros, 'foi_dentista_anteriormente')
    ultima_ida = _contagem(registros, 'tempo_ultima_vez_dentista')
    dificuldades = _contagem(registros, 'dificuldades')
    graficos_dificuldades = []
    totais_dificuldades = []
    for indice, (sufixo, preposicao, acao) in enumerate(_DIFICULDADES_BUCAIS):
        graficos, total = _graficos_dificuldade_bucal(registros, sufixo, preposicao, acao, numero=6 + 2 * indice)
        graficos_dificuldades += graficos
        totais_dificuldades.append([f'Dificuldade em {acao}', total])
    ultima_ida_rotulos = {1: 'Menos de 1 mês', 2: 'Entre 1 e 6 meses', 3: 'Entre 6 e 12 meses', 4: 'Entre 1 a 2 anos', 5: 'Mais de 2 anos'}
    return [
        _grafico(
            BarChart,
            'grafico1',
            'Ida Anterior ao Dentista',
            'Classificação por Ida Anterior ao Dentista',
            _nao_informado_se_vazio(
                registros,
                foi_ao_dentista,
                _rotular_sim_nao(foi_ao_dentista, 'foi_dentista_anteriormente', 'Foi ao Dentista Anteriormente', 'Não foi ao Dentista Anteriormente'),
            ),
        ),
        _grafico(
            BarChart,
            'grafico2',
            'Última Ida ao Dentista',
            'Classificação por Última Ida ao Dentista',
            _nao_informado_se_vazio(registros, ultima_ida, _rotular(ultima_ida, 'tempo_ultima_vez_dentista', ultima_ida_rotulos)),
        ),
        _grafico(
            PieChart,
            'grafico25',
            'Uso do Fio Dentral',
            'Classificação por quem nunca usou e quem usou na ultima semana',
            _dados_uso_fio_dental(registros),
        ),
        _grafico(
            BarChart,
            'grafico3',
            'Uso do Fio Dental na Última Semana',
            'Classificação por Uso do Fio Dental na Última Semana',
            _dados_vezes_na_semana(registros, 'qtd_vezes_fio_dental_ultima_semana'),
        ),
        _grafico(
            BarChart,
            'grafico4',
            'Consumo de Doces, Balas e Refrigerantes na Última Semana',
            'Classificação por Consumo de Doces, Balas e Refrigerantes na Última Semana',
            _dados_vezes_na_semana(registros, 'qtd_dias_consumiu_doce_ultima_semana'),
        ),
        _grafico(
            BarChart,
            'grafico5',
            'Dificuldade Relacionada à Boca',
            'Classificação por Dificuldade Relacionada à Boca',
            _nao_informado_se_vazio(
                registros, dificuldades, _rotular_sim_nao(dificuldades, 'dificuldades', 'Tem Dificuldade', 'Não Tem Dificuldade')
            ),
        ),
        _grafico(BarChart, 'grafico24', 'Quantitativos Totais - Dificuldades', 'Valor total para cada dificuldade', totais_dificuldades),
        _grafico(
            BarChart,
            'grafico26',
            'Quantitativos Totais - Motivos da Dificuldade',
            'Valor total para cada motivo de dificulddade',
            _dados_motivos_dificuldade(registros),
        ),
        *graficos_dificuldades,
        # Perguntas da Demanda 2301, que substituem as dos gráficos 3, 4, 17, 19 e 25 nas fichas novas.
        _grafico(
            BarChart,
            'grafico27',
            'Dias de Uso do Fio Dental nos Últimos 7 Dias',
            'Classificação por Dias de Uso do Fio Dental nos Últimos 7 Dias',
            _dados_dias_fio_dental(registros),
        ),
        _grafico(
            BarChart,
            'grafico28',
            'Consumo de Alimentos ou Bebidas com Açúcar por Dia',
            'Classificação por Vezes por Dia que Consome Alimentos ou Bebidas com Açúcar',
            _dados_por_opcao(registros, 'qtd_por_dia_consome_acucar', PercepcaoSaudeBucal.FrequenciaDoces.choices),
        ),
        _grafico(
            BarChart,
            'grafico29',
            'Motivo de Dificuldade para Estudar ou Trabalhar',
            'Classificação por Motivo de Dificuldade para Estudar ou Trabalhar',
            _dados_por_nome(
                registros.filter(motivo_dificuldade_estudar_trabalhar__isnull=False), 'motivo_dificuldade_estudar_trabalhar__dificuldade'
            ),
        ),
    ]


def _graficos_saude_doenca(registros: QuerySet) -> list[Chart]:
    doencas = _sem_zero_no_fim(_dados_por_nome(registros, 'doencas_cronicas__nome'))
    auditivo = _sem_zero_no_fim(_dados_sim_nao(registros, 'problema_auditivo', 'Possui Problema Auditivo', 'Não Possui Problema Auditivo'))
    alunas = registros.filter(atendimento__aluno__pessoa_fisica__sexo='F')
    gestantes = _sem_zero_no_fim(_dados_sim_nao(alunas, 'gestante', 'Gestante', 'Não é gestante'))
    return [
        _grafico(BarChart, 'grafico1', 'Doenças Crônicas', 'Classificação por Doença Crônica', doencas),
        _grafico(PieChart, 'grafico2', 'Problema Auditivo', 'Classificação por Problema Auditivo', auditivo),
        _grafico(PieChart, 'grafico3', 'Alunas Gestantes', 'Quantidade de Alunas Gestantes', gestantes),
    ]


def _relatorio_fichas(registros: QuerySet, request: HttpRequest, exportar: Callable, montar_graficos: Callable) -> dict | HttpResponse:
    """Exporta para XLS ou devolve as fichas e, havendo alguma, os gráficos."""
    if 'xls' in request.GET:
        return exportar(registros)
    contexto = {'registros': registros}
    if registros.exists():
        contexto['pie_chart_lists'] = _graficos_com_dado(montar_graficos(registros))
    return contexto


def _relatorio_antropometria(dados: Mapping, request: HttpRequest) -> dict | HttpResponse:
    registros = _filtrar_periodo_e_campus(Antropometria.objects.filter(atendimento__aluno__isnull=False, estatura__gt=0, peso__gt=0), dados)
    registros = _restringir_ao_campus_do_usuario(registros, request.user)
    contexto = {'registros': registros}
    # Diferente das outras fichas, a antropometria só exporta quando há registros.
    if registros.exists():
        if 'xls' in request.GET:
            return tasks.graficos_antropometria_to_xls(registros)
        contexto['pie_chart_lists'] = _graficos_com_dado(_graficos_antropometria(registros))
    return contexto


_FILTRO_VINCULO_ATENDIMENTO = {
    Vinculo.ALUNO: {'atendimento__aluno__isnull': False},
    Vinculo.SERVIDOR: {'atendimento__servidor__isnull': False},
    Vinculo.PRESTADOR_SERVICO: {'atendimento__prestador_servico__isnull': False},
    Vinculo.COMUNIDADE_EXTERNA: {
        'atendimento__servidor__isnull': True,
        'atendimento__prestador_servico__isnull': True,
        'atendimento__aluno__isnull': True,
    },
}


def _relatorio_saude_doenca(dados: Mapping, request: HttpRequest) -> dict | HttpResponse:
    """Fichas de saúde-doença do relatório de avaliação e da tela de gráficos; vínculo vazio = todos."""
    registros = _filtrar_periodo_e_campus(ProcessoSaudeDoenca.objects.order_by('-id'), dados)
    if dados.get('vinculo') not in (None, ''):
        registros = registros.filter(**_FILTRO_VINCULO_ATENDIMENTO.get(int(dados['vinculo']), {}))
    registros = _restringir_ao_campus_do_usuario(registros, request.user)
    contexto = _relatorio_fichas(registros, request, tasks.graficos_saude_doenca_to_xls, _graficos_saude_doenca)
    if isinstance(contexto, dict) and 'pie_chart_lists' in contexto:
        # Ordenar por agregado: order_by direto no M2M desdobra a ficha por doença no GROUP BY.
        contexto['lista_alunos_doenca'] = (
            registros.annotate(qtd_doenca_cronica=Count('doencas_cronicas'), primeira_doenca=Min('doencas_cronicas__nome'))
            .filter(qtd_doenca_cronica__gt=0)
            .order_by('primeira_doenca', '-id')
        )
    return contexto


def _relatorio_odontograma(dados: Mapping, request: HttpRequest) -> dict | HttpResponse:
    atendimentos = Atendimento.objects.filter(tipo=TipoAtendimento.ODONTOLOGICO, aluno__isnull=False).exclude(situacao=SituacaoAtendimento.CANCELADO)
    inicio, fim = dados.get('data_inicio'), dados.get('data_termino')
    if inicio and fim:
        atendimentos = atendimentos.filter(
            data_aberto__gte=datetime.datetime(inicio.year, inicio.month, inicio.day, 0, 0, 0),
            data_aberto__lte=datetime.datetime(fim.year, fim.month, fim.day, 23, 59, 59),
        )
    if dados.get('uo'):
        atendimentos = atendimentos.filter(usuario_aberto__vinculo__setor__uo=dados.get('uo'))
    atendimentos = _restringir_ao_campus_do_usuario(atendimentos, request.user, prefixo='')
    if 'xls' in request.GET:
        return tasks.relatorios_atendimentos_odontologicos_to_xls(atendimentos)
    contexto = {'atendimentos': atendimentos}
    if atendimentos.exists():
        contexto.update(pie_chart_lists=[], registros=atendimentos)
    return contexto


# tipo do relatório: (fichas, tarefa de exportação em `saude.tasks`, montagem dos gráficos)
_RELATORIOS_FICHAS = {
    '1': (AcuidadeVisual.objects.all, 'exportar_graficos_acuidade_visual_to_xls', _graficos_acuidade_visual),
    '3': (DesenvolvimentoPessoal.objects.all, 'graficos_desenvolvimento_pessoal_to_xls', _graficos_desenvolvimento_pessoal),
    '4': (ExameFisico.objects.all, 'graficos_exame_fisico_to_xls', _graficos_exame_fisico),
    '5': (lambda: HabitosDeVida.objects.order_by('-id'), 'graficos_habitos_vida_to_xls', _graficos_habitos_vida),
    '6': (PercepcaoSaudeBucal.objects.all, 'graficos_percepcao_saude_bucal_to_xls', _graficos_percepcao_saude_bucal),
}

_RELATORIOS_ESPECIAIS = {'2': _relatorio_antropometria, '7': _relatorio_saude_doenca, '8': _relatorio_odontograma}


def _montar_relatorio_avaliacao(dados: Mapping, request: HttpRequest) -> dict | HttpResponse:
    tipo = dados.get('tipo_relatorio')
    if tipo in _RELATORIOS_FICHAS:
        fichas, tarefa, montar_graficos = _RELATORIOS_FICHAS[tipo]
        registros = _restringir_ao_campus_do_usuario(_filtrar_periodo_e_campus(fichas(), dados), request.user)
        return _relatorio_fichas(registros, request, getattr(tasks, tarefa), montar_graficos)
    if tipo in _RELATORIOS_ESPECIAIS:
        return _RELATORIOS_ESPECIAIS[tipo](dados, request)
    return {}


@rtr()
@permission_required('saude.view_atividadegrupo')
def relatorio_avaliacao_biomedica(request: HttpRequest) -> dict | HttpResponse:
    title = 'Relatório - Avaliação de Saúde'
    form = RelatorioAvaliacaoBiomedicaForm(request.GET or None, request=request)
    contexto = {}
    if form.is_valid():
        contexto = _montar_relatorio_avaliacao(form.cleaned_data, request)
        if isinstance(contexto, HttpResponse):
            return contexto
    return {'title': title, 'form': form, **contexto}


@rtr()
@group_required(['Médico', 'Enfermeiro', 'Técnico em Enfermagem', 'Auxiliar de Enfermagem', 'Nutricionista'])
@permission_required('rh.eh_servidor')
def adicionar_nutricao_alimentacao(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Nutrição e Alimentação - {atendimento.get_vinculo()}'
    nutricao = NutricaoAlimentacao.objects.filter(atendimento=atendimento.pk)

    if nutricao.exists():
        nutricao = nutricao.latest('id')
        nutricao.id = None
    else:
        nutricao = NutricaoAlimentacao()
        nutricao.sentimento_relacao_corpo = None
        nutricao.periodo_sem_comida = None

    nutricao.profissional = request.user
    nutricao.data_cadastro = datetime.datetime.now()
    nutricao.atendimento = atendimento

    form = NutricaoAlimentacaoForm(request.POST or None, instance=nutricao, request=request)
    if form.is_valid():
        form.save()
        if atendimento.is_atendimento_avaliacao_biomedica():
            return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_nutricao', 'Nutrição e alimentação registrada com sucesso.')
        else:
            return httprr(f'/saude/atendimento_nutricional/{atendimento.id}/?tab=aba_nutricao', 'Nutrição e alimentação registrada com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def adicionar_encaminhamento(request, prontuario_id):
    prontuario = get_object_or_404(Prontuario, pk=prontuario_id)
    title = f'Cadastrar Encaminhamento - {prontuario.vinculo}'

    obj = EncaminhamentoPaciente()
    obj.cadastrado_por = request.user.get_vinculo()
    obj.prontuario = prontuario

    form = EncaminhamentoPacienteForm(request.POST or None, request=request, instance=obj)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_encaminhamentos', 'Encaminhamento registrado com sucesso.')

    return locals()


@rtr()
@group_required(Especialidades.GRUPOS)
def finalizar_encaminhamento(request, encaminhamento_id):
    encaminhamento = get_object_or_404(EncaminhamentoPaciente, pk=encaminhamento_id)
    prontuario = encaminhamento.prontuario
    title = f'Finalizar Encaminhamento - {prontuario.vinculo}'
    form = FinalizarEncaminhamentoPacienteForm(request.POST or None, request=request, instance=encaminhamento)
    if form.is_valid():
        o = form.save(False)
        o.atendido_em = datetime.datetime.now()
        o.atendido_por = request.user.get_vinculo()
        o.save()
        return httprr(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_encaminhamentos', 'Encaminhamento finalizado com sucesso.')

    return locals()


@rtr()
@group_required(
    [
        'Médico',
        'Odontólogo',
        'Enfermeiro',
        'Técnico em Enfermagem',
        'Auxiliar de Enfermagem',
        'Fisioterapeuta',
        'Nutricionista',
        'Técnico em Saúde Bucal',
        'Psicólogo',
    ]
)
@permission_required('rh.eh_servidor')
def adicionar_saudemental(request, atendimento_id):
    atendimento = get_object_or_404(Atendimento, pk=atendimento_id)
    title = f'Adicionar Saúde Mental - {atendimento.get_vinculo()}'
    saudemental = SaudeMental.objects.filter(atendimento=atendimento.pk)

    if saudemental.exists():
        saudemental = saudemental.latest('id')
        saudemental.id = None
    else:
        saudemental = SaudeMental()

    saudemental.profissional = request.user
    saudemental.data_cadastro = datetime.datetime.now()
    saudemental.atendimento = atendimento
    form = SaudeMentalForm(request.POST or None, instance=saudemental, request=request)

    if form.is_valid():
        form.save()
        return httprr(f'/saude/avaliacao_biomedica/{atendimento.id}/?tab=aba_saudemental', 'Saúde mental registrada com sucesso.')

    return locals()


@permission_required('rh.eh_servidor')
def confirmar_leitura_anotacao(request, anotacao_id):
    vinculo_logado = request.user.get_vinculo()
    if vinculo_logado:
        anotacao = get_object_or_404(AnotacaoInterdisciplinar, pk=anotacao_id)
        InteressadoAnotacaoInterdisciplinar.objects.filter(anotacao_interdisciplinar=anotacao, interessado=vinculo_logado, lido_em=None).update(
            lido_em=datetime.datetime.now()
        )
        return httprr(
            request.META.get('HTTP_REFERER', '.'),
            'Confirmação de leitura realizada com sucesso.',
        )
    else:
        raise PermissionDenied


@rtr()
@permission_required('rh.eh_servidor')
def anotacoes_pendentes(request):
    title = 'Anotações interdisciplinares pendentes de confirmação de leitura'
    pode_ver_prontuarios = request.user.has_group_cached(Especialidades.GRUPOS_PRONTUARIO)
    pode_adicionar_anotacao = request.user.has_group_cached([*Especialidades.GRUPOS, 'Assistente Social'])
    anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(
        id__in=InteressadoAnotacaoInterdisciplinar.objects.filter(lido_em=None, interessado=request.user.get_vinculo()).values_list(
            'anotacao_interdisciplinar', flat=True
        )
    ).order_by('-data')
    exibe_coluna_aluno = True
    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def acompanhamento_anotacoes_interdisciplinares(request):
    title = 'Acompanhamento das anotações interdisciplinares'
    pode_ver_prontuarios = request.user.has_group_cached(Especialidades.GRUPOS_PRONTUARIO)
    pode_adicionar_anotacao = request.user.has_group_cached([*Especialidades.GRUPOS, 'Assistente Social'])
    exibe_coluna_aluno = True
    form = AcompanhamentoAnotacoesInterdisciplinaresForm(request.GET or None)
    if form.is_valid():
        vinculo = form.cleaned_data.get('vinculo')
        situacao = form.cleaned_data.get('situacao')
        matricula = form.cleaned_data.get('matricula')
        if vinculo:
            if vinculo == AcompanhamentoAnotacoesInterdisciplinaresForm.POR_MIM:
                anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(profissional=request.user.get_relacionamento()).order_by('-data')
            else:
                anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(
                    id__in=InteressadoAnotacaoInterdisciplinar.objects.filter(interessado=request.user.get_vinculo()).values_list(
                        'anotacao_interdisciplinar', flat=True
                    )
                ).order_by('-data')
        else:
            anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(
                Q(
                    id__in=InteressadoAnotacaoInterdisciplinar.objects.filter(interessado=request.user.get_vinculo()).values_list(
                        'anotacao_interdisciplinar', flat=True
                    )
                )
                | Q(profissional=request.user.get_relacionamento())
            ).order_by('-data')
        if situacao:
            if situacao == AcompanhamentoAnotacoesInterdisciplinaresForm.PENDENTE_CIENCIA:
                anotacoes_disciplinares = anotacoes_disciplinares.filter(
                    id__in=InteressadoAnotacaoInterdisciplinar.objects.filter(lido_em=None).values_list('anotacao_interdisciplinar', flat=True)
                )
            else:
                anotacoes_disciplinares = anotacoes_disciplinares.exclude(
                    id__in=InteressadoAnotacaoInterdisciplinar.objects.filter(lido_em=None).values_list('anotacao_interdisciplinar', flat=True)
                )

        if matricula:
            aluno = Aluno.objects.filter(matricula=matricula).last()
            if aluno:
                anotacoes_disciplinares = anotacoes_disciplinares.filter(prontuario__vinculo=aluno.get_vinculo())
            else:
                anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.none()
    return locals()
