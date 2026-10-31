from collections import OrderedDict
from datetime import date, timedelta
from os.path import expanduser, join

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.aggregates import Count
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.utils import get_uo
from djtools import layout
from djtools.signals import minhas_acoes
from djtools.templatetags.filters import in_group
from djtools.utils import documento, httprr, montar_timeline_horizontal, permission_required, rtr, send_notification
from progressoes.forms import (
    AssinaturaAvaliadoForm,
    AssinaturaAvaliadorForm,
    AssinaturaChefeForm,
    AssinaturaProcessoForm,
    AvaliacaoServidorFormFactory,
    EstagioProbatorioPeriodoAvaliadoresForm,
    ProcessoProgressaoPeriodoAvaliadoresForm,
    ProcessoProgressaoPeriodoForm,
    SelecionarProcessoEletronicoForm,
    SelecionarProtocoloForm,
    UltimaProgressaoForm,
    EscolherFonteAtualizacaoForm,
)
from progressoes.models import AvaliacaoModelo, ProcessoProgressao, ProcessoProgressaoAvaliacao, ProcessoProgressaoPeriodo, ServidorAProgredir
from rh.models import PosicionamentoPCA, Servidor, ServidorAfastamento


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    usuario_logado = request.user.get_vinculo()

    if usuario_logado.eh_servidor:
        numero_minhas_avaliacoes_pendentes = ProcessoProgressaoAvaliacao.objects.filter(
            avaliador=usuario_logado,
            status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_PENDENTE,
            periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE,
        ).count()
        if numero_minhas_avaliacoes_pendentes:
            pendencias.append(
                {
                    'titulo': f'Avaliaç{pluralize(numero_minhas_avaliacoes_pendentes, "ão,ões")} de Desempenho',
                    'subtitulo': 'a responder',
                    'qtd': numero_minhas_avaliacoes_pendentes,
                    'url': '/progressoes/minhas_avaliacoes/?tab=tab0',
                }
            )

        # assinaturas pendentes
        avaliacoes_pendentes_a_assinar_como_avaliado = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_avaliado(
            avaliado=usuario_logado
        )
        avaliacoes_pendentes_a_assinar_como_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_avaliador(
            avaliador=usuario_logado
        )
        avaliacoes_pendentes_a_assinar_como_chefe = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_chefe(chefe=usuario_logado)
        avaliacoes_com_assinaturas_pendentes = (
            avaliacoes_pendentes_a_assinar_como_avaliado | avaliacoes_pendentes_a_assinar_como_avaliador | avaliacoes_pendentes_a_assinar_como_chefe
        )

        numero_avaliacoes_com_assinaturas_pendentes_numero = avaliacoes_com_assinaturas_pendentes.distinct().count()
        if numero_avaliacoes_com_assinaturas_pendentes_numero:
            pendencias.append(
                {
                    'titulo': f'Avaliaç{pluralize(numero_avaliacoes_com_assinaturas_pendentes_numero, "ão,ões")} de Desempenho',
                    'subtitulo': 'a assinar',
                    'qtd': numero_avaliacoes_com_assinaturas_pendentes_numero,
                    'url': '/progressoes/minhas_avaliacoes/?tab=tab2',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    eh_rh_sistemico = in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    eh_rh_campus = in_group(request.user, 'Coordenador de Gestão de Pessoas,Operador de Gestão de Pessoas', ignore_groups_if_superuser=False)
    if eh_rh_sistemico or eh_rh_campus:
        id_uo_usuario_logado = get_uo(request.user).id if get_uo(request.user) else None
        numero_processos_progressao_a_iniciar = 0
        numero_processos_progressao_a_finalizar = 0
        numero_processos_identificados = 0
        if eh_rh_sistemico:
            numero_processos_progressao_a_iniciar = ProcessoProgressao.obter_processos_a_iniciar().count()
            numero_processos_progressao_a_finalizar = ProcessoProgressao.obter_processos_a_finalizar().count()
            numero_processos_identificados = ServidorAProgredir.objects.filter(avaliado__ativo=True).count()
        elif eh_rh_campus and id_uo_usuario_logado:
            numero_processos_progressao_a_iniciar = (
                ProcessoProgressao.obter_processos_a_iniciar().filter(avaliado__setor__uo_id=id_uo_usuario_logado).count()
            )
            numero_processos_progressao_a_finalizar = (
                ProcessoProgressao.obter_processos_a_finalizar().filter(avaliado__setor__uo_id=id_uo_usuario_logado).count()
            )
            numero_processos_identificados = ServidorAProgredir.objects.filter(
                avaliado__ativo=True, avaliado__setor__uo_id=id_uo_usuario_logado
            ).count()

        if numero_processos_progressao_a_iniciar:
            pendencias.append(
                {
                    'titulo': f'Avaliaç{pluralize(numero_processos_progressao_a_iniciar, "ão,ões")} de Desempenho',
                    'subtitulo': 'a iniciar',
                    'qtd': numero_processos_progressao_a_iniciar,
                    'url': '/admin/progressoes/processoprogressao/?tab=tab_a_iniciar',
                }
            )

        if numero_processos_progressao_a_finalizar:
            pendencias.append(
                {
                    'titulo': f'Avaliaç{pluralize(numero_processos_progressao_a_finalizar, "ão,ões")} de Desempenho',
                    'subtitulo': 'a finalizar',
                    'qtd': numero_processos_progressao_a_finalizar,
                    'url': '/admin/progressoes/processoprogressao/?tab=tab_a_finalizar',
                }
            )

        if numero_processos_identificados:
            pendencias.append(
                {
                    'titulo': f'Avaliaç{pluralize(numero_processos_identificados, "ão,ões")} de Desempenho',
                    'subtitulo': f'identificad{pluralize(numero_processos_identificados, "a,as")}',
                    'qtd': numero_processos_identificados,
                    'url': '/admin/progressoes/servidoraprogredir/',
                }
            )

    return pendencias


@layout.quadro('Progressões', icone='users')
def index_quadros(quadro, request):
    # Ações do Servidor
    usuario_logado = request.user
    if usuario_logado.eh_servidor:
        servidor_logado = usuario_logado.get_relacionamento()
        numero_meus_processos_progressao_em_tramite = (
            ProcessoProgressao.obter_processos_por_avaliado(servidor_logado).filter(status=ProcessoProgressao.STATUS_EM_TRAMITE).count()
        )
        if numero_meus_processos_progressao_em_tramite:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Avaliaç{} de Desempenho'.format(pluralize(numero_meus_processos_progressao_em_tramite, 'ão,ões')),
                    subtitulo='Em trâmite',
                    qtd=numero_meus_processos_progressao_em_tramite,
                    url='/progressoes/meus_processos/',
                )
            )

    return quadro


def _get_dados_novo_padrao(processo):
    if processo.is_tipo_progressao_merito:
        nivel_capacitacao = processo.avaliado.get_nivel_capacitacao()
        if nivel_capacitacao:
            pos_vert_anterior = processo.padrao_anterior.posicao_vertical
            pos_vert_novo = processo.padrao_novo.posicao_vertical
            #
            padrao_anterior = f'{nivel_capacitacao}{pos_vert_anterior}'
            _padrao_anterior_reenq = Servidor.calcula_novo_padrao(nivel_padrao=padrao_anterior, eh_tae=True)
            padrao_anterior_reenq = f'{processo.padrao_novo.classe}{_padrao_anterior_reenq}'
            #
            padrao_novo = f'{nivel_capacitacao}{pos_vert_novo}'
            _padrao_novo_reenq = Servidor.calcula_novo_padrao(nivel_padrao=padrao_novo, eh_tae=True)
            padrao_novo_reenq = f'{processo.padrao_novo.classe}{_padrao_novo_reenq}'
            return padrao_anterior_reenq, padrao_novo_reenq
    return None


@rtr()
@permission_required('progressoes.change_processoprogressao')
def editar_processo(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    #
    if processo.is_tipo_progressao_merito:
        title = 'Processo de Progressão'
    else:
        title = 'Processo de Estágio Probatório'

    # afastamentos_no_periodo = processo.obtem_afastamentos()
    afastamentos_no_periodo = []
    total_dias_interrompem_estagio_probatorio = 0

    for a in processo.obtem_afastamentos():
        total_dias_interrompem_estagio_probatorio += a.dias_incluindo_ultimo_dia()
        afastamentos_no_periodo.append(
            {
                'periodo': f'{a.data_inicio} a {a.data_termino}',
                'dias': a.dias_incluindo_ultimo_dia,
                'tipo': a.afastamento.get_tipo_display,
                'nome': a.afastamento.nome,
                'interrompe_tempo_servico': a.afastamento.interrompe_tempo_servico,
                'suspende_estagio_probatorio': a.afastamento.suspende_estagio_probatorio,
            }
        )
    afastamento_regra_24_meses = _afastamentos_24_meses(processo)

    #
    # dias afastanentos que interrompem progressão por mérito
    dias_afast_merito, _ids_afast_interrompe_progressao = processo.obtem_dias_afastamento_interrompe_progressao_merito()
    afastamentos_interrompem_progressao = []
    if dias_afast_merito > 0:
        try:
            for x in _ids_afast_interrompe_progressao:
                sa = ServidorAfastamento.objects.get(pk=x)
                afastamentos_interrompem_progressao.append(
                    {
                        'total_dias': sa.dias_incluindo_ultimo_dia(),
                        'nome': sa.afastamento.nome,
                        'data_inicio': sa.data_inicio,
                        'data_termino': sa.data_termino,
                    }
                )
        except Exception:
            pass

    servidor = processo.avaliado

    historico_setor = servidor.historico_setor_suap(
        data_inicio=processo.data_inicio_contagem_progressao, data_fim=processo.data_fim_contagem_progressao
    )
    historico_setor_siape = servidor.historico_setor_siape(
        data_inicio=processo.data_inicio_contagem_progressao, data_fim=processo.data_fim_contagem_progressao
    )
    historico_funcao = servidor.historico_funcao(data_inicio=processo.data_inicio_contagem_progressao, data_fim=processo.data_fim_contagem_progressao)
    #
    timeline_historico_setor = montar_timeline_horizontal(
        historico_setor,
        processo.data_inicio_contagem_progressao,
        processo.data_fim_contagem_progressao,
        'data_inicio_no_setor',
        'data_fim_no_setor',
        'setor',
        'Histórico de Setores SUAP',
    )
    #
    timeline_historico_setor_siape = montar_timeline_horizontal(
        historico_setor_siape,
        processo.data_inicio_contagem_progressao,
        processo.data_fim_contagem_progressao,
        'data_inicio_setor_lotacao',
        'data_fim_setor_lotacao',
        'setor_exercicio',
        'Setores Exercício SIAPE',
    )
    #
    timeline_historico_funcao = montar_timeline_horizontal(
        historico_funcao,
        processo.data_inicio_contagem_progressao,
        processo.data_fim_contagem_progressao,
        'data_inicio_funcao',
        'data_fim_funcao',
        'funcao_display',
        'Funções',
    )

    app_processo_eletronico_instalada = 'processo_eletronico' in settings.INSTALLED_APPS

    return locals()


# definição que retorna se o avaliado do processo tem dias do afastamento de 24 meses das licenças de saúde (alínea "b", inciso VIII do Art. 102 da Lei 8.112/90)
def _afastamentos_24_meses(processo):
    afastamento_regra_24_meses = {}
    dados_24_meses = processo.avaliado.dados_afastamentos_efetivo_exercicio_24_meses(contar_a_partir_de=processo.data_inicio_contagem_progressao)
    if dados_24_meses:
        for x, v in dados_24_meses.items():
            if hasattr(x, 'pk'):
                afast = x.afastamento
                if afast not in afastamento_regra_24_meses:
                    afastamento_regra_24_meses[afast] = [valor.get('data').strftime('%d/%m/%Y') for valor in v]
                else:
                    for valor in v:
                        afastamento_regra_24_meses[afast].append(valor.get('data').strftime('%d/%m/%Y'))
        #
        # limpando dicionário de dados que o valor é uma lista vazia
        indices_para_remover = [k for k, v in afastamento_regra_24_meses.items() if v == []]
        for k in indices_para_remover:
            del afastamento_regra_24_meses[k]
    #
    return afastamento_regra_24_meses


@documento(enumerar_paginas=False)
@rtr()
@permission_required('progressoes.view_processoprogressao')
def imprimir_processo(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    #
    if processo.status != ProcessoProgressao.STATUS_FINALIZADO:
        return httprr('..', message='Impressão não disponível.', tag='failure')
    #
    afastamentos_no_periodo = []
    total_dias_interrompem_estagio_probatorio = 0
    tem_observacao = processo.observacaoafastamentoefetivoexercicio_set.all().exists()
    if tem_observacao:
        afastamentos_servidor = ServidorAfastamento.objects.filter(
            pk__in=processo.observacaoafastamentoefetivoexercicio_set.all().values_list('afastamentos__pk', flat=True)
        )
        datas_afetadas = processo.observacaoafastamentoefetivoexercicio_set.all().values_list('data_afetada', flat=True)
        qtd_dias_descontados = processo.observacaoafastamentoefetivoexercicio_set.all().aggregate(Count('data_afetada'))['data_afetada__count']
    for a in processo.obtem_afastamentos():
        total_dias_interrompem_estagio_probatorio += a.dias_incluindo_ultimo_dia()
        afastamentos_no_periodo.append(
            {
                'dias': a.dias_incluindo_ultimo_dia,
                'tipo': a.afastamento.get_tipo_display,
                'nome': a.afastamento.nome,
                'interrompe_tempo_servico': a.afastamento.interrompe_tempo_servico,
                'suspende_estagio_probatorio': a.afastamento.suspende_estagio_probatorio,
            }
        )
    #
    afastamento_regra_24_meses = _afastamentos_24_meses(processo)
    #
    avaliacoes = []
    for periodo in processo.processoprogressaoperiodo_set.all().order_by('data_inicio'):
        avaliacoes.extend(periodo.processoprogressaoavaliacao_set.all().order_by('data_avaliacao'))
    return locals()


@rtr()
@permission_required('progressoes.view_processoprogressao')
def detalhes_processo(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)

    if processo.is_tipo_progressao_merito:
        title = 'Detalhes do Processo de Progressão'
    else:
        title = 'Detalhes do Processo de Estágio Probatório'

    app_processo_eletronico_instalada = 'processo_eletronico' in settings.INSTALLED_APPS

    return locals()


@rtr()
@permission_required('progressoes.view_processoprogressaoavaliacao')
def abrir_avaliacao(request, avaliacao_id):
    title = 'Avaliação de Desempenho'
    #
    avaliacao = get_object_or_404(ProcessoProgressaoAvaliacao, pk=ProcessoProgressaoAvaliacao.id_decoded(avaliacao_id))
    #
    FormClass = AvaliacaoServidorFormFactory(request, avaliacao)
    if not FormClass.usuario_pode_abrir:
        raise PermissionDenied
    else:
        # assinaturas
        assinatura_avaliado = AssinaturaAvaliadoForm(request=request, avaliacao=avaliacao)

        assinatura_avaliador = AssinaturaAvaliadorForm(request=request, avaliacao=avaliacao)

        assinatura_chefe = AssinaturaChefeForm(request=request, avaliacao=avaliacao)
        #
        form = FormClass(request.POST or None)
        if form.is_valid():
            if not form.avaliacao_somente_leitura:
                avaliador_estava_respondendo = form.is_avaliador_respondendo
                form.save()
                if avaliador_estava_respondendo and avaliacao.is_avaliada:
                    # solicita assinatura do avaliador
                    return httprr(
                        f'/progressoes/assinar_avaliacao/{avaliacao.id_encoded}/', message='Avaliação salva. Se desejar, pode assiná-la agora.'
                    )
                return httprr('..', message='Avaliação salva.')
            else:
                return httprr('..')
        #
        return locals()


@permission_required('progressoes.change_processoprogressao')
def reavaliar_avaliacao(request, avaliacao_id):
    avaliacao = get_object_or_404(ProcessoProgressaoAvaliacao, pk=ProcessoProgressaoAvaliacao.id_decoded(avaliacao_id))
    #
    FormClass = AvaliacaoServidorFormFactory(request, avaliacao)
    if not FormClass.usuario_pode_abrir:
        raise PermissionDenied
    else:
        avaliacao_form = FormClass()
        if avaliacao_form.is_rh_comentando:
            avaliacao.reavaliar()
            return httprr('..', message='Avaliação desbloqueada.')
        #
        return httprr('..', message='Não foi possível desbloquear a avaliação.', tag='failure')


@login_required()
@rtr()
def assinar_avaliacao(request, avaliacao_id):
    title = 'Assinaturas da Avaliação'
    #
    avaliacao = get_object_or_404(ProcessoProgressaoAvaliacao, pk=ProcessoProgressaoAvaliacao.id_decoded(avaliacao_id))
    #
    avaliacao_pode_abrir = AvaliacaoServidorFormFactory(request, avaliacao).usuario_pode_abrir
    #
    if not avaliacao_pode_abrir:
        raise PermissionDenied
    else:
        avaliacao_avaliada = avaliacao.is_avaliada
        if avaliacao_avaliada:
            #
            # a página de assinatura possui 3 forms, portanto, 3 submissões distintas
            processa_assinatura_avaliado = AssinaturaAvaliadoForm.senha_assinante_field_name in request.POST
            processa_assinatura_avaliador = AssinaturaAvaliadorForm.senha_assinante_field_name in request.POST
            processa_assinatura_chefe = AssinaturaChefeForm.senha_assinante_field_name in request.POST
            #
            form_assinatura_avaliado = AssinaturaAvaliadoForm(
                (processa_assinatura_avaliado and (request.POST or None)) or None, request=request, avaliacao=avaliacao
            )
            form_assinatura_avaliador = AssinaturaAvaliadorForm(
                (processa_assinatura_avaliador and (request.POST or None)) or None, request=request, avaliacao=avaliacao
            )
            form_assinatura_chefe = AssinaturaChefeForm(
                (processa_assinatura_chefe and (request.POST or None)) or None, request=request, avaliacao=avaliacao
            )
            #
            if form_assinatura_avaliado.avaliacao.data_assinatura_avaliado:
                form_assinatura_avaliado.SUBMIT_BUTTON = False

            if form_assinatura_avaliador.avaliacao.data_assinatura_avaliador:
                form_assinatura_avaliador.SUBMIT_BUTTON = False

            if form_assinatura_chefe.avaliacao.data_assinatura_chefe_imediato:
                form_assinatura_chefe.SUBMIT_BUTTON = False

            if processa_assinatura_avaliado and form_assinatura_avaliado.is_valid():
                form_assinatura_avaliado.save()
            if processa_assinatura_avaliador and form_assinatura_avaliador.is_valid():
                form_assinatura_avaliador.save()
            if processa_assinatura_chefe and form_assinatura_chefe.is_valid():
                form_assinatura_chefe.save()
    #
    return locals()


@login_required()
@rtr()
def assinar_processo(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    #
    if processo.is_tipo_progressao_merito:
        title = 'Assinar Processo de Progressão'
    else:
        title = 'Assinar Processo de Estágio Probatório'
    #
    usuario_logado = request.user.get_vinculo()
    #
    avaliacoes_avaliado = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_avaliado(usuario_logado).filter(
        periodo__processo_progressao=processo
    )
    avaliacoes_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_avaliador(usuario_logado).filter(
        periodo__processo_progressao=processo
    )
    avaliacoes_chefe = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_chefe(usuario_logado).filter(
        periodo__processo_progressao=processo
    )

    avaliacoes = (avaliacoes_avaliado | avaliacoes_avaliador | avaliacoes_chefe).distinct()
    #
    form_assinante = AssinaturaProcessoForm(request.POST or None, request=request)
    #
    if form_assinante.is_valid():
        for avaliacao in avaliacoes_avaliado:
            form_assinatura_do_avaliado = AssinaturaAvaliadoForm(request.POST or None, avaliacao=avaliacao)
            # confirma se o assinante eh realmente o esperado
            if form_assinatura_do_avaliado.get_assinante().id == form_assinante.assinante.get_vinculo().id:
                if form_assinatura_do_avaliado.is_valid():
                    form_assinatura_do_avaliado.gera_assinatura()
                    form_assinatura_do_avaliado.save()

        for avaliacao in avaliacoes_avaliador:
            form_assinatura_do_avaliador = AssinaturaAvaliadorForm(request.POST or None, avaliacao=avaliacao)
            # confirma se o assinante eh realmente o esperado
            if form_assinatura_do_avaliador.get_assinante().id == form_assinante.assinante.get_vinculo().id:
                if form_assinatura_do_avaliador.is_valid():
                    form_assinatura_do_avaliador.gera_assinatura()
                    form_assinatura_do_avaliador.save()

        for avaliacao in avaliacoes_chefe:
            form_assinatura_do_chefe = AssinaturaChefeForm(request.POST or None, avaliacao=avaliacao)
            # confirma se o assinante eh realmente o esperado
            if form_assinatura_do_chefe.get_assinante().id == form_assinante.assinante.get_vinculo().id:
                if form_assinatura_do_chefe.is_valid():
                    form_assinatura_do_chefe.gera_assinatura()
                    form_assinatura_do_chefe.save()
        #
        return httprr('/progressoes/minhas_avaliacoes/?tab=tab2')
    #
    return locals()


@rtr()
@permission_required('progressoes.change_processoprogressao')
def adicionar_periodo(request, processo_id):
    title = 'Adicionar Período ao Processo'
    #
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    if processo.is_a_iniciar:
        periodo_novo = ProcessoProgressaoPeriodo()
        periodo_novo.processo_progressao = processo

        #
        form = ProcessoProgressaoPeriodoForm(request.POST or None, instance=periodo_novo, processo_tipo=processo.tipo)
        if form.is_valid():
            #
            form.save()
            #
            return httprr('..', message='Período cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('progressoes.change_processoprogressao')
def adicionar_avaliadores(request, periodo_id):
    periodo = get_object_or_404(ProcessoProgressaoPeriodo, pk=periodo_id)
    processo = periodo.processo_progressao
    #
    if processo.is_a_iniciar:
        if request.POST:
            if periodo.processo_progressao.is_tipo_progressao_merito:
                form = ProcessoProgressaoPeriodoAvaliadoresForm(request.POST, instance=periodo)
            elif periodo.processo_progressao.is_tipo_estagio_probatorio:
                form = EstagioProbatorioPeriodoAvaliadoresForm(request.POST, instance=periodo)
            #
            if form.is_valid():
                form.save()
                #
                return httprr('..', message='Avaliadores cadastrados com sucesso.')
        else:
            if processo.is_tipo_progressao_merito:
                form = ProcessoProgressaoPeriodoAvaliadoresForm(instance=periodo)
            elif processo.is_tipo_estagio_probatorio:
                form = EstagioProbatorioPeriodoAvaliadoresForm(instance=periodo)
        #
        if processo.is_tipo_progressao_merito:
            title = 'Adicionar/Editar Avaliadores do Período'
        else:
            title = 'Adicionar/Editar Avaliador do Período'
        #
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('progressoes.change_processoprogressao')
def editar_periodo(request, periodo_id):
    title = 'Editar Período'
    #
    periodo = get_object_or_404(ProcessoProgressaoPeriodo, pk=periodo_id)
    if periodo.processo_progressao.is_a_iniciar:
        form = ProcessoProgressaoPeriodoForm(request.POST or None, instance=periodo)
        if request.POST:
            if form.is_valid():
                form.save()
                return httprr('..', message='Período atualizado com sucesso.')
        #
        return locals()
    else:
        raise PermissionDenied


@permission_required('progressoes.change_processoprogressao')
def remover_periodo(request, periodo_id):
    periodo = get_object_or_404(ProcessoProgressaoPeriodo, pk=periodo_id)
    if periodo.processo_progressao.is_a_iniciar:
        # "guarda" o processo
        processo = periodo.processo_progressao
        # exclui o período
        periodo.delete()
        # recalcula média do processo
        processo.calcular_media_processo()

        return httprr(f'/progressoes/editar_processo/{periodo.processo_progressao_id:d}/', message='Período removido com sucesso.')
    else:
        raise PermissionDenied


@permission_required('progressoes.change_processoprogressao')
def liberar_avaliacoes(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)

    if processo.status == ProcessoProgressao.STATUS_A_INICIAR:
        periodos_validos, periodos_mensagem = processo.validar_periodos()
        if periodos_validos:
            processo.status = ProcessoProgressao.STATUS_EM_TRAMITE
            processo.save()

            # definindo o tipo do processo
            tipo_processo = 'Avaliação de Desempenho'
            if processo.tipo == ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO:
                tipo_processo = 'Estágio Probatório'

            assunto = f'[SUAP] Processo de {tipo_processo}'
            vinculos_avaliadores = processo.obter_vinculos_avaliadores(incluir_avaliado=False)
            url = f'{settings.SITE_URL}/progressoes/minhas_avaliacoes/?tab=tab0'
            mensagem = f"""
                <h1>Avaliação de Processo de {tipo_processo}</h1>
                <p>Você foi selecionado como avaliador no <strong>Processo de {tipo_processo}</strong> do servidor
                <strong>{processo.avaliado.pessoa_fisica.nome}</strong>.</p>
                <p class="more-info">Para responder a avaliação, acesse: <a href="{url}">{url}</a></p>
                """
            if vinculos_avaliadores:
                send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos_avaliadores)

            # enviar e-mail de auto-avaliação apenas no processo de avaliação de desempenho
            if processo.tipo == ProcessoProgressao.TIPO_PROGRESSAO_MERITO:
                mensagem = f"""
                    <h1>Avaliação de Processo de {tipo_processo}</h1>
                    <p>{processo.avaliado.pessoa_fisica.nome}, o seu Processo de {tipo_processo} foi iniciado.</p>
                    <p class="more-info">Para responder a autoavaliação, acesse: <a href="{url}">{url}</a></p>"""
                if processo.avaliado:
                    send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo.avaliado.get_vinculo()])

            avaliacoes_liberadas = processo.obter_avaliacoes()
            for avaliacao_liberada in avaliacoes_liberadas:
                avaliacao_liberada.numero_liberacoes += 1  # incrementa o número de liberações
                avaliacao_liberada.save()
            return httprr(
                f'/progressoes/editar_processo/{processo.id:d}/', message='Avaliações liberadas com sucesso. Os avaliadores foram notificados.'
            )
        else:
            return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message=periodos_mensagem, tag='warning')
    else:
        return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Avaliações já liberadas.', tag='warning')


@permission_required('progressoes.change_processoprogressao')
def finalizar_processo(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    #
    if processo.pode_finalizar:
        finalizado, mensagem = processo.finalizar_processo()
        if finalizado:
            return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message=mensagem)
        else:
            return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message=mensagem, tag='warning')
    #
    return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Processo já finalizado ou ainda pendente.', tag='warning')


@permission_required('progressoes.change_processoprogressao')
def gerar_protocolo_processo_eletronico(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    if not processo.is_finalizado:
        raise PermissionDenied
    try:
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            avaliacoes_pdf_content = imprimir_processo(request, processo_id).content

            file_tmp = None

            if settings.DEBUG:
                try:
                    # home do usuário (windows ou linux)
                    dir_home = expanduser('~')
                    file_tmp = join(dir_home, f'progressao_processo_{processo_id}.pdf')
                except Exception:
                    # padrão produção (linux)
                    file_tmp = f'/tmp/progressao_processo_{processo_id}.pdf'

            if not file_tmp:
                file_tmp = f'/tmp/progressao_processo_{processo_id}.pdf'

            avaliacoes_pdf_arquivo_em_disco = open(file_tmp, 'wb+')
            avaliacoes_pdf_arquivo_em_disco.write(avaliacoes_pdf_content)

            processo.gerar_processo_eletronico(avaliacoes_pdf_arquivo_em_disco)

            mensagem = 'Processo eletrônico gerado com sucesso.'
        else:
            processo.gerar_protocolo()

            mensagem = 'Protocolo gerado com sucesso.'
        return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message=mensagem)
    except Exception as erro:
        return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message=str(erro), tag='warning')


@rtr()
@permission_required('progressoes.change_processoprogressao')
def selecionar_protocolo_processo_eletronico(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)

    if not processo.is_finalizado:
        raise PermissionDenied

    if 'processo_eletronico' in settings.INSTALLED_APPS:
        form = SelecionarProcessoEletronicoForm(request.POST or None, instance=processo)
        processo_tipo = 'Processo Eletrônico'
    else:
        form = SelecionarProtocoloForm(request.POST or None, instance=processo)
        processo_tipo = 'Protocolo'

    title = f'Selecionar {processo_tipo}'

    if form.is_valid():
        form.save()
        return httprr('..', message=f'{processo_tipo} salvo.')

    return locals()


@permission_required('progressoes.change_processoprogressao')
def reabrir_processo(request, processo_id):
    #
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    #
    if processo.status == ProcessoProgressao.STATUS_FINALIZADO:
        processo.status = ProcessoProgressao.STATUS_EM_TRAMITE
        processo.save()
        return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Processo reaberto.')
    #
    return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Processo não finalizado.', tag='warning')


@permission_required('progressoes.change_processoprogressao')
def cancelar_tramite(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)

    if processo.status == ProcessoProgressao.STATUS_EM_TRAMITE:
        processo.status = ProcessoProgressao.STATUS_A_INICIAR
        processo.save()
        return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Processo com trâmite cancelado.')

    return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Processo não está em trâmite.', tag='warning')


@rtr()
@permission_required('progressoes.view_processoprogressao')
def meus_processos(request):
    title = 'Meus Processos'
    #
    avaliado = request.user.get_relacionamento()
    lista_processos = ProcessoProgressao.obter_processos_por_avaliado(avaliado)
    #
    return locals()


@rtr()
@permission_required('progressoes.view_processoprogressaoavaliacao')
def minhas_avaliacoes(request):
    title = 'Minhas avaliações de progressão'

    # usuário logado
    servidor_logado = request.user.get_vinculo()

    ##########################################
    # universo das avaliações (processos em tramite ou finalizados)

    # avaliações como avaliado
    select_related_processo_progressao_avaliacao = [
        'periodo',
        'avaliador',
        'periodo__setor',
        'periodo__avaliacao_modelo',
        'periodo__processo_progressao',
        'periodo__processo_progressao__avaliado',
    ]
    #
    # para ser um avaliado, o usuário deve ser um Servidor
    lista_avaliacoes_como_avaliado = ()  # garantindo uma tupla vazia
    if servidor_logado.eh_servidor():
        lista_avaliacoes_como_avaliado = (
            ProcessoProgressaoAvaliacao.avaliacoes_como_avaliado(servidor_logado.relacionamento)
            .exclude(periodo__processo_progressao__status=ProcessoProgressao.STATUS_A_INICIAR)
            .select_related(*select_related_processo_progressao_avaliacao)
        )

    # avaliações como avaliador
    lista_avaliacoes_como_avaliador = (
        ProcessoProgressaoAvaliacao.avaliacoes_como_avaliador(servidor_logado)
        .exclude(periodo__processo_progressao__status=ProcessoProgressao.STATUS_A_INICIAR)
        .select_related(*select_related_processo_progressao_avaliacao)
    )

    # avaliações como chefe
    lista_avaliacoes_como_chefe = (
        ProcessoProgressaoAvaliacao.avaliacoes_como_chefe(servidor_logado)
        .exclude(periodo__processo_progressao__status=ProcessoProgressao.STATUS_A_INICIAR)
        .select_related(*select_related_processo_progressao_avaliacao)
    )

    ##########################################
    # PENDENTES DE AVALIAÇÃO
    ############
    lista_avaliacoes_pendentes_avaliar = ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_avaliar(
        qs_avaliacoes_como_avaliador=lista_avaliacoes_como_avaliador
    )

    ##########################################
    # AVALIADAS
    lista_avaliacoes_avaliadas = ProcessoProgressaoAvaliacao.avaliacoes_avaliadas(
        qs_avaliacoes_como_avaliador=lista_avaliacoes_como_avaliador
    ).order_by('-data_avaliacao')

    ##########################################
    # PENDENTES DE ASSINATURA
    ############

    # pendentes de assinatura como avaliado
    lista_avaliacoes_pendentes_assinar_como_avaliado = (
        ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_avaliado(qs_avaliacoes_como_avaliado=lista_avaliacoes_como_avaliado)
        .filter(
            periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE  # processos em tramite
        )
        .select_related(*select_related_processo_progressao_avaliacao)
    )

    # pendentes de assinatura como avaliador
    lista_avaliacoes_pendentes_assinar_como_avaliador = (
        ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_avaliador(qs_avaliacoes_como_avaliador=lista_avaliacoes_como_avaliador)
        .filter(
            periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE  # processos em tramite
        )
        .select_related(*select_related_processo_progressao_avaliacao)
    )

    # pendentes de assinatura como chefe
    lista_avaliacoes_pendentes_assinar_como_chefe = (
        ProcessoProgressaoAvaliacao.avaliacoes_pendentes_a_assinar_como_chefe(qs_avaliacoes_como_chefe=lista_avaliacoes_como_chefe)
        .filter(
            periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE  # processos em tramite
        )
        .select_related(*select_related_processo_progressao_avaliacao)
    )

    # pendentes de assinatura (todas)
    lista_avaliacoes_pendentes_assinar = (
        (
            lista_avaliacoes_pendentes_assinar_como_avaliado
            | lista_avaliacoes_pendentes_assinar_como_avaliador
            | lista_avaliacoes_pendentes_assinar_como_chefe
        )
        # .order_by('periodo__processo_progressao__avaliado__pessoa_fisica__nome', 'avaliador__pessoa_fisica__nome')
        .distinct()
    ).select_related(*select_related_processo_progressao_avaliacao)

    # pendentes de assinatura por processo
    lista_avaliacoes_pendentes_assinar_por_processo = OrderedDict()  # {'id_processo': (processo, avaliacoes)}
    for avaliacao in lista_avaliacoes_pendentes_assinar:
        processo = avaliacao.periodo.processo_progressao
        if processo.id not in lista_avaliacoes_pendentes_assinar_por_processo:
            lista_avaliacoes_pendentes_assinar_por_processo[processo.id] = (processo, [])
        lista_avaliacoes_pendentes_assinar_por_processo[processo.id][1].append(avaliacao)

    ##########################################
    # ASSINADAS
    ############

    # assinadas como avaliado
    lista_avaliacoes_assinadas_como_avaliado = ProcessoProgressaoAvaliacao.avaliacoes_assinadas_como_avaliado(
        qs_avaliacoes_como_avaliado=lista_avaliacoes_como_avaliado
    ).select_related(*select_related_processo_progressao_avaliacao)

    # assinadas como avaliador
    lista_avaliacoes_assinadas_como_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_assinadas_como_avaliador(
        qs_avaliacoes_como_avaliador=lista_avaliacoes_como_avaliador
    ).select_related(*select_related_processo_progressao_avaliacao)

    # assinadas como chefe
    lista_avaliacoes_assinadas_como_chefe = ProcessoProgressaoAvaliacao.avaliacoes_assinadas_como_chefe(
        qs_avaliacoes_como_chefe=lista_avaliacoes_como_chefe
    ).select_related(*select_related_processo_progressao_avaliacao)

    # assinadas (todas)
    lista_avaliacoes_assinadas_todas = (
        (lista_avaliacoes_assinadas_como_avaliado | lista_avaliacoes_assinadas_como_avaliador | lista_avaliacoes_assinadas_como_chefe)
        .distinct()
        .select_related(*select_related_processo_progressao_avaliacao)
    )

    # ordena as avaliações assinadas pela última data de assinatura (são 3 assinaturas possíveis por avaliação)
    lista_avaliacoes_assinadas_temp = {}  # {key_data_assinatura: [última_data_assinatura, avaliacao], ...}
    for avaliacao_assinada in lista_avaliacoes_assinadas_todas:
        datas_assinatura = []
        if avaliacao_assinada in lista_avaliacoes_assinadas_como_avaliado:
            if avaliacao_assinada.data_assinatura_avaliado:
                datas_assinatura.append(avaliacao_assinada.data_assinatura_avaliado)
        if avaliacao_assinada in lista_avaliacoes_assinadas_como_avaliador:
            if avaliacao_assinada.data_assinatura_avaliador:
                datas_assinatura.append(avaliacao_assinada.data_assinatura_avaliador)
        if avaliacao_assinada in lista_avaliacoes_assinadas_como_chefe:
            if avaliacao_assinada.data_assinatura_chefe_imediato:
                datas_assinatura.append(avaliacao_assinada.data_assinatura_chefe_imediato)
        #
        if datas_assinatura:
            data_assinatura = max(datas_assinatura)
            key_data_assinatura = '{}_{}'.format(data_assinatura.strftime('%Y%m%d'), avaliacao_assinada.id)
        else:
            data_assinatura = None
            key_data_assinatura = f'00000000_{avaliacao_assinada.id}'
        #
        lista_avaliacoes_assinadas_temp[key_data_assinatura] = [data_assinatura, avaliacao_assinada]

    lista_avaliacoes_assinadas = []  # [[última_data_assinatura, avaliacao], [última_data_assinatura, avaliacao], ...]
    for key_data_assinatura in sorted(lista_avaliacoes_assinadas_temp.keys(), reverse=True):
        lista_avaliacoes_assinadas.append(lista_avaliacoes_assinadas_temp[key_data_assinatura])

    return locals()


@rtr()
@permission_required('progressoes.view_avaliacaomodelo')
def avaliacao_modelo_visualizar(request, avaliacao_modelo_id):
    avaliacao = AvaliacaoModelo.objects.get(pk=avaliacao_modelo_id)
    title = 'Visualização de Modelo de Avaliação'
    return locals()


@rtr()
@permission_required('progressoes.change_processoprogressao')
def calcular_novos_processos(request):
    title = 'Novos Processos de Progressão'
    novos_processos = ProcessoProgressao.calcular_servidores_a_progredir()
    return locals()


@rtr()
@permission_required('progressoes.change_processoprogressao')
def recalcular_medias(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    #
    processo_periodos = processo.processoprogressaoperiodo_set.all()
    for processo_periodo in processo_periodos:
        processo_periodo.calcular_media_periodo()  # a média do processo também será atualizada
    #
    return httprr(f'/progressoes/editar_processo/{processo.id:d}/')


@rtr()
@permission_required('progressoes.change_processoprogressao')
def recalcular_intersticio(request, processo_id):
    processo = get_object_or_404(ProcessoProgressao, pk=processo_id)
    processo.recalcular_intersticio()
    #
    return httprr(f'/progressoes/editar_processo/{processo.id:d}/', message='Interstício recalculado com sucesso.')


@rtr()
@permission_required('progressoes.change_processoprogressao')
def ultima_progressao_data(request, id):
    title = 'Adicionar a Data de Início da Contagem Manualmente'
    processo = get_object_or_404(ServidorAProgredir, pk=id)
    form = UltimaProgressaoForm(request.POST or None, instance=processo)
    if form.is_valid():
        form.processar(form.cleaned_data)
        return httprr('..', message='Data cadastrada com sucesso.', close_popup=True)
    #
    return locals()


@rtr()
@permission_required('progressoes.add_processoprogressao')
def criar_processo(request, id, novo_periodo=None):
    try:
        retorno_url = request.META.get('HTTP_REFERER')
        with transaction.atomic():
            servidor_a_progredir = get_object_or_404(ServidorAProgredir, pk=id)
            #
            # definindo a data da última progressão
            data_ultima_progressao = servidor_a_progredir.data_inicio_contagem
            if servidor_a_progredir.data_inicio_contagem_manual:
                data_ultima_progressao = servidor_a_progredir.data_inicio_contagem_manual
            #
            # criando o obj ProcessoProgressao
            processo_progressao = ProcessoProgressao()
            if novo_periodo:
                processo_progressao.intersticio_ajustado_novo_periodo = True
            processo_progressao.data_inicio_contagem_progressao = data_ultima_progressao
            processo_progressao.avaliado = servidor_a_progredir.avaliado
            processo_progressao.registro_a_progredir = servidor_a_progredir
            # adicionando saldo calculado no relatório de servidores a progredir
            processo_progressao.dias_saldo = servidor_a_progredir.saldo_dias
            # calcula e define a data (final) da progressao
            processo_progressao.calcular_data_de_progressao()
            # prepara o proximo padrao de vencimento (se for o caso)
            processo_progressao.calcular_proximo_padrao_vencimento(servidor_a_progredir.avaliado)
            processo_existe = ProcessoProgressao.objects.filter(
                avaliado=servidor_a_progredir.avaliado, data_fim_contagem_progressao=processo_progressao.data_fim_contagem_progressao
            ).exists()
            if not processo_existe:
                processo_progressao.status = ProcessoProgressao.STATUS_A_INICIAR
                processo_progressao.save(force_insert=True)
                servidor_a_progredir.processo_criado = True
                servidor_a_progredir.save()
                retorno_url = f'/progressoes/editar_processo/{processo_progressao.pk}/'
                return httprr(retorno_url, message='Processo de progressão criando com sucesso.')
    except Exception as ex:
        return httprr(retorno_url, message=f'Erro: {ex}', tag='error')
    return httprr(retorno_url, message='Não foi possível criar o processo de progressão. Verifique se o processo já existe.', tag='error')


@permission_required('progressoes.pode_ver_relatorio_progressao')
def executar_importacao(request):
    if request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico'):
        from django.core.management import call_command

        call_command('servidores_a_progredir', '-s', interactive=False, raise_exception=False, verbosity=0)
        return httprr(request.META.get('HTTP_REFERER'), message='Importação executada com sucesso.')
    else:
        return httprr(request.META.get('HTTP_REFERER'), message='Usuário não autorizado para esta operação.', tag='error')


@permission_required('progressoes.pode_ver_relatorio_progressao')
def marcar_como_capacitacao(request, id):
    with transaction.atomic():
        servidor_a_progredir = get_object_or_404(ServidorAProgredir, pk=id)
        qs_pgr = PosicionamentoPCA.objects.filter(
            pca__servidor=servidor_a_progredir.avaliado, data_inicio_posicionamento_pca=servidor_a_progredir.data_inicio_contagem
        )
        if qs_pgr.exists():
            pos = qs_pgr[0]
            pos.eh_capacitacao = True
            pos.save()
            servidor_a_progredir.delete()
            # recalculando...
            ProcessoProgressao.calcular_servidores_a_progredir(salvar_processos=True, matricula=servidor_a_progredir.avaliado.matricula)
        else:
            return httprr(request.META.get('HTTP_REFERER'), message='Não foi encontrado nenhum posicionamento PCA para o registro.', tag='error')
    return httprr(request.META.get('HTTP_REFERER'), message='Registro marcado como capacitação com sucesso.')


@permission_required('progressoes.pode_ver_relatorio_progressao')
def atualizar_dados_progredir(request, id):
    if not request.user.has_perm('rh.eh_rh_sistemico') and not request.user.has_perm('rh.eh_rh_campus'):
        raise PermissionDenied('Você não tem permissão para acessar essa funcionalidade.')
    try:
        with transaction.atomic():
            servidor_a_progredir = get_object_or_404(ServidorAProgredir, pk=id)
            data_referencia = date.today()
            if servidor_a_progredir.data_inicio_contagem_manual:
                data_referencia = servidor_a_progredir.data_inicio_contagem_manual
            # verificando a necessidade de criar registro novo
            ProcessoProgressao.calcular_servidores_a_progredir(
                salvar_processos=True,
                data_referencia=data_referencia,
                matricula=servidor_a_progredir.avaliado.matricula,
                atualizando=True,
                ignorar_lista_matricula=True,
                pk_relatorio=servidor_a_progredir.pk,
            )
    except Exception as ex:
        return httprr(request.META.get('HTTP_REFERER'), message=ex, tag='error')
    return httprr(request.META.get('HTTP_REFERER'), message='Usuário atualizado com sucesso.')


@rtr('detalhes_servidoraprogredir.html')
@permission_required('progressoes.pode_ver_relatorio_progressao')
def servidoraprogredir(request, id):
    servidor_a_progredir = get_object_or_404(ServidorAProgredir, pk=id)
    title = f'Dados a progredir de {servidor_a_progredir.avaliado}'
    #
    # criando um objeto ProcessoProgressao para ter acessar a algumas informações geradas apenas quando existe uma instância desse objeto
    pp = ProcessoProgressao()
    pp.data_inicio_contagem_progressao = servidor_a_progredir.data_inicio_contagem
    pp.data_fim_contagem_progressao = servidor_a_progredir.data_fim_contagem_normal
    pp.avaliado = servidor_a_progredir.avaliado
    pp.tipo = ProcessoProgressao.TIPO_PROGRESSAO_MERITO
    try:
        pp.calcular_proximo_padrao_vencimento(pp.avaliado)
    except ValidationError as error:
        url = request.META.get('HTTP_REFERER')
        if not url:
            url = f'/admin/progressoes/servidoraprogredir/?q={servidor_a_progredir.avaliado.matricula}'
        return httprr(url, message=' '.join(error.messages), tag='error')
    #
    # dias afastamentos
    dias_afast, _ = pp.obtem_afastamentos_numero_dias()
    #
    # dias afastamentos de efetivo exercício
    dias_afast_efet, _ = pp.obtem_dias_desconto_efetivo_exercicio()
    #
    # dias afastanentos que interrompem progressão por mérito
    dias_afast_merito, _ = pp.obtem_dias_afastamento_interrompe_progressao_merito()

    dias_regra_24_meses = pp.avaliado.dados_afastamentos_efetivo_exercicio_24_meses(contar_a_partir_de=pp.data_inicio_contagem_progressao)

    # calculo com dias de afastamentos que interrompem tempo de serviço apenas
    nova_data_interrompe_tempo_servico = pp.data_fim_contagem_progressao + timedelta(days=dias_afast)

    ultimo_pca = servidor_a_progredir.avaliado.ultimo_pca_progressao_merito()
    ultima_progressao = ProcessoProgressao.ultima_progressao_servidor(servidor_a_progredir.avaliado)

    #
    # mostrar calculo da nova data fim da contagem?
    mostrar_calculo = dias_afast_merito > 0 or dias_afast_efet > 0 or dias_afast > 0
    soma_dias_afastamentos = dias_afast_merito + dias_afast_efet + dias_afast
    nova_data_final_contagem = pp.data_fim_contagem_progressao + timedelta(soma_dias_afastamentos)
    extenso_calculo = f"""
        Tempo de serviço interrompido: {dias_afast} +
        Desconto de efetivo exercício: {dias_afast_efet} +
        Tempo interrompido de progressão: {dias_afast_merito} =
        {soma_dias_afastamentos}
        <br />
        Nova data final de contagem: {pp.data_fim_contagem_progressao.strftime('%d/%m/%Y')} + {soma_dias_afastamentos} dia(s) = <strong style="font-size: 18px">{nova_data_final_contagem.strftime('%d/%m/%Y')}</strong>
        """

    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_progressoes(request, data, datahora_inicio, datahora_fim):
    if request.user.eh_servidor:
        servidor_id = request.user.get_relacionamento().id

        filters_progressoes_assinadas = {}
        if datahora_inicio:
            filters_progressoes_assinadas['data_assinatura_avaliador__gte'] = datahora_inicio
        if datahora_fim:
            filters_progressoes_assinadas['data_assinatura_avaliador__lte'] = datahora_fim
        qs_avaliacoes_progressao = (
            ProcessoProgressaoAvaliacao.objects.filter(avaliador_id=servidor_id, **filters_progressoes_assinadas)
            .select_related('periodo__processo_progressao', 'periodo__processo_progressao__avaliado')
            .order_by('data_assinatura_avaliador')
        )
        for avaliacao_progressao in qs_avaliacoes_progressao:
            tipo_processo = avaliacao_progressao.periodo.processo_progressao.get_tipo_display()
            data.append(
                (
                    'Avaliações Funcionais',
                    f'{tipo_processo}',
                    f'Servidor(a) {avaliacao_progressao.periodo.processo_progressao.avaliado}',
                    f'em {avaliacao_progressao.data_assinatura_avaliador.strftime("%d/%m/%Y")}',
                    f'{avaliacao_progressao.get_absolute_url()}',
                )
            )


@rtr()
@permission_required('progressoes.pode_ver_relatorio_progressao')
def escolher_fonte_atualizacao(request, id):
    #
    if not request.user.has_perm('rh.eh_rh_sistemico') and not request.user.has_perm('rh.eh_rh_campus'):
        raise PermissionDenied('Você não tem permissão para acessar essa funcionalidade.')
    #
    processo = get_object_or_404(ServidorAProgredir, pk=id)
    title = f'Divergência de datas encontrada para {processo.avaliado}'
    #
    form = EscolherFonteAtualizacaoForm(request.POST or None, instance=processo)
    #
    if form.is_valid():
        form.processar()
        return httprr('..', message='Atualização salva com sucesso.', close_popup=True)
    #
    return locals()
