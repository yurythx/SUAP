from typing import Any

from djtools.management.commands import BaseCommandPlus
from pesquisa.management.commands._rpi import LEIAUTE_PATENTE, Importacao, importar_revista_recente

PATENTES = Importacao(
    tipo='Patente',
    prefixo='P',
    leiaute=LEIAUTE_PATENTE,
    baixar_sempre=True,
    ler_pelo_nome_do_zip=False,
    reler_em_latin1=False,
    despacho_por_codigo=True,
)


class Command(BaseCommandPlus):
    def handle(self, *args: Any, **options: Any) -> int | str | None:
        # Importa os registros de patentes da instituição e seus despachos da última RPI do INPI (http://revistas.inpi.gov.br/rpi/)
        # ou da RPI ``numero_da_rpi``. As grafias aceitas do nome da instituição ficam em ``_rpi.GRAFIAS_INSTITUICAO``.
        return importar_revista_recente(PATENTES, options.get('numero_da_rpi'), coluna=7)
