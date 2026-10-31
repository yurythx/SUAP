"""Substrato dos e2e do tesouro_gerencial: o gestor, um campus com códigos de UG e a execução de referência.

O módulo importa relatórios do Tesouro Gerencial (notas de crédito, execução de empenhos, restos a
pagar e receitas por GRU) e calcula, por campus e ano, as onze **variáveis financeiras** da matriz
orçamentária (``Variavel`` em ``tesouro_gerencial/models.py``). As telas são três views próprias
(``urls.py``) e os dois cadastros de documento de empenho específico que o ``menu.yaml`` oferece.

Decisões deste módulo (as quatro da seção (c) de ``docs/agents/e2e-receita.md``):

1. **Seed** — por factories (#17486), sobre o ``e2e_seed``: o campus ``TGE`` com ``codigo_ug`` e
   ``codigo_ugr`` próprios (é por eles que toda variável acha o que é do campus — a UGR para a
   execução, a UG para a receita de GRU), os dois servidores de ``SERVIDORES`` e a **execução de
   referência** de ``ANO_REFERENCIA`` (``_semear_execucao_de_referencia``), com números fixos e
   ``django_get_or_create`` em todas as factories: o relatório dela tem de dar os mesmos totais em
   toda execução, então nada ali pode duplicar no ``--reuse-db``. Não há ``features/`` no módulo:
   o roteiro veio de ``urls.py``, ``menu.yaml``, ``permissions.yaml``, ``views.py`` e dos models.
2. **Papéis** — sim: dois servidores e o ``admin``. O módulo inteiro é governado pelo grupo
   ``Gestor do Tesouro Gerencial``: ``group_required`` nas três views, ``in_group`` nos alertas da
   página inicial e as oito permissões de ``permissions.yaml`` nos dois admins. O ``servidor`` é o
   contraponto da matriz de acesso (``staff``, para que o 403 do admin seja de permissão e não o
   redirect de quem não entra no ``/admin/``). Os admins dos dados importados não são de grupo
   nenhum: quem os abre é o ``admin`` (superusuário) que o ``e2e_seed`` já cria. Criação eager e
   session-scoped por causa do cache de permissão por processo (armadilha 3).
3. **Relógio** — a sessão NÃO congela. O domínio tem ano (``ano`` do formulário, ``data_emissao``
   dos documentos), mas os relatórios recebem o ano como **parâmetro**: a execução de referência vive
   em 2020 e é consultada como 2020, sem mexer no relógio. Os alertas da página inicial e a regra de
   documento específico olham o ano corrente, e as fixtures deles gravam no ano corrente. Logo
   ``storage_states`` (login cacheado por papel) vale. A única exceção é a pendência de "atualizar os
   relatórios" (``test_alertas.py``), que só depende do ano do relógio: aquele teste congela em volta
   de **uma requisição** de cada vez, e a sessão sobrevive porque o backend de sessão é de arquivo
   (expira pelo ``mtime``, que o congelamento não toca).
4. **Encadeamento** — arquivos independentes, sem prefixo ``NN``. O que um teste muda é dele: o
   empenho da regra de documento específico, o tipo sem documento do alerta e os números das
   planilhas importadas levam ``uuid4``, porque a suíte não dá flush e o CI usa ``--reuse-db``
   (armadilha 8). **Nenhum teste pode gravar no campus ``TGE`` em ``ANO_REFERENCIA``**: os totais
   afirmados em ``test_relatorios.py`` deixariam de fechar em silêncio.

Gate (módulo sem ``features/``, a unidade de cobertura é a rota)::

    python bin/scripts/paridade_e2e.py tesouro_gerencial --rotas

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest tesouro_gerencial/tests/e2e --reuse-db
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:  # os models só são importados dentro dos corpos (padrão dos e2e do repo)
    from rh.models import Setor, UnidadeOrganizacional
    from tesouro_gerencial.models import DocumentoEmpenho, SubElementoNaturezaDespesa, TipoDocumentoEmpenhoEspecifico

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

GRUPO_GESTOR = 'Gestor do Tesouro Gerencial'

# Apelido -> matrícula. Faixa 1620xx, própria do módulo: o job de doc roda vários módulos num banco
# só e a `ServidorFactory` é get-or-create pela matrícula. O `superusuario` é o `admin` do `e2e_seed`:
# os 25 admins de dados importados não estão em grupo nenhum, só ele os abre.
PAPEIS = {'gestor': '162001', 'servidor': '162002', 'superusuario': 'admin'}

# Matrícula -> (nome, grupos).
SERVIDORES: dict[str, tuple[str, list[str]]] = {
    '162001': ('Gestora do Tesouro Gerencial', ['Servidor', GRUPO_GESTOR]),
    '162002': ('Servidor sem Papel no Tesouro', ['Servidor']),
}

# O campus do módulo. UG e UGR diferentes de propósito: `Variavel` acha a execução pela UGR
# (`responsavel_ug`) e a receita de GRU pela UG (`emitente_ug`); com os dois iguais, trocar um
# pelo outro no código passaria despercebido.
SIGLA_CAMPUS = 'TGE'
NOME_CAMPUS = 'Campus Tesouro Gerencial'
CODIGO_UG = '158901'
CODIGO_UGR = '158902'

# Unidade orçamentária do IFRN: as variáveis de LOA exigem `26435`; as de destaque, qualquer outra.
UO_IFRN = '26435'
UO_DESTAQUE = '26298'

# Ano da execução de referência — passado e fixo, para que nenhum teste do ano corrente o toque.
ANO_REFERENCIA = 2020
EMPENHO_LOA = f'{ANO_REFERENCIA}NE000101'
EMPENHO_DESTAQUE = f'{ANO_REFERENCIA}NE000102'

# Tipos de documento de empenho específico da regra de cálculo (`aplicar_calculo`).
TIPO_COM_REGRA = 'E2E Folha de pagamento (aplica a regra)'
TIPO_SEM_REGRA = 'E2E Registro informativo (sem regra)'


def _campus_do_tesouro() -> tuple[Setor, UnidadeOrganizacional]:
    """O setor e a UO do campus ``TGE``, com os códigos de UG gravados na UO.

    ``campus()`` é idempotente pela sigla e não conhece os códigos de UG: eles vão por ``update``
    na UO, que também evita o ``UnidadeOrganizacional.save`` (que regrava todos os setores).
    """
    from rh.models import UnidadeOrganizacional

    setor_campus = campus(SIGLA_CAMPUS, NOME_CAMPUS)
    UnidadeOrganizacional.objects.filter(setor=setor_campus).update(codigo_ug=CODIGO_UG, codigo_ugr=CODIGO_UGR)
    return setor_campus, UnidadeOrganizacional.objects.get(setor=setor_campus)


def classificacoes_do_campus() -> dict[str, object]:
    """Classificações orçamentárias de uma execução do campus ``TGE`` — chaves prontas para as factories."""
    from tesouro_gerencial.tests.factories import (
        AcaoGovernoFactory,
        ClassificacaoInstitucionalFactory,
        FonteRecursoFactory,
        UnidadeGestoraFactory,
    )

    return {
        'unidade_orcamentaria': ClassificacaoInstitucionalFactory(codigo=UO_IFRN, nome='Instituto Federal do Rio Grande do Norte'),
        'acao_governo': AcaoGovernoFactory(codigo='20RL', nome='Funcionamento das instituições federais de educação'),
        'fonte_recurso': FonteRecursoFactory(codigo='1000000000', nome='Recursos ordinários'),
        'emitente_ug': UnidadeGestoraFactory(codigo=CODIGO_UG, nome=NOME_CAMPUS.upper()),
        'responsavel_ug': UnidadeGestoraFactory(codigo=CODIGO_UGR, nome=f'{NOME_CAMPUS.upper()} (UGR)'),
    }


def _subitem_de_contrato_continuado() -> SubElementoNaturezaDespesa:
    """Subitem 17 da natureza 339039 (manutenção de máquinas): o que põe a despesa também na variável GCC."""
    from tesouro_gerencial.tests.factories import NaturezaDespesaFactory, SubElementoNaturezaDespesaFactory

    return SubElementoNaturezaDespesaFactory(
        codigo_subelemento='17', nome='Manutenção e conservação de máquinas', natureza_despesa=NaturezaDespesaFactory()
    )


def empenho_liquidado(numero: str, data: datetime.date, valor_liquidado: Decimal, **campos: object) -> DocumentoEmpenho:
    """Empenho do campus ``TGE`` com uma liquidação (NS) de ``valor_liquidado`` — o que as variáveis somam.

    As variáveis de execução somam a **liquidação** dos empenhos (``Variavel.get_valor_nss``), não o
    valor empenhado: um empenho sem NS entra na listagem com valor zero. Os campos ``*_original`` são
    os que as regras de exclusão leem (ação 20RL, grupo 3 de custeio, natureza 339039).
    """
    from tesouro_gerencial.tests.factories import (
        DocumentoEmpenhoFactory,
        DocumentoEmpenhoItemFactory,
        DocumentoLiquidacaoFactory,
        DocumentoLiquidacaoItemFactory,
    )

    classificacoes = classificacoes_do_campus() | campos
    originais = {
        'acao_governo_original': classificacoes['acao_governo'].codigo,
        'fonte_recurso_original': classificacoes['fonte_recurso'].codigo,
        'naturesa_despesa_original': '339039',
        'grupo_despesa_original': '3',
    }
    empenho = DocumentoEmpenhoFactory(numero=numero, data_emissao=data, **classificacoes, **originais)
    subitem = _subitem_de_contrato_continuado()
    DocumentoEmpenhoItemFactory(documento_empenho=empenho, subitem=subitem, valor=valor_liquidado * 2, subitem_original='17')
    liquidacao = DocumentoLiquidacaoFactory(numero=numero.replace('NE', 'NS'), data_emissao=data, **classificacoes, **originais)
    DocumentoLiquidacaoItemFactory(
        documento_liquidacao=liquidacao, documento_empenho_inicial=empenho, subitem=subitem, valor=valor_liquidado, subitem_original='17'
    )
    return empenho


def _semear_execucao_de_referencia() -> None:
    """A execução do campus ``TGE`` em ``ANO_REFERENCIA``: uma linha de cada fonte que as variáveis somam.

    Os valores são escolhidos para que cada parcela seja reconhecível no total (4.000 + 700 + 300 na
    LOA; 250 só no destaque; 1.500 de receita), e são os que ``test_relatorios.py`` afirma.
    Idempotente: toda factory daqui é get-or-create, inclusive os itens.
    """
    from tesouro_gerencial.tests.factories import (
        AcaoGovernoFactory,
        ClassificacaoInstitucionalFactory,
        FonteRecursoFactory,
        NotaCreditoFactory,
        NotaCreditoItemFactory,
        RAPFactory,
        RAPItemFactory,
        ReceitaGRUFactory,
    )

    data = datetime.date(ANO_REFERENCIA, 3, 10)
    classificacoes = classificacoes_do_campus()
    empenho_liquidado(EMPENHO_LOA, data, Decimal('4000.00'))
    empenho_liquidado(
        EMPENHO_DESTAQUE, data, Decimal('250.00'), unidade_orcamentaria=ClassificacaoInstitucionalFactory(codigo=UO_DESTAQUE, nome='Órgão concedente')
    )

    subitem = _subitem_de_contrato_continuado()
    rap = RAPFactory(
        numero=f'{ANO_REFERENCIA - 1}NE000555',
        ano=ANO_REFERENCIA,
        acao_governo_original='20RL',
        fonte_recurso_original='1000000000',
        naturesa_despesa_original='339039',
        grupo_despesa_original='3',
        **classificacoes,
    )
    RAPItemFactory(rap=rap, subitem=subitem, subitem_original='17', valor_nao_proc_liquidado=Decimal('700.00'))

    nota = NotaCreditoFactory(
        numero=f'{ANO_REFERENCIA}NC000101',
        data_emissao=data,
        unidade_orcamentaria=classificacoes['unidade_orcamentaria'],
        emitente_ug=classificacoes['emitente_ug'],
        favorecido_ug=classificacoes['responsavel_ug'],
    )
    NotaCreditoItemFactory(
        nota_credito=nota,
        responsavel_ug=classificacoes['responsavel_ug'],
        acao_governo=AcaoGovernoFactory(codigo='20RL'),
        fonte_recurso=FonteRecursoFactory(codigo='1000000000'),
        subitem=subitem,
        valor=Decimal('300.00'),
    )
    ReceitaGRUFactory(ano=ANO_REFERENCIA, emitente_ug=classificacoes['emitente_ug'], valor=Decimal('1500.00'))


@pytest.fixture(scope='session')
def tesouro_seed(e2e_seed) -> UnidadeOrganizacional:
    """Campus ``TGE``, servidores com papel e a execução de referência — antes da primeira request.

    Os tipos de documento específico da regra de cálculo também nascem aqui: são cadastro de
    referência (dois, fixos), e não estado de teste.
    """
    from tesouro_gerencial.tests.factories import TipoDocumentoEmpenhoEspecificoFactory

    setor_campus, uo = _campus_do_tesouro()
    criar_servidores(setor_campus, SERVIDORES)
    _semear_execucao_de_referencia()
    TipoDocumentoEmpenhoEspecificoFactory(descricao=TIPO_COM_REGRA, aplicar_calculo=True)
    TipoDocumentoEmpenhoEspecificoFactory(descricao=TIPO_SEM_REGRA, aplicar_calculo=False)
    return uo


@pytest.fixture
def logado_tesouro(logado, tesouro_seed):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def empenho_do_ano(tesouro_seed) -> Iterator[DocumentoEmpenho]:
    """Empenho NOVO do campus ``TGE`` no ano corrente, liquidado — apagado ao fim do teste.

    É estado consumível: os testes de documento específico o marcam e desmarcam. Número com
    ``uuid4`` (a suíte não dá flush) e limpeza no teardown, para que a aba de cada variável do ano
    corrente não acumule empenhos de execuções anteriores.
    """
    from tesouro_gerencial.models import DocumentoEmpenho, DocumentoLiquidacao

    ano = datetime.date.today().year
    numero = f'{ano}NE{uuid4().int % 10**6:06d}'  # só dígitos depois do NE, como o Tesouro numera
    empenho = empenho_liquidado(numero, datetime.date.today(), Decimal('3210.00'))
    yield empenho
    DocumentoLiquidacao.objects.filter(numero=numero.replace('NE', 'NS')).delete()
    DocumentoEmpenho.objects.filter(numero=numero).delete()


@pytest.fixture
def tipo_sem_documento(tesouro_seed) -> Iterator[TipoDocumentoEmpenhoEspecifico]:
    """Tipo de documento específico NOVO, sem documento no ano — o estado que gera o alerta do gestor.

    Apagado no teardown (com os documentos dele, em cascata): um tipo esquecido no banco viraria um
    alerta permanente na página inicial do gestor no ano seguinte.
    """
    from tesouro_gerencial.tests.factories import TipoDocumentoEmpenhoEspecificoFactory

    tipo = TipoDocumentoEmpenhoEspecificoFactory(descricao=f'E2E Tipo sem documento {uuid4().hex[:8]}')
    yield tipo
    tipo.delete()
