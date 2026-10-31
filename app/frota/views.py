import datetime
import io
import zipfile

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.db.models.aggregates import Count, Sum
from django.db.transaction import atomic
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.utils import get_uo
from djtools import layout
from djtools.choices import Situacao
from djtools.html.calendarios import CalendarioPlus
from djtools.html.graficos import ColumnChart, GraficoAgendamento, PieChart
from djtools.utils import httprr, ids_da_query, permission_required, rtr, send_notification, somar_dias, user_has_one_of_perms
from edu.models import Aluno
from estacionamento.models import Veiculo
from frota import tasks
from frota.forms import (
    ControleRevisaoForm,
    EditarDataProximaRevisaoForm,
    EstatisticasViagemForm,
    PeriodoForm,
    PeriodoRelatorioViagemForm,
    ViagemAgendamentoRespostaForm,
    ViagemChegadaForm,
    ViagemRetroativaForm,
    ViagemSaidaForm,
    ViaturaOrdemAbastecimentoForm,
    EditarAgendamentoDeferidoForm,
    MultaViagemForm,
)
from frota.models import (
    ManutencaoViatura,
    Viagem,
    ViagemAgendamento,
    ViagemAgendamentoResposta,
    Viatura,
    EdicaoAgendamentoDeferido,
    MultaViagem,
    ViaturaOrdemAbastecimento,
)
from rh.models import Funcao, Setor, UnidadeOrganizacional


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Integração com o painel "Atribuídos a mim" do SUAP.

    Para servidores que ocupam cargo de chefia hoje, conta os agendamentos
    `PENDENTE` (ainda sem avaliação) cujos setores estão sob sua chefia e
    cuja saída ainda não passou. Devolve um cartão linkando para o admin de
    agendamentos pendentes de autorização.
    """
    pendencias = []
    usuario = request.user
    if usuario.eh_servidor:
        servidor = usuario.get_relacionamento()
        hoje = datetime.datetime.now().date()
        setores = (
            servidor.historico_funcao(hoje, hoje).filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia()).values_list('setor_suap', flat=True)
        )

        viagens_pendentes_avaliacao = ViagemAgendamento.objects.filter(
            data_saida__gte=datetime.datetime.now(), setor__in=setores, avaliado_em__isnull=True, status=Situacao.PENDENTE
        ).count()
        if viagens_pendentes_avaliacao:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(viagens_pendentes_avaliacao, "ão,ões")} de Viagem',
                    'subtitulo': 'a autorizar',
                    'qtd': viagens_pendentes_avaliacao,
                    'url': '/admin/frota/viagemagendamento/?tab=tab_agendamentos_pendentes_autorizacao',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    """Integração com o painel "Atribuídos a meus grupos".

    Conta agendamentos `PENDENTE` com saída futura, restrito ao campus do
    coordenador (`tem_acesso_viatura_campus`) ou geral para o sistêmico
    (`tem_acesso_viatura_sistemico`). Retorna um cartão para a fila de
    avaliação.
    """
    pendencias = []
    eh_coordenador_frota_campus = request.user.has_perm('frota.tem_acesso_viatura_campus', ignore_superuser=True)
    eh_coordenador_frota_sistemico = request.user.has_perm('frota.tem_acesso_viatura_sistemico', ignore_superuser=True)
    eh_operador = request.user.has_perm('frota.tem_acesso_agendamento_operador', ignore_superuser=True)

    registros = 0
    if eh_coordenador_frota_campus:
        registros = ViagemAgendamento.objects.filter(
            setor__uo=get_uo(request.user), status=Situacao.PENDENTE, data_saida__gte=datetime.datetime.now()
        ).count()
    if eh_coordenador_frota_sistemico:
        registros = ViagemAgendamento.objects.filter(status=Situacao.PENDENTE, data_saida__gte=datetime.datetime.now()).count()
    if registros:
        pendencias.append(
            {
                'titulo': f'Viage{pluralize(registros, "m,ns")}',
                'subtitulo': 'a avaliar',
                'qtd': registros,
                'url': '/admin/frota/viagemagendamento/?status__exact=Pendente',
            }
        )
    if eh_operador:
        qtd = ViagemAgendamento.objects.filter(
            id__in=EdicaoAgendamentoDeferido.objects.filter(avaliada_em=None).values_list('agendamento', flat=True), setor__uo=get_uo(request.user)
        ).count()
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Viage{pluralize(qtd, "m,ns")}',
                    'subtitulo': 'com pedido de edição a avaliar',
                    'qtd': qtd,
                    'url': '/admin/frota/viagemagendamento/?edicao_pendente=1&tab=tab_any_data',
                }
            )

    return pendencias


@layout.quadro('Frota', icone='car', pode_esconder=True)
def index_quadros(quadro, request):
    """Monta o quadro "Frota" na home do SUAP.

    Para coordenadores e operadores adiciona:

    - alerta de viaturas cujo campus diverge da carga contábil do patrimônio;
    - atalho "Agendar Viagem";
    """
    eh_coordenador_frota_campus = request.user.has_perm('frota.tem_acesso_viatura_campus')
    eh_coordenador_frota_sistemico = request.user.has_perm('frota.tem_acesso_viatura_sistemico')
    eh_operador_frota = request.user.has_perm('frota.tem_acesso_agendamento_operador')

    if eh_coordenador_frota_campus or eh_coordenador_frota_sistemico or eh_operador_frota:
        viaturas_inconsistentes = Viatura.objects.filter(patrimonio__isnull=False).exclude(patrimonio__carga_contabil__campus=F('campus')).only('id')
        if viaturas_inconsistentes.exists():
            qtd_viaturas_inconsistentes = viaturas_inconsistentes.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Viatura{pluralize(qtd_viaturas_inconsistentes)}',
                    subtitulo=f'Vinculada{pluralize(qtd_viaturas_inconsistentes)} a um campus diferente da carga contábil do patrimônio',
                    qtd=qtd_viaturas_inconsistentes,
                    url=f'/admin/frota/viatura/{viaturas_inconsistentes[0].id}/',
                )
            )

        quadro.add_item(layout.ItemAcessoRapido(titulo='Agendar Viagem', url='/admin/frota/viagemagendamento/add/', icone='plus', classe='success'))
    return quadro


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def avaliar_agendamento_viagem(request, agendamento_id):
    """Avalia (defere/indefere) o agendamento e atribui viatura/motoristas.

    Monta um `GraficoAgendamento` cobrindo o intervalo da viagem (±1 dia)
    pintando em ``alert`` as viaturas/motoristas já comprometidos com
    viagens ou agendamentos deferidos sobrepostos, e em ``success`` o
    período-alvo de cada viatura disponível.

    Ao deferir, persiste a viatura e os motoristas escolhidos via
    `ViagemAgendamentoResposta`, sincronizando a relação m2m de motoristas;
    ao indeferir, limpa motoristas previamente atribuídos. Em seguida
    notifica por e-mail o solicitante, vínculos interessados e (se
    deferido) os motoristas selecionados.

    Se o agendamento já foi pré-rejeitado pela chefia (`avaliado_em`
    preenchido com `aprovado=False`), redireciona com erro antes de
    qualquer alteração.
    """
    title = 'Avaliação de Agendamento'
    status = Situacao.get_choices()
    viaturas_indisponiveis = []
    motoristas_indisponiveis = []
    agendamento = get_object_or_404(ViagemAgendamento, pk=agendamento_id)
    if not request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
        if not agendamento.setor.uo == get_uo(request.user):
            raise PermissionDenied

    if not agendamento.aprovado and agendamento.avaliado_em:
        return httprr('/admin/frota/viagemagendamento/', 'Agendamento não autorizado pela chefia.', tag='error')

    limite_inferior = somar_dias(agendamento.data_saida, -1)
    limite_superior = somar_dias(agendamento.data_chegada, +1)
    viaturas = Viatura.objects.filter(ativo=True, campus=get_uo(request.user))

    grafico = GraficoAgendamento(limite_inferior, limite_superior)
    grafico.set_items(viaturas)

    viagens = Viagem.objects.filter(
        saida_data__lte=agendamento.data_chegada,
        saida_data__gte=agendamento.data_saida,
        chegada_data__gte=agendamento.data_saida,
        agendamento_resposta__agendamento__setor__uo=get_uo(request.user),
        agendamento_resposta__agendamento__status=Situacao.DEFERIDA,
    ) | Viagem.objects.filter(
        saida_data__lte=agendamento.data_chegada,
        saida_data__gte=agendamento.data_saida,
        chegada_data__isnull=True,
        agendamento_resposta__agendamento__setor__uo=get_uo(request.user),
        agendamento_resposta__agendamento__status=Situacao.DEFERIDA,
    )

    agendamentos = ViagemAgendamento.objects.filter(
        data_saida__lte=agendamento.data_chegada,
        data_chegada__gte=agendamento.data_saida,
        status=Situacao.DEFERIDA,
        viagemagendamentoresposta__viagem__isnull=True,
    ).exclude(id=agendamento.id)
    respostas_agendamentos = ViagemAgendamentoResposta.objects.filter(agendamento__in=agendamentos.values_list('id', flat=True))
    respostas_viagens = ViagemAgendamentoResposta.objects.filter(id__in=viagens.values_list('agendamento_resposta__id', flat=True))
    respostas = respostas_agendamentos | respostas_viagens

    for resposta in respostas:
        if resposta.viatura and resposta.viatura.ativo:
            texto = resposta.agendamento.objetivo + ' Motoristas: ' + resposta.get_motoristas()
            grafico.preencher_intervalo(resposta.viatura.id, 'alert', resposta.agendamento.data_saida, resposta.agendamento.data_chegada, texto)
            viaturas_indisponiveis.append(resposta.viatura.id)
            for motorista in resposta.motoristas.all():
                motoristas_indisponiveis.append(motorista.id)
    for viatura in viaturas:
        grafico.preencher_intervalo(viatura.id, 'success', agendamento.data_saida, agendamento.data_chegada, agendamento.objetivo)

    if agendamento.status == Situacao.PENDENTE:
        form = ViagemAgendamentoRespostaForm(
            request.POST or None,
            agendamento_id=agendamento_id,
            request=request,
            viaturas_indisponiveis=set(viaturas_indisponiveis),
            motoristas_indisponiveis=set(motoristas_indisponiveis),
        )
    else:
        agendamentoResposta = ViagemAgendamentoResposta.objects.get(agendamento=agendamento)
        form = ViagemAgendamentoRespostaForm(
            request.POST or None,
            instance=agendamentoResposta,
            agendamento_id=agendamento_id,
            request=request,
            viaturas_indisponiveis=set(viaturas_indisponiveis),
            motoristas_indisponiveis=set(motoristas_indisponiveis),
        )

    if form.is_valid():
        registro = form.save(commit=False)
        viatura_escolhida = None
        status = form.cleaned_data.get('status')
        agendamento.status = status
        if status == Situacao.DEFERIDA:
            agendamento.local_saida = form.cleaned_data.get('local_saida')
            if form.cleaned_data.get('viatura'):
                viatura_escolhida = form.cleaned_data.get('viatura')
        agendamento.save()

        kwargs = {
            'obs': form.cleaned_data.get('obs'),
            'data': datetime.datetime.now(),
            'vinculo_responsavel': request.user.get_vinculo(),
            'viatura': viatura_escolhida,
        }

        avaliacao_agendamento = ViagemAgendamentoResposta.objects.update_or_create(agendamento=agendamento, defaults=kwargs)[0]
        string_motoristas = ''
        if status == Situacao.DEFERIDA:
            for motorista in form.cleaned_data.get('motoristas'):
                avaliacao_agendamento.motoristas.add(motorista)
                string_motoristas += motorista.pessoa.nome + ', '
            string_motoristas = string_motoristas[:-2]
            for motorista in avaliacao_agendamento.motoristas.all():
                if motorista not in form.cleaned_data.get('motoristas'):
                    avaliacao_agendamento.motoristas.remove(motorista)
        elif status == Situacao.INDEFERIDA:
            for motorista in avaliacao_agendamento.motoristas.all():
                avaliacao_agendamento.motoristas.remove(motorista)

        agendamento_avaliado = get_object_or_404(ViagemAgendamento, pk=agendamento_id)
        titulo = '[SUAP] Avaliação de Agendamento da Viagem'
        texto = (
            '<h1>Frota</h1>'
            f'<h2>Avaliação de Agendamento da Viagem #{agendamento_avaliado.id}</h2>'
            f'<p>A viagem, com o objetivo "{agendamento_avaliado.objetivo}", foi <strong>{agendamento_avaliado.status}</strong>.</p><br />'
        )
        if form.cleaned_data['status'] == Situacao.DEFERIDA:
            texto += (
                '<dl>'
                '<dt>Motorista(s):</dt><dd>{}<dd>'
                '<dt>Veículo:</dt><dd>{}<dd>'
                '<dt>Local de Saída:</dt><dd>{}</dd>'
                '<dt>Saída:</dt><dd>{}</dd>'
                '<dt>Chegada:</dt><dd>{}</dd>'.format(
                    string_motoristas,
                    form.cleaned_data['viatura'],
                    form.cleaned_data['local_saida'],
                    agendamento_avaliado.data_saida,
                    agendamento_avaliado.data_chegada,
                )
            )
        if form.cleaned_data['obs']:
            texto += '<dt>Observação do Avaliador:</dt><dd>{}</dd>'.format(form.cleaned_data['obs'])
        texto += '</dl>'

        destinatarios = [agendamento_avaliado.vinculo_solicitante]
        if agendamento.vinculos_interessados.exists():
            destinatarios.extend(list(agendamento.vinculos_interessados.all()))

        if form.cleaned_data['status'] == Situacao.DEFERIDA:
            if form.cleaned_data.get('motoristas'):
                destinatarios.extend(list(form.cleaned_data.get('motoristas', [])))
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, destinatarios)
        return httprr('/admin/frota/viagemagendamento/', 'Agendamento avaliado com sucesso.')

    return locals()


@rtr()
@permission_required(
    [
        'frota.tem_acesso_viagem_sistemico',
        'frota.tem_acesso_viagem_campus',
        'frota.tem_acesso_viagem_operador',
        'frota.pode_registrar_saida_chegada_viagem',
    ]
)
def viagens_agendadas(request):
    """Lista respostas de agendamento DEFERIDAS ainda sem viagem iniciada.

    Janela: saídas entre 30 dias passados e 15 dias futuros. Coordenadores
    de campus/operadores enxergam apenas o próprio campus; sistêmico vê
    tudo. `?all` desativa o filtro adicional por campus da viatura
    associada.
    """
    title = 'Viagens Agendadas'
    is_gerente = request.user.has_perm('frota.tem_acesso_viagem_sistemico') or request.user.is_superuser

    if not is_gerente:
        agendamentos_viagem = list(
            Viagem.objects.filter(agendamento_resposta__agendamento__setor__uo=get_uo(request.user)).values_list('agendamento_resposta_id', flat=True)
        )
        resp_agendamentos = (
            ViagemAgendamentoResposta.objects.filter(
                agendamento__status=Situacao.DEFERIDA,
                agendamento__data_saida__lte=datetime.date.today() + datetime.timedelta(15),
                agendamento__data_saida__gte=datetime.date.today() + datetime.timedelta(-30),
            )
            .filter(Q(agendamento__setor__uo=get_uo(request.user)) | Q(motoristas=request.user.get_vinculo()))
            .exclude(id__in=agendamentos_viagem)
            .order_by('-agendamento__data_saida')
        )
    else:
        agendamentos_viagem = list(Viagem.objects.all().values_list('agendamento_resposta_id', flat=True))
        resp_agendamentos = (
            ViagemAgendamentoResposta.objects.filter(
                agendamento__status=Situacao.DEFERIDA,
                agendamento__data_saida__lte=datetime.date.today() + datetime.timedelta(15),
                agendamento__data_saida__gte=datetime.date.today() + datetime.timedelta(-30),
            )
            .exclude(id__in=agendamentos_viagem)
            .order_by('-agendamento__data_saida')
        )

    if 'all' in request.GET:
        pass
    else:
        resp_agendamentos = resp_agendamentos.filter(viatura__campus=get_uo(request.user))

    return locals()


@rtr()
@permission_required(
    [
        'frota.tem_acesso_viagem_sistemico',
        'frota.tem_acesso_viagem_campus',
        'frota.tem_acesso_viagem_operador',
        'frota.pode_registrar_saida_chegada_viagem',
    ]
)
def saida_viagem(request, resp_agendamento_id):
    """Registra a saída da viagem a partir de uma resposta de agendamento.

    Persiste odômetro/observação, vincula os motoristas selecionados e —
    como atalho de embarque em massa — adiciona passageiros via três fontes
    excludentes do formulário: ``turma`` (todos os alunos matriculados),
    ``lista_alunos`` (CSV de matrículas) ou ``diario`` (alunos do diário).
    """
    title = 'Registrar Saída'
    resp_agendamento = get_object_or_404(ViagemAgendamentoResposta, pk=resp_agendamento_id)
    eh_motorista = (
        not request.user.has_perm('frota.tem_acesso_viagem_sistemico')
        and not request.user.has_perm('frota.tem_acesso_viagem_campus')
        and not request.user.has_perm('frota.tem_acesso_viagem_operador')
    )
    if not request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
        if request.user.get_vinculo() not in resp_agendamento.motoristas.all():
            if not eh_motorista and not resp_agendamento.agendamento.setor.uo == get_uo(request.user):
                raise PermissionDenied
    if request.POST:
        form = ViagemSaidaForm(request.POST, request=request, resp_agendamento_id=resp_agendamento_id)
        if form.is_valid():
            o = form.save(False)
            if eh_motorista:
                o.saida_validada = False
            else:
                o.saida_validada_por = request.user.get_vinculo()
                o.saida_validada_em = datetime.datetime.now()
            o.save()
            for motorista in form.cleaned_data.get('motoristas'):
                form.instance.motoristas.add(motorista)
            turma = form.cleaned_data.get('turma')
            lista_alunos = form.cleaned_data.get('lista_alunos')
            diario = form.cleaned_data.get('diario')

            if turma:
                matriculas = turma.get_alunos_matriculados()
                for matricula in matriculas:
                    form.instance.vinculos_passageiros.add(matricula.aluno.vinculos.all()[0])
                    form.instance.save()

            if lista_alunos:
                matriculas = lista_alunos.split(',')
                for matricula in matriculas:
                    aluno = Aluno.objects.filter(matricula=matricula)
                    if aluno.exists():
                        form.instance.vinculos_passageiros.add(aluno[0].vinculos.all()[0])
                        form.instance.save()

            if diario:
                alunos = Aluno.objects.filter(matriculaperiodo__matriculadiario__diario=diario)
                if alunos.exists():
                    for aluno in alunos:
                        form.instance.vinculos_passageiros.add(aluno.vinculos.all()[0])
                        form.instance.save()

            return httprr('/frota/viagens_agendadas/', 'Viagem iniciada com sucesso.')
    else:
        form = ViagemSaidaForm(resp_agendamento_id=resp_agendamento.id, request=request)
    return locals()


@rtr('frota/templates/viagens_iniciadas.html')
@permission_required(
    [
        'frota.tem_acesso_viagem_sistemico',
        'frota.tem_acesso_viagem_campus',
        'frota.tem_acesso_viagem_operador',
        'frota.pode_registrar_saida_chegada_viagem',
    ]
)
def viagens_iniciadas(request):
    """Lista viagens em andamento (com saída registrada e sem chegada).

    Coordenadores de campus veem somente o próprio campus; sistêmico vê
    tudo. `?all` removes o filtro adicional por campus da viatura.
    """
    title = 'Viagens Iniciadas'
    is_gerente = request.user.has_perm('frota.tem_acesso_viagem_sistemico') or request.user.is_superuser
    eh_motorista = (
        not request.user.has_perm('frota.tem_acesso_viagem_sistemico')
        and not request.user.has_perm('frota.tem_acesso_viagem_campus')
        and not request.user.has_perm('frota.tem_acesso_viagem_operador')
    )
    if not is_gerente:
        if eh_motorista:
            viagens = Viagem.objects.filter(chegada_data=None, motoristas=request.user.get_vinculo())
        else:
            viagens = (
                Viagem.objects.filter(chegada_data=None)
                .filter(Q(agendamento_resposta__agendamento__setor__uo=get_uo(request.user)) | Q(motoristas=request.user.get_vinculo()))
                .order_by('-saida_data')
            )
    else:
        viagens = Viagem.objects.filter(chegada_data=None).order_by('-saida_data')

    if 'all' in request.GET:
        pass
    else:
        viagens = viagens.filter(viatura__campus=get_uo(request.user)).order_by('-saida_data')

    return locals()


@rtr()
@permission_required(
    [
        'frota.tem_acesso_viagem_sistemico',
        'frota.tem_acesso_viagem_campus',
        'frota.tem_acesso_viagem_operador',
        'frota.pode_registrar_saida_chegada_viagem',
    ]
)
def chegada_viagem(request, viagem_id):
    """Encerra a viagem registrando chegada (odômetro/data/observações)."""
    title = 'Registrar Chegada'
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    resp_agendamento_id = viagem.agendamento_resposta.id
    eh_motorista = (
        not request.user.has_perm('frota.tem_acesso_viagem_sistemico')
        and not request.user.has_perm('frota.tem_acesso_viagem_campus')
        and not request.user.has_perm('frota.tem_acesso_viagem_operador')
    )

    if not request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
        if request.user.get_vinculo() not in viagem.motoristas.all():
            if not eh_motorista and not viagem.agendamento_resposta.agendamento.setor.uo == get_uo(request.user):
                raise PermissionDenied
    if request.POST:
        form = ViagemChegadaForm(request.POST, resp_agendamento_id=resp_agendamento_id, instance=viagem)
        if form.is_valid():
            o = form.save(False)
            if eh_motorista:
                o.chegada_validada = False
            else:
                o.chegada_validada_por = request.user.get_vinculo()
                o.chegada_validada_em = datetime.datetime.now()
            o.save()
            return httprr('/frota/viagens_iniciadas/', 'Viagem finalizada com sucesso.')
    else:
        form = ViagemChegadaForm(resp_agendamento_id=resp_agendamento_id)
    return locals()


@rtr('frota/templates/viagens.html')
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus', 'frota.tem_acesso_viagem_operador'])
def viagens(request):
    """Listagem histórica de viagens com filtros (default: últimos 30 dias).

    Filtra por período, grupo de viatura, UO, id do agendamento e passageiro
    (`PeriodoForm`). O escopo de visibilidade depende do perfil:
    coordenador de campus vê viagens cujo setor solicitante está na sua UO;
    operador vê apenas as viagens que ele próprio solicitou; sistêmico vê
    tudo.
    """
    title = 'Listar Viagens'
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    eh_sistemico = request.user.has_perm('frota.tem_acesso_viagem_sistemico')
    if request.method == 'GET' and 'data_inicio' not in request.GET:
        form = PeriodoForm(request=request)
        form.fields['data_inicio'].initial = data_inicio
        form.fields['data_termino'].initial = data_termino
    else:
        form = PeriodoForm(request.GET, request=request)

    if form.is_valid():
        data_inicio = form.cleaned_data['data_inicio']
        data_termino = form.cleaned_data['data_termino']
        grupo_viatura = form.cleaned_data['grupo_viatura']
        uo = form.cleaned_data['uo']
        id_viagem = form.cleaned_data['id_viagem']
        passageiro = form.cleaned_data['passageiro']

        viagens = Viagem.objects.filter(saida_data__gt=data_inicio, saida_data__lt=data_termino).order_by('-saida_data')
        if request.user.has_perm('frota.tem_acesso_viagem_campus'):
            viagens = viagens.filter(agendamento_resposta__agendamento__setor__uo=get_uo(request.user))
        elif request.user.has_perm('frota.tem_acesso_viagem_operador'):
            viagens = viagens.filter(agendamento_resposta__agendamento__vinculo_solicitante__user=request.user)

        if grupo_viatura:
            viagens = viagens.filter(viatura__grupo=grupo_viatura)

        if uo:
            viagens = viagens.filter(viatura__campus=uo)

        if id_viagem:
            viagens = viagens.filter(agendamento_resposta__agendamento=id_viagem)
        if passageiro:
            viagens = viagens.filter(vinculos_passageiros=passageiro)

    return locals()


@rtr('frota/templates/agendamento.html')
@login_required()
@permission_required('frota.view_viagemagendamento')
def agendamento(request, agendamento_id):
    """Tela de detalhes de um agendamento de viagem.

    Permite acesso a perfis de frota (sistêmico/campus/operador/agendador),
    ao avaliador que aprovou o agendamento e ao chefe do setor de origem.
    Quando já há resposta, expõe também a viatura escolhida.
    """
    agendamento = get_object_or_404(ViagemAgendamento, id=agendamento_id)
    eh_o_chefe = False

    if request.user.is_authenticated:
        vinculo = request.user.get_vinculo()
        if vinculo.eh_servidor():
            eh_o_chefe = request.user.get_relacionamento().eh_chefe_do_setor_hoje(agendamento.setor)

        if (
            user_has_one_of_perms(
                request.user,
                [
                    'frota.tem_acesso_viagem_sistemico',
                    'frota.tem_acesso_viagem_campus',
                    'frota.tem_acesso_viagem_operador',
                    'frota.tem_acesso_agendamento_agendador',
                ],
            )
            or request.user.get_relacionamento() == agendamento.avaliado_por
            or eh_o_chefe
        ):
            title = 'Dados do Agendamento da Viagem'

            resposta = ViagemAgendamentoResposta.objects.filter(agendamento=agendamento)
            if resposta:
                viatura = resposta[0].viatura
            return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus', 'frota.tem_acesso_viagem_operador'])
def viagem(request, viagem_id):
    """Tela de detalhes da viagem (saída/chegada/passageiros/motoristas)."""
    eh_sistemico = request.user.has_perm('frota.tem_acesso_viagem_sistemico')
    viagem = get_object_or_404(Viagem, id=viagem_id)
    title = f'Viagem #{viagem.agendamento_resposta.agendamento.id}'
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus', 'frota.tem_acesso_viagem_operador'])
def pdf_requisicao(request, viagem_id):
    """Prepara os dados para a Requisição de Viagem em PDF.

    Recebe `viagem_id` que na verdade é o id da `ViagemAgendamentoResposta`
    e devolve no contexto solicitante, avaliador, viatura, intinerário,
    datas previstas e a lista de passageiros formatada.
    """
    agendamento_resposta = get_object_or_404(ViagemAgendamentoResposta, pk=viagem_id)
    try:
        setor = agendamento_resposta.agendamento.vinculo_solicitante.setor
    except Exception:
        pass
    solicitante = agendamento_resposta.agendamento.vinculo_solicitante
    dt_solicitacao = agendamento_resposta.agendamento.data_solicitacao
    hr_solicitacao = agendamento_resposta.agendamento.data_solicitacao
    avaliador = agendamento_resposta.vinculo_responsavel
    dt_avaliacao = agendamento_resposta.data_avaliacao
    hr_avaliacao = agendamento_resposta.data_avaliacao
    veiculo = agendamento_resposta.viatura
    objetivo = agendamento_resposta.agendamento.objetivo
    intinerario = agendamento_resposta.agendamento.intinerario
    dt_prev_saida = agendamento_resposta.agendamento.data_saida
    hr_prev_saida = agendamento_resposta.agendamento.data_saida
    dt_prev_chegada = agendamento_resposta.agendamento.data_chegada
    hr_prev_chegada = agendamento_resposta.agendamento.data_chegada
    lista_passageiros = ', '.join(
        [passageiro.pessoa.nome for passageiro in agendamento_resposta.agendamento.vinculos_passageiros.all().order_by('pessoa__nome')]
    )
    return locals()


@rtr('frota/templates/viatura.html')
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus', 'frota.tem_acesso_viatura_operador'])
def viatura(request, viatura_id):
    """Tela de detalhes da viatura (cadastro, histórico de viagens e revisões)."""
    viatura = get_object_or_404(Viatura, id=viatura_id)
    title = f'Viatura {viatura.placa_codigo_atual} ({viatura.modelo})'

    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus', 'frota.tem_acesso_viatura_operador'])
def ordem_abastecimento(request, viagem_id):
    """Cadastra uma ordem de abastecimento (com anexo) vinculada à viagem."""
    viagem = get_object_or_404(Viagem, id=viagem_id)
    title = f'Registrar Ordem de Abastecimento - Viagem #{viagem.agendamento_resposta.agendamento.id}'
    if request.POST:
        form = ViaturaOrdemAbastecimentoForm(request.POST, request.FILES, viagem_id=viagem_id)
        if form.is_valid():
            form.save()
            return httprr(f'/frota/viagem/{viagem_id}/', 'Ordem de Abastecimento cadastrada com sucesso.')
    else:
        form = ViaturaOrdemAbastecimentoForm(viagem_id=viagem_id)
    return locals()


@rtr()
@atomic
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus', 'frota.tem_acesso_viagem_operador'])
def viagem_retroativa(request):
    """Cadastra uma viagem ex post (atômica) — agendamento + resposta + viagem.

    Se o formulário não informa `agendamento_resposta`, cria do zero um
    `ViagemAgendamento` já DEFERIDO + uma `ViagemAgendamentoResposta` cujo
    responsável é o próprio usuário corrente. Em seguida persiste a viagem
    com odômetros e datas reais; ajusta o odômetro da viatura se a chegada
    for maior que o atual; vincula passageiros e motoristas.
    """
    title = 'Viagem Retroativa'
    form = ViagemRetroativaForm(request.POST or None, request=request)
    if form.is_valid():
        v = Viagem()
        if not form.cleaned_data['agendamento_resposta']:
            a = ViagemAgendamento()
            a.status = Situacao.DEFERIDA
            a.vinculo_solicitante = form.cleaned_data['vinculo_solicitante']
            a.objetivo = form.cleaned_data['objetivo']
            a.intinerario = form.cleaned_data['itinerario']
            a.data_saida = form.cleaned_data['data_saida']
            a.data_chegada = form.cleaned_data['data_chegada']
            a.data_solicitacao = form.cleaned_data['data_saida']
            a.save()
            a.vinculos_passageiros.set(form.cleaned_data['vinculos_passageiros'])

            a.save()

            r = ViagemAgendamentoResposta()
            r.agendamento = a
            r.vinculo_responsavel = form.request.user.get_vinculo()
            r.data = datetime.datetime.now()
            r.save()

            v.agendamento_resposta = r
        else:
            v.agendamento_resposta = form.cleaned_data['agendamento_resposta']

        v.viatura = form.cleaned_data['viatura']

        v.saida_odometro = form.cleaned_data['saida_odometro']
        v.saida_data = form.cleaned_data['data_saida']
        v.saida_obs = form.cleaned_data['saida_obs']

        v.chegada_odometro = form.cleaned_data['chegada_odometro']
        v.chegada_data = form.cleaned_data['data_chegada']
        v.chegada_obs = form.cleaned_data['chegada_obs']
        v.save()

        if v.viatura.odometro < form.cleaned_data['chegada_odometro']:
            v.viatura.odometro = form.cleaned_data['chegada_odometro']
            v.viatura.save()

        v.vinculos_passageiros.set(form.cleaned_data['vinculos_passageiros'])
        v.save()

        for motorista in form.cleaned_data['motoristas']:
            v.motoristas.add(motorista)
        return httprr('/frota/viagem_retroativa/', f'Viagem retroativa #{v.agendamento_resposta.agendamento.id} cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus'])
def estatisticas_viaturas(request):
    """Pizza com o total de viaturas por campus.

    Viaturas sem campus aparecem agregadas como "SEM CAMPUS" quando há
    diferença entre o total e a soma das fatias.
    """
    # grafico 1
    title = 'Estatística de Viaturas por Campus'
    viaturas_total = Viatura.objects.all()
    conta_viatura = 0
    series = viaturas_total.values('campus__nome').annotate(qtd=Count('campus__sigla')).order_by('campus__nome')
    dados = []
    for item in series:
        dados.append([item['campus__nome'], item['qtd']])
        conta_viatura += item['qtd']
    if dados and dados[-1][1] == 0:
        dados.pop()
    if viaturas_total.count() != conta_viatura:
        dados.append(['SEM CAMPUS', viaturas_total.count() - conta_viatura])

    grafico1 = PieChart('grafico1', title='Viaturas por Campus', subtitle='Total de viaturas por campus', minPointLength=0, data=dados)

    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus'])
def estatisticas_deslocamento(request):
    """Gráfico de km rodados por viatura, agrupado por UO no período (default 30d).

    Soma `chegada_odometro - saida_odometro` das viagens fechadas dentro do
    intervalo, opcionalmente restringindo a uma viatura específica. Gera um
    `ColumnChart` por UO listada.
    """
    title = 'Relatório de Deslocamento por Viatura'
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    form = PeriodoRelatorioViagemForm(request.GET or None, request=request)
    form.fields['data_inicio'].initial = data_inicio
    form.fields['data_termino'].initial = data_termino
    graficos = []
    if form.is_valid():
        data_inicio = form.cleaned_data['data_inicio']
        data_termino = form.cleaned_data['data_termino']
        viatura_form = form.cleaned_data['viatura']
        motorista_form = form.cleaned_data['motorista']
        uo = form.cleaned_data['uo']
        if uo:
            uos = UnidadeOrganizacional.objects.suap().filter(id=uo.id)
        else:
            uos = UnidadeOrganizacional.objects.suap().all()
        for uo in uos:
            dados = []
            viagens = Viagem.objects.filter(viatura__campus=uo, saida_data__gte=data_inicio, chegada_data__lte=data_termino)
            if viatura_form:
                viagens = viagens.filter(viatura=viatura_form)
            if motorista_form:
                viagens = viagens.filter(motoristas=motorista_form)
            if viagens:
                series2 = (
                    viagens.values('viatura__placa_codigo_atual')
                    .order_by('viatura__placa_codigo_atual')
                    .annotate(count=Sum(F('chegada_odometro') - F('saida_odometro')))
                )
                teste = list(series2.values_list('viatura__placa_codigo_atual', flat=True))
                teste2 = list(series2.values_list('count', flat=True))
                for i, _item in enumerate(teste):
                    modelo = str(Veiculo.objects.get(placa_codigo_atual=teste[i]).modelo)
                    teste[i] = teste[i] + ' - ' + modelo
                contador = 0
                for item in teste:
                    x = []
                    x.append(item)
                    x.append(teste2[contador])
                    dados.append(x)
                    contador = contador + 1
                grafico2 = ColumnChart(
                    'grafico' + str(uo.id),
                    title='Deslocamento por Viatura',
                    subtitle='Número de km rodados por viatura',
                    minPointLength=0,
                    data=dados,
                )
                grafico2.id = uo.id
                grafico2.h1 = UnidadeOrganizacional.objects.suap().get(pk=uo.id).nome
                graficos.append(grafico2)
            else:
                pass

    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def viagens_por_viatura(request):
    """Relatório detalhado de viagens por viatura no período (default 30d).

    Anexa em cada `Viatura` (somente em memória) a lista de viagens com
    distância, passageiros/motoristas formatados e — quando há salto entre
    odômetros consecutivos — o campo `descontinuidade`, indicando que a
    diferença não foi coberta por viagem registrada.
    """
    title = 'Relatório de Viagem por Viatura'
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    form = PeriodoRelatorioViagemForm(request.GET or None, request=request)
    form.fields['data_inicio'].initial = data_inicio
    form.fields['data_termino'].initial = data_termino
    existe_registro = False
    graficos = []
    if form.is_valid():
        data_inicio = form.cleaned_data['data_inicio']
        data_termino = form.cleaned_data['data_termino']
        viatura_form = form.cleaned_data['viatura']
        uo = form.cleaned_data['uo']
        motorista_form = form.cleaned_data['motorista']

        viaturas = []

        if uo:
            viaturas = Viatura.objects.filter(campus=uo)
        else:
            viaturas = Viatura.objects.all()

        if viatura_form:
            viaturas = viaturas.filter(pk=viatura_form.id)

        for viatura in viaturas:
            viagens_totais = (
                Viagem.objects.exclude(chegada_odometro=None)
                .filter(saida_data__gt=data_inicio, saida_data__lt=data_termino, viatura=viatura)
                .order_by('saida_data')
            )
            if motorista_form:
                viagens_totais = viagens_totais.filter(motoristas=motorista_form)
            viagens = viagens_totais.values(
                'chegada_odometro',
                'agendamento_resposta__agendamento__objetivo',
                'chegada_data',
                'saida_odometro',
                'saida_data',
                'agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome',
                'id',
                'viatura_id',
            ).annotate(distancia=F('chegada_odometro') - F('saida_odometro'))
            viatura.viagens = viagens
            total = 0
            for viagem in viatura.viagens:
                if viagem['distancia']:
                    total = total + viagem['distancia']
                viagem_obj = viagens_totais.filter(id=viagem['id'])[0]
                qtd_passageiros = viagem_obj.vinculos_passageiros.count()
                viagem['qtd_passageiros'] = qtd_passageiros
                viagem['passageiros'] = viagem_obj.get_string_passageiros()
                viagem['passageiros_xls'] = viagem_obj.get_lista_passageiros_xls()
                viagem['motoristas'] = viagem_obj.get_motoristas()
                viagem['ordens_abastecimentos'] = ViaturaOrdemAbastecimento.objects.filter(
                    viatura=viatura, data__range=[viagem['saida_data'], viagem['chegada_data']]
                ).exists()

            viatura.total = total
            count = 0
            if len(viagens) > 0:
                existe_registro = True

            for viagem in viagens:
                if count < len(viagens) - 1 and Viagem.objects.get(id=viagem['id']).tem_descontinuidade():
                    viagens[count]['descontinuidade'] = viagens[count + 1]['saida_odometro'] - viagens[count]['chegada_odometro']
                else:
                    viagens[count]['descontinuidade'] = 0
                count += 1
        if 'xls' in request.GET:
            return tasks.viagens_por_viatura_to_xls(viaturas, motorista_form, data_inicio, data_termino)
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def estatistica_viagens_por_campus_setor(request):
    """Pizza de viagens por setor solicitante dentro de uma UO no período."""
    title = 'Estatística de Viagens por Campus/Setor'
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    form = EstatisticasViagemForm(request.POST or None, request=request)
    form.fields['data_inicio'].initial = data_inicio
    form.fields['data_termino'].initial = data_termino
    existe_registro = False
    graficos = []
    if form.is_valid():
        data_inicio = form.cleaned_data['data_inicio']
        data_termino = form.cleaned_data['data_termino']
        uo = form.cleaned_data['uo']
        series = (
            Viagem.objects.filter(
                agendamento_resposta__agendamento__vinculo_solicitante__setor__uo=uo, saida_data__gt=data_inicio, saida_data__lt=data_termino
            )
            .values('agendamento_resposta__agendamento__vinculo_solicitante__setor__nome')
            .annotate(qtd=Count('agendamento_resposta__agendamento__vinculo_solicitante__setor__nome'))
            .order_by('agendamento_resposta__agendamento__vinculo_solicitante__setor__nome')
        )
        if series:
            dados = []
            for item in series:
                dados.append([item['agendamento_resposta__agendamento__vinculo_solicitante__setor__nome'], item['qtd']])
            if dados[-1][1] == 0:
                dados.pop()
            grafico1 = PieChart(
                'grafico1',
                title='Viagens por Campus/Setor',
                subtitle='Total de Viagens por Campus/Setor no Período Informado',
                minPointLength=0,
                data=dados,
            )

    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus', 'frota.tem_acesso_viatura_operador'])
def manutencaoviatura(request, servico_id):
    """Tela de detalhes de um serviço de manutenção (`ManutencaoViatura`)."""
    servico = get_object_or_404(ManutencaoViatura, pk=servico_id)
    title = 'Dados do Serviço'

    return locals()


@rtr()
@permission_required('frota.view_viagemagendamento')
def ver_calendario_agendamento(request):
    """Calendário visual dos agendamentos DEFERIDOS/PENDENTES por mês.

    A janela cobre do mês corrente (ou ano/mês filtrado) até o mês do
    último agendamento. Eventos que cruzam mais de um dia são quebrados em
    três blocos (saída no dia 1, "Todo o dia" nos dias intermediários,
    chegada no último dia). Cor: ``success`` (deferido), ``danger``
    (indeferido) ou ``warning`` (pendente). Não-sistêmicos veem apenas a
    própria UO; filtros aceitos via querystring espelham os do admin:
    `status__exact`, `setor__uo__id__exact`, `setor__id__exact`,
    `data_saida__year`, `data_saida__month`.
    """
    title = 'Calendário de Agendamento'

    # ------------
    # até o mês do último agendamento que 'caia' pelo menos dentro do mês corrente
    qs_solicitacoes = ViagemAgendamento.objects.filter(status__in=[Situacao.DEFERIDA, Situacao.PENDENTE]).order_by('data_saida')
    cal_meses = []

    uo = ''
    setor = ''
    status = ''
    mes_filtro = ''
    ano_filtro = ''
    if request.GET.get('status__exact'):
        status = request.GET.get('status__exact')
        qs_solicitacoes = ViagemAgendamento.objects.filter(status=status)

    data_agora = datetime.datetime.now()
    ano_corrente = data_agora.year
    mes_corrente = data_agora.month

    if request.GET.get('setor__uo__id__exact'):
        uo = get_object_or_404(UnidadeOrganizacional, pk=request.GET.get('setor__uo__id__exact'))
    else:
        uo = get_uo(request.user)
    qs_solicitacoes = qs_solicitacoes.filter(setor__uo=uo)

    if not request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
        qs_solicitacoes = qs_solicitacoes.filter(setor__uo=get_uo(request.user))

    if request.GET.get('setor__id__exact'):
        setor = get_object_or_404(Setor, pk=request.GET.get('setor__id__exact'))
        qs_solicitacoes = qs_solicitacoes.filter(setor=setor)

    if request.GET.get('data_saida__year'):
        ano_filtro = int(request.GET.get('data_saida__year'))
        qs_solicitacoes = qs_solicitacoes.filter(data_saida__year=ano_filtro)
        ano_corrente = ano_filtro

        if request.GET.get('data_saida__month'):
            mes_filtro = int(request.GET.get('data_saida__month'))
            qs_solicitacoes = qs_solicitacoes.filter(data_saida__month=mes_filtro)
            mes_corrente = mes_filtro
        else:
            mes_corrente = 1
    else:
        qs_solicitacoes = qs_solicitacoes.filter(data_saida__year=data_agora.date().year)

    if qs_solicitacoes.exists():
        data_fim = qs_solicitacoes.latest('data_saida').data_saida
        if (data_fim.year == ano_corrente and data_fim.month >= mes_corrente) or (data_fim.year > ano_corrente):
            ultimo_ano = data_fim.year
            ultimo_mes = data_fim.month

            cal = CalendarioPlus()
            cal.mostrar_mes_e_ano = True

            mes = mes_corrente  # inicializa mês

            for ano in range(ano_corrente, ultimo_ano + 1):
                mes_final = 12  # por padrão
                if ano == ultimo_ano:
                    mes_final = ultimo_mes
                for imes in range(mes, mes_final + 1):
                    # -----------------------
                    # Adição das Solicitações
                    for solicitacao in qs_solicitacoes:
                        solicitacao_conflito = False
                        for [agenda_data_inicio, agenda_data_fim] in [[solicitacao.data_saida, solicitacao.data_chegada]]:
                            if agenda_data_inicio.year == ano and agenda_data_inicio.month == imes:
                                dia_todo_list = solicitacao.get_dia_todo_list()

                                if solicitacao.is_deferido():
                                    css = 'success'
                                elif solicitacao.is_indeferido():
                                    css = 'danger'
                                else:
                                    css = 'warning'

                                # Se for o dia todo os eventos são separados, o primeiro e o ultimo tem o horário diferenciado
                                if dia_todo_list:
                                    data_fim = datetime.datetime(
                                        agenda_data_inicio.year, agenda_data_inicio.month, agenda_data_inicio.day, 23, 59, 59
                                    )  # hour,minute,second
                                    horario = '{} às {}'.format(agenda_data_inicio.strftime('%H:%M'), data_fim.strftime('%H:%M'))

                                    descricao = (
                                        f'<a href="/frota/agendamento/{solicitacao.id}/"><strong>{horario}</strong> {solicitacao.objetivo}</a>'
                                    )

                                    cal.adicionar_evento_calendario(agenda_data_inicio, data_fim, descricao, css)

                                    for dia_todo in dia_todo_list:
                                        if dia_todo.day != agenda_data_fim.day:
                                            horario = 'Todo o dia'

                                            descricao = f'<a href="/frota/agendamento/{solicitacao.id}/"><strong>{horario}</strong> {solicitacao.objetivo}</a>'

                                            cal.adicionar_evento_calendario(dia_todo, dia_todo, descricao, css, dia_todo=True)

                                    data_inicio = datetime.datetime(
                                        agenda_data_fim.year, agenda_data_fim.month, agenda_data_fim.day, 0, 0, 0
                                    )  # hour,minute,second
                                    horario = '{} às {}'.format(data_inicio.strftime('%H:%M'), agenda_data_fim.strftime('%H:%M'))
                                    descricao = (
                                        f'<a href="/frota/agendamento/{solicitacao.id}/"><strong>{horario}</strong> {solicitacao.objetivo}</a>'
                                    )

                                    cal.adicionar_evento_calendario(data_inicio, agenda_data_fim, descricao, css)
                                else:
                                    horario = '{} às {}'.format(agenda_data_inicio.strftime('%H:%M'), agenda_data_fim.strftime('%H:%M'))
                                    descricao = (
                                        f'<a href="/frota/agendamento/{solicitacao.id}/"><strong>{horario}</strong> {solicitacao.objetivo}</a>'
                                    )

                                    cal.adicionar_evento_calendario(agenda_data_inicio, agenda_data_fim, descricao, css)
                    cal_meses.append(cal.formato_mes(ano, imes))
                    # -------------------
                mes = 1

    return locals()


@rtr()
@login_required()
@permission_required('frota.view_viagemagendamento')
def autorizar_agendamento(request, agendamento_id, opcao):
    """Pré-autorização do chefe do setor solicitante (etapa anterior ao coordenador).

    Só o chefe do setor de origem pode operar, e apenas enquanto o
    agendamento estiver `PENDENTE`. ``opcao='1'`` marca como aprovado pela
    chefia; ``'2'`` reprova. Em ambos os casos grava `avaliado_por` e
    `avaliado_em`. O coordenador de frota ainda precisará rodar
    `avaliar_agendamento_viagem` para deferir/indeferir efetivamente.
    """
    agendamento = get_object_or_404(ViagemAgendamento, pk=agendamento_id)
    eh_o_chefe = False
    vinculo = request.user.get_vinculo()
    if vinculo.eh_servidor():
        eh_o_chefe = request.user.get_relacionamento().eh_chefe_do_setor_hoje(agendamento.setor)
    if eh_o_chefe and agendamento.status == Situacao.PENDENTE:
        if opcao == '1':
            agendamento.aprovado = True
        elif opcao == '2':
            agendamento.aprovado = False
        agendamento.avaliado_por = request.user.get_relacionamento()
        agendamento.avaliado_em = datetime.datetime.now()
        agendamento.save()
        return httprr(f'/frota/agendamento/{agendamento_id}', 'Agendamento avaliado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus', 'frota.tem_acesso_viatura_operador'])
def controle_revisoes_viaturas(request):
    """Lista viaturas filtradas por situação de revisão.

    Situações suportadas (via `ControleRevisaoForm`): revisão em atraso,
    revisão prevista nos próximos 30 dias e revisão por quilometragem
    (odômetro próximo dos 10k do último serviço). Combina com filtros de
    UO e viatura específica.
    """
    title = 'Controle das Revisões das Viaturas'
    viaturas = Viatura.objects.all().order_by('campus', 'placa_codigo_atual')
    form = ControleRevisaoForm(request.GET or None)
    if form.is_valid():
        situacao = form.cleaned_data.get('situacao')
        if form.cleaned_data.get('uo'):
            viaturas = viaturas.filter(campus=form.cleaned_data.get('uo'))
        if form.cleaned_data.get('viatura'):
            viaturas = viaturas.filter(id=form.cleaned_data.get('viatura').id)
        if situacao:
            ids_viaturas = []
            if situacao == ControleRevisaoForm.SITUACAO_ATRASO:
                for viatura in viaturas:
                    if viatura.tem_revisao_atraso():
                        ids_viaturas.append(viatura.id)
                viaturas = viaturas.filter(id__in=ids_viaturas)
            elif situacao == ControleRevisaoForm.SITUACAO_PREVISTA:
                for viatura in viaturas:
                    if viatura.tem_revisao_atraso_dentro_limite():
                        ids_viaturas.append(viatura.id)
                viaturas = viaturas.filter(id__in=ids_viaturas)
            elif situacao == ControleRevisaoForm.SITUACAO_REVISAO_KM:
                for viatura in viaturas:
                    if viatura.tem_odometro_perto_km_revisao():
                        ids_viaturas.append(viatura.id)
                viaturas = viaturas.filter(id__in=ids_viaturas)

    return locals()


@rtr()
@permission_required('frota.change_viatura')
def editar_proxima_revisao_viatura(request, viatura_id):
    """Edita a data prevista para a próxima revisão da viatura."""
    viatura = get_object_or_404(Viatura, pk=viatura_id)
    url = request.META.get('HTTP_REFERER', '.')
    title = f'Informar Data da Próxima Revisão - {viatura}'
    form = EditarDataProximaRevisaoForm(request.POST or None, instance=viatura, url=url)
    if form.is_valid():
        form.save()
        return httprr(form.cleaned_data.get('url'), 'Data da próxima revisão cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('frota.view_viagemagendamento')
def editar_agendamento_deferido(request, agendamento_id):
    agendamento = get_object_or_404(ViagemAgendamento, pk=agendamento_id)
    eh_operador = (
        request.user.has_perm('frota.tem_acesso_agendamento_operador') and agendamento.setor and agendamento.setor.uo == get_uo(request.user)
    )
    vinculo_usuario = request.user.get_vinculo()
    if (eh_operador or (agendamento.vinculo_solicitante == vinculo_usuario)) and agendamento.is_deferido() and not agendamento.viagem_em_andamento():
        title = f'Editar agendamento deferido - {agendamento}'
        edicao = EdicaoAgendamentoDeferido()
        edicao.agendamento = agendamento
        form = EditarAgendamentoDeferidoForm(request.POST or None, instance=edicao)
        if form.is_valid():
            with transaction.atomic():
                o = form.save(False)
                o.cadastrado_por = request.user.get_vinculo()
                msg_confirmacao = 'Solicitação de edição do agendamento cadastrada com sucesso.'
                if eh_operador:
                    o.deferida = True
                    o.avaliada_em = datetime.datetime.now()
                    o.avaliada_por = vinculo_usuario
                    msg_confirmacao = 'Agendamento editado com sucesso.'
                    agendamento.data_saida = form.cleaned_data.get('data_saida')
                    agendamento.data_chegada = form.cleaned_data.get('data_chegada')
                    agendamento.save()
                    agendamento.vinculos_passageiros.clear()
                    agendamento.vinculos_passageiros.set(form.cleaned_data.get('vinculos_passageiros'))
                o.save()
                o.vinculos_passageiros.set(form.cleaned_data.get('vinculos_passageiros'))
            return httprr('..', msg_confirmacao)
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('frota.view_viagemagendamento')
def ver_solicitacoes_edicao(request, agendamento_id):
    agendamento = get_object_or_404(ViagemAgendamento, pk=agendamento_id)
    title = f'Solicitações de edição - Agendamento {agendamento}'
    edicoes = EdicaoAgendamentoDeferido.objects.filter(agendamento=agendamento).order_by('-id')
    eh_operador = (
        request.user.has_perm('frota.tem_acesso_agendamento_operador') and agendamento.setor and agendamento.setor.uo == get_uo(request.user)
    )
    return locals()


@rtr()
@permission_required('frota.view_viagemagendamento')
def avaliar_edicao(request, edicao_id, opcao):
    edicao = get_object_or_404(EdicaoAgendamentoDeferido, pk=edicao_id)
    agendamento = edicao.agendamento
    request.META.get('HTTP_REFERER', '.')
    eh_operador = (
        request.user.has_perm('frota.tem_acesso_agendamento_operador') and agendamento.setor and agendamento.setor.uo == get_uo(request.user)
    )
    if eh_operador and not edicao.avaliada_em:
        with transaction.atomic():
            if opcao == 1:
                edicao.deferida = True
                agendamento.data_saida = edicao.data_saida
                agendamento.data_chegada = edicao.data_chegada
                agendamento.save()
                agendamento.vinculos_passageiros.clear()
                agendamento.vinculos_passageiros.set(edicao.vinculos_passageiros.all())
            else:
                edicao.deferida = False
            edicao.avaliada_em = datetime.datetime.now()
            edicao.avaliada_por = request.user.get_vinculo()
            edicao.save()

        return httprr('..', 'Edição avaliada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('frota.add_multaviagem')
def cadastrar_multa(request, viagem_id):
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    title = f'Cadastrar multa - {viagem}'
    multa = MultaViagem()
    multa.viagem = viagem
    form = MultaViagemForm(request.POST or None, request.FILES or None, instance=multa)
    if form.is_valid():
        o = form.save(False)
        o.cadastrado_por = request.user.get_vinculo()
        o.editado_por = request.user.get_vinculo()
        o.save()
        return httprr('..', 'Multa cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('frota.add_multaviagem')
def editar_multa(request, multa_id):
    multa = get_object_or_404(MultaViagem, pk=multa_id)
    title = f'Editar multa - {multa.viagem}'
    form = MultaViagemForm(request.POST or None, request.FILES or None, instance=multa)
    if form.is_valid():
        o = form.save(False)
        o.editado_por = request.user.get_vinculo()
        o.save()
        return httprr('..', 'Multa editada com sucesso.')
    return locals()


@rtr()
@permission_required('frota.add_multaviagem')
def visualizar_multas(request, viagem_id):
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    title = f'Visualizar multas - Viagem {viagem}'
    multas = MultaViagem.objects.filter(viagem=viagem).order_by('-id')
    return locals()


@rtr()
@permission_required('frota.add_multaviagem')
def validar_saida(request, viagem_id):
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    if not viagem.saida_validada:
        viagem.saida_validada = True
        viagem.saida_validada_por = request.user.get_vinculo()
        viagem.saida_validada_em = datetime.datetime.now()
        viagem.save()
        return httprr('..', 'Registro de saída da viagem validado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('frota.add_multaviagem')
def validar_chegada(request, viagem_id):
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    if viagem.saida_validada and viagem.chegada_odometro:
        viagem.chegada_validada = True
        viagem.chegada_validada_por = request.user.get_vinculo()
        viagem.chegada_validada_em = datetime.datetime.now()
        viagem.save()
        return httprr('..', 'Registro de chegada da viagem validado com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('frota.add_multaviagem')
def validar_ordem_abastecimento(request, ordem_id):
    ordem = get_object_or_404(ViaturaOrdemAbastecimento, pk=ordem_id)
    if not ordem.validada:
        ordem.validada = True
        ordem.validada_por = request.user.get_vinculo()
        ordem.validada_em = datetime.datetime.now()
        ordem.save()
        return httprr('..', 'Ordem de abastecimento validada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def ver_passageiros_viagem(request, viagem_id):
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    title = f'Passageiros - {viagem}'
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def ver_ordens_abastecimento_viagem(request, viagem_id):
    viagem = get_object_or_404(Viagem, pk=viagem_id)
    return httprr(
        f'/admin/frota/viaturaordemabastecimento/?id={viagem.viatura.id}&drf__data__gte={viagem.saida_data.date()}&drf__data__lte={viagem.chegada_data.date() + relativedelta(days=1)}'
    )


@rtr()
@permission_required('frota.view_manutencaoviatura')
def baixar_notas_fiscais_servicos(request: HttpRequest) -> HttpResponse:
    ids = ids_da_query(request)
    zip_buffer = io.BytesIO()
    zip_file = zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED)

    for registro in ManutencaoViatura.objects.filter(id__in=ids):
        if registro.arquivo_nf_pecas:
            zip_file.writestr(registro.arquivo_nf_pecas.name.split('/')[-1], registro.arquivo_nf_pecas.read())
        if registro.arquivo_nf_servicos:
            zip_file.writestr(registro.arquivo_nf_servicos.name.split('/')[-1], registro.arquivo_nf_servicos.read())
    zip_file.close()
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename=notas_fiscais_servicos_pecas_viaturas_{datetime.datetime.now()}.zip'
    return response
