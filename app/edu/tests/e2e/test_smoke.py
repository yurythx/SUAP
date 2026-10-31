"""Canário do e2e do edu: o relógio congelado sobrevive a uma request de browser?

Todo o resto da suíte depende de o SUAP responder como se fosse 2019 — é o que faz o
calendário acadêmico, as etapas e as matrículas do seed serem válidas. ``freeze_time``
patcheia o módulo ``datetime`` do processo, e a thread do ``live_server`` roda no mesmo
processo, mas isso é premissa, não fato observado. Este teste é o que a observa.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_relogio_congelado_vale_na_thread_do_servidor(logado_edu):
    """A view enxerga 2019 e o curso do seed aparece na listagem de cursos correntes.

    ``/admin/edu/cursocampus/correntes/`` filtra por ano letivo **corrente**: se o
    servidor estivesse na data real, o curso de 2019 não estaria na lista. Ou seja, a
    própria asserção da listagem é a prova do congelamento.
    """
    page = logado_edu('admin_academico')
    page.goto('/admin/edu/cursocampus/correntes/')
    expect(page.get_by_text('Especialização em Educação Profissional').first).to_be_visible()
