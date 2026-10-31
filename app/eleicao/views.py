import datetime
import hashlib
import io

import qrcode
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef
from django.db.models.functions import Lower
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404

from comum.models import PrestadorServico
from comum.utils import get_sigla_reitoria
from djtools import layout
from djtools.templatetags.filters import format_datetime
from djtools.utils import XlsResponse, documento, get_client_ip, get_tabs, httprr, permission_required, render, rtr, to_ascii
from edu.models import Aluno
from eleicao.forms import (
    BuscarPublicoForm,
    CandidatoInscricaoForm,
    CandidatoValidarForm,
    ChapaInscricaoForm,
    ChapaValidarForm,
    EditarInscricaoForm,
    ValidarVotoBuscarForm,
    ValidarVotoForm,
)
from eleicao.models import Candidato, Chapa, Edital, Eleicao, Voto
from rh.models import Servidor, UnidadeOrganizacional


@layout.quadro('Eleições', icone='vote-yea', pode_esconder=True)
def index_quadros(quadro, request):
    user = request.user

    # Eleições em campanha
    eleicoes_em_campanha = Eleicao.get_em_campanha(user)
    for eleicao in eleicoes_em_campanha:
        quadro.add_item(
            layout.ItemNoticia(
                grupo='Em campanha:',
                titulo=eleicao.descricao,
                url='/eleicao/campanha/',
                chapeu=f'Até {eleicao.edital.data_campanha_fim.strftime("%d/%m/%Y %H:%M")}',
            )
        )

    # Eleições em votação
    eleicoes_em_votacao = Eleicao.get_em_votacao(user)
    for eleicao in eleicoes_em_votacao:
        if not Voto.objects.filter(eleitor=user, candidato__eleicao=eleicao).exists():
            quadro.add_item(
                layout.ItemNoticia(
                    grupo='Votação aberta',
                    titulo=eleicao.descricao,
                    url=f'/eleicao/votacao/{eleicao.id}/',
                    chapeu=f'Até {eleicao.edital.data_votacao_fim.strftime("%d/%m/%Y %H:%M")}',
                )
            )

    # Eleições com inscrição aberta
    eleicoes_em_inscricao = Eleicao.get_inscricao_aberta(user)
    for eleicao in eleicoes_em_inscricao:
        quadro.add_item(
            layout.ItemNoticia(
                grupo='Inscrições abertas:',
                titulo=eleicao.descricao,
                url=f'/eleicao/inscricao/{eleicao.id:d}/',
                chapeu=f'Até {eleicao.edital.data_inscricao_fim.strftime("%d/%m/%Y %H:%M")}',
            )
        )

    eleicoes_abertas = Eleicao.get_abertas(user)
    if eleicoes_abertas:
        # Eleições que gerencio
        if (
            user.eh_servidor
            and Edital.objects.filter(vinculos_coordenadores=user.get_vinculo(), data_resultado_final__year__gte=datetime.date.today().year).exists()
        ):
            quadro.add_item(
                layout.ItemAcessoRapido(titulo='Gerenciamento de eleições', icone='bars', url='/admin/eleicao/edital/?tab=tab_minhas_eleicoes')
            )

        # Eleições que concorri
        tem_eleicoes_participacao = Candidato.objects.filter(candidato_vinculo=user.get_vinculo())
        if tem_eleicoes_participacao:
            quadro.add_item(layout.ItemAcessoRapido(titulo='Minhas eleições', icone='bars', url='/eleicao/minhas_eleicoes/'))

        # Eleições em votação
        for eleicao in Eleicao.get_em_votacao(user):
            if Voto.objects.filter(eleitor=user, candidato__eleicao=eleicao).exists():
                quadro.add_item(layout.ItemLista(titulo='Comprovante de Votação', valor=eleicao, url=f'/eleicao/votacao/{eleicao.id}/'))

        # Resultado Preliminar
        for eleicao in eleicoes_abertas:
            if eleicao.pode_ver_resultado_preliminar(user.get_vinculo()):
                quadro.add_item(layout.ItemLista(titulo='Resultado Preliminar', valor=eleicao, url=f'/eleicao/resultado/{eleicao.id}/'))

    return quadro


@rtr()
@login_required
def votacao(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, id=eleicao_id)
    title = f'Votação para {eleicao.descricao}'
    vinculo = request.user.get_vinculo()
    candidatos = eleicao.get_candidatos_validos(vinculo)
    voto = Voto.get_por_eleicao_eleitor(eleicao, vinculo)
    if voto:
        title = 'Comprovante de Votação'
        return render('votar.html', locals())

    if not eleicao.pode_votar(vinculo):
        raise PermissionDenied

    return locals()


@rtr()
@login_required
def votar(request, candidato_id):
    title = 'Comprovante de Votação'
    candidato = get_object_or_404(Candidato, pk=candidato_id)
    vinculo = request.user.get_vinculo()
    if not candidato.eleicao.pode_votar_em(vinculo, candidato):
        raise PermissionDenied

    sub_instance = vinculo.relacionamento
    if isinstance(sub_instance, Aluno):
        campus = sub_instance.curso_campus.diretoria.setor.uo
    elif isinstance(sub_instance, PrestadorServico):
        campus = sub_instance.setor.uo
    elif isinstance(sub_instance, Servidor):
        if sub_instance.campus_lotacao_siape:
            campus = sub_instance.campus_lotacao_siape.equivalente
        elif sub_instance.campus_exercicio_siape:
            campus = sub_instance.campus_exercicio_siape.equivalente
        elif sub_instance.campus:
            campus = sub_instance.campus.equivalente

    voto = Voto.objects.create(
        eleicao=candidato.eleicao, candidato=candidato, data_voto=datetime.datetime.today(), ip=get_client_ip(request), campus=campus
    )
    voto.string_hash = f'{voto.id}|{to_ascii(voto.candidato.candidato_vinculo.pessoa.nome)}|{to_ascii(voto.eleitor.get_profile().nome)}|{format_datetime(voto.data_voto)}|{voto.ip}'.encode()
    voto.hash = hashlib.sha1(voto.string_hash).hexdigest()
    voto.save()
    return locals()


@rtr()
@login_required
def votar_branco_nulo(request, eleicao_id, tipo_voto):
    if tipo_voto not in ['branco', 'nulo']:
        raise PermissionDenied('Tipo de voto inválido')

    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    vinculo = request.user.get_vinculo()
    if not eleicao.edital.permite_voto_branco_nulo:
        raise PermissionDenied('Edital não está configurado para voto branco ou nulo.')

    sub_instance = vinculo.relacionamento
    if isinstance(sub_instance, Aluno):
        campus = sub_instance.curso_campus.diretoria.setor.uo
    elif isinstance(sub_instance, PrestadorServico):
        campus = sub_instance.setor.uo
    elif isinstance(sub_instance, Servidor):
        if sub_instance.campus_lotacao_siape:
            campus = sub_instance.campus_lotacao_siape.equivalente
        elif sub_instance.campus_exercicio_siape:
            campus = sub_instance.campus_exercicio_siape.equivalente
        elif sub_instance.campus:
            campus = sub_instance.campus.equivalente
    kwargs = {}
    if tipo_voto == 'branco':
        kwargs['eh_voto_branco'] = True
    elif tipo_voto == 'nulo':
        kwargs['eh_voto_nulo'] = True
    voto = Voto.objects.create(
        eleicao=eleicao, candidato=None, data_voto=datetime.datetime.today(), ip=get_client_ip(request), valido=True, campus=campus, **kwargs
    )
    voto.string_hash = (
        f'{voto.id}|{to_ascii(str(voto))}|{to_ascii(voto.eleitor.get_profile().nome)}|{format_datetime(voto.data_voto)}|{voto.ip}'.encode()
    )
    voto.hash = hashlib.sha1(voto.string_hash).hexdigest()
    voto.save()
    return httprr(f'/eleicao/votacao/{eleicao.pk}', 'Seu voto foi efetuado com sucesso.')


@login_required
def voto_qrcode(request, voto_id):
    voto = get_object_or_404(Voto, pk=voto_id)
    # gerando qrcode
    img = qrcode.make(voto.string_hash)
    fp = io.BytesIO()
    img.save(fp, 'png')
    return HttpResponse(fp.getvalue(), content_type='image/png')


@rtr()
@login_required
def editar_inscricao(request, candidato_id):
    candidato = get_object_or_404(Candidato, pk=candidato_id)
    title = f'Editar Inscrição para {candidato.eleicao.descricao}'
    if not candidato.pode_ser_validado():
        raise PermissionDenied

    form = EditarInscricaoForm(request.POST or None, instance=candidato)
    if form.is_valid():
        form.save()
        return httprr('/eleicao/minhas_eleicoes/', 'Inscrição atualizada com sucesso.')

    return locals()


@rtr()
@permission_required('eleicao.validar_candidato')
def validar_candidato(request, candidato_id):
    title = 'Avaliar Candidatura'
    candidato = get_object_or_404(Candidato, pk=candidato_id)
    if not candidato.eleicao.pode_validar(request.user.get_vinculo()) or not candidato.pode_ser_validado():
        raise PermissionDenied

    form = CandidatoValidarForm(request.POST or None, candidato=candidato)
    if form.is_valid():
        form.validar()
        return httprr('..', 'O candidato foi avaliado.')

    return locals()


@rtr()
@permission_required('eleicao.validar_chapa')
def validar_chapa(request, chapa_id):
    title = 'Avaliar Candidatura'
    chapa = get_object_or_404(Chapa, pk=chapa_id)
    if not chapa.eleicao.pode_validar(request.user.get_vinculo()) or not chapa.pode_ser_validado():
        raise PermissionDenied

    form = ChapaValidarForm(request.POST or None, chapa=chapa)
    if form.is_valid():
        form.validar()
        return httprr('..', 'A chapa foi avaliada.')

    return locals()


@rtr()
@login_required
def minhas_eleicoes(request):
    title = 'Minhas eleições'
    vinculo = request.user.get_vinculo()
    candidaturas = Candidato.objects.filter(candidato_vinculo=vinculo)

    sub_instance = vinculo.relacionamento
    if isinstance(sub_instance, Aluno):
        campus = sub_instance.curso_campus.diretoria.setor.uo
    elif isinstance(sub_instance, PrestadorServico):
        campus = sub_instance.setor.uo
    elif isinstance(sub_instance, Servidor):
        if sub_instance.campus_lotacao_siape:
            campus = sub_instance.campus_lotacao_siape.equivalente
        elif sub_instance.campus_exercicio_siape:
            campus = sub_instance.campus_exercicio_siape.equivalente
        elif sub_instance.campus:
            campus = sub_instance.campus.equivalente
    # Subquery para buscar a inscrição do candidato
    eleicoes_em_campanha = Eleicao.get_em_campanha(request.user)
    # Eleições em votação com informações adicionais
    eleicoes_em_votacao = Eleicao.get_em_votacao(request.user)
    # Eleições em inscrição com informações adicionais
    eleicoes_em_inscricao = Eleicao.get_inscricao_aberta(request.user)
    tem_eleicao_em_votacao = eleicoes_em_votacao.exists()
    tem_eleicao_em_campanha = eleicoes_em_campanha.exists()
    tem_eleicao_em_inscricao = eleicoes_em_inscricao.exists()
    tab_eleicoes = get_tabs(request, 'tabs/tab_minhas_eleicoes.html', modulo='eleicao', dict_context=locals())
    tab_candidaturas = get_tabs(request, 'tabs/tab_minhas_candidaturas.html', modulo='eleicao', dict_context=locals())
    return locals()


@rtr()
@login_required
def inscricao(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    vinculo = request.user.get_vinculo()
    if not eleicao.pode_inscrever(vinculo):
        raise PermissionDenied

    sub_instance = vinculo.relacionamento
    if isinstance(sub_instance, Aluno):
        campus = sub_instance.curso_campus.diretoria.setor.uo
    elif isinstance(sub_instance, PrestadorServico):
        campus = sub_instance.setor.uo
    elif isinstance(sub_instance, Servidor):
        if sub_instance.campus_lotacao_siape:
            campus = sub_instance.campus_lotacao_siape.equivalente
        elif sub_instance.campus_exercicio_siape:
            campus = sub_instance.campus_exercicio_siape.equivalente
        elif sub_instance.campus:
            campus = sub_instance.campus.equivalente

    title = f'Inscrição para {eleicao.descricao}'
    form = None
    if eleicao.tipo == Eleicao.TIPO_CHAPA:
        form = ChapaInscricaoForm(request.POST or None, eleicao=eleicao)
    else:
        candidato = Candidato()
        candidato.candidato_vinculo = vinculo
        candidato.campus = campus
        candidato.eleicao = eleicao
        form = CandidatoInscricaoForm(request.POST or None, instance=candidato, eleicao=eleicao)

    if form.is_valid():
        form.save()
        return httprr('/eleicao/minhas_eleicoes/', 'Sua inscrição foi realizada.')

    return locals()


@rtr()
@login_required
def campanha(request):
    title = 'Campanhas para Eleições'
    eleicoes = Eleicao.get_em_campanha(request.user)
    if not eleicoes:
        raise PermissionDenied

    for eleicao in eleicoes:
        eleicao.candidatos = eleicao.get_candidatos_validos(request.user.get_vinculo())

    return locals()


@rtr()
@permission_required('eleicao.add_eleicao')
def validar_votacao(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    title = f'Validar Votos: {eleicao.descricao}'
    if not eleicao.pode_homologar(request.user.get_vinculo()):
        raise PermissionDenied

    form = ValidarVotoBuscarForm(request.GET or None)
    votos = eleicao.voto_set.order_by('eleitor__vinculo__pessoa__pessoafisica__nome')
    if form.is_valid():
        votos = form.processar(votos)

    return locals()


@rtr()
@permission_required('eleicao.validar_voto')
def invalidar_voto(request, voto_id):
    title = 'Avaliar voto'
    voto = get_object_or_404(Voto, pk=voto_id)
    if not voto.eleicao.pode_homologar(request.user.get_vinculo()):
        raise PermissionDenied

    voto.valido = False
    form = ValidarVotoForm(request.POST or None, instance=voto)
    if form.is_valid():
        form.save()
        return httprr('..', 'Voto avaliado com sucesso.')

    return locals()


@rtr()
@login_required()
def dashboard_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    title = f'Dashboard: {edital.descricao}'

    if not (request.user.eh_servidor and Edital.objects.filter(vinculos_coordenadores=request.user.get_vinculo()).exists()):
        raise PermissionDenied

    eleicoes = edital.eleicao_set.all()

    return locals()


@rtr()
@login_required()
def resultado(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    title = f'Resultado: {eleicao.descricao}'
    if not eleicao.pode_ver_resultado_final(request.user.get_vinculo()) and not eleicao.pode_ver_resultado_preliminar(request.user.get_vinculo()):
        raise PermissionDenied
    candidatos = None
    campi = None
    if eleicao.resultado_global:
        candidatos = eleicao.obter_resultados()
    else:
        campi = eleicao.obter_resultados_por_campus()

    if (candidatos or campi) and eleicao.edital.permite_voto_branco_nulo:
        brancos_nulos = eleicao.obter_brancos_nulos()

    return locals()


@documento()
@rtr()
@login_required()
def resultado_pdf(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    title = f'Resultado: {eleicao.descricao}'
    if not eleicao.pode_ver_resultado_final(request.user.get_vinculo()) and not eleicao.pode_ver_resultado_preliminar(request.user.get_vinculo()):
        raise PermissionDenied

    uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
    candidatos = None
    campi = None
    if eleicao.resultado_global:
        candidatos = eleicao.obter_resultados()
    else:
        campi = eleicao.obter_resultados_por_campus()

    if (candidatos or campi) and eleicao.edital.permite_voto_branco_nulo:
        brancos_nulos = eleicao.obter_brancos_nulos()

    return locals()


@login_required()
def exportar_resultado(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    if not edital.pode_ver_resultado(request.user.get_vinculo()):
        raise PermissionDenied(f'Você não pode visualizar o resultado do edital {edital}')

    rows = [['Campus', 'Público', 'Candidato', 'Tempo na Instituição (Em anos)', 'Idade (Em anos)', 'Quantidade de votos']]
    for eleicao in edital.eleicao_set.order_by('publico'):
        obter_brancos_nulos = eleicao.obter_brancos_nulos()
        nome_publico = eleicao.publico.nome if eleicao.publico else '-'
        if eleicao.resultado_global or not eleicao.campi.all().exists():
            candidatos = eleicao.obter_resultados()
            for candidato in candidatos:
                relacionamento = candidato.candidato_vinculo.relacionamento
                row = []
                row.append(relacionamento.campus or '-')
                row.append(nome_publico)
                row.append(candidato.candidato_vinculo.pessoa.nome)
                row.append(candidato.get_tempo_na_instituicao().days / 365.25)
                data_nascimento = '-'
                if relacionamento.pessoa_fisica.nascimento_data:
                    data_nascimento = (datetime.date.today() - relacionamento.pessoa_fisica.nascimento_data).days / 365.25
                row.append(data_nascimento)
                votos = f'{candidato.qtd_votos}'
                row.append(votos)
                rows.append(row)
            if eleicao.edital.permite_voto_branco_nulo:
                rows.append(['-', nome_publico, 'Branco', '-', '-', obter_brancos_nulos.get('Geral').get('qtd_votos_brancos') or 0])
                rows.append(['-', nome_publico, 'Nulo', '-', '-', obter_brancos_nulos.get('Geral').get('qtd_votos_nulos') or 0])
        else:
            campi = eleicao.obter_resultados_por_campus()
            for campus in campi:
                if hasattr(campus, 'candidatos'):
                    for candidato in campus.candidatos:
                        row = []
                        row.append(campus.nome)
                        row.append(nome_publico)
                        row.append(candidato.candidato_vinculo.pessoa.nome)
                        row.append(candidato.get_tempo_na_instituicao().days / 365.25)
                        data_nascimento = '-'
                        if candidato.candidato_vinculo.relacionamento.pessoa_fisica.nascimento_data:
                            data_nascimento = (
                                datetime.date.today() - candidato.candidato_vinculo.relacionamento.pessoa_fisica.nascimento_data
                            ).days / 365.25
                        row.append(data_nascimento)
                        votos = f'{candidato.qtd_votos}'
                        row.append(votos)
                        rows.append(row)
                if eleicao.edital.permite_voto_branco_nulo:
                    if obter_brancos_nulos.get(campus.sigla):
                        rows.append(
                            [campus.nome, nome_publico, 'Branco', '-', '-', obter_brancos_nulos.get(campus.sigla).get('qtd_votos_brancos') or 0]
                        )
                        rows.append([campus.nome, nome_publico, 'Nulo', '-', '-', obter_brancos_nulos.get(campus.sigla).get('qtd_votos_nulos') or 0])
                    else:
                        rows.append([campus.nome, nome_publico, 'Branco', '-', '-', obter_brancos_nulos.get('Geral').get('qtd_votos_brancos') or 0])
                        rows.append([campus.nome, nome_publico, 'Nulo', '-', '-', obter_brancos_nulos.get('Geral').get('qtd_votos_nulos') or 0])

    return XlsResponse(rows)


@rtr()
@login_required()
def ver_publico(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    title = f'Público da Eleição: {eleicao}'
    vinculo = request.user.get_vinculo()
    eh_coordenador_eleicao = eleicao.edital.eh_coordenador(vinculo) or request.user.is_superuser
    votos = Voto.objects.filter(candidato__eleicao=eleicao, valido=True).select_related('eleitor')
    publico = []

    pode_ver_resultados = False
    if (eleicao.pode_ver_resultado_final(vinculo) or eleicao.pode_ver_resultado_preliminar(vinculo)) and votos.exists():
        pode_ver_resultados = True
    form = BuscarPublicoForm(request.GET or None, eleicao=eleicao)
    if form.is_valid():
        vinculos = form.processar()
    else:
        vinculos = eleicao.vinculo_publico_eleicao.all().order_by(Lower('pessoa__nome'))
    vinculos = vinculos.annotate(votou=Exists(Voto.objects.filter(eleicao=eleicao, eleitor_id=OuterRef('user_id')).values('pk'))).order_by(
        Lower('pessoa__nome')
    )
    try:
        contador = int(request.GET.get('page', 1)) - 1
    except Exception:
        contador = 0
    return locals()


@rtr()
@login_required()
def atualizar_publico(request, eleicao_id):
    eleicao = get_object_or_404(Eleicao, pk=eleicao_id)
    vinculo = request.user.get_vinculo()
    if not eleicao.edital.eh_coordenador(vinculo) and not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão para acessar essa tela.')

    eleicao.save()
    return httprr(f'/eleicao/ver_publico/{eleicao_id}/', f'Público da eleição {eleicao} foi atualizado com sucesso.')
