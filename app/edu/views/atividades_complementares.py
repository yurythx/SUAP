from __future__ import annotations

import datetime
from typing import Any
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from djtools.utils import (
    breadcrumbs,
    JsonResponse,
    httprr,
    permission_required,
    rtr,
)
from edu import perms
from edu.forms import (
    AtividadeAprofundamentoForm,
    AtividadeComplementarForm,
    AtividadeCurricularExtensaoExtraForm,
    AtividadePraticaProfissionalForm,
    AvaliarAtividadePraticaProfissionalForm,
    ConcluirAtividadePraticaProfissionalForm,
    DesfazerAvaliacaoAtividadeForm,
    EditarAtividadePraticaProfissionalForm,
    EditarHorarioAtividadeExtraForm,
    HorarioAtividadeExtraForm,
    IndeferirAtividadeComplementarForm,
    IndeferirAtividadeAprofundamentoForm,
    ItemConfiguracaoAtividadeAprofundamentoForm,
    ItemConfiguracaoAtividadeComplementarForm,
    ItemConfiguracaoCreditosEspeciaisForm,
    RemoverAtividadeForm,
    ReplicarConfiguracaoAACCForm,
    ReplicarConfiguracaoATPAForm,
    VincularAtividadeExtensaoForm,
    VincularConfiguracaoAtividadeAprofundamentoForm,
    VincularConfiguracaoAtividadeComplementarForm,
)
from edu.models import (
    Aluno,
    AtividadeAprofundamento,
    AtividadeComplementar,
    AtividadeCurricularExtensao,
    AtividadeCurricularExtensaoExtra,
    AtividadePraticaProfissional,
    ConfiguracaoAtividadeAprofundamento,
    ConfiguracaoAtividadeComplementar,
    ConfiguracaoCreditosEspeciais,
    ItemConfiguracaoAtividadeAprofundamento,
    ItemConfiguracaoAtividadeComplementar,
    ItemConfiguracaoCreditosEspeciais,
    MatriculaPeriodo,
    Matriz,
    NivelEnsino,
    SituacaoMatricula,
    TipoAtividadeComplementar,
    VinculacaoAtividadeExtensao,
)
from edu.models.atividades import HorarioAtividadeExtra


@login_required()
@rtr()
def cadastrar_atividade_complementar(request, aluno_pk, atividadecomplementar_pk=None):
    title = '{} atividade complementar'.format(atividadecomplementar_pk and 'Editar' or 'Adicionar')
    aluno = get_object_or_404(Aluno, pk=aluno_pk)

    atividade_complementar = None
    if atividadecomplementar_pk:
        atividade_complementar = get_object_or_404(AtividadeComplementar.objects, pk=atividadecomplementar_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = AtividadeComplementarForm(
        request.POST or None,
        initial={'aluno': aluno.pk},
        files=request.FILES or None,
        instance=atividade_complementar,
        request=request,
        as_aluno=False,
    )

    if form.is_valid():
        form.processar(request.user.get_vinculo())
        redirect = '..'
        if not atividadecomplementar_pk:
            return httprr(redirect, 'Atividade complementar adicionada com sucesso.')
        else:
            return httprr(redirect, 'Atividade complementar atualizada com sucesso.')
    return locals()


@login_required()
@rtr()
def cadastrar_atividade_aprofundamento(request, aluno_pk, atividadeaprofundamento_pk=None):
    title = '{} atividade teórico-práticas de aprofundamento'.format(atividadeaprofundamento_pk and 'Editar' or 'Adicionar')
    aluno = get_object_or_404(Aluno, pk=aluno_pk)

    atividade_aprofundamento = None
    if atividadeaprofundamento_pk:
        atividade_aprofundamento = get_object_or_404(AtividadeAprofundamento.objects, pk=atividadeaprofundamento_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = AtividadeAprofundamentoForm(
        request.POST or None,
        initial={'aluno': aluno.pk},
        files=request.FILES or None,
        instance=atividade_aprofundamento,
        request=request,
        as_aluno=False,
    )

    if form.is_valid():
        form.processar(request.user.get_vinculo())
        redirect = '..'
        if not atividadeaprofundamento_pk:
            return httprr(redirect, 'Atividade complementar adicionada com sucesso.')
        else:
            return httprr(redirect, 'Atividade complementar atualizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_configuracaoatividadecomplementar')
def configuracaoatividadecomplementar(request, pk):
    obj = ConfiguracaoAtividadeComplementar.objects.get(pk=pk)
    title = 'Configuração da AACC'

    if 'desvincular_matriz' in request.GET and request.user.has_perm('edu.change_configuracaoatividadecomplementar'):
        matriz = Matriz.objects.get(pk=request.GET.get('desvincular_matriz'))
        matriz.configuracao_atividade_academica = None
        matriz.save()
        return httprr(f'/edu/configuracaoatividadecomplementar/{pk}/?tab=matrizes', 'Matriz desvinculada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_configuracaoatividadeaprofundamento')
def configuracaoatividadeaprofundamento(request, pk):
    obj = ConfiguracaoAtividadeAprofundamento.objects.get(pk=pk)
    title = 'Configuração da ATPa'

    if 'desvincular_matriz' in request.GET and request.user.has_perm('edu.change_configuracaoatividadeaprofundamento'):
        matriz = Matriz.objects.get(pk=request.GET.get('desvincular_matriz'))
        matriz.configuracao_atividade_aprofundamento = None
        matriz.save()
        return httprr(f'/edu/configuracaoatividadeaprofundamento/{pk}/?tab=matrizes', 'Matriz desvinculada com sucesso.')
    return locals()


@rtr()
@login_required()
def atividadeaprofundamento(request, pk):
    obj = get_object_or_404(AtividadeAprofundamento, pk=pk)
    title = 'Atividade de aprofundamento'
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.aluno.curso_campus)
    if pode_realizar_procedimentos:
        if 'deferir' in request.GET:
            obj.deferida = True
            obj.save()
            return httprr('..', 'Deferimento realizado com sucesso')
        elif 'indeferir' in request.GET:
            title = 'Atividade de aprofundamento: Indeferir'
            form = IndeferirAtividadeAprofundamentoForm(data=request.POST or None, instance=obj)
            if form.is_valid():
                form.save()
                return httprr('..', 'Indeferimento realizado com sucesso.')
        elif 'desfazer' in request.GET:
            title = 'Atividade de aprofundamento: Desfazer avaliação'
            form = DesfazerAvaliacaoAtividadeForm(request.POST or None)
            if form.is_valid():
                obj.desfazer_avaliacao(motivo=form.cleaned_data.get('motivo', None), vinculo=request.user.get_vinculo())
                return httprr('..', 'Avaliação da atividade de aprofundamento desfeita com sucesso.')
    return locals()


@rtr()
@permission_required('edu.delete_atividadecomplementar')
def atividadeaprofundamento_delete(request, pk):
    title = 'Remover atividade de aprofundamento'
    form = RemoverAtividadeForm(request.POST or None)
    if form.is_valid():
        obj = get_object_or_404(AtividadeAprofundamento, pk=pk)
        url_retorno = obj.aluno.get_absolute_url() + '?tab=aprofundamento'
        obj.delete(motivo=form.cleaned_data['motivo'], vinculo=request.user.get_vinculo())
        return httprr(url_retorno, 'Atividade de aprofundamento removida com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def dados_atividade_complementar_ajax(request, aluno_pk, tipo_pk):
    obj = get_object_or_404(Aluno, pk=aluno_pk)
    tipos = obj.get_ch_atividades_complementares_por_tipo(True)
    tipo = None
    for var in tipos:
        if var.pk == int(tipo_pk):
            tipo = var
            break
    return locals()


@login_required()
def listar_atividades_complementares_ajax(request, aluno_pk, vinculacao):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    if int(vinculacao) == AtividadeComplementarForm.VINCULADO_CURSO:
        tipos = (
            TipoAtividadeComplementar.objects.filter(itemconfiguracaoatividadecomplementar__configuracao__matriz__aluno=aluno)
            .distinct()
            .values_list('id', 'descricao')
        )
    else:
        tipos = (
            TipoAtividadeComplementar.objects.filter(modalidades__in=[aluno.curso_campus.modalidade])
            .exclude(itemconfiguracaoatividadecomplementar__configuracao__matriz__aluno=aluno)
            .distinct()
            .values_list('id', 'descricao')
        )
    return JsonResponse(list(tipos))


@rtr()
@permission_required('edu.change_configuracaoatividadecomplementar')
def vincular_configuracao_atividade_complementar(request, pk):
    title = 'Vincular Matriz'
    form = VincularConfiguracaoAtividadeComplementarForm(request.POST or None)
    if form.is_valid():
        obj = ConfiguracaoAtividadeComplementar.objects.get(pk=pk)
        for matriz in form.cleaned_data['matrizes']:
            if matriz.configuracao_atividade_academica:
                return httprr('.', f'Matriz({matriz}) já vinculada a configuração({matriz.configuracao_atividade_academica.descricao}).', 'error')

        for matriz in form.cleaned_data['matrizes']:
            matriz.configuracao_atividade_academica = obj
            matriz.save()
        return httprr('..', 'Matrizes vinculadas com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_configuracaoatividadeaprofundamento')
def vincular_configuracao_atividade_aprofundamento(request, pk):
    title = 'Vincular Matriz'
    form = VincularConfiguracaoAtividadeAprofundamentoForm(request.POST or None)
    if form.is_valid():
        obj = ConfiguracaoAtividadeAprofundamento.objects.get(pk=pk)
        for matriz in form.cleaned_data['matrizes']:
            if matriz.configuracao_atividade_aprofundamento:
                return httprr('.', f'Matriz({matriz}) já vinculada a configuração({matriz.configuracao_atividade_academica.descricao}).', 'error')

        for matriz in form.cleaned_data['matrizes']:
            matriz.configuracao_atividade_aprofundamento = obj
            matriz.save()
        return httprr('..', 'Matrizes vinculadas com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_configuracaoatividadecomplementar')
def adicionar_item_configuracao_aacc(request, pk):
    title = 'Adicionar Atividade Acadêmica'

    instance = None
    if 'atividadeacademica' in request.GET:
        instance = ItemConfiguracaoAtividadeComplementar.objects.get(pk=request.GET.get('atividadeacademica'))
        title = f'Editar Atividade Acadêmica - {instance.tipo.descricao}'
        atividade_complementar = AtividadeComplementar.objects.filter(tipo__itemconfiguracaoatividadecomplementar=instance).exists()
    form = ItemConfiguracaoAtividadeComplementarForm(request.POST or None, instance=instance, configuracao_pk=pk)
    if form.is_valid():
        form.instance.configuracao = ConfiguracaoAtividadeComplementar.objects.get(pk=pk)
        try:
            form.instance.save()
        except IntegrityError:
            return httprr('.', 'Não foi possível adicionar a atividade complementar pois ela já pertence a esta Configuração de AACCs', 'error')

        if instance:
            return httprr('..', 'Atividade acadêmica alterada com sucesso.')
        else:
            return httprr('..', 'Atividade acadêmica cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_configuracaoatividadeaprofundamento')
def adicionar_item_configuracao_atpa(request, pk):
    title = 'Adicionar Atividade de Aprofundamento'

    instance = None
    if 'atividadeaprofundamento' in request.GET:
        instance = ItemConfiguracaoAtividadeAprofundamento.objects.get(pk=request.GET.get('atividadeaprofundamento'))
        title = f'Editar Atividade de Aprofundamento - {instance.tipo.descricao}'
        atividade_aprofundamento = AtividadeAprofundamento.objects.filter(tipo__itemconfiguracaoatividadeaprofundamento=instance).exists()
    form = ItemConfiguracaoAtividadeAprofundamentoForm(request.POST or None, instance=instance, configuracao_pk=pk)
    if form.is_valid():
        form.instance.configuracao = ConfiguracaoAtividadeAprofundamento.objects.get(pk=pk)
        try:
            form.instance.save()
        except IntegrityError:
            return httprr('.', 'Não foi possível adicionar a atividade de aprofundamento pois ela já pertence a esta Configuração de ATPA', 'error')

        if instance:
            return httprr('..', 'Atividade de aprofundamento alterada com sucesso.')
        else:
            return httprr('..', 'Atividade de aprofundamento cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_configuracaocreditosespeciais')
def adicionar_item_configuracao_ce(request, pk, pk_atividade=None):
    title = 'Adicionar Atividade'
    configuracao = ConfiguracaoCreditosEspeciais.objects.get(pk=pk)
    instance = None
    if pk_atividade:
        instance = ItemConfiguracaoCreditosEspeciais.objects.get(pk=pk_atividade)
        title = f'Editar Atividade - {instance}'
    form = ItemConfiguracaoCreditosEspeciaisForm(request.POST or None, instance=instance)
    if form.is_valid():
        obj = form.save(False)
        obj.configuracao = configuracao
        obj.save()
        if instance:
            return httprr('..', 'Atividade alterada com sucesso.')
        else:
            return httprr('..', 'Atividade cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_configuracaoatividadecomplementar')
def replicar_configuracao_aacc(request, pk):
    configuracao = ConfiguracaoAtividadeComplementar.objects.get(pk=pk)
    title = f'Replicar - {configuracao.descricao}'
    form = ReplicarConfiguracaoAACCForm(request.POST or None)
    if request.POST and form.is_valid():
        resultado = form.processar(configuracao)
        return httprr(
            '..',
            mark_safe(
                f'Configuração de AACC replicada com sucesso para {resultado.descricao}. Deseja <a href="/edu/configuracaoatividadecomplementar/{resultado.pk}/">Visualizá-la?</a>'
            ),
        )
    return locals()


@rtr()
@permission_required('edu.add_configuracaoatividadeaprofundamento')
def replicar_configuracao_atpa(request, pk):
    configuracao = ConfiguracaoAtividadeAprofundamento.objects.get(pk=pk)
    title = f'Replicar - {configuracao.descricao}'
    form = ReplicarConfiguracaoATPAForm(request.POST or None)
    if request.POST and form.is_valid():
        resultado = form.processar(configuracao)
        return httprr(
            '..',
            mark_safe(
                f'Configuração de ATPA replicada com sucesso para {resultado.descricao}. Deseja <a href="/edu/configuracaoatividadeaprofundamento/{resultado.pk}/">Visualizá-la?</a>'
            ),
        )
    return locals()


@rtr()
@login_required()
def visualizar_atividades_complementares_cumpridas(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    title = 'Atividades Complementares Cumpridas'
    atividades_complementares = obj.get_atividades_complementares(True)
    tipos = obj.get_ch_atividades_complementares_por_tipo()
    return locals()


@rtr()
@login_required()
def visualizar_atividades_aprofundamento_cumpridas(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    title = 'Atividades de Aprofudamento'
    atividades_aprofundamento = obj.atividadeaprofundamento_set.filter(deferida=True)
    return locals()


@rtr()
@login_required()
def visualizar_atividades_complementares_pendentes(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    title = 'Atividades Complementares Pendentes'
    requer_atividade_obrigatoria = False
    tipos = obj.get_ch_atividades_complementares_por_tipo(apenas_obrigatorias=True)
    for tipo in tipos:
        if tipo.ch_considerada < tipo.ch_min_curso:
            requer_atividade_obrigatoria = True
            break
    return locals()


@rtr()
@login_required()
def solicitar_atividade_complementar(request: HttpRequest, pk: int | None = None) -> dict[str, Any] | HttpResponse:
    title = '{} solicitação de atividade complementar'.format(pk and 'Editar' or 'Adicionar')
    aluno = Aluno.objects.filter(matricula=request.user.username).first()

    if aluno is None or not aluno.pode_solicitar_atividade_complementar(request.user):
        return httprr('..', 'Você não tem permissão para solicitar atividade complementar.', 'error')

    atividade = None
    if pk:
        atividade = get_object_or_404(AtividadeComplementar.objects, pk=pk, deferida__isnull=True, aluno=aluno)

    form = AtividadeComplementarForm(
        request.POST or None, initial={'aluno': aluno.pk}, files=request.FILES or None, instance=atividade, as_aluno=True, request=request
    )

    if form.is_valid():
        form.processar(request.user.get_vinculo())
        msg = pk and 'atualizada' or 'adicionada'
        return httprr(
            f'{aluno.get_absolute_url()}?tab=acc',
            f'Atividade complementar {msg} com sucesso. Compareça à coordenação de curso ou setor competente para validação do documento.',
            close_popup=True,
        )
    return locals()


@rtr()
@login_required()
def solicitar_atividade_aprofundamento(request: HttpRequest, pk: int | None = None) -> dict[str, Any] | HttpResponse:
    title = '{} solicitação de atividade aprofundamento'.format(pk and 'Editar' or 'Adicionar')
    aluno = get_object_or_404(
        Aluno,
        matricula=request.user.username,
        curso_campus__modalidade__nivel_ensino__pk__in=[NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO],
        situacao__id__in=[SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL],
    )

    atividade = None
    if pk:
        atividade = get_object_or_404(AtividadeAprofundamento.objects, pk=pk, deferida__isnull=True, aluno=aluno)

    form = AtividadeAprofundamentoForm(
        request.POST or None, initial={'aluno': aluno.pk}, files=request.FILES or None, instance=atividade, as_aluno=True, request=request
    )

    if form.is_valid():
        form.save()
        redirect = '..'
        if not pk:
            return httprr(
                redirect,
                'Atividade de Aprofundamento adicionada com sucesso. Compareça à coordenação de curso ou setor competente para validação do documento.',
            )
        else:
            return httprr(
                redirect,
                'Atividade de Aprofundamento atualizada com sucesso. Compareça à coordenação de curso ou setor competente para validação do documento.',
            )
    return locals()


@rtr()
@permission_required('edu.view_atividadecomplementar')
def atividadecomplementar(request, pk):
    title = 'Atividade complementar'
    obj = get_object_or_404(AtividadeComplementar, pk=pk)
    if request.user.has_perm('edu.change_atividadecomplementar'):
        if 'deferir' in request.GET:
            obj.deferida = True
            obj.data_deferimento_atividade = datetime.date.today()
            obj.save()
            return httprr('..', 'Deferimento realizado com sucesso.')
        elif 'indeferir' in request.GET:
            title = 'Atividade complementar: Indeferir'
            form = IndeferirAtividadeComplementarForm(data=request.POST or None, instance=obj)
            if form.is_valid():
                form.save()
                return httprr('..', 'Indeferimento realizado com sucesso.')
        elif 'desfazer' in request.GET:
            title = 'Atividade complementar: Desfazer avaliação'
            form = DesfazerAvaliacaoAtividadeForm(request.POST or None)
            if form.is_valid():
                obj.desfazer_avaliacao(motivo=form.cleaned_data.get('motivo', None), vinculo=request.user.get_vinculo())
                return httprr('..', 'Avaliação da atividade complementar desfeita com sucesso.')
    return locals()


@rtr()
@permission_required('edu.delete_atividadecomplementar')
def atividadecomplementar_delete(request, pk):
    title = 'Remover atividade complementar'
    form = RemoverAtividadeForm(request.POST or None)
    if form.is_valid():
        obj = get_object_or_404(AtividadeComplementar, pk=pk)
        url_retorno = obj.aluno.get_absolute_url() + '?tab=acc'
        obj.delete(motivo=form.cleaned_data['motivo'], vinculo=request.user.get_vinculo())
        return httprr(url_retorno, 'Atividade complementar removida com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.add_horarioatividadeextra')
def adicionar_horario_atividade_extra(request, aluno_pk, ano, periodo):
    aluno = get_object_or_404(Aluno.objects, pk=aluno_pk)
    mp = MatriculaPeriodo.objects.filter(aluno__pk=aluno_pk, ano_letivo__ano=ano, periodo_letivo=periodo)
    if not mp.exists():
        return httprr('..', f'Não existe uma matrícula no período {ano}.{periodo} para este o aluno {aluno}.', 'error')
    if request.user.eh_aluno and not aluno.is_user(request):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    title = 'Adicionar Atividade Extra'
    turnos = mp[0].get_horarios_aula_atividade_por_turno()
    form = HorarioAtividadeExtraForm(data=request.POST or None, request=request, matricula_periodo=mp[0])
    if form.is_valid():
        horarios = dict(request.POST).get('horario')
        form.save(horarios)
        return httprr('..', 'Atividade adicionada com sucesso.')
    return locals()


@rtr('adicionar_horario_atividade_extra.html')
@permission_required('edu.add_horarioatividadeextra')
def editar_horario_atividade_extra(request, aluno_pk, ano, periodo, atividade_extra_pk):
    aluno = get_object_or_404(Aluno.objects, pk=aluno_pk)
    mp = get_object_or_404(MatriculaPeriodo.objects, aluno__pk=aluno_pk, ano_letivo__ano=ano, periodo_letivo=periodo)
    atividade_extra = get_object_or_404(HorarioAtividadeExtra.objects, pk=atividade_extra_pk)
    if request.user.eh_aluno and not aluno.is_user(request):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    title = 'Alterar Horário da Atividade Extra'
    turnos = mp.get_horarios_aula_atividade_por_turno()
    form = EditarHorarioAtividadeExtraForm(data=request.POST or None, request=request, instance=atividade_extra, matricula_periodo=mp)
    if form.is_valid():
        horarios = dict(request.POST).get('horario')
        form.save(horarios)
        return httprr('..', 'Atividade atualizada com sucesso.')
    return locals()


@rtr()
@login_required
def distribuir_atividadecurricularextensao(request, pk):
    obj = get_object_or_404(AtividadeCurricularExtensao.objects, pk=pk)
    if not obj.pode_distribuir(request.user):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error', close_popup=True)

    title = f'{obj.get_tipo()}: {obj.descricao} ({obj.get_carga_horaria()}h)'
    form = VincularAtividadeExtensaoForm(atividade_extensao=obj, data=request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Distribuição realizada com sucesso.', close_popup=True)
    return locals()


def _erro_avaliacao_extensao(obj: VinculacaoAtividadeExtensao, msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {
            'erro': msg,
            'situacao_anterior': obj.get_codigo_situacao(),
        },
        status=status,
    )


def _formatar_status_ch_extensao(ch_cumprida: int | None, ch_requerida: int) -> str:
    if not ch_cumprida:
        return '<span class="status status-alert">Nenhuma</span>'
    classe = 'status-success' if ch_cumprida >= ch_requerida else 'status-info'
    return f'<span class="status {classe}">{ch_cumprida} de {ch_requerida} hora(s)</span>'


def _aplicar_situacao_vinculacao_extensao(obj: VinculacaoAtividadeExtensao, situacao: str, ch_requerida: int, user: object) -> str | None:
    if situacao == '1':
        ch_homologada = obj.get_ch_vinculada_outros(incluir_pendentes=False)
        if ch_requerida > 0 and ch_homologada + obj.carga_horaria > ch_requerida:
            return (
                f'Não é possível homologar esta atividade pois a soma das horas homologadas '
                f'({ch_homologada + obj.carga_horaria}h) supera a carga horária exigida pela disciplina ({ch_requerida}h).'
            )
        obj.homologada = True
        obj.data_homologacao = datetime.datetime.now()
        obj.responsavel_homologacao = user
    elif situacao == '0':
        obj.homologada = None
        obj.data_homologacao = None
        obj.responsavel_homologacao = None
    elif situacao == '2':
        obj.homologada = False
        obj.data_homologacao = datetime.datetime.now()
        obj.responsavel_homologacao = user
    else:
        return 'Situação de homologação inválida.'
    return None


@rtr()
@login_required
def avaliar_vinculacaoatividadeextensao_ajax(request: HttpRequest, pk: int, situacao: str) -> HttpResponse:
    obj = get_object_or_404(VinculacaoAtividadeExtensao.objects, pk=pk)
    diario = obj.matricula_diario.diario
    if not diario.pode_avaliar_atividade_extensao(request.user):
        return _erro_avaliacao_extensao(obj, 'Você não tem permissão para avaliar atividades de extensão neste diário.', status=403)
    if not obj.matricula_diario.habilitada() or not obj.matricula_diario.is_cursando():
        return _erro_avaliacao_extensao(
            obj,
            'Não é possível alterar a situação de atividades de extensão pois o período letivo deste aluno está fechado.',
        )

    ch_requerida = diario.componente_curricular.get_ch_extensao_exigida() or 0
    erro = _aplicar_situacao_vinculacao_extensao(obj, situacao, ch_requerida, request.user)
    if erro:
        return _erro_avaliacao_extensao(obj, erro)

    obj.save()
    ch_cumprida = obj.matricula_diario.get_ch_atividade_extensao_cumprida()
    return HttpResponse(_formatar_status_ch_extensao(ch_cumprida, ch_requerida))


@rtr()
@permission_required('edu.add_atividadecurricularextensaoextra')
def adicionar_atividadecurricularextensaoextra(request, aluno_pk):
    title = 'Adicionar atividade curricular de extensão extra'
    form = AtividadeCurricularExtensaoExtraForm(data=request.POST or None, files=request.FILES or None, aluno_pk=aluno_pk)
    if form.is_valid():
        form.processar()
        return httprr('.', 'Atividade cadastrada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_atividadecurricularextensaoextra')
def editar_atividadecurricularextensaoextra(request, pk):
    title = 'Editar atividade curricular de extensão extra'
    atividade = AtividadeCurricularExtensaoExtra.objects.get(pk=pk)
    form = AtividadeCurricularExtensaoExtraForm(data=request.POST or None, files=request.FILES or None, instance=atividade)
    if form.is_valid():
        form.processar()
        return httprr('.', 'Atividade cadastrada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.add_atividadepraticaprofissional')
def cadastrar_atividadepraticaprofissional_aluno(request, pk, modalidade):
    title = 'Cadastrar atividade de prática profissional'
    aluno = get_object_or_404(Aluno, pk=pk)

    is_coordenador_curso = request.user.get_vinculo().id in [aluno.curso_campus.coordenador_id, aluno.curso_campus.coordenador_2_id]
    is_proprio_aluno = aluno.is_user(request)

    if is_proprio_aluno or is_coordenador_curso:
        form = AtividadePraticaProfissionalForm(data=request.POST or None, files=request.FILES or None, request=request)
        if form.is_valid():
            mp_id = aluno.get_ultima_matricula_periodo(excluir_em_aberto=True).id
            form.processar(request.user, mp_id, modalidade)
            return httprr('.', 'Atividade cadastrada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def iniciar_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    url = breadcrumbs.breadcrumbs_current_url(request)
    if atividade.pode_iniciar(request.user):
        atividade.iniciar()
        return httprr(url, 'Atividade iniciada com sucesso.')
    return httprr(url, 'Você não tem permissão para realizar isso.', 'error')


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def indeferir_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    url = breadcrumbs.breadcrumbs_current_url(request)
    if atividade.pode_indeferir(request.user):
        atividade.indeferir()
        return httprr(url, 'Atividade indeferida com sucesso.')
    return httprr(url, 'Você não tem permissão para realizar isso.', 'error')


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def deferir_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)

    if atividade.pode_deferir(request.user):
        atividade.deferir()
        return httprr('..', 'Atividade deferida com sucesso.')
    return httprr('..', 'Você não tem permissão para realizar isso.', 'error')


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def concluir_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    title = 'Concluir atividade de prática profissional'
    if not atividade.pode_concluir(request.user):
        return httprr('.', 'Você não tem permissão para realizar isso.', 'error', close_popup=True)
    form = ConcluirAtividadePraticaProfissionalForm(data=request.POST or None, files=request.FILES or None, instance=atividade)
    if form.is_valid():
        form.processar()
        return httprr('.', 'Atividade concluída com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def lancar_nota_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    title = 'Avaliar atividade de prática profissional'
    if not atividade.pode_lancar_nota(request.user):
        return httprr('.', 'Você não tem permissão para realizar isso.', 'error', close_popup=True)
    form = AvaliarAtividadePraticaProfissionalForm(data=request.POST or None, files=request.FILES or None, instance=atividade)
    if form.is_valid():
        form.processar()
        return httprr('.', 'Atividade avaliada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def editar_atividadepraticaprofissional(request, pk):
    title = 'Editar atividade de prática profissional'
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    if not atividade.can_change(request.user):
        return httprr('.', 'Você não tem permissão para realizar isso.', 'error', close_popup=True)
    form = EditarAtividadePraticaProfissionalForm(data=request.POST or None, files=request.FILES or None, instance=atividade)
    if form.is_valid():
        try:
            form.processar()
            return httprr('.', 'Atividade avaliada com sucesso.', close_popup=True)
        except ValidationError as e:
            return httprr('.', e.message, 'error', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def desconsiderar_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    url = breadcrumbs.breadcrumbs_current_url(request)
    if not atividade.pode_desconsiderar(request.user):
        return httprr(
            url,
            'Você não tem permissão para realizar isso.',
            'error',
        )
    atividade.desconsiderar()
    return httprr(url, 'Atividade desconsiderada com sucesso.', anchor=pk)


@rtr()
@permission_required('edu.change_atividadepraticaprofissional')
def reconsiderar_atividadepraticaprofissional(request, pk):
    atividade = AtividadePraticaProfissional.objects.get(pk=pk)
    url = breadcrumbs.breadcrumbs_current_url(request)
    if not atividade.pode_reconsiderar(request.user):
        return httprr(
            url,
            'Você não tem permissão para realizar isso.',
            'error',
        )
    atividade.reconsiderar()
    return httprr(url, 'Atividade reconsiderada com sucesso.', anchor=pk)
