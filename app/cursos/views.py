from collections import OrderedDict
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.models import Ano
from cursos.enums import SituacaoCurso, SituacaoDetalhamentoAtividadeParticipante, SituacaoParticipante, TipoCurso
from cursos.forms import (
    AdicionarHorasTrabalhadasForm,
    CotaAnualServidorGECCForm,
    EditarMesPagamentoGECCForm,
    FiltrarParticipanteForm,
    FiltroPendentesPagamentoForm,
    IndeferimentoParticipanteForm,
    IndeferirDetalhamentoAtividadeForm,
    ParticipanteForm,
    PreencherDetalhamentoAtividadeForm,
    RelatorioFinanceiroPagamentoGECCForm,
)
from cursos.models import Curso, Participante
from djtools import layout
from djtools.choices import Meses
from djtools.utils import documento, httprr, rtr, permission_required


@layout.info()
def index_infos(request):
    """Sinaliza ao servidor logado se há horas de cursos/concursos no mês corrente.

    Args:
        request: requisição HTTP usada para identificar o servidor logado.

    Returns:
        list[dict]: contém um aviso com ``url`` e ``titulo`` quando existe participação
        registrada para o mês e ano atuais; lista vazia caso contrário.
    """
    infos = []

    hoje = datetime.today()
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        if Participante.objects.filter(servidor=servidor, mes_pagamento=hoje.month, curso__ano_pagamento=hoje.year).exists():
            infos.append({'url': '/cursos/horas_trabalhadas/', 'titulo': 'Há horas de cursos/concursos registradas para este mês.'})

    return infos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []

    if request.user.eh_servidor:
        participantes_liberacao_pendente = Participante.get_participantes_liberacao_pendente(request.user)
        if participantes_liberacao_pendente.exists():
            qtd_participantes = participantes_liberacao_pendente.count()
            pendencias.append(
                {
                    'titulo': f'Participante{pluralize(qtd_participantes)} de Curso/Concurso',
                    'subtitulo': 'aguardando aprovação',
                    'qtd': qtd_participantes,
                    'url': '/admin/cursos/participante/?tab=tab_aguardando_chefia',
                }
            )

        for participante in Participante.get_participantes_detalhamento_horas_preenchimento_pendente(request.user):
            pendencias.append(
                {
                    'titulo': '<strong>Detalhamento de Horas Trabalhadas</strong> em Cursos/Concursos.',
                    'subtitulo': 'aguardando preenchimento',
                    'qtd': 1,
                    'url': f'/cursos/preencher_detalhamento_atividade/{participante.id}',
                }
            )

        for participante in Participante.get_participantes_detalhamento_horas_avaliacao_pendente(request.user):
            pendencias.append(
                {
                    'titulo': f'<strong>Detalhamento de Horas Trabalhadas</strong> de {participante.servidor} em Cursos/Concursos.',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': 1,
                    'url': f'{participante.get_absolute_url()}',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    eh_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    eh_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
    if eh_rh_sistemico or eh_rh_campus:
        qs_gecc_pendente = Curso.objects.filter(situacao=SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA).count()
        if qs_gecc_pendente:
            pendencias.append(
                {
                    'titulo': f'Curso{pluralize(qs_gecc_pendente)}/Concurso{pluralize(qs_gecc_pendente)}',
                    'subtitulo': 'a cadastrar em folha',
                    'qtd': qs_gecc_pendente,
                    'url': '/admin/cursos/curso/?situacao__exact=3',
                }
            )

    return pendencias


@rtr()
@permission_required('cursos.view_curso')
def curso(request, id):
    curso = get_object_or_404(Curso, pk=id)
    title = str(curso)

    horas_previstas_total = curso.horas_previstas_total() or None
    horas_previstas_total_pendentes = curso.horas_previstas_total([SituacaoParticipante.PENDENTE]) or None

    horas_trabalhadas_total = curso.horas_trabalhadas_total() or None
    horas_trabalhadas_total_pendentes = curso.horas_trabalhadas_total([SituacaoParticipante.PENDENTE]) or None

    valor_total = curso.valor_total() or None
    valor_total_pendentes = curso.valor_total([SituacaoParticipante.PENDENTE]) or None

    pode_iniciar_curso = _pode_iniciar_curso(curso, request)
    pode_finalizar_curso = _pode_finalizar_curso(curso, request)
    pode_adicionar_horas_participante = _pode_adicionar_horas_participante(curso, request)
    pode_gerenciar_participante = _pode_gerenciar_participante(curso, request)
    pode_informar_cadastro_folha = _pode_informar_cadastro_folha(curso, request)
    pode_liberar_participantes = _pode_liberar_participantes(request)
    pode_imprimir_listagem = curso.pode_imprimir_listagem()
    pode_mudar_situacao_curso_concurso = _pode_mudar_situacao_curso_concurso(request)
    pode_visualizar_participantes = curso.pode_visualizar_participantes(request.user)
    pode_ativar_desativar_detalhamento_atividade = curso.pode_ativar_desativar_detalhamento_atividade(request.user)
    ativar_desativar_detalhamento_atividade_label = (
        f'{"Desativar" if curso.participantes_detalhamento_atividade_ativado else "Ativar"} Detalhamento das Horas Trabalhadas'
    )

    servidor_logado = request.user.get_relacionamento()

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@permission_required('cursos.view_curso')
def imprimir_listagem(request, curso_id):
    curso = get_object_or_404(Curso, pk=curso_id)

    return locals()


@rtr()
@login_required()
def adicionar_horas(request, id):
    title = 'Adicionar Horas Trabalhadas'
    instance = get_object_or_404(Participante, id=id)

    if not _pode_adicionar_horas_participante(instance.curso, request):
        return httprr('..', 'Você não tem permissão para adicionar horas.', 'error')

    form = AdicionarHorasTrabalhadasForm(request.POST or None, instance=instance)

    if form.is_valid():
        form.save()
        return httprr('..', 'Horas adicionadas com sucesso.')

    return locals()


@rtr()
@login_required()
@permission_required('cursos.pode_ver_seu_relatorio')
def mostrar_atividades(request):
    pode_visualizar_qualquer_participante = Participante.pode_visualizar_qualquer_participante(request.user)

    form_initial = {}

    form_data = request.GET or form_initial

    form = FiltrarParticipanteForm(form_data, pode_selecionar_servidor=pode_visualizar_qualquer_participante)

    if form.is_valid():
        form_data = form.cleaned_data

    servidor = form_data.get('servidor')

    if not servidor:
        servidor = request.user.get_relacionamento()  # o servidor logado

        if pode_visualizar_qualquer_participante:
            form_data.update({'servidor': servidor})

        form = FiltrarParticipanteForm(form_data, pode_selecionar_servidor=pode_visualizar_qualquer_participante)

    if not servidor:
        raise PermissionDenied

    title = f'Horas Trabalhadas/Atividades - {servidor}'

    class ParticipacaoInfo:
        def __init__(self) -> None:
            self.participacao: Participante = None
            self.pode_preencher_detalhamento: bool = None

    class AnoInfo:
        def __init__(self) -> None:
            self.participacoes: list[ParticipacaoInfo] = []
            self.totais_horas_prevista: float = 0.0
            self.totais_horas_trabalhada: float = 0.0
            self.totais_valor_total: float = 0.0
            self.tem_problemas_com_horas: bool = False

    atividades: OrderedDict[Ano, AnoInfo] = OrderedDict()

    participante_filter = {'servidor': servidor}

    if form_data.get('ano'):
        participante_filter.update({'curso__ano_pagamento__ano': form_data.get('ano')})

    if form_data.get('situacao_curso'):
        if form_data.get('situacao_curso') == 'andamento':
            participante_filter.update({'curso__situacao__in': SituacaoCurso.curso_em_andamento()})
        elif form_data.get('situacao_curso') == 'concluido':
            participante_filter.update({'curso__situacao__in': SituacaoCurso.curso_concluido()})
        else:
            participante_filter.update({'curso__situacao': form_data.get('situacao_curso')})

    if form_data.get('situacao_participante'):
        if form_data.get('situacao_participante') == 'atividade':
            participante_filter.update({'situacao__in': SituacaoParticipante.participante_em_atividade()})
        else:
            participante_filter.update({'situacao': form_data.get('situacao_participante')})

    if form_data.get('situacao_detalhamento_horas'):
        if form_data.get('situacao_detalhamento_horas') == 'pendente':
            participante_filter.update({'situacao_detalhamento__in': SituacaoDetalhamentoAtividadeParticipante.detalhamento_pendente()})
        else:
            participante_filter.update({'situacao_detalhamento': form_data.get('situacao_detalhamento_horas')})

    for participacao in Participante.objects.filter(**participante_filter).order_by('curso__ano_pagamento__ano', 'id'):
        ano = participacao.curso.ano_pagamento

        if ano not in atividades:
            ano_info = AnoInfo()
            atividades[ano] = ano_info

        participacao_info = ParticipacaoInfo()
        participacao_info.participacao = participacao
        participacao_info.pode_preencher_detalhamento = participacao.pode_preencher_detalhamento_atividade(request.user)

        atividades[ano].participacoes.append(participacao_info)

        atividades[ano].totais_horas_prevista += participacao.horas_prevista or 0
        atividades[ano].totais_horas_trabalhada += participacao.horas_trabalhada or 0
        atividades[ano].totais_valor_total += participacao.valor_total
        atividades[ano].tem_problemas_com_horas = atividades[ano].tem_problemas_com_horas or participacao.problema_com_detalhamento_horas

    return locals()


@rtr()
@login_required()
def participante(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_visualizar(request.user):
        raise PermissionDenied

    participante.detalhamento_horas_clean_valor_inicial_situacao()

    title = 'Participante de Curso/Concurso'

    pode_preencher_detalhamento = participante.pode_preencher_detalhamento_atividade(request.user)
    pode_avaliar_detalhamento = participante.pode_deferir_indeferir_detalhamento_atividade(request.user)
    # pode_gerar_documento_eletronico = participante.pode_gerar_documento_eletronico_detalhamento_atividade(request.user)
    pode_notificar_detalhamento_atividade = participante.pode_notificar_detalhamento_atividade(request.user)
    pode_gerar_compensacao_especifica = participante.pode_gerar_compensacao_especifica(request.user)

    return locals()


@login_required()
def notificar_detalhamento_atividade(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_notificar_detalhamento_atividade(request.user):
        raise PermissionDenied

    notificacao_ok = False

    if participante.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO:
        participante.notificar_preenchimento_detalhamento_atividade()
        notificacao_ok = True

    if participante.is_aguardando_avaliacao_detalhamento_horas:
        participante.notificar_avaliacao_detalhamento_atividade()
        notificacao_ok = True

    return httprr(
        f'{participante.get_absolute_url()}',
        'Notificação reenviada.' if notificacao_ok else 'Nenhuma notificação foi enviada.',
        'success' if notificacao_ok else 'warning',
    )


@rtr()
@login_required()
def preencher_detalhamento_atividade(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_preencher_detalhamento_atividade(request.user):
        raise PermissionDenied

    title = 'Detalhamento das Atividades Executadas'

    form = PreencherDetalhamentoAtividadeForm(request.POST or None, request=request, instance=participante)
    if form.is_valid():
        form.save()
        return httprr(f'{participante.get_absolute_url()}', 'Detalhamento das Atividades preenchido com sucesso.', close_popup=True)

    return locals()


@login_required()
def deferir_detalhamento_atividade(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_deferir_indeferir_detalhamento_atividade(request.user):
        raise PermissionDenied

    participante.deferir_detalhamento_atividade()

    return httprr(f'{participante.get_absolute_url()}', 'Detalhamento das Atividades deferido com sucesso.')


@login_required()
def gerar_documento_eletronico_detalhamento_atividade(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_gerar_documento_eletronico_detalhamento_atividade(request.user):
        raise PermissionDenied

    doc_gerado, msg = participante.gerar_documento_eletronico_detalhamento_atividade(request.user)

    return httprr(
        f'{participante.get_absolute_url()}',
        'Documento Eletrônico gerado com sucesso.' if doc_gerado else f'O Documento Eletrônico não foi gerado: {msg}',
        'success' if doc_gerado else 'error',
    )


@login_required()
def gerar_compensacao_especifica(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_gerar_compensacao_especifica(request.user):
        raise PermissionDenied

    compensacao_gerada = participante.gerar_compensacao_especifica(servidor_responsavel=participante.responsavel_compensacao_especifica)

    return httprr(
        f'{participante.get_absolute_url()}',
        'Compensação Específica gerada com sucesso.' if compensacao_gerada else 'A Compensação Específica não foi gerada.',
        'success' if compensacao_gerada else 'error',
    )


@rtr()
@login_required()
def indeferir_detalhamento_atividade(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.pode_deferir_indeferir_detalhamento_atividade(request.user):
        raise PermissionDenied

    title = 'Indeferir Detalhamento das Atividades Executadas'

    form = IndeferirDetalhamentoAtividadeForm(request.POST or None, request=request, instance=participante)
    if form.is_valid():
        form.save()
        return httprr(f'{participante.get_absolute_url()}', 'O Detalhamento das Atividades foi indeferido.', tag='error', close_popup=True)

    return locals()


@login_required()
@permission_required('cursos.delete_curso')
def curso_remover(request, id):
    curso = Curso.objects.get(id=id)
    if curso.pode_excluir_curso():
        curso.delete()
        return httprr('/admin/cursos/curso/', 'Curso/Concurso removido com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_participante(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.curso.pode_gerenciar_participante(request.user):
        return httprr('..', 'Você não tem permissão para editar participantes.', 'error')

    title = f'Editar Participante {participante.servidor}'
    form = ParticipanteForm(request.POST or None, instance=participante)
    if form.is_valid():
        form.save()
        return httprr('..', 'Participante editado com sucesso.')
    return locals()


@login_required()
def curso_iniciar(request, id):
    try:
        curso = get_object_or_404(Curso, id=id)

        if not _pode_iniciar_curso(curso, request):
            return HttpResponseForbidden('Você não tem permissão para iniciar o curso.')

        curso.iniciar()
        return httprr(request.META.get('HTTP_REFERER'), 'Curso iniciado com sucesso.')
    except ValidationError as e:
        return httprr(request.META.get('HTTP_REFERER'), e.message, 'error')


@login_required()
def ativar_desativar_detalhamento_atividade(request, id):
    try:
        curso = get_object_or_404(Curso, id=id)

        if not curso.pode_ativar_desativar_detalhamento_atividade(request.user):
            return PermissionDenied

        curso.ativar_desativar_detalhamento_atividade()

        return httprr(request.META.get('HTTP_REFERER'), 'Ação executada com sucesso.')
    except ValidationError as e:
        return httprr(request.META.get('HTTP_REFERER'), e.message, 'error')


@login_required()
def curso_finalizar(request, id):
    curso = get_object_or_404(Curso, id=id)

    if not _pode_finalizar_curso(curso, request):
        return PermissionDenied

    try:
        curso.finalizar()
        return httprr(f'{curso.get_absolute_url()}', 'Curso finalizado com sucesso.')
    except ValidationError as e:
        return httprr(f'{curso.get_absolute_url()}', e.message, 'error')


@rtr()
@login_required()
def add_participante(request, curso_id):
    title = 'Adicionar um Participante'
    curso_concurso = get_object_or_404(Curso, id=curso_id)

    if not curso_concurso.pode_gerenciar_participante(request.user):
        return httprr('..', 'Você não tem permissão para adicionar participantes.', 'error')

    form = ParticipanteForm(request.POST or None, curso=curso_concurso)
    if form.is_valid():
        form.save()
        return httprr('..', 'Participante adicionado com sucesso.')

    return locals()


@rtr()
@login_required()
def remover_participante(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    if not participante.curso.pode_gerenciar_participante(request.user):
        return httprr('..', 'Você não tem permissão para remover participantes.', 'error')

    participante.delete()
    return httprr(request.META.get('HTTP_REFERER'), 'Participante removido com sucesso.')


@rtr()
@login_required()
def deferir_participacao(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)
    try:
        responsavel = request.user.get_relacionamento()
        participante.deferir_participacao(responsavel)
        return httprr(request.META.get('HTTP_REFERER'), f'A participação do(a) servidor(a) {participante.servidor} foi deferida com sucesso.')
    except ValidationError as e:
        return httprr(request.META.get('HTTP_REFERER'), e.message, 'error')


@rtr()
@login_required()
def indeferir_participacao(request, participante_id):
    title = 'Indeferimento de Participante'

    participante = get_object_or_404(Participante, id=participante_id)

    form = IndeferimentoParticipanteForm(request.POST or None, participante=participante)

    if form.is_valid():
        form.processar()
        return httprr('..', f'A participação do(a) servidor(a) {participante.servidor} foi indeferida.')

    return locals()


@login_required()
def informar_cadastro_folha(request, id):
    curso = get_object_or_404(Curso, id=id)

    if not _pode_informar_cadastro_folha(curso, request):
        raise PermissionDenied

    try:
        curso.informar_cadastro_folha(request)
        return httprr(f'{curso.get_absolute_url()}', 'A ação foi realizada com sucesso.')
    except ValidationError as e:
        return httprr(f'{curso.get_absolute_url()}', e.message, 'error')


@rtr()
@login_required()
@permission_required('cursos.pode_ver_relatorio_pagamento_gecc')
def relatorio_pagamento(request):
    title = 'Relatório Financeiro para Pagamento de GECC'

    form = RelatorioFinanceiroPagamentoGECCForm(request.POST or None)
    if form.is_valid():
        ano = form.cleaned_data.get('ano')
        mes = form.cleaned_data.get('mes')
        return httprr(f'/cursos/relatorio_pagamento_gecc_pdf/{mes}/{ano}/')

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
@permission_required('cursos.pode_ver_relatorio_pagamento_gecc')
def relatorio_pagamento_gecc_pdf(request, mes, ano):
    mes_nome = Meses.get_mes(mes)
    ano = Ano.objects.get(ano=ano)

    relatorio = {}
    gecc_curso_valor = 0
    gecc_concurso_valor = 0
    gecc_atividade_extra_valor = 0
    gecc_total_valor = 0

    for p in Participante.objects.filter(mes_pagamento__isnull=False, mes_pagamento=mes, curso__ano_pagamento=ano).exclude(
        situacao=SituacaoParticipante.PENDENTE
    ):
        if not relatorio.get(p.curso.campus.sigla):
            relatorio[p.curso.campus.sigla] = {}
            relatorio[p.curso.campus.sigla]['gecc_curso_valor'] = 0
            relatorio[p.curso.campus.sigla]['gecc_concurso_valor'] = 0
            relatorio[p.curso.campus.sigla]['gecc_atividade_extra_valor'] = 0
            relatorio[p.curso.campus.sigla]['gecc_total_valor'] = 0

        _valor_total = p.valor_total or 0

        if p.curso.tipo == TipoCurso.CURSO:
            relatorio[p.curso.campus.sigla]['gecc_curso_valor'] += _valor_total
            gecc_curso_valor += _valor_total

        if p.curso.tipo == TipoCurso.CONCURSO:
            relatorio[p.curso.campus.sigla]['gecc_concurso_valor'] += _valor_total
            gecc_concurso_valor += _valor_total

        if p.curso.tipo == TipoCurso.ATIVIDADE_EXTERNA:
            relatorio[p.curso.campus.sigla]['gecc_atividade_extra_valor'] += _valor_total
            gecc_atividade_extra_valor += _valor_total

        relatorio[p.curso.campus.sigla]['gecc_total_valor'] += _valor_total
        gecc_total_valor += _valor_total

    relatorio_final = {}
    relatorio_final['gecc_curso_valor'] = gecc_curso_valor
    relatorio_final['gecc_concurso_valor'] = gecc_concurso_valor
    relatorio_final['gecc_atividade_extra_valor'] = gecc_atividade_extra_valor
    relatorio_final['gecc_total_valor'] = gecc_total_valor

    return locals()


@rtr()
@login_required()
def cota_anual_servidor(request):
    title = 'Cota Anual do Servidor'
    qs_participantes = (
        Participante.objects.all()
        .order_by('servidor__pessoa_fisica__nome', 'curso__ano_pagamento__ano')
        .distinct('servidor__pessoa_fisica__nome', 'curso__ano_pagamento__ano')
    )

    form = CotaAnualServidorGECCForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            qs_participantes = qs_participantes.filter(curso__ano_pagamento=form.cleaned_data.get('ano'))
        if form.cleaned_data.get('texto_busca'):
            strings = form.cleaned_data.get('texto_busca').split(' ')
            for string in strings:
                qs_participantes = qs_participantes.filter(servidor__pessoa_fisica__nome__icontains=string)

    return locals()


@rtr()
@login_required()
def liberar_participantes(request, curso_id):
    try:
        if not _pode_liberar_participantes(request):
            raise ValidationError('Você não tem permissão para executar esta ação.')

        curso = get_object_or_404(Curso, id=curso_id)

        # consultando os participantes que ainda não foram liberados

        responsavel_liberacao = request.user.get_relacionamento()

        for p in curso.participante_set.filter(situacao=SituacaoParticipante.AGUARDANDO_LIBERACAO):
            # se o participante tiver problemas com horas, NÃO será liberado automaticamente
            if p.problema_com_horas_insuficientes:
                continue

            p.situacao = SituacaoParticipante.LIBERADO
            p.responsavel_liberacao = responsavel_liberacao
            p.data_liberacao = datetime.today()

            p.save()

        return httprr(request.META.get('HTTP_REFERER'), 'A ação foi realizada com sucesso.')
    except ValidationError as e:
        return httprr(request.META.get('HTTP_REFERER'), e.message, 'error')


@rtr()
@login_required()
def editar_mes_pagamento(request, participante_id):
    if not _pode_mudar_situacao_curso_concurso(request):
        return httprr('..', 'Você não tem permissão para acessar esta funcionalidade.', 'error')

    participante = get_object_or_404(Participante, id=participante_id)
    title = f'Editar Mês de Pagamento - {participante}'
    form = EditarMesPagamentoGECCForm(request.POST or None, participante=participante)
    if form.is_valid():
        form.processar()
        return httprr('..', f'O mês de pagamento do participante {participante.servidor} foi atualizado com sucesso.')

    return locals()


@rtr()
@login_required()
def hora_prevista_to_hora_trabalhada(request, curso_id):
    try:
        curso = get_object_or_404(Curso, id=curso_id)
        if not _pode_adicionar_horas_participante(curso, request):
            raise ValidationError('Você não tem permissão para executar esta ação.')
        #
        # consultando os participantes que tem horas previstas
        for p in curso.participante_set.filter(horas_prevista__isnull=False):
            p.horas_trabalhada = p.horas_prevista
            p.preparar_preenchimento_detalhamento_atividade()

        return httprr(request.META.get('HTTP_REFERER'), 'A ação foi realizada com sucesso.')
    except ValidationError as e:
        return httprr(request.META.get('HTTP_REFERER'), e.message, 'error')


@login_required()
@permission_required('cursos.pode_informar_cadastro_em_folha')
def realizar_pagamento_participante_pendente(request, participante_id):
    participante = get_object_or_404(Participante, id=participante_id)

    try:
        # verifica se existe cronograma válido
        cronograma = Curso.get_cronograma_folha_valido()
        if not cronograma:
            raise ValidationError('Não existe cadastrado um cronograma para fechamento de folha que seja válido para os cálculos de pagamento.')

        curso = participante.curso
        curso.informar_execucao_pagamento_participantes(request.user, [participante.id], cronograma)

        return httprr(request.META.get('HTTP_REFERER') or f'{curso.get_absolute_url()}', 'A ação foi realizada com sucesso.')
    except ValidationError as e:
        return httprr(request.META.get('HTTP_REFERER') or f'{curso.get_absolute_url()}', e.message, 'error')


@rtr()
@login_required()
@permission_required('cursos.pode_informar_cadastro_em_folha')
def participantes_pendentes_pagamento(request):
    title = 'Lista de Participantes com Pendência de Pagamento'
    participantes = Participante.pendentes.all()

    form = FiltroPendentesPagamentoForm(request.GET or None)
    if form.is_valid():
        if form.cleaned_data.get('participante'):
            participantes = participantes.filter(servidor__pessoa_fisica__nome__icontains=form.cleaned_data.get('participante'))

        if form.cleaned_data.get('evento'):
            participantes = participantes.filter(curso__id=form.cleaned_data.get('evento'))

    return locals()


#################
# Permissões    #
#################
def _pode_iniciar_curso(curso, request):
    return curso.pode_iniciar_curso() and (
        curso.eh_responsavel(request.user.get_vinculo()) or request.user.has_perm('cursos.pode_gerenciar_curso_concurso')
    )


def _pode_finalizar_curso(curso: Curso, request):
    pode_finalizar_curso, _ = curso.pode_finalizar_curso(analisar_apenas_horas_trabalhadas=True)
    return pode_finalizar_curso and (
        curso.eh_responsavel(request.user.get_vinculo()) or request.user.has_perm('cursos.pode_gerenciar_curso_concurso')
    )


def _pode_adicionar_horas_participante(curso, request):
    return curso.pode_adicionar_horas_participante() and (
        curso.eh_responsavel(request.user.get_vinculo()) or request.user.has_perm('cursos.pode_gerenciar_curso_concurso')
    )


def _pode_gerenciar_participante(curso, request):
    return curso.pode_gerenciar_participante(request.user)


def _pode_informar_cadastro_folha(curso, request):
    return curso.situacao == SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA and request.user.has_perm('cursos.pode_informar_cadastro_em_folha')


def _pode_mudar_situacao_curso_concurso(request):
    return request.user.has_perm('cursos.pode_mudar_situacao_curso_concurso')


def _pode_liberar_participantes(request):
    return request.user.is_superuser
