"""Substrato das capturas de doc do frota.

O relógio congelado em 25/11/2018, o seed (cadastros básicos + os cinco papéis) e a sessão de
login vêm do conftest do **e2e do próprio módulo** — é ele que decide congelar o relógio da
sessão e fazer login de verdade a cada teste, e a doc não pode ter uma segunda opinião sobre
isso. Aqui só se declara o destino das capturas, como manda a camada compartilhada.

Os dois `_fixtures` importados pelo nome **não** são redundância: `from ... import *` descarta
nomes que começam com `_`, e sem `_django_db_helper` o pytest-django volta a embrulhar os
testes em `TransactionTestCase` (o `live_server` força `transaction=True`) e dá **flush em
todas as tabelas entre os testes**. O sintoma não aponta para o truque: o seed some depois do
primeiro teste e o segundo login falha com "usuário e senha corretos".
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from djtools.e2e_fixtures import _exige_banco_de_e2e, capturas
from frota.tests.e2e.conftest import *  # noqa: F403
from frota.tests.e2e.conftest import _django_db_helper

DESTINO = Path(settings.BASE_DIR) / 'frota' / 'docs' / 'usuario'
capturar = capturas(DESTINO)
