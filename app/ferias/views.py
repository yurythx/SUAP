from django.core.exceptions import PermissionDenied
from django.dispatch import receiver
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404

from djtools.html.calendarios import Calendario
from djtools.utils import permission_required, render_to_string, rtr
from ferias.forms import CalendarioFeriasFormFactory
from ferias.models import Ferias
from rh.models import Servidor, ServidorAfastamento
from rh.views import rh_servidor_view_tab


@rtr()
@permission_required('ferias.view_ferias')
def ver_ferias_servidor(request, ano, servidor_matricula):
    is_rh = request.user.has_perm('rh.change_servidor')

    servidor_consultado = get_object_or_404(Servidor, matricula=servidor_matricula)
    is_chefe = False
    servidor = request.user.get_relacionamento()
    if request.user.eh_servidor:
        is_chefe = servidor.eh_chefe_de(servidor_consultado)
    verificacao_propria = request.user == servidor_consultado.get_user()

    pode_ver_ferias = request.user.has_perm('rh.pode_ver_ferias_servidor') or verificacao_propria or is_chefe or is_rh

    if not pode_ver_ferias:
        raise PermissionDenied('Não é possível visualizar a férias deste servidor.')
    title = f'Férias {ano} do Servidor: {servidor_consultado}'
    ferias = Ferias.objects.get(servidor=servidor_consultado, ano__ano=ano)
    return locals()


@rtr()
@permission_required('ferias.view_ferias')
def ver_ferias(request, ano, servidor_matricula):
    is_rh = request.user.has_perm('rh.change_servidor')
    servidor_consultado = get_object_or_404(Servidor, matricula=servidor_matricula)
    pessoa_logada = request.user.get_relacionamento()
    is_chefe = False
    if request.user.eh_servidor:
        is_chefe = pessoa_logada.eh_chefe_de(servidor_consultado)
    verificacao_propria = request.user == servidor_consultado.get_user()
    pode_ver_ferias = verificacao_propria or is_chefe or is_rh or request.user.has_perm('rh.pode_ver_ferias_servidor')
    if not pode_ver_ferias:
        raise PermissionDenied('Não é possível visualizar a férias deste servidor.')
    ferias = Ferias.objects.filter(servidor=servidor_consultado, ano__ano=ano).first()
    return locals()


@permission_required('ferias.view_ferias')
def redirect_ferias_por_uo(request):
    url = '/admin/ferias/ferias/?cadastrado__exact=1&incluir_sub_setores=NAO'
    servidor = request.user.get_relacionamento()
    if request.user.eh_servidor and servidor.campus:
        url = url + f'&uo={servidor.campus.id}'
    return HttpResponseRedirect(url)


@rtr()
@permission_required('ferias.pode_ver_calendario_ferias_setor')
def calendario_ferias_setor(request):
    title = 'Calendário de Férias por Setor'
    FormClass = CalendarioFeriasFormFactory(request.user)
    form = FormClass(request.POST or None)
    if form.is_valid():
        ano_inicio = form.cleaned_data['ano_inicio']
        ano_fim = form.cleaned_data['ano_fim']
        setor = form.cleaned_data['setor']
        incluir_subsetores = form.cleaned_data.get('incluir_subsetores')
        pessoa_fisica = request.user.get_profile()

        # cal.adicionar_evento_calendario(liberacao.data_inicio, liberacao.data_fim, liberacao.descricao, css)
        calendario_ferias = Calendario(tipos_eventos_default=False)
        calendario_ferias.adicionar_tipo_evento('info', 'Férias de 1 servidor')
        calendario_ferias.adicionar_tipo_evento('warning', 'Conflito entre 2 servidores')
        calendario_ferias.adicionar_tipo_evento('danger', 'Conflito entre 3 ou mais servidores')
        calendario_ferias.adicionar_tipo_evento('extra', 'Afastamento')
        calendarios = {}

        servidores_setor = Servidor.objects.none()

        if incluir_subsetores:
            servidores_setor = Servidor.objects.ativos_permanentes().filter(setor__in=setor.descendentes).distinct()
        else:
            servidores_setor = Servidor.objects.ativos_permanentes().filter(setor=setor)

        anos = list(range(ano_inicio.ano - 2, ano_fim.ano + 1))
        ferias_servidores = Ferias.objects.filter(servidor__in=servidores_setor, ano__ano__in=anos)

        afastamentos_servidores = ServidorAfastamento.objects.filter(
            servidor__in=servidores_setor, data_termino__year__lte=ano_fim.ano, cancelado=False
        )

        for afastamento in afastamentos_servidores:
            calendario_ferias.adicionar_evento_calendario(
                afastamento.data_inicio,
                afastamento.data_termino,
                f'{afastamento.servidor.pessoa_fisica.nome_usual} - {afastamento.afastamento.nome}',
                'extra',
            )

        for fe in ferias_servidores:
            if fe.parcelaferias_set.exists():
                for parcela in fe.parcelaferias_set.all():
                    calendario_ferias.adicionar_evento_calendario(
                        parcela.data_inicio, parcela.data_fim, f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano}', 'info'
                    )
            else:
                data_interrupcao_periodo1 = None
                data_interrupcao_periodo2 = None
                data_interrupcao_periodo3 = None
                if fe.interrupcaoferias_set.all().exists():
                    for interrupcao in fe.interrupcaoferias_set.all():
                        if interrupcao.data_inicio_continuacao_periodo and interrupcao.data_fim_continuacao_periodo:
                            calendario_ferias.adicionar_evento_calendario(
                                interrupcao.data_inicio_continuacao_periodo,
                                interrupcao.data_fim_continuacao_periodo,
                                f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}',
                                'info',
                            )
                        if fe.data_inicio_periodo1 <= interrupcao.data_interrupcao_periodo < fe.data_fim_periodo1:
                            data_interrupcao_periodo1 = interrupcao.data_interrupcao_periodo
                        if fe.data_inicio_periodo2 and fe.data_inicio_periodo2 <= interrupcao.data_interrupcao_periodo < fe.data_fim_periodo2:
                            data_interrupcao_periodo2 = interrupcao.data_interrupcao_periodo
                        if fe.data_inicio_periodo3 and fe.data_inicio_periodo3 <= interrupcao.data_interrupcao_periodo < fe.data_fim_periodo3:
                            data_interrupcao_periodo3 = interrupcao.data_interrupcao_periodo
                if data_interrupcao_periodo1:
                    calendario_ferias.adicionar_evento_calendario(
                        fe.data_inicio_periodo1, data_interrupcao_periodo1, f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}', 'info'
                    )
                else:
                    if fe.data_inicio_periodo1 and fe.data_fim_periodo1:
                        calendario_ferias.adicionar_evento_calendario(
                            fe.data_inicio_periodo1, fe.data_fim_periodo1, f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}', 'info'
                        )
                if fe.data_inicio_periodo2:
                    if data_interrupcao_periodo2:
                        calendario_ferias.adicionar_evento_calendario(
                            fe.data_inicio_periodo2,
                            data_interrupcao_periodo2,
                            f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}',
                            'info',
                        )
                    else:
                        calendario_ferias.adicionar_evento_calendario(
                            fe.data_inicio_periodo2, fe.data_fim_periodo2, f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}', 'info'
                        )
                if fe.data_inicio_periodo3:
                    if data_interrupcao_periodo3:
                        calendario_ferias.adicionar_evento_calendario(
                            fe.data_inicio_periodo3,
                            data_interrupcao_periodo3,
                            f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}',
                            'info',
                        )
                    else:
                        calendario_ferias.adicionar_evento_calendario(
                            fe.data_inicio_periodo3, fe.data_fim_periodo3, f'{fe.servidor.pessoa_fisica.nome_usual} - {fe.ano.ano!s}', 'info'
                        )
        for ano in range(ano_inicio.ano, ano_fim.ano + 1):
            calendarios[ano] = calendario_ferias.formato_ano(ano)

    return locals()


# View que se conecta a view rh.views.servidor
@receiver(rh_servidor_view_tab)
def servidor_view_tab_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    pode_ver_ferias_servidor = request.user.has_perm('rh.pode_ver_ferias_servidor') or verificacao_propria or eh_chefe

    if pode_ver_ferias_servidor:
        qs_ferias = Ferias.objects.filter(servidor=servidor).order_by('-ano__ano').select_related('ano')
        ultima_ferias = qs_ferias.first()
        ultimo_ano_ferias = ultima_ferias.ano.ano if ultima_ferias else None

        return render_to_string(
            template_name='ferias/templates/servidor_view_tab.html',
            context={'lps_context': {'nome_modulo': 'ferias'}, 'servidor': servidor, 'ultimo_ano_ferias': ultimo_ano_ferias, 'qs_ferias': qs_ferias},
            request=request,
        )
    return False
