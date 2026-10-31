"""Telas da importação SIAPE: upload, seleção de arquivos, progresso, interrupção e ocorrências."""

from __future__ import annotations

import re
from collections.abc import Collection

from django.db.models import Case, Count, ExpressionWrapper, IntegerField, OuterRef, Q, QuerySet, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from sentry_sdk import capture_exception

from comum.models import Log
from djtools.utils import JsonResponse, httprr, permission_required, rtr
from rh.importacao_siape.execucao import (
    ImportacaoNaoAgendada,
    ImportacaoNaoCancelada,
    ImportacaoNaoIniciada,
    ImportacaoNaoInterrompida,
    agendar_importacao,
    cancelar_agendamento,
    encerrar_com_falha,
    iniciar_importacao,
    interromper_importacao,
)
from rh.importacao_siape.forms import ImportacaoSiapeUploadForm
from rh.importacao_siape.layouts import GRUPO_HISTORICOS, GRUPO_NUCLEO, GRUPO_TABELAS, LAYOUTS, dependencias_transitivas, ordem_topologica
from rh.importacao_siape.preparacao import ArquivoExtratorInvalido, criar_importacao
from rh.models import ImportacaoSiape, ImportacaoSiapeArquivo, ImportacaoSiapeLote, ImportacaoSiapeOcorrencia, SituacaoArquivoSiape

RE_SUFIXO_WORKER = re.compile(r'_(\d+)$')

PERMISSAO = 'rh.pode_gerenciar_extracao_siape'
# ocorrências exibidas por arquivo: um layout grande pode registrar dezenas de milhares de avisos
LIMITE_OCORRENCIAS = 2000
GRUPO_OUTROS = 'Não reconhecidos ou sem importação'

MENSAGEM_UPLOAD = 'Arquivos identificados. Marque o que será importado e escolha entre importar agora ou agendar para a execução noturna (01:07).'


# Para que serve: é a porta de entrada do operador de RH para trazer um zip do extrator sem
# depender da pasta vigiada pelo comando noturno. Também é onde ele confere o histórico recente
# (o que foi importado, quando, com quantas falhas) antes de subir um arquivo novo.
@rtr()
@permission_required(PERMISSAO)
def importacao_siape_lista(request: HttpRequest) -> HttpResponse | dict:
    """Tela inicial: formulário de upload do zip do extrator, as 30 importações mais recentes e os
    20 últimos `Log` "Importação de arquivos" do `rh`.

    Ao receber um upload válido, cria a importação (`preparacao.criar_importacao`) e redireciona
    para a tela de detalhe dela; um zip inválido volta como erro do campo `arquivo`.
    """
    title = 'Importação SIAPE'
    form = ImportacaoSiapeUploadForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        arquivo = form.cleaned_data['arquivo']
        try:
            importacao = criar_importacao(arquivo.name, arquivo.read(), origem='tela', usuario=request.user)
        except ArquivoExtratorInvalido as erro:
            form.add_error('arquivo', str(erro))
        else:
            return httprr(importacao.get_absolute_url(), MENSAGEM_UPLOAD)
    importacoes = _importacoes_com_resumo()[:30]
    logs = Log.objects.filter(app='rh', titulo='Importação de arquivos').order_by('-horario', '-id')[:20]
    return locals()


def _contagem_arquivos_falhos() -> Subquery:
    """Subquery: nº de arquivos selecionados em situação `falhou`/`pulado`, por importação (`OuterRef`).

    Contado à parte da soma de ocorrências (`_contagem_ocorrencias`) porque as duas vêm de tabelas
    diferentes (`ImportacaoSiapeArquivo`/`ImportacaoSiapeOcorrencia`); somar as duas no mesmo
    `annotate` da importação, via join direto, multiplicaria linhas (um arquivo x várias
    ocorrências de outro arquivo da mesma importação). Como subquery correlacionada, cada uma soma
    certo antes de virarem uma única expressão em `_importacoes_com_resumo`.
    """
    situacoes_com_falha = (SituacaoArquivoSiape.FALHOU, SituacaoArquivoSiape.PULADO)
    contagem = (
        ImportacaoSiapeArquivo.objects.filter(importacao=OuterRef('pk'), selecionado=True, situacao__in=situacoes_com_falha)
        .order_by()
        .values('importacao')
        .annotate(total=Count('id'))
        .values('total')
    )
    return Coalesce(Subquery(contagem, output_field=IntegerField()), 0)


def _contagem_ocorrencias(niveis: Collection[str]) -> Subquery:
    """Subquery: nº de `ImportacaoSiapeOcorrencia` dos `niveis` dados, somadas entre todos os
    arquivos de uma importação (`OuterRef`). Ver `_contagem_arquivos_falhos` sobre o porquê de ser
    uma subquery à parte, em vez de um `Count` no mesmo `annotate` da importação.
    """
    contagem = (
        ImportacaoSiapeOcorrencia.objects.filter(arquivo__importacao=OuterRef('pk'), nivel__in=niveis)
        .order_by()
        .values('arquivo__importacao')
        .annotate(total=Count('id'))
        .values('total')
    )
    return Coalesce(Subquery(contagem, output_field=IntegerField()), 0)


def _importacoes_com_resumo() -> QuerySet[ImportacaoSiape]:
    """Importações com o total de linhas importadas dos arquivos selecionados, falhas e avisos,
    da mais nova para a mais antiga.

    Falhas = nº de arquivos selecionados `falhou`/`pulado` + nº de ocorrências `error`/`critical`
    da importação; Avisos = nº de ocorrências `warning`. As duas contagens de ocorrência vêm de
    subqueries (`_contagem_arquivos_falhos`/`_contagem_ocorrencias`): um `Count` direto, no mesmo
    `annotate`, juntando o join de `arquivos` com o de `arquivos__ocorrencias` multiplicaria linhas
    (uma por combinação arquivo x ocorrência), inflando as duas contagens.
    """
    selecionados = Q(arquivos__selecionado=True)
    total_falhas = _contagem_arquivos_falhos() + _contagem_ocorrencias(('error', 'critical'))
    # com agregação o Django ignora o Meta.ordering: a ordem (mais nova primeiro) tem de ser explícita
    return (
        ImportacaoSiape.objects.select_related('enviado_por')
        .annotate(
            linhas_importadas=Sum('arquivos__processadas', filter=selecionados),
            total_falhas=ExpressionWrapper(total_falhas, output_field=IntegerField()),
            total_avisos=_contagem_ocorrencias(('warning',)),
        )
        .order_by('-enviado_em', '-id')
    )


# Para que serve: um zip do extrator traz dezenas de arquivos e o operador raramente quer todos;
# aqui ele vê o que foi reconhecido, escolhe o que importar (com as dependências de cada layout à
# vista) e decide entre rodar agora ou deixar para a noite, fora do horário de uso do sistema.
@rtr()
@permission_required(PERMISSAO)
def importacao_siape_detalhe(request: HttpRequest, importacao_id: int) -> HttpResponse | dict:
    """Tela de detalhe de uma importação: seleção de layouts (GET) e as ações de importar,
    agendar ou cancelar o agendamento (POST, despachadas por `_despachar_acao`).
    """
    importacao = get_object_or_404(ImportacaoSiape, pk=importacao_id)
    if request.method == 'POST':
        return _despachar_acao(request, importacao)
    title = f'Importação SIAPE #{importacao.pk}'
    grupos = _agrupar(importacao)
    dependencias = {nome: sorted(dependencias_transitivas(nome)) for nome in LAYOUTS}
    outra_em_execucao = ImportacaoSiape.existe_em_execucao()
    return locals()


# Para que serve: se o processo que rodava a importação morre (reinício, deploy, worker caído), ela
# fica `executando` para sempre e bloqueia qualquer importação nova. Este botão é a saída manual
# do operador para destravar, sem precisar de alguém mexendo direto no banco.
@permission_required(PERMISSAO)
def importacao_siape_interromper(request: HttpRequest, importacao_id: int) -> HttpResponse:
    """Marca manualmente como interrompida (`falhou`) uma importação presa em execução."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    importacao = get_object_or_404(ImportacaoSiape, pk=importacao_id)
    try:
        interromper_importacao(importacao, request.user)
    except ImportacaoNaoInterrompida as erro:
        return httprr(importacao.get_absolute_url(), str(erro), 'error')
    return httprr(importacao.get_absolute_url(), 'Importação marcada como interrompida.')


def _ids_selecionados(request: HttpRequest) -> set[int]:
    """Ids dos arquivos marcados no POST (campo `arquivos`, multi-valor), ignorando não numéricos."""
    return {int(valor) for valor in request.POST.getlist('arquivos') if valor.isdigit()}


def _despachar_acao(request: HttpRequest, importacao: ImportacaoSiape) -> HttpResponse:
    """Despacha o POST da tela de detalhe para a ação pedida (`acao`): agendar, cancelar ou importar.

    Sem o campo `acao`, assume `importar`; um valor desconhecido volta como "Ação inválida.".
    """
    acao = request.POST.get('acao') or 'importar'
    if acao == 'agendar':
        return _agendar(request, importacao)
    if acao == 'cancelar_agendamento':
        return _cancelar_agendamento(importacao)
    if acao == 'importar':
        return _iniciar(request, importacao)
    return httprr(importacao.get_absolute_url(), 'Ação inválida.', 'error')


def _agendar(request: HttpRequest, importacao: ImportacaoSiape) -> HttpResponse:
    """Grava a seleção e agenda a importação para a execução noturna."""
    try:
        agendar_importacao(importacao, _ids_selecionados(request))
    except ImportacaoNaoAgendada as erro:
        return httprr(importacao.get_absolute_url(), str(erro), 'error')
    return httprr(importacao.get_absolute_url(), 'Importação agendada para a execução noturna (01:07).')


def _cancelar_agendamento(importacao: ImportacaoSiape) -> HttpResponse:
    """Desfaz o agendamento e volta a importação para `identificada`."""
    try:
        cancelar_agendamento(importacao)
    except ImportacaoNaoCancelada as erro:
        return httprr(importacao.get_absolute_url(), str(erro), 'error')
    return httprr(importacao.get_absolute_url(), 'Agendamento cancelado.')


def _iniciar(request: HttpRequest, importacao: ImportacaoSiape) -> HttpResponse:
    """Grava a seleção e dispara a execução da importação (task `@task`: Celery ou thread).

    Se a chamada a `executar_importacao_siape` levantar, reporta o erro ao Sentry e encerra a
    importação como `falhou` via `execucao.encerrar_com_falha` (trava, arquivos/lotes pendentes
    fechados, `Log` e pasta apagada). Em produção isso só pega falha de despacho (a execução roda
    em segundo plano); nos testes a task roda inline, e uma exceção da própria execução também cai
    neste ramo — nesse caso a própria execução já encerrou a importação (fora de `executando`), e
    `encerrar_com_falha` levanta `ImportacaoNaoInterrompida`, que este ramo ignora para não
    sobrescrever o resultado real.

    No modo Celery, se `.delay()` levantar depois que a mensagem já foi publicada no broker, este
    ramo marca `falhou` mesmo que um worker chegue a pegar e rodar a task (raro; a recuperação
    nesse caso é reenviar o zip, criando uma importação nova).
    """
    from rh.tasks import executar_importacao_siape

    ids = _ids_selecionados(request)
    try:
        iniciar_importacao(importacao, ids)
    except ImportacaoNaoIniciada as erro:
        return httprr(importacao.get_absolute_url(), str(erro), 'error')
    try:
        executar_importacao_siape(importacao.pk)
    except Exception as erro:
        capture_exception(erro)
        try:
            encerrar_com_falha(importacao, f'Não foi possível iniciar a importação: {erro}')
        except ImportacaoNaoInterrompida:
            pass  # a própria execução (ex.: task inline em teste) já encerrou a importação
        return httprr(importacao.get_absolute_url(), f'Não foi possível iniciar a importação: {erro}', 'error')
    return httprr(importacao.get_absolute_url(), 'Importação iniciada. Acompanhe o andamento abaixo.')


def _resumo_lotes(lotes: list[ImportacaoSiapeLote]) -> str:
    """Texto resumo (contagem por situação) dos lotes de um arquivo, exibido na tela de detalhe."""
    total = len(lotes)
    concluidos = sum(1 for lote in lotes if lote.situacao == SituacaoArquivoSiape.CONCLUIDO)
    executando = sum(1 for lote in lotes if lote.situacao == SituacaoArquivoSiape.EXECUTANDO)
    falhas = sum(1 for lote in lotes if lote.situacao == SituacaoArquivoSiape.FALHOU)
    pulados = sum(1 for lote in lotes if lote.situacao == SituacaoArquivoSiape.PULADO)
    fila = total - concluidos - executando - falhas - pulados
    return f'{total} lotes · {concluidos} concluídos · {executando} em execução · {fila} na fila · {pulados} pulados · {falhas} com falha'


def _agrupar(importacao: ImportacaoSiape) -> list[tuple[str, list[dict]]]:
    """Agrupa os arquivos da importação por grupo do layout (Tabelas, Núcleo, Históricos ou "Não
    reconhecidos ou sem importação", que reúne também os layouts inativos), cada grupo na ordem
    topológica dos layouts, com os dados que a tela precisa.

    Args:
        importacao: Importação cujos arquivos serão agrupados.

    Returns:
        Lista de `(nome do grupo, linhas)`, só com os grupos que têm ao menos um arquivo; cada
        linha é um dict com o arquivo, as dependências do layout dele, as dependências ainda
        ausentes na importação, os lotes e o resumo textual dos lotes (quando há mais de um).
    """
    ordem = {nome: indice for indice, nome in enumerate(ordem_topologica(apenas_ativos=False))}
    presentes = set(importacao.arquivos.exclude(layout=None).values_list('layout', flat=True))
    grupos: dict[str, list[dict]] = {GRUPO_TABELAS: [], GRUPO_NUCLEO: [], GRUPO_HISTORICOS: [], GRUPO_OUTROS: []}
    for arquivo in importacao.arquivos.select_related('importacao').prefetch_related('lotes'):
        layout = LAYOUTS.get(arquivo.layout or '')
        grupo = layout.grupo if layout and layout.ativo else GRUPO_OUTROS
        ausentes = sorted(set(layout.dependencias) - presentes) if layout else []
        lotes = list(arquivo.lotes.all())
        grupos[grupo].append(
            {
                'arquivo': arquivo,
                'dependencias': layout.dependencias if layout else (),
                'ausentes': ausentes,
                'lotes': lotes,
                'resumo_lotes': _resumo_lotes(lotes) if len(lotes) > 1 else '',
            }
        )
    for linhas in grupos.values():
        linhas.sort(key=lambda linha: ordem.get(linha['arquivo'].layout, len(ordem)))
    return [(nome, linhas) for nome, linhas in grupos.items() if linhas]


def _rotulo_worker(nome: str) -> str:
    """'importacao_siape_0' -> 'W1'; sem o sufixo numérico (execução serial), 'W1'."""
    sufixo = RE_SUFIXO_WORKER.search(nome or '')
    return f'W{int(sufixo.group(1)) + 1}' if sufixo else 'W1'


def _chave_ordenacao_worker(nome: str) -> tuple:
    """Ordena pelo sufixo numérico da thread (W10 depois de W9); sem sufixo, pelo nome."""
    sufixo = RE_SUFIXO_WORKER.search(nome or '')
    return (0, int(sufixo.group(1))) if sufixo else (1, nome or '')


def _lote_payload(lote: ImportacaoSiapeLote) -> dict:
    """Serializa um lote para o JSON consumido pelo polling de progresso da tela."""
    return {
        'id': lote.pk,
        'numero': lote.numero,
        'situacao': lote.situacao,
        'situacao_display': lote.get_situacao_display(),
        'classe_status': lote.classe_status,
        'percentual': lote.percentual,
        'processadas': lote.processadas,
        'total_linhas': lote.total_linhas,
        'falhas': lote.falhas,
        'worker': lote.worker,
    }


def _arquivo_payload(arquivo: ImportacaoSiapeArquivo, lotes: list[ImportacaoSiapeLote]) -> dict:
    """Serializa um arquivo (e os payloads de seus lotes) para o JSON de progresso da tela.

    O `motivo` é truncado aos últimos 2000 caracteres: quando o próprio arquivo falhou na leitura,
    na divisão em lotes ou no fim do layout, ele carrega o traceback inteiro, e só a última parte
    (a mensagem do erro) interessa à tela. Falha de lote chega aqui já resumida ("Lote N falhou: ...").
    """
    return {
        'id': arquivo.pk,
        'situacao': arquivo.situacao,
        'situacao_display': arquivo.get_situacao_display(),
        'classe_status': arquivo.classe_status,
        'processadas': arquivo.processadas,
        'total_linhas': arquivo.total_linhas,
        'percentual': arquivo.percentual,
        'falhas': arquivo.falhas,
        'avisos': arquivo.avisos,
        'motivo': arquivo.motivo[-2000:],
        'lotes': [_lote_payload(lote) for lote in lotes],
    }


def _worker_payload(arquivo: ImportacaoSiapeArquivo, lote: ImportacaoSiapeLote, total_lotes: int) -> dict:
    """Serializa, para o JSON de progresso, o lote que um worker está executando agora."""
    return {
        'worker': lote.worker,
        'rotulo': _rotulo_worker(lote.worker),
        'layout': arquivo.layout or '',
        'lote': lote.numero,
        'total_lotes': total_lotes,
        'percentual': lote.percentual,
        'processadas': lote.processadas,
        'total_linhas': lote.total_linhas,
    }


def _workers_do_arquivo(arquivo: ImportacaoSiapeArquivo, lotes: list[ImportacaoSiapeLote]) -> list[dict]:
    """Payloads de worker (ver `_worker_payload`) só dos lotes do arquivo em execução agora."""
    total = len(lotes)
    return [_worker_payload(arquivo, lote, total) for lote in lotes if lote.situacao == SituacaoArquivoSiape.EXECUTANDO]


# Para que serve: uma importação leva de minutos a horas; sem este endpoint o operador só saberia
# o resultado recarregando a página. A tela de detalhe consulta aqui periodicamente para mostrar
# o avanço de cada arquivo/lote e o que cada worker está fazendo, sem recarregar tudo.
@permission_required(PERMISSAO)
def importacao_siape_progresso(request: HttpRequest, importacao_id: int) -> JsonResponse:
    """Endpoint de polling (chamado periodicamente pela tela de detalhe) com o progresso atual da
    importação: situação geral, cada arquivo (com seus lotes) e os workers em execução no momento.
    """
    importacao = get_object_or_404(ImportacaoSiape, pk=importacao_id)
    arquivos = []
    workers = []
    for arquivo in importacao.arquivos.prefetch_related('lotes'):
        lotes = list(arquivo.lotes.all())
        arquivos.append(_arquivo_payload(arquivo, lotes))
        workers.extend(_workers_do_arquivo(arquivo, lotes))
    workers.sort(key=lambda worker: _chave_ordenacao_worker(worker['worker']))
    return JsonResponse(
        {
            'situacao': importacao.situacao,
            'situacao_display': importacao.get_situacao_display(),
            'classe_status': importacao.classe_status,
            'em_execucao': importacao.em_execucao,
            'arquivos': arquivos,
            'workers': workers,
        }
    )


# Para que serve: quando um layout termina com avisos/erros por registro, o operador precisa ver
# quais linhas do arquivo do extrator deram problema e por quê, sem abrir o log do servidor.
# Esta tela lista essas ocorrências (linha, nível, mensagem) de um arquivo da importação, erros
# primeiro (o que o operador mais precisa ver), depois as mais recentes.
@rtr()
@permission_required(PERMISSAO)
def importacao_siape_ocorrencias(request: HttpRequest, importacao_id: int, arquivo_id: int) -> HttpResponse | dict:
    """Tela com as ocorrências (avisos/erros) de um arquivo da importação: as `LIMITE_OCORRENCIAS`
    primeiras (com aviso na tela quando há mais),
    erros primeiro (`error`/`critical`), depois as mais recentes (`-id`) — não mais a ordem de
    registro (`ImportacaoSiapeOcorrencia.Meta.ordering = ['id']`, usada só como desempate).
    """
    arquivo = get_object_or_404(ImportacaoSiapeArquivo, pk=arquivo_id, importacao_id=importacao_id)
    title = f'Ocorrências de {arquivo}'
    prioridade_erro = Case(When(nivel__in=['error', 'critical'], then=Value(0)), default=Value(1), output_field=IntegerField())
    total = arquivo.ocorrencias.count()
    ocorrencias = arquivo.ocorrencias.annotate(prioridade=prioridade_erro).order_by('prioridade', '-id')[:LIMITE_OCORRENCIAS]
    limite = LIMITE_OCORRENCIAS
    return locals()
