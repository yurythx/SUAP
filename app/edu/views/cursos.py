import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from djtools.templatetags.filters import format_
from djtools.utils import (
    XlsResponse,
    group_required,
    httprr,
    permission_required,
    rtr,
)
from djtools.middleware.threadlocals import set_ano_letivo
from edu import tasks
from edu.forms import (
    AtoRegulatorioCursoCampusForm,
    ComponenteCurricularForm,
    ConfiguracaoCertificacaoParcialForm,
    DataFuncionamentoCursoCampusForm,
    EditarAbreviaturaComponenteForm,
    EditarDiretoriaCurso,
    EditarLegislacaoForm,
    ImportarComponentesForm,
    ImportarComponentesMatrizForm,
    InserirDiretoriaForm,
    MatrizCursoForm,
    ReplicacaoCursoCampusForm,
    ReplicacaoMatrizForm,
    RequisitosComponenteCurricularForm,
    TramitacaoProcessoEMECForm,
    VincularComponenteCurricularConfiguracaoCertificacaoParcialForm,
    VincularModuloConfiguracaoCertificacaoParcialForm,
    RelatorioDisciplinasEADForm,
)
from edu.models import (
    Aluno,
    AtoRegulatorioCurso,
    ClassificacaoComplementarComponenteCurricular,
    Componente,
    ComponenteCurricular,
    ConfiguracaoCertificacaoParcial,
    ComponenteCurricularCertificacaoParcial,
    CursoCampus,
    EstruturaCurso,
    Log,
    MatriculaDiario,
    Matriz,
    MatrizCurso,
    SituacaoMatricula,
    TramitacaoProcessoEMEC,
)


@permission_required('edu.view_cursocampus')
@rtr()
def cursocampus(request, pk):
    obj = get_object_or_404(CursoCampus, pk=pk)
    if obj.is_minicurso():
        return httprr(f'/edu/minicurso/{obj.pk}/')

    title = str(obj)
    is_avaliador_regulador = request.user.has_group_cached('Diretor de Avaliação e Regulação do Ensino')
    possui_estagio_docente = obj.is_licenciatura()
    pode_definir_coordenador_estagio_docente = possui_estagio_docente and request.user.has_group_cached(
        'Secretário Acadêmico,Coordenador de Curso,Diretor Acadêmico,Administrador Acadêmico'
    )

    if obj.suspenso:
        ato_suspensao = obj.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_SUSPENSAO).last()

    pendente_homologacao_ato = obj.atoregulatoriocurso_set.filter(ad_referendum=True, ato_homologador__isnull=True).exists()

    tab = request.GET.get('tab', '')
    if tab == 'matrizes':
        pode_visualizar_estatistica = request.user.has_group_cached(
            'Secretário Acadêmico,Coordenador de Curso,Diretor Acadêmico,Administrador Acadêmico,Pedagogo'
        )
        pode_migrar_aluno = request.user.has_perm('edu.add_matriz') and obj.aluno_set.filter(matriz__isnull=True).exists()
        matrizes_curso = obj.matrizcurso_set.all().order_by('-matriz__ativo', '-matriz__ano_criacao')
        alerta_matriz_modular = (
            obj.periodicidade != CursoCampus.PERIODICIDADE_LIVRE
            and obj.matrizcurso_set.filter(matriz__estrutura__tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_MODULAR).exists()
        )

    elif tab == 'coordenacao':
        logs = (
            Log.objects.filter(
                modelo='CursoCampus', ref=pk, registrodiferenca__campo__in=['Coordenador', 'Vice-Coordenador', 'Coordenador substituto']
            )
            .order_by('-pk')
            .values_list('dt', 'registrodiferenca__valor_anterior', 'registrodiferenca__valor_atual', 'registrodiferenca__campo')
        )

    elif tab == 'reconhecimento':
        pode_solicitar_reconhecimento = obj.pode_solicitar_reconhecimento(request.user)
        processo = obj.get_tramitacao_processo_emec()

    elif tab == 'atos':
        atos = obj.atoregulatoriocurso_set.exclude(ad_referendum=False, atoregulatoriocurso__isnull=False).order_by('-data')
    return locals()


@permission_required('edu.change_cursocampus')
@rtr()
def replicar_cursocampus(request, pk):
    title = 'Replicação de Curso'
    curso_campus = get_object_or_404(CursoCampus.locals, pk=pk)
    form = ReplicacaoCursoCampusForm(data=request.POST or None, curso_campus=curso_campus)
    if request.POST and form.is_valid():
        try:
            resultado = form.processar(curso_campus)
            return httprr('..', mark_safe(f'Curso replicado com sucesso. <a href="/admin/edu/cursocampus/{resultado.pk}/">Você deseja editá-lo?</a>'))
        except ValidationError as e:
            return httprr('..', f'Não foi possível replicar o curso: {e.messages[0]}', 'error')
    return locals()


@permission_required('edu.add_atoregulatoriocurso')
@rtr()
def editar_funcionamento_cursocampus(request, pk):
    title = 'Editar datas de funcionamento'
    curso_campus = CursoCampus.objects.get(pk=pk)
    form = DataFuncionamentoCursoCampusForm(request.POST or None, instance=curso_campus)
    if form.is_valid():
        try:
            form.save()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Datas de funcionamento atualizadas com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_atoregulatoriocurso')
@rtr()
def adicionar_atoregulatorio_cursocampus(request, pk, ato_ad_referendum_pk=None):
    title = 'Adicionar ato regulatório de curso'
    if ato_ad_referendum_pk:
        title = 'Adicionar homologação de ato regulatório de curso'

    form = AtoRegulatorioCursoCampusForm(request.POST or None, files=request.FILES or None, curso_id=pk, ato_ad_referendum_pk=ato_ad_referendum_pk)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Ato regulatório adicionado com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_atoregulatoriocurso')
@rtr()
def adicionar_tramitacaoprocessoemec_cursocampus(request, pk):
    title = 'Adicionar tramitação de processo e-MEC'
    form = TramitacaoProcessoEMECForm(request.POST or None, curso_id=pk)
    if form.is_valid():
        try:
            form.save()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Tramitação de processo e-MEC adicionada com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_atoregulatoriocurso')
@rtr()
def editar_atoregulatoriocurso(request, pk):
    title = 'Editar ato regulatório de curso'
    ato = AtoRegulatorioCurso.objects.get(id=pk)
    form = AtoRegulatorioCursoCampusForm(request.POST or None, files=request.FILES or None, instance=ato)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Ato regulatório atualizado com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.view_atoregulatoriocurso')
@rtr()
def atoregulatoriocurso(request, pk):
    ato = AtoRegulatorioCurso.objects.get(id=pk)
    title = ato.get_tipo_display()
    doc_eletronico = AtoRegulatorioCurso.get_documento(ato.id_documento)
    ato_ad_referendum = ato.atoregulatoriocurso_set.first()
    return locals()


@permission_required('edu.add_atoregulatoriocurso')
@rtr()
def editar_tramitacaoprocessoemec(request, pk):
    title = 'Editar tramitação de processo e-MEC'
    processo = TramitacaoProcessoEMEC.objects.get(id=pk)
    form = TramitacaoProcessoEMECForm(request.POST or None, instance=processo)
    if form.is_valid():
        try:
            form.save()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Tramitação de processo e-MEC atualizada com sucesso.', close_popup=True)
    return locals()


@group_required('Diretor de Avaliação e Regulação do Ensino')
@rtr()
def editar_legislacao_matriz(request, pk):
    obj = get_object_or_404(MatrizCurso, pk=pk)
    title = str(obj.matriz.descricao)
    form = EditarLegislacaoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Edição realizada com sucesso.')
    return locals()


@permission_required('edu.view_matriz')
@rtr()
def matriz(request, pk):
    obj = get_object_or_404(Matriz, pk=pk)
    title = str(obj)
    matrizppc = obj.get_matrizppc()
    pode_ser_editada = obj.pode_ser_editada(request.user)
    pode_editar_matriz = obj.can_change(request.user)
    alerta_edicao = pode_editar_matriz and Configuracao.get_valor_por_chave('edu', 'editar_matriz_alunos_concluidos') and obj.tem_aluno_concluido()
    is_avaliador_regulador = request.user.has_group_cached('Diretor de Avaliação e Regulação do Ensino')
    possui_certificacao_parcial = obj.configuracaocertificacaoparcial_set.exists()
    exibe_certificacao_parcial = obj.emite_certificacao_parcial or possui_certificacao_parcial

    tab = request.GET.get('tab', '')
    if tab == 'modulos':
        rotulos_modulo = obj.rotulomodulo_set.all()

    elif tab == 'componentes':
        exibir_classificacao_complementar = ClassificacaoComplementarComponenteCurricular.objects.exists()

    elif tab == 'cursos_alunos':
        alerta_matriz_modular = (
            obj.is_regime_modular() and obj.matrizcurso_set.exclude(curso_campus__periodicidade=CursoCampus.PERIODICIDADE_LIVRE).exists()
        )

    elif tab == 'certificacao':
        certificacoes = obj.configuracaocertificacaoparcial_set.all()

    if tab in ['componentes', 'pre_requisitos']:
        componentes_curriculares = obj.componentecurricular_set.select_related('nucleo', 'componente')

    if 'xls' in request.GET:
        rows = [
            [
                '#',
                'Período',
                'Sigla',
                'Componente',
                'Tipo',
                'Optativo',
                'Qtd. Avaliações',
                'Núcleo',
                'CH Componente',
                'CH Teórica',
                'CH Prática',
                'Pré-Requisitos',
                'Co-Requisitos',
                'Classificação Complementar',
            ]
        ]
        count = 0
        for componente_curricular in obj.componentecurricular_set.all():
            count += 1
            if componente_curricular.optativo:
                optativo = 'Sim'
            else:
                optativo = 'Não'
            ch_componente = f'CH Relógio: {componente_curricular.componente.get_ch_hora_relogio()}, CH Aula: {componente_curricular.componente.get_ch_hora_aula()}'
            row = [
                count,
                format_(componente_curricular.periodo_letivo),
                format_(componente_curricular.componente.sigla),
                format_(f'{componente_curricular.componente.id} - {componente_curricular.componente.descricao}'),
                format_(componente_curricular.get_tipo_display()),
                format_(optativo),
                format_(componente_curricular.qtd_avaliacoes),
                format_(componente_curricular.nucleo),
                format_(ch_componente),
                format_(componente_curricular.get_ch_presencial()),
                format_(componente_curricular.get_ch_pratica()),
                format_(', '.join(componente_curricular.pre_requisitos.all().values_list('componente__descricao', flat=True))),
                format_(', '.join(componente_curricular.co_requisitos.all().values_list('componente__descricao', flat=True))),
                format_(componente_curricular.classificacao_complementar),
            ]
            rows.append(row)
        return XlsResponse(rows)
    return locals()


def delete_componentes_certificacaoparcial_modulo(self, configuracao_certificacao_parcial_id, tipo_modulo):
    ComponenteCurricularCertificacaoParcial.objects.filter(
        configuracao_certificacao_parcial=configuracao_certificacao_parcial_id,
        componente_curricular__tipo_modulo=tipo_modulo,
    ).delete()
    return httprr('.', 'Módulo desvinculado com sucesso.', close_popup=True)


@login_required()
@rtr()
def grade_curricular_matriz(request, pk):
    matriz = get_object_or_404(Matriz, pk=pk)
    title = f'Matriz Curricular: {matriz!s}'
    if (
        not request.user.has_perm('edu.view_matriz')
        and not Aluno.objects.filter(matricula=request.user.username, matriz=matriz).exists()
        and not request.user.has_group_cached('Estagiário')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    return locals()


@permission_required('edu.add_matriz')
@rtr()
def replicar_matriz(request, pk):
    title = 'Replicação de Matriz'
    matriz = get_object_or_404(Matriz, pk=pk)
    form = ReplicacaoMatrizForm(matriz, data=request.POST or None)
    if request.POST and form.is_valid():
        try:
            resultado = form.processar()
            return httprr(f'/edu/matriz/{resultado.id}/', 'Matriz replicada com sucesso.')
        except ValidationError as e:
            return httprr('..', f'Não foi possível replicar a matriz: {e.messages[0]}', 'error')
    return locals()


@permission_required('edu.add_componentecurricular')
@rtr()
def vincular_componente_matriz(request, pk, componente_pk=None):
    title = '{} Componente de Matriz'.format(componente_pk and 'Editar' or 'Vincular')
    matriz = get_object_or_404(Matriz, pk=pk)

    if not matriz.pode_ser_editada(request.user):
        return httprr(f'/edu/matriz/{pk}/?tab=componentes', 'A matriz não pode ser editada.', 'error')

    if componente_pk:
        mc = get_object_or_404(ComponenteCurricular.objects, componente__pk=componente_pk, matriz=matriz)

    form = ComponenteCurricularForm(matriz, data=request.POST or None, instance=componente_pk and mc or None)

    if form.is_valid():
        form.processar()
        redirect = '..'
        if 'continuar' in request.POST:
            redirect = '.'
        if not componente_pk:
            return httprr(redirect, 'Componente de matriz adicionado com sucesso.')
        else:
            return httprr(f'/edu/matriz/{pk}/?tab=componentes', 'Componente de matriz atualizado com sucesso.')
    return locals()


@permission_required('edu.add_matriz')
@rtr()
def adicionar_configuracaocertificacaoparcial_matriz(request, pk):
    title = 'Adicionar configuração de certificação parcial'
    form = ConfiguracaoCertificacaoParcialForm(request.POST or None, matriz_id=pk)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Configuração de certificação parcial adicionada com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_matriz')
@rtr()
def editar_configuracaocertificacaoparcial(request, pk):
    title = 'Editar configuração de certificação parcial'
    obj = ConfiguracaoCertificacaoParcial.objects.get(id=pk)
    form = ConfiguracaoCertificacaoParcialForm(request.POST or None, instance=obj)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Configuração de certificação parcial adicionada com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_matriz')
@rtr()
def vincular_componentecurricular_configuracaocertificacaoparcial(request, pk):
    title = 'Vincular componente curricular'
    form = VincularComponenteCurricularConfiguracaoCertificacaoParcialForm(request.POST or None, configuracao_id=pk)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Componente curricular vinculado com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_matriz')
@rtr()
def vincular_modulo_configuracaocertificacaoparcial(request, pk):
    title = 'Vincular módulo'
    ccp = ConfiguracaoCertificacaoParcial.objects.get(id=pk)
    form = VincularModuloConfiguracaoCertificacaoParcialForm(request.POST or None, ccp=ccp)
    if form.is_valid():
        try:
            form.processar()
        except ValidationError as e:
            return httprr('.', f'Ocorreu um erro: {e.messages[0]}', 'error')
        return httprr('.', 'Módulo vinculado com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.add_componentecurricular')
@rtr()
def definir_requisitos(request, pk):
    title = 'Definir Pré e Co-requisitos'
    instance = get_object_or_404(ComponenteCurricular, pk=pk)
    form = RequisitosComponenteCurricularForm(request.POST or None, instance=instance)
    if form.is_valid():
        form.save()
        return httprr('..', 'Requisitos definidos com sucesso.')
    return locals()


@permission_required('edu.add_matrizcurso')
@rtr()
def adicionar_matriz_curso(request, curso_campus_pk, matriz_curso_pk=None):
    title = 'Adicionar Matriz'
    curso_campus = get_object_or_404(CursoCampus.locals, pk=curso_campus_pk)
    if curso_campus.is_minicurso():
        return httprr('..', 'Cursos da modalidade FIC- (Minicurso) não possuem matriz curricular.', 'error')
    if matriz_curso_pk:
        matriz_curso = curso_campus.matrizcurso_set.get(pk=matriz_curso_pk)
    form = MatrizCursoForm(data=request.POST or None, instance=matriz_curso_pk and matriz_curso or None)
    form.initial.update({'curso_campus': curso_campus.pk})
    if form.is_valid():
        form.save()
        return httprr('..', 'Matriz adicionada com sucesso.')
    return locals()


@permission_required('edu.add_componente')
@rtr()
def importar_componentes(request):
    title = 'Importar Componentes'
    form = ImportarComponentesForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Componentes importados com sucesso.')
    return locals()


@permission_required('edu.add_componentecurricular')
@rtr()
def importar_componentes_matriz(request, pk):
    matriz = get_object_or_404(Matriz, pk=pk)
    if matriz.pode_ser_editada(request.user):
        title = f'Importar Componentes em {matriz}'
        form = ImportarComponentesMatrizForm(matriz, data=request.POST or None, files=request.FILES or None)
        if form.is_valid():
            form.processar()
            return httprr(f'/edu/matriz/{pk}/?tab=componentes', 'Componentes importados com sucesso.')
    else:
        return httprr(f'/edu/matriz/{pk}/?tab=componentes', 'Esta matriz não pode ser alterada.', 'error')
    return locals()


@group_required('Administrador Acadêmico, Diretor Acadêmico, Coordenador de Curso, Coordenador de Modalidade Acadêmica, Secretário Acadêmico')
@rtr()
@login_required()
def editar_abreviatura_componente(request, pk):
    title = 'Editar Abreviatura de Componente'
    obj = get_object_or_404(Componente, pk=pk)
    form = EditarAbreviaturaComponenteForm(data=request.POST or None, instance=obj)

    if form.is_valid():
        form.save()
        return httprr('..', 'Abreviatura atualizada com sucesso.')

    return locals()


@permission_required('edu.view_componente')
@rtr()
def componente(request, pk):
    obj = get_object_or_404(Componente, pk=pk)
    title = f'{obj.sigla} - {obj.descricao_historico}'
    planodisciplina = obj.get_planodisciplina()
    possui_planodisciplina = planodisciplina is not None
    possui_secao_ead = planodisciplina.get_secoes_ead().exists() if planodisciplina else False

    if request.GET.get('tab') == 'matriz':
        matrizes = Matriz.objects.filter(componentecurricular__componente=obj)
    elif request.GET.get('tab') == 'equivalencias':
        equivalencias = obj.eq1.all() | obj.eq2.all()

    return locals()


def cadastrar_pre_requisito_ajax(request, componente_curricular_pk, pre_requisito_pk):
    componente_curricular = get_object_or_404(ComponenteCurricular, pk=componente_curricular_pk)
    pre_requisito = get_object_or_404(ComponenteCurricular, pk=pre_requisito_pk)
    componente_curricular.pre_requisitos.add(pre_requisito)
    return HttpResponse('OK')


def remover_pre_requisito_ajax(request, componente_curricular_pk, pre_requisito_pk):
    componente_curricular = get_object_or_404(ComponenteCurricular, pk=componente_curricular_pk)
    pre_requisito = get_object_or_404(ComponenteCurricular, pk=pre_requisito_pk)
    componente_curricular.pre_requisitos.remove(pre_requisito)
    return HttpResponse('OK')


@rtr()
@login_required()
def visualizar_estrutura_curso(request, estrutura_curso_pk):
    title = 'Estrutura de Curso'
    obj = get_object_or_404(EstruturaCurso, pk=estrutura_curso_pk)
    if 'replicar' in request.GET:
        obj.pk = None
        obj.descricao = f'{obj.descricao} [REPLICADA]'
        obj.save()
        return httprr(f'/admin/edu/estruturacurso/{obj.pk}/', 'Estrutura replicada com sucesso. Edite a descrição e os demais dados necessários.')
    matrizes_ativas = obj.get_matrizes_ativas()
    matrizes_inativas = obj.get_matrizes_inativas()

    return locals()


@permission_required('edu.add_matriz')
@rtr()
def inserir_diretoria_curso(request, pk):
    title = 'Inserir Diretoria em Curso'
    curso_campus = get_object_or_404(CursoCampus, pk=pk)
    form = InserirDiretoriaForm(request.POST or None, request=request)

    if curso_campus.diretoria:
        return httprr('..', 'Curso selecionado já possui diretoria.', 'error')

    if form.is_valid():
        curso_campus.diretoria = form.cleaned_data['diretoria']
        curso_campus.save()
        return httprr('..', 'Diretoria atualizada com sucesso.')

    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def editar_diretoria_curso(request, pk):
    title = 'Editar Diretoria'
    curso_campus = get_object_or_404(CursoCampus, pk=pk)
    form = EditarDiretoriaCurso(request.POST or None, instance=curso_campus)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Diretoria editada com sucesso.')
    return locals()


@rtr()
@group_required('Secretário Acadêmico,Coordenador de Curso,Diretor Acadêmico,Administrador Acadêmico,Pedagogo')
def analise_curso(request, pk, componente_curricular_pk=None, exibir=None):
    matriz_curso = get_object_or_404(MatrizCurso, pk=pk)
    registros = []
    pk_alunos = []
    alunos = []
    exibicao = []
    mapa_requisitos = {}

    for pk, pre, co, componente_pk in matriz_curso.matriz.componentecurricular_set.values_list(
        'pk', 'pre_requisitos', 'co_requisitos', 'pre_requisitos__componente'
    ):
        if pk not in mapa_requisitos:
            mapa_requisitos[pk] = ([], [], [], [])
        if pre:
            mapa_requisitos[pk][0].append(pre)
        if co:
            mapa_requisitos[pk][1].append(co)
        if componente_pk:
            mapa_requisitos[pk][3].append(componente_pk)

    for pk in mapa_requisitos:
        for pre in mapa_requisitos[pk][0]:
            if pre in mapa_requisitos:
                if pk not in mapa_requisitos[pre][2]:
                    mapa_requisitos[pre][2].append(pk)

    situacoes = [SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL, SituacaoMatricula.TRANCADO]
    for aluno in Aluno.objects.filter(matriz=matriz_curso.matriz, curso_campus=matriz_curso.curso_campus, situacao__in=situacoes):
        pk_alunos.append(aluno.pk)
        aluno.ids_componentes_cumpridos = []
        if exibir != 'cursando':
            aluno.ids_componentes_cumpridos = aluno.get_ids_componentes_cumpridos()
        alunos.append(aluno)

    qs_periodos = matriz_curso.matriz.componentecurricular_set.exclude(periodo_letivo__isnull=True)
    if componente_curricular_pk:
        qs_periodos = qs_periodos.filter(pk=componente_curricular_pk)
    periodos = qs_periodos.order_by('periodo_letivo').values_list('periodo_letivo', flat=True).distinct()
    for periodo in [*list(periodos), None]:
        componentes_curriculares = []
        if periodo is None:
            qs_componente_curricular = matriz_curso.matriz.componentecurricular_set.filter(periodo_letivo__isnull=True)
        else:
            qs_componente_curricular = matriz_curso.matriz.componentecurricular_set.filter(periodo_letivo=periodo)
        if componente_curricular_pk:
            qs_componente_curricular = qs_componente_curricular.filter(pk=componente_curricular_pk)
        for componente_curricular in qs_componente_curricular:
            qs_cursando = MatriculaDiario.objects.filter(
                diario__componente_curricular__componente=componente_curricular.componente_id,
                situacao=MatriculaDiario.SITUACAO_CURSANDO,
                matricula_periodo__aluno__in=pk_alunos,
            ).values_list('matricula_periodo__aluno', flat=True)
            componente_curricular.qtd_matriculados = len(qs_cursando)
            componente_curricular.qtd_concluidos = 0
            componente_curricular.qtd_pendentes = 0
            componente_curricular.qtd_aptos = 0
            componente_curricular.possui_requisitos = (
                mapa_requisitos[componente_curricular.pk][0]
                or mapa_requisitos[componente_curricular.pk][1]
                or mapa_requisitos[componente_curricular.pk][2]
            )
            for aluno in alunos:
                if componente_curricular.componente.pk in aluno.ids_componentes_cumpridos:
                    componente_curricular.qtd_concluidos += 1
                    if exibir == 'concluidos':
                        exibicao.append(aluno)
                else:
                    componente_curricular.qtd_pendentes += 1
                    if exibir == 'pendentes':
                        exibicao.append(aluno)
                    apto = True
                    if (
                        componente_curricular.periodo_letivo
                        and componente_curricular.periodo_letivo > aluno.periodo_atual
                        and (aluno.is_seriado() or aluno.is_modular())
                    ):
                        apto = False
                    else:
                        for componente_pk in mapa_requisitos[componente_curricular.pk][3]:
                            if componente_pk not in aluno.ids_componentes_cumpridos:
                                apto = False
                                break
                    if apto and aluno.pk not in qs_cursando:
                        componente_curricular.qtd_aptos += 1
                        if exibir == 'aptos':
                            exibicao.append(aluno)
            if exibir == 'cursando':
                exibicao = Aluno.objects.filter(pk__in=qs_cursando.values_list('matricula_periodo__aluno', flat=True))
            if exibir:
                title = f'Lista de Alunos ({len(exibicao)})'
                return locals()
            componentes_curriculares.append(componente_curricular)
        registros.append({'periodo': periodo or 'Optativo', 'componentes_curriculares': componentes_curriculares})

    width = 100 / len(registros)
    title = f'{matriz_curso.curso_campus.codigo} - {matriz_curso.curso_campus.descricao_historico} ({len(alunos)} alunos)'
    mapa_requisitos_js = json.dumps(mapa_requisitos)
    return locals()


@permission_required('edu.add_polo')
@rtr()
def relatorio_disciplinas_ead(request):
    title = 'Relatório de Disciplinas EAD'
    form = RelatorioDisciplinasEADForm(data=request.GET or None)
    if form.is_valid():
        ano_letivo, qs = form.processar()
        if form.cleaned_data['exibicao'] == 'arquivo':
            return tasks.relatorio_disciplinas_ead(ano_letivo, qs)
        else:
            set_ano_letivo(ano_letivo)
    return locals()
