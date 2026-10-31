from __future__ import annotations

import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from djtools import layout
from djtools.utils import httprr, rtr
from edu.models import Professor
from pit_rit_v3.forms import (
    CriarPlanoIndividualTrabalhoForm,
    EnviarPlanoForm,
    ParecerForm,
    PlanejarAtividadeForm,
)
from django.template.defaultfilters import pluralize
from .models import PlanoIndividualTrabalhoV3


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    if request.user.has_perm('pit_rit_v3.view_planoindividualtrabalhov3'):
        qtd_plano = PlanoIndividualTrabalhoV3.objects.filter(aprovado__isnull=True, avaliador__vinculos__user=request.user).count()
        if qtd_plano:
            pendencias.append(
                {
                    'titulo': f'Plano{pluralize(qtd_plano)} Individua{pluralize(qtd_plano, "l,is")} de Trabalho',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': qtd_plano,
                    'url': '/admin/pit_rit_v3/planoindividualtrabalhov3/?tab=tab_aguardando_avaliacao',
                }
            )
    return pendencias


@rtr()
@login_required()
def criar_plano(request, professor_id):
    title = 'Criar Plano Individual de Trabalho'
    if not PlanoIndividualTrabalhoV3.modulo_ativo():
        return httprr('/', 'O módulo de PIT V3 não está configurado para uso.', tag='error')
    professor = get_object_or_404(Professor, pk=professor_id)
    if professor.vinculo != request.user.get_vinculo():
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = CriarPlanoIndividualTrabalhoForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj = form.processar(professor_id)
        url = f'/edu/professor/{professor_id}/?tab=planoatividades&ano-periodo={obj.ano_letivo}.{obj.periodo_letivo}'
        return httprr(url, 'Ação realizada com sucesso.')
    return locals()


@rtr()
@login_required()
def planejar_atividade(request, pit_id, grupo_id, pk=None):
    title = 'Planejar Atividades'
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pit_id)
    if pit.professor.vinculo.user != request.user or pit.avaliador is not None:
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    instance = pit.atividadeplanejada_set.filter(pk=pk).first() if pk else None
    form = PlanejarAtividadeForm(data=request.POST or None, instance=instance, files=request.FILES or None)
    form.fields['atividade'].queryset = form.fields['atividade'].queryset.filter(
        subgrupo__grupo_id=grupo_id, fonte_dados__isnull=True, configuracao__ativa=True
    )
    if form.is_valid():
        form.instance.pit = pit
        form.save()
        return httprr(pit.get_absolute_url(), 'Atividade salva com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def remover_atividade(request, pit_id, pk):
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pit_id)
    if pit.professor.vinculo.user != request.user or pit.avaliador is not None:
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    obj = pit.atividadeplanejada_set.filter(pk=pk).first() if pk else None
    if obj:
        obj.delete()
    return httprr(pit.get_absolute_url(), 'Atividade removida com sucesso.')


@rtr()
@login_required()
def enviar_plano(request, pk):
    title = 'Enviar Plano Individual de Trabalho'
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pk)
    if not pit.pode_enviar_plano(request.user) and not pit.pode_alterar_avaliador_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error', close_popup=True)
    form = EnviarPlanoForm(data=request.POST or None, instance=pit)
    if form.is_valid():
        if form.instance.avaliador:
            form.instance.data_envio = datetime.datetime.now()
        else:
            form.instance.data_envio = None
        form.save()
        return httprr('..', 'Plano enviado com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def aprovar_plano(request, pk):
    title = 'Aprovar Plano'
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pk)
    if not pit.pode_avaliar_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = ParecerForm(data=request.POST or None, request=request)
    if form.is_valid():
        pit.aprovar_plano(request.user, form.instance)
        return httprr('..', 'Plano aprovado com sucesso.')
    return locals()


@rtr()
@login_required()
def devolver_plano(request, pk):
    title = 'Devolver Plano'
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pk)
    if not pit.pode_avaliar_plano(request.user) and not pit.pode_desfazer_aprovacao_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = ParecerForm(data=request.POST or None, request=request)
    if form.is_valid():
        pit.devolver_plano(request.user, form.instance)
        return httprr('..', 'Plano devolvido com sucesso.')
    return locals()


@rtr()
@login_required()
def desfazer_envio_plano(request: HttpRequest, pk: int) -> HttpResponse:
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pk)
    if not pit.pode_desfazer_envio_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    pit.desfazer_envio_plano(request.user)
    return httprr(pit.get_absolute_url(), 'Envio do plano desfeito com sucesso.')


@rtr()
@login_required()
def desfazer_envio_relatorio(request: HttpRequest, pk: int) -> HttpResponse:
    pit = get_object_or_404(PlanoIndividualTrabalhoV3, pk=pk)
    if not pit.pode_desfazer_envio_relatorio(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    pit.desfazer_envio_relatorio(request.user)
    return httprr(pit.get_absolute_url(), 'Envio do relatório desfeito com sucesso.')
