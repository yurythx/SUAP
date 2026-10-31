"""Harness da doc de usuário do módulo ``demandas``.

Reusa as fixtures de ``djtools/e2e_fixtures.py`` **sem alterá-las**; aqui vive só o que é
decisão do módulo: o seed e o atalho de login por papel.

Os cinco papéis saem das ``.feature`` do behave (``demandas/features/*.feature``), que é
onde o módulo declara quem faz o quê. Os usuários são criados pelo mesmo passo que o
behave usava, agora por factories (``criar_servidores``, #17486): servidor de verdade, com
vínculo na árvore — criar ``User`` na mão daria um usuário sem servidor e o menu lateral viria
vazio.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, setor

DESTINO = Path(settings.BASE_DIR) / 'demandas' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405


PAPEIS = {
    'demandante': '105001',
    'analista': '105002',
    'servidor': '105004',
    'servidor2': '105005',
    'ti': '105006',
}

# Matrícula -> (nome, grupos), das `.feature` do behave. O demandante fica em DIAC/CEN, os demais
# em DIAC/CZN (ver `demandas_doc_seed`).
SERVIDORES = {
    PAPEIS['demandante']: ('Demandante', ['Demandante']),
    PAPEIS['analista']: ('Analista do Demandas', ['Analista']),
    PAPEIS['servidor']: ('Servidor Comum', ['Servidor']),
    PAPEIS['servidor2']: ('Servidor Comum2', ['Servidor']),
    PAPEIS['ti']: ('TI', ['Coordenador de TI sistêmico']),
}


@pytest.fixture(scope='session')
def demandas_doc_seed(e2e_seed):
    """Cadastros básicos do módulo, na mesma forma do ``given.py`` do behave.

    Escopo de sessão: o seed é commitado uma vez e vive a run inteira — o painel de permissões
    é cacheado por processo, então criar grupo ou vínculo dentro do teste daria o cache errado
    para o seguinte.
    """
    import datetime

    from comum.models import AreaAtuacao, User
    from demandas.models import AreaAtuacaoDemanda, Atualizacao, Tag

    diac_cen = setor('DIAC/CEN', campus('CEN', 'Campus Central'))
    diac_czn = setor('DIAC/CZN', campus('CZN', 'Campus Zona Norte'))
    matricula_demandante = PAPEIS['demandante']
    criar_servidores(diac_cen, {matricula_demandante: SERVIDORES[matricula_demandante]})
    criar_servidores(diac_czn, {m: dados for m, dados in SERVIDORES.items() if m != matricula_demandante})

    area, _ = AreaAtuacao.objects.get_or_create(nome='Tecnologia da Informação')
    tag, _ = Tag.objects.get_or_create(nome='Tag Especial')

    demandante = User.objects.get(username=PAPEIS['demandante'])
    area_atuacao, _ = AreaAtuacaoDemanda.objects.get_or_create(area=area)
    area_atuacao.demandante_responsavel = demandante
    area_atuacao.demandantes.add(demandante)
    area_atuacao.recebe_sugestoes_publico_aluno = True
    area_atuacao.recebe_sugestoes_publico_servidor = True
    area_atuacao.recebe_sugestoes_publico_prestador_servico = True
    area_atuacao.save()
    area_atuacao.tags_relacionadas.set([tag])

    # A lista pública de atualizações do sistema nasce vazia no seed; sem ao menos
    # uma linha a tela não tem o que mostrar e a face pública do módulo não se documenta.
    atualizacao, _ = Atualizacao.objects.get_or_create(
        descricao='Melhoria no módulo de demandas',
        defaults={
            'tipo': Atualizacao.FUNCIONALIDADE,
            'data': datetime.date.today(),
            'detalhamento': 'Ajustes de usabilidade no acompanhamento das demandas.',
        },
    )
    atualizacao.tags.set([tag])


@pytest.fixture
def logado_demandas(logado, demandas_doc_seed):
    """Devolve ``(papel) -> Page`` autenticado, com o papel nomeado como nas ``.feature``."""

    def _logado(papel: str):
        return logado(PAPEIS[papel])

    return _logado
