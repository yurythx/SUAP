import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404

from djtools.utils import (
    documento,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import AvaliarNadaConstaForm, InformarResponsaveisNadaConstaForm, ReplicarConfiguracaoNadaConstaForm, RevogarNadaConstaForm
from edu.models import Aluno, ConfiguracaoNadaConsta, NadaConsta


@permission_required('edu.view_configuracaonadaconsta')
@rtr()
def informar_responsaveis_nada_consta(request, pk):
    title = 'Informar Responsáveis'
    obj = get_object_or_404(ConfiguracaoNadaConsta, pk=pk)
    pode_realizar_procedimento = (
        request.user.has_group_cached('Administrador Acadêmico')
        or request.user.has_group_cached('Secretário Acadêmico')
        and obj.uo == request.user.get_vinculo().setor.uo
    )
    if not pode_realizar_procedimento:
        return HttpResponseForbidden()
    form = InformarResponsaveisNadaConstaForm(data=request.POST or None, instance=obj, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@login_required()
def configuracaonadaconsta(request, pk):
    title = 'Configuração de Nada Consta'
    obj = get_object_or_404(ConfiguracaoNadaConsta, pk=pk)
    return locals()


@permission_required('edu.add_configuracaonadaconsta')
@rtr()
def replicar_configuracaonadaconsta(request, pk):
    title = 'Replicar Configuração de Nada Consta'
    obj = get_object_or_404(ConfiguracaoNadaConsta, pk=pk)
    form = ReplicarConfiguracaoNadaConstaForm(data=request.POST or None)
    if request.POST and form.is_valid():
        try:
            form.processar(obj)
            return httprr('/admin/edu/configuracaonadaconsta/', 'Configuração de nada consta replicada com sucesso.')
        except ValidationError as e:
            return httprr(obj.get_absolute_url(), str(e), 'error')
    return locals()


@rtr()
def avaliar_registro_nada_consta(request, pk):
    title = 'Avaliar Nada Consta'
    obj = get_object_or_404(NadaConsta, pk=pk)
    if not obj.pode_avaliar(request.user):
        return HttpResponseForbidden()
    form = AvaliarNadaConstaForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Avaliação realizada com sucesso.')
    return locals()


@rtr()
def revogar_registro_nada_consta(request, pk):
    title = 'Revogar Nada Consta'
    obj = get_object_or_404(NadaConsta, pk=pk)
    form = RevogarNadaConstaForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        try:
            form.processar()
            obj.aluno.solicitar_quitacao_nada_consta(item_id=obj.item_configuracao_id)
        except ValidationError as e:
            return httprr('..', e.message, 'error', close_popup=True)
        return httprr('..', 'Revogação realizada com sucesso.', close_popup=True)
    return locals()


@login_required
@documento('Declaração de Nada Consta', validade=30, enumerar_paginas=False, modelo='edu.nadaconsta', exibe_emissor=True)
@rtr()
def declaracao_item_nada_consta(request, pk):
    obj = get_object_or_404(NadaConsta, pk=pk)
    if not obj.pode_gerar_declaracao():
        return httprr(f'{obj.aluno.get_absolute_url()}?tab=nada_consta', 'Não é possível gerar a declaração deste nada consta.', 'error')
    uo = obj.aluno.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()
    return locals()


@login_required
@documento('Declaração de Nada Consta', validade=30, enumerar_paginas=False, modelo='edu.aluno', exibe_emissor=True)
@rtr()
def declaracao_nada_consta(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    if not obj.pode_gerar_declaracao_nada_consta():
        return httprr(f'{obj.get_absolute_url()}?tab=nada_consta', 'Não é possível gerar a declaração deste nada consta.', 'error')
    uo = obj.curso_campus.diretoria.setor.uo
    hoje = datetime.date.today()
    return locals()
