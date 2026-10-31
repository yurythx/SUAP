from typing import Any

from djtools.management.commands import BaseCommandPlus
from pesquisa.management.commands._rpi import LEIAUTE_SOFTWARE_ANTIGO, Importacao, importar_historico

SOFTWARES_EM_REVISTAS_DE_PATENTES = Importacao(
    tipo='Software',
    prefixo='P',
    leiaute=LEIAUTE_SOFTWARE_ANTIGO,
    baixar_sempre=False,
    ler_pelo_nome_do_zip=False,
    reler_em_latin1=True,
    despacho_por_codigo=True,
)


class Command(BaseCommandPlus):
    def handle(self, *args: Any, **options: Any) -> None:
        # Importa os registros de programas de computador da instituição publicados nas RPI de patentes do INPI
        # (http://revistas.inpi.gov.br/rpi/): da 2139, a mais antiga, até a 2403, a última que ainda trazia os softwares junto.
        importar_historico(SOFTWARES_EM_REVISTAS_DE_PATENTES, inicio=2139, fim=2403)
