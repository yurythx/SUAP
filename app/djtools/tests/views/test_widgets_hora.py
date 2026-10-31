import datetime

import pytest

from djtools.forms.fields import DateTimeFieldPlus, TimeFieldPlus


@pytest.mark.parametrize(
    ('campo', 'sem_segundos', 'com_segundos'),
    [
        (TimeFieldPlus, datetime.time(14, 0), datetime.time(14, 0, 30)),
        (DateTimeFieldPlus, datetime.datetime(2026, 10, 20, 14, 0), datetime.datetime(2026, 10, 20, 14, 0, 30)),
        # Re-render depois de um erro de validação: o valor volta como string.
        (TimeFieldPlus, '14:00', '14:00:30'),
        (DateTimeFieldPlus, '2026-10-20T14:00:00', '2026-10-20T14:00:30'),
    ],
)
def test_segundos_so_aparecem_se_pedidos_ou_ja_gravados(campo, sem_segundos, com_segundos):
    assert 'step' not in campo().widget.render('hora', sem_segundos)
    # Com o passo padrão de 60 s, o navegador recusaria submeter um valor já gravado com segundos;
    # e os segundos precisam continuar no valor, senão o próximo "Salvar" os trunca.
    html = campo().widget.render('hora', com_segundos)
    assert 'step="1"' in html
    assert ':00:30"' in html


@pytest.mark.parametrize(
    ('campo', 'valor'),
    [(TimeFieldPlus, datetime.time(14, 0)), (DateTimeFieldPlus, datetime.datetime(2026, 10, 20, 14, 0))],
)
def test_show_seconds_exibe_os_segundos(campo, valor):
    assert 'step="1"' in campo(show_seconds=True).widget.render('hora', valor)
