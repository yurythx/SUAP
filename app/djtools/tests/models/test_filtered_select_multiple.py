import re

from django.conf import settings
from django.contrib.staticfiles import finders

from djtools.forms.widgets.select import FilteredSelectMultiplePlus


def test_media_so_referencia_estaticos_servidos_sem_collectstatic() -> None:
    # Sem o admin_i18n.js o SelectFilter2 aborta no `interpolate` e o seletor duplo degrada em silêncio (#17425).
    html = str(FilteredSelectMultiplePlus('campi', is_stacked=False).media)
    caminhos = [src.split('?')[0].removeprefix(settings.STATIC_URL) for src in re.findall(r'src="([^"]+)"', html)]
    assert [caminho for caminho in caminhos if not finders.find(caminho)] == []
    assert any(caminho.endswith('admin_i18n.js') for caminho in caminhos)
