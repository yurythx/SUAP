from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from os.path import expanduser, join

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import pluralize
from django_tables2 import LinkColumn, TemplateColumn
from django_tables2.columns.base import Column
from django_tables2.utils import Accessor
from django.utils.text import capfirst
from sentry_sdk import capture_exception

from djtools import layout
from djtools.db import transaction
from djtools.tables import TableReportPlus, get_table
from djtools.utils import JsonResponse, documento, httprr, permission_required, rtr
from progressao_docente.forms import (
    AceleracaoProgressaoForm,
    AdicionarPontuacaoForm,
    AssinaturaAvaliadorForm,
    ConcluirReavaliacaoForm,
    DataBaseProgressaoDocenteFiltroForm,
    EditarDataBaseProgressaoDocente,
    InconsistenciasRelatorioFiltroForm,
    ReavaliacaoObservacaoForm,
)
from progressao_docente.models import (
    Avaliacao,
    AvaliacaoItem,
    ConfiguracaoProgressaoDocente,
    Criterio,
    DiscenteAptosAvaliacao,
    DocenteAProgredir,
    Formulario,
    ProgressaoDocente,
)
from rh.models import Servidor
from rh.utils import is_blank


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Lista pendências de Progressão Docente atribuídas ao usuário logado.

    Consolida em poucas consultas as contagens de processos a avaliar,
    despachar e homologar segundo o papel do usuário (servidor, chefia,
    membro CPPD, gestor do RH), evitando os antigos múltiplos counts.

    Args:
        request: requisição HTTP usada para obter vínculo e papéis do usuário.

    Returns:
        list[dict]: cartões com ``titulo``, ``subtitulo``, ``qtd`` e ``url``;
        lista vazia quando o app não está instalado ou não há ações pendentes.
    """
    pendencias = []

    if 'progressao_docente' in settings.INSTALLED_APPS:
        usuario = request.user.get_vinculo()
        # quando usuário é aluno
        if usuario.eh_aluno():
            #
            aluno = request.user.get_relacionamento()
            #
            qs_discente_apto = DiscenteAptosAvaliacao.objects.filter(
                matricula=aluno.matricula,
                avaliacao__formulario__criterio__avaliacao_discente=True,
                avaliacao_realizada=False,
                nao_reconhece_docente=False,
                avaliacao__situacao__in=[Avaliacao.AGUARDANDO_PREENCHIMENTO, Avaliacao.EM_AVALIACAO],
            ).distinct('progressao__pk')  # garantindo que o aluno verá apenas uma avaliação por processo de progressão docente
            qtd_discente_apto = qs_discente_apto.count()
            if qtd_discente_apto:
                pendencias.append(
                    {
                        'titulo': 'Avaliação Docente',
                        'subtitulo': 'aguardando avaliação',
                        'qtd': qtd_discente_apto,
                        'url': '/progressao_docente/ver_avaliacoes_discente/',
                    }
                )
        elif usuario.eh_servidor():
            # quando é servidor
            if usuario.eh_servidor():
                usuario_logado = request.user.get_relacionamento()
                # verificando se existe alguma avaliação que necessita de preenchimento por parte do servidor (quando é o avaliado)
                contagens_avaliado = Avaliacao.objects.filter(progressao__avaliado=usuario_logado).aggregate(
                    aguardando_preenchimento=Count('id', filter=Q(situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO)),
                    aguardando_ciencia=Count('id', filter=Q(situacao=Avaliacao.AGUARDANDO_CIENCIA_RESULTADO)),
                )
                if contagens_avaliado['aguardando_preenchimento']:
                    pendencias.append(
                        {
                            'titulo': 'Avaliações de Progressão Docente',
                            'subtitulo': 'aguardando preenchimento',
                            'qtd': contagens_avaliado['aguardando_preenchimento'],
                            'url': '/admin/progressao_docente/avaliacao/?tab=tab_aguardando_preenchimento',
                        }
                    )
                if contagens_avaliado['aguardando_ciencia']:
                    pendencias.append(
                        {
                            'titulo': 'Avaliações de Progressão Docente',
                            'subtitulo': 'aguardando ciência de resultado',
                            'qtd': contagens_avaliado['aguardando_ciencia'],
                            'url': '/admin/progressao_docente/avaliacao/?tab=tab_aguardando_ciencia',
                        }
                    )
                #
                # Avaliações onde o usuário é o "primeiro avaliador" (semântica preservada do código antigo).
                # Era loop em TODAS Avaliações em EM_AVALIACAO/REAVALIACAO + N queries (avaliadores.first() + get_vinculo()).
                # Agora: 1 query SQL via Subquery no through table do M2M + aggregate condicional.
                primeiro_avaliador_id_sq = (
                    Avaliacao.avaliadores.through.objects.filter(avaliacao_id=OuterRef('pk')).order_by('servidor_id').values('servidor_id')[:1]
                )
                contagens_avaliador = (
                    Avaliacao.objects.filter(situacao__in=[Avaliacao.EM_AVALIACAO, Avaliacao.REAVALIACAO])
                    .annotate(primeiro_avaliador_id=Subquery(primeiro_avaliador_id_sq))
                    .filter(primeiro_avaliador_id=usuario_logado.pk)
                    .aggregate(
                        em_avaliacao=Count('id', filter=Q(situacao=Avaliacao.EM_AVALIACAO)),
                        reavaliacao=Count('id', filter=Q(situacao=Avaliacao.REAVALIACAO)),
                    )
                )
                if contagens_avaliador['em_avaliacao']:
                    pendencias.append(
                        {
                            'titulo': 'Avaliações de Progressão Docente',
                            'subtitulo': 'aguardando avaliação',
                            'qtd': contagens_avaliador['em_avaliacao'],
                            'url': '/admin/progressao_docente/avaliacao/?tab=tab_em_avaliacao',
                        }
                    )
                if contagens_avaliador['reavaliacao']:
                    pendencias.append(
                        {
                            'titulo': 'Avaliações de Progressão Docente',
                            'subtitulo': 'aguardando reavaliação',
                            'qtd': contagens_avaliador['reavaliacao'],
                            'url': '/admin/progressao_docente/avaliacao/?tab=tab_em_reavaliacao',
                        }
                    )
            # apenas coordenados de rh sistêmico e campus pode acessar essa informação
            grupo_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
            grupo_coordenador_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)

            if grupo_rh_sistemico or grupo_coordenador_rh_campus:
                #
                # VERIFICAR OS DOCENTES SEM DATABASE
                qtd_docentes_sem_database = Servidor.get_docente_sem_database(request.user, ProgressaoDocente.ULTIMOS_NIVEIS).count()
                if qtd_docentes_sem_database:
                    pendencias.append(
                        {
                            'titulo': 'Docentes sem data base',
                            'subtitulo': 'aguardando correção',
                            'qtd': qtd_docentes_sem_database,
                            'url': '/progressao_docente/docentes_sem_data_base/',
                        }
                    )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    #
    eh_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    eh_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
    #
    if eh_rh_sistemico or eh_rh_campus:
        _qs = DocenteAProgredir.get_inconsistencias()
        # se é campus
        if eh_rh_campus:
            servidor = request.user.get_relacionamento()
            if servidor and servidor.setor:
                _qs = _qs.filter(avaliado__setor__uo=servidor.setor.uo)
        qtd = _qs.count()
        if qtd:
            _pluralize = pluralize(qtd)
            pendencias.append(
                {
                    'titulo': f'Inconsistência em Progressão Docente{_pluralize}',
                    'subtitulo': 'a ajustar',
                    'qtd': qtd,
                    'url': '/progressao_docente/inconsistencias_relatorio/',
                }
            )
    #
    return pendencias


@rtr()
@permission_required('progressao_docente.change_progressaodocente')
def inconsistencias_relatorio(request):
    title = 'Inconsistências no relatório de docentes a progredir'
    eh_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    eh_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
    #
    if not eh_rh_sistemico and not eh_rh_campus:
        raise PermissionDenied('Você não tem permissão para acessar essa área.')
    #
    form = InconsistenciasRelatorioFiltroForm(request.GET or None, eh_campus=eh_rh_campus)
    #
    docentes = DocenteAProgredir.get_inconsistencias()
    #
    if eh_rh_campus and not eh_rh_sistemico:
        servidor = request.user.get_relacionamento()
        if servidor and servidor.setor:
            docentes = docentes.filter(avaliado__setor__uo=servidor.setor.uo)
    #
    if form.is_valid():
        nome = form.cleaned_data.get('nome')
        campus = form.cleaned_data.get('campus')
        if nome:
            docentes = docentes.filter(Q(avaliado__pessoa_fisica__nome__icontains=nome) | Q(avaliado__matricula__icontains=nome))
        if campus:
            docentes = docentes.filter(avaliado__setor__uo=campus)

    #
    if eh_rh_campus or eh_rh_sistemico:
        #
        custom_fields = {
            'matricula': Column('Matrícula', accessor='avaliado__matricula', order_by='avaliado__matricula'),
            'servidor': Column('Servidor', accessor='avaliado__pessoa_fisica__nome', order_by='avaliado__pessoa_fisica__nome'),
            'campus': Column('Campus', accessor='avaliado__setor__uo__sigla', order_by='avaliado__setor__uo__sigla'),
            'alert': TemplateColumn(
                template_code='<span class="status status-alert">Nível <strong>{{ record.nivel_atual }}</strong> encontrado <strong>{{ record.count }}</strong> vezes.</span>',
                verbose_name='Inconsistência',
            ),
            'link_admin': TemplateColumn(
                template_code='<a class="btn btn-success" href="/admin/progressao_docente/docenteaprogredir/?q={{ record.avaliado__matricula }}">Ajustar</a>',
                verbose_name='Ações',
            ),
        }
        sequence = [
            'matricula',
            'servidor',
            'campus',
        ]
        table = get_table(
            request=request,
            queryset=docentes,
            custom_fields=custom_fields,
            sequence=sequence,
        )
    return locals()


# PROCESSO
@rtr('ver_processo.html')
@login_required()
def ver_processo(request, pk):
    processo = get_object_or_404(ProgressaoDocente, pk=pk)
    #
    title = f'Progressão Docente - {processo.avaliado}'
    dias_descobertos = processo._lista_dias_nao_cobertos()
    avaliado_progressao = processo.avaliado.get_vinculo()
    #
    processo.afastamentos_interrompem_tempo_servico = processo.avaliado.dados_afastamentos_interrompem_tempo_servico(
        processo.data_inicio_periodo, processo.data_fim_periodo
    )
    processo.afastamentos_efetivo_exercicio_30_dias = processo.avaliado.dados_afastamentos_efetivo_exercicio_30_dias(
        processo.data_inicio_periodo, processo.data_fim_periodo
    )
    afastamento_regra_24_meses = _afastamentos_24_meses(processo)
    #
    avaliacoes = []
    for a in processo.avaliacao_set.all():
        avaliador = a.avaliadores.first().get_vinculo()
        a.informacoes_avaliacao = a.info_avaliacao(avaliacao=a, avaliado=avaliado_progressao, avaliador=avaliador)
        a.pode_editar_avaliacao = a.pode_editar_avaliacao(request)
        a.pode_remover_avaliacao = a.pode_remover_avaliacao(request)
        a.pode_recalcular_pontuacao = a.pode_recalcular_pontuacao(request)
        avaliacoes.append(a)
    #
    # verificando permissões
    pode_iniciar_avaliacao = processo.pode_iniciar_avaliacao()
    pode_adicionar_avaliacao = processo.pode_adicionar_avaliacao(request)
    pode_finalizar_processo = processo.pode_finalizar_processo(request)
    pode_gerar_processo_eletronico = processo.pode_gerar_processo_eletronico(request)
    pode_notificar_responsaveis = processo.pode_notificar_responsaveis(request)
    #
    return locals()


@rtr()
@login_required()
def recalcular_pontuacao(request, pk):
    usuario = request.user
    if not (usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus')):
        raise PermissionDenied('Você não tem permissário para acessar essa funcionalidade.')

    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    avaliado_processo = avaliacao.progressao.avaliado.get_vinculo()

    for c in avaliacao.formulario.criterio_set.all():
        c.itens = c.get_itens(avaliacao=avaliacao, responsavel=avaliado_processo)
        c.pontuacao_total = c.get_pontuacao_total(avaliacao, avaliado_processo, itens=c.itens)

    return httprr(request.META.get('HTTP_REFERER', '.'), 'Avaliação recalculada.')


def _afastamentos_24_meses(processo):
    afastamento_regra_24_meses = {}
    dados_24_meses = processo.avaliado.dados_afastamentos_efetivo_exercicio_24_meses(contar_a_partir_de=processo.data_inicio_periodo)
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


@rtr()
@login_required()
def finalizar_progressao(request, pk):
    progressao = get_object_or_404(ProgressaoDocente, pk=pk)
    if progressao.pode_finalizar_processo(request):
        retorno, msg = progressao.finalizar()
        if not retorno:
            return httprr(request.META.get('HTTP_REFERER', '..'), msg, tag='warning')
        return httprr(request.META.get('HTTP_REFERER', '..'), msg)
    else:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível finalizar a progressão. Verifique se todas as avaliações foram concluídas e se você tem permissão para esta ação.',
            tag='error',
        )


@rtr()
@login_required()
def iniciar_avaliacao(request, pk):
    processo = get_object_or_404(ProgressaoDocente, pk=pk)
    processo.iniciar_avaliacao()
    return httprr(f'/progressao_docente/ver/{processo.pk}/', 'Avaliação iniciada com sucesso.', close_popup=True)


@rtr()
@login_required()
def voltar_situacao_anterior(request, pk):
    processo = get_object_or_404(ProgressaoDocente, pk=pk)
    processo.voltar_situacao_anterior(request)
    return httprr(f'/progressao_docente/ver/{processo.pk}/', 'Situação atualizada.', close_popup=True)


##
# FORMULÁRIO


@rtr('ver_formulario.html')
@login_required()
def ver_formulario(request, pk):
    formulario = get_object_or_404(Formulario, pk=pk)
    title = formulario
    return locals()


##
# CRITÉRIO


@rtr('ver_criterio.html')
@login_required()
def ver_criterio(request, pk):
    criterio = get_object_or_404(Criterio, pk=pk)
    return locals()


##
# AVALIAÇÃO


@rtr('ver_avaliacao.html')
@login_required()
def ver_avaliacao(request, pk):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)

    if avaliacao.progressao:
        avaliado_progressao = avaliacao.progressao.avaliado.get_vinculo()
        avaliador = avaliacao.avaliadores.first().get_vinculo()
        processo = avaliacao.progressao
        # novos padrões
        dados_novo_padrao = processo._get_dados_novo_padrao()
        if dados_novo_padrao:
            padrao_anterior_reenq, padrao_novo_reenq = dados_novo_padrao
        #
        avaliacao.total_avaliacao = avaliacao.total_pontuacao_avaliacao(avaliador, avaliado_progressao)
        avaliacao.informacoes_avaliacao = avaliacao.info_avaliacao(avaliacao=avaliacao, avaliado=avaliado_progressao, avaliador=avaliador)
        #
        title = f'Avaliação - {processo.avaliado}'
        #
        pode_revalidar_assinatura = avaliacao.pode_revalidar_assinatura(request)
        #
        return locals()
    return httprr('..', 'Não existe uma progressão associada com a avaliação', tag='error')


@rtr()
@login_required()
def preencher(request, pk):
    #
    title = 'Avaliação'
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    processo = avaliacao.progressao
    # verificando acesso
    avaliado_processo = avaliacao.progressao.avaliado.get_vinculo()
    if (
        request.user.get_vinculo() != avaliado_processo
    ):  # apenas o avaliado do processo pode preencher o avaliação na situação "AGUARDANDO_PREENCHIMENTO"
        raise PermissionDenied('Você não tem permissão de acessar essa funcionalidade.')
    #
    avaliador = avaliacao.avaliadores.first().get_vinculo()
    pode_preencher = avaliacao.situacao in [Avaliacao.AGUARDANDO_PREENCHIMENTO, Avaliacao.EDITACAO_PARA_REAVALIACAO] and (
        avaliacao.preenchida is False or avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO
    )
    estah_em_edicao_reavaliacao = avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO

    criterios = []
    #
    if pode_preencher:
        #
        for c in avaliacao.formulario.criterio_set.all():
            c.usuario_pode_adicionar_pontuacao = c.pode_adicionar_pontuacao(avaliacao, avaliado_processo)
            c.itens = c.get_itens(avaliacao=avaliacao, responsavel=avaliado_processo)
            c.pontuacao_total = c.get_pontuacao_total(avaliacao, avaliado_processo, itens=c.itens)
            # c.media_para_avaliacao_criterio = c.media_avaliacao_criterio(avaliacao=avaliacao, avaliador=avaliador, avaliado_processo=avaliado_processo)
            # c.pontuacao_para_consideracao_positiva = c.get_pontuacao_consideracao_positiva(avaliacao=avaliacao, avaliador=avaliador, avaliado_processo=avaliado_processo)
            criterios.append(c)

    if processo.pode_acelerar:
        form_aceleracao = AceleracaoProgressaoForm(data=request.POST or None, files=request.FILES or None, instance=avaliacao.progressao)
        if form_aceleracao.is_valid():
            with transaction.atomic():
                avaliacao.progressao.validacao_aceleracao = None
                avaliacao.progressao.save()
                form_aceleracao.save()
            return httprr('.', 'Aceleração cadastrada com sucesso.')

    return locals()


@rtr()
@login_required()
def concluir_preenchimento(request, pk):
    #
    # concluíndo preenchimento da avaliação por parte do avaliado
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    if avaliacao.pode_concluir_preenchimento(request):
        avaliacao.concluir_preenchimento_avaliacao(request)
    else:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível concluir o preenchimento a avaliação. Verifique se todos os itens foram avaliados e tente novamente.',
            tag='error',
        )
    return httprr('/admin/progressao_docente/avaliacao/', 'Avaliação preenchida com sucesso')


@rtr()
@login_required()
def finalizar_avaliacao(request, pk):
    #
    # finalizando avaliação (avaliador)
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    if avaliacao.pode_finalizar_avaliacao(request):
        avaliacao.finalizar_avaliacao(request)
    else:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível finalizar a avaliação. Verifique se todos os itens foram avaliados e tente novamente.',
            tag='error',
        )
    return httprr('/admin/progressao_docente/avaliacao/', 'Avaliação finalizada com sucesso')


@rtr()
@login_required()
def assinar_avaliacao(request, pk):
    # TODO APENAS O AVALIADOR PODE ASSINAR E APENAS AS SUAS AVALIAÇÕES

    #
    # finalizando avaliação (avaliador)
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    if avaliacao.pode_assinar_avaliacao(request):
        title = f'Assinar Progressão Docente - {avaliacao.progressao.avaliado}'
        form = AssinaturaAvaliadorForm(
            request.POST or None,
            request=request,
            conteudo=avaliacao.conteudo_a_ser_assinado_da_avaliacao,
            chave=avaliacao.chave_a_ser_utilizada_na_assinatura_da_avaliacao,
        )
        if form.is_valid() and form.assinatura_is_valida():
            avaliacao.assinatura_avaliador = form.assinatura
            avaliacao.string_assinatura_avaliador = avaliacao.conteudo_a_ser_assinado_da_avaliacao
            avaliacao.data_assinatura_avaliador = datetime.now()
            # após a assinatura da avaliação, esta deve ser colocada para a ciência de resultado
            avaliacao.encaminhar_avaliacao_para_ciencia(request)
            # processo - calcular pontuação
            avaliacao.progressao.calcular_pontuacao_final_processo()
            return httprr(
                '/admin/progressao_docente/avaliacao/',
                'A avaliação foi concluída com sucesso e foi encaminhada para ciência de resultado.',
                close_popup=True,
            )
        return locals()
    else:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível finalizar a avaliação. Verifique se todos os itens foram avaliados e tente novamente.',
            tag='error',
            close_popup=True,
            anchor='feedback_message',
        )


@rtr()
@login_required()
def assinar_ciencia_resultado(request, pk):
    # TODO APENAS O AVALIADO POR ASSINAR E APENAS AS SUAS AVALIAÇÕES
    #
    # dando ciência do resultado (avaliado)
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    if avaliacao.pode_dar_ciencia_avaliacao(request):
        title = f'Assinar Progressão Docente - {avaliacao.progressao.avaliado}'
        form = AssinaturaAvaliadorForm(
            request.POST or None,
            request=request,
            conteudo=avaliacao.conteudo_a_ser_assinado_da_ciencia_de_resultado,
            chave=avaliacao.chave_a_ser_utilizada_na_assinatura_da_ciencia_de_resultado,
        )
        if form.is_valid() and form.assinatura_is_valida():
            avaliacao.assinatura_avaliado_processo = form.assinatura
            avaliacao.string_assinatura_avaliado_processo = avaliacao.conteudo_a_ser_assinado_da_ciencia_de_resultado
            avaliacao.data_assinatura_avaliado_processo = datetime.now()
            # após a assinatura da ciência, esta deve ser finalizada
            if avaliacao.pode_finalizar_ciencia_resultado(request):
                avaliacao.finalizar_ciencia_resultado(request)
                return httprr('/admin/progressao_docente/avaliacao/', 'Ciência de resultado registrada com sucesso.')
            else:
                return httprr(
                    request.META.get('HTTP_REFERER', '..'),
                    'Não foi possível registrar a ciência do resultado. Verifique as informações e tente novamente.',
                    tag='error',
                    close_popup=True,
                    anchor='feedback_message',
                )
        return locals()
    else:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível registrar a ciência do resultado. Verifique as informações e tente novamente.',
            tag='error',
            close_popup=True,
            anchor='feedback_message',
        )


@rtr()
@login_required()
def finalizar_avaliacao_discente(request, pk):
    #
    # finalizando avaliação (avaliador discente)
    avaliador = request.user.get_vinculo()
    relacionamento = request.user.get_relacionamento()
    eh_aluno = avaliador.eh_aluno()
    #
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    #
    if eh_aluno and _aluno_pode_avaliar(avaliacao=avaliacao, matricula=relacionamento.matricula):
        # salvando as notas que o discente inseriu na avaliação
        with transaction.atomic():
            if request.POST:
                qs_criterio = avaliacao.formulario.criterio_set.filter(avaliacao_discente=True)
                criterio = None
                if qs_criterio.exists():
                    criterio = qs_criterio.first()
                for item in criterio.item_set.all():
                    pontuacao = request.POST.get(f'nota_{item.pk}')
                    if pontuacao:
                        pontuacao = Decimal(pontuacao)
                        obj, _ = AvaliacaoItem.get_or_create(
                            item_id=item.pk, deferimento=AvaliacaoItem.TIPO_DEFERIDO, avaliacao_id=avaliacao.pk, responsavel=avaliador
                        )
                        if not obj.avaliacao.pode_ser_avaliada():
                            raise PermissionDenied('A avaliação não pode ser avaliada no momento. Tente novamente mais tarde.')
                        obj.pontuacao_form = Decimal(pontuacao)
                        obj.save()

        if avaliacao.pode_finalizar_avaliacao_discente(request):
            avaliacao.finalizar_avaliacao_discente(relacionamento)
        else:
            return httprr(
                request.META.get('HTTP_REFERER', '..'),
                'Não foi possível finalizar a avaliação. Verifique se todos os itens foram avaliados e tente novamente.',
                tag='error',
            )
        return httprr('/progressao_docente/ver_avaliacoes_discente/', 'Avaliação finalizada com sucesso')
    else:
        return httprr(request.META.get('HTTP_REFERER', '..'), 'Você não tem permissão para realizar essa ação.', tag='error')


@rtr('ciencia_resultado.html')
@login_required()
def ciencia_resultado(request, pk):
    #
    title = 'Avaliação'
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    #
    # checando a situação da avaliação
    # - se for EDITACAO_PARA_REAVALIACAO, devemos redirecionar a avaliação para a edição dos arquivos
    if avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO:
        return redirect(to=f'/progressao_docente/avaliacao/{avaliacao.pk}/preencher/')
    processo = avaliacao.progressao
    avaliador = avaliacao.avaliadores.first().get_vinculo()
    avaliado_progressao = request.user.get_vinculo()
    usuario_eh_avaliado_processo = processo.avaliado.get_vinculo() == avaliado_progressao
    pode_dar_ciencia = avaliacao.pode_dar_ciencia_avaliacao(request)
    #
    if pode_dar_ciencia:
        avaliacao.total_avaliacao = avaliacao.total_pontuacao_avaliacao(avaliador, avaliado_progressao)
        avaliacao.informacoes_avaliacao = avaliacao.info_avaliacao(avaliacao=avaliacao, avaliado=avaliado_progressao, avaliador=avaliador)
    #
    return locals()


@rtr()
@login_required()
def adicionar_pontuacao(request, pk, pk_criterio):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    responsavel = request.user.get_vinculo()
    criterio = get_object_or_404(Criterio, pk=pk_criterio)
    title = f'Adicionar Pontuação - {criterio}'
    if not criterio.pode_adicionar_pontuacao(avaliacao, responsavel):
        raise PermissionDenied

    form = AdicionarPontuacaoForm(request.POST or None, files=request.FILES or None, avaliacao=avaliacao, criterio=criterio, responsavel=responsavel)
    if form.is_valid():
        form.save()
        # form.processar(request)
        return httprr('..', 'Pontuação cadastrada com sucesso.', close_popup=True)

    return locals()


@rtr()
@login_required()
def apagar_avaliacaoitem(request, pk):
    avaliacaoitem = get_object_or_404(AvaliacaoItem, pk=pk)
    avaliacaoitem.apagar(request)
    return httprr(
        request.META.get('HTTP_REFERER'), anchor=f'criterio_{avaliacaoitem.item.criterio.pk}', message='Item da avaliação deletado com sucesso.'
    )


@rtr()
@login_required()
def editar_avaliacaoitem(request, pk):
    avaliacaoitem = get_object_or_404(AvaliacaoItem, pk=pk)
    title = f'Editar Pontuação - {avaliacaoitem.item.criterio}'
    responsavel = request.user.get_vinculo()
    form = AdicionarPontuacaoForm(
        request.POST or None,
        files=request.FILES or None,
        avaliacao=avaliacaoitem.avaliacao,
        criterio=avaliacaoitem.item.criterio,
        responsavel=responsavel,
        instance=avaliacaoitem,
    )
    if form.is_valid():
        form.save(commit=True)
        return httprr('.', 'Informações atualizadas com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('progressao_docente.pode_avaliar_processo')
def salvar_item_avaliacao(request, pk_item, pk_avaliacao, pontuacao):
    retorno = {'ok': True, 'msg': 'Pontuação salva com sucesso!'}
    with transaction.atomic():
        try:
            # TODO checagem de segurança para saber se o item pode ser salvo no estado do processo
            # verificando avaliacaoitem
            pontuacao = Decimal(pontuacao)
            avaliador = request.user.get_vinculo()
            eh_aluno = avaliador.eh_aluno()
            if eh_aluno:
                raise PermissionDenied(f"Acesso negado para '{avaliador}'. Esta tentativa de acesso vou registrada para fins de auditoria.")
            obj, _ = AvaliacaoItem.get_or_create(
                item_id=pk_item, deferimento=AvaliacaoItem.TIPO_DEFERIDO, avaliacao_id=pk_avaliacao, responsavel=avaliador
            )
            if not obj.avaliacao.pode_ser_avaliada():
                raise PermissionDenied('A avaliação não pode ser avaliada no momento. Tente novamente mais tarde.')
            obj.pontuacao_form = Decimal(pontuacao)
            obj.save()
            #
            # avaliacao = obj.avaliacao
            # avaliado_processo = avaliacao.progressao.avaliado.get_vinculo()
            # criterio = obj.item.criterio
            #
            # pontuacao_total = criterio.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel=avaliador)
            # qtd_itens = obj.item.criterio.qtd_itens()
            # media_criterio = criterio.media_avaliacao_criterio(avaliacao=avaliacao, avaliador=avaliador, avaliado_processo=avaliado_processo)
            # pontuacao_consideracao_positiva = criterio.get_pontuacao_consideracao_positiva(avaliacao=avaliacao, avaliador=avaliador, avaliado_processo=avaliado_processo)
            #
            retorno.update(
                {
                    # "total": pontuacao_total.get("p"),
                    'criterio': obj.item.criterio.pk,
                    # "media_criterio": media_criterio,
                    # "pontuacao_consideracao_positiva": pontuacao_consideracao_positiva,
                    'eh_aluno': eh_aluno,
                    # "total_discente": pontuacao_total.get("nota_discente")
                }
            )

        except Exception as e:
            retorno = {'ok': False, 'msg': e.args[0]}
    #
    return JsonResponse(retorno)


@rtr()
@login_required()
def ver_avaliacao_criterio(request, pk, pk_criterio):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    criterio = Criterio.objects.filter(item__avaliacaoitem__avaliacao__id=pk, pk=pk_criterio).distinct('id').first()
    relacionamento = request.user.get_relacionamento()
    avaliador = request.user.get_vinculo()
    avaliado_processo = avaliacao.progressao.avaliado.get_vinculo()
    eh_aluno = avaliador.eh_aluno()
    aluno_pode_avaliar = _aluno_pode_avaliar(avaliacao, relacionamento.matricula)
    #
    # verificar se o usuário é um avaliador da avaliação
    if not (relacionamento in avaliacao.avaliadores.all() or (eh_aluno and aluno_pode_avaliar)):
        raise PermissionDenied('Você não tem permissão de acesso a essa avaliação.')
    #
    if criterio is None:
        return httprr('..', 'Critério de avaliação não encontrado', tag='error')
    qs = None
    if criterio.autoavaliacao:
        qs = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item__criterio=criterio, responsavel=avaliado_processo)
        # verificando se é avaliação discente e se o avaliador é um aluno
        eh_aluno = avaliador.eh_aluno()
        if criterio.avaliacao_discente and eh_aluno:
            qs = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item__criterio=criterio, responsavel=avaliador)
    else:
        qs = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item__criterio=criterio, responsavel=avaliador)
        if criterio.necessita_arquivos:
            qs = AvaliacaoItem.objects.filter(
                avaliacao=avaliacao, item__criterio=criterio, responsavel=avaliado_processo, responsavel_avaliacao=avaliador
            )
    #
    return locals()


@rtr()
@login_required()
@permission_required('progressao_docente.pode_avaliar_processo')
def avaliar_processo(request, pk):
    #
    avaliador = request.user.get_vinculo()
    eh_aluno = avaliador.eh_aluno()
    relacionamento = request.user.get_relacionamento()
    #
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    #
    if eh_aluno:
        aluno_pode_avaliar = _aluno_pode_avaliar(avaliacao, relacionamento.matricula)
        aluno_pode_visualizar_avaliacao = _aluno_pode_visualizar_avaliacao(avaliacao, relacionamento.matricula)
        if not aluno_pode_visualizar_avaliacao:
            raise PermissionDenied(
                f'Acesso negado para a matrícula <strong>{relacionamento.matricula}</strong>. A tentativa de acesso a esta avaliação foi registrado para fins de auditoria.'
            )
        if not aluno_pode_avaliar:
            raise PermissionDenied('A avaliação está fora do período avaliativo.')
    #
    if not avaliacao.pode_ser_avaliada():
        raise PermissionDenied('A avaliação está fora do período avaliativo.')
    #
    processo = avaliacao.progressao
    title = f'Avaliação da Progressão Docente - {avaliacao.progressao.avaliado}'
    avaliador = request.user.get_vinculo()
    avaliado_processo = processo.avaliado.get_vinculo()
    tem_aceleracao_para_validar = (
        processo.tipo_aceleracao in [ProgressaoDocente.ESPECIALIZACAO, ProgressaoDocente.MESTRADO_DOUTORADO] and processo.validacao_aceleracao is None
    )
    #
    # verificar se o usuário é um avaliador da avaliação
    if not (relacionamento in avaliacao.avaliadores.all() or (eh_aluno and aluno_pode_avaliar)):
        raise PermissionDenied('Você não tem permissão de acesso a essa avaliação.')
    #
    # critérios que serão renderizados de acordo com o usuário
    criterios = []
    _qs_criterios = avaliacao.formulario.criterio_set.all()
    if eh_aluno:
        _qs_criterios = _qs_criterios.filter(avaliacao_discente=True)
    for c in _qs_criterios:
        if eh_aluno and not c.avaliacao_discente:
            continue  # garante que o aluno não vai ver critérios que não são para eles
        #
        c.itens = c.get_itens(avaliacao=avaliacao, responsavel=avaliado_processo)
        #
        if not eh_aluno and c.necessita_arquivos:
            c.qtde_itens_avaliados = c.get_qtde_itens_avaliados(avaliacao, avaliado_processo)
            c.pontuacao = c.get_pontuacao_total(avaliacao, avaliado_processo)
            c.pontuacao_total_avaliado = c.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel=avaliado_processo)
        #
        criterios.append(c)
    return locals()


@rtr()
@permission_required('progressao_docente.pode_avaliar_processo')
def aceleracao(request, acao):
    id_processo = request.POST.get('id_processo')
    processo = get_object_or_404(ProgressaoDocente, pk=id_processo)
    if not processo.eh_avaliador_processo(request.user):
        return JsonResponse(data={'msg': 'Você não é um avaliador do processo.'})
    # realizando a ação sobre a aceleração do processo
    if acao == 'validar':
        processo.validacao_aceleracao = ProgressaoDocente.ACELERACAO_VALIDADA
        processo.save()
    if acao == 'indeferir':
        processo.validacao_aceleracao = ProgressaoDocente.ACELERACAO_INVALIDADA
        processo.motivo_invalidacao = request.POST.get('justificativa')
        processo.save()
    msg = 'Avaliação da aceleração concluída com sucesso.'
    messages.success(request=request, message=msg)
    return JsonResponse(data={'ok': True, 'msg': msg})


@rtr()
@permission_required('progressao_docente.pode_avaliar_processo')
def avaliar_item_arquivo(request, pk_avaliacaoitem):
    avaliacao_item = get_object_or_404(AvaliacaoItem, pk=pk_avaliacaoitem)
    if not avaliacao_item.avaliacao.pode_ser_avaliada():
        raise PermissionDenied('A avaliação não pode ser avaliada no momento. Tente novamente mais tarde.')
    title = 'Avaliação do Item'
    #
    # verificando permissões
    # TODO ver condições de avaliação do item; verificar se é avaliador do processo

    return locals()


@rtr()
@permission_required('progressao_docente.pode_avaliar_processo')
def salvar_avaliar_item_arquivo(request, acao):
    #
    # TODO: verificar permissões de avaliação, se a avaliação é do usuário
    #
    dados = request.POST
    just = dados.get('justificativa')
    pontuacao_validada = dados.get('pontuacao_validada')
    # validar_avancar, pular, validar, indeferir
    avaliacao_item = get_object_or_404(AvaliacaoItem, pk=dados.get('id_avaliacao_item'))
    if not avaliacao_item.avaliacao.pode_ser_avaliada():
        raise PermissionDenied('A avaliação não pode ser avaliada no momento. Tente novamente mais tarde.')
    #
    try:
        avaliacao_item.validar_dados(request)
    except ValueError as err:
        return JsonResponse({'ok': False, 'fechar': False, 'msg': str(err)})
    #
    # VALIDAR
    if acao == 'validar':
        if pontuacao_validada and not just:
            return JsonResponse({'msg': 'É necessário preencher a justificativa.', 'error': 'justificativa_em_branco', 'justificar': True})
        avaliacao_item.deferir(request)
        # atualizar contador
        avaliacao_item.item.criterio.get_qtde_itens_avaliados(
            avaliacao=avaliacao_item.avaliacao, responsavel=avaliacao_item.avaliacao.progressao.avaliado.get_vinculo(), atualizar=True
        )
        #
        return JsonResponse(
            {
                'ok': True,
                'fechar': True,
            }
        )
    #
    # INDEFERIR
    if acao == 'indeferir':
        if not just:
            return JsonResponse({'msg': 'É necessário preencher a justificativa.', 'error': 'justificativa_em_branco', 'justificar': True})
        avaliacao_item.indeferir(request, just)
        # atualizar contador
        avaliacao_item.item.criterio.get_qtde_itens_avaliados(
            avaliacao=avaliacao_item.avaliacao, responsavel=avaliacao_item.avaliacao.progressao.avaliado.get_vinculo(), atualizar=True
        )
        #
        return JsonResponse(
            {
                'ok': True,
                'fechar': True,
            }
        )

    return locals()


@rtr()
@login_required()
def reavaliar_observacao(request, id_avaliacao):
    title = 'Adicionar Observações'
    avaliacao = get_object_or_404(Avaliacao, pk=id_avaliacao)
    form = ReavaliacaoObservacaoForm(request.POST or None)
    if form.is_valid():
        avaliacao.reavaliar_avaliacao(request)
        return httprr(url='/admin/progressao_docente/avaliacao/?tab=tab_em_reavaliacao', message='Reavaliação solicitada com sucesso.')
    return locals()


@rtr()
@login_required()
def preparar_edicao_reavaliacao(request, id_avaliacao):
    avaliacao = get_object_or_404(Avaliacao, pk=id_avaliacao)
    # a guarda anterior comparava `processo.avaliado.get_vinculo()` com uma variável que recebia
    # esse mesmo valor: era sempre verdadeira. Com a reabertura carimbando a data de liberação,
    # um terceiro conseguia disparar o relógio de processo alheio e, no decurso, a conclusão.
    if not avaliacao.usuario_eh_dono(request.user):
        raise PermissionDenied('Apenas o avaliado pode editar a própria avaliação para reavaliação.')
    #
    # reentrada na etapa não recarimba a data: renovar o prazo a cada acesso permitiria ao
    # avaliado adiar a edição indefinidamente.
    if avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO:
        avaliacao.reabrir_para_edicao_reavaliacao()
    elif avaliacao.situacao != Avaliacao.EDITACAO_PARA_REAVALIACAO:
        raise PermissionDenied('A avaliação não está em uma etapa que permita edição para reavaliação.')
    return redirect(to=f'/progressao_docente/avaliacao/{avaliacao.pk}/preencher/')


@rtr('reavaliacao.html')
@login_required()
def reavaliar(request, pk):
    title = 'Avaliação'
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    avaliador = avaliacao.avaliadores.first().get_vinculo()
    avaliado_processo = avaliacao.progressao.avaliado.get_vinculo()
    eh_aluno = avaliador.eh_aluno()
    processo = avaliacao.progressao
    pode_reavaliar = avaliacao.pode_reavaliar_avaliacao(request)
    #
    # critérios que serão renderizados de acordo com o usuário
    criterios = []
    for c in avaliacao.formulario.criterio_set.all():
        if eh_aluno and not c.avaliacao_discente:
            continue
        #
        c.itens = c.get_itens(avaliacao=avaliacao, responsavel=avaliado_processo)
        if c.autoavaliacao or c.avaliacao_discente:  # for autoavaliacao ou avaliação discete, carrega apenas os itens
            criterios.append(c)
            continue
        #
        if c.necessita_arquivos:
            c.qtde_itens_avaliados = c.get_qtde_itens_avaliados(avaliacao, avaliado_processo)
            c.pontuacao = c.get_pontuacao_total(avaliacao, avaliado_processo)
            c.pontuacao_total_avaliado = c.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel=avaliado_processo)
        else:
            c.pontuacao = c.get_pontuacao_total(avaliacao, avaliador)
            c.pontuacao_total_avaliado = c.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel_avaliacao=avaliador)
            c.media_para_avaliacao_criterio = c.media_avaliacao_criterio(
                avaliacao=avaliacao, avaliador=avaliador, avaliado_processo=avaliado_processo
            )
            c.pontuacao_para_consideracao_positiva = c.get_pontuacao_consideracao_positiva(
                avaliacao=avaliacao, avaliador=avaliador, avaliado_processo=avaliado_processo
            )
        #
        criterios.append(c)

    return locals()


@rtr()
@login_required()
def revalidar_assinatura(request, pk):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    if not avaliacao.pode_revalidar_assinatura(request):
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível revalidar a assinatura. Verifique as informações e tente novamente.',
            tag='error',
        )
    else:
        avaliacao.revalidar_assinatura(request)
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Revalidação da assinatura realizada com sucesso.',
        )


@rtr()
@login_required()
def finalizar_reavaliacao(request, pk):
    title = 'Adicionar Observações da Reavaliação'
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    try:
        form = ConcluirReavaliacaoForm(request.POST or None)
        if form.is_valid():
            avaliacao.finalizar_reavaliacao(request)
            avaliacao.progressao.calcular_pontuacao_final_processo()
            return httprr('/admin/progressao_docente/avaliacao/', message='Reavaliação finalizada com sucesso.')
    except Exception as ex:
        return httprr(request.META.get('HTTP_REFERER'), message=f'Erro ao finalizar a reavaliação. Erro: {ex}')
    return locals()


@rtr()
@login_required()
def ver_avaliacoes_discente(request):
    #
    # apenas alunos acessam essa área
    title = 'Avaliações Discente'
    aluno = request.user.get_vinculo()
    relacionamento = request.user.get_relacionamento()
    eh_aluno = aluno.eh_aluno()
    if not eh_aluno:
        raise PermissionDenied('Você não tem permissão para acessar essa funcionalidade.')
    #
    # selecionando avaliações para o aluno logado
    # - mostrar apenas uma avaliação por processo de progressão
    base_queryset = (
        DiscenteAptosAvaliacao.objects.select_related(
            'avaliacao',
            'avaliacao__formulario',
            'progressao',
        )
        .filter(matricula=relacionamento.matricula, avaliacao__formulario__criterio__avaliacao_discente=True, nao_reconhece_docente=False)
        .distinct('progressao__pk')
    )

    aguardando_avaliacao = base_queryset.filter(
        avaliacao_realizada=False,
        avaliacao__situacao__in=[
            Avaliacao.AGUARDANDO_PREENCHIMENTO,
            Avaliacao.EM_AVALIACAO,
        ],
    )

    avaliacoes_realizadas = base_queryset.filter(avaliacao_realizada=True)

    nao_avaliadas = base_queryset.filter(
        avaliacao_realizada=False,
    ).exclude(
        avaliacao__situacao__in=[
            Avaliacao.AGUARDANDO_PREENCHIMENTO,
            Avaliacao.EM_AVALIACAO,
        ]
    )
    #
    return locals()


@rtr()
@login_required()
def detalhar_avaliacao_discente(request, pk_avaliacao):
    #
    # apenas alunos acessam essa área
    title = 'Detalhe da Avaliação Discente'
    aluno = request.user.get_vinculo()
    relacionamento = request.user.get_relacionamento()
    avaliacao = get_object_or_404(Avaliacao, pk=pk_avaliacao)
    eh_aluno = aluno.eh_aluno()
    if eh_aluno and not _aluno_pode_visualizar_avaliacao(avaliacao, relacionamento.matricula):
        raise PermissionDenied(
            f'Acesso negado para a matrícula <strong>{relacionamento.matricula}</strong> na avaliação {avaliacao}. Essa tentativa de acesso foi registrada para fins de auditoria.'
        )
    #
    if not eh_aluno:
        raise PermissionDenied('Você não tem permissão para acessar essa funcionalidade.')
    #
    # selecionando avaliações para o aluno logado
    itens = AvaliacaoItem.objects.filter(avaliacao__id=pk_avaliacao, responsavel=aluno)
    #
    return locals()


def _aluno_pode_avaliar(avaliacao, matricula):
    aluno_pode_avaliar = False
    # consulta as matrículas de alunos aptos para essa avaliação
    qs = (
        DiscenteAptosAvaliacao.objects.select_related('progressao')
        .select_related('avaliacao')
        .filter(
            matricula=matricula,
            progressao__avaliacao__formulario__criterio__avaliacao_discente=True,
            avaliacao_realizada=False,
            avaliacao=avaliacao,
            nao_reconhece_docente=False,
        )
    )
    if qs.exists():
        aluno_pode_avaliar = True
    return aluno_pode_avaliar


def _aluno_pode_visualizar_avaliacao(avaliacao, matricula):
    pode_visualizar = False
    # consulta as matrículas de alunos aptos para essa avaliação
    qs = DiscenteAptosAvaliacao.objects.filter(
        matricula=matricula, progressao__avaliacao__formulario__criterio__avaliacao_discente=True, avaliacao=avaliacao, nao_reconhece_docente=False
    )
    if qs.exists():
        pode_visualizar = True
    return pode_visualizar


@rtr()
@login_required()
def nao_reconhece_docente(request, pk):
    discente_aptos = get_object_or_404(DiscenteAptosAvaliacao, pk=pk)
    #
    aluno = request.user.get_vinculo()
    eh_aluno = aluno.eh_aluno()
    if not eh_aluno or not _aluno_pode_visualizar_avaliacao(discente_aptos.avaliacao, aluno.relacionamento.matricula):
        if not eh_aluno:
            # Mensagem para o caso de o usuário não ser um aluno
            mensagem_erro = f'Acesso negado. O usuário <strong>{request.user.username}</strong> não possui vínculo de discente.'
        else:
            # Mensagem para o aluno sem permissão
            mensagem_erro = (
                f'Acesso negado para a matrícula <strong>{aluno.relacionamento.matricula}</strong> na avaliação {discente_aptos.avaliacao}.'
            )

        # Adiciona a nota de auditoria e lança a exceção
        raise PermissionDenied(
            f'{mensagem_erro} Você não tem permissão para acessar essa funcionalidade. Esta tentativa de acesso foi registrada para fins de auditoria.'
        )
    #
    # se chegou aqui, o aluno pode marcar a opção de não reconhecer o docente
    DiscenteAptosAvaliacao.objects.filter(
        matricula=aluno.relacionamento.matricula, nao_reconhece_docente=False, progressao=discente_aptos.progressao
    ).update(nao_reconhece_docente=True)

    return httprr('/progressao_docente/ver_avaliacoes_discente/', 'Opção "Não Reconhece Docente" marcada com sucesso.')


@rtr()
@login_required()
@permission_required('progressao_docente.view_docenteaprogredir')
def docentes_sem_data_base(request):
    title = 'Docentes sem Data Base Cadastrada'
    eh_campus = True
    if request.user.has_perm('comum.is_coordenador_de_gestao_de_pessoas_sistemico') or request.user.is_superuser:
        eh_campus = False
    form = DataBaseProgressaoDocenteFiltroForm(request.GET or None, eh_campus=eh_campus)
    # selecionando os docentes que não tenham uma data base cadastrada para realizar a progressão docente
    docentes = Servidor.get_docente_sem_database(request.user, ProgressaoDocente.ULTIMOS_NIVEIS)
    #
    if form.is_valid():
        nome = form.cleaned_data.get('nome')
        campus = form.cleaned_data.get('campus')
        if nome:
            docentes = docentes.filter(Q(pessoa_fisica__nome__icontains=nome) | Q(matricula__icontains=nome))
        if campus:
            docentes = docentes.filter(setor__uo=campus)

    class MinhaTabela(TableReportPlus):
        def render_nivel_docente(self, record):
            return record.nivel_docente

    custom_fields = {
        'matricula': Column('Matrícula', accessor='matricula', order_by='matricula'),
        'servidor': Column('Servidor', accessor='pessoa_fisica__nome', order_by='pessoa_fisica__nome'),
        'campus': Column('Campus', accessor='setor.uo', order_by='setor__uo'),
        'setor': Column('Setor', accessor='setor', order_by='setor'),
        'nivel_docente': Column(
            'Nível',
            orderable=False,
            accessor='*',
            attrs={'td': {'class': 'classe-nivel'}},
            empty_values=(),  # necessário para usar o método value
        ),
        'situacao': Column('Situação', accessor='situacao', order_by='situacao'),
        'link_column': LinkColumn(
            'progressao_docente:editar_data_base_progressao',
            kwargs={'matricula': Accessor('matricula')},
            verbose_name='#',
            text='Adicionar Data Base',
            attrs={'a': {'class': 'btn popup'}},
        ),
    }
    sequence = ['matricula', 'servidor', 'nivel_docente', 'campus', 'setor', 'situacao', 'link_column']
    table = get_table(
        request=request,
        queryset=docentes,
        custom_fields=custom_fields,
        sequence=sequence,
        table_class=MinhaTabela,
    )

    return locals()


@rtr()
@login_required()
def editar_data_base_progressao(request, matricula):
    title = 'Adicionar Database'
    list_perms = ['comum.is_coordenador_de_gestao_de_pessoas_sistemico', 'comum.is_coordenador_de_gestao_de_pessoas']
    if not any(request.user.has_perm(perm_name) for perm_name in list_perms):
        raise PermissionDenied('Você não tem permissão para acessar essa funcionalidade.')
    servidor = get_object_or_404(Servidor, matricula=matricula)
    form = EditarDataBaseProgressaoDocente(request.POST or None, instance=servidor)
    if form.is_valid():
        form.save()
        ProgressaoDocente.calcular_docentes_a_progredir(
            matriculas=[
                matricula,
            ]
        )
        return httprr('..', 'Database alterada com sucesso.')
    return locals()


@rtr()
@permission_required('progressao_docente.change_progressaodocente')
def docenteaprogredir(request, id):
    title = 'Informações de Docente a Progredir'
    docente_a_progredir = get_object_or_404(DocenteAProgredir, pk=id)
    afastamentos_interrompem_tempo_servico = docente_a_progredir.avaliado.dados_afastamentos_interrompem_tempo_servico(
        docente_a_progredir.data_inicio_contagem, docente_a_progredir.data_fim_contagem
    )
    afastamentos_efetivo_exercicio_30_dias = docente_a_progredir.avaliado.dados_afastamentos_efetivo_exercicio_30_dias(
        docente_a_progredir.data_inicio_contagem, docente_a_progredir.data_fim_contagem
    )
    processo = docente_a_progredir._get_progressao_simulada(
        nivel_atual=docente_a_progredir.nivel_atual, proximo_nivel=docente_a_progredir.proximo_nivel
    )
    dias_interrompem = afastamentos_interrompem_tempo_servico['total_dias'] if afastamentos_interrompem_tempo_servico else 0
    interrompem = _agrupar_por_tipo(
        (f'{a["codigo"]} - {a["nome"]}', {'inicio': a['data_inicio'], 'fim': a['data_termino'], 'dias': a['dias_afastamento']})
        for a in (afastamentos_interrompem_tempo_servico or {}).get('afastamentos', [])
    )
    observacoes_30_dias = afastamentos_efetivo_exercicio_30_dias['observacoes'] if afastamentos_efetivo_exercicio_30_dias else []
    periodos_30_dias = _periodos_regra_30_dias(observacoes_30_dias)
    afastamentos_30_dias = _afastamentos_regra_30_dias(observacoes_30_dias)
    regra_24_meses = _periodos_regra_24_meses(processo)
    dias_24_meses = sum(linha['dias'] for linha in regra_24_meses)
    return locals()


def _agrupar_dias_consecutivos(dias: Iterable[date]) -> list[dict]:
    """Junta dias seguidos em intervalos, para a tela não listar dia a dia.

    Args:
        dias: Datas avulsas, em qualquer ordem.

    Returns:
        Intervalos com `inicio`, `fim` e `dias`, em ordem cronológica.
    """
    intervalos: list[dict] = []
    for dia in sorted(set(dias)):
        if intervalos and dia - intervalos[-1]['fim'] == timedelta(days=1):
            intervalos[-1]['fim'] = dia
            intervalos[-1]['dias'] += 1
        else:
            intervalos.append({'inicio': dia, 'fim': dia, 'dias': 1})
    for intervalo in intervalos:
        intervalo['texto'] = _texto_periodo(intervalo['inicio'], intervalo['fim'])
    return intervalos


def _texto_periodo(inicio: date, fim: date) -> str:
    """Período no formato da tela: um dia só aparece sem repetir a data."""
    if inicio == fim:
        return inicio.strftime('%d/%m/%Y')
    return f'{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}'


def _periodos_regra_30_dias(observacoes: list[dict]) -> list[dict]:
    """Agrupa os dias que extrapolaram 30 dias no ano em intervalos contínuos.

    Cada intervalo leva também a faixa do total acumulado nos 12 meses anteriores,
    que antes aparecia repetida em uma linha por dia.

    Args:
        observacoes: `observacoes` de `Servidor.dados_afastamentos_efetivo_exercicio_30_dias`.

    Returns:
        Intervalos com `inicio`, `fim`, `dias`, `acumulado_min` e `acumulado_max`.
    """
    acumulado = {obs['data_afetada']: obs['qtd_dias'] for obs in observacoes}
    periodos = _agrupar_dias_consecutivos(acumulado)
    for periodo in periodos:
        valores = [qtd for dia, qtd in acumulado.items() if periodo['inicio'] <= dia <= periodo['fim']]
        periodo['acumulado_min'], periodo['acumulado_max'] = min(valores), max(valores)
    return periodos


def _afastamentos_regra_30_dias(observacoes: list[dict]) -> list[dict]:
    """Afastamentos que pesaram em algum dia da regra dos 30 dias, agrupados por tipo.

    Args:
        observacoes: `observacoes` de `Servidor.dados_afastamentos_efetivo_exercicio_30_dias`.

    Returns:
        Uma linha por tipo de afastamento, com `afastamento`, `periodos` (um por registro) e `dias`.
    """
    registros = {afastamento.pk: afastamento for obs in observacoes for afastamento in obs['lista_afastamentos']}
    return _agrupar_por_tipo(
        (r.afastamento, {'inicio': r.data_inicio, 'fim': r.data_termino, 'dias': r.dias_incluindo_ultimo_dia()})
        for r in sorted(registros.values(), key=lambda afastamento: afastamento.data_inicio)
    )


def _agrupar_por_tipo(periodos: Iterable[tuple]) -> list[dict]:
    """Junta os registros de afastamento do mesmo tipo em uma linha, sem fundir os registros.

    Args:
        periodos: Pares (tipo de afastamento, período com `inicio`, `fim` e `dias`).

    Returns:
        Uma linha por tipo, com `afastamento`, `periodos` e `dias`.
    """
    por_tipo: dict = {}
    for tipo, periodo in periodos:
        periodo['texto'] = _texto_periodo(periodo['inicio'], periodo['fim'])
        por_tipo.setdefault(tipo, []).append(periodo)
    return [{'afastamento': tipo, 'periodos': lista, 'dias': sum(p['dias'] for p in lista)} for tipo, lista in por_tipo.items()]


def _periodos_regra_24_meses(processo: ProgressaoDocente) -> list[dict]:
    """Dias de licença para tratamento de saúde além dos 24 meses, agrupados por tipo e em intervalos.

    Args:
        processo: Progressão (simulada ou real) de onde saem o avaliado e o início do interstício.

    Returns:
        Uma linha por tipo de afastamento, com `afastamento`, `periodos` e `dias`. Os `dias` contam
            cada ocorrência, como o `total_dias` do cálculo: registros sobrepostos somam o mesmo dia
            duas vezes, ainda que o período apareça uma vez só.
    """
    dados = processo.avaliado.dados_afastamentos_efetivo_exercicio_24_meses(contar_a_partir_de=processo.data_inicio_periodo) or {}
    dias_por_tipo: dict = {}
    for servidor_afastamento, dias in dados.items():
        if hasattr(servidor_afastamento, 'pk') and dias:
            dias_por_tipo.setdefault(servidor_afastamento.afastamento, []).extend(dia['data'] for dia in dias)
    return [{'afastamento': tipo, 'periodos': _agrupar_dias_consecutivos(dias), 'dias': len(dias)} for tipo, dias in dias_por_tipo.items()]


def _campos_obrigatorios_faltando_docente(docente):
    """Retorna nomes amigáveis (verbose_name) dos campos obrigatórios em falta."""
    obrigatorios = [
        'avaliado',
        'data_inicio_contagem',
        'eh_primeira_promocao',
        'nivel_atual',
        'proximo_nivel',
    ]
    faltando = []
    for field_name in obrigatorios:
        valor = getattr(docente, field_name, None)
        if is_blank(valor):
            verbose = capfirst(docente._meta.get_field(field_name).verbose_name)
            faltando.append(verbose)
    return faltando


@rtr()
@permission_required('progressao_docente.change_docenteaprogredir')
def criar_progressao(request: HttpRequest, id: int) -> HttpResponse:
    docente_a_progredir = get_object_or_404(DocenteAProgredir, pk=id)

    # Validação prévia dos campos obrigatórios
    faltando = _campos_obrigatorios_faltando_docente(docente_a_progredir)
    if faltando:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível criar a progressão. Preencha os seguintes campos em "Docente a Progredir": ' + ', '.join(faltando) + '.',
            'error',
        )

    # Criação/obtenção da Progressão pela chave única do model (avaliado, período, nível), não pela
    # situação: senão, uma progressão que já avançou ganhava uma cópia (#17738)
    campos = {
        'situacao': ProgressaoDocente.A_INICIAR,
        'relatorio_a_progredir': docente_a_progredir,
        'eh_primeira_promocao': docente_a_progredir.eh_primeira_promocao,
        'proximo_nivel': docente_a_progredir.proximo_nivel,
    }
    with transaction.atomic():
        p, criada = ProgressaoDocente.objects.get_or_create(
            avaliado=docente_a_progredir.avaliado,
            data_inicio_periodo=docente_a_progredir.data_inicio_contagem,
            nivel_atual=docente_a_progredir.nivel_atual,
            defaults=campos,
        )
        if not criada and p.situacao != ProgressaoDocente.A_INICIAR:
            docente_a_progredir.progressao_criada = True
            docente_a_progredir.progressao_finalizada = p.situacao == ProgressaoDocente.FINALIZADO
            docente_a_progredir.save()
            return httprr(f'/progressao_docente/ver/{p.pk}/', 'Já existe progressão docente para este período e nível.', 'warning')
        # Ainda não iniciada: alinha ao relatório, como faria a criação
        for campo, valor in campos.items():
            setattr(p, campo, valor)

        # Determina o tipo
        try:
            p.tipo = p.get_tipo_progressao()
        except ValidationError as e:
            # Não salva nem sinaliza como criado quando não é possível determinar o tipo
            return httprr('..', f'Não foi possível criar a progressão: {e}', 'error')

        p.save()

        docente_a_progredir.progressao_criada = True
        docente_a_progredir.save()

    return httprr(f'/progressao_docente/ver/{p.pk}/', 'Progressão docente criada com sucesso.')


@permission_required('progressao_docente.change_docenteaprogredir')
def executar_importacao(request):
    if request.user.has_perm('comum.is_coordenador_de_gestao_de_pessoas_sistemico'):
        from django.core.management import call_command

        call_command('docentes_a_progredir', interactive=False, raise_exception=False, verbosity=0)
        return httprr(request.META.get('HTTP_REFERER'), message='Importação executada com sucesso.')
    else:
        return httprr(request.META.get('HTTP_REFERER'), message='Usuário não autorizado para esta operação.', tag='error')


@rtr()
@permission_required('progressao_docente.change_docenteaprogredir')
def recalcular_pontuacao_avaliacao(request, id_avaliacao):
    if request.user.has_perm('comum.is_coordenador_de_gestao_de_pessoas_sistemico'):
        avaliacao = get_object_or_404(Avaliacao, pk=id_avaliacao)
        avaliacao.calcular_pontuacao_avaliacao()
        return httprr(request.META.get('HTTP_REFERER'), message='Pontuação recalculada com sucesso.')
    else:
        return httprr(request.META.get('HTTP_REFERER'), message='Usuário não autorizado para esta operação.', tag='error')


@documento(enumerar_paginas=False)
@rtr()
@permission_required('progressao_docente.change_docenteaprogredir')
def imprimir_processo(request, id_processo):
    progressao = get_object_or_404(ProgressaoDocente, pk=id_processo)
    #
    dados_novo_padrao = progressao._get_dados_novo_padrao()
    if dados_novo_padrao:
        padrao_anterior_reenq, padrao_novo_reenq = dados_novo_padrao
    avaliado_progressao = progressao.avaliado.get_vinculo()
    #
    progressao.afastamentos_interrompem_tempo_servico = progressao.avaliado.dados_afastamentos_interrompem_tempo_servico(
        progressao.data_inicio_periodo, progressao.data_fim_periodo
    )
    progressao.afastamentos_efetivo_exercicio_30_dias = progressao.avaliado.dados_afastamentos_efetivo_exercicio_30_dias(
        progressao.data_inicio_periodo, progressao.data_fim_periodo
    )
    #
    avaliacoes = []
    for a in progressao.avaliacao_set.all():
        avaliador = a.avaliadores.first()
        a.avaliador = avaliador
        a.informacoes_avaliacao = a.info_avaliacao(
            avaliacao=a, avaliado=avaliado_progressao, avaliador=avaliador.get_vinculo()
        )  # a.info_avaliacao(servidor)
        avaliacoes.append(a)
    #
    return locals()


@permission_required('progressao_docente.change_docenteaprogredir')
def gerar_processo_eletronico(request, id_processo):
    processo = get_object_or_404(ProgressaoDocente, pk=id_processo)
    if not processo.situacao == ProgressaoDocente.FINALIZADO:
        raise PermissionDenied
    mensagem = ''
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        processo_pdf = imprimir_processo(request, id_processo).content
        file_tmp = None
        if settings.DEBUG:
            try:
                # home do usuário (windows ou linux)
                dir_home = expanduser('~')
                file_tmp = join(dir_home, f'progressao_docente_{id_processo}.pdf')
            except Exception:
                # padrão produção (linux)
                file_tmp = f'/tmp/progressao_docente_{id_processo}.pdf'
        if not file_tmp:
            file_tmp = f'/tmp/progressao_docente_{id_processo}.pdf'

        avaliacoes_pdf_arquivo_em_disco = open(file_tmp, 'wb+')
        avaliacoes_pdf_arquivo_em_disco.write(processo_pdf)
        try:
            processo.gerar_processo_eletronico(avaliacoes_pdf_arquivo_em_disco, request.user)
            mensagem = 'Processo eletrônico gerado com sucesso.'
        except ValidationError as error:
            return httprr(request.META.get('HTTP_REFERER'), message=error.message, tag='error')
        except Exception as error:
            capture_exception(error)
            mensagem = error.message
    else:
        return httprr(request.META.get('HTTP_REFERER'), message='O módulo de processo eletrônico não está configurado no SUAP.', tag='error')
    return httprr(request.META.get('HTTP_REFERER'), message=mensagem)


@rtr()
@permission_required('progressao_docente.change_progressaodocente')
def enviar_notificacao(request, pk):
    try:
        progressao = get_object_or_404(ProgressaoDocente, pk=pk)
        progressao.enviar_email_alerta(ignorar_limite_tempo=True)
        return httprr(request.META.get('HTTP_REFERER'), message='Os responsável pelo processo de progressão foram notificados com sucesso.')
    except Exception:
        return httprr(
            request.META.get('HTTP_REFERER'),
            message='Não foi possível notificar os responsável pelo processo de progressão. Tente novamente mais tarde.',
            tag='error',
        )


@rtr('detalhar_configuracao.html')
@permission_required('progressao_docente.change_configuracaoprogressaodocente')
def detalhar_configuracao(request, pk):
    title = 'Configuração - Progressão Docente'
    config = get_object_or_404(ConfiguracaoProgressaoDocente, pk=pk)
    return locals()


@rtr()
@permission_required('progressao_docente.change_progressaodocente')
def reabrir_edicao(request, pk):
    title = 'Avaliações Identificadas'
    processo = get_object_or_404(ProgressaoDocente, pk=pk)
    #
    if request.POST:
        # identificando as avaliações que foram selecionadas
        avaliacoes = request.POST.getlist('avaliacao')
        if not avaliacoes:
            return httprr(request.META.get('HTTP_REFERER'), message='É necessário selecionar ao menos uma avaliação.', tag='error')
        #
        with transaction.atomic():
            for a in Avaliacao.objects.filter(id__in=avaliacoes):
                # a situação do processo sai da derivação em Avaliacao.save(), que espelha a
                # avaliação mais atrasada. Fixá-la aqui exibia "Aguardando Ciência de Resultado"
                # justamente quando a bola tinha voltado para o avaliado editar.
                a.reabrir_para_edicao_reavaliacao()
            return httprr('/admin/progressao_docente/avaliacao/', message='As avaliações selecionadas foram reabertas com sucesso.')
    #
    if processo.pode_reabrir_edicao(request):
        # verificar as avaliações do processo
        # se identificarmos mais de uma avaliação, devemos especificar qual delas serão reabertas
        qs_avaliacao = processo.avaliacao_set.all()
        if qs_avaliacao.count() > 1:
            # mostrar tela para identificação de avaliação
            return locals()
        else:
            with transaction.atomic():
                for avaliacao in qs_avaliacao:
                    # idem: quem define a situação do processo é a derivação em Avaliacao.save()
                    avaliacao.reabrir_para_edicao_reavaliacao()
            return httprr(
                request.META.get('HTTP_REFERER'),
                message='O processo foi posto em edição para reavaliação. Basta o avaliado acessar a avaliação e editar a seu critério.',
            )
    #
    raise PermissionDenied('No momento o processo não pode ter as avaliações reabertas.')
