import datetime
import math
from collections import defaultdict
from collections.abc import Iterable
from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.dispatch import receiver
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, reverse

from comum.models import Ano, Configuracao, User, Vinculo
from djtools.templatetags.filters import format_datetime
from djtools.utils import (
    documento,
    group_required,
    httprr,
    permission_required,
    render_to_string,
    rtr,
)
from edu import tasks
from edu.forms import (
    AtualizarFotoProfessorForm,
    ConfiguracaoDadosDocentesForm,
    DisciplinaIngressoProfessorForm,
    ExportarDadosPNP,
    InformarDadosTitulacaoForm,
    ParticipacaoBancaForm,
    ProfessorExternoForm,
    RelatorioProfessorForm,
)
from edu.models import Aluno, CursoCampus, Diario, HistoricoRelatorio, ParticipanteEvento, PeriodoLetivoAtual, Professor, ProjetoFinal
from edu.models.diarios import Aula, ProfessorDiario
from edu.models.professores import ConfiguracaoDadosDocentes
from edu.perms import pode_ver_endereco_professores
from rh.models import Funcao
from rh.views import rh_servidor_view_tab


@permission_required('edu.add_professordiario')
@rtr()
def cadastrar_professor_nao_servidor(request):
    title = 'Adicionar Professor Prestador de Serviço'
    form = ProfessorExternoForm(data=request.POST or None, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Professor cadastrado com sucesso.')
    return locals()


def _eh_gestao_academica_do_campus(user: User, vinculo: Vinculo) -> bool:
    """Papel sistêmico, ou Diretor Acadêmico/Diretor Geral/Secretário Acadêmico do campus do setor do vínculo."""
    if user.has_group_cached('Administrador Acadêmico, Diretor de Avaliação e Regulação do Ensino'):
        return True
    vinculo_usuario = user.get_vinculo()
    usuario_uo = vinculo_usuario and vinculo_usuario.setor and vinculo_usuario.setor.uo
    professor_uo = vinculo.setor and vinculo.setor.uo
    return bool(usuario_uo and usuario_uo == professor_uo and user.has_group_cached('Diretor Acadêmico, Diretor Geral, Secretário Acadêmico'))


def pode_ver_dados_pessoais_professor(user: User, professor: Professor) -> bool:
    """Se ``user`` vê CPF, RG, endereço etc. na tela do professor.

    Servidor: a gestão acadêmica do campus, desde que o servidor atue como docente (é da carreira
    docente ou tem diário). Prestador: a gestão acadêmica do campus do setor e o próprio prestador;
    sem setor, só os papéis sistêmicos e o próprio.
    """
    vinculo = professor.vinculo
    if vinculo.eh_servidor():
        atua_como_docente = vinculo.relacionamento.eh_docente or professor.professordiario_set.exists()
        return atua_como_docente and _eh_gestao_academica_do_campus(user, vinculo)
    return user == vinculo.user or _eh_gestao_academica_do_campus(user, vinculo)


@rtr()
@login_required()
def professor(request, pk=None):
    if pk:
        obj = get_object_or_404(Professor, pk=pk)
    else:
        obj = get_object_or_404(Professor, vinculo__user=request.user)
    vinculo = obj.vinculo
    verificacao_propria = request.user == vinculo.user
    pode_ver_dados_professor = request.user.has_perm('edu.view_professor')

    if not (pode_ver_dados_professor or verificacao_propria):
        return httprr('..', 'Você não tem permissão para ver os dados deste professor.')
    professor_eh_servidor = vinculo.eh_servidor()
    professor_eh_docente = professor_eh_servidor and vinculo.relacionamento.eh_docente
    eh_proprio_professor = request.user == vinculo.user
    pode_ver_dados_pessoais = pode_ver_dados_pessoais_professor(request.user, obj)

    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, obj)
    title = f'Professor(a): {obj.get_nome()} ({obj.get_matricula()})'

    projetos_finais = ProjetoFinal.objects.filter(orientador=obj)
    projetos_finais_coorientador = ProjetoFinal.objects.filter(coorientadores_vinculos__id=obj.vinculo.id)

    orientacoes_pos = Aluno.objects.filter(orientador=obj)
    coorientacoes_pos = vinculo.alunos_coorientados.all()

    ano_letivo = None
    periodo_letivo = None
    tipo = ''
    data_inicio = None
    data_fim = None
    ordenar_por = 'resultado_data'
    tipo_ordenacao = ''
    participacao_banca_form = ParticipacaoBancaForm(data=request.POST or None)
    if participacao_banca_form.is_valid():
        ano_letivo = participacao_banca_form.cleaned_data.get('ano_letivo')
        if ano_letivo:
            ano_letivo = ano_letivo.ano
        periodo_letivo = participacao_banca_form.cleaned_data.get('periodo_letivo')
        tipo = participacao_banca_form.cleaned_data.get('tipo')
        data_inicio = participacao_banca_form.cleaned_data.get('data_inicio')
        data_fim = participacao_banca_form.cleaned_data.get('data_fim')
        ordenar_por = participacao_banca_form.cleaned_data.get('ordenar_por', ordenar_por)
        tipo_ordenacao = participacao_banca_form.cleaned_data.get('tipo_ordenacao', tipo_ordenacao)

    bancas_presidente, bancas_examinador = obj.get_participacoes_em_bancas(
        ano_letivo, periodo_letivo, tipo, data_inicio, data_fim, ordenar_por, tipo_ordenacao
    )
    qtd_bancas_presidente = len(bancas_presidente)
    qtd_bancas_examinador = len(bancas_examinador)

    qtd_estagios = (
        obj.praticaprofissional_set.count()
        + obj.estagiodocente_orientador_set.count()
        + obj.aprendizagem_set.count()
        + obj.atividadeprofissionalefetiva_set.count()
    )

    app_pit_rit_instalada = 'pit_rit' in settings.INSTALLED_APPS or 'pit_rit_v2' in settings.INSTALLED_APPS or 'pit_rit_v3' in settings.INSTALLED_APPS
    exibir_diarios = not request.GET.get('tab') and not pode_ver_dados_pessoais

    if request.GET.get('tab') in ['planoatividades', 'disciplinas'] or exibir_diarios:
        vinculos_turmas_minicurso = obj.get_vinculos_minicurso(periodo_letivo_atual.ano, periodo_letivo_atual.periodo)
        diarios_especiais = obj.get_vinculos_diarios_especiais(periodo_letivo_atual.ano, periodo_letivo_atual.periodo)

    if request.GET.get('tab') == 'disciplinas' or exibir_diarios:
        vinculos_diarios_regulares = obj.get_vinculo_diarios(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, False)
        vinculos_diarios_fics = obj.get_vinculo_diarios(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, True)

    if request.GET.get('tab') == 'planoatividades':
        pit = None
        versao_pit = None
        vinculos_diarios = obj.get_vinculo_diarios(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, None, True, False)
        vinculos_diarios_regulares = obj.get_vinculo_diarios(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, False, True, False)
        vinculos_diarios_fics = obj.get_vinculo_diarios(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, True, True, False)
        ano_letivo = Ano.objects.get(ano=periodo_letivo_atual.ano)
        ano_corrente = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or datetime.date.today().year)
        periodo_corrente = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)

        if 'pit_rit_v3' in settings.INSTALLED_APPS:
            from pit_rit_v3.models import PlanoIndividualTrabalhoV3

            if PlanoIndividualTrabalhoV3.modulo_ativo(periodo_letivo_atual.ano, periodo_letivo_atual.periodo):
                versao_pit = 3
        if versao_pit is None and 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            if periodo_letivo_atual.ano >= PlanoIndividualTrabalhoV2.ANO_INICIO_APP:
                versao_pit = 2

        if versao_pit is None and 'pit_rit' in settings.INSTALLED_APPS:
            from pit_rit.models import ConfiguracaoAtividadeDocente, PlanoIndividualTrabalho

            versao_pit = 1

        if versao_pit == 1:
            pit = PlanoIndividualTrabalho.objects.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo, professor=obj).first()
            if not pit and eh_proprio_professor:
                configuracoes_ativas = ConfiguracaoAtividadeDocente.objects.filter(
                    ano_letivo_inicio=ano_letivo, periodo_letivo_inicio=periodo_letivo_atual.periodo
                )
                if configuracoes_ativas.exists():
                    pit = PlanoIndividualTrabalho.objects.create(
                        ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo, professor=obj, configuracao=configuracoes_ativas[0]
                    )
        if versao_pit == 2:
            qs_relatorios = PlanoIndividualTrabalhoV2.objects.filter(
                ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo, professor=obj
            )
            if qs_relatorios.exists():
                pit = qs_relatorios.first()

        if versao_pit == 3:
            qs_relatorios = PlanoIndividualTrabalhoV3.objects.filter(
                ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo, professor=obj
            )
            if qs_relatorios.exists():
                pit = qs_relatorios.first()

        if pit and versao_pit == 1:
            pode_editar_plano_atividade = not pit.deferida

            atividades_ensino = pit.get_atividades_ensino()
            atividades_pesquisa = pit.get_atividades_pesquisa()
            atividades_extensao = pit.get_atividades_extensao()
            atividades_gestao = pit.get_atividades_gestao()
            atividades_cargo_funcao = pit.get_atividades_cargo_funcao()

            for professor_diario in vinculos_diarios:
                professor_diario.ch_qtd_creditos = professor_diario.get_qtd_creditos_efetiva(pit.periodo_letivo)

            for diario_especial in diarios_especiais:
                diario_especial.ch_qtd_creditos = math.ceil(float(diario_especial.componente.ch_qtd_creditos) / diario_especial.professores.count())

            ch_semanal_diarios = pit.get_ch_diarios()
            ch_semanal_diarios_fic = pit.get_ch_diarios(True)
            ch_semanal_minicursos = pit.get_ch_minicursos_ha()
            ch_semanal_manutencao_ensino = ch_semanal_diarios + ch_semanal_diarios_fic + ch_semanal_minicursos
            ch_semanal_atividades_ensino = pit.get_ch_semanal_atividades_ensino()
            ch_semanal_atividades_pesquisa = pit.get_ch_semanal_atividades_pesquisa()
            ch_semanal_atividades_extensao = pit.get_ch_semanal_atividades_extensao()
            ch_semanal_atividades_gestao = pit.get_ch_semanal_atividades_gestao()
            ch_semanal_atividades_cargo_funcao = pit.get_ch_semanal_atividades_cargo_funcao()
            ch_total_semanal = pit.get_ch_semanal_total()

            # Validando se o Professor está de acordo com as normas definidas na Configuração de Atividades Docentes.
            ha_semanal = pit.configuracao.ha_semanal
            ha_minima_semanal = pit.configuracao.ha_minima_semanal
            percentual_reducao = 0
            carga_horaria_servidor = None
            funcao_servidor = None

            if professor_eh_servidor:
                data_inicio = datetime.datetime.strptime(f'01/01/{periodo_letivo_atual.ano}', '%d/%m/%Y')
                data_fim = datetime.datetime.strptime(f'31/12/{periodo_letivo_atual.ano}', '%d/%m/%Y')
                servidor = obj.vinculo.relacionamento
                historico_funcoes = servidor.historico_funcao(data_inicio=data_inicio, data_fim=data_fim)

                if periodo_letivo_atual.ano < 2017 or (periodo_letivo_atual.ano == 2017 and periodo_letivo_atual.periodo == 1):
                    funcao_servidor = historico_funcoes.last().funcao_display if historico_funcoes.exists() else None
                else:
                    atividade_cargo_funcao_semestral = pit.get_atividade_cargo_funcao_semestral()
                    if atividade_cargo_funcao_semestral:
                        funcao_servidor = atividade_cargo_funcao_semestral.tipo_atividade.descricao
                carga_horaria_servidor = servidor.jornada_trabalho and servidor.jornada_trabalho.nome

            # Aplicando os redutores na Carga Horária do Docente 20Hrs
            if carga_horaria_servidor == '20 HORAS SEMANAIS':
                percentual_reducao = pit.configuracao.percentual_reducao_20h
                ha_semanal = ha_semanal - ((percentual_reducao * ha_semanal) / 100)

            # Aplicando os redutores na Carga Horária do Docente ocupante de Função
            if funcao_servidor:
                if funcao_servidor == 'CD1':
                    percentual_reducao = pit.configuracao.percentual_reducao_cd1
                elif funcao_servidor == 'CD2':
                    percentual_reducao = pit.configuracao.percentual_reducao_cd2
                elif funcao_servidor == 'CD3':
                    percentual_reducao = pit.configuracao.percentual_reducao_cd3
                elif funcao_servidor == 'CD4':
                    percentual_reducao = pit.configuracao.percentual_reducao_cd4
                elif funcao_servidor == 'FG1' or funcao_servidor == 'FCC' or funcao_servidor == 'FUC1':
                    percentual_reducao = pit.configuracao.percentual_reducao_fg1
                elif funcao_servidor == 'FG2':
                    percentual_reducao = pit.configuracao.percentual_reducao_fg2
                elif funcao_servidor == 'FG3':
                    percentual_reducao = pit.configuracao.percentual_reducao_fg3
                elif funcao_servidor == 'FG4':
                    percentual_reducao = pit.configuracao.percentual_reducao_fg4
                elif funcao_servidor == Funcao.get_sigla_funcao_apoio_a_gestao():
                    if obj.vinculo.setor.uo.eh_reitoria:
                        percentual_reducao = pit.configuracao.percentual_reducao_fa_reitoria
                    else:
                        percentual_reducao = pit.configuracao.percentual_reducao_fa_campus
            if percentual_reducao:
                ha_semanal = ha_semanal - ((percentual_reducao * ha_semanal) / 100)
                ha_minima_semanal = ha_minima_semanal - ((percentual_reducao * ha_minima_semanal) / 100)

        if versao_pit == 2:
            if not pit and eh_proprio_professor:
                qs = PlanoIndividualTrabalhoV2.objects.filter(professor=obj, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo)
                pit = qs.first()
                if pit is None:
                    if obj.requer_pit_no_periodo(periodo_letivo_atual.ano, periodo_letivo_atual.periodo):
                        pit = PlanoIndividualTrabalhoV2.objects.create(
                            professor=obj, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo
                        )

            if pit:
                if 'cancelar_submissao' in request.GET and eh_proprio_professor:
                    pit.avaliador = None
                    pit.data_envio = None
                    pit.save()
                    return httprr(
                        f'/edu/professor/{obj.pk}/?tab=planoatividades&ano-periodo={periodo_letivo_atual.ano}.{periodo_letivo_atual.periodo}',
                        'Submissão cancelada com sucesso',
                    )
                pode_editar_plano_atividade = True
                (
                    ch_semanal_aulas,
                    ch_aulas,
                    ch_semanal_diarios,
                    ch_semanal_diarios_fic,
                    ch_semanal_minicursos,
                    ch_semanal_diarios_especiais,
                    ch_preparacao_manutencao_ensino,
                    ch_apoio_ensino,
                    ch_programas_projetos_ensino,
                    ch_orientacao_alunos,
                    ch_reunioes,
                    ch_pesquisa,
                    ch_extensao,
                    ch_gestao,
                    ch_total,
                ) = pit.get_cargas_horarias()

                ch_resumo = [
                    (ch_aulas, 'AULAS'),
                    (ch_preparacao_manutencao_ensino, 'PREPARAÇÃO E MANUTENÇÃO DO ENSINO'),
                    (ch_apoio_ensino, 'APOIO AO ENSINO'),
                    (ch_programas_projetos_ensino, 'PROGRAMAS OU PROJETOS DE ENSINO'),
                    (ch_orientacao_alunos, 'ATENDIMENTO, ACOMPANHAMENTO, AVALIAÇÃO E ORIENTAÇÃO DE ALUNOS'),
                    (ch_reunioes, 'REUNIÕES PEDAGÓGICAS, DE GRUPO E AFINS'),
                    (ch_pesquisa, 'PESQUISA E INOVAÇÃO'),
                    (ch_extensao, 'EXTENSÃO'),
                    (ch_gestao, 'GESTÃO E REPRESENTAÇÃO INSTITUCIONAL'),
                ]
                pode_enviar_plano = pit.pode_enviar_plano(request.user)
                pode_alterar_avaliador_plano = pit.pode_alterar_avaliador_plano(request.user)
                pode_avaliar_plano = pit.pode_avaliar_plano(request.user)
                pode_desfazer_aprovacao_plano = pit.pode_desfazer_aprovacao_plano(request.user)

                pode_preencher_relatorio = pit.pode_preencher_relatorio(request.user)
                pode_enviar_relatorio = pit.pode_enviar_relatorio(request.user)
                pode_alterar_avaliador_relatorio = pit.pode_alterar_avaliador_relatorio(request.user)
                pode_avaliar_relatorio = pit.pode_avaliar_relatorio(request.user)
                pode_desfazer_aprovacao_relatorio = pit.pode_desfazer_aprovacao_relatorio(request.user)
                pode_desfazer_publicacao_relatorio = pit.pode_desfazer_publicacao_relatorio(request.user)

        if versao_pit == 3:
            if not pit and eh_proprio_professor:
                qs = PlanoIndividualTrabalhoV3.objects.filter(professor=obj, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo)
                pit = qs.first()
                if pit is None:
                    if obj.requer_pit_no_periodo(periodo_letivo_atual.ano, periodo_letivo_atual.periodo):
                        pit = PlanoIndividualTrabalhoV3.objects.create(
                            professor=obj, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo_atual.periodo
                        )
            if pit:
                ch_semanal_aulas, ch_aulas = pit.get_ch_aulas()
                ch_total, atividades_planejadas = pit.get_atividades_planejadas()
                is_proprio_professor = obj.vinculo == request.user.get_vinculo()
                pode_enviar_plano = pit.pode_enviar_plano(request.user)
                pode_alterar_avaliador_plano = pit.pode_alterar_avaliador_plano(request.user)
                pode_avaliar_plano = pit.pode_avaliar_plano(request.user)
                pode_desfazer_aprovacao_plano = pit.pode_desfazer_aprovacao_plano(request.user)
                ch_prevista = pit.get_ch_prevista()
                ch_pendente = max(ch_prevista - ch_total, 0)
                ch_considerada = min(ch_total, ch_prevista)

    if request.GET.get('tab') == 'estagios':
        estagios_requerem_registro_visita = not Configuracao.get_valor_por_chave('estagios', 'opcional_registro_visita')

    if request.GET.get('tab') == 'horarios':
        horarios_campus = obj.get_horarios_aula_por_horario_campus(periodo_letivo_atual.ano, periodo_letivo_atual.periodo)

    ferias_instaladas = 'ferias' in settings.INSTALLED_APPS
    if professor_eh_servidor and ferias_instaladas:
        Ferias = apps.get_model('ferias', 'Ferias')
        servidor_ferias = Ferias.objects.filter(servidor=obj.vinculo.relacionamento).order_by('ano')

    from projetos.models import Participacao as PartExtensao

    participacoes_extensao = PartExtensao.objects.filter(vinculo_pessoa=vinculo, ativo=True, projeto__aprovado=True)

    from pesquisa.models import Participacao as PartPesquisa

    participacoes_pesquisa = PartPesquisa.objects.filter(vinculo_pessoa=vinculo, ativo=True, projeto__aprovado=True)

    participacoes_eventos = ParticipanteEvento.objects.filter(participante_id=vinculo.id)

    return locals()


@documento()
@rtr('relatorio_professor_impressao_pdf.html')
@login_required()
def relatorio_professor_pdf(request, campos_exibicao):
    title = 'Listagem de Professores'
    pode_ver_endereco = pode_ver_endereco_professores(request.user)
    form = RelatorioProfessorForm(data=request.GET or None, pode_ver_endereco=pode_ver_endereco)
    campos_exibicao = campos_exibicao[0:3]
    campos_exibicao_choices = form.EXIBICAO_CHOICES
    if form.is_valid():
        professores = form.processar()
        uo = professores[0].vinculo.setor.uo
        filtros = professores.filtros
    return locals()


@rtr()
@login_required()
@permission_required('ponto.pode_ver_frequencia_propria')
def relatorio_professor(request):
    title = 'Listagem de Professores'
    pode_ver_endereco = pode_ver_endereco_professores(request.user)
    form = RelatorioProfessorForm(data=request.GET or None, pode_ver_endereco=pode_ver_endereco)
    exibir_botao_executar = HistoricoRelatorio.objects.filter(user=request.user, tipo=HistoricoRelatorio.TIPO_PROFESSOR).exists()
    if form.is_valid():
        query_string = request.META.get('QUERY_STRING', '').encode('utf-8').hex()
        professores = form.processar()
        filtros = professores.filtros
        campos_exibicao = form.cleaned_data['exibicao']
        ano_letivo = form.cleaned_data['ano_letivo']
        periodo_letivo = form.cleaned_data['periodo_letivo']

        if 'imprimir' in request.GET:
            return relatorio_professor_pdf(request, campos_exibicao)

        if 'xls' in request.GET:
            return tasks.exportar_listagem_professores_xls(request, professores, campos_exibicao, form.EXIBICAO_CHOICES, ano_letivo, periodo_letivo)
    return locals()


@permission_required('edu.change_professor')
@rtr()
def atualizar_foto_professor(request, pk):
    title = 'Atualizar foto'
    professor = Professor.objects.filter(pk=pk).first()
    if professor is None:
        return httprr('..', 'Professor não encontrado.', 'error')
    if not professor.can_change(request.user):
        return httprr('..', 'Você não tem permissão para atualizar foto.', 'error')
    if request.method == 'POST':
        form = AtualizarFotoProfessorForm(data=request.POST or None, files=request.FILES)
    else:
        form = AtualizarFotoProfessorForm()
    form.initial.update(professor=pk)
    if form.is_valid():
        return httprr('..', form.processar(request))
    return locals()


@rtr()
@group_required('Professor')
@login_required()
def locais_aula_professor(request):
    title = 'Locais e Horários de Aula'
    professor = get_object_or_404(Professor, vinculo__user__username=request.user.username)
    is_professor = True
    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, professor)
    tipo = 'professor'
    professor_diarios = professor.professordiario_set.filter(ativo=True)
    professores_diario_anual = professor_diarios.filter(
        diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, diario__ano_letivo__ano=periodo_letivo_atual.ano
    )

    # excluíndo os diários semestrais em cursos anuais
    if periodo_letivo_atual.periodo == 1:
        professores_diario_anual = professores_diario_anual.exclude(diario__segundo_semestre=True)
    else:
        professores_diario_anual = professores_diario_anual.exclude(diario__segundo_semestre=False, diario__componente_curricular__qtd_avaliacoes=2)

    professores_diario_semestral = professor_diarios.filter(
        diario__turma__curso_campus__periodicidade__in=[CursoCampus.PERIODICIDADE_SEMESTRAL, CursoCampus.PERIODICIDADE_LIVRE],
        diario__ano_letivo__ano=periodo_letivo_atual.ano,
        diario__periodo_letivo=periodo_letivo_atual.periodo,
    )
    professor_diarios = (professores_diario_anual | professores_diario_semestral).order_by('diario__turma__curso_campus')
    horarios_campus = professor.get_horarios_aula_por_horario_campus(periodo_letivo_atual.ano, periodo_letivo_atual.periodo)

    return locals()


def _texto_periodo_vinculo_docente(professor: Professor) -> str:
    """Trecho da declaração que descreve o período em que o docente ministrou as disciplinas."""
    if professor.vinculo.eh_prestador():
        return 'ministrou as disciplinas'
    relacionamento = professor.vinculo.relacionamento
    inicio = format_datetime(relacionamento.data_inicio_exercicio_no_cargo)
    if relacionamento.data_fim_servico_na_instituicao is None:
        return f'desde {inicio}, vem ministrando as disciplinas'
    return f'de {inicio} a {format_datetime(relacionamento.data_fim_servico_na_instituicao)}, ministrou as disciplinas'


def _ch_ministrada_por_professor_diario(aulas: Iterable[Aula]) -> defaultdict[int, int]:
    """Soma, por vínculo professor-diário, a quantidade das aulas que ele ministrou.

    A aula conta para o titular e para os ``outros_professor_diario`` do mesmo diário. As aulas devem
    vir com ``professor_diario`` e ``outros_professor_diario`` já carregados: nada aqui consulta o banco.
    """
    total = defaultdict(int)
    for aula in aulas:
        total[aula.professor_diario_id] += aula.quantidade
        for outro in aula.outros_professor_diario.all():
            if outro.id != aula.professor_diario_id and outro.diario_id == aula.professor_diario.diario_id:
                total[outro.id] += aula.quantidade
    return total


def _linha_diario_docente(diario: Diario, prof_diario: ProfessorDiario) -> tuple:
    """Linha da tabela da declaração para um diário regular."""
    curso = diario.turma.curso_campus
    componente = diario.componente_curricular.componente
    return (
        curso.descricao_historico,
        curso.modalidade.descricao,
        curso.diretoria.setor.sigla,
        diario.ano_letivo.ano,
        diario.get_periodo_letivo(),
        componente.get_ch_hora_relogio(),
        diario.pk,
        prof_diario.get_percentual_ch_ministrada(),
        componente.descricao_historico,
        componente.ch_qtd_creditos,
        diario.segundo_semestre,
        curso.periodicidade == CursoCampus.PERIODICIDADE_ANUAL and not diario.is_semestral_em_calendario_anual() and 'Anual' or 'Semestral',
        prof_diario.get_percentual_ch(),
    )


@login_required
@documento('Declaração de Vínculo Docente', False, validade=30, enumerar_paginas=False, modelo='edu.professor', exibe_emissor=True)
@rtr('declaracaodocencia_pdf.html')
def declaracaodocencia_pdf(request: HttpRequest, pk: int, ano: int | None = None) -> dict:
    ANO_NOVO_CALCULO_CH = 2023
    oculta_ch_ministrada = ano and ano < ANO_NOVO_CALCULO_CH
    obj = get_object_or_404(Professor, pk=pk)
    if not obj.pode_emitir_declaracao_docencia(request.user):
        raise PermissionDenied
    uo = obj.get_uo()
    hoje = datetime.date.today()
    texto_periodo_vinculo = _texto_periodo_vinculo_docente(obj)

    diarios = Diario.objects.filter(professordiario__professor_id=pk).select_related(
        'turma__curso_campus',
        'turma__curso_campus__modalidade',
        'turma__curso_campus__diretoria__setor',
        'componente_curricular__componente',
        'ano_letivo',
        'calendario_academico',
    )

    diarios_minicurso = obj.professorminicurso_set.select_related(
        'turma_minicurso__minicurso__modalidade',
        'turma_minicurso__minicurso__diretoria__setor',
        'turma_minicurso__ano_letivo',
    ).order_by('turma_minicurso__ano_letivo__ano', 'turma_minicurso__periodo_letivo', 'turma_minicurso__minicurso__descricao', 'pk')

    diarios_especiais = obj.diarioespecial_set.select_related(
        'componente',
        'diretoria__setor',
        'ano_letivo',
    ).order_by('ano_letivo__ano', 'periodo_letivo', 'componente__descricao_historico', 'pk')

    qs_professordiario = obj.professordiario_set.select_related('diario__ano_letivo', 'diario__componente_curricular__componente')

    if ano:
        diarios = diarios.filter(ano_letivo__ano=ano)
        diarios_minicurso = diarios_minicurso.filter(turma_minicurso__ano_letivo__ano=ano)
        diarios_especiais = diarios_especiais.filter(ano_letivo__ano=ano)
        qs_professordiario = qs_professordiario.filter(diario__ano_letivo__ano=ano)

    todas_aulas = (
        Aula.objects.filter(professor_diario__diario_id__in=qs_professordiario.values_list('diario_id'), data__lte=hoje)
        .select_related('professor_diario')
        .prefetch_related(Prefetch('outros_professor_diario', queryset=ProfessorDiario.objects.only('id', 'diario_id')))
    )
    ch_ministrada_por_professor_diario = _ch_ministrada_por_professor_diario(todas_aulas)

    diarios_professor_map = {}
    for prof_diario in qs_professordiario:
        if prof_diario.diario.ano_letivo.ano >= ANO_NOVO_CALCULO_CH:
            prof_diario._carga_horaria_ministrada = ch_ministrada_por_professor_diario[prof_diario.id]
        diarios_professor_map[prof_diario.diario_id] = prof_diario

    attrs_diario = (
        'turma__curso_campus__descricao_historico',
        'turma__curso_campus__modalidade__descricao',
        'turma__curso_campus__diretoria__setor__sigla',
        'ano_letivo__ano',
        'periodo_letivo',
        'componente_curricular__componente__descricao_historico',
        'pk',
    )
    # distinct: com dois vínculos do professor no mesmo diário, o join repetiria a disciplina.
    diarios = diarios.order_by(*attrs_diario).distinct()

    lists_diarios = [_linha_diario_docente(diario, diarios_professor_map[diario.id]) for diario in diarios if diario.id in diarios_professor_map]
    for diario in diarios_minicurso:
        lists_diarios.append(
            (
                'Minicursos',
                diario.turma_minicurso.minicurso.modalidade.descricao if diario.turma_minicurso.minicurso.modalidade else '',
                diario.turma_minicurso.minicurso.diretoria.setor.sigla,
                diario.turma_minicurso.ano_letivo.ano,
                diario.turma_minicurso.periodo_letivo,
                diario.carga_horaria,
                '-',
                '100',
                diario.turma_minicurso.minicurso.descricao,
                '-',
                False,
                '',
                '100',
            )
        )
    for diario in diarios_especiais:
        lists_diarios.append(
            (
                'Diários Especiais',
                '',
                diario.diretoria.setor.sigla,
                diario.ano_letivo.ano,
                diario.periodo_letivo,
                diario.componente.get_ch_hora_relogio(),
                diario.pk,
                '100',
                diario.componente.descricao_historico,
                diario.componente.ch_qtd_creditos,
                False,
                'Semestral',
                '100',
            )
        )
    return locals()


@receiver(rh_servidor_view_tab)
def servidor_view_tab_participacoes_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    participacoes_eventos = ParticipanteEvento.objects.filter(participante__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf)
    if participacoes_eventos.exists():
        return render_to_string(
            template_name='edu/templates/tabs/professor_participacoes_eventos.html',
            context={
                'lps_context': {'nome_modulo': 'edu', 'extra_dir': 'tabs'},
                'servidor': servidor,
                'participacoes_eventos': participacoes_eventos,
                'verificacao_propria': verificacao_propria,
            },
            request=request,
        )
    return False


@rtr()
@permission_required('rh.eh_rh_sistemico')
def editar_disciplina_docente(request, docente_pk):
    professor_docente = get_object_or_404(Professor, vinculo__pessoa__pk=docente_pk)
    form = DisciplinaIngressoProfessorForm(request.POST or None, instance=professor_docente)
    if form.is_valid():
        form.save()
        return httprr('..', 'Disciplina salva com sucesso.')
    return locals()


@permission_required('edu.change_registroeducacenso')
@rtr()
def exportar_dados_pnp(request):
    title = 'Exportar Dados - Plataforma Nilo Peçanha'
    form = ExportarDadosPNP(data=request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@login_required
def preencher_dados_titulacao(request):
    title = 'Dados da Titulação'
    obj = get_object_or_404(Professor.objects, vinculo=request.user.get_vinculo())
    form = InformarDadosTitulacaoForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        request.session['informacao-titulacao-pendente'] = False
        request.session.save()
        return httprr('/', 'Dados salvos com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_dados_portal(request, pk):
    title = 'Editar Dados para o Portal Institucional'
    professor = get_object_or_404(Professor, pk=pk)
    vinculo = professor.vinculo
    # Somente o próprio professor pode editar
    if not vinculo or not vinculo.user or request.user != vinculo.user:
        return httprr('..', 'Você não tem permissão para editar estes dados.', 'error')

    if not vinculo.tem_email_valido():
        return httprr('..', 'Você precisa definir um email válido para poder editar os dados do portal institucional.', 'error')

    # Recupera configuração existente ou cria uma nova
    config, _ = ConfiguracaoDadosDocentes.objects.get_or_create(professor=professor)

    form = ConfiguracaoDadosDocentesForm(
        request.POST or None,
        instance=config,
    )

    if form.is_valid():
        form.save()
        url = reverse('professor', args=(pk,))
        return httprr(url, 'Configuração salva com sucesso. O Portal Institucional será atualizado no dia seguinte.')

    return locals()
