import datetime
import math
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.models import Vinculo
from djtools import documentos, layout
from djtools.utils import documento, group_required, httprr, permission_required, render, rtr
from edu.models import CursoCampus, HorarioAula, PeriodoLetivoAtual, Professor
from pit_rit import tasks
from pit_rit.forms import AdicionarAtividadeDocenteForm, BuscaPlanoIndividualTrabalhoForm, PlanoIndividualTrabalhoForm
from pit_rit.models import AtividadeDocente, ConfiguracaoAtividadeDocente, HorarioAulaAtividadeDocente, PlanoIndividualTrabalho, TipoAtividadeDocente
from pit_rit.utils import PontoDocente
from ponto.forms import FrequenciaDocenteFormFactory
from ponto.models import Frequencia
from ponto.utils import DIA_DA_SEMANA_SEG, DIA_DA_SEMANA_SEX, is_dia_da_semana
from ponto.views import frequencia_funcionario_get_contexto_relatorio_ponto_pessoa


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    for pit in PlanoIndividualTrabalho.objects.filter(professor__vinculo__pessoa__id=request.user.get_vinculo().pessoa.id):
        data.append(
            (
                'Ensino',
                'PIT/RIT',
                'Planos Individuais de Trabalho',
                f'{pit.ano_letivo}/{pit.periodo_letivo}',
                f'/pit_rit/plano_atividade_docente_pdf/{pit.pk}/',
            )
        )
        if pit.get_percentual_preenchimento_relatorio():
            data.append(
                (
                    'Ensino',
                    'PIT/RIT',
                    'Relatórios Individuais de Trabalho',
                    f'{pit.ano_letivo}/{pit.periodo_letivo}',
                    f'/pit_rit/plano_atividade_docente_pdf/{pit.pk}/',
                )
            )


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append(
        {'categoria': 'Ensino', 'url': '/pit_rit/planos_individuais_trabalho/', 'icone': 'file', 'titulo': 'Relatórios Individuais de Trabalho'}
    )

    return servicos_anonimos


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    # ATIVIDADES DOCENTES A DEFERIR
    if request.user.has_group_cached('Diretor Acadêmico', ignore_groups_if_superuser=False):
        ids = AtividadeDocente.get_pendentes(request.user).values_list('pit_id', flat=True).distinct()
        qtd_rit_com_atividades_a_deferir = PlanoIndividualTrabalho.objects.filter(id__in=ids).count()
        if qtd_rit_com_atividades_a_deferir:
            pendencias.append(
                {
                    'titulo': f'Plano{pluralize(qtd_rit_com_atividades_a_deferir)} Individua{pluralize(qtd_rit_com_atividades_a_deferir, "l,is")} de Trabalho',
                    'subtitulo': 'a avaliar atividades',
                    'qtd': qtd_rit_com_atividades_a_deferir,
                    'url': '/admin/pit_rit/planoindividualtrabalho/?tab=tab_pendentes',
                }
            )

    return pendencias


@rtr()
def frequencia_docente(request):
    title = 'Frequências por Funcionário'

    if not request.user.has_perm('ponto.pode_ver_frequencia_propria'):
        raise PermissionDenied('Usuário não pode ver frequencia própria.')

    funcionario_logado = request.user.get_relacionamento()
    if not funcionario_logado.setor:
        raise PermissionDenied('Funcionário não está associado a nenhum setor.')

    form_class = FrequenciaDocenteFormFactory(request)
    form = form_class(request.GET or None)

    if form.is_valid():
        escopo_relatorio_ponto_pessoa = frequencia_funcionario_get_contexto_relatorio_ponto_pessoa(request, form)

        pode_ver_frequencias = escopo_relatorio_ponto_pessoa['pode_ver_frequencias']

        if not pode_ver_frequencias:
            raise PermissionDenied(
                ' '.join(
                    [
                        'Você não tem permissão para visualizar a frequência deste servidor para o período informado.',
                        *escopo_relatorio_ponto_pessoa['nao_pode_ver_frequencias_msgs'],
                    ]
                )
            )

        servidor_is_docente = escopo_relatorio_ponto_pessoa['servidor_is_docente']
        data_inicio = escopo_relatorio_ponto_pessoa['data_inicio']
        data_fim = escopo_relatorio_ponto_pessoa['data_fim']

        if not servidor_is_docente:
            form.add_error('funcionario', 'Funcionário não é docente.')
        else:
            title = escopo_relatorio_ponto_pessoa['title']
            servidor = escopo_relatorio_ponto_pessoa['servidor']

            so_semanas_inconsistentes = escopo_relatorio_ponto_pessoa['so_inconsistentes']
            if so_semanas_inconsistentes:
                # data_inicio deve ser uma segunda-feira
                while not is_dia_da_semana(data_inicio, DIA_DA_SEMANA_SEG):
                    # procura a primeira segunda-feira ANTERIOR
                    data_inicio = data_inicio - timedelta(1)

                # data_fim deve ser uma sexta-feira
                while not is_dia_da_semana(data_fim, DIA_DA_SEMANA_SEX):
                    # procura a primeira sexta-feira POSTERIOR
                    data_fim = data_fim + timedelta(1)

            relatorio = Frequencia.relatorio_ponto_pessoa(
                vinculo=servidor.get_vinculo(),
                data_ini=data_inicio,
                data_fim=data_fim,
                dias_em_que_foi_chefe_setor=escopo_relatorio_ponto_pessoa['dias_em_que_foi_chefe_setor'],
                so_frequencias_em_que_era_chefe=escopo_relatorio_ponto_pessoa['so_frequencias_em_que_era_chefe'],
                dias_em_que_estava_no_campus=escopo_relatorio_ponto_pessoa['dias_em_que_estava_no_campus'],
                so_inconsistentes=False,
                trata_compensacoes=False,
            )

            # relatório de ponto adaptado para o ponto docente
            relatorio = PontoDocente(
                servidor=servidor,
                data_inicial=data_inicio,
                data_final=data_fim,
                relatorio_de_ponto=relatorio,
                so_semanas_inconsistentes=so_semanas_inconsistentes,
            ).get_relatorio_de_ponto_adaptado()

            return render('pit_rit/templates/relatorio_frequencia_docente.html', locals())

    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def configuracaoatividadedocente(request, pk):
    obj = get_object_or_404(ConfiguracaoAtividadeDocente.objects, pk=pk)
    if 'replicar' in request.GET:
        replicado = obj.replicar()
        return httprr(
            f'/pit_rit/configuracaoatividadedocente/{replicado.pk}/',
            'Configuração replicada com sucesso. Por favor, edite as informações clicando no botão "Editar" no canto superior da tela.',
        )
    return locals()


@rtr()
@login_required()
@group_required('Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso,Secretário Acadêmico,Professor')
def adicionar_atividade_docente(request, pk, tipo=TipoAtividadeDocente.PESQUISA, atividade_pk=None):
    title = 'Adicionar Atividade'
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pk)
    atividade = atividade_pk and get_object_or_404(AtividadeDocente, pk=atividade_pk) or None
    is_proprio_professor = request.user == pit.professor.vinculo.user

    if not is_proprio_professor and not request.user.has_group_cached(
        'Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso,Secretário Acadêmico'
    ):
        raise PermissionDenied

    form = AdicionarAtividadeDocenteForm(pit, tipo, data=request.POST or None, instance=atividade, files=request.POST and request.FILES or None)
    if form.is_valid():
        form.instance.pit = pit
        form.save()
        return httprr('..', 'Atividade Docente adicionada com sucesso.')

    return locals()


@rtr()
@group_required('Administrador Acadêmico,Diretor Acadêmico,Diretor Geral,Coordenador de Curso,Secretário Acadêmico,Professor')
def deferir_todas_atividade_docente(request, pk, tipo=TipoAtividadeDocente.PESQUISA):
    obj = get_object_or_404(PlanoIndividualTrabalho, pk=pk)
    pks_atividades_docentes_deferidas = request.POST.getlist('atividades_docentes')

    obj.atividadedocente_set.filter(tipo_atividade__categoria=tipo, pk__in=pks_atividades_docentes_deferidas).update(deferida=True)
    return httprr(
        f'/edu/professor/{obj.professor.pk}/?tab=planoatividades&ano-periodo={obj.ano_letivo.ano}.{obj.periodo_letivo}',
        'Atividades deferidas com sucesso.',
    )


@group_required('Administrador Acadêmico,Diretor Acadêmico,Diretor Geral,Coordenador de Curso,Secretário Acadêmico,Professor')
def relatorio_atividade_docente_pdf(request, professor_pk):
    try:
        return plano_atividade_docente_pdf(request, professor_pk, is_relatorio=True)
    except SystemExit:
        return httprr('/', 'Ocorreu um erro ao tentar gerar o plano de atividade docente.', 'error')


@documento()
@rtr()
@group_required('Administrador Acadêmico,Diretor Acadêmico,Diretor Geral,Coordenador de Curso,Secretário Acadêmico,Professor')
def plano_atividade_docente_pdf(request, professor_pk, is_relatorio=False):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=professor_pk)
    uo = (pit.professor.vinculo.setor and pit.professor.vinculo.setor.uo) or (
        pit.professor.vinculo.relacionamento.setor_lotacao and pit.professor.vinculo.relacionamento.setor_lotacao.uo.equivalente
    )
    hoje = datetime.date.today()

    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, pit.professor)
    is_servidor = pit.professor.vinculo.eh_servidor()
    funcao_servidor = None

    if is_servidor:
        data_inicio = None
        data_fim = None

        servidor = pit.professor.vinculo.relacionamento
        historico_funcoes = servidor.historico_funcao(data_inicio=data_inicio, data_fim=data_fim)
        funcao_servidor = historico_funcoes.last().funcao_display if historico_funcoes.exists() else None
        carga_horaria_servidor = servidor.jornada_trabalho.nome

    vinculos_diarios = pit.get_vinculo_diarios()
    vinculos_diarios_regulares = pit.get_vinculo_diarios(False)
    vinculos_diarios_fics = pit.get_vinculo_diarios(True)
    vinculos_turmas_minicurso = pit.get_vinculos_minicurso()
    diarios_especiais = pit.get_vinculos_diarios_especiais()
    atividades_ensino = pit.get_atividades_ensino().filter(deferida=True)
    atividades_pesquisa = pit.get_atividades_pesquisa().filter(deferida=True)
    atividades_extensao = pit.get_atividades_extensao().filter(deferida=True)
    atividades_gestao = pit.get_atividades_gestao().filter(deferida=True)
    atividades_cargo_funcao = pit.get_atividades_cargo_funcao().filter(deferida=True)

    # Calculando as CH com base no número de professores no diário e diário especial e arredondando para cima.
    for professor_diario in vinculos_diarios:
        professor_diario.ch_qtd_creditos = professor_diario.get_qtd_creditos_efetiva(pit.periodo_letivo)
        if professor_diario.diario.turma.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            if (
                professor_diario.diario.is_semestral_em_calendario_anual()
                and professor_diario.diario.segundo_semestre is False
                and periodo_letivo_atual.periodo == 2
            ) or (
                professor_diario.diario.is_semestral_em_calendario_anual()
                and professor_diario.diario.segundo_semestre is True
                and periodo_letivo_atual.periodo == 1
            ):
                professor_diario.ch_qtd_creditos = 0

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

    return locals()


@rtr()
@login_required()
@permission_required('pit_rit.change_atividadedocente')
def relatar_atividade_docente(request, pk):
    title = 'Relatar Atividades'
    obj = get_object_or_404(PlanoIndividualTrabalho, pk=pk)
    form = PlanoIndividualTrabalhoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Relatos registrados com sucesso.')
    return locals()


@rtr()
def planos_individuais_trabalho(request):
    title = 'Relatórios Individuais de Trabalho'
    category = 'Relatórios'
    icon = 'file'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = BuscaPlanoIndividualTrabalhoForm(data=request.GET or None)
    pits = PlanoIndividualTrabalho.objects.filter(ano_letivo__ano__gte=2017, deferida=True).exclude(ano_letivo__ano=2017, periodo_letivo=1)
    pits2 = PlanoIndividualTrabalho.objects.none()
    if 'pit_rit_v2' in settings.INSTALLED_APPS:
        from pit_rit_v2.models import PlanoIndividualTrabalhoV2

        pits2 = PlanoIndividualTrabalhoV2.objects.filter(publicado=True)
    if form.is_valid():
        pits, pits2 = form.processar()
    return locals()


@rtr()
@login_required()
@group_required('Administrador Acadêmico,Diretor Geral,Diretor Acadêmico,Coordenador de Curso,Secretário Acadêmico,Professor')
def deferir_indeferir_atividade_docente(request, pk):
    obj = get_object_or_404(AtividadeDocente, pk=pk)
    acao = int(request.GET.get('acao', '0'))

    obj.deferida = bool(acao)
    obj.save()

    if obj.deferida:
        return httprr(
            '/edu/professor/{}/?tab=planoatividades&ano-periodo={}'.format(obj.pit.professor.pk, request.GET['ano-periodo']),
            'Atividade Docente deferida com sucesso.',
        )
    else:
        return httprr(
            '/edu/professor/{}/?tab=planoatividades&ano-periodo={}'.format(obj.pit.professor.pk, request.GET['ano-periodo']),
            'Atividade Docente indeferida com sucesso.',
        )


@rtr()
@login_required()
@permission_required('pit_rit.change_atividadedocente')
def definir_horario_atividade_docente(request, pk):
    obj = get_object_or_404(AtividadeDocente, pk=pk)
    if obj.pit.professor.vinculo.relacionamento.setor_lotacao:
        uo_lotacao = obj.pit.professor.vinculo.relacionamento.setor_lotacao.uo.equivalente or None
    else:
        uo_lotacao = obj.pit.professor.vinculo.setor.uo

    is_proprio_professor = request.user == obj.pit.professor.vinculo.user
    if not is_proprio_professor and not request.user.has_group_cached(
        'Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso,Secretário Acadêmico'
    ):
        raise PermissionDenied

    campus_definiu_horario = (
        uo_lotacao and HorarioAula.objects.filter(horario_campus__uo__pk=uo_lotacao.pk, horario_campus__eh_padrao=True).exists() or False
    )

    horario_aula = obj.get_horario_aulas() or ''
    if horario_aula:
        horario_aula = f'({horario_aula})'

    title = f'Definir Horário de Aula {horario_aula}'

    if request.method == 'POST':
        horarios = dict(request.POST).get('horario')
        if horarios:
            if len(horarios) != obj.ch_aula:
                return httprr('.', 'A quantidade de horários selecionados não corresponde com a Carga Horária Semanal da Atividade.', 'error')

            HorarioAulaAtividadeDocente.objects.filter(atividade_docente=obj).delete()
            for horario in horarios:
                horario_split = horario.split(';')
                horario_aula = get_object_or_404(HorarioAula, pk=horario_split[0])
                dia_semana = horario_split[1]
                HorarioAulaAtividadeDocente.objects.create(atividade_docente=obj, dia_semana=dia_semana, horario_aula=horario_aula)
        else:
            HorarioAulaAtividadeDocente.objects.filter(atividade_docente=obj).delete()
        return httprr('..', 'Horário definido com sucesso.')

    turnos = obj.get_horarios_aula_por_turno()
    turnos.as_form = True

    return locals()


@rtr()
@group_required('Diretor Acadêmico')
def relatorio_atividades_docentes_a_deferir(request):
    ids = (
        AtividadeDocente.objects.filter(professor__vinculo__ativo=True, professor__vinculo__setor=request.user.get_vinculo().setor, deferida=None)
        .distinct()
        .values_list('professor', flat=True)
    )
    qs_professores_com_atividades_a_deferir = Professor.servidores_docentes.filter(pk__in=ids)
    title = 'Relatório - Professor{} com atividades docentes não deferidas'.format(pluralize(qs_professores_com_atividades_a_deferir.count(), 'es'))
    return locals()


@rtr()
@group_required('Diretor Acadêmico')
def relatorio_professores_sem_atividades_docentes(request):
    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request)
    atividades = AtividadeDocente.objects.filter(
        professor__vinculo__ativo=True,
        professor__vinculo__setor=request.user.get_vinculo().setor,
        ano_letivo__ano=periodo_letivo_atual.ano,
        periodo_letivo=periodo_letivo_atual.periodo,
    ).distinct()
    qs_professores = (
        Professor.servidores_docentes.filter(vinculo__ativo=True, vinculo__setor=request.user.get_vinculo().setor)
        .exclude(atividadedocente__in=atividades)
        .distinct()
    )
    title = 'Relatório - Professor{} sem atividades docentes cadastrada para {}.{}'.format(
        pluralize(qs_professores.count(), 'es'), periodo_letivo_atual.ano, periodo_letivo_atual.periodo
    )

    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def relatorio_ch_docente(request):
    title = 'Relatório de Carga Horária Docente'
    form = BuscaPlanoIndividualTrabalhoForm(data=request.GET or None)
    if form.is_valid():
        pits = form.processar()[0]
        pits = pits.filter(professor__vinculo__id__in=Vinculo.objects.servidores().values_list('id', flat=True))
        if 'xls' in request.GET:
            return tasks.exportar_relatorio_ch_docente_xls(pits)
    return locals()
