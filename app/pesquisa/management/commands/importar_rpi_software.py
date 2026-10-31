from typing import Any

from djtools.management.commands import BaseCommandPlus
from pesquisa.management.commands._rpi import LEIAUTE_SOFTWARE, Importacao, importar_revista_recente

SOFTWARES = Importacao(
    tipo='Software',
    prefixo='PC',
    leiaute=LEIAUTE_SOFTWARE,
    baixar_sempre=False,
    ler_pelo_nome_do_zip=True,
    reler_em_latin1=True,
    despacho_por_codigo=True,
)


class Command(BaseCommandPlus):
    def handle(self, *args: Any, **options: Any) -> int | str | None:
        # Importa os registros de programas de computador da instituição e seus despachos da última RPI de softwares do INPI
        # (http://revistas.inpi.gov.br/rpi/) ou da RPI ``numero_da_rpi``.
        return importar_revista_recente(SOFTWARES, options.get('numero_da_rpi'), coluna=8)
