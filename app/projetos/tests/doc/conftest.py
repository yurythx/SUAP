"""Substrato da rodada de geração da doc de usuário do ``projetos`` (Extensão).

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

O conftest monta o seed aqui mesmo (o de ``tests/e2e/`` roda com a data real e este congela
datas de 2018): star-import de ``djtools.e2e_fixtures`` (obrigatório e primeiro — traz os nomes
privados ``_django_db_helper``/``_exige_banco_de_e2e``), ``e2e_seed`` por factories (#17486:
só ``semear_base``) e, no ``doc_seed``, o campus CZN, os papéis (``criar_servidores``) e
``_dados_basicos_extensao`` — as tabelas de apoio que o step do behave "os dados básicos para
a extensão" criava, trazidas para cá quando as ``.feature`` do módulo foram apagadas.

NÃO importa ``projetos/tests/conftest.py``: o seed daqui é próprio. O motivo original era
que as fixtures de lá usavam ``suap_data``, incompatível com o seed e2e no mesmo banco (ver
``djtools/e2e_fixtures.py``); desde a migração delas para factories esse impedimento não
existe mais, mas a separação foi mantida — unificar os dois seeds não foi testado.

Rodar::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5432 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \
      TEST_DATABASE_NAME=test_suap_doc_e2e_projetos DJANGO_SETTINGS_MODULE=suap.settings_test \
      .venv/bin/python -m pytest -m doc --create-db projetos/tests/doc/ -q

O relógio é congelado por teste (cada fase do edital tem sua data, como no behave — o
``projetos`` não roda com a data real, o ciclo inteiro é dirigido por datas de 2018). Como
cada teste congela uma data diferente, a sessão de login não pode ser reusada entre testes
(cookie expirado sob outra data): o ``logado_doc`` faz login REAL a cada teste, no padrão do
``logado_edu`` (``edu/tests/e2e/conftest.py``).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, setor

DESTINO = Path(settings.BASE_DIR) / 'projetos' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Papéis da doc: faixa 157xxx (não colide com `eventos` 1550xx nem com os módulos irmãos,
# que rodam no mesmo banco no CI).
PAPEIS = {
    'gerente': '157001',
    'coordenador': '157002',
    'coord_projeto': '157003',
    'servidor_equipe': '157004',
    'avaliador_a': '157005',
    'avaliador_b': '157006',
}

# Matrícula -> (nome, grupos). O gerente fica no campus CZN; os demais na DIAC/CZN.
GERENTE = {'157001': ('Gerente Projetos Doc', ['Gerente Sistêmico de Extensão'])}
SERVIDORES_DIAC = {
    '157002': ('Coordenador Extensao Doc', ['Coordenador de Extensão']),
    '157003': ('Coordenador Projeto Doc', ['Servidor']),
    '157004': ('Servidor Equipe Doc', ['Servidor']),
    '157005': ('Avaliador A Doc', ['Servidor']),
    '157006': ('Avaliador B Doc', ['Servidor']),
}


class _Relogio:
    """Congelador de data reaproveitável, no padrão de ``edu/tests/e2e/conftest.py``.

    O fluxo do ``projetos`` é dirigido por fases de um edital de 2018 — mesmos períodos do
    behave — e cada teste congela a data da fase que executa. ``freeze_time`` troca
    ``datetime.datetime`` no módulo, então a thread do ``live_server`` (mesmo processo)
    enxerga a mesma data que o teste.
    """

    def __init__(self) -> None:
        self._congelador = None

    def congelar(self, data_br: str) -> None:
        """Fixa a data do processo inteiro; aceita ``dd/mm/aaaa`` ou ``dd/mm/aaaa HH:MM``."""
        from freezegun import freeze_time

        self.descongelar()
        if ' ' in data_br:
            data, hora = data_br.split(maxsplit=1)
            dia, mes, ano = data.split('/')
        else:
            dia, mes, ano = data_br.split('/')
            hora = '00:00'
        self._congelador = freeze_time(f'{ano}-{mes}-{dia} {hora}', tick=True)
        self._congelador.start()

    def descongelar(self) -> None:
        if self._congelador is not None:
            self._congelador.stop()
            self._congelador = None

    def execute_steps(self, texto: str) -> None:
        """Interface mínima do ``context`` do behave, caso um step precise andar com a data."""
        data = re.search(r'"(\d{2}/\d{2}/\d{4})"', texto)
        assert data, f'step não suportado fora do behave: {texto!r}'
        self.congelar(data.group(1))


@pytest.fixture(scope='session')
def relogio():
    """Congelador da sessão; cada teste fixa a própria data e o autouse destrava no fim."""
    # `freeze_time` troca `datetime.date` por `FakeDate` no módulo `datetime`. O `suap/urls.py`
    # importa `suap/api.py`, que monta os schemas pydantic do django-ninja — e o pydantic não
    # reconhece `FakeDate`, estourando `PydanticSchemaGenerationError`. Como esse import é
    # preguiçoso (só acontece na primeira request), sem este aquecimento ele cairia dentro do
    # primeiro congelamento (ver `edu/tests/e2e/conftest.py:_importar_urlconf`).
    from django.urls import get_resolver

    assert get_resolver().url_patterns, 'urlconf vazia: o aquecimento não importou suap/urls.py'
    relogio = _Relogio()
    yield relogio
    relogio.descongelar()


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Seed do módulo: campus CZN, os seis papéis da doc e os dados básicos da extensão.

    Session-scoped e eager pelo mesmo motivo de sempre: o cache de permissão é por processo,
    então um usuário que ganha grupo depois do primeiro login continuaria sem acesso.

    O campus vem antes de ``_dados_basicos_extensao``, que liga o foco tecnológico à UO
    ``CZN``. O ``OrigemRecursoEdital`` (PROEX) não estava no step do behave e a tela de Fonte
    de Recursos o exige na lista de Origem.
    """
    from projetos.models import OrigemRecursoEdital

    czn = campus('CZN', 'Campus Zona Norte')
    criar_servidores(czn, GERENTE)
    criar_servidores(setor('DIAC/CZN', czn, 'Diretoria Acadêmica'), SERVIDORES_DIAC)
    _dados_basicos_extensao()
    OrigemRecursoEdital.objects.get_or_create(descricao='PROEX')


def _dados_basicos_extensao() -> None:
    """Tabelas de apoio da extensão: naturezas 339018/339020/339030, foco, área, tema, bolsas, beneficiário, anos.

    Mesmos valores do antigo step do behave (``projetos/features/steps/given.py``, apagado com as
    ``.feature``): os roteiros da doc escolhem essas opções pelo nome.
    """
    from ae.models import CategoriaBolsa
    from comum.models import Ano
    from financeiro.models import CategoriaEconomicaDespesa, ElementoDespesa, GrupoNaturezaDespesa, ModalidadeAplicacao, NaturezaDespesa
    from projetos.models import AreaTematica, FocoTecnologico, Tema, TipoBeneficiario
    from rh.models import UnidadeOrganizacional

    categoria = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    grupo = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidade = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    for codigo, nome in (('30', 'Material de Consumo'), ('18', 'Auxílio Financeiro a Estudantes'), ('20', 'Auxílio Financeiro a Pesquisadores')):
        elemento = ElementoDespesa.objects.get_or_create(codigo=codigo, nome=nome)[0]
        NaturezaDespesa.objects.get_or_create(
            categoria_economica_despesa=categoria,
            grupo_natureza_despesa=grupo,
            modalidade_aplicacao=modalidade,
            elemento_despesa=elemento,
            codigo=f'3390{codigo}',
            nome=nome,
        )

    czn = UnidadeOrganizacional.objects.suap().get(sigla='CZN')
    FocoTecnologico.objects.get_or_create(descricao='Multidisciplinar', ativo=True)[0].campi.add(czn)
    area = AreaTematica.objects.get_or_create(descricao='Multidisciplinar')[0]
    Tema.objects.get_or_create(descricao='Tecnologia da Informação  e Comunicação', areatematica=area)

    CategoriaBolsa.objects.get_or_create(nome='Bolsa de Extensão', descricao='Bolsa de Extensão', tipo_bolsa='extensão')
    CategoriaBolsa.objects.get_or_create(
        nome='Bolsa de iniciação científica', descricao='Bolsa de iniciação científica', tipo_bolsa='iniciação científica'
    )
    TipoBeneficiario.objects.get_or_create(descricao='Movimentos Sociais')

    Ano.objects.get_or_create(ano=str(datetime.date.today().year))
    Ano.objects.get_or_create(ano='2018')


@pytest.fixture(autouse=True)
def descongela_relogio(relogio):
    """Destrava o relógio ao fim de CADA teste.

    Os testes irmãos de outros módulos (e a própria suíte ``pytest -m doc`` inteira, que roda
    num processo só no CI) dependem da data real: uma data de 2018 que vazasse corromperia
    tudo o que vier depois.
    """
    yield
    relogio.descongelar()


@pytest.fixture
def logado_doc(new_context, login_ui, doc_seed):
    """``(papel) -> Page`` autenticada, com login REAL a cada teste.

    Não usa o ``storage_states`` do ``djtools/e2e_fixtures.py`` (que cacheia um cookie por
    matrícula na sessão) porque cada teste congela uma data diferente: um cookie emitido em
    01/01/2018 e reusado num teste que congelou 16/01/2018 já está expirado. O hasher MD5 de
    ``suap/settings_test.py`` torna o login por teste barato.
    """

    def _logado(papel: str):
        matricula = PAPEIS.get(papel, papel)
        contexto = new_context()
        page = contexto.new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        return login_ui(page, matricula)

    return _logado
