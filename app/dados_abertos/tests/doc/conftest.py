"""Substrato da rodada de geração da doc de usuário do ``dados_abertos``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

Ao contrário do ``eventos`` e do ``edu``, aqui **não há** ``dados_abertos/tests/e2e/`` de
onde herdar seed e papéis — o módulo nunca teve ``.feature`` nem suíte e2e. Por isso o
substrato inteiro nasce neste arquivo, e o star-import é só um:
``djtools.e2e_fixtures``, que traz também os nomes **privados** (``_django_db_helper``,
``_exige_banco_de_e2e``) por causa do ``__all__`` de lá.

O que o seed acrescenta, e por quê (cada item é uma tela que não abriria sem ele):

1. **dois servidores com grupo** — ``Gestor de Dados Abertos Sistêmico`` e
   ``Responsável LAI``, de ``dados_abertos/permissions.yaml``. Criados no seed de SESSÃO
   porque o cache de permissão é por processo: usuário que ganha grupo depois do primeiro
   login continua sem acesso.
2. **permissões individuais do gestor** — sete modelos do módulo (PDA, vínculo PDA/base,
   grupo de trabalho, avaliação da matriz, versão, tópico) NÃO pertencem a nenhum grupo
   padrão (``python bin/scripts/papeis.py dados_abertos.add_planodadosabertos`` devolve 0
   grupos). Sem concedê-las o roteiro para na segunda tela. É exatamente a ressalva que a
   doc faz ao leitor: hoje o roteiro completo pressupõe perfil administrativo.
3. **API externa CKAN ativa** — a linha já vem cadastrada (``carregar_apis`` roda dentro do
   ``e2e_seed``), mas **inativa**. Sem ativar, toda tela de sincronização responde
   *"API CKAN não configurada ou inativa"*.
4. **``configurar_etapas_padrao``** — cria as 5 etapas e 11 ações. Sem o command o dashboard
   renderiza um checklist vazio e não há o que capturar.
5. **``initial_data_criterios``** — os 7 critérios da Resolução nº 3/2017. NÃO vêm no
   ``loaddata initial_data`` do seed comum (o Django casa o *nome* da fixture, e esta se
   chama diferente): sem eles a matriz de priorização sai sem colunas.
6. **uma licença e um tema** — para os selects do cadastro de base de dados não saírem
   vazios na captura.

O servidor CKAN é **falso** (fixture ``ckan_falso``): não existe instância de CKAN nesta
rodada e apontar para uma externa está fora de cogitação. O que o falso substitui é só o
transporte HTTP (``CKANClient._request``); tudo do lado do SUAP — botão, permissão, ordem
das chamadas, payload enviado, ``id_remoto``/``sincronizado_em`` gravados, estado na tela —
é executado de verdade.

Rodar::

    DATABASE_HOST=localhost DATABASE_PORT=5432 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc --create-db dados_abertos/tests/doc/

``--create-db`` porque é o que o CI faz (o job ``gerar-doc`` roda sobre um serviço recém
subido). A suíte é uma **cadeia** — o PDA criado no primeiro teste é o mesmo que chega ao
CKAN no último — e as chaves são fixas (organização, PDA, base, recurso, tópico), então cada
teste apaga o registro homônimo antes de recriá-lo pela tela. É isso que torna o
``--reruns 2`` do CI seguro; de quebra, a rodada inteira é repetível: medido em 11/08/2026,
``--reuse-db`` sobre o banco da rodada anterior fecha 11/11 em 87 s.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

DESTINO = Path(settings.BASE_DIR) / 'dados_abertos' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Apelido -> matrícula, para os testes não ficarem cheios de números mágicos.
PAPEIS = {'gestor': '166001', 'lai': '166002'}

# Matrícula -> (nome, grupos); os dois no campus CZN.
SERVIDORES = {
    '166001': ('Gestor Dados Abertos', ['Gestor de Dados Abertos Sistêmico']),
    '166002': ('Responsavel LAI', ['Responsável LAI']),
}

# Chaves fixas da cadeia. Um teste cria, os seguintes leem — e cada criador apaga o registro
# anterior da mesma chave, para o `--reruns 2` do CI não esbarrar no `unique`.
ORGANIZACAO_TITULO = 'Reitoria'
ORGANIZACAO_SLUG = 'reitoria'
PDA_TITULO = 'Plano de Dados Abertos Institucional'
BASE_TITULO = 'Contratos Vigentes'
BASE_SLUG = 'contratos-vigentes'
RECURSO_NOME = 'Contratos vigentes em CSV'
TOPICO_TITULO = 'Bases priorizadas'

# Conteúdo do recurso que sobe pela tela: a prévia da Deliberação LAI lê o arquivo anexado e
# mostra os 5 primeiros registros, então ele precisa ser um CSV de verdade — os arquivos de
# upload compartilhados (`djtools/e2e_ui.py:ARQUIVOS`) são pdf/docx/png/jpg.
CSV_DE_TESTE = 'numero;objeto;valor;vigencia\n' + '\n'.join(f'2026/{n:03d};Contrato de manutenção {n};{n * 1000},00;31/12/2026' for n in range(1, 9))


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items) -> None:
    """Mantém a cadeia num worker só quando a rodada é paralela (``--dist loadgroup``).

    ``tryfirst`` é obrigatório: sem ele o marcador é aplicado depois de o xdist já ter
    decidido a distribuição, o ``loadgroup`` degrada para ``load`` em silêncio e a cadeia se
    parte entre workers. O CI roda ``-n 1``, mas a rodada local usa ``-n`` à vontade.

    O hook de um conftest de subdiretório recebe os itens da sessão INTEIRA, não só os deste
    diretório — sem o filtro, todo teste de doc ganhava também este marcador e o grupo virava
    a união dos dois nomes (``dados_abertos_doc_projetos`` nos nodeids do CI).
    """
    for item in items:
        if item.nodeid.startswith('dados_abertos/'):
            item.add_marker(pytest.mark.xdist_group('dados_abertos_doc'))


def _completar_permissoes_do_gestor() -> None:
    """Dá ao gestor as permissões do módulo que nenhum grupo padrão concede.

    Só ``deliberar_lai`` fica de fora: é o que separa o Gestor do Responsável LAI, e a doc
    afirma essa separação.
    """
    from django.contrib.auth.models import Permission

    from comum.models import User

    gestor = User.objects.get(username=PAPEIS['gestor'])
    faltantes = Permission.objects.filter(content_type__app_label='dados_abertos').exclude(codename='deliberar_lai')
    gestor.user_permissions.add(*faltantes)


def _ativar_api_ckan() -> None:
    """Preenche e liga a linha ``CKAN`` de APIs Externas (``carregar_apis`` a cria inativa).

    ``save()`` e não ``update()``: ``APIExterna.save`` reescreve o cache
    (``APIEXTERNA_CACHED_CKAN``) de onde ``APIExterna.CKAN`` lê. Um ``queryset.update()``
    deixaria o cache com a linha antiga (inativa) e toda sincronização responderia
    *"API CKAN não configurada ou inativa"* — que é indistinguível de "o falso não pegou".
    """
    from comum.models import APIExterna

    api = APIExterna.objects.get(nome='CKAN')
    api.url_base = 'https://ckan.example.org'
    api.secret = 'chave-de-api-de-teste'
    api.client_id = 'suap'
    api.ativo = True
    api.save()


@pytest.fixture(scope='session')
def dados_abertos_seed(e2e_seed):
    """Papéis, permissões, API CKAN, etapas do PDA e tabelas de apoio — antes da 1ª request."""
    from django.core.management import call_command

    from dados_abertos.models import Licenca, Tema

    criar_servidores(campus('CZN', 'Campus Zona Norte'), SERVIDORES)
    _completar_permissoes_do_gestor()
    _ativar_api_ckan()
    call_command('loaddata', 'initial_data_criterios', verbosity=0, skip_checks=True)
    call_command('configurar_etapas_padrao', verbosity=0, skip_checks=True)
    Licenca.objects.get_or_create(nome='Creative Commons Attribution 4.0', defaults={'descricao': 'CC-BY 4.0'})
    Tema.objects.get_or_create(nome='Governo e Política', defaults={'descricao': 'Gestão e transparência pública'})


@pytest.fixture
def logado_da(logado, dados_abertos_seed):
    """``(papel) -> Page`` autenticada, pelos apelidos de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


def _resposta_do_ckan_falso(remoto: dict, acao: str, dados: dict) -> dict:
    """O CKAN de mentira: cria, atualiza e devolve registros em memória.

    Despacha por sufixo da action (``_create``/``_patch``/``_show``) porque é assim que o
    ``ckan_service`` decide o caminho: ``package_show`` que levanta 404 é o sinal de "não
    existe lá, crie"; devolver ``{}`` para tudo faria o serviço tomar o ramo de atualização e
    nunca gravar ``id_remoto``.
    """
    from dados_abertos.ckan_client import CKANError

    tipo = acao.split('_', maxsplit=1)[0]
    if acao.endswith('_create'):
        registro = {**dados, 'id': f'{tipo}-{uuid4().hex[:8]}', 'state': dados.get('state') or 'active'}
        remoto['por_id'][registro['id']] = registro
        if dados.get('name'):
            remoto['por_nome'][dados['name']] = registro
        if tipo == 'resource':
            remoto['recursos'].setdefault(dados.get('package_id'), []).append(registro)
        return registro
    if acao.endswith('_patch'):
        registro = remoto['por_id'].setdefault(dados.get('id'), {'id': dados.get('id')})
        registro.update(dados)
        return registro
    if acao.endswith('_show'):
        chave = dados.get('id')
        registro = remoto['por_id'].get(chave) or remoto['por_nome'].get(chave)
        if not registro:
            raise CKANError('404 Not found')
        if acao == 'package_show':
            return {**registro, 'resources': remoto['recursos'].get(registro['id'], [])}
        return registro
    raise CKANError(f'action não simulada pelo CKAN falso: {acao}')


@pytest.fixture
def ckan_falso(monkeypatch):
    """Troca o transporte HTTP do ``CKANClient`` por um CKAN de mentira, em memória.

    Patch em ``CKANClient._request``: é o único ponto por onde as seis funções de
    sincronização de ``services/ckan_service.py`` falam com a rede (todas montam o cliente
    com ``CKANClient(base_url=..., api_key=...)``). O ``live_server`` roda numa **thread** do
    mesmo processo, então o patch vale para as requisições servidas por ele.

    Devolve um objeto com ``chamadas`` — a lista ``(action, payload)`` na ordem em que o SUAP
    as fez. É o que permite AFIRMAR (e não deduzir do código) que o conjunto sobe ao CKAN
    levando o dono no ``owner_org``, e que ele é o ``id_remoto`` da organização.
    """
    from dados_abertos.ckan_client import CKANClient

    remoto: dict = {'por_id': {}, 'por_nome': {}, 'recursos': {}}
    chamadas: list[tuple[str, dict]] = []

    def _request(self, action: str, *, data: dict | None = None, files=None, method: str | None = None) -> dict:
        dados = dict(data or {})
        chamadas.append((action, dados))
        return _resposta_do_ckan_falso(remoto, action, dados)

    monkeypatch.setattr(CKANClient, '_request', _request)
    return SimpleNamespace(chamadas=chamadas, remoto=remoto, acoes=lambda: [acao for acao, _ in chamadas])


@pytest.fixture(scope='session')
def arquivo_csv(tmp_path_factory) -> str:
    """Caminho de um CSV real, para o upload do recurso e a prévia da Deliberação LAI."""
    caminho = tmp_path_factory.mktemp('dados_abertos') / 'contratos.csv'
    caminho.write_text(CSV_DE_TESTE, encoding='utf-8')
    return str(caminho)
