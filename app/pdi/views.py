from collections import OrderedDict
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.translation import ngettext

from comum.utils import get_uo
from djtools import layout
from djtools.html.graficos import GroupedColumnChart, PieChart
from djtools.utils import JsonResponse, group_required, httprr, rtr, send_notification
from pdi.forms import (
    FiltroSugestaoComunidadeForm,
    FiltroSugestaoConsolidacaoForm,
    RelatoriosForm,
    SecaoPDICampusForm,
    SecaoPDIInstitucionalForm,
    SugestaoComunidadeForm,
    SugestaoConsolidacaoForm,
)
from pdi.models import (
    PDI,
    ComissaoPDI,
    SecaoPDI,
    SecaoPDICampus,
    SecaoPDIInstitucional,
    SugestaoComunidade,
    SugestaoComunidadeUsuario,
    SugestaoConsolidacao,
    SugestaoConsolidacaoUsuario,
    TipoComissaoChoices,
)
from rh.models import Servidor, UnidadeOrganizacional


@layout.info()
def index_infos(request):
    infos = []

    cpf = request.user.get_profile().cpf
    if request.user.eh_servidor:
        pode_acessar = True  # Se é servidor logado pode acessar
    elif request.user.eh_prestador:
        pode_acessar = False  # Se é prestador logado não pode acessar
    else:
        pode_acessar = not Servidor.objects.filter(pessoa_fisica__cpf=cpf).exists()  # Se é aluno logado e não tem servidor então pode acessar

    # Não exibir para um aluno que é servidor
    if pode_acessar:
        pdi = PDI.get_atual()
        if pdi and pdi.periodo_sugestao_inicial <= date.today() <= pdi.periodo_sugestao_final:
            infos.append({'url': '/pdi/contribuicao/', 'titulo': 'Contribua com o <strong>PDI</strong>.'})
            infos.append({'url': '/pdi/contribuicoes_campi/', 'titulo': 'Veja as contribuições para o <strong>PDI</strong> do seu campus.'})

        if pdi and pdi.periodo_sugestao_melhoria_inicial <= date.today() <= pdi.periodo_sugestao_melhoria_final:
            infos.append({'url': '/pdi/contribuicao_consolidacao/', 'titulo': 'Participe da Consolidação dos Resultados do <strong>PDI</strong>.'})
    return infos


@rtr()
@login_required
def contribuicao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    title = f'Contribuições para PDI {pdi}'

    cpf = request.user.get_profile().cpf
    if request.user.get_vinculo().eh_servidor():
        pode_acessar = True  # Se é servidor logado pode acessar
    elif request.user.get_vinculo().eh_prestador():
        pode_acessar = False  # Se é prestador logado não pode acessar
    else:
        pode_acessar = not Servidor.objects.filter(pessoa_fisica__cpf=cpf).exists()  # Se é aluno logado e não tem servidor então pode acessar

    if not pode_acessar:
        return httprr('..', 'Você deve acessar o sistema como servidor para contribuir com o PDI.', tag='error')

    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    if not get_uo(request.user):
        return httprr(
            '..', 'Você não está associado a nenhum setor. Entre em contato com a coordenação do RH para regularizar sua situação.', tag='error'
        )

    periodo_contribuicao_aberto = pdi.periodo_sugestao_inicial <= date.today() <= pdi.periodo_sugestao_final
    if pdi.periodo_sugestao_inicial > date.today() or date.today() > pdi.periodo_final:
        return httprr('..', f'Período do PDI {pdi.ano} encerrado.', tag='error')

    sugestao = None
    if sugestao_id:
        sugestao = get_object_or_404(SugestaoComunidade, pk=sugestao_id)
        if sugestao.cadastrada_por != request.user or sugestao.anonima:
            raise PermissionDenied

        messages.info(
            request, 'Ao editar esta contribuição, ela voltará a ficar com a situação "Em análise" e as avaliações da comunidade serão excluídas.'
        )

    demais_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi).order_by('-id')
    if not (
        request.user.has_group_cached('Comissão Temática do PDI')
        or request.user.has_group_cached('Comissão Central do PDI')
        or request.user.has_group_cached('Administrador do PDI')
    ):
        demais_contribuicoes = demais_contribuicoes.filter(campus=get_uo(request.user))

    if pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA).exists():
        comissao = pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
        if comissao.exists():
            demais_contribuicoes = demais_contribuicoes.filter(secao_pdi__nome=comissao[0].nome)

    if request.user.has_group_cached('Comissão Temática do PDI') and request.user.has_group_cached('Comissão Central do PDI'):
        demais_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi).order_by('-id')

    minhas_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi, cadastrada_por=request.user)
    secoes = SecaoPDI.objects.filter(pdi=pdi).order_by('nome')
    secoes_contribuidas_id = minhas_contribuicoes.values_list('secao_pdi__id', flat=True)
    secoes_disponiveis = SecaoPDI.objects.filter(pdi=pdi)
    form = SugestaoComunidadeForm(request.POST or None, instance=sugestao, request=request, secoes_disponiveis=secoes_disponiveis)
    get = {}
    filtro_form = FiltroSugestaoComunidadeForm(request.GET or None, request=request)
    if request.GET and 'page' in request.GET:
        get = request.GET.dict()
        get.pop('page')
        filtro_form = FiltroSugestaoComunidadeForm(get or None, request=request)

    if filtro_form.is_valid():
        demais_contribuicoes = filtro_form.processar()
        demais_contribuicoes = demais_contribuicoes.filter(secao_pdi__pdi=pdi)

    if form.is_valid():
        if sugestao:
            sugestao.analisada = False

        msg = 'Sua contribuição foi adicionada com sucesso.'
        if form.instance.pk:
            msg = 'Sua contribuição foi alterada com sucesso.'

        form.instance.save(delete_avaliacoes=True)
        return httprr('/pdi/contribuicao/', msg)

    return locals()


@rtr()
@login_required
def remover_contribuicao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoComunidade, pk=sugestao_id)
    if sugestao.cadastrada_por != request.user:
        raise PermissionDenied

    sugestao.delete()
    return httprr('/pdi/contribuicao/', 'Contribuição removida com sucesso.')


@login_required
def concordar_contribuicao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoComunidade, pk=sugestao_id)
    if sugestao.cadastrada_por == request.user and sugestao.anonima is False:
        raise PermissionDenied

    voto, novo = SugestaoComunidadeUsuario.objects.get_or_create(sugestao=sugestao, cadastrada_por=request.user)
    concordou = True
    if novo:
        voto.concorda = True
    elif voto.concorda is True:
        voto.concorda = None
        concordou = False
    else:
        voto.concorda = True

    voto.save()
    return retorno_avaliacao(sugestao, {'concordou': concordou})


@login_required
def discordar_contribuicao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoComunidade, pk=sugestao_id)
    if sugestao.cadastrada_por == request.user:
        raise PermissionDenied

    voto, novo = SugestaoComunidadeUsuario.objects.get_or_create(sugestao=sugestao, cadastrada_por=request.user)
    discordou = True
    if novo:
        voto.concorda = False
    elif voto.concorda is False:
        voto.concorda = None
        discordou = False
    else:
        voto.concorda = False

    voto.save()
    return retorno_avaliacao(sugestao, {'discordou': discordou})


def retorno_avaliacao(sugestao, dicionario):
    qtd = sugestao.concordam().count()
    qtd_concordaram = ngettext('%(count)d pessoa concordou', '%(count)d pessoas concordaram', qtd) % {'count': qtd}
    dicionario['qtd_concordaram'] = qtd_concordaram
    qtd = sugestao.discordam().count()
    qtd_discordaram = ngettext('%(count)d pessoa não concordou', '%(count)d pessoas não concordaram', qtd) % {'count': qtd}
    dicionario['qtd_discordaram'] = qtd_discordaram
    return JsonResponse(dicionario)


@login_required
def concordar_contribuicao_consolidacao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoConsolidacao, pk=sugestao_id)
    if sugestao.cadastrada_por == request.user and sugestao.anonima is False:
        raise PermissionDenied

    voto, novo = SugestaoConsolidacaoUsuario.objects.get_or_create(sugestao=sugestao, cadastrada_por=request.user)
    concordou = True
    if novo:
        voto.concorda = True
    elif voto.concorda is True:
        voto.concorda = None
        concordou = False
    else:
        voto.concorda = True

    voto.save()
    return retorno_avaliacao(sugestao, {'concordou': concordou})


@login_required
def discordar_contribuicao_consolidacao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoConsolidacao, pk=sugestao_id)
    if sugestao.cadastrada_por == request.user:
        raise PermissionDenied

    voto, novo = SugestaoConsolidacaoUsuario.objects.get_or_create(sugestao=sugestao, cadastrada_por=request.user)
    discordou = True
    if novo:
        voto.concorda = False
    elif voto.concorda is False:
        voto.concorda = None
        discordou = False
    else:
        voto.concorda = False

    voto.save()
    return retorno_avaliacao(sugestao, {'discordou': discordou})


@rtr()
@group_required('Comissão Local do PDI')
def redigir_local(request, secao_pdi_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    if not get_comissao_local(request, get_uo(request.user)):
        return httprr('..', 'Você não está associado a nenhuma Comissão Local.', 'error')

    title = 'Proposta consolidada pela Comissão Local para esta seção do PDI'
    periodo_local_aberto = pdi and pdi.periodo_inicial <= date.today() <= pdi.data_final_local
    sugestoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi, campus=get_uo(request.user), analisada=False)

    secao_local = None
    if secao_pdi_id:
        secao_pdi = get_object_or_404(SecaoPDI, pk=secao_pdi_id)
        secao_local, criado = SecaoPDICampus.objects.get_or_create(secao_pdi=secao_pdi, campus=get_uo(request.user))
        sugestoes = sugestoes.filter(secao_pdi__id=secao_pdi_id)

    form = SecaoPDICampusForm(
        request.POST or None, request.FILES or None, instance=secao_local, request=request, periodo_local_aberto=periodo_local_aberto
    )
    if form.is_valid():
        form.save()
        return httprr(f'/pdi/redigir_local/{secao_pdi_id}', 'A proposta foi adicionada com sucesso.')

    return locals()


@rtr()
@group_required('Comissão Temática do PDI')
def redigir_tematica(request, secao_pdi_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    if not pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA):
        return httprr('..', 'Você não está associado a Comissão Temática.', 'error')

    title = 'Proposta consolidada pela Comissão Temática para esta seção do PDI'
    secoes_locais = SecaoPDICampus.objects.filter(secao_pdi__pdi=pdi)
    secao_institucional = None
    if secao_pdi_id:
        secao_pdi = get_object_or_404(SecaoPDI, pk=secao_pdi_id)
        secao_institucional, criado = SecaoPDIInstitucional.objects.get_or_create(secao_pdi=secao_pdi)
        secoes_locais = secoes_locais.filter(secao_pdi=secao_pdi)

    periodo_tematica_aberto = pdi and date.today() <= pdi.data_final_tematica
    if pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo()).exists():
        comissoes = pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo())
        for comissao in comissoes:
            if comissao.tipo == TipoComissaoChoices.TEMATICA:
                secoes_locais = secoes_locais.filter()

    form = SecaoPDIInstitucionalForm(
        request.POST or None, request.FILES or None, instance=secao_institucional, request=request, periodo_tematica_aberto=periodo_tematica_aberto
    )
    if form.is_valid():
        form.save()
        return httprr(f'/pdi/redigir_tematica/{secao_pdi_id}', 'A redação foi adicionada com sucesso.')

    return locals()


@rtr()
@group_required('Comissão Local do PDI')
def confirmar_analise_sugestao(request, sugestao_id):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoComunidade, pk=sugestao_id)
    if not request.user.has_group_cached('Comissão Local do PDI'):
        return httprr('/pdi/redigir_local/', 'Você não está associado a nenhuma Comissão Local.', 'error')

    titulo = f'[SUAP] Contribuição para a Seção {sugestao.secao_pdi} do PDI'
    corpo = (
        '<h1>PDI</h1>'
        f'<p>Agradecemos-lhe pela colaboração para a construção do PDI. Sua contribuição foi analisada pela Comissão Local e poderá compor o texto final do campus {sugestao.campus}.</p>'
    )

    msg = '.'
    if send_notification(
        titulo, corpo, settings.DEFAULT_FROM_EMAIL, [sugestao.cadastrada_por.get_vinculo()], categoria='Contribuição para Seção do PDI'
    ):
        msg = ', e uma mensagem foi enviada para o usuário.'

    sugestao.analisada = True
    sugestao.save()
    return httprr('/pdi/redigir_local/', f'A análise da contribuição foi confirmada com sucesso {msg}')


@rtr()
@group_required('Comissão Temática do PDI, Comissão Central do PDI')
def exibir_redacao_tematica(request, secao_institucional_id):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    secao_institucional = get_object_or_404(SecaoPDIInstitucional, pk=secao_institucional_id)
    title = f'Redação Temática - {secao_institucional.secao_pdi}'

    nao_participa_comissao_tematica = not pdi.comissaopdi_set.filter(
        vinculos_avaliadores=request.user.get_vinculo(), secoes=secao_institucional.secao_pdi, tipo=TipoComissaoChoices.TEMATICA
    ).exists()
    nao_participa_comissao_central = not pdi.comissaopdi_set.filter(
        vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.CENTRAL
    ).exists()
    if nao_participa_comissao_tematica and nao_participa_comissao_central:
        return httprr('..', 'Não tem permissão para acessar a redação temática.', tag='error')

    return locals()


@rtr()
@group_required('Administrador do PDI, Comissão Central do PDI, Comissão Temática do PDI, Comissão Local do PDI')
def membros(request):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    title = 'Membros das Comissões'
    comissao_central = ComissaoPDI.objects.filter(pdi=pdi, tipo=TipoComissaoChoices.CENTRAL).order_by('nome')
    comissoes_tematicas = ComissaoPDI.objects.filter(pdi=pdi, tipo=TipoComissaoChoices.TEMATICA).order_by('nome')
    comissoes_locais = ComissaoPDI.objects.filter(pdi=pdi, tipo=TipoComissaoChoices.LOCAL).order_by('nome')
    return locals()


def get_comissao_local(request, campus):
    comissao = ComissaoPDI.objects.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.LOCAL)
    comissao = comissao.filter(vinculos_avaliadores__setor__uo=campus)
    return comissao.exists() and comissao.distinct().latest('id')


def get_comissao_tematica(request, secao_pdi_id=None):
    comissao = ComissaoPDI.objects.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
    if secao_pdi_id:
        comissao = comissao.filter(secoes__id=secao_pdi_id)

    return comissao.exists() and comissao.distinct().latest('id')


@rtr()
@group_required('Administrador do PDI, Comissão Central do PDI')
def relatorios(request):
    title = 'Relatórios'
    form = RelatoriosForm(request.GET or None, request=request)

    # Organização de informações por campus
    campi = OrderedDict()
    lista = []
    if 'ano' in request.GET:
        form.is_valid()
        ano = form.cleaned_data.get('ano')
    else:
        ano = PDI.objects.latest('ano').ano
    for uo in UnidadeOrganizacional.objects.suap().all():
        sugestaocomunidade = SugestaoComunidade.objects.filter(campus=uo, secao_pdi__pdi__ano=ano)
        comissaopdi = ComissaoPDI.objects.filter(vinculos_avaliadores__setor__uo=uo, pdi__ano=ano)
        if uo.sigla not in campi:
            lista_uo = []
            contribuicoes = sugestaocomunidade.count()
            contribuicoes_nao_analisadas = sugestaocomunidade.filter(analisada=False).count()
            contribuicoes_concordam = sugestaocomunidade.filter(sugestaocomunidadeusuario__concorda=True).count()
            contribuicoes_nao_concordam = sugestaocomunidade.filter(sugestaocomunidadeusuario__concorda=False).count()
            if contribuicoes_concordam > 0 or contribuicoes_nao_concordam > 0:
                lista_uo.append(uo.sigla)
                lista_uo.append(contribuicoes_concordam)
                lista_uo.append(contribuicoes_nao_concordam)
                lista.append(lista_uo)
            membros_comissao_local = comissaopdi.filter(tipo=TipoComissaoChoices.LOCAL).count()
            membros_comissao_tematica = comissaopdi.filter(tipo=TipoComissaoChoices.TEMATICA).count()
            membros_comissao_central = comissaopdi.filter(tipo=TipoComissaoChoices.CENTRAL).count()
            campi[uo.sigla] = {
                'contribuicoes': contribuicoes,
                'contribuicoes_nao_analisadas': contribuicoes_nao_analisadas,
                'contribuicoes_concordam': contribuicoes_concordam,
                'contribuicoes_nao_concordam': contribuicoes_nao_concordam,
                'membros_comissao_local': membros_comissao_local,
                'membros_comissao_tematica': membros_comissao_tematica,
                'membros_comissao_central': membros_comissao_central,
            }

    # Organização de informações por Seção do PDI
    secoes = OrderedDict()
    for secao in SecaoPDI.objects.filter(pdi__ano=ano):
        if secao.nome not in secoes:
            contribuicoes = SugestaoComunidade.objects.filter(secao_pdi=secao, secao_pdi__pdi__ano=ano).count()
            secoes[secao.nome] = {'contribuicoes': contribuicoes}

    # Monta os gráficos
    data1 = []
    data2 = []
    data3 = []
    data4 = []
    data5 = []
    data6 = []
    for sigla, dados in list(campi.items()):
        data1.append([sigla, dados['contribuicoes']])
        if dados['contribuicoes_nao_analisadas'] > 0:
            data2.append([sigla, dados['contribuicoes_nao_analisadas']])
        if dados['membros_comissao_local'] > 0:
            data4.append([sigla, dados['membros_comissao_local']])
        if dados['membros_comissao_tematica'] > 0:
            data5.append([sigla, dados['membros_comissao_tematica']])
        if dados['membros_comissao_central'] > 0:
            data6.append([sigla, dados['membros_comissao_central']])
    for nome, dados in list(secoes.items()):
        data3.append([nome, dados['contribuicoes']])

    # Escreve gráficos
    grafico1 = PieChart(
        'grafico1',
        title='Contribuições por Campus',
        subtitle='Em percentual (%)',
        data=data1,
        dataLabels_format='<b>{point.name}</b>: {point.percentage:.2f} %',
    )
    grafico2 = PieChart(
        'grafico2',
        title='Contribuições Não Analisadas',
        subtitle='Total de contribuições não analisadas por campus',
        data=data2,
        dataLabels_format='<b>{point.name}</b>: {point.percentage:.2f} %',
    )
    grafico3 = PieChart(
        'grafico3',
        title='Contribuições por Seção do PDI',
        subtitle='Total de contribuições por Seção do PDI',
        data=data3,
        dataLabels_format='<b>{point.name}</b>: {point.percentage:.2f} %',
    )
    grafico4 = PieChart(
        'grafico4',
        title='Membros de Comissões Locais',
        subtitle='Total de membros de Comissões Locais por campus',
        data=data4,
        dataLabels_format='<b>{point.name}</b>: {point.percentage:.2f} %',
    )
    grafico5 = PieChart(
        'grafico5',
        title='Membros de Comissões Temáticas',
        subtitle='Total de membros de Comissões Temáticas por campus',
        data=data5,
        dataLabels_format='<b>{point.name}</b>: {point.percentage:.2f} %',
    )
    grafico6 = PieChart(
        'grafico6',
        title='Membros de Comissão Central',
        subtitle='Total de membros de Comissão Central por campus',
        data=data6,
        dataLabels_format='<b>{point.name}</b>: {point.percentage:.2f} %',
    )
    grafico7 = GroupedColumnChart(
        'grafico7',
        title='Avaliação das Contribuições da Comunidade',
        subtitle='Total de avaliações das contribuições da comunidade por campus',
        data=lista,
        groups=['Concordam', 'Não Concordam'],
    )

    graficos = [grafico1, grafico2, grafico3, grafico4, grafico5, grafico6, grafico7]
    graficos_id = ['grafico1', 'grafico2', 'grafico3', 'grafico4', 'grafico5', 'grafico6']

    return locals()


@rtr()
@login_required
def contribuicoes_campi(request, sugestao_id=None):
    pdi = PDI.get_atual()
    title = f'Contribuições da Comunidade para PDI {pdi}'

    cpf = request.user.get_profile().cpf
    if request.user.get_vinculo().eh_servidor():
        pode_acessar = True  # Se é servidor logado pode acessar
    elif request.user.get_vinculo().eh_prestador():
        pode_acessar = False  # Se é prestador logado não pode acessar
    else:
        pode_acessar = not Servidor.objects.filter(pessoa_fisica__cpf=cpf).exists()  # Se é aluno logado e não tem servidor então pode acessar

    # Não exibir para um aluno que é servidor
    if not pode_acessar:
        return httprr('..', 'Você deve acessar o sistema como servidor para contribuir com o PDI.', tag='error')

    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    if not get_uo(request.user):
        return httprr(
            '..', 'Você não está associado a nenhum setor. Entre em contato com a coordenação do RH para regularizar sua situação.', tag='error'
        )

    periodo_contribuicao_aberto = pdi.periodo_sugestao_inicial <= date.today() <= pdi.periodo_sugestao_final
    if pdi.periodo_sugestao_inicial > date.today() or date.today() > pdi.periodo_final:
        return httprr('..', f'Período do PDI {pdi.ano} encerrado.', tag='error')

    sugestao = None

    demais_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi).order_by('-id')
    if not (
        request.user.has_group_cached('Comissão Temática do PDI')
        or request.user.has_group_cached('Comissão Central do PDI')
        or request.user.has_group_cached('Administrador do PDI')
    ):
        demais_contribuicoes = demais_contribuicoes.filter(campus=get_uo(request.user))

    if pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA).exists():
        comissao = pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
        if comissao.exists():
            demais_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi, secao_pdi__nome=comissao[0].nome)

    if request.user.has_group_cached('Comissão Temática do PDI') and request.user.has_group_cached('Comissão Central do PDI'):
        demais_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi)
    minhas_contribuicoes = SugestaoComunidade.objects.filter(secao_pdi__pdi=pdi, cadastrada_por=request.user)
    secoes = SecaoPDI.objects.filter(pdi=pdi).order_by('nome')
    secoes_contribuidas_id = minhas_contribuicoes.values_list('secao_pdi__id', flat=True)
    secoes_disponiveis = SecaoPDI.objects.filter(pdi=pdi)
    form = SugestaoComunidadeForm(request.POST or None, instance=sugestao, request=request, secoes_disponiveis=secoes_disponiveis)
    get = {}
    filtro_form = FiltroSugestaoComunidadeForm(request.GET or None, request=request)
    if request.GET and 'page' in request.GET:
        get = request.GET.dict()
        get.pop('page')
        filtro_form = FiltroSugestaoComunidadeForm(get or None, request=request)

    if filtro_form.is_valid():
        demais_contribuicoes = filtro_form.processar()
        demais_contribuicoes = demais_contribuicoes.filter(secao_pdi__pdi=pdi)

    return locals()


@rtr()
@group_required('Administrador do PDI')
def listar_eixos(request):
    pdi = PDI.get_atual()
    if pdi:
        return httprr(f'/admin/pdi/secaopdi/?pdi__id__exact={pdi.id}')
    else:
        return httprr('/admin/pdi/secaopdi/')


@rtr()
@group_required('Administrador do PDI')
def listar_comissoes(request):
    pdi = PDI.get_atual()
    if pdi:
        return httprr(f'/admin/pdi/comissaopdi/?pdi__id__exact={pdi.id}')
    else:
        return httprr('/admin/pdi/comissaopdi/')


@rtr()
@group_required('Administrador do PDI, Comissão Central do PDI, Comissão Local do PDI, Comissão Temática do PDI')
def listar_contribuicoes(request):
    pdi = PDI.get_atual()
    if pdi:
        return httprr(f'/admin/pdi/sugestaocomunidade/?secao_pdi__pdi__id__exact={pdi.id}')
    else:
        return httprr('/admin/pdi/sugestaocomunidade/')


@rtr()
@login_required
def contribuicao_consolidacao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    title = f'Consolidação das Contribuições por Área Temática do PDI {pdi.descricao}'

    cpf = request.user.get_profile().cpf
    if request.user.get_vinculo().eh_servidor():
        pode_acessar = True  # Se é servidor logado pode acessar
    elif request.user.get_vinculo().eh_prestador():
        pode_acessar = False  # Se é prestador logado não pode acessar
    else:
        pode_acessar = not Servidor.objects.filter(pessoa_fisica__cpf=cpf).exists()  # Se é aluno logado e não tem servidor então pode acessar

    # Não exibir para um aluno que é servidor
    if not pode_acessar:
        return httprr('..', 'Você deve acessar o sistema como servidor para contribuir com o PDI.', tag='error')

    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    if not get_uo(request.user):
        return httprr(
            '..', 'Você não está associado a nenhum setor. Entre em contato com a coordenação do RH para regularizar sua situação.', tag='error'
        )

    periodo_consolidacao_aberto = pdi.periodo_sugestao_melhoria_inicial <= date.today() <= pdi.periodo_sugestao_melhoria_final

    if pdi.periodo_inicial > date.today() or date.today() > pdi.periodo_final:
        return httprr('..', f'Período do PDI {pdi.ano} encerrado.', tag='error')

    sugestao = None
    if sugestao_id:
        sugestao = get_object_or_404(SugestaoConsolidacao, pk=sugestao_id)
        if sugestao.cadastrada_por != request.user or sugestao.anonima:
            raise PermissionDenied

        messages.info(
            request, 'Ao editar esta contribuição, ela voltará a ficar com a situação "Em análise" e as avaliações da comunidade serão excluídas.'
        )

    demais_contribuicoes = SugestaoConsolidacao.objects.filter(secao_pdi__pdi=pdi).order_by('-id')
    if not (
        request.user.has_group_cached(name='Comissão Temática do PDI')
        or request.user.has_group_cached(name='Comissão Central do PDI')
        or request.user.has_group_cached(name='Administrador do PDI')
    ):
        demais_contribuicoes = demais_contribuicoes.filter(campus=get_uo(request.user))

    if pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA).exists():
        comissao = pdi.comissaopdi_set.filter(vinculos_avaliadores=request.user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
        if comissao.exists():
            demais_contribuicoes = demais_contribuicoes.filter(secao_pdi__nome=comissao[0].nome)

    if request.user.has_group_cached('Comissão Temática do PDI') and request.user.has_group_cached('Comissão Central do PDI'):
        demais_contribuicoes = SugestaoConsolidacao.objects.filter(secao_pdi__pdi=pdi).order_by('-id')

    minhas_contribuicoes = SugestaoConsolidacao.objects.filter(secao_pdi__pdi=pdi, cadastrada_por=request.user)
    secoes = SecaoPDI.objects.filter(pdi=pdi).order_by('nome')
    redacao_tematica = SecaoPDIInstitucional.objects.filter(secao_pdi__in=secoes)
    secoes_contribuidas_id = minhas_contribuicoes.values_list('secao_pdi__id', flat=True)
    secoes_disponiveis = SecaoPDI.objects.filter(pdi=pdi)
    form = SugestaoConsolidacaoForm(request.POST or None, instance=sugestao, request=request, secoes_disponiveis=secoes_disponiveis)
    get = {}
    filtro_form = FiltroSugestaoConsolidacaoForm(request.GET or None, request=request)
    if request.GET and 'page' in request.GET:
        get = request.GET.dict()
        get.pop('page')
        filtro_form = FiltroSugestaoConsolidacaoForm(get or None, request=request)

    if filtro_form.is_valid():
        demais_contribuicoes = filtro_form.processar()
        demais_contribuicoes = demais_contribuicoes.filter(secao_pdi__pdi=pdi)

    if form.is_valid():
        if sugestao:
            sugestao.analisada = False

        msg = 'Sua contribuição foi adicionada com sucesso.'
        if form.instance.pk:
            msg = 'Sua contribuição foi alterada com sucesso.'

        form.instance.save(delete_avaliacoes=True)
        return httprr('/pdi/contribuicao_consolidacao/', msg)

    return locals()


@rtr()
@login_required
def remover_contribuicao_consolidacao(request, sugestao_id=None):
    pdi = PDI.get_atual()
    if not pdi:
        return httprr('..', 'Não existe PDI cadastrado.', tag='error')

    sugestao = get_object_or_404(SugestaoConsolidacao, pk=sugestao_id)
    if sugestao.cadastrada_por != request.user:
        raise PermissionDenied

    sugestao.delete()
    return httprr('/pdi/contribuicao_consolidacao/', 'Contribuição removida com sucesso.')
