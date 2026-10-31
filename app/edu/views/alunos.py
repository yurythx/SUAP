import base64
import datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.aggregates import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from comum.models import APIExterna, Configuracao
from comum.utils import get_uo
from djtools import layout
from djtools.html.graficos import GroupedColumnChart, LineChart, PieChart
from djtools.lps import lps
from djtools.utils import (
    JsonResponse,
    get_client_ip,
    group_required,
    httprr,
    int_to_roman,
    normalizar_nome_proprio,
    permission_required,
    rtr,
    send_mail,
)
from documento_eletronico.models import DocumentoTexto
from edu import perms, tasks
from edu.forms import (
    AcessoResponsavelForm,
    AlterarMatrizAlunoForm,
    AlterarMatrizLoteForm,
    AlunoCRAForm,
    AtualizarDadosPessoaisForm,
    AlterarAnoPeriodoIngressoForm,
    AtualizarDadosSISTECAlunoForm,
    AtualizarEmailAlunoForm,
    AtualizarFotoForm,
    CadastrarMatriculaPeriodo,
    DadosIncompletosAlunoForm,
    EditarDadosResponsavelForm,
    EditarObsIntegralizacaoEnsinoMedioForm,
    EditarOrientacaoForm,
    ObservacaoForm,
    SituacaoMatriculaForm,
    SituacaoMatriculaPeriodoForm,
    TurnoForm,
    SolicitarQuitacaoNadaConstaForm,
)
from edu.models import (
    Aluno,
    AlunoArquivo,
    AtividadePraticaProfissional,
    ComponenteCurricular,
    CreditoEspecial,
    CursoCampus,
    Diretoria,
    EstagioDocente,
    FrequenciaPeDeMeia,
    ItemConfiguracaoAvaliacao,
    MatriculaDiario,
    MatriculaPeriodo,
    Modalidade,
    NotaAvaliacao,
    Observacao,
    PeriodoLetivoAtual,
    ProcedimentoMatricula,
    RegistroConvocacaoENADE,
    RegistroEmissaoDiploma,
    Requerimento,
    RotuloModulo,
    SituacaoMatricula,
    TipoAtividadeComplementar,
)
from edu.models.nada_consta import ItemConfiguracaoNadaConsta
from etep.perms import tem_permissao_realizar_procedimentos_etep
from processo_eletronico.models import Processo
from protocolo.models import Processo as ProcessoProtocolo
from rh.models import PessoaInfoComplementar, UnidadeOrganizacional

from .pdfs import comprovante_matricula_pdf


@csrf_exempt
def fotografar(request):
    return HttpResponse(base64.b64encode(request.body))


@rtr()
@lps
def aluno(request, matricula):
    """Exibe a página de detalhes de um aluno.

    Carrega dados pessoais, acadêmicos, financeiros e de assuntos
    estudantis do aluno, além de gerenciar abas como requerimentos,
    grade curricular, abono de faltas e nada consta.

    Args:
        request: requisição HTTP.
        matricula: número de matrícula do aluno.

    Returns:
        dicionário com o contexto para renderização do template.
    """
    obj = get_object_or_404(Aluno, matricula=matricula)
    title = f'{normalizar_nome_proprio(obj.get_nome())} ({obj.matricula!s})'
    academico_nome_sistema = Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema')
    aluno_possui_matriz = obj.matriz_id is not None
    is_responsavel = False
    is_proprio_aluno = obj.is_user(request)
    eh_menor_idade = obj.eh_menor_idade
    if request.user.is_anonymous:
        if request.session.get('matricula_aluno_como_resposavel') == matricula:
            is_responsavel = True
            if eh_menor_idade:
                autorizacao_uso_imagem = request.GET.get('autorizar_uso_imagem')
                if autorizacao_uso_imagem:
                    autorizado = autorizacao_uso_imagem == '1'
                    obj.autorizar_uso_imagem(None, autorizado)
                    msg = 'Autorização registrada com sucesso' if autorizado else 'Recusa registrada com sucesso'
                    return httprr(f'/edu/aluno/{matricula}/?tab=comunicacao_social', msg)
        else:
            return httprr('/', 'Você não tem permissão para acessar esta página.', 'error')
    elif is_proprio_aluno and not eh_menor_idade:
        autorizacao_uso_imagem = request.GET.get('autorizar_uso_imagem')
        if autorizacao_uso_imagem:
            autorizado = autorizacao_uso_imagem == '1'
            obj.autorizar_uso_imagem(request.user, autorizado)
            msg = 'Autorização registrada com sucesso' if autorizado else 'Recusa registrada com sucesso'
            return httprr(f'/edu/aluno/{matricula}/?tab=comunicacao_social', msg)

    is_pedemeia = obj.curso_campus.modalidade_id in (Modalidade.INTEGRADO, Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA)
    is_assistente_social = request.user.has_perm('ae.pode_abrir_inscricao_do_campus')
    is_admin = request.user.has_group_cached('Administrador Acadêmico')
    is_auxiliar_secretaria = request.user.has_group_cached('Auxiliar de Secretaria Acadêmica')
    is_diretor_geral = request.user.has_group_cached('Diretor Geral') and obj.curso_campus.diretoria.diretor_geral_id == request.user.get_vinculo().id
    is_orientador = perms.is_orientador(request, obj)
    is_coorientador = perms.is_coorientador(request, obj)
    is_cra = request.user.has_group_cached('Coordenador de Registros Acadêmicos') and obj.situacao.id in [
        SituacaoMatricula.CONCLUIDO,
        SituacaoMatricula.FORMADO,
        SituacaoMatricula.EVASAO,
        SituacaoMatricula.TRANCADO,
        SituacaoMatricula.FALECIDO,
        SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
        SituacaoMatricula.CANCELADO,
        SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
        SituacaoMatricula.TRANSFERIDO_EXTERNO,
        SituacaoMatricula.JUBILADO,
    ]
    is_da_mesma_diretoria_academica = Diretoria.locals.filter(setor__id=obj.setor.id).exists() if obj.setor else False
    is_do_mesmo_campus = UnidadeOrganizacional.locals.filter(id=obj.setor.uo.id).exists() if obj.setor else False
    pode_ver_dados_sociais = is_proprio_aluno or request.user.has_group_cached(
        'Assistente Social, Coordenador de Atividades Estudantis Sistêmico, Auditor'
    )
    pode_ver_dados_bancarios = pode_ver_dados_sociais or request.user.has_group_cached('Coordenador de Pesquisa')
    pode_ver_dados_academicos = perms.pode_ver_dados_academicos(request, obj)
    pode_ver_historico = not obj.eh_aluno_minicurso() and (
        pode_ver_dados_academicos or pode_ver_dados_sociais or request.user.has_perm('edu.emitir_historico')
    )
    pode_ver_boletim = not obj.eh_aluno_minicurso() and (
        pode_ver_dados_academicos or pode_ver_dados_sociais or request.user.has_perm('edu.emitir_boletim')
    )
    pode_ver_botao_ldap = (
        not settings.DEBUG and obj.situacao.ativo and (obj.matriz or obj.participanteturmaminicurso_set.filter(turma__gerar_matricula=True).exists())
    )

    pode_enviar_mensagem = request.user.has_perm('edu.add_mensagem') and (
        request.user.has_group_cached('Administrador Acadêmico')
        or is_da_mesma_diretoria_academica
        or (request.user.has_group_cached('Coordenador de Registros Acadêmicos,Operador do Comunicador') and is_do_mesmo_campus)
    )
    pode_editar_email_secundario_aluno = request.user.has_perm('rh.pode_editar_email_secundario_aluno')
    tem_permissao_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.curso_campus)
    pode_ver_etep = (
        not is_responsavel
        and 'etep' in settings.INSTALLED_APPS
        and (
            tem_permissao_realizar_procedimentos_etep(request, obj.curso_campus.diretoria.setor)
            or obj.acompanhamento_set.filter(interessado__vinculo=request.user.get_vinculo())
        )
    )

    tem_permissao_para_emitir_docs_matricula = (
        request.user.has_perm('edu.efetuar_matricula') or request.user.has_group_cached('Estagiário')
    ) and is_da_mesma_diretoria_academica
    pode_editar_titulacao_diario_resumido = tem_permissao_realizar_procedimentos or is_admin
    pode_realizar_procedimentos = tem_permissao_realizar_procedimentos and not obj.is_concluido() or is_admin
    pode_cadastrar_procedimento_matricula = tem_permissao_realizar_procedimentos and Configuracao.get_valor_por_chave(
        'edu', 'pode_cadastrar_procedimento_matricula'
    )
    pode_desfazer_procedimentos = tem_permissao_realizar_procedimentos and not obj.is_concluido(ignorar_integralizacao_fase_escolar=True) or is_admin
    pode_realizar_operacoes_qacademico = is_do_mesmo_campus and (
        request.user.has_perm('edu.efetuar_matricula') or request.user.has_perm('edu.view_registroemissaodiploma')
    )
    pode_realizar_transferencia = (
        pode_realizar_procedimentos and obj.get_ultima_matricula_periodo() and obj.get_ultima_matricula_periodo().pode_realizar_transferencia()
    )
    pode_desfazer_migracao = not is_responsavel and request.user.has_group_cached('Administrador Acadêmico', ignore_groups_if_superuser=False)
    pode_ver_cpf = (
        pode_ver_dados_sociais
        or pode_ver_dados_academicos
        or request.user.has_group_cached('Coordenador de TI de campus, Coordenador de TI sistêmico, Coordenador de Atividades Estudantis, Servidor')
    )
    pode_alterar_email = perms.pode_alterar_email(request, obj)
    pode_ver_requisitos_de_conclusao = (
        pode_ver_dados_academicos
        or request.user.has_group_cached('Diretor de Avaliação e Regulação do Ensino, Operador de Censo')
        or (
            request.user.has_group_cached('Organizador de Formatura, Coordenador de Registros Acadêmicos')
            and (is_da_mesma_diretoria_academica or is_do_mesmo_campus)
        )
    )

    diploma = RegistroEmissaoDiploma.objects.filter(aluno=obj, cancelado=False).order_by('-via')
    emitiu_diploma = diploma.exists()
    if not (
        pode_editar_email_secundario_aluno
        or pode_ver_dados_sociais
        or pode_ver_dados_academicos
        or pode_realizar_procedimentos
        or request.user.has_perm('edu.view_aluno')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    ultima_matricula_periodo = obj.get_ultima_matricula_periodo()
    is_lancamento_conceito = obj.matriz and obj.matriz.estrutura and obj.matriz.estrutura.is_lancamento_conceito() or False
    is_matriculado = obj.situacao.id == SituacaoMatricula.MATRICULADO
    is_matricula_vinculo = obj.situacao.id == SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL
    is_nivel_pos_graduacao = obj.curso_campus.modalidade and obj.eh_aluno_nivel_pos_graduacao()
    pode_editar_orientadores_pos = perms.pode_editar_orientadores_pos(request, obj)
    pode_editar_titulo_pesquisa_pos = is_proprio_aluno or is_orientador or is_coorientador or pode_editar_orientadores_pos
    pode_solicitar_atividade_complementar = obj.pode_solicitar_atividade_complementar(request.user)
    pode_evadir = False
    pode_integralizar_fase_escolar = request.user.has_group_cached('Administrador Acadêmico') or obj.pode_integralizar_fase_escolar()

    if ultima_matricula_periodo:
        pode_evadir = pode_realizar_procedimentos and (
            ultima_matricula_periodo.is_matriculado() or ultima_matricula_periodo.is_matricula_vinculo() or ultima_matricula_periodo.is_aberto()
        )

    if 'enviar_comprovante_matricula' in request.GET:
        if obj.email_notificacao:
            attachments = [('Comprovante.pdf', comprovante_matricula_pdf(request, obj.pk).content, 'application/pdf')]
            send_mail(
                'Comprovante de Matrícula',
                'Caro aluno(a), segue em anexo seu comprovante de matrícula.',
                settings.DEFAULT_FROM_EMAIL,
                [obj.email_notificacao],
                fail_silently=False,
                attachments=attachments,
            )
            mensagem_envio_email = f'Comprovante de matrícula enviado para {obj.email_notificacao}.'
            return httprr(f'{obj.get_absolute_url()}', mensagem_envio_email)

    if 'desfazer_migracao' in request.GET and pode_desfazer_migracao:
        obj.desfazer_migracao()
        return httprr('..', 'A migração do aluno do Q-Acadêmico foi desfeita com sucesso!')

    if 'excluir_procedimento_id' in request.GET and pode_cadastrar_procedimento_matricula:
        procedimento = get_object_or_404(ProcedimentoMatricula, pk=request.GET['excluir_procedimento_id'])
        if procedimento.identificador_externo == 999999999:
            procedimento.delete()
            return httprr(f'/edu/aluno/{obj.matricula}/?tab=procedimentos', 'Procedimento excluído com sucesso!')
        else:
            return httprr(f'/edu/aluno/{obj.matricula}/?tab=procedimentos', 'Procedimento não pode ser excluído.', 'error')

    if 'procedimento_id' in request.GET and pode_desfazer_procedimentos:
        procedimento = get_object_or_404(ProcedimentoMatricula, pk=request.GET['procedimento_id'])
        try:
            procedimento.desfazer()
        except Exception as e:
            return httprr('.', e.message, 'error')
        return httprr('.', 'Procedimento desfeito com sucesso!')

    if (
        'reprocessar_historico' in request.GET
        and pode_realizar_procedimentos
        and (obj.matriz and obj.matriz.estrutura)
        and (is_matriculado or is_matricula_vinculo)
    ):
        obj.atualizar_situacao('Reprocessamento do Histórico')
        obj.identificar_registros_equivalencia(gerar=True)
        return httprr('.', 'Histórico reprocessado com sucesso.')

    tab = request.GET.get('tab')

    # PROCEDIMENTOS DE MATRÍCULA
    procedimentos = obj.get_procedimentos_matricula()

    # PROCEDIMENTOS COM REDUÇÃO DE CH INTEGRALIZAADA
    procedimentos_reducao_ch = obj.get_procedimentos_reducao_ch()

    # ATIVIDADES ESTUDANTIS
    if tab == 'atividades_estudantis' and 'ae' in settings.INSTALLED_APPS:
        from ae.models import (
            AgendamentoRefeicao,
            DemandaAluno,
            DocumentoInscricaoAluno,
            HistoricoFaltasAlimentacao,
            HistoricoSuspensoesAlimentacao,
            Participacao,
            ParticipacaoBolsa,
            PeriodoInscricao,
        )

        atendimentos = obj.demandaalunoatendida_set.filter(quantidade__gt=0).order_by('-data')[:10]
        participacoes = Participacao.objects.filter(inscricao__aluno=obj).order_by('data_inicio', 'data_termino')
        participacoes_bolsas = ParticipacaoBolsa.objects.filter(aluno=obj).order_by('data_inicio', 'data_termino')

        mes = datetime.date.today().month
        ano = datetime.date.today().year
        demandas_atendidas = obj.demandaalunoatendida_set.filter(quantidade__gt=0, data__month=mes, data__year=ano)
        atendimentos_grafico = []

        for demanda in DemandaAluno.ativas.all():
            atendimentos_do_mes = demandas_atendidas.filter(demanda__nome=demanda.nome)
            if atendimentos_do_mes.exists():
                atendimentos_grafico.append([demanda.nome, atendimentos_do_mes.aggregate(Sum('quantidade'))['quantidade__sum'] or 0])

        nome_pk = 'grafico_atendimentos'
        grafico = PieChart(nome_pk, title='Total de Atendimentos neste Mês', minPointLength=0, data=atendimentos_grafico)
        grafico.id = nome_pk

        agendamentos = AgendamentoRefeicao.objects.filter(cancelado=False, aluno=obj, data__gte=datetime.date.today()).order_by('-data')

        historico_faltas = HistoricoFaltasAlimentacao.objects.filter(aluno=obj).order_by('-data')[:10]
        historico_suspensoes = HistoricoSuspensoesAlimentacao.objects.filter(participacao__aluno=obj).order_by('-data_inicio')[:10]
        documentos = DocumentoInscricaoAluno.objects.filter(aluno=obj).order_by('-data_cadastro', '-integrante_familiar')
        hoje = datetime.date.today()
        periodos_permitidos = PeriodoInscricao.objects.filter(
            campus=obj.curso_campus.diretoria.setor.uo,
            data_termino__gte=datetime.datetime.today(),
            programa__instituicao=get_uo(request.user),
            edital__ativo=True,
        )

        aluno_pode_adicionar_documento = is_proprio_aluno and periodos_permitidos.exists()

    fazer_avaliacao_biomedica = False
    prazo_alerta_avaliacao_biomedica = Configuracao.get_valor_por_chave('saude', 'prazo_alerta_avaliacao_biomedica')
    if 'saude' in settings.INSTALLED_APPS and prazo_alerta_avaliacao_biomedica:
        from saude.models import Atendimento, TipoAtendimento

        fazer_avaliacao_biomedica = (
            obj.data_matricula
            and (datetime.datetime.now() - obj.data_matricula).days > int(prazo_alerta_avaliacao_biomedica)
            and obj.situacao_id == SituacaoMatricula.MATRICULADO
            and obj.curso_campus.modalidade_id == Modalidade.INTEGRADO
            and obj.ano_letivo
            and obj.ano_letivo.ano > 2015
            and not Atendimento.objects.filter(tipo=TipoAtendimento.AVALIACAO_BIOMEDICA, aluno=obj).exists()
        )

    # DIPLOMAS E CERTIFICADOS
    diplomas = obj.get_registros_emissao_diploma()

    # MODULOS
    if tab == 'modulos':
        qs_cc = ComponenteCurricular.objects.filter(matriz_id=obj.matriz_id).only('id', 'tipo_modulo').order_by('tipo_modulo')
        modulos = set()
        for componente_curricular in qs_cc:
            componente_curricular.matricula_diario = (
                MatriculaDiario.objects.filter(matricula_periodo__aluno_id=obj.id, diario__componente_curricular_id=componente_curricular.id)
                .order_by('-diario_id')
                .first()
            )
            if componente_curricular.tipo_modulo is not None:
                modulos.add(componente_curricular.tipo_modulo)
        modulos_aptos_certificacao = []
        for modulo in modulos:
            ids_cc = ComponenteCurricular.objects.filter(matriz_id=obj.matriz_id, tipo_modulo=modulo).order_by('id').values_list('id', flat=True)
            ids_md = (
                MatriculaDiario.objects.filter(
                    matricula_periodo__aluno_id=obj.id,
                    diario__componente_curricular__tipo_modulo=modulo,
                    situacao__in=[
                        MatriculaDiario.SITUACAO_APROVADO,
                        MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                        MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
                    ],
                )
                .order_by('diario__componente_curricular__id')
                .values_list('diario__componente_curricular_id', flat=True)
            )
            if list(ids_cc) == list(ids_md):
                rotulo = RotuloModulo.objects.filter(matriz=obj.matriz, tipo_modulo=modulo).first() or f'Módulo {int_to_roman(modulo)}'
                modulos_aptos_certificacao.append((modulo, rotulo))

    # BOLETIM
    if tab == 'boletim':
        qs = obj.get_matriculas_periodo()
        if qs.exists():
            anos_periodos = qs.values_list('ano_letivo__ano', 'periodo_letivo').distinct()
        matriculas_diario = None
        if not request.GET.get('ano_periodo'):
            matricula_periodo = ultima_matricula_periodo
            matriculas_diario = ultima_matricula_periodo and matricula_periodo.matriculadiario_set.select_related(
                'diario__componente_curricular__componente_curricular_associado'
            ).all().order_by('diario__componente_curricular__tipo_modulo', 'diario__componente_curricular__componente__descricao')
        elif request.GET.get('ano_periodo'):
            try:
                ano_periodo = request.GET.get('ano_periodo').split('_')
                ano = int(ano_periodo[0])
                periodo = int(ano_periodo[1])
                qs_matricula_periodo = MatriculaPeriodo.objects.filter(aluno=obj, ano_letivo__ano=ano, periodo_letivo=periodo)
                if qs_matricula_periodo:
                    matricula_periodo = qs_matricula_periodo[0]
                    matriculas_diario = (
                        matricula_periodo.matriculadiario_set.select_related('diario__componente_curricular__componente_curricular_associado')
                        .all()
                        .order_by('diario__componente_curricular__componente__descricao')
                    )
            except ValueError:
                return httprr('.', 'Requisição inválida.', 'error')
            except Exception:
                return httprr('.', 'Erro.', 'error')
        if matriculas_diario:
            tem_nota_atitudinal = matriculas_diario[0].diario.utiliza_nota_atitudinal()
            qtd_colunas_etapa = tem_nota_atitudinal and 4 or 2

            try:
                etapa = int(request.GET.get('etapa'))
            except Exception:
                etapa = 1
            etapa = etapa > 7 and 1 or etapa
            id_grafico = 'graficoBoletim'
            grafico = GroupedColumnChart(
                id_grafico, data=matricula_periodo.get_estatisticas_boletim(etapa), groups=['Nota do Aluno', 'Média da Turma']
            )
            grafico.series[0]['dataLabels'] = {'enabled': True, 'color': '#FFF', 'align': 'center', 'y': 30}
            grafico.series[1]['dataLabels'] = {'enabled': True, 'color': '#FFF', 'align': 'center', 'y': 30}

            if obj.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                max_qtd_avaliacoes = 4
            else:
                max_qtd_avaliacoes = 1
                for matricula_diario in matriculas_diario:
                    if matricula_diario.diario.componente_curricular.qtd_avaliacoes > max_qtd_avaliacoes:
                        max_qtd_avaliacoes = matricula_diario.diario.componente_curricular.qtd_avaliacoes

    # ATIVIDADES ESPECIFICAS
    diarios_especiais = obj.get_diarios_especiais()
    if tab == 'atividades_especificas':
        if diarios_especiais.exists():
            anos_periodos = diarios_especiais.values_list('ano_letivo__ano', 'periodo_letivo').distinct()

        if request.GET.get('ano_periodo'):
            ano_periodo = request.GET.get('ano_periodo').split('_')
            ano = int(ano_periodo[0])
            periodo = int(ano_periodo[1])
            qs_matricula_periodo = MatriculaPeriodo.objects.filter(aluno=obj, ano_letivo__ano=ano, periodo_letivo=periodo)
            if qs_matricula_periodo:
                matricula_periodo = qs_matricula_periodo[0]
                if obj.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                    diarios_especiais = diarios_especiais.filter(
                        ano_letivo=matricula_periodo.ano_letivo, periodo_letivo=matricula_periodo.periodo_letivo
                    ).order_by('componente__descricao')
                else:
                    diarios_especiais = diarios_especiais.filter(ano_letivo=matricula_periodo.ano_letivo).order_by('componente__descricao')

    # HISTÓRICO
    if tab == 'historico':
        if 'order_by' in request.GET:
            ordenar_por = (
                request.GET['order_by'] == 'componente'
                and Aluno.ORDENAR_HISTORICO_POR_COMPONENTE
                or request.GET['order_by'] == 'periodo_matriz'
                and Aluno.ORDENAR_HISTORICO_POR_PERIODO_MATRIZ
                or Aluno.ORDENAR_HISTORICO_POR_PERIODO_LETIVO
            )
        else:
            ordenar_por = Aluno.ORDENAR_HISTORICO_POR_PERIODO_MATRIZ
        exibir_optativas = 'optativas' in request.GET
        if obj.iniciou_suap() or obj.integralizou_suap():
            historico = obj.get_historico(False, ordenar_por, exibir_optativas)
        else:
            historico = cache.get(f'historico-{obj.pk}')
            if historico is None:
                historico = obj.get_historico_legado()
                cache.set(f'historico-{obj.pk}', historico, 1 * 60)

    # PROJETO FINAL
    projetos = obj.get_projetos_finais()

    # MEDIDAS DISCIPLINARES
    if tab == 'medidas_premiacoes':
        medidas_disciplinares = obj.medidadisciplinar_set.all()
        premiacoes = obj.premiacao_set.all()
        pode_gerenciar_medidas_premiacoes = (pode_realizar_procedimentos or is_diretor_geral) and not obj.is_cancelado()

    # ATIVIDADES COMPLEMENTARES
    modalidade_possui_aacc = (
        obj.matriz
        and obj.matriz.ch_atividades_complementares
        and TipoAtividadeComplementar.objects.filter(modalidades__in=[obj.curso_campus.modalidade]).exists()
    )
    if tab == 'acc':
        tipos = obj.get_ch_atividades_complementares_por_tipo()

    atividades_complementares = obj.get_atividades_complementares()

    if tab == 'extensao':
        pode_cadastrar_atividade_curricular_extensao_extra = (
            Configuracao.get_valor_por_chave('edu', 'habilita_atividade_curricular_extensao_extra') and pode_realizar_procedimentos
        )
        pode_editar_matricula_diario_resumida = request.user.has_perm('edu.add_atividadecurricularextensao') and pode_realizar_procedimentos
        exibe_acoes_atividades = pode_cadastrar_atividade_curricular_extensao_extra or pode_editar_matricula_diario_resumida

    # ATIVIDADES DE APROFUNDAMENTO
    if tab == 'atividades_aprofundamento':
        pass
    atividades_aprofundamento = obj.atividadeaprofundamento_set.all()

    # REQUISITOS DE CONCLUSÃO
    possui_pendencias_conclusao = obj.possui_pendencia()
    matrizppc = obj.matriz.get_matrizppc() if aluno_possui_matriz else None
    possui_pratica_ppc = matrizppc.ppc.ch_pratica > 0 if matrizppc else False
    if tab == 'requisitos' and aluno_possui_matriz:
        # CH Esperada
        ch_componentes_regulares_obrigatorios_esperada = obj.get_ch_componentes_regulares_obrigatorios_esperada()
        ch_componentes_regulares_optativos_esperada = obj.get_ch_componentes_regulares_optativos_esperada()
        ch_pratica_como_componente_esperada = obj.get_ch_pratica_como_componente_esperada()
        ch_visita_tecnica_esperada = obj.get_ch_visita_tecnica_esperada()
        ch_componentes_eletivos_esperada = obj.get_ch_componentes_eletivos_esperada()
        ch_componentes_seminario_esperada = obj.get_ch_componentes_seminario_esperada()
        ch_componentes_pratica_profissional_esperada = obj.get_ch_componentes_pratica_profissional_esperada()
        ch_componentes_tcc_esperada = obj.get_ch_componentes_tcc_esperada()
        ch_atividades_complementares_esperada = obj.get_ch_atividades_complementares_esperada()
        ch_atividade_aprofundamento_esperada = obj.get_ch_atividade_aprofundamento_esperada()
        ch_extensao_componentes_esperada = obj.get_ch_extensao_componentes_esperada()
        ch_extensao_outras_atividades_esperada = obj.get_ch_extensao_outras_atividades_esperada()
        ch_extensao_outros_componentes_esperada = obj.get_ch_extensao_outros_componentes_esperada()
        ch_atividades_pratica_profissional_esperada = obj.get_ch_atividade_pratica_profissional_esperada() if possui_pratica_ppc else 0
        total_ch_esperada = obj.matriz.get_carga_horaria_total_prevista()
        requer_pp_atp = ch_componentes_pratica_profissional_esperada and ch_atividade_aprofundamento_esperada
        tipos_atividades_extensao = sum(
            1 for v in [ch_extensao_componentes_esperada, ch_extensao_outras_atividades_esperada, ch_extensao_outros_componentes_esperada] if v > 1
        )

        # CH Cumprida
        (
            ch_componentes_regulares_obrigatorios_cumprida,
            ch_componentes_regulares_optativos_cumprida,
            ch_componentes_seminario_cumprida,
            ch_componentes_pratica_profissional_cumprida,
            ch_componentes_tcc_cumprida,
            ch_atividades_complementares_cumprida,
            ch_atividades_aprofundamento_cumprida,
            ch_extensao_componentes_cumprida,
            ch_extensao_outras_atividades_cumprida,
            ch_extensao_outros_componentes_cumprida,
            ch_pratica_como_componente_cumprida,
            ch_visita_tecnica_cumprida,
            ch_componentes_eletivos_cumprida,
            ch_atividades_pratica_profissional_cumprida,
            percentual_ch_cumprida,
        ) = obj.get_ch_componentes_com_percentual_ch_cumprida()
        percentual_ch_cumprida = int(percentual_ch_cumprida)

        # Pendente
        (
            ch_componentes_regulares_obrigatorios_pendente,
            ch_componentes_regulares_optativos_pendente,
            ch_componentes_eletivos_pendente,
            ch_componentes_seminario_pendente,
            ch_componentes_pratica_profissional_pendente,
            ch_atividades_aprofundamento_pendente,
            ch_extensao_componentes_pendente,
            ch_extensao_outras_atividades_pendente,
            ch_extensao_outros_componentes_pendente,
            ch_componentes_tcc_pendente,
            ch_atividades_complementares_pendente,
            ch_componentes_pratica_como_componente_pendente,
            ch_componentes_visita_tecnica_pendente,
            ch_atividades_pratica_profissional_pendente,
            total_ch_pendente,
        ) = obj.get_ch_pendente(detalhado=True)
        total_ch_cumprida = max(total_ch_esperada - total_ch_pendente, 0)
        pendencias_atividade_pratica_profissional = obj.get_pendencias_atividade_pratica_profissional(resumido=True) if possui_pratica_ppc else None

    # ATIVIDADES DE PRÁTICA PROFISSIONAL
    if tab == 'atividades_pratica_profissional' and matrizppc:
        ch_pratica_contabilizada = obj.get_ch_atividade_pratica_profissional_contabilizada()
        media_pratica_profissional = obj.calcular_media_atividade_pratica_profissional()
        atingiu_media_aprovacao_atividade_pratica_profissional = (
            media_pratica_profissional >= obj.matriz.estrutura.media_aprovacao_sem_prova_final if media_pratica_profissional else False
        )
        atividades_pratica_profissional = AtividadePraticaProfissional.objects.filter(matricula_periodo__aluno_id=obj.id)
        pendencias_atividade_pratica_profissional = obj.get_pendencias_atividade_pratica_profissional() if possui_pratica_ppc else None
        pode_cadastrar_atividade_pratica_profissional = request.user.has_perm('edu.add_atividadepraticaprofissional') and (
            is_proprio_aluno or tem_permissao_realizar_procedimentos
        )

        modalidades = matrizppc.get_modalidades_praticaprofissionalppc()
        modalidades_obrigatorias = [m for m in modalidades if not m.optativa]
        modalidades_optativas = [m for m in modalidades if m.optativa]
        percentual_pratica_cumprida = (
            Decimal(ch_pratica_contabilizada / matrizppc.ppc.ch_pratica * 100).quantize(Decimal('0.01')) if ch_pratica_contabilizada else Decimal(0)
        )

    # PEDIDOS DE MATRÍCULA
    pedidos_matricula = obj.get_pedidos_matricula()

    # PROJETOS DE EXTENSAO E PESQUISA
    if 'pesquisa' in settings.INSTALLED_APPS and obj.get_vinculo():
        ProjetoPesquisa = apps.get_model('pesquisa', 'Projeto')
        ParticipacaoPesquisa = apps.get_model('pesquisa', 'Participacao')
        participacoes_pesquisa = ParticipacaoPesquisa.objects.filter(vinculo_pessoa__id=obj.get_vinculo().id, projeto__aprovado=True)
        participacoes_projetos_pesquisa = ProjetoPesquisa.objects.filter(id__in=participacoes_pesquisa.values_list('projeto', flat=True))
    else:
        participacoes_projetos_pesquisa = []

    if 'projetos' in settings.INSTALLED_APPS and obj.get_vinculo():
        ProjetoExtensao = apps.get_model('projetos', 'Projeto')
        ParticipacaoExtensao = apps.get_model('projetos', 'Participacao')
        participacoes_extensao = ParticipacaoExtensao.objects.filter(vinculo_pessoa__id=obj.get_vinculo().id, projeto__aprovado=True)
        participacoes_projetos_extensao = ProjetoExtensao.objects.filter(id__in=participacoes_extensao.values_list('projeto', flat=True))
    else:
        participacoes_projetos_extensao = []

    qtd_participacoes_projetos = len(participacoes_projetos_pesquisa) + len(participacoes_projetos_extensao)

    # PASTA DOCUMENTAL
    total_aluno_arquivos = obj.alunoarquivo_set.count()
    if tab == 'pasta_documental':
        aluno_arquivos = obj.alunoarquivo_set.all()
        if aluno_arquivos.exists():
            for arquivo in aluno_arquivos:
                arquivo.pode_ser_deletado = arquivo.can_delete(request.user)

        if 'aluno_arquivo' in request.GET:
            if is_admin or pode_realizar_procedimentos or is_proprio_aluno:
                aluno_arquivo = AlunoArquivo.objects.filter(pk=request.GET['aluno_arquivo'], aluno=obj).first()
                if aluno_arquivo and aluno_arquivo.can_delete(request.user):
                    aluno_arquivo.delete()
                    return httprr(f'{obj.get_absolute_url()}?tab=pasta_documental', 'Arquivo excluído com sucesso.')
            else:
                return httprr(f'{obj.get_absolute_url()}?tab=pasta_documental', 'Você não possui permissão para isso.', 'error')

    # ESTAGIOS
    if tab == 'estagios':
        estagios = obj.praticaprofissional_set.all()

    qtd_estagios = (
        obj.praticaprofissional_set.all().count()
        + EstagioDocente.objects.filter(matricula_diario__matricula_periodo__aluno=obj).distinct().count()
        + obj.aprendizagem_set.all().count()
        + obj.atividadeprofissionalefetiva_set.count()
    )

    # ENADE
    if tab == 'convocacoes_enade':
        pode_realizar_procedimentos_enade = perms.pode_realizar_procedimentos_enade(request.user, obj.curso_campus) and not obj.is_concluido()
        if request.user.has_group_cached('Diretor de Avaliação e Regulação do Ensino'):
            pode_realizar_dispensa_enade = obj.pode_ser_dispensado_enade(ignorar_pendencias=True)
        else:
            pode_realizar_dispensa_enade = pode_realizar_procedimentos_enade and obj.pode_ser_dispensado_enade()

        convocacoes_enade = obj.get_convocacoes_enade()
        qtd_convocacoes_enade = convocacoes_enade.count()
        convocacoes_enade_sem_situacao = convocacoes_enade.filter(situacao__isnull=True)
        exibe_mensagem_concluinte_invalido = (
            not obj.cumpriu_enade_concluinte(incluir_pratica=False)
            and obj.get_convocacoes_enade().filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE).exists()
        )

    # LOCAIS/HORÁRIOS DE AULA
    eh_minicurso = obj.eh_aluno_minicurso()
    if tab == 'locais_aula_aluno' and not eh_minicurso:
        periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, obj)
        tipo = 'aluno'
        matriculas_periodo = obj.matriculaperiodo_set.filter(ano_letivo__ano=periodo_letivo_atual.ano, periodo_letivo=periodo_letivo_atual.periodo)
        if matriculas_periodo:
            matriculas_diario = matriculas_periodo[0].matriculadiario_set.exclude(
                situacao__in=(MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_CANCELADO, MatriculaDiario.SITUACAO_TRANSFERIDO)
            )
            turnos = matriculas_periodo[0].get_horarios_aula_atividade_por_turno()
            atividades = matriculas_periodo[0].horarioatividadeextra_set.all().distinct('descricao_atividade')
            for atividade in atividades:
                atividade.horarios = atividade.get_horario_aulas()

    # ANOTAÇÕES INTERDISCIPLINARES - MÓDULO SAÚDE
    pode_ver_anotacoes_interdisciplinares = False
    if 'saude' in settings.INSTALLED_APPS:
        from saude.models import AnotacaoInterdisciplinar, Especialidades, InteressadoAnotacaoInterdisciplinar

        grupos_permitidos = Especialidades.GRUPOS
        pode_ver_prontuarios = request.user.has_group_cached(Especialidades.GRUPOS_PRONTUARIO)
        pode_adicionar_anotacao = request.user.has_group_cached([*Especialidades.GRUPOS, 'Assistente Social'])
        grupos_permitidos.append('Pedagogo')
        pode_ver_anotacoes_interdisciplinares = request.user.has_perm('rh.eh_servidor')
        anotacoes_disciplinares = AnotacaoInterdisciplinar.objects.filter(prontuario__vinculo=obj.get_vinculo())
        if not request.user.is_anonymous and not request.user.has_group_cached(grupos_permitidos):
            anotacoes_disciplinares = anotacoes_disciplinares.filter(
                id__in=InteressadoAnotacaoInterdisciplinar.objects.filter(interessado=request.user.get_vinculo()).values_list(
                    'anotacao_interdisciplinar', flat=True
                )
            )

    # ETEP
    if 'etep' in settings.INSTALLED_APPS:
        Acompanhamento = apps.get_model('etep', 'Acompanhamento')
        acompanhamentos = Acompanhamento.locals.filter(aluno=obj)
    else:
        acompanhamenots = []

    # REQUERIMENTO
    if tab == 'requerimentos':
        MATRICULA_DISCIPLINA = Requerimento.MATRICULA_DISCIPLINA
        TRANCAMENTO_DISCIPLINA = Requerimento.TRANCAMENTO_DISCIPLINA
        REALIZACAO_PROVA = Requerimento.REALIZACAO_PROVA
        TRANCAMENTO_MATRICULA = Requerimento.TRANCAMENTO_MATRICULA
        APROVEITAMENTO_ESTUDO = Requerimento.APROVEITAMENTO_ESTUDO
        tipos_requerimentos_abertos_alunos = Requerimento.get_tipos_abertos_alunos()
        tipos_requerimentos_diversos = Requerimento.get_aluno_choices()
        pode_solicitar_requerimento = (
            is_proprio_aluno
            and obj.situacao.ativo
            and obj.matriz
            and (
                obj.matriz.estrutura.tipo_avaliacao == 1
                or tipos_requerimentos_diversos
                or APROVEITAMENTO_ESTUDO in tipos_requerimentos_abertos_alunos
            )
        )
        requerimentos = Requerimento.objects.filter(aluno=obj).order_by('-data')
        if 'del_requerimento' in request.GET:
            requerimento = Requerimento.objects.filter(pk=request.GET.get('del_requerimento', 0)).first()
            if requerimento and requerimento.aluno == obj and requerimento.deferido is None:
                requerimento.delete()
                return httprr(f'{obj.get_absolute_url()}?tab=requerimentos', 'Requerimento excluído com sucesso.')

    # JUSTIFICATIVA DE FALTA
    pode_visualizar_abono_falta = False
    if request.GET.get('tab') == 'abono_falta':
        abonos = obj.abonofaltas_set.order_by('-id')
        pode_visualizar_abono_falta = is_proprio_aluno or tem_permissao_realizar_procedimentos or request.user.has_perm('edu.view_abonofaltas')

    # NADA CONSTA
    if tab == 'nada_consta':
        obj.checar_registros_nada_consta()
        tem_nada_consta_nao_solicitado = obj.nadaconsta_set.filter(valido=True, data_solicitacao__isnull=True, quitado__isnull=True).exists()
        pode_solicitar_nada_consta = tem_nada_consta_nao_solicitado and (
            tem_permissao_realizar_procedimentos or (not emitiu_diploma and (is_responsavel or is_proprio_aluno))
        )
        itens_nada_consta = ItemConfiguracaoNadaConsta.objects.filter(
            configuracao__modalidades__in=[
                obj.curso_campus.modalidade_id,
            ],
            configuracao__uo=obj.curso_campus.diretoria.setor.uo,
        ).distinct()
        itens_nada_consta = itens_nada_consta.filter(cursos__in=[obj.curso_campus]) | itens_nada_consta.filter(cursos__isnull=True)
        nada_consta_andamento = obj.nadaconsta_set.filter(data_solicitacao__isnull=False).order_by('-data_solicitacao')

    # Pé-de-Meia
    if tab == 'pedemeia':
        frequencias = FrequenciaPeDeMeia.objects.filter(matricula_periodo__aluno=obj).order_by('-ano__ano', '-mes')

    # Histórico/Diploma eletrônico
    urls_diploma_historico = obj.get_url_historico_diploma()
    pode_emitir_historico_final = (
        obj.is_concluido() and urls_diploma_historico is None and (tem_permissao_realizar_procedimentos or (is_cra and is_do_mesmo_campus))
    )

    # Documentos, Processos e Protocolos vinculados ao Aluno via atributo Aluno.pessoa_fisica
    if 'processo_eletronico' in settings.INSTALLED_APPS and tab == 'documentos_processos':
        documentos_eletronicos = (
            DocumentoTexto.get_documentos_por_vinculo(obj.get_vinculo())
            .distinct()
            .defer(
                'corpo',
                'corpo_indexado',
                'cabecalho',
                'rodape',
            )
        )
        processos_eletronicos = (
            Processo.objects.filter(interessados__pessoa__pessoafisica__cpf=obj.pessoa_fisica.cpf)
            .distinct()
            .only(
                'id',
                'numero_protocolo_fisico',
                'numero_protocolo',
                'assunto',
                'status',
            )
            if obj.pessoa_fisica.cpf
            else Processo.objects.none()
        ).order_by('-data_hora_criacao')
        processos_fisicos = (
            ProcessoProtocolo.get_protocolos_por_vinculo(obj.get_vinculo()).distinct().only('id', 'numero_processo_eletronico', 'numero_processo')
        )

    if tab == 'caracterizacao':
        # CadÚnico
        info_cadunico = None
        erro_cadunico = None
        api_externa = APIExterna.CADUNICO
        if api_externa.ativo:
            try:
                info_cadunico = PessoaInfoComplementar.get_instance(obj.pessoa_fisica, api_externa, force=False)
            except ValidationError as e:
                erro_cadunico = e.message

    if tab == 'grade_curricular':
        grade_curricular = obj.matriz.get_grade_curricular(obj.curso_campus)

    return locals()


@rtr()
@permission_required('edu.view_requerimento')
def solicitacoes_nada_consta(request, pk):
    title = 'Solicitações de Nada Consta'
    obj = get_object_or_404(Aluno, pk=pk)
    nada_consta_andamento = obj.nadaconsta_set.filter(data_solicitacao__isnull=False).order_by('-data_solicitacao')
    return locals()


@rtr()
@login_required()
def progresso_ch_por_matriculaperiodo(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)
    series = []
    percentual_ch_cumprida = 0
    if aluno.matriz:
        ultimo_periodo = aluno.get_ultima_matricula_periodo()
        for mp in aluno.get_matriculas_periodo(orderbyDesc=False):
            percentual_ch_cumprida = mp.percentual_ch_cumprida and float(mp.percentual_ch_cumprida) or 0
            # ajuste de arredondamento dos % cumpridos dos períodos anteriores
            if aluno.percentual_ch_cumprida == 100 and mp == ultimo_periodo:
                percentual_ch_cumprida = 100
            series.append([f'{mp.ano_letivo.ano}.{mp.periodo_letivo}', percentual_ch_cumprida])

    grafico_evolucao_anual = LineChart('grafico', title='', data=series, groups=['C.H Cumprida (%)'])
    return locals()


@group_required('Coordenador de Registros Acadêmicos, edu Administrador')
@rtr()
@login_required()
def editar_aluno(request, pk):
    aluno = get_object_or_404(
        Aluno,
        pk=pk,
        situacao__in=[
            SituacaoMatricula.CONCLUIDO,
            SituacaoMatricula.FORMADO,
            SituacaoMatricula.EVASAO,
            SituacaoMatricula.TRANCADO,
            SituacaoMatricula.FALECIDO,
            SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
            SituacaoMatricula.CANCELADO,
            SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            SituacaoMatricula.TRANSFERIDO_EXTERNO,
            SituacaoMatricula.JUBILADO,
        ],
    )
    title = 'Aluno'
    form = AlunoCRAForm(data=request.POST or None, files=request.FILES or None, instance=aluno)

    if form.is_valid():
        form.save()
        return httprr('..', 'Aluno atualizado com sucesso!')

    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def editar_dados_incompletos_aluno(request, pk):
    aluno = get_object_or_404(Aluno.locals, pk=pk)
    title = f'Editar dados: {aluno}'
    if aluno.situacao_id not in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]:
        return httprr('..', 'Você não tem permissão para editar os dados incompletos deste aluno.', 'error', close_popup=True)
    form = DadosIncompletosAlunoForm(data=request.POST or None, instance=aluno)

    if form.is_valid():
        form.processar()
        return httprr('..', 'Dados incompletos do aluno atualizados com sucesso!', close_popup=True)

    return locals()


@rtr()
@login_required()
def editar_observacao_integralizacao_ensino_medio(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    if not obj.pode_editar_obs_integralizacao_ensino_medio(request.user):
        return httprr('..', 'Você não tem permissão para editar a observação de integralização do ensino médio.', 'error', close_popup=True)
    title = f'Editar observação de integralização do Ensino Médio - {obj}'
    form = EditarObsIntegralizacaoEnsinoMedioForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Observação de integralização do ensino médio atualizada com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def editar_situacao_matricula_periodo(request, pk):
    if not request.user.has_group_cached('Administrador Acadêmico', ignore_groups_if_superuser=False):
        return httprr('.', 'Você não tem permissão para realizar isso.', 'error')

    obj = get_object_or_404(MatriculaPeriodo, pk=pk)
    title = f'Editar {obj}'
    form = SituacaoMatriculaPeriodoForm(data=request.POST or None, instance=obj)

    if form.is_valid():
        form.processar()
        return httprr(obj.aluno.get_absolute_url(), 'Situação de matrícula período alterada com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def cadastrar_matricula_periodo(request, pk):
    if not request.user.is_superuser and not request.user.has_group_cached('Administrador Acadêmico'):
        return httprr('.', 'Você não tem permissão para realizar isso.', 'error')
    title = 'Cadastrar Matrícula em Período'
    form = CadastrarMatriculaPeriodo(pk, data=request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Matrícula no período cadastrada com sucesso.')
    return locals()


@group_required('edu Administrador')
@rtr()
def editar_situacao_matricula(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    title = f'Editar {obj}'
    form = SituacaoMatriculaForm(data=request.POST or None, instance=obj)

    if form.is_valid():
        form.processar()
        return httprr('..', 'Situação de matrícula do aluno alterada com sucesso.')
    return locals()


@permission_required('comum.is_operador_de_censo')
@rtr()
def editar_turno(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    title = f'Editar {obj}'
    form = TurnoForm(data=request.POST or None, instance=obj)

    if form.is_valid():
        form.save()
        return httprr('..', 'Turno atualizado com sucesso.')
    return locals()


def alunos_ws(request):
    """WebService criado para o EAD"""
    if 'ponto' in settings.INSTALLED_APPS:
        Maquina = apps.get_model('ponto', 'Maquina')
        try:
            get_object_or_404(Maquina, ip=get_client_ip(request), cliente_ponto=True, ativo=True)
        except Maquina.DoesNotExist:
            raise PermissionDenied('Máquina sem permissões.')
    else:
        raise PermissionDenied('Máquina sem permissões.')

    if 'alunos_qs' in cache:
        return cache.get('alunos_qs')

    def aluno_to_dict(aluno):
        return {
            'nome': aluno.get_nome_social_composto(),
            'email': aluno.email_notificacao,
            'matricula': aluno.matricula,
            'curso': str(aluno.curso_campus),
            'campus': str(aluno.curso_campus.diretoria.setor.uo.sigla),
        }

    campus_sigla = request.GET.get('campus', '')
    alunos_qs = Aluno.objects.filter(situacao__ativo=True, curso_campus__diretoria__setor__uo__sigla__iexact=campus_sigla)[0:20]
    alunos = [aluno_to_dict(a) for a in alunos_qs]
    response = JsonResponse(alunos)
    cache.set('alunos_qs', response, 60 * 60 * 12)
    return response


# utilizado pelo sistema da saúde


def exportar_alunos_academico(request, matricula):
    nome_aluno = ''
    try:
        aluno = get_object_or_404(Aluno, matricula__iexact=matricula)
        if aluno.situacao.ativo:
            nome_aluno = aluno.pessoa_fisica.nome
    except Exception:
        pass
    return HttpResponse(nome_aluno)


@rtr()
@group_required(
    'Administrador Acadêmico,Secretário Acadêmico,Diretor Acadêmico,Estagiário,Assistente Social,Coordenador de Atividades Estudantis Sistêmico,'
)
def atualizar_dados_pessoais(request, pk):
    title = 'Atualização de Dados Pessoais'
    aluno = get_object_or_404(Aluno, pk=pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not (pode_realizar_procedimentos or request.user.has_perm('ae.add_demandaalunoatendida')):
        raise PermissionDenied
    initial = {
        'nome_usual': aluno.pessoa_fisica.nome_usual,
        'email_secundario': aluno.email_notificacao,
        'logradouro': aluno.logradouro,
        'numero': aluno.numero,
        'complemento': aluno.complemento,
        'bairro': aluno.bairro,
        'cep': aluno.cep,
        'cidade': aluno.cidade,
        'lattes': aluno.pessoa_fisica.lattes,
        'telefone_principal': aluno.telefone_principal,
        'telefone_secundario': aluno.telefone_secundario,
        'telefone_adicional_1': aluno.telefone_adicional_1,
        'telefone_adicional_2': aluno.telefone_adicional_2,
    }

    form = AtualizarDadosPessoaisForm(
        data=request.POST or None, initial=initial, instance=aluno, pode_realizar_procedimentos=pode_realizar_procedimentos
    )
    form.fields['nis'].required = False
    form.fields['nis'].help_text = ''
    if form.is_valid():
        form.save(aluno)
        return httprr('..', 'Dados Pessoais atualizados com sucesso.')
    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def alterar_ano_periodo_ingresso(request, pk):
    title = 'Alterar Ano/Período de Ingresso'
    aluno = get_object_or_404(Aluno, pk=pk)
    form = AlterarAnoPeriodoIngressoForm(data=request.POST or None)
    if form.is_valid():
        matricula = aluno.trocar_periodo_letivo_ingresso(
            novo_ano_letivo=form.cleaned_data['ano_letivo'], novo_periodo_letivo=form.cleaned_data['periodo_letivo']
        )
        if matricula:
            return httprr(f'/edu/aluno/{matricula}/', 'Período letivo corrigido com sucesso.', close_popup=True)
        else:
            return httprr(f'/edu/aluno/{aluno.matricula}/', 'Não foi possível realizar a alteração.', tag='error', close_popup=True)
    return locals()


@rtr()
@group_required('Administrador Acadêmico,Secretário Acadêmico,Diretor Acadêmico')
def editar_dados_sistec(request, pk):
    title = 'Atualizar dados SISTEC'
    aluno = get_object_or_404(Aluno, pk=pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        raise PermissionDenied
    form = AtualizarDadosSISTECAlunoForm(data=request.POST or None, instance=aluno)
    if form.is_valid():
        form.save()
        return httprr('.', 'Dados Pessoais atualizados com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def atualizar_meus_dados_pessoais(request, matricula, renovacao_matricula=None):
    """Exibe e processa o formulário de atualização de dados pessoais do aluno.

    Args:
        request: objeto da requisição HTTP.
        matricula: número de matrícula do aluno.
        renovacao_matricula: quando informado, redireciona para o fluxo de
            pedido de matrícula após a atualização.

    Returns:
        HttpResponse com o formulário renderizado ou redirecionamento.

    Raises:
        Http404: se nenhum aluno for encontrado com a matrícula informada.
    """
    title = 'Atualização de Dados Pessoais'
    aluno = get_object_or_404(Aluno, matricula=matricula)

    if request.user != aluno.get_user():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    initial = {
        'nome_usual': aluno.pessoa_fisica.nome_usual,
        'email_secundario': aluno.email_notificacao,
        'logradouro': aluno.logradouro,
        'numero': aluno.numero,
        'complemento': aluno.complemento,
        'bairro': aluno.bairro,
        'cep': aluno.cep,
        'cidade': aluno.cidade,
        'lattes': aluno.pessoa_fisica.lattes,
        'telefone_principal': aluno.telefone_principal,
        'telefone_secundario': aluno.telefone_secundario,
        'utiliza_transporte_escolar_publico': aluno.poder_publico_responsavel_transporte is not None
        and (aluno.poder_publico_responsavel_transporte and 'Sim' or 'Não')
        or None,
        'poder_publico_responsavel_transporte': aluno.poder_publico_responsavel_transporte,
        'tipo_veiculo': aluno.tipo_veiculo,
        'nis': aluno.nis,
    }
    form = AtualizarDadosPessoaisForm(data=request.POST or None, initial=initial, instance=aluno, pode_realizar_procedimentos=False, request=request)
    if form.is_valid():
        form.save(aluno)
        if renovacao_matricula:
            request.session['dados_atualizados'] = True
            request.session.save()
            if aluno.is_credito():
                url = f'/edu/pedido_matricula_credito/{aluno.pk}/'
            else:
                url = f'/edu/pedido_matricula_seriado/{aluno.pk}/'
            return httprr(url, 'Dados Pessoais atualizados com sucesso.')
        return httprr('..', 'Dados Pessoais atualizados com sucesso.')
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def atualizar_dados_responsavel(request, pk):
    title = 'Atualizar Dados do Responsável'
    aluno = get_object_or_404(Aluno, pk=pk)
    form = EditarDadosResponsavelForm(data=request.POST or None, instance=aluno)
    if form.is_valid():
        form.save()
        return httprr('..', 'Dados alterados com sucesso.')
    return locals()


@permission_required('edu.change_foto_aluno')
@rtr()
def atualizar_foto(request, pk):
    title = 'Atualização de Foto'
    aluno = get_object_or_404(Aluno, pk=pk)
    if request.method == 'POST':
        form = AtualizarFotoForm(data=request.POST or None, files=request.FILES)
    else:
        form = AtualizarFotoForm()
    form.initial.update(aluno=pk)
    if form.is_valid():
        return httprr(aluno.get_absolute_url(), form.processar(request))
    return locals()


@rtr()
@group_required('Aluno')
@login_required()
def locais_aula_aluno(request):
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    return httprr(f'/edu/aluno/{aluno.matricula}/?tab=locais_aula_aluno')


@rtr()
def visualizar_requisitos_conclusao(request, pk, tipo_requisito, tipo_ch, tipo_extensao=None):
    if not request.user.is_authenticated and 'matricula_aluno_como_resposavel' not in request.session:
        raise PermissionDenied
    obj = get_object_or_404(Aluno, pk=pk)
    cumpridos = nao_cumpridos = pendentes = None
    # Verificando o tipo do Requisito
    if tipo_requisito == 'disciplinas_regulares_obrigatorias':
        title = 'Disciplinas Obrigatórias'
        if tipo_ch == 'pendente':
            pendentes = obj.get_componentes_regulares_obrigatorios_pendentes()
        else:
            cumpridos = obj.get_componentes_regulares_obrigatorios_cumpridos()
    elif tipo_requisito == 'disciplinas_regulares_optativas':
        title = 'Disciplinas Optativas'
        if tipo_ch == 'pendente':
            nao_cumpridos = obj.get_componentes_regulares_optativos_nao_cumpridos()
        else:
            cumpridos = obj.get_componentes_regulares_optativos_cumpridos()
            credito_especial = CreditoEspecial.objects.filter(matricula_periodo__in=obj.matriculaperiodo_set.all())
    elif tipo_requisito == 'disciplinas_eletivas':
        title = 'Disciplina Eletivas'
        componentes = obj.get_componentes_eletivos_cumpridos()
    elif tipo_requisito == 'seminario':
        title = 'Disciplinas de Seminário'
        if tipo_ch == 'pendente':
            pendentes = obj.get_componentes_seminario_pendentes()
            nao_cumpridos = obj.get_componentes_seminario_nao_cumpridos().exclude(pk__in=pendentes.values_list('id', flat=True))
        else:
            cumpridos = obj.get_componentes_seminario_cumpridos()
    elif tipo_requisito == 'pratica_como_componente':
        title = 'Prática como Componente Curricular'
        if tipo_ch == 'pendente':
            pendentes = obj.get_componentes_pratica_como_componente_pendentes()
            nao_cumpridos = obj.get_componentes_pratica_como_componente_nao_cumpridos().exclude(pk__in=pendentes.values_list('id', flat=True))
        else:
            cumpridos = obj.get_componentes_pratica_como_componente_cumpridos()
    elif tipo_requisito == 'visita_tecnica':
        title = 'Visita Técnica / Aula de Campo'
        if tipo_ch == 'pendente':
            pendentes = obj.get_componentes_visita_tecnica_pendentes()
            nao_cumpridos = obj.get_componentes_visita_tecnica_nao_cumpridos().exclude(pk__in=pendentes.values_list('id', flat=True))
        else:
            cumpridos = obj.get_componentes_visita_tecnica_cumpridos()
    elif tipo_requisito == 'pratica':
        title = 'Prática Profissional'
        if tipo_ch == 'pendente':
            pendentes = obj.get_componentes_pratica_profissional_pendentes()
            nao_cumpridos = obj.get_componentes_pratica_profissional_nao_cumpridos().exclude(pk__in=pendentes.values_list('id', flat=True))
        else:
            cumpridos = obj.get_componentes_pratica_profissional_cumpridos()
    elif tipo_requisito == 'projeto_final':
        title = 'Disciplinas de TCC'
        if tipo_ch == 'pendente':
            pendentes = obj.get_componentes_tcc_pendentes()
            nao_cumpridos = obj.get_componentes_tcc_nao_cumpridos().exclude(pk__in=pendentes.values_list('id', flat=True))
        else:
            cumpridos = obj.get_componentes_tcc_cumpridos()
    elif tipo_requisito == 'atividades_extensao':
        title = 'Atividades curriculares de extensão'
        if tipo_extensao == 'componentes':
            atividades = obj.get_atividades_extensao_componentes()
        elif tipo_extensao == 'outros_componentes':
            atividades = obj.get_atividades_extensao_outros_componentes()
        elif tipo_extensao == 'outras_atividades':
            atividades = obj.get_atividades_extensao_outras_atividades()

    lista = []
    if cumpridos is not None:
        lista.append({'descricao': 'Componentes Cursados', 'componentes': cumpridos})
    if pendentes is not None:
        lista.append({'descricao': 'Componentes Não-Cursados (Obrigatórios)', 'componentes': pendentes})
    if nao_cumpridos is not None:
        lista.append({'descricao': 'Componentes Não-Cursados (Optativos)', 'componentes': nao_cumpridos})
    return locals()


@login_required()
@rtr()
def meus_dados_academicos(request):
    obj = get_object_or_404(Aluno, matricula=request.user.username)
    return HttpResponseRedirect(obj.get_absolute_url())


@login_required()
@rtr()
def minha_caracterizacao_socioeconomica(request):
    obj = get_object_or_404(Aluno, matricula=request.user.username)
    return HttpResponseRedirect(f'/ae/caracterizacao/{obj.pk}/')


@rtr()
def alterar_matriz_aluno(request, pk_aluno):
    aluno = get_object_or_404(Aluno.objects, pk=pk_aluno)
    if aluno.eh_aluno_minicurso():
        return httprr('..', 'Alunos de curso FIC- (Minicurso) não possuem matriz curricular.', 'error')
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    title = f'Alterar Matriz - {aluno}'
    form = AlterarMatrizAlunoForm(data=request.POST or None, instance=aluno)
    if form.is_valid():
        form.processar(request.user.get_vinculo())
        return httprr('..', 'Matriz alterada com sucesso.')
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def alterar_matriz_lote(request):
    title = 'Alterar Matriz em Lote'
    form = AlterarMatrizLoteForm(data=request.GET or None)
    if form.is_valid():
        alunos = form.processar()
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def alterar_matriz_alunos_selecionados(request):
    if 'alunos_selecionados' in request.POST:
        ids = request.POST.getlist('alunos_selecionados')
        if ids:
            alunos_selecionados = Aluno.locals.filter(id__in=ids)
            return tasks.alterar_matriz_lote(alunos_selecionados, request.POST['matriz_id'], request.POST['motivo'], request.user.get_vinculo())
    else:
        return httprr('/')


@rtr()
def acesso_responsavel(request):
    title = 'Acesso do Responsável'
    category = 'Acessos'
    icon = 'passport'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = AcessoResponsavelForm(request.POST or None)
    if form.is_valid():
        matricula = form.cleaned_data['matricula']
        request.session['matricula_aluno_como_resposavel'] = matricula
        return httprr(f'/edu/aluno/{matricula}/')
    return locals()


@permission_required('edu.add_observacao')
@rtr()
def adicionar_observacao(request, aluno_pk):
    title = ' Adicionar Observação'
    aluno = Aluno.locals.filter(pk=aluno_pk).first()
    if aluno:
        form = ObservacaoForm(aluno, request.user, request.POST or None, instance=None)
        if form.is_valid():
            obj = form.save()
            return httprr('..', 'Observação adicionada com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para modificar os dados deste aluno.', 'error')
    return locals()


@permission_required('edu.change_observacao')
@rtr()
def editar_observacao(request, observacao_pk=None):
    title = ' Editar Observação'
    observacao = Observacao.objects.get(pk=observacao_pk)
    if request.user == observacao.usuario:
        form = ObservacaoForm(observacao.aluno, request.user, request.POST or None, instance=observacao)
        if form.is_valid():
            obj = form.save()
            return httprr('..', 'Observação atualizada com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para modificar a observação de outro usuário.', 'error')
    return locals()


@rtr()
@login_required()
def atualizar_email(request, pk):
    title = 'Atualização do E-mail'
    aluno = Aluno.locals.filter(pk=pk).first()
    if not perms.pode_alterar_email(request, aluno):
        raise PermissionDenied
    form = AtualizarEmailAlunoForm(request.POST or None, request=request, aluno=aluno)
    if form.is_valid():
        form.save()
        return httprr('..', 'E-mail atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_aluno')
@login_required()
def editar_orientacao(request, pk):
    title = 'Editar Orientação'
    aluno = Aluno.locals.filter(pk=pk).first()

    if not perms.pode_editar_orientadores_pos(request, aluno):
        raise PermissionDenied

    form = EditarOrientacaoForm(request.POST or None, instance=aluno)
    if form.is_valid():
        form.save()
        return httprr('..', 'Orientadores atualizados com sucesso.')
    return locals()


@rtr()
def detalhar_matricula_diario_boletim(request, aluno_pk, matricula_diario_pk):
    if not request.user.is_authenticated and 'matricula_aluno_como_resposavel' not in request.session:
        raise PermissionDenied

    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    matricula_diario = get_object_or_404(MatriculaDiario, pk=matricula_diario_pk)
    diario = matricula_diario.diario
    title = f'Notas: {diario.componente_curricular.componente.descricao_historico}'

    pode_ver_dados_academicos = perms.pode_ver_dados_academicos(request, aluno)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)

    if not (pode_ver_dados_academicos or pode_realizar_procedimentos or request.user.has_perm('edu.view_aluno')):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    notas_avaliacoes = NotaAvaliacao.objects.filter(
        matricula_diario_id=matricula_diario.id, matricula_diario__matricula_periodo__aluno_id=aluno.id
    ).order_by('item_configuracao_avaliacao__configuracao_avaliacao__etapa')
    if matricula_diario.diario.estrutura_curso.permite_recuperacao_etapa:
        nota_recuperacao = notas_avaliacoes.filter(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)
        notas_avaliacoes = notas_avaliacoes.exclude(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)

    qtd_avaliacoes = diario.componente_curricular.qtd_avaliacoes
    etapas = list(range(1, qtd_avaliacoes + 1))

    is_lancamento_conceito = aluno.matriz.estrutura.is_lancamento_conceito()
    return locals()


@rtr()
@login_required()
def solicitar_quitacao_nada_consta(request, pk):
    title = 'Solicitar Quitação de Nada Consta'
    aluno = get_object_or_404(Aluno, pk=pk)

    # Check permissions
    emitiu_diploma = RegistroEmissaoDiploma.objects.filter(aluno=aluno, cancelado=False).exists()
    is_responsavel = request.user.is_anonymous and request.session.get('matricula_aluno_como_resposavel') == aluno.matricula

    is_proprio_aluno = aluno.is_user(request)
    tem_permissao_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)

    aluno.checar_registros_nada_consta()
    tem_nada_consta_nao_solicitado = aluno.nadaconsta_set.filter(valido=True, data_solicitacao__isnull=True, quitado__isnull=True).exists()
    pode_solicitar_nada_consta = tem_nada_consta_nao_solicitado and (
        tem_permissao_realizar_procedimentos or (not emitiu_diploma and (is_responsavel or is_proprio_aluno))
    )

    if not pode_solicitar_nada_consta:
        return httprr('..', 'Você não tem permissão para solicitar quitação de nada consta.', 'error')

    form = SolicitarQuitacaoNadaConstaForm(request.POST or None)

    if form.is_valid():
        item_id = request.GET.get('item') or None
        form.processar(aluno, item_id)
        return httprr('..', 'Solicitação de quitação realizada com sucesso.')

    return locals()
