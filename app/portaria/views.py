from datetime import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.models import Configuracao, Vinculo
from comum.utils import get_uo
from djtools import layout
from djtools.utils import cpf_valido, group_required, httprr, mask_cpf, permission_required, rtr, send_notification, to_ascii
from edu.models import settings
from integracao_wifi.utils import gerar_chave_rucks
from portaria.forms import (
    AcessoExternoForm,
    AcessoInternoForm,
    BaixaEmAcessoForm,
    CadastrarVisitanteForm,
    ListarAcessosCampusForm,
    ListarHistoricoAcessoGeralForm,
    ListarPessoasForm,
    RegistrarChaveWifiForm,
)
from portaria.models import Acesso, AcessoExterno, AcessoInterno, SolicitacaoEntrada, Visitante
from portaria.util import get_configuracao


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_group_cached('Coordenador da Sede', ignore_groups_if_superuser=False):
        solicitacoes_a_validar = SolicitacaoEntrada.objects.filter(
            sala__predio__uo=get_uo(request.user), deferida__isnull=True, cancelada=False
        ).count()
        if solicitacoes_a_validar:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(solicitacoes_a_validar, "ão,ões")} de Entrada no Campus',
                    'subtitulo': 'a validar',
                    'qtd': solicitacoes_a_validar,
                    'url': '/admin/portaria/solicitacaoentrada/?tab=tab_a_validar',
                }
            )

    return pendencias


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def cadastrar_pessoa_externa(request):
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    title = f'Cadastrar Pessoa (Sem Vínculo com o {instituicao})'

    link_voltar = retornar_lista_pessoas(request)

    usa_camera = get_configuracao('habilitar_camera')

    if request.method == 'GET':
        form = CadastrarVisitanteForm(request=request)
    else:
        form = CadastrarVisitanteForm(request.POST, request=request)
        if form.is_valid():
            obj_pe = form.save()

            if form.cleaned_data.get('foto'):
                obj_pe.foto.save(f've_{obj_pe.pk}.jpg', ContentFile(form.cleaned_data['foto']))
                obj_pe.save()

            if form.cleaned_data.get('registrar_acesso'):
                return httprr(f'/portaria/registrar_acesso_pessoa_externa/{obj_pe.pk}/', 'Pessoa Externa cadastrada com sucesso.')
            else:
                return httprr('..', 'Pessoa Externa cadastrada com sucesso.')

    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def alterar_pessoa_externa(request, visitante_id):
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    title = f'Alterar Pessoa (Sem Vínculo com o {instituicao})'

    link_voltar = retornar_lista_pessoas(request)

    pessoa_externa = get_object_or_404(Visitante, pk=visitante_id)
    # foto_atual = pessoa_externa.get_foto_150x200_url()

    usa_camera = get_configuracao('habilitar_camera')

    form = CadastrarVisitanteForm(data=request.POST or None, instance=pessoa_externa, request=request)
    if form.is_valid():
        obj_pe = form.save()

        if form.cleaned_data.get('foto'):
            obj_pe.foto.save(f've_{obj_pe.pk}.jpg', ContentFile(form.cleaned_data['foto']))
            obj_pe.save()
        return httprr('..', 'Pessoa Externa alterada com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico')
def visualizar_pessoa_externa(request, visitante_id):
    pessoa_externa = get_object_or_404(Visitante, pk=visitante_id)
    foto_atual = pessoa_externa.get_foto_150x200_url()

    title = f'Visualizar {pessoa_externa.nome}'

    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def registro_acesso_campus(request):
    try:
        title = f'Visitas ao Campus: {get_uo(request.user).nome}'
    except Exception:
        return httprr('/', 'Usuário sem campus associado.', 'error')

    form = ListarAcessosCampusForm(request.GET or None)

    qs_ai = AcessoInterno.objects.all()
    qs_ae = AcessoExterno.objects.all()
    qs_ai = qs_ai.filter(local_acesso__sigla=get_uo(request.user))
    qs_ae = qs_ae.filter(local_acesso__sigla=get_uo(request.user))

    if form.is_valid() and ((form.cleaned_data.get('plac')) or (form.cleaned_data.get('filtro'))):
        if form.cleaned_data['plac']:
            # Pessoa com vinculo com o IFRN - Nome, Usuario (matricula de aluno ou SIAPE), Chave WIFI
            # Não busca por CPF
            qs_ai = qs_ai.filter(
                Q(
                    vinculo__user__username=(
                        mask_cpf(form.cleaned_data['plac']) if (cpf_valido(form.cleaned_data['plac'])) else form.cleaned_data['plac']
                    )
                )
                | Q(vinculo__pessoa__nome__icontains=form.cleaned_data['plac'])
                | Q(cracha=form.cleaned_data['plac'])
            )

            # Pessoa SEM vinculo com o IFRN - Nome, RG, CPF, Chave WIFI
            qs_ae = qs_ae.filter(
                Q(pessoa_externa__rg=form.cleaned_data['plac'])
                | Q(
                    pessoa_externa__cpf=(
                        mask_cpf(form.cleaned_data['plac']) if (cpf_valido(form.cleaned_data['plac'])) else form.cleaned_data['plac']
                    )
                )
                | Q(pessoa_externa__nome__unaccent__icontains=form.cleaned_data['plac'])
                | Q(cracha=form.cleaned_data['plac'])
            )

        if form.cleaned_data['filtro'] == 'hoje':
            hoje = datetime.now()
            inicio = datetime(hoje.year, hoje.month, hoje.day, 0, 0, 0)
            final = datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)
            qs_ai = qs_ai.filter(data_hora_entrada__range=(inicio, final))
            qs_ae = qs_ae.filter(data_hora_entrada__range=(inicio, final))

        if form.cleaned_data['filtro'] == 'nestemes':
            hoje = datetime.now()
            inicio = datetime(hoje.year, hoje.month, 1, 0, 0, 0)
            final = datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)
            qs_ai = qs_ai.filter(data_hora_entrada__range=(inicio, final))
            qs_ae = qs_ae.filter(data_hora_entrada__range=(inicio, final))

    else:
        # Por padrao lista os acessos de HOJE
        hoje = datetime.now()
        inicio = datetime(hoje.year, hoje.month, hoje.day, 0, 0, 0)
        final = datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)
        qs_ai = qs_ai.filter(data_hora_entrada__range=(inicio, final))
        qs_ae = qs_ae.filter(data_hora_entrada__range=(inicio, final))

    qs_ai = qs_ai.extra(select={'is_interno': True}).all()
    qs_ae = qs_ae.extra(select={'is_interno': False}).all()

    is_gerar_chave_wifi = get_configuracao('habilitar_geracao_chave_wifi')

    lista_acessos = list(qs_ai) + list(qs_ae)
    lista_acessos.sort(key=lambda a: a.data_hora_entrada, reverse=True)

    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def listar_pessoas(request):
    def order_by_nome(pessoa):
        return pessoa.nome.strip()

    try:
        title = f'Registrar Visita(s) ao Campus {get_uo(request.user).nome}'
    except Exception:
        return httprr('/', 'Usuário sem setor associado.', 'error')

    form = ListarPessoasForm(request.GET or None)

    if form.is_valid():
        # Nao busca por CPF
        tipo_pessoa = form.cleaned_data.get('tipo_pessoa')
        termo = to_ascii(form.cleaned_data.get('pb_pessoa'))
        if tipo_pessoa == '1':
            vinculos = (
                Vinculo.objects.filter(pessoa__pessoafisica__isnull=False, ativo=True)
                .filter(
                    Q(pessoa__nome__icontains=termo)
                    | Q(user__username__icontains=termo)
                    | Q(pessoa__pessoafisica__cpf=(mask_cpf(termo) if cpf_valido(termo) else termo))
                    | Q(pessoa__pessoafisica__rg=termo)
                )
                .order_by('pessoa__nome')
            )
        # Busca por Pessoa Externa - Nome, CPF, RG
        elif tipo_pessoa == '0':
            visitantes = Visitante.objects.filter(
                Q(nome__unaccent__icontains=termo) | Q(cpf=(mask_cpf(termo) if (cpf_valido(termo)) else termo)) | Q(rg=termo)
            ).order_by('nome')

    return locals()


@rtr('portaria/templates/registrar_acesso_pessoa_interna.html')
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def registrar_acesso_pessoa(request, vinculo_id):
    try:
        title = f'Registrar Visita de Pessoa ao Campus {get_uo(request.user).nome}'
    except Exception:
        return httprr('/', 'Usuário sem setor associado.', 'error')

    link_voltar = retornar_lista_pessoas(request)

    acesso_interno = AcessoInterno()
    acesso_interno.vinculo = get_object_or_404(Vinculo, pk=vinculo_id)
    acesso_interno.local_acesso = get_uo(request.user)
    acesso_interno.user_entrada = request.user

    form = AcessoInternoForm(request.POST or None, instance=acesso_interno, request=request)

    if form.is_valid():
        obj = form.save()
        if form.cleaned_data.get('gerar_chave_wifi'):
            dias = form.cleaned_data.get('quantidade_dias_chave_wifi') or 1
            gerar_chave_wifi(request, obj.id, dias)
        return httprr('/portaria/registro_acesso_campus/', 'Registro da Visita realizado com sucesso')

    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def registrar_acesso_pessoa_externa(request, visitante_id):
    try:
        title = f'Registrar Visita ao Campus {get_uo(request.user).nome}'
    except Exception:
        return httprr('/', 'Usuário sem setor associado.', 'error')
    link_voltar = retornar_lista_pessoas(request)

    acesso_externo = AcessoExterno()
    acesso_externo.pessoa_externa = get_object_or_404(Visitante, pk=visitante_id)
    acesso_externo.local_acesso = get_uo(request.user)
    acesso_externo.user_entrada = request.user

    form = AcessoExternoForm(request.POST or None, instance=acesso_externo, request=request)

    if form.is_valid():
        obj = form.save()
        if form.cleaned_data.get('gerar_chave_wifi'):
            dias = form.cleaned_data.get('quantidade_dias_chave_wifi') or 1
            try:
                gerar_chave_wifi(request, obj.id, dias)
            except Exception:
                return httprr('/portaria/registro_acesso_campus/', 'Erro ao tentar gerar chave wifi.', 'error')
        return httprr('/portaria/registro_acesso_campus/', 'Registro da Visita realizado com sucesso')

    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def registrar_chave_wifi(request):
    title = 'Confirma a geração da chave de acesso ao WI-FI?'

    if request.method == 'POST':
        form = RegistrarChaveWifiForm(request.POST)
        if form.is_valid():
            dias = form.cleaned_data.get('quantidade_dias_chave_wifi') or 1
            gerar_chave_wifi(request, form.cleaned_data.get('acesso_id'), dias)
            return httprr('..')
    else:
        form = RegistrarChaveWifiForm(initial={'acesso_id': request.GET['ida']})

    return locals()


@rtr()
@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def cadastrar_baixa_em_acesso(request):
    title = 'Confirma o registro da saída?'

    if request.method == 'POST':
        form = BaixaEmAcessoForm(request.POST)
        if form.is_valid():
            acesso = Acesso.objects.get(id=form.cleaned_data['acesso_id'])
            acesso.data_hora_saida = datetime.today()
            acesso.user_saida = request.user
            acesso.save()
            return httprr('..', 'Saída registrada com sucesso.')
    else:
        form = BaixaEmAcessoForm(initial={'acesso_id': request.GET['ida']})

    return locals()


@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def gerar_chave_wifi(request, acesso_id, dias=1):
    # Gera chave de wi-fi para acesso de pessoa externa e interna
    acesso = get_object_or_404(Acesso, pk=acesso_id)
    #
    if isinstance(acesso.sub_instance(), AcessoExterno):
        pessoa = acesso.sub_instance().pessoa_externa
        identificador = pessoa.get_identificador()
    else:
        pessoa = acesso.sub_instance().vinculo.pessoa
        identificador = pessoa.get_cpf_ou_cnpj()
    #
    acesso.chave_wifi = gerar_chave_rucks(identificador)
    acesso.quantidade_dias_chave_wifi = dias
    acesso.user_geracao_chave_wifi = request.user
    acesso.data_geracao_chave_wifi = datetime.today()
    acesso.save()

    messages.add_message(request, messages.SUCCESS, f'Chave do WI-FI gerada com sucesso: {acesso.chave_wifi}')
    return acesso.chave_wifi


@rtr()
@group_required('Coordenador de Visitantes Sistêmico')
def listar_historico_acesso_geral(request):
    title = 'Histórico Geral de Visitas'

    form = ListarHistoricoAcessoGeralForm(request.GET or None)

    if form.is_valid():
        qs_ai = AcessoInterno.objects.all()
        qs_ae = AcessoExterno.objects.all()

        if form.cleaned_data['valor']:
            # Pessoa com vinculo com o IFRN - Nome, Usuario (matricula de aluno ou SIAPE), Chave WIFI
            qs_ai = qs_ai.filter(
                Q(pk=(int(form.cleaned_data['valor']) if (form.cleaned_data['valor'].isdigit()) else 0))
                | Q(vinculo__user__username=('' if (cpf_valido(form.cleaned_data['valor'])) else form.cleaned_data['valor']))
                | Q(vinculo__pessoa__nome__icontains=form.cleaned_data['valor'])
                | Q(cracha=form.cleaned_data['valor'])
                | Q(chave_wifi=form.cleaned_data['valor'])
            )
            # Pessoa SEM vinculo com o IFRN - Nome, RG, CPF, Chave WIFI
            qs_ae = qs_ae.filter(
                Q(pk=(int(form.cleaned_data['valor']) if (form.cleaned_data['valor'].isdigit()) else 0))
                | Q(pessoa_externa__rg=form.cleaned_data['valor'])
                | Q(
                    pessoa_externa__cpf=(
                        mask_cpf(form.cleaned_data['valor']) if (cpf_valido(form.cleaned_data['valor'])) else form.cleaned_data['valor']
                    )
                )
                | Q(pessoa_externa__nome__unaccent__icontains=form.cleaned_data['valor'])
                | Q(cracha=form.cleaned_data['valor'])
                | Q(chave_wifi=form.cleaned_data['valor'])
            )

        if form.cleaned_data['campus']:
            qs_ai = qs_ai.filter(Q(local_acesso__sigla=form.cleaned_data['campus']))
            qs_ae = qs_ae.filter(Q(local_acesso__sigla=form.cleaned_data['campus']))

        if form.cleaned_data['data_inicial'] and form.cleaned_data['data_final']:
            qs_ai = qs_ai.filter(data_hora_entrada__range=(form.cleaned_data['data_inicial'], form.cleaned_data['data_final']))
            qs_ae = qs_ae.filter(data_hora_entrada__range=(form.cleaned_data['data_inicial'], form.cleaned_data['data_final']))

        qs_ai = qs_ai.extra(select={'is_interno': True}).all()
        qs_ae = qs_ae.extra(select={'is_interno': False}).all()

        lista_acessos = list(qs_ai) + list(qs_ae)
        lista_acessos.sort(key=lambda a: a.data_hora_entrada, reverse=True)

    return locals()


@group_required('Coordenador de Visitantes Sistêmico, Operador de Visitantes')
def retornar_lista_pessoas(request):
    bc = request.session.get('bc', ())
    for link in bc:
        if 'pb_pessoa=' in link[1]:
            return link[1]
    return '/portaria/listar_pessoas/'


@rtr()
@group_required('Coordenador da Sede')
def deferir_solicitacaoentrada(request, solicitacaoentrada_id):
    solicitacaoentrada = get_object_or_404(SolicitacaoEntrada, pk=solicitacaoentrada_id)
    solicitacaoentrada.deferida = True
    solicitacaoentrada.save()

    titulo = '[SUAP] Validação de Solicitação de Entrada'
    texto = []
    texto.append('<h1>Validação de Solicitação de Entrada</h1>')
    texto.append('<h2>A sua solicitação foi <strong>deferida</strong></h2>')
    texto.append('<dl>')
    texto.append('<dt>Data:</dt><dd>{}</dd>'.format(solicitacaoentrada.data.strftime('%d/%m/%Y')))
    texto.append(f'<dt>Horário:</dt><dd>{solicitacaoentrada.hora_entrada} às {solicitacaoentrada.hora_saida}</dd>')
    texto.append(f'<dt>Sala:</dt><dd>{solicitacaoentrada.sala}</dd>')
    texto.append(f'<dt>Atividade a ser realizada:</dt><dd>{solicitacaoentrada.atividade}</dd>')
    texto.append(f'<dt>Solicitante(s):</dt><dd>{solicitacaoentrada.get_solicitantes()}</dd>')
    texto.append('</dl>')
    texto.append(
        '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
            settings.SITE_URL, solicitacaoentrada.get_absolute_url()
        )
    )

    for solicitante in solicitacaoentrada.solicitantes.all():
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitante])

    return httprr('/admin/portaria/solicitacaoentrada/?cancelada__exact=0', 'A solicitação de entrada foi deferida.')


@rtr()
@group_required('Coordenador da Sede')
def indeferir_solicitacaoentrada(request, solicitacaoentrada_id):
    solicitacaoentrada = get_object_or_404(SolicitacaoEntrada, pk=solicitacaoentrada_id)
    solicitacaoentrada.deferida = False
    solicitacaoentrada.save()

    titulo = '[SUAP] Validação de Solicitação de Entrada'
    texto = []
    texto.append('<h1>Validação de Solicitação de Entrada</h1>')
    texto.append('<h2>A sua solicitação foi <strong>indeferida</strong></h2>')
    texto.append('<dl>')
    texto.append('<dt>Data:</dt><dd>{}</dd>'.format(solicitacaoentrada.data.strftime('%d/%m/%Y')))
    texto.append(f'<dt>Hora da Entrada:</dt><dd>{solicitacaoentrada.hora_entrada}</dd>')
    texto.append(f'<dt>Hora da Saída:</dt><dd>{solicitacaoentrada.hora_saida}</dd>')
    texto.append(f'<dt>Sala:</dt><dd>{solicitacaoentrada.sala}</dd>')
    texto.append(f'<dt>Atividade a ser realizada:</dt><dd>{solicitacaoentrada.atividade}</dd>')
    texto.append(f'<dt>Solicitante(s):</dt><dd>{solicitacaoentrada.get_solicitantes()}</dd>')
    texto.append('</dl>')
    texto.append(
        '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
            settings.SITE_URL, solicitacaoentrada.get_absolute_url()
        )
    )

    for solicitante in solicitacaoentrada.solicitantes.all():
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitante])

    return httprr('/admin/portaria/solicitacaoentrada/?cancelada__exact=0', 'A solicitação de entrada foi indeferida.')


@rtr()
@permission_required('portaria.change_solicitacaoentrada')
def cancelar_solicitacaoentrada(request, solicitacaoentrada_id):
    solicitacaoentrada = get_object_or_404(SolicitacaoEntrada, pk=solicitacaoentrada_id)

    if not solicitacaoentrada.eh_solicitante(request.user.get_vinculo()):
        raise PermissionDenied

    if solicitacaoentrada.deferida is None:
        solicitacaoentrada.cancelada = True
        solicitacaoentrada.save()
        return httprr('/admin/portaria/solicitacaoentrada/?cancelada__exact=0', 'A solicitação de entrada foi cancelada.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('portaria.view_solicitacaoentrada')
def solicitacao_entrada(request, solicitacaoentrada_id):
    solicitacao = get_object_or_404(SolicitacaoEntrada, pk=solicitacaoentrada_id)

    title = f'{solicitacao}'

    return locals()
