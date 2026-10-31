"""Spike/canário do harness e2e: login real + as duas afirmações que sustentam o desenho.

1. ``test_a_visibilidade`` — dado criado pelo teste (via ORM) é visível na conexão da
   thread do ``live_server``. Prova que o override no-op de ``_django_db_helper`` de fato
   tirou o teste de dentro de uma transação revertida.
2. ``test_b_sem_flush`` — o mesmo dado ainda existe no teste seguinte. Prova que não há
   flush entre testes (que é o que apagaria ``auth_group``/``sync_permissions``).

Um teste só não prova o par, por isso são dois. ``test_a`` usa o ``page`` cru do
pytest-playwright (sem ``logado``) de propósito: valida que o ``unblock()`` de
``e2e_banco`` chega pela cadeia ``browser_context_args → base_url → live_server →
e2e_seed → e2e_banco`` — com ``_django_db_helper`` neutralizado, nada mais desbloqueia o banco.

O objeto é criado via ORM, não pela UI do admin: o spike testa o desenho do harness, não
uma tela.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Gerado no import: os dois testes compartilham o mesmo marcador único dentro da sessão.
MARCA = f'E2E-SPIKE-{uuid4().hex[:8]}'
CODIGO = uuid4().hex[:10]  # Atividade.codigo é varchar(10)
URL_BUSCA = f'/admin/rh/atividade/?q={MARCA}'


def test_a_visibilidade(page, login_ui):
    from rh.models import Atividade

    Atividade.objects.create(codigo=CODIGO, nome=MARCA)

    login_ui(page, 'admin')
    page.goto(URL_BUSCA)
    expect(page.get_by_text(MARCA).first).to_be_visible()


def test_b_sem_flush(logado):
    page = logado('admin')
    page.goto(URL_BUSCA)
    expect(page.get_by_text(MARCA).first).to_be_visible()
