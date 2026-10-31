from datetime import datetime, timedelta

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from boletim_servico import models
from boletim_servico.forms import GerarBoletimMesForm
from comum.utils import get_uo
from djtools.utils import group_required, httprr, rtr

from .models import BoletimPeriodo
from .tasks import gerar_boletim


def boletins_publicos(request):
    modeladmin = admin.site._registry[models.BoletimPeriodo]  # Obtém model admin da classe
    return modeladmin.changelist_view(request)


@rtr()
@group_required('Gerente Sistêmico de Boletins de Serviço, Gerente de Boletins de Serviço')
def gerar_boletim_servico(request, boletim_programado_pk):
    boletim_programado = models.BoletimProgramado.objects.filter(pk=boletim_programado_pk).first()
    if not boletim_programado:
        return httprr('/admin/boletim_servico/boletimprogramado/', 'Boletim programado não encontrado.', 'error')
    user = request.user
    uo = get_uo(user)
    if user.groups.filter(name='Gerente de Boletins de Serviço') and boletim_programado.campus != uo:
        return httprr('/admin/boletim_servico/boletimprogramado/', 'Você não tem permissão para gerar este boletim.', 'error')
    if boletim_programado.programado:
        try:
            return boletim_programado.gerar_boletim_diario()
        except ValidationError as e:
            return httprr('/admin/boletim_servico/boletimprogramado/', e.messages[0], 'error')
    elif boletim_programado.programado_semanal:
        try:
            return boletim_programado.gerar_boletim_semanal()
        except ValidationError as e:
            return httprr('/admin/boletim_servico/boletimprogramado/', e.messages[0], 'error')
    elif boletim_programado.programado_mensal:
        form = GerarBoletimMesForm(request.GET or None, request=request)
        if form.is_valid():
            cleaned_data = form.cleaned_data
            ano = cleaned_data.get('ano', 0)
            mes = cleaned_data.get('mes', 0)
            data = datetime(ano, mes, 28) + timedelta(days=5)
            try:
                return boletim_programado.gerar_boletim_mensal(data=data)
            except ValidationError as e:
                return httprr('/admin/boletim_servico/boletimprogramado/', e.messages[0], 'error')
        return locals()


@rtr()
@group_required('Gerente Sistêmico de Boletins de Serviço')
def reprocessar_boletim(request, boletim_pk):
    try:
        boletim = get_object_or_404(BoletimPeriodo, id=boletim_pk)
        return gerar_boletim(boletim, somente_documentos=False, reprocessamento=True)
    except ValidationError as e:
        return httprr('/admin/boletim_servico/boletimperiodo/', e.messages[0], 'error')


@rtr()
@group_required('Gerente Sistêmico de Boletins de Serviço')
def remover_boletim_periodo(request, boletim_pk):
    try:
        boletim = get_object_or_404(BoletimPeriodo, id=boletim_pk)

        if not request.user.has_perm('boletim_servico.delete_boletimperiodo'):
            return httprr(request.META.get('HTTP_REFERER'), 'Você não tem permissão para remover o boletim de serviço.')

        boletim.delete()
        return httprr(request.META.get('HTTP_REFERER'), 'Boletim removido com sucesso.')
    except Exception as e:
        return httprr(request.META.get('HTTP_REFERER'), e, 'error')
