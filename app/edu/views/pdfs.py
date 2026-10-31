import datetime
import io
import math
import os
import tempfile
from itertools import islice
from typing import Any

import magic
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.db.models.aggregates import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from comum.models import Configuracao
from djtools.etiquetas.labels import factory
from djtools.models import Task
from djtools.utils import (
    PDFResponse,
    documento,
    httprr,
    int_to_roman,
    mask_ch_componente,
    merge_pdf_files,
    permission_required,
    rtr,
    running_tests,
)
from edu import tasks
from edu.forms import RelatorioForm
from edu.models import (
    Aluno,
    AssinaturaDigital,
    AssinaturaEletronica,
    Aula,
    CertificadoDiploma,
    ComponenteCurricular,
    ConfiguracaoPedidoMatricula,
    Diario,
    Falta,
    HistoricoEscolarParcial,
    HorarioAulaDiario,
    MatriculaDiario,
    MatriculaPeriodo,
    Matriz,
    Nucleo,
    PedidoMatricula,
    PedidoMatriculaDiario,
    RegistroEmissaoDiploma,
    RotuloModulo,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
)
from rh.models import UnidadeOrganizacional


@login_required
@documento(enumerar_paginas=False)
@rtr()
def comprovante_matricula_pdf(request: HttpRequest, pk: int) -> dict[str, Any] | HttpResponse:
    hoje = datetime.date.today()
    aluno = get_object_or_404(Aluno.locals, pk=pk)
    if not request.user.has_perm('edu.efetuar_matricula') and not request.user.has_group_cached('Estagiário'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.possui_historico():
        return httprr('..', 'Aluno importado. Não possui diários no SUAP.', 'error')

    if aluno.is_concluido():
        return httprr('..', 'Aluno já concluiu, não é possível emitir o comprovante de matrícula.', 'error')

    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    uo = aluno.curso_campus.diretoria.setor.uo
    return locals()


@login_required
@documento('Comprovante de Dados Acadêmicos', validade=30, modelo='edu.aluno', exibe_emissor=True)
@rtr()
def comprovante_dados_academicos_pdf(request, pk):
    hoje = datetime.date.today()
    aluno = get_object_or_404(Aluno.locals, pk=pk)
    if (
        not aluno.is_user(request)
        and not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_group_cached('Estagiário, Pedagogo')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.possui_historico():
        return httprr('.', 'Aluno importado. Não possui diários no SUAP.', 'error')

    uo = aluno.curso_campus.diretoria.setor.uo
    procedimentos = aluno.get_procedimentos_matricula()
    return locals()


def emitir_boletim_pdf(request, pks):
    pks = pks.split('_')
    matriculas_periodo = MatriculaPeriodo.objects.filter(pk__in=pks)

    mp = matriculas_periodo.first()
    if mp is None:
        return httprr('/', 'Boletim não localizado.', 'error')

    if request.user.is_anonymous:
        if not matriculas_periodo.filter(aluno__matricula=request.session.get('matricula_aluno_como_resposavel')).exists():
            return httprr('/', 'Você não tem permissão para acessar está página.', 'error')

    elif not request.user.has_perm('edu.emitir_boletim'):
        if len(pks) != 1 or not mp.aluno.is_user(request):
            return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if matriculas_periodo.count() > 1:
        return tasks.emitir_boletins_pdf(request, matriculas_periodo)
    else:
        return emitir_boletins_aluno_pdf(request, matriculas_periodo)


@documento()
@rtr('emitir_boletim_pdf.html')
def emitir_boletins_aluno_pdf(request: HttpRequest, matriculas_periodo: QuerySet, task: Task | None = None) -> dict[str, Any]:
    title = 'Impressão de Boletim'
    hoje = datetime.date.today()
    site_url = settings.SITE_URL
    matriculas_periodo = matriculas_periodo.order_by('aluno__pessoa_fisica__nome')

    tem_nota_atitudinal = matriculas_periodo[0].utiliza_nota_atitudinal()
    is_lancamento_conceito = matriculas_periodo[0].aluno.matriz.estrutura.is_lancamento_conceito()
    qtd_colunas_etapa = tem_nota_atitudinal and 4 or 2

    uo = matriculas_periodo.exists() and matriculas_periodo.first().aluno.curso_campus.diretoria.setor.uo
    if task:
        task.start_progress(total=matriculas_periodo.count() + 50)
    i = 0
    permite_recuperacao_etapa = False
    for matricula_periodo in matriculas_periodo:
        if matricula_periodo.aluno.get_matriculas_periodo_com_diario():
            matricula_periodo.matriculas_diario = matricula_periodo.matriculadiario_set.all().order_by(
                'diario__componente_curricular__componente__descricao'
            )
            if matricula_periodo.matriculas_diario:
                matricula_periodo.etapa = int(request.GET.get('etapa', 1))
                matricula_periodo.max_qtd_avaliacoes = 1
                for matricula_diario in matricula_periodo.matriculas_diario:
                    # verifica se pelo menos uma estrutura de curso permite recuperação
                    if not permite_recuperacao_etapa:
                        permite_recuperacao_etapa = matricula_diario.diario.estrutura_curso.permite_recuperacao_etapa

                        # adiciona 2 columnas, uma para nota parcial e outra para recuperação
                        if permite_recuperacao_etapa:
                            qtd_colunas_etapa += 2

                    if matricula_diario.diario.componente_curricular.qtd_avaliacoes > matricula_periodo.max_qtd_avaliacoes:
                        matricula_periodo.max_qtd_avaliacoes = matricula_diario.diario.componente_curricular.qtd_avaliacoes
        i += 1
        if task:
            task.update_progress(i)

    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()

    return locals()


@login_required()
@permission_required('edu.emitir_boletins')
@documento()
@rtr('emitir_boletim_diario_pdf.html')
def emitir_boletins_pdf(request, diario_pk):
    hoje = datetime.date.today()
    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    qtd_avaliacoes = diario.componente_curricular.qtd_avaliacoes
    max_qtd_avaliacoes = qtd_avaliacoes
    is_lancamento_conceito = diario.is_lancamento_conceito()
    qtd_colunas_etapa = 2
    uo = diario.turma.curso_campus.diretoria.setor.uo
    matriculas_diario = diario.matriculadiario_set.all().exclude(
        situacao__in=[MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_CANCELADO]
    )
    if not running_tests():
        matriculas_diario = matriculas_diario.order_by('matricula_periodo__aluno__pessoa_fisica__nome')
    title = str(diario)
    exibe_notas = max_qtd_avaliacoes > 0 and diario
    return locals()


@documento()
@login_required()
def emitir_historico_legado_pdf(request, pk):
    if not request.user.has_perm('edu.efetuar_matricula') and not request.user.has_perm('edu.view_registroemissaodiploma'):
        return httprr('/', 'Você não tem permissão para realizar isso.', 'error')
    return emitir_historico_legado(request, pk)


@rtr('emitir_historico_pdf.html')
def emitir_historico_legado(request: HttpRequest, pk: int | str, eletronico: bool = False, qr: Any = None) -> dict[str, Any]:
    historicos = []
    aluno = get_object_or_404(Aluno, pk=pk)
    historicos.append(aluno.get_historico_legado(eletronico=eletronico))
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    cancelado_por_duplicidade = aluno.situacao_id == SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE
    final = aluno.situacao_id in (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO)
    return locals()


@rtr('emitir_historico_pdf.html')
def emitir_historico_pdf(
    request: HttpRequest, pks: int | str, final: bool = False, eletronico: bool = False, qr: Any = None
) -> dict[str, Any] | HttpResponse:
    """Gera o PDF do histórico escolar de um ou mais alunos.

    Verifica permissões do usuário, obtém os dados do histórico via
    :meth:`Aluno.get_historico` e retorna o contexto para renderização do
    template. Alunos PROITEC são redirecionados com erro pois não possuem
    histórico.

    Args:
        request: objeto da requisição HTTP.
        pks: string com PK única ou múltiplas PKs separadas por ``_``.
        final: quando ``True``, gera histórico final (concluído).
        eletronico: quando ``True``, gera histórico eletrônico com assinatura.
        qr: dados do QR code para o histórico eletrônico (opcional).

    Returns:
        ``HttpResponse`` de redirecionamento em caso de erro, ou dicionário
        de contexto para renderização do template de histórico.
    """
    is_proprio_aluno = True
    esconder_assinatura = 'digital' in request.GET
    if not final:
        is_proprio_aluno = get_object_or_404(Aluno.locals, pk=pks).is_user(request)

    if (
        not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_group_cached('Estagiário,Coordenador de Curso, Pedagogo, Professor')
        and not request.user.has_perm('edu.view_registroemissaodiploma')
        and not is_proprio_aluno
    ):
        return httprr('/', 'Você não tem permissão para realizar isso.', 'error')

    historicos = []

    if '_' not in pks:
        aluno = get_object_or_404(Aluno, pk=pks)
        title = str(aluno)
        if aluno.matriz:
            if aluno.matriz.estrutura and aluno.is_proitec():
                return httprr('/', f'Aluno {title} de cursos PROITEC não possuem histórico.', 'error')
        else:
            return httprr('/', f'Aluno {title} não possui matriz associada.', 'error')

        if aluno.possui_historico():
            historicos.append(aluno.get_historico(final, Aluno.ORDENAR_HISTORICO_POR_PERIODO_MATRIZ, eletronico=eletronico))
        else:
            academico_nome_sistema = Configuracao.get_valor_por_chave('comum', 'academico_nome_sistema')
            return httprr('/', f'Aluno {title} não foi matriculado através do SUAP ou não foi migrado do {academico_nome_sistema}.', 'error')
    else:
        alunos = Aluno.objects.filter(pk__in=pks.split('_'))
        count_historicos = alunos.count()
        for aluno in alunos:
            historicos.append(aluno.get_historico(final, Aluno.ORDENAR_HISTORICO_POR_PERIODO_MATRIZ, eletronico=eletronico))

    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    cancelado_por_duplicidade = aluno.situacao_id == SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE
    return locals()


@login_required
@documento('Histórico', validade=30, modelo='edu.aluno', exibe_emissor=True)
def emitir_historico_parcial_pdf(request, pk):
    aluno = get_object_or_404(Aluno.locals, pk=pk)
    if aluno.is_concluido():
        return httprr('/', 'O histórico parcial só pode ser emitido para alunos que não concluíram o curso.', 'error')

    return emitir_historico_pdf(request, pk)


@login_required
@documento(enumerar_paginas=True)
def emitir_historico_final_pdf(request, pks):
    if not Aluno.objects.filter(
        pk__in=pks.split('_'), situacao__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO]
    ).exists():
        return httprr('/', 'Os alunos selecionados ainda não estão formados ou concluídos.', 'error')
    if '_' in pks:
        temp_files = []
        for pk in pks.split('_'):
            response = emitir_historico_final_pdf(request, pk)
            temp = tempfile.NamedTemporaryFile(suffix='.pdf', dir=settings.TEMP_DIR, delete=False)
            temp_files.append(temp.name)
            temp.write(response.content)
            temp.close()
        content = merge_pdf_files(temp_files)
        for temp in temp_files:
            os.remove(temp)
        return HttpResponse(content, content_type='application/pdf')
    else:
        return emitir_historico_pdf(request, pks, final=True)


@rtr('emitir_historico_pdf.html')
def emitir_historico_legado_sica(request: HttpRequest, pk: int | str, eletronico: bool = False, qr: Any = None) -> dict[str, Any]:
    historicos = []
    aluno = get_object_or_404(Aluno, pk=pk)
    historicos.append(aluno.get_historico_legado_sica(eletronico=eletronico))
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    cancelado_por_duplicidade = aluno.situacao_id == SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE
    final = True
    return locals()


@documento(tipo_para_verificacao='Histórico Final', enumerar_paginas=False, pdf_response=False, exibe_emissor=True)
@login_required()
def emitir_historico_final_eletronico_pdf(request, pk, legado=False, qr=None, via=None):
    qs = Aluno.objects.filter(
        pk=pk, situacao__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO]
    )
    qs = qs.filter(Q(curso_campus__assinatura_eletronica=True) | Q(curso_campus__assinatura_digital=True))
    aluno = qs.first()
    if aluno:
        if legado:
            if aluno.is_sica():
                return emitir_historico_legado_sica(request, pk, eletronico=True, qr=qr)
            if aluno.is_qacademico():
                return emitir_historico_legado(request, pk, eletronico=True, qr=qr)
        else:
            return emitir_historico_pdf(request, pk, final=True, eletronico=True, qr=qr)


@documento(tipo_para_verificacao='Histórico Final Ensino Médio Integralizado', enumerar_paginas=False, pdf_response=False, exibe_emissor=True)
@login_required()
def emitir_historico_ensino_medio_integralizado_pdf(request, pk, qr=None):
    aluno = Aluno.objects.filter(pk=pk, integralizou_ensino_medio=True, curso_campus__assinatura_eletronica=True).first()
    if aluno:
        return emitir_historico_pdf(request, pk, final=True, eletronico=True, qr=qr)


@documento()
@rtr('relatorio_impressao_pdf.html')
@login_required()
def relatorio_pdf(request, alunos, filtros, formatacao, campos_exibicao, task):
    title = 'Listagem de Alunos'
    campos_exibicao = campos_exibicao[0:3]
    campos_exibicao_choices = RelatorioForm.EXIBICAO_CHOICES + RelatorioForm.PENDENCIAS_EXIBICAO_CHOICES + RelatorioForm.EXIBICAO_DADOS_PESSOAIS
    if alunos:
        uo = alunos[0].curso_campus.diretoria.setor.uo
    if task:
        task.start_progress(total=alunos.count())
    return locals()


@permission_required('edu.gerar_relatorio')
def etiquetas_alunos_pdf(request, alunos, etiquetas):
    rows = []
    for aluno in alunos:
        matricula = aluno.getattr('matricula', request, justification='')
        nome = aluno.getattr('get_nome_social_composto', request, justification='')
        row = [f'{matricula} - {nome}', '', aluno.curso_campus.descricao_historico, 'Situação: __________________________________']
        rows.append(row)
    labels = factory('Pimaco', etiquetas)
    f = io.BytesIO()
    labels.generate(rows, f)
    f.seek(0)
    return PDFResponse(f.read(), nome='Etiquetas.pdf')


@permission_required('edu.gerar_relatorio')
@documento()
@rtr('assinaturas_alunos_pdf.html')
def assinaturas_alunos_pdf(request, alunos, filtros, agrupamento):
    title = 'Assinatura dos Alunos'
    if alunos:
        uo = alunos[0].curso_campus.diretoria.setor.uo
    return locals()


@permission_required('edu.gerar_relatorio')
@documento()
@rtr('carometros_alunos_pdf.html')
def carometros_alunos_pdf(request, alunos, filtros):
    title = 'Carômetros dos Alunos'
    uo = request.user.get_vinculo().setor.uo
    return locals()


@login_required
@documento('Histórico Parcial Digital', modelo='edu.historicoescolarparcial', pdf_response=False, exibe_emissor=True)
def emitir_historico_parcial_digital_pdf(request, pk, qr=None):
    obj = get_object_or_404(HistoricoEscolarParcial.objects, pk=pk)
    return emitir_historico_pdf(request, str(obj.aluno.pk), qr=qr)


@login_required
@documento('Atestado de Frequência', modelo='edu.aluno', validade=30, enumerar_paginas=False)
@rtr('atestadofrequencia_pdf.html')
def atestado_frequencia_digital(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)
    if not aluno.is_user(request) and not request.user.has_perm('edu.efetuar_matricula') and not request.user.has_group_cached('Estagiário'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    try:
        return atestadofrequencia_pdf(request, aluno, True)
    except ValidationError as e:
        return httprr('..', e.message, 'error')


@login_required
@documento(enumerar_paginas=False)
@rtr('atestadofrequencia_pdf.html')
def atestado_frequencia_fisico(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)
    if not request.user.has_perm('edu.efetuar_matricula') and not request.user.has_group_cached('Estagiário'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    try:
        return atestadofrequencia_pdf(request, aluno, False)
    except ValidationError as e:
        return httprr('..', e.message, 'error')


def atestadofrequencia_pdf(request, aluno, digital):
    eh_masculino = aluno.pessoa_fisica.sexo == 'M'

    if not aluno.possui_historico():
        raise ValidationError('Este aluno não está cursando no Suap.')

    if not aluno.is_matriculado() and not aluno.is_intercambio():
        raise ValidationError('Não é possível emitir a declaração, pois o aluno não está matriculado e nem se encontra em intercâmbio.')

    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno).latest('id')
    if matricula_periodo.situacao.pk != SituacaoMatriculaPeriodo.MATRICULADO:
        raise ValidationError('Não é possível emitir a declaração, pois o aluno não está matriculado em diário no último período.')

    uo = aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()

    # Verificando se o aluno possui faltou consecutivamente nos últimos 30 dias.
    data_mes_anterior = hoje + datetime.timedelta(days=-30)
    aulas = Aula.objects.filter(
        professor_diario__diario__matriculadiario__matricula_periodo__aluno=aluno,
        data__range=(data_mes_anterior, hoje),
        registro_frequencia_confirmado=True,
    )
    faltas = (
        Falta.objects.filter(contabilizar=True)
        .filter(matricula_diario__matricula_periodo__aluno=aluno, aula__in=aulas.values_list('pk', flat=True))
        .distinct()
    )

    if aulas.exists() and faltas.count() == aulas.count():
        raise ValidationError('Não é possível emitir o atestado, pois o aluno possui 30 dias consecutivos de faltas.')

    return locals()


@login_required
@documento('Declaração de Vínculo Discente', False, validade=30, enumerar_paginas=False, modelo='edu.aluno', exibe_emissor=True)
@rtr('declaracaovinculo_pdf.html')
def declaracaovinculo_pdf(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)
    situacao = aluno.situacao
    pode_ver_dados_sociais = request.user.has_group_cached('Assistente Social, Coordenador de Atividades Estudantis Sistêmico, Auditor')
    is_usuario_proprio_aluno = aluno.is_user(request)
    if (
        not is_usuario_proprio_aluno
        and not pode_ver_dados_sociais
        and not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_group_cached('Estagiário, Pedagogo, Coordenador de Curso')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    matricula_periodo = aluno.get_ultima_matricula_periodo()
    uo = aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    return locals()


@login_required
@documento('Certificado de Conclusão de Módulo', enumerar_paginas=False, modelo='edu.aluno', exibe_emissor=True)
@rtr('declaracao_certificacao_parcial_pdf.html')
def declaracao_certificacao_parcial_pdf(request, pk, modulo):
    obj = get_object_or_404(Aluno, pk=pk)
    uo = obj.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    componentes = ComponenteCurricular.objects.filter(matriz_id=obj.matriz_id, tipo_modulo=modulo).order_by('id')
    ids_cc = componentes.values_list('id', flat=True)
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
    rotulo = f'módulo {int_to_roman(modulo)}'
    rotulo_modulo = RotuloModulo.objects.filter(matriz_id=obj.matriz_id, tipo_modulo=modulo).first()
    if rotulo_modulo:
        rotulo = f'{rotulo} - {rotulo_modulo.descricao}'
    if list(ids_cc) != list(ids_md):
        return httprr('..', f'O aluno {obj} não concluiu todas as disciplinas do {rotulo}.', 'error')
    total_ch = mask_ch_componente(componentes.aggregate(Sum('componente__ch_hora_relogio'))['componente__ch_hora_relogio__sum'])
    return locals()


@login_required
@documento('Declaração de Matrícula', False, validade=30, enumerar_paginas=False, modelo='edu.aluno', exibe_emissor=True)
@rtr()
def declaracaomatricula_pdf(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)
    situacao = aluno.situacao
    exibir_modalidade = 'Técnico' in aluno.curso_campus.modalidade.descricao
    eh_masculino = aluno.pessoa_fisica.sexo == 'M'
    pode_ver_dados_sociais = request.user.has_group_cached('Assistente Social, Coordenador de Atividades Estudantis Sistêmico, Auditor')
    is_usuario_proprio_aluno = aluno.is_user(request)
    if (
        not is_usuario_proprio_aluno
        and not pode_ver_dados_sociais
        and not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_group_cached('Estagiário, Pedagogo, Coordenador de Curso')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.possui_historico():
        return httprr('.', 'Aluno importado. Não possui diários no SUAP.', 'error')

    if not aluno.is_matriculado() and not aluno.is_intercambio():
        return httprr('..', 'Não é possível emitir a declaração, pois o aluno não está matriculado e também não está em intercâmbio.', 'error')

    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno).latest('id')
    uo = aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    polo = aluno.polo
    return locals()


@login_required
@documento('Declaração de Carga Horária Cumprida', False, validade=30, enumerar_paginas=False, modelo='edu.aluno', exibe_emissor=True)
@rtr()
def declaracao_ch_cumprida_pdf(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)
    sexo_aluno = aluno.pessoa_fisica.sexo == 'M' and 'o' or 'a'
    is_usuario_proprio_aluno = aluno.is_user(request)
    if (
        not is_usuario_proprio_aluno
        and not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_group_cached('Estagiário, Pedagogo, Coordenador de Curso')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.possui_historico():
        return httprr('.', 'Aluno importado. Não possui diários no SUAP.', 'error')

    if not aluno.is_matriculado() and not aluno.is_intercambio():
        return httprr('..', 'Não é possível emitir a declaração, pois o aluno não está matriculado e também não está em intercâmbio.', 'error')

    uo = aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    return locals()


@login_required
@documento('Declaração de Horários de Aula', False, validade=30, enumerar_paginas=False, modelo='edu.aluno', exibe_emissor=True)
@rtr()
def declaracao_horarios_aula_pdf(request, pk):
    aluno = get_object_or_404(Aluno, pk=pk)

    is_usuario_proprio_aluno = aluno.is_user(request)
    if (
        not is_usuario_proprio_aluno
        and not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_group_cached('Estagiário, Pedagogo, Coordenador de Curso')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.possui_historico():
        return httprr('.', 'Aluno importado. Não possui diários no SUAP.', 'error')

    mp = aluno.get_ultima_matricula_periodo(excluir_em_aberto=True)
    if mp is None:
        return httprr('..', 'Não foi possível localizar a última matrícula do aluno.', 'error')

    uo = aluno.curso_campus.diretoria.setor.uo
    turnos = mp.get_horarios_aula_atividade_por_turno()
    sexo_aluno = aluno.pessoa_fisica.sexo == 'M' and 'o' or 'a'
    return locals()


@permission_required('edu.view_matriz')
@documento()
@rtr()
def imprimir_matriz(request, pk):
    obj = get_object_or_404(Matriz, pk=pk)
    componentes_curriculares = obj.componentecurricular_set.all()
    periodos = list(range(1, obj.qtd_periodos_letivos + 1))
    title = str(obj)
    uo = request.user.get_vinculo().setor.uo
    return locals()


@permission_required('edu.view_matriz')
@documento()
@rtr()
def imprimir_ch_matriz(request, pk):
    obj = get_object_or_404(Matriz, pk=pk)
    qtd_semestre = 2 * obj.qtd_periodos_letivos
    periodos = list(range(1, obj.qtd_periodos_letivos + 1))
    title = str(obj)
    uo = request.user.get_vinculo().setor.uo

    nucleos_componentes_obrigatorios = Nucleo.objects.filter(
        componentecurricular__matriz=obj, componentecurricular__in=obj.get_componentes_curriculares_regulares_obrigatorios()
    ).distinct()
    for nucleo in nucleos_componentes_obrigatorios:
        nucleo.componentes_regulares = obj.get_componentes_curriculares_regulares_obrigatorios().filter(nucleo=nucleo)
        nucleo.subtotal = []
        for periodo_letivo in periodos:
            nucleo.subtotal.append(obj.get_qtd_credito_componentes_obrigatorios(nucleo=nucleo, periodo_letivo=periodo_letivo))
        nucleo.subtotal.append(obj.get_ch_componentes_obrigatorios(nucleo=nucleo, relogio=False))
        nucleo.subtotal.append(obj.get_ch_componentes_obrigatorios(nucleo=nucleo))
        nucleo.total = []
        for periodo_letivo in periodos:
            nucleo.total.append(obj.get_qtd_credito_componentes_obrigatorios(periodo_letivo=periodo_letivo))
        nucleo.total.append(obj.get_ch_componentes_obrigatorios(relogio=False))
        nucleo.total.append(obj.get_ch_componentes_obrigatorios())

    nucleos_componentes_optativos = Nucleo.objects.filter(
        componentecurricular__matriz=obj, componentecurricular__in=obj.get_componentes_curriculares_optativos()
    ).distinct()
    for nucleo in nucleos_componentes_optativos:
        nucleo.componentes_optativos = obj.get_componentes_curriculares_optativos().filter(nucleo=nucleo)
        nucleo.subtotal = []
        nucleo.subtotal.append(obj.get_qtd_credito_componentes_optativos(nucleo=nucleo))
        nucleo.subtotal.append(obj.get_ch_componentes_optativos(nucleo=nucleo, relogio=False))
        nucleo.subtotal.append(obj.get_ch_componentes_optativos(nucleo=nucleo))
        nucleo.total = []
        nucleo.total.append(obj.get_qtd_credito_componentes_optativos())
        nucleo.total.append(obj.get_ch_componentes_optativos(relogio=False))
        nucleo.total.append(obj.get_ch_componentes_optativos())

    nucleos_componentes_seminarios = Nucleo.objects.filter(
        componentecurricular__matriz=obj, componentecurricular__in=obj.get_componentes_curriculares_seminario()
    ).distinct()
    for nucleo in nucleos_componentes_seminarios:
        nucleo.componentes_seminarios = obj.get_componentes_curriculares_seminario().filter(nucleo=nucleo)
        nucleo.subtotal = []
        for periodo_letivo in periodos:
            nucleo.subtotal.append(obj.get_qtd_credito_componentes_seminarios(nucleo=nucleo, periodo_letivo=periodo_letivo))
        nucleo.subtotal.append(obj.get_ch_componentes_seminario(nucleo=nucleo, relogio=False))
        nucleo.subtotal.append(obj.get_ch_componentes_seminario(nucleo=nucleo))
        nucleo.total = []
        for periodo_letivo in periodos:
            nucleo.total.append(obj.get_qtd_credito_componentes_seminarios(periodo_letivo=periodo_letivo))
        nucleo.total.append(obj.get_ch_componentes_seminario(relogio=False))
        nucleo.total.append(obj.get_ch_componentes_seminario())

    nucleos_componentes_pratica_profissional = Nucleo.objects.filter(
        componentecurricular__matriz=obj, componentecurricular__in=obj.get_componentes_curriculares_pratica_profissional()
    ).distinct()
    for nucleo in nucleos_componentes_pratica_profissional:
        nucleo.componentes_seminarios = obj.get_componentes_curriculares_pratica_profissional().filter(nucleo=nucleo)
        nucleo.subtotal = []
        for periodo_letivo in periodos:
            nucleo.subtotal.append(obj.get_qtd_credito_componentes_pratica_profissional(nucleo=nucleo, periodo_letivo=periodo_letivo))
        nucleo.subtotal.append(obj.get_ch_componentes_pratica_profissional(nucleo=nucleo, relogio=False))
        nucleo.subtotal.append(obj.get_ch_componentes_pratica_profissional(nucleo=nucleo))
        nucleo.total = []
        for periodo_letivo in periodos:
            nucleo.total.append(obj.get_qtd_credito_componentes_pratica_profissional(periodo_letivo=periodo_letivo))
        nucleo.total.append(obj.get_ch_componentes_pratica_profissional(relogio=False))
        nucleo.total.append(obj.get_ch_componentes_pratica_profissional())

    creditos_totais = []
    for periodo_letivo in periodos:
        creditos_totais.append(
            obj.get_qtd_credito_componentes_obrigatorios(periodo_letivo=periodo_letivo)
            + obj.get_qtd_credito_componentes_seminarios(periodo_letivo=periodo_letivo)
            + obj.get_qtd_credito_componentes_pratica_profissional(periodo_letivo=periodo_letivo)
        )
    creditos_totais.append(obj.ch_atividades_complementares)
    creditos_totais.append(
        obj.get_ch_componentes_obrigatorios(relogio=False)
        + obj.get_ch_componentes_seminario(relogio=False)
        + obj.get_ch_componentes_pratica_profissional(relogio=False)
    )
    creditos_totais.append(
        obj.ch_componentes_optativos
        + obj.get_ch_componentes_obrigatorios()
        + obj.get_ch_componentes_seminario()
        + obj.get_ch_componentes_pratica_profissional()
    )
    return locals()


@permission_required('edu.emitir_boletins')
@documento()
@rtr('relacao_alunos_pdf.html')
def relacao_alunos_pdf(request: HttpRequest, diario_pk: int) -> dict[str, Any]:
    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    situacoes_inativas = [MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_CANCELADO]
    matriculas_diario = diario.matriculadiario_set.exclude(situacao__in=situacoes_inativas)
    if not running_tests():
        matriculas_diario = matriculas_diario.order_by('matricula_periodo__aluno__pessoa_fisica__nome')
    uo = diario.turma.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


@permission_required('comum.is_professor')
@documento()
@rtr()
def relacao_alunos_emails_pdf(request: HttpRequest, diario_pk: int) -> dict[str, Any]:
    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    if not diario.is_professor_diario(request.user):
        raise PermissionDenied
    situacoes_inativas = [MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_CANCELADO]
    matriculas_diario = diario.matriculadiario_set.exclude(situacao__in=situacoes_inativas).order_by('matricula_periodo__aluno__pessoa_fisica__nome')
    uo = diario.turma.curso_campus.diretoria.setor.uo
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


@permission_required('edu.emitir_boletins')
@documento()
@rtr('diario_pdf.html')
def diario_pdf(request, pk, etapa):
    diarios = []
    etapa = int(etapa)
    diario = get_object_or_404(Diario, pk=pk)
    etapas = etapa and [etapa] or ([*list(range(1, diario.componente_curricular.qtd_avaliacoes + 1)), 5])
    uo = diario.turma.curso_campus.diretoria.setor.uo
    orientation = 'portrait'
    hoje = datetime.date.today()

    for i, etapa in enumerate(etapas):
        if i != 0:
            diario = get_object_or_404(Diario, pk=pk)
        diario.hoje = hoje
        diario.uo = uo
        diario.etapa = etapa
        diario.aula = Aula(quantidade=' ', data=' ', conteudo=' ')
        diario.aulas = list(diario.get_aulas(etapa).order_by('data'))
        diario.datas_aulas = {}
        diario.faltas = Falta.objects.filter(aula__professor_diario__diario_id=diario.id, aula__etapa=etapa)
        diario.map = {}
        # criando cache de número de faltas por data e aluno
        for falta in diario.faltas:
            key = f'{falta.aula.data};{falta.matricula_diario_id}'
            if key in diario.map:
                diario.map[key] += falta.quantidade
            else:
                diario.map[key] = falta.quantidade

        diario.matriculas_diario = diario.matriculadiario_set.all().exclude(
            situacao__in=[MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_CANCELADO]
        )
        if not running_tests():
            diario.matriculas_diario = diario.matriculas_diario.order_by('matricula_periodo__aluno__pessoa_fisica__nome')

        diario.etapa_s = 'final' if int(diario.etapa) == 5 else diario.etapa

        for i, matricula_diario in enumerate(diario.matriculas_diario):
            matricula_diario.nota = getattr(matricula_diario, f'nota_{diario.etapa_s}')
            if diario.is_lancamento_conceito():
                matricula_diario.nota = diario.estrutura_curso.get_conceito(matricula_diario.nota)
            matricula_diario.faltas = []
            matricula_diario.total = 0
            datas_verificadas = []
            for contador, aula in enumerate(diario.aulas):
                # adicionando as datas das aulas sem repetição com a respectiva quantidade
                if i == 0:
                    if aula.data not in diario.datas_aulas:
                        diario.datas_aulas[aula.data] = aula.quantidade
                    else:
                        diario.datas_aulas[aula.data] += aula.quantidade
                # calculando o número de faltas em uma data
                if aula.data not in datas_verificadas:
                    key = f'{aula.data};{matricula_diario.id}'
                    quantidade = key in diario.map and diario.map[key]
                    matricula_diario.total += quantidade
                    if not quantidade and contador < len(diario.get_aulas(diario.etapa)):
                        quantidade = '-'
                    matricula_diario.faltas.append(quantidade or '')
                datas_verificadas.append(aula.data)
        diarios.append(diario)

        diario.total_paginas = math.ceil(float(len(diario.aulas)) / 25)
        total_aulas = len(diario.aulas)
        diario.pagina = []
        diario.pagina_faltas = {}
        paginacao = list(range(diario.total_paginas))

        if diario.total_paginas > 1:
            for matricula_diario in diario.matriculas_diario:
                start_item = 0
                end_item = 25
                for n in range(diario.total_paginas):
                    diario.pagina_faltas[str(matricula_diario.matricula_periodo.aluno.id) + f'pag0{n + 1}'] = matricula_diario.faltas[
                        start_item:end_item
                    ]
                    start_item += 25

                    if total_aulas < (start_item + 25):
                        end_item = total_aulas
                    else:
                        end_item = start_item + 25

            # reinicia as variáveis de controle de paginação
            start_item = 0
            end_item = 25
            # este segundo for não poder ser feito juntamente com o primeiro, pois o primeiro irá percorrer todas as matrículas e este segundo, irá percorrer os dias de aula
            for _ in range(diario.total_paginas):
                diario.pagina.append(dict(islice(diario.datas_aulas.items(), start_item, end_item)))
                start_item += 25
                if total_aulas < (start_item + 25):
                    end_item = total_aulas
                else:
                    end_item = start_item + 25

        if orientation == 'portrait' and len(diario.aulas) > 17:
            orientation = 'landscape'
    return locals()


@documento(enumerar_paginas=False)
@rtr('registroemissaodiploma_pdf.html')
@permission_required('edu.view_registroemissaodiploma')
def registroemissaodiploma_pdf(request: HttpRequest, pk: int) -> dict[str, Any]:
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk, data_expedicao__isnull=False)
    objs = [obj]
    esconder_assinatura = 'digital' in request.GET
    uo = obj.aluno.curso_campus.diretoria.setor.uo
    if not obj.aluno.matriz_id:
        if 'sica' in settings.INSTALLED_APPS and obj.aluno.historico_set.exists():
            uo = UnidadeOrganizacional.objects.suap().get(pk=1)
    cra = obj.get_coordenador_registro_academico()
    hoje = datetime.datetime.now()
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    credenciamento = (Configuracao.get_valor_por_chave('edu', 'credenciamento'),)
    recredenciamento = Configuracao.get_valor_por_chave('edu', 'recredenciamento')
    return locals()


@documento()
@rtr('registroemissaodiploma_pdf.html')
@permission_required('edu.view_registroemissaodiploma')
def registrosemissaodiploma_pdf(request, pks):
    objs = RegistroEmissaoDiploma.objects.filter(pk__in=pks.split('_'))
    if objs.exists():
        uo = objs[0].aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    return locals()


@documento('Diploma/Certificado', pdf_response=False, modelo='edu.registroemissaodiploma', exibe_emissor=True)
@rtr('registroemissaodiploma_pdf.html')
@permission_required(['edu.change_registroemissaodiploma', 'edu.view_assinaturaeletronica'])
def gerar_autenticacao_diploma_pdf(request, pk):
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    objs = [obj]
    uo = obj.aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.datetime.now()
    esconder_assinatura = True
    return locals()


def baixar_pdf_representacao_visual(request, pk, token=None):
    obj = get_object_or_404(AssinaturaDigital, pk=pk)
    if not obj.validar_token_download(request.user, token):
        return httprr('/', 'Token inválido.', 'error')
    try:
        return obj.baixar_pdf_representacao_visual()
    except Exception as e:
        return httprr('..', str(e), 'error')


def baixar_pdf_diploma_eletronico(request, pk, token=None):
    obj = get_object_or_404(AssinaturaEletronica, pk=pk)
    if not obj.validar_token_download(request.user, token):
        return httprr('/', 'Token inválido.', 'error')
    try:
        mime = magic.Magic(mime=True)
        with obj.diploma.open('rb') as f:
            content = f.read()
        content_type = mime.from_buffer(content)
        response = HttpResponse(content, content_type=content_type)
        _file_name, file_extension = os.path.splitext(obj.diploma.name)
        response['Content-Disposition'] = f'inline; filename=RepresentacaoVisual{file_extension}'
        return response
    except Exception as e:
        return httprr('..', str(e), 'error')


@documento()
@login_required()
@rtr('comprovante_pedido_matricula_pdf.html')
def comprovante_pedido_matricula_pdf(request, pk):
    hoje = datetime.datetime.now()
    obj = get_object_or_404(PedidoMatricula, pk=pk)
    aluno = obj.matricula_periodo.aluno
    uo = aluno.curso_campus.diretoria.setor.uo

    # horarios
    dias_semana = HorarioAulaDiario.get_dias_semana_seg_a_sex()
    turnos = obj.get_turnos_horarios()

    pedidos_diario_turma = obj.pedidomatriculadiario_set.filter(diario__turma=obj.turma)
    pedidos_diario_dependencias = obj.pedidomatriculadiario_set.exclude(diario__turma=obj.turma)
    return locals()


@documento()
@login_required()
@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def imprimir_pedidos_diarios_pdf(request: HttpRequest, pk_configuracao: int) -> dict[str, Any]:
    configuracao = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk_configuracao)
    uo = configuracao.cursos.all()[0].diretoria.setor.uo
    quantitativos_diario = configuracao.get_diarios_quantitativos()
    quantitativo_diarios_alunos = []
    for quantitativo_diario in quantitativos_diario:
        diario_pk = quantitativo_diario[10]
        pedidos_alunos_diario = PedidoMatriculaDiario.objects.filter(
            diario__pk=diario_pk, pedido_matricula__configuracao_pedido_matricula__pk=pk_configuracao
        ).order_by('pedido_matricula__matricula_periodo__aluno__pessoa_fisica__nome')
        quantitativo_diario.append(pedidos_alunos_diario)
        quantitativo_diarios_alunos.append(quantitativo_diario)
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


@login_required()
@documento('Certificado de Conclusão', False, validade=120, enumerar_paginas=False, modelo='edu.certificadodiploma', exibe_emissor=True)
@rtr()
def certificado_diploma_pdf(request, pk):
    hoje = datetime.date.today()
    obj = get_object_or_404(CertificadoDiploma, pk=pk)
    uo = obj.aluno.curso_campus.diretoria.setor.uo
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    return locals()


@documento()
@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def imprimir_pedido_diario_pdf(request, pk_configuracao, pk_diario):
    configuracao = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk_configuracao)
    quantitativos_diario = configuracao.get_diarios_quantitativos(pk_diario)
    pedidos_alunos_diario = PedidoMatriculaDiario.objects.filter(
        diario__id=pk_diario, pedido_matricula__configuracao_pedido_matricula__pk=pk_configuracao
    ).order_by('pedido_matricula__matricula_periodo__aluno__pessoa_fisica__nome')
    if pedidos_alunos_diario.exists():
        uo = pedidos_alunos_diario[0].diario.turma.curso_campus.diretoria.setor.uo
    return locals()


@documento()
@login_required()
@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def imprimir_pedidos_alunos_pdf(request: HttpRequest, pk_configuracao: int) -> dict[str, Any]:
    configuracao = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk_configuracao)
    uo = configuracao.cursos.all()[0].diretoria.setor.uo
    pedidos_matriculas_periodos = (
        MatriculaPeriodo.objects.filter(pedidomatricula__configuracao_pedido_matricula=configuracao).distinct().order_by('aluno__pessoa_fisica__nome')
    )
    pedidos_alunos_diarios = []
    for matricula_periodo in pedidos_matriculas_periodos:
        pedidos_alunos = []
        pedidos_alunos.append(matricula_periodo)
        pedidos_diarios_aluno = PedidoMatriculaDiario.objects.filter(
            pedido_matricula__matricula_periodo=matricula_periodo, pedido_matricula__configuracao_pedido_matricula__pk=pk_configuracao
        ).order_by('diario__componente_curricular__componente__descricao')
        pedidos_alunos.append(pedidos_diarios_aluno)
        pedidos_alunos_diarios.append(pedidos_alunos)

    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()

    return locals()
