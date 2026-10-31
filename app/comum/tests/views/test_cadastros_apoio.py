"""Cadastros de apoio de prédio e sala pelo admin.

Estas 19 telas são as tabelas de apoio que o formulário de prédio e o de sala oferecem em
lista (cobertura, vedação, piso, forro, climatização…). São a única parte do ``comum`` que
o gate de rotas (``bin/scripts/paridade_e2e.py comum --rotas``) não enxerga: ele colhe rotas
literais de ``comum/urls.py``, e estas são rotas do ``django.contrib.admin``. Até este
arquivo existir, quem as cobria eram os 19 cenários de
``comum/features/003.comum.predio_salas.feature``, removida junto com este commit.

O fluxo é um só — abrir a listagem, abrir o formulário, salvar, ver o registro — repetido
sobre 19 models registrados no **mesmo** ``SomenteDescricaoModelAdmin``
(``comum/admin.py:135``). Por isso a parametrização: o que pode quebrar
individualmente é o registro do model no admin e o seu ``verbose_name``, não o fluxo.

Papel: ``Coordenador da Sede``, o mesmo que a feature usava. Não é enfeite — o menu
publica as telas por ``comum.add_predio``, mas o admin decide por permissão **do próprio
model** (``comum.add_coberturapredio`` e companhia), e esse grupo é o único que as concede
(``comum/permissions.yaml:116``). Um usuário com ``add_predio`` e nada mais vê o item no
menu e toma 403 na tela.
"""

import pytest
from django.contrib.auth.models import Group

from comum.models import (
    AcabamentoExternoPredio,
    AcabamentoParedeSala,
    ClassificacaoSala,
    ClimatizacaoSala,
    CoberturaPredio,
    EsquadriasSala,
    EstruturaPredio,
    ForroSala,
    InstalacaoEletricaSala,
    InstalacaoGasesSala,
    InstalacaoHidraulicaSala,
    InstalacaoLogicaSala,
    PisoSala,
    SistemaAbastecimentoPredio,
    SistemaAlimentacaoEletricaPredio,
    SistemaProtecaoDescargaAtmosfericaPredio,
    SistemaSanitarioPredio,
    UsoSala,
    VedacaoPredio,
)
from comum.tests.factories import PredioFactory
from rh.tests.factories import ServidorFactory, SetorFactory

# (model, url do admin, valor de `descricao`). A URL é literal de propósito: é ela que o
# `menu.yaml` publica, e derivá-la de `_meta` esconderia uma troca de rótulo do menu.
CADASTROS = [
    (AcabamentoExternoPredio, '/admin/comum/acabamentoexternopredio/', 'Pintura'),
    (CoberturaPredio, '/admin/comum/coberturapredio/', 'Laje impermeabilizada'),
    (EstruturaPredio, '/admin/comum/estruturapredio/', 'Alvenaria estrutural'),
    (SistemaAbastecimentoPredio, '/admin/comum/sistemaabastecimentopredio/', 'Concessionária'),
    (SistemaAlimentacaoEletricaPredio, '/admin/comum/sistemaalimentacaoeletricapredio/', 'Transformador individual'),
    (SistemaProtecaoDescargaAtmosfericaPredio, '/admin/comum/sistemaprotecaodescargaatmosfericapredio/', 'Para-raios tipo Franklin'),
    (SistemaSanitarioPredio, '/admin/comum/sistemasanitariopredio/', 'Rede pública de esgoto'),
    (VedacaoPredio, '/admin/comum/vedacaopredio/', 'Alvenaria de tijolo cerâmico'),
    (AcabamentoParedeSala, '/admin/comum/acabamentoparedesala/', 'Pintura acrílica'),
    (ClassificacaoSala, '/admin/comum/classificacaosala/', 'Sala de aula'),
    (ClimatizacaoSala, '/admin/comum/climatizacaosala/', 'Ar-condicionado split'),
    (EsquadriasSala, '/admin/comum/esquadriassala/', 'Alumínio com vidro'),
    (ForroSala, '/admin/comum/forrosala/', 'Forro de PVC'),
    (InstalacaoGasesSala, '/admin/comum/instalacaogasessala/', 'Rede de gás liquefeito'),
    (InstalacaoEletricaSala, '/admin/comum/instalacaoeletricasala/', 'Embutida em conduíte'),
    (InstalacaoHidraulicaSala, '/admin/comum/instalacaohidraulicasala/', 'Aparente em PVC'),
    (InstalacaoLogicaSala, '/admin/comum/instalacaologicasala/', 'Cabeamento estruturado categoria 6'),
    (PisoSala, '/admin/comum/pisosala/', 'Piso cerâmico'),
    (UsoSala, '/admin/comum/usosala/', 'Aula teórica'),
]

# `ClassificacaoSala.descricao_expandida` é um `TextField` sem `blank=True`, logo
# obrigatório no formulário — os outros 18 models têm só `descricao` e `ativo`.
CAMPOS_EXTRA = {ClassificacaoSala: {'descricao_expandida': 'Ambiente destinado a aulas expositivas.'}}


@pytest.fixture
def coordenador_da_sede(db, sync_permissions):
    """Servidor no grupo ``Coordenador da Sede``, logado pelo cliente de teste.

    ``ServidorFactory`` já cria ``User`` e ``Vinculo``; o grupo é o que carrega as
    permissões de `add`/`change`/`view` dos 19 models.
    """
    servidor = ServidorFactory(setor=SetorFactory(sigla='SEDE'))
    user = servidor.get_user()
    user.groups.add(Group.objects.get(name='Coordenador da Sede'))
    return user


@pytest.mark.parametrize(('model', 'url', 'descricao'), CADASTROS, ids=[url.split('/')[3] for _, url, _ in CADASTROS])
def test_cadastrar_tabela_de_apoio_de_predio_e_sala(client, coordenador_da_sede, model, url, descricao):
    client.force_login(coordenador_da_sede)

    assert client.get(url).status_code == 200
    assert client.get(f'{url}add/').status_code == 200

    dados = {'descricao': descricao, 'ativo': 'on', '_save': ''} | CAMPOS_EXTRA.get(model, {})
    resposta = client.post(f'{url}add/', dados, follow=True)

    assert resposta.status_code == 200
    assert model.objects.filter(descricao=descricao, ativo=True).count() == 1


def test_sem_a_permissao_do_model_a_tela_nao_abre(client, db, sync_permissions):
    """O menu publica as telas por ``comum.add_predio``; o admin cobra a do próprio model.

    Contraexemplo do papel: quem cadastra prédio mas não está na Sede vê o item no menu e
    não passa da porta. É o que separa esta suíte de uma que só afirmasse HTTP 200.
    """
    servidor = ServidorFactory(setor=SetorFactory(sigla='OUTRO'))
    user = servidor.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Chaves'))
    client.force_login(user)

    assert user.has_perm('comum.add_predio')
    assert not user.has_perm('comum.add_coberturapredio')
    assert client.get('/admin/comum/coberturapredio/').status_code == 403


def test_ficha_de_predio_inexistente_responde_404(client, coordenador_da_sede):
    """A ficha do prédio (``/comum/predio/<pk>/``) responde 404 para pk inexistente, não 500."""
    client.force_login(coordenador_da_sede)
    predio = PredioFactory()

    assert client.get(f'/comum/predio/{predio.pk}/').status_code == 200
    assert client.get(f'/comum/predio/{predio.pk + 1}/').status_code == 404
