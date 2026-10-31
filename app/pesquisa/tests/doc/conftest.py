"""Substrato da rodada de geração da doc de usuário do ``pesquisa``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa do ciclo
edital → projeto → pré-seleção → avaliação → distribuição de bolsas → execução →
monitoramento → conclusão; a asserção existe só para a rodada falhar alto quando a tela
mudou de forma.

O ``pesquisa`` não tem ``tests/e2e/`` (diferente do ``eventos``): todo o seed nasce aqui.
O star-import de ``djtools.e2e_fixtures`` (obrigatório — traz os nomes privados
``_django_db_helper``/``_exige_banco_de_e2e``) fornece ``capturas``, ``logado`` e o
``e2e_seed`` (a base por factories, ``semear_base``, #17486). Os atores
do módulo são criados por factories (``servidor_com_login`` e ``seed.criar_aluno``), com
matrículas na faixa própria 156xxx — o CI roda ``pytest -m doc`` num banco só, com os
módulos irmãos.

NÃO importar ``pesquisa/tests/conftest.py``: a semeadura aqui é por ORM/UI e os payloads
de lá serviram só de referência para os campos. O motivo original da separação era que as
fixtures de lá usavam ``suap_data``, incompatível com o seed e2e no mesmo banco (ver
``djtools/e2e_fixtures.py``); desde a migração delas para factories esse impedimento não
existe mais, mas a separação foi mantida — unificar os dois seeds não foi testado.

Rodar::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5432 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e_pesquisa DJANGO_SETTINGS_MODULE=suap.settings_test \\
        .venv/bin/python -m pytest -m doc --create-db pesquisa/tests/doc/ -q

``--create-db``, não ``--reuse-db``: esta suíte não é idempotente entre execuções (a
cadeia de estados edital→projeto→… depende do banco da rodada).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login

DESTINO = Path(settings.BASE_DIR) / 'pesquisa' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Um papel por ator do ciclo. Matrículas na faixa 156xxx (eventos usa 1550xx e os irmãos
# projetos/projetos_ensino têm faixas próprias; o CI roda todos no mesmo banco).
PAPEIS = {
    'diretor': '156001',
    'coord_pesquisa': '156002',
    'coord_projeto': '156003',
    'servidor': '156004',
    'avaliador1': '156005',
    'avaliador2': '156006',
    'aluno': '201911156001',
}

# ``matrícula -> (nome, grupo, CPF)`` dos servidores, todos no campus CZN. O CPF é o que o
# currículo Lattes repete abaixo.
SERVIDORES = {
    PAPEIS['diretor']: ('Diretor Pesquisa Doc', 'Diretor de Pesquisa', '134.256.669-67'),
    PAPEIS['coord_pesquisa']: ('Coordenador Pesquisa Doc', 'Coordenador de Pesquisa', '856.545.239-53'),
    PAPEIS['coord_projeto']: ('Coordenador Projeto Doc', 'Servidor', '893.981.052-09'),
    PAPEIS['servidor']: ('Servidor Projeto Doc', 'Servidor', '659.884.814-85'),
    PAPEIS['avaliador1']: ('Avaliador Um Doc', 'Servidor', '783.244.946-26'),
    PAPEIS['avaliador2']: ('Avaliador Dois Doc', 'Servidor', '647.463.593-26'),
}


def _hoje(dias: int = 0) -> datetime.datetime:
    return datetime.datetime.now() + datetime.timedelta(days=dias)


def marcar_periodo(edital, fase: str) -> None:
    """Desloca o calendário do edital para a fase que o teste vai exercitar.

    Mesma janela do behave (que congela o relógio) e dos testes de fluxo
    (``comum/tests/fluxo_edital_helpers.py``), mas sem congelar nada: o edital nasce com
    datas relativas a hoje e cada teste reposiciona a fase antes de navegar.
    """
    if fase == 'inscricao':
        edital.inicio_inscricoes, edital.fim_inscricoes = _hoje(0), _hoje(5)
        edital.inicio_pre_selecao, edital.inicio_selecao, edital.fim_selecao, edital.divulgacao_selecao = (
            _hoje(10),
            _hoje(15),
            _hoje(20),
            _hoje(21),
        )
    elif fase == 'pre_selecao':
        edital.inicio_inscricoes, edital.fim_inscricoes = _hoje(-10), _hoje(-5)
        edital.inicio_pre_selecao, edital.inicio_selecao, edital.fim_selecao, edital.divulgacao_selecao = (
            _hoje(0),
            _hoje(15),
            _hoje(20),
            _hoje(21),
        )
    elif fase == 'selecao':
        edital.inicio_inscricoes, edital.fim_inscricoes = _hoje(-15), _hoje(-10)
        edital.inicio_pre_selecao, edital.inicio_selecao, edital.fim_selecao, edital.divulgacao_selecao = (
            _hoje(-5),
            _hoje(0),
            _hoje(20),
            _hoje(21),
        )
    elif fase == 'distribuicao':
        edital.inicio_inscricoes, edital.fim_inscricoes = _hoje(-25), _hoje(-20)
        edital.inicio_pre_selecao, edital.inicio_selecao, edital.fim_selecao, edital.divulgacao_selecao = (
            _hoje(-15),
            _hoje(-10),
            _hoje(-1),
            _hoje(1),
        )
    elif fase == 'execucao':
        edital.inicio_inscricoes, edital.fim_inscricoes = _hoje(-30), _hoje(-25)
        edital.inicio_pre_selecao, edital.inicio_selecao, edital.fim_selecao, edital.divulgacao_selecao = (
            _hoje(-20),
            _hoje(-15),
            _hoje(-5),
            _hoje(0),
        )
    else:
        raise AssertionError(f'fase desconhecida: {fase}')
    edital.save(update_fields=['inicio_inscricoes', 'fim_inscricoes', 'inicio_pre_selecao', 'inicio_selecao', 'fim_selecao', 'divulgacao_selecao'])


def _curriculo_lattes(servidor, identificador: str, cpf: str) -> None:
    """Currículo Lattes mínimo — pré-requisito de `Edital.pode_submeter_projeto`."""
    from cnpq.models import CurriculoVittaeLattes, DadoComplementar, DadoGeral, GrupoPesquisa

    grupo = GrupoPesquisa.objects.get(codigo='01')
    curriculo = CurriculoVittaeLattes.objects.create(sistema_origem_xml='', numero_identificador=identificador)
    curriculo.dado_complementar = DadoComplementar.objects.create()
    curriculo.dado_geral = DadoGeral.objects.create(
        nome_completo=servidor.pessoa_fisica.nome,
        nome_citacao=servidor.pessoa_fisica.nome,
        nacionalidade='Brasileiro',
        cpf=cpf,
        pais_nascimento='Brasil',
        uf_nascimento='RN',
        cidade_nascimento='Natal',
        sexo='F',
        permissao_divulgacao='Sim',
    )
    curriculo.vinculo = servidor.get_vinculo()
    curriculo.grupos_pesquisa.add(grupo)
    curriculo.save()


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """``e2e_seed`` + o campus CZN + as tabelas de apoio + os atores do ciclo de pesquisa.

    Session-scoped e eager pelo mesmo motivo de todos os módulos: o cache de permissão é
    por processo, então um usuário que ganha grupo depois do primeiro login continua sem
    acesso.
    """
    from datetime import date

    from cnpq.models import GrupoPesquisa
    from comum.models import Ano
    from pesquisa.tests.e2e import seed
    from rh.models import AreaConhecimento, Titulacao

    # O plano de oferta e a distribuição de bolsas são do campus CZN; o laboratório de
    # `seed.dados_basicos` também procura por ele.
    czn = campus('CZN')
    campus('CEN')

    # Tabelas de apoio: áreas de conhecimento, natureza de despesa (rubricas),
    # origem de recurso, titulação, categoria de bolsa, etc. O behave do módulo foi
    # aposentado (`b8c6253131`) e `pesquisa/features/` não existe mais; `seed.dados_basicos`
    # é o replay do mesmo passo (`given.py:32`), já usado pelo `tests/e2e/`.
    seed.dados_basicos()

    # Os atores, por factories (a tabela `os seguintes usuários` do behave).
    servidores = {
        matricula: servidor_com_login(matricula, czn, grupos=[grupo], staff=True, pessoa_fisica__nome=nome, pessoa_fisica__cpf=cpf)
        for matricula, (nome, grupo, cpf) in SERVIDORES.items()
    }
    seed.criar_aluno(czn, PAPEIS['aluno'], 'Aluno Projeto Doc', '392.501.964-23')

    # Complementos do behave `os usuários da pesquisa` (incompatível com as matrículas
    # desta rodada, então replicado à mão): Lattes do coordenador e do servidor,
    # titulação e áreas dos avaliadores, ano corrente.
    GrupoPesquisa.objects.get_or_create(codigo='01', descricao='Grupo de Pesquisa', instituicao='IFRN')
    area = AreaConhecimento.objects.get(codigo='10000003')
    titulacao = Titulacao.objects.get(codigo='26')
    for papel, identificador in (('coord_projeto', 'doc-01'), ('servidor', 'doc-02'), ('avaliador1', 'doc-03'), ('avaliador2', 'doc-04')):
        servidor = servidores[PAPEIS[papel]]
        _curriculo_lattes(servidor, identificador, SERVIDORES[PAPEIS[papel]][2])
        servidor.areas_de_conhecimento.add(area)
    for papel in ('avaliador1', 'avaliador2'):
        servidores[PAPEIS[papel]].titulacao = titulacao
        servidores[PAPEIS[papel]].save(update_fields=['titulacao'])

    # O `Ano` corrente alimenta os autocompletes de ano (desembolso, gastos).
    Ano.objects.get_or_create(ano=date.today().year)


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada, pelo nome do papel em ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado
