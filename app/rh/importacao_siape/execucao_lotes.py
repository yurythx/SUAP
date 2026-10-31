"""Lotes de uma importação SIAPE: expansão de cada layout em etapas de lotes, execução e consolidação.

Cada layout pronto é expandido na thread principal (`expandir`): uma etapa por arquivo, um lote
por fatia do arquivo (ver `lotes.dividir_em_lotes`). Os lotes de uma etapa rodam em paralelo no
pool do agendador (ou em série na thread atual, com `workers <= 1`), cada um com seu próprio
`ImportadorSIAPE` (`_rodar_com_retentativa`, que tenta o lote de novo do zero, até
`TENTATIVAS_POR_DEADLOCK` vezes, se ele esbarrar num deadlock do Postgres — ver `_eh_deadlock`).
Quando o layout termina, `ao_finalizar` (de volta à thread principal) consolida a situação de cada
arquivo pelos lotes.
"""

from __future__ import annotations

import random
import threading
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING

import psycopg
from django.db import OperationalError, connection
from django.db.models import F

from comum.importador import get_itens
from rh.importacao_siape.layouts import LAYOUTS
from rh.importacao_siape.lotes import Lote, chave_de_particao, dividir_em_lotes
from rh.importacao_siape.progresso import ItensComProgresso, capturando_ocorrencias
from rh.models import ImportacaoSiapeArquivo, ImportacaoSiapeLote, ImportacaoSiapeOcorrencia, Servidor, SituacaoArquivoSiape

if TYPE_CHECKING:
    from rh.importador import ImportadorSIAPE

Unidade = Callable[[], None]

MOTIVO_ARQUIVO_ANTERIOR_FALHOU = 'Arquivo anterior do mesmo layout falhou.'
MOTIVO_LOTE_ANTERIOR_FALHOU = 'Lote anterior do mesmo arquivo falhou.'
MOTIVO_OUTRO_ARQUIVO_FALHOU = 'Outro arquivo do mesmo layout falhou ao ser lido.'

# Para que serve: o post_save de `ServidorFuncaoHistorico` (`processo_eletronico`, fora deste app)
# apaga e recria os `CompartilhamentoProcessoEletronicoPoderDeChefe` de TODO o setor da função,
# travando o vínculo de cada chefe do setor. Foi assim que dois LOTES do próprio servidor2 (quando
# ele ainda tinha partição por CPF/matrícula, e setores diferentes rodavam em paralelo) travaram um
# no outro — deadlock do Postgres, visto nas importações #4 e #14 — e é por isso que `servidor2` e
# `historico_funcao` não são mais divididos em lotes (ver `layouts._PARTICOES`): sem partição, cada
# um roda um único lote, e um layout só tem uma etapa em execução por vez mesmo com mais de um
# arquivo (etapas do mesmo nó rodam em sequência, nunca em paralelo — ver `agendador`), então não
# sobra mais nenhum par de lotes DESTA importação disputando essa trava entre si. A retentativa
# abaixo é a rede de segurança que continua necessária: um deadlock ainda pode vir de FORA da
# importação (a tela do setor, o cron de outro módulo, qualquer código que grave
# `ServidorFuncaoHistorico`/o vínculo do chefe ao mesmo tempo, pelo mesmo post_save) ou de um
# layout futuro que precise continuar particionado apesar de cair no mesmo efeito colateral por
# setor.
TENTATIVAS_POR_DEADLOCK = 3  # tentativa original + até 2 repetições
INTERVALO_RETENTATIVA_SEGUNDOS = (0.5, 2.0)
_CODIGO_SQLSTATE_DEADLOCK = '40P01'


def _eh_deadlock(erro: BaseException) -> bool:
    """Se `erro` é um deadlock do Postgres detectado numa transação.

    Reconhece um `OperationalError` do Django cuja causa (`__cause__`, a exceção original do
    driver) é `psycopg.errors.DeadlockDetected`, ou cujo `sqlstate` é `40P01` (o código do Postgres
    para deadlock) — checar o `sqlstate` além do tipo é mais robusto a mudanças na classe exata
    levantada pelo driver.

    Args:
        erro: Exceção capturada ao rodar um lote.

    Returns:
        `True` se `erro` for um deadlock (candidato a retentativa); `False` para qualquer outra
        falha (que continua sem retentativa).
    """
    if not isinstance(erro, OperationalError):
        return False
    causa = erro.__cause__
    if causa is None:
        return False
    return isinstance(causa, psycopg.errors.DeadlockDetected) or getattr(causa, 'sqlstate', None) == _CODIGO_SQLSTATE_DEADLOCK


def _aguardar_antes_de_tentar_novamente() -> None:
    """Espera um intervalo aleatório (`INTERVALO_RETENTATIVA_SEGUNDOS`) antes de repetir um lote
    após um deadlock, para reduzir a chance de os lotes concorrentes colidirem de novo na mesma
    trava. Função à parte (em vez de `time.sleep` direto no chamador) para os testes substituírem
    por um no-op e não esperarem de verdade.
    """
    time.sleep(random.uniform(*INTERVALO_RETENTATIVA_SEGUNDOS))


# `SubgrupoOcorrencia` não tem restrição única em `descricao`: dois lotes criando o mesmo
# subgrupo ao mesmo tempo gerariam duplicatas (e `MultipleObjectsReturned` depois). Os subgrupos
# de descrição constante são criados antes de os lotes começarem, pelo mesmo método do importador.
_SUBGRUPOS_POR_LAYOUT: dict[str, tuple[tuple[str, bool], ...]] = {
    # (descrição, usa o `ModelPlus.get_or_create` da classe em vez do `objects.get_or_create`)
    'servidor1': (('EXCLUSAO', False),),
    'servidor2': (('INCLUSAO NO ORGAO', True), ('INCLUSAO NO SERVICO PUBLICO', True)),
}


def _agora() -> datetime:
    """Atalho para `datetime.now()`, usado em todos os carimbos de início/fim deste módulo."""
    return datetime.now()


def _atualizar(obj: ImportacaoSiapeArquivo | ImportacaoSiapeLote, **campos: object) -> None:
    """Atualiza os campos no objeto em memória e faz o `UPDATE` correspondente no banco."""
    for campo, valor in campos.items():
        setattr(obj, campo, valor)
    type(obj).objects.filter(pk=obj.pk).update(**campos)


def _ultima_linha(texto: str) -> str:
    """Última linha não vazia de um texto (usado para resumir o traceback de um lote falho)."""
    linhas = texto.strip().splitlines()
    return linhas[-1] if linhas else ''


# Para que serve: com o servidor1 dividido em lotes, cada lote veria só parte dos cargos sem
# correspondente no SUAP; gravar por lote registraria contagens parciais e concorrentes. Isto junta
# tudo e grava uma vez só, quando o layout termina.
class PendenciasDeCargo:
    """Soma, entre os lotes do `servidor1`, os cargos do SIAPE sem correspondente no SUAP.

    Cada lote acumula na própria instância de `ImportadorSIAPE`; a gravação acontece uma vez,
    quando o layout termina, com a soma de todos os lotes (os lotes rodam em threads diferentes).
    """

    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._pendencias: dict[str, dict] = {}

    def somar(self, acumulador: Mapping[str, dict]) -> None:
        """Soma, de forma thread-safe, as pendências de cargo de um lote ao total acumulado.

        Args:
            acumulador: `cargos_emprego_pendentes` de um `ImportadorSIAPE` (código do cargo ->
                dados com `grupo_codigo` e `qtd_servidores`), como produzido por um lote do servidor1.
        """
        with self._trava:
            for codigo, dados in acumulador.items():
                pendencia = self._pendencias.setdefault(codigo, {'grupo_codigo': dados['grupo_codigo'], 'qtd_servidores': 0})
                pendencia['qtd_servidores'] += dados['qtd_servidores']

    def registrar(self) -> None:
        """Grava as pendências de cargo acumuladas de todos os lotes, via `ImportadorSIAPE`."""
        from rh.importador import ImportadorSIAPE

        importador = ImportadorSIAPE()
        importador.cargos_emprego_pendentes = self._pendencias
        importador._registrar_cargos_emprego_pendentes()


# Os itens de um arquivo grande ocupam muita memória: sem soltar a lista ao fim do último lote,
# todos os arquivos já processados ficariam vivos até o fim da importação.
class _ItensDoArquivo:
    """Itens de um arquivo, compartilhados pelos lotes dele e liberados quando o último termina."""

    def __init__(self, itens: list[dict], quantidade_de_lotes: int) -> None:
        self._itens: list[dict] | None = itens
        self._restantes = quantidade_de_lotes
        self._trava = threading.Lock()

    def sublista(self, indices: Sequence[int]) -> list[dict]:
        """Devolve os itens do arquivo nos índices dados (os índices do lote), na ordem recebida."""
        itens = self._itens or []
        return [itens[indice] for indice in indices]

    def liberar(self) -> None:
        """Marca um lote deste arquivo como terminado; libera a lista de itens quando for o último."""
        with self._trava:
            self._restantes -= 1
            if self._restantes <= 0:
                self._itens = None


class _ProgressoDoLote:
    """Grava o avanço do lote e soma ao arquivo só o que andou desde o último aviso."""

    def __init__(self, arquivo_id: int, lote_id: int) -> None:
        self._arquivo_id = arquivo_id
        self._lote_id = lote_id
        self._reportado = 0

    @property
    def reportado(self) -> int:
        """Quantidade já somada ao `processadas` do arquivo por esta instância, até agora.

        Usada por `ExecucaoPorLotes._preparar_retentativa` para desfazer, numa retentativa por
        deadlock, exatamente o que esta tentativa já tinha reportado (nem mais, nem menos).
        """
        return self._reportado

    def __call__(self, processadas: int) -> None:
        """Grava `processadas` no lote e soma ao arquivo o delta desde o último aviso.

        Args:
            processadas: Quantidade total de linhas do lote já percorridas até agora.
        """
        delta = processadas - self._reportado
        ImportacaoSiapeLote.objects.filter(pk=self._lote_id).update(processadas=processadas)
        ImportacaoSiapeArquivo.objects.filter(pk=self._arquivo_id).update(processadas=F('processadas') + delta)
        # só depois dos dois UPDATEs: se o segundo falhar, `reportado` continua refletindo o que
        # de fato está gravado, e uma retentativa (`_preparar_retentativa`) desfaz exatamente isso.
        self._reportado = processadas


def _registrar_ocorrencia(
    lote: ImportacaoSiapeLote, indices: Sequence[int], nivel: str, posicao: int | None, mensagem: str
) -> ImportacaoSiapeOcorrencia:
    """Cria a `ImportacaoSiapeOcorrencia` de um lote e soma 1 à contagem certa (falhas ou avisos) do
    lote e do arquivo, conforme o nível.

    Args:
        lote: Lote onde a ocorrência aconteceu.
        indices: Índices (0-based, no arquivo) das linhas deste lote, na mesma ordem em que foram
            passadas ao importador — usado para traduzir a posição dentro do lote em linha do arquivo.
        nivel: Nível da ocorrência (`warning`, `error`, `critical`), em minúsculas. `warning` soma 1
            a `avisos`; qualquer outro nível (`error`/`critical` — os únicos capturados por
            `CapturaOcorrencias`, que só instala o handler a partir de `logging.WARNING`) soma 1 a
            `falhas`.
        posicao: Posição 1-based, dentro do lote, do item que estava sendo percorrido no momento
            do log. Com `None` (posição não rastreada) ou `0` (log antes do primeiro item), a
            ocorrência é gravada com esse mesmo valor em `linha`, sem traduzir para linha do arquivo.
        mensagem: Texto da ocorrência.

    Returns:
        A ocorrência criada — devolvida (em vez de descartada) para quem chama poder rastrear o
        `pk` sem uma consulta extra; ver `_OcorrenciasDaTentativa`, que usa isso para desfazer os
        registros de uma tentativa de lote que acabou batendo num deadlock.
    """
    # posição 1-based dentro do lote -> linha 1-based no arquivo
    linha = indices[posicao - 1] + 1 if posicao else posicao
    ocorrencia = ImportacaoSiapeOcorrencia.objects.create(arquivo_id=lote.arquivo_id, nivel=nivel, linha=linha, mensagem=mensagem)
    campo = 'avisos' if nivel == 'warning' else 'falhas'
    ImportacaoSiapeArquivo.objects.filter(pk=lote.arquivo_id).update(**{campo: F(campo) + 1})
    ImportacaoSiapeLote.objects.filter(pk=lote.pk).update(**{campo: F(campo) + 1})
    return ocorrencia


# Para que serve: numa retentativa por deadlock, tudo o que a tentativa perdedora já tinha
# registrado (ocorrências, e o que elas somaram a `falhas`/`avisos`) precisa ser desfeito antes de
# rodar de novo — senão a tentativa seguinte grava as mesmas ocorrências de novo (duplicando na
# tela e inflando os contadores) e um `error`/`critical` que sobrasse da tentativa perdida faria
# `execucao._situacao_final` marcar a importação como concluída com falhas mesmo quando a
# retentativa dá certo. Esta classe é o `registrar` passado a `capturando_ocorrencias`: grava pelo
# caminho de sempre (`_registrar_ocorrencia`) e também lembra o que essa tentativa criou.
class _OcorrenciasDaTentativa:
    """Ocorrências registradas por uma tentativa de lote, para poderem ser desfeitas se ela falhar.

    Attributes:
        ids: `pk` de cada `ImportacaoSiapeOcorrencia` que esta tentativa criou, na ordem em que
            foram registradas.
        falhas: Quantas dessas ocorrências somaram a `falhas` (nível `error`/`critical`).
        avisos: Quantas dessas ocorrências somaram a `avisos` (nível `warning`).
    """

    def __init__(self, lote: ImportacaoSiapeLote, indices: Sequence[int]) -> None:
        self._lote = lote
        self._indices = indices
        self.ids: list[int] = []
        self.falhas = 0
        self.avisos = 0

    def __call__(self, nivel: str, posicao: int | None, mensagem: str) -> None:
        """Registra a ocorrência (mesmo caminho de sempre) e soma ao que esta tentativa acumulou."""
        ocorrencia = _registrar_ocorrencia(self._lote, self._indices, nivel, posicao, mensagem)
        self.ids.append(ocorrencia.pk)
        if nivel == 'warning':
            self.avisos += 1
        else:
            self.falhas += 1


# Para que serve: o agendador é genérico (só conhece nomes de nós e unidades); esta classe é a
# ponte com o domínio. Traduz "layout pronto" em lotes do `ImportadorSIAPE` e mantém arquivos e
# lotes no banco coerentes para a tela de progresso, inclusive quando algo falha no meio.
class ExecucaoPorLotes:
    """Callbacks do agendador (`expandir`, `ao_finalizar`, `ao_pular`) para os layouts de uma importação.

    Attributes:
        por_layout: Nome do layout -> arquivos selecionados desse layout, na importação.
        fechar_conexao: Se `True` (workers > 1), fecha a conexão do banco ao fim de cada lote —
            necessário porque cada thread do pool abre a sua própria.
        tamanho_lote: Tamanho de referência para dividir um arquivo em lotes (ver `lotes.dividir_em_lotes`).
        workers: Quantidade de workers do pool (usado como `minimo_de_lotes` ao dividir um arquivo).
        pendencias_de_cargo: Acumulador, entre os lotes do servidor1, dos cargos do SIAPE sem
            correspondente no SUAP.
    """

    def __init__(self, por_layout: Mapping[str, list[ImportacaoSiapeArquivo]], workers: int, tamanho_lote: int) -> None:
        self.por_layout = por_layout
        self.fechar_conexao = workers > 1
        self.tamanho_lote = tamanho_lote
        self.workers = workers
        self.pendencias_de_cargo = PendenciasDeCargo()

    # --- expansão (thread principal) ---------------------------------------------------

    def expandir(self, nome: str) -> list[list[Unidade]]:
        """Callback `expandir` do agendador: lê os arquivos do layout e os divide em etapas de lotes.

        Uma etapa por arquivo (na ordem em que aparecem em `por_layout[nome]`); os lotes de uma
        mesma etapa rodam em paralelo. Antes de devolver, se o layout somar mais de um lote,
        "aquece" (`_aquecer_lookups`) os lookups que não podem ser criados de forma concorrente
        por dois lotes do layout.

        Args:
            nome: Nome do layout pronto para ser expandido (todas as dependências já concluíram).

        Returns:
            Uma lista de etapas (uma por arquivo), cada etapa uma lista de unidades (uma por lote).

        Raises:
            Exception: qualquer falha ao ler um arquivo, dividir em lotes ou aquecer os lookups —
                antes de propagar, marca os arquivos/lotes afetados como falhos/pulados.
        """
        arquivos = self.por_layout[nome]
        etapas: list[list[Unidade]] = []
        itens_do_layout: list[list[dict]] = []
        try:
            chave = self._chave_do_layout(nome)
            for arquivo in arquivos:
                itens = get_itens(arquivo.nome_ref, arquivo.nome_txt)
                etapas.append(self._expandir_arquivo(nome, arquivo, itens, chave))
                itens_do_layout.append(itens)
        except Exception:
            _falhar_expansao(arquivos, len(etapas))
            raise
        if sum(len(etapa) for etapa in etapas) > 1:
            try:
                _aquecer_lookups(nome, itens_do_layout)
            except Exception:
                _falhar_arquivos(arquivos, traceback.format_exc())
                raise
        return etapas

    def _chave_do_layout(self, nome: str) -> Callable[[dict], str] | None:
        """Monta a função de chave de partição do layout, ou `None` se ele não tiver partição.

        Para partições do tipo `cpf_da_matricula`, monta antes o mapa matrícula -> CPF (uma
        consulta), para não repeti-la por item.
        """
        particao = LAYOUTS[nome].particao
        if particao is None:
            return None
        cpf_por_matricula = None
        if particao.tipo == 'cpf_da_matricula':
            cpf_por_matricula = dict(Servidor.objects.values_list('matricula', 'pessoa_fisica__cpf'))
        return chave_de_particao(particao, cpf_por_matricula)

    def _expandir_arquivo(self, nome: str, arquivo: ImportacaoSiapeArquivo, itens: list[dict], chave: Callable[[dict], str] | None) -> list[Unidade]:
        """Divide os itens do arquivo em lotes, cria o `ImportacaoSiapeLote` de cada um e devolve
        as unidades (uma por lote) que os processam, presas ao mesmo `_ItensDoArquivo` compartilhado.
        """
        lotes = dividir_em_lotes(itens, chave, self.tamanho_lote, minimo_de_lotes=self.workers)
        registros = ImportacaoSiapeLote.objects.bulk_create(
            [ImportacaoSiapeLote(arquivo=arquivo, numero=lote.numero, total_linhas=len(lote.indices)) for lote in lotes]
        )
        compartilhados = _ItensDoArquivo(itens, len(lotes))
        return [partial(self._executar_lote, nome, registro, lote, compartilhados) for registro, lote in zip(registros, lotes, strict=True)]

    # --- lote (thread do pool) ---------------------------------------------------------

    def _executar_lote(self, nome: str, registro: ImportacaoSiapeLote, lote: Lote, compartilhados: _ItensDoArquivo) -> None:
        """Unidade submetida ao pool para um lote: processa e sempre libera os itens compartilhados
        do arquivo e fecha a conexão do banco desta thread, quando há mais de um worker.
        """
        try:
            self._processar_lote(nome, registro, lote, compartilhados)
        finally:
            compartilhados.liberar()
            if self.fechar_conexao:
                connection.close()

    def _processar_lote(self, nome: str, registro: ImportacaoSiapeLote, lote: Lote, compartilhados: _ItensDoArquivo) -> None:
        """Roda o lote (com retentativa em caso de deadlock, ver `_rodar_com_retentativa`); marca o
        arquivo como `executando` se este for o primeiro lote dele a começar e grava a situação
        final (`concluido` ou `falhou`, com o traceback da última tentativa) do lote ao terminar.
        """
        try:
            agora = _agora()
            _atualizar(registro, situacao=SituacaoArquivoSiape.EXECUTANDO, inicio=agora, worker=threading.current_thread().name)
            # condicional e atômico: só o primeiro lote a começar marca o arquivo
            ImportacaoSiapeArquivo.objects.filter(pk=registro.arquivo_id, situacao=SituacaoArquivoSiape.AGUARDANDO).update(
                situacao=SituacaoArquivoSiape.EXECUTANDO, inicio=agora
            )
            self._rodar_com_retentativa(nome, registro, lote, compartilhados)
        except Exception:
            _atualizar(registro, situacao=SituacaoArquivoSiape.FALHOU, motivo=traceback.format_exc(), fim=_agora())
            raise
        _atualizar(registro, situacao=SituacaoArquivoSiape.CONCLUIDO, processadas=registro.total_linhas, fim=_agora())

    def _rodar_com_retentativa(self, nome: str, registro: ImportacaoSiapeLote, lote: Lote, compartilhados: _ItensDoArquivo) -> None:
        """Roda o lote, tentando de novo em caso de deadlock, até `TENTATIVAS_POR_DEADLOCK` no total.

        Cada tentativa usa uma instância nova de `ImportadorSIAPE`, de `ItensComProgresso` e de
        `_OcorrenciasDaTentativa` (os caches do importador são só leitura; reprocessar as mesmas
        linhas é o que toda reimportação já faz — as funções `importar_*` são idempotentes por
        linha). Um deadlock antes da última tentativa é engolido aqui — `_preparar_retentativa`
        desfaz o progresso e as ocorrências já contabilizados e espera antes de tentar de novo;
        qualquer outro erro, ou o deadlock da última tentativa, propaga normalmente (o `except` de
        `_processar_lote` marca o lote como `falhou`).
        """
        from rh.importador import ImportadorSIAPE

        for tentativa in range(1, TENTATIVAS_POR_DEADLOCK + 1):
            importador = ImportadorSIAPE()
            progresso = _ProgressoDoLote(registro.arquivo_id, registro.pk)
            ocorrencias = _OcorrenciasDaTentativa(registro, lote.indices)
            itens = ItensComProgresso(compartilhados.sublista(lote.indices), progresso)
            try:
                with capturando_ocorrencias(ocorrencias, itens):
                    self._importar(nome, importador, itens)
                return
            except Exception as erro:
                if not _eh_deadlock(erro) or tentativa == TENTATIVAS_POR_DEADLOCK:
                    raise
                self._preparar_retentativa(registro, progresso, ocorrencias, tentativa)

    def _preparar_retentativa(
        self, registro: ImportacaoSiapeLote, progresso: _ProgressoDoLote, ocorrencias: _OcorrenciasDaTentativa, tentativa: int
    ) -> None:
        """Desfaz o `processadas` e as ocorrências (com `falhas`/`avisos`) já contabilizados pela
        tentativa que acabou de sofrer o deadlock, e registra o aviso de que o lote vai tentar de
        novo, antes de esperar e tentar de novo.

        Args:
            registro: Lote que vai ser tentado de novo.
            progresso: `_ProgressoDoLote` da tentativa que falhou, para saber quanto desfazer.
            ocorrencias: `_OcorrenciasDaTentativa` da tentativa que falhou, para apagar o que ela
                tinha registrado (ver `_desfazer_ocorrencias`).
            tentativa: Número (1-based) da tentativa que acabou de falhar.
        """
        if progresso.reportado:
            ImportacaoSiapeArquivo.objects.filter(pk=registro.arquivo_id).update(processadas=F('processadas') - progresso.reportado)
        ImportacaoSiapeLote.objects.filter(pk=registro.pk).update(processadas=0)
        _desfazer_ocorrencias(registro, ocorrencias)
        restantes = TENTATIVAS_POR_DEADLOCK - 1
        mensagem = f'Lote {registro.numero}: conflito de concorrência no banco (deadlock); nova tentativa {tentativa} de {restantes}.'
        # registrada pelo mesmo caminho (`_registrar_ocorrencia`) de qualquer outra ocorrência, para
        # que `avisos` conte também os avisos de retentativa (consistente com a coluna): não é um
        # problema na linha, mas o operador precisa ver que a tentativa anterior não terminou por
        # um motivo "normal". Criada fora do `_OcorrenciasDaTentativa` desta tentativa (que já
        # terminou) — não entra nos ids apagados por uma eventual retentativa seguinte: cada aviso
        # de retentativa é permanente, um por deadlock enfrentado.
        _registrar_ocorrencia(registro, (), 'warning', None, mensagem)
        _aguardar_antes_de_tentar_novamente()

    def _importar(self, nome: str, importador: ImportadorSIAPE, itens: ItensComProgresso) -> None:
        """Chama a função `importar_*` do layout no `ImportadorSIAPE`.

        Caso especial do `servidor1`: chama `importar_servidor1` sem registrar as pendências de
        cargo por lote (`registrar_pendentes=False`) e acumula-as em `self.pendencias_de_cargo`
        para serem gravadas uma única vez, quando o layout inteiro terminar (`ao_finalizar`).
        """
        if nome != 'servidor1':
            importador._get_map_layout_functions()[nome](itens)
            return
        importador.importar_servidor1(itens, registrar_pendentes=False)
        self.pendencias_de_cargo.somar(importador.cargos_emprego_pendentes)

    # --- fim do layout (thread principal) ----------------------------------------------

    def ao_finalizar(self, nome: str, erro: BaseException | None) -> None:
        """Callback `ao_finalizar` do agendador: registra as pendências de cargo do servidor1 (se
        o layout terminou sem erro) e consolida a situação de cada arquivo do layout pelos lotes.
        """
        if erro is None and nome == 'servidor1':
            try:
                self.pendencias_de_cargo.registrar()
            except Exception:
                _falhar_arquivos(self.por_layout[nome], traceback.format_exc())
                raise
        for arquivo in self.por_layout[nome]:
            _consolidar_arquivo(arquivo)

    def ao_pular(self, nome: str, motivo: str) -> None:
        """Callback `ao_pular` do agendador: marca todos os arquivos do layout pulado como `pulado`."""
        for arquivo in self.por_layout[nome]:
            _atualizar(arquivo, situacao=SituacaoArquivoSiape.PULADO, motivo=motivo, fim=_agora())


def _desfazer_ocorrencias(registro: ImportacaoSiapeLote, ocorrencias: _OcorrenciasDaTentativa) -> None:
    """Apaga as ocorrências de uma tentativa perdedora e devolve a `falhas`/`avisos` do arquivo e do
    lote o que elas tinham somado.

    Sem isto, a retentativa reprocessaria as mesmas linhas e regravaria as mesmas ocorrências —
    duplicando-as na tela e inflando os contadores — e um `error`/`critical` que sobrasse da
    tentativa perdida faria `execucao._situacao_final` marcar a importação como concluída com
    falhas mesmo quando a retentativa seguinte dá certo.
    """
    if ocorrencias.ids:
        ImportacaoSiapeOcorrencia.objects.filter(pk__in=ocorrencias.ids).delete()
    if ocorrencias.falhas:
        ImportacaoSiapeArquivo.objects.filter(pk=registro.arquivo_id).update(falhas=F('falhas') - ocorrencias.falhas)
        ImportacaoSiapeLote.objects.filter(pk=registro.pk).update(falhas=F('falhas') - ocorrencias.falhas)
    if ocorrencias.avisos:
        ImportacaoSiapeArquivo.objects.filter(pk=registro.arquivo_id).update(avisos=F('avisos') - ocorrencias.avisos)
        ImportacaoSiapeLote.objects.filter(pk=registro.pk).update(avisos=F('avisos') - ocorrencias.avisos)


def _aquecer_lookups(nome: str, itens_do_layout: Sequence[Sequence[dict]]) -> None:
    """Cria antes dos lotes os subgrupos de ocorrência de descrição constante do layout (e, para o
    servidor4, os municípios dos endereços), para dois lotes não disputarem o mesmo `get_or_create`.

    Chamada só quando o layout tem mais de um lote no total (ver `expandir`): com um único lote não
    há concorrência a evitar.
    """
    from rh.importador import ImportadorSIAPE, SubgrupoOcorrencia

    for descricao, pelo_model_plus in _SUBGRUPOS_POR_LAYOUT.get(nome, ()):
        try:
            if pelo_model_plus:
                SubgrupoOcorrencia.get_or_create(descricao=descricao)
            else:
                SubgrupoOcorrencia.objects.get_or_create(descricao=descricao)
        except Exception:
            # sem unique constraint em `descricao`: uma duplicata já existente em produção
            # (criada por uma corrida antiga) faz o `get_or_create` estourar `MultipleObjectsReturned`;
            # a própria linha do lote vai reproduzir o erro e registrá-lo como ocorrência.
            continue
    if nome == 'servidor4':
        _aquecer_municipios(ImportadorSIAPE.municipio_do_endereco, itens_do_layout)


def _aquecer_municipios(municipio_do_endereco: Callable[[dict], object], itens_do_layout: Sequence[Sequence[dict]]) -> None:
    """Cria antes dos lotes os municípios dos endereços do servidor4.

    `Municipio.get_or_create` não trata a violação da unicidade de `identificacao`: dois lotes
    criando o mesmo município ao mesmo tempo fariam um deles perder o endereço daquela linha.
    Uma chamada por (município, UF) distinto, pelo mesmo caminho do importador; erro numa chave
    é ignorado aqui (a própria linha vai reproduzi-lo e registrá-lo como ocorrência).
    """
    vistos: set[tuple[str, str]] = set()
    for itens in itens_do_layout:
        for item in itens:
            chave = (item.get('IT-NO-MUNICIPIO', ''), item.get('IT-SG-UF-SERV-DISPONIVEL', ''))
            if chave in vistos:
                continue
            vistos.add(chave)
            try:
                municipio_do_endereco(item)
            except Exception:
                continue


def _falhar_expansao(arquivos: Sequence[ImportacaoSiapeArquivo], indice_falho: int) -> None:
    """Um arquivo falhou ao ser expandido (leitura ou divisão): nenhum lote do layout vai rodar.

    O falho leva o traceback; os seguintes nem são lidos; os anteriores já têm lotes criados,
    que não vão rodar e ficam pulados junto com o arquivo. Chamado dentro do `except`.
    """
    motivo = traceback.format_exc()
    for indice, arquivo in enumerate(arquivos):
        if indice < indice_falho:
            _atualizar(arquivo, situacao=SituacaoArquivoSiape.PULADO, motivo=MOTIVO_OUTRO_ARQUIVO_FALHOU, fim=_agora())
            _pular_lotes_aguardando(arquivo, MOTIVO_OUTRO_ARQUIVO_FALHOU)
        elif indice == indice_falho:
            _atualizar(arquivo, situacao=SituacaoArquivoSiape.FALHOU, motivo=motivo, fim=_agora())
        else:
            _atualizar(arquivo, situacao=SituacaoArquivoSiape.PULADO, motivo=MOTIVO_ARQUIVO_ANTERIOR_FALHOU, fim=_agora())


def _falhar_arquivos(arquivos: Sequence[ImportacaoSiapeArquivo], motivo: str) -> None:
    """Marca todos os arquivos como `falhou` (com o mesmo motivo) e pula os lotes ainda aguardando.

    Usado em dois momentos: quando `_aquecer_lookups` falha (lotes já criados, nenhum começou) e
    quando o registro das pendências de cargo do servidor1 falha em `ao_finalizar` (todos os
    lotes já rodaram; aí não há lote aguardando e os arquivos viram `falhou` mesmo com os dados
    gravados).
    """
    for arquivo in arquivos:
        _atualizar(arquivo, situacao=SituacaoArquivoSiape.FALHOU, motivo=motivo, fim=_agora())
        _pular_lotes_aguardando(arquivo, 'O layout falhou antes de este lote começar.')


def _lote_por_situacao(lotes: Sequence[ImportacaoSiapeLote], situacao: str) -> ImportacaoSiapeLote | None:
    """Primeiro lote da lista com a situação dada, ou `None` se nenhum tiver."""
    return next((lote for lote in lotes if lote.situacao == situacao), None)


def _falhar_arquivo_por_lote(arquivo: ImportacaoSiapeArquivo, motivo: str) -> None:
    """Marca o arquivo como `falhou` (por causa de um lote) e pula os lotes dele ainda aguardando."""
    _atualizar(arquivo, situacao=SituacaoArquivoSiape.FALHOU, motivo=motivo, fim=_agora())
    _pular_lotes_aguardando(arquivo, MOTIVO_LOTE_ANTERIOR_FALHOU)


def _consolidar_arquivo(arquivo: ImportacaoSiapeArquivo) -> None:
    """Deriva a situação final do arquivo a partir da situação de seus lotes, ao fim do layout.

    Chamado por `ExecucaoPorLotes.ao_finalizar` para cada arquivo do layout, uma vez que todos os
    lotes dele já terminaram (ou nunca chegaram a rodar). Um arquivo já `falhou`/`pulado` na
    expansão é ignorado (decidido ainda lá); senão, a situação vem do pior lote: algum `falhou`
    vence, depois algum preso em `executando` (não devia acontecer, mas é tratado), depois todos
    `concluido` vira `concluido`, e por fim nenhum lote sequer começou vira `pulado`.
    """
    if arquivo.situacao in (SituacaoArquivoSiape.FALHOU, SituacaoArquivoSiape.PULADO):
        return  # decidido ainda na expansão, nesta mesma thread (as do pool só gravam EXECUTANDO)
    lotes = list(arquivo.lotes.order_by('numero'))
    falho = _lote_por_situacao(lotes, SituacaoArquivoSiape.FALHOU)
    preso = _lote_por_situacao(lotes, SituacaoArquivoSiape.EXECUTANDO)
    if falho is not None:
        _falhar_arquivo_por_lote(arquivo, f'Lote {falho.numero} falhou: {_ultima_linha(falho.motivo)}')
    elif preso is not None:
        # o lote nem chegou a gravar FALHOU (erro na própria gravação, ou uma BaseException que
        # cancelou o pool antes de o `finally` da unidade rodar): sem isso o arquivo cairia no
        # ramo "PULADO" abaixo, com um motivo que não descreve que um lote ficou pendurado.
        _atualizar(preso, situacao=SituacaoArquivoSiape.FALHOU, motivo='Lote não terminou.', fim=_agora())
        _falhar_arquivo_por_lote(arquivo, f'Lote {preso.numero} não terminou.')
    elif all(lote.situacao == SituacaoArquivoSiape.CONCLUIDO for lote in lotes):
        _atualizar(arquivo, situacao=SituacaoArquivoSiape.CONCLUIDO, processadas=arquivo.total_linhas, fim=_agora())
    else:
        # os lotes nem começaram: a etapa de um arquivo anterior do layout falhou
        _atualizar(arquivo, situacao=SituacaoArquivoSiape.PULADO, motivo=MOTIVO_ARQUIVO_ANTERIOR_FALHOU, fim=_agora())
        _pular_lotes_aguardando(arquivo, MOTIVO_ARQUIVO_ANTERIOR_FALHOU)


def _pular_lotes_aguardando(arquivo: ImportacaoSiapeArquivo, motivo: str) -> None:
    """Marca como `pulado` todos os lotes do arquivo ainda em `aguardando` (nunca chegaram a rodar)."""
    arquivo.lotes.filter(situacao=SituacaoArquivoSiape.AGUARDANDO).update(situacao=SituacaoArquivoSiape.PULADO, motivo=motivo, fim=_agora())
