from typing import Any

from djtools.management.commands import BaseCommandPlus
from pesquisa.management.commands._rpi import LEIAUTE_SOFTWARE, Importacao, importar_historico

SOFTWARES_HISTORICO = Importacao(
    tipo='Software',
    prefixo='PC',
    leiaute=LEIAUTE_SOFTWARE,
    baixar_sempre=False,
    ler_pelo_nome_do_zip=True,
    reler_em_latin1=True,
    despacho_por_codigo=True,
)


class Command(BaseCommandPlus):
    def handle(self, *args: Any, **options: Any) -> None:
        # Importa todos os registros de programas de computador da instituição e seus despachos das RPI de softwares do INPI
        # (http://revistas.inpi.gov.br/rpi/). A 2404 é a primeira revista de softwares e não deve ser alterada; ``fim`` é a última.
        importar_historico(SOFTWARES_HISTORICO, inicio=2404, fim=2771)
