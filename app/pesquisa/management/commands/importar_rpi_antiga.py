from typing import Any

from djtools.management.commands import BaseCommandPlus
from pesquisa.management.commands._rpi import LEIAUTE_PATENTE, Importacao, importar_historico

PATENTES_HISTORICO = Importacao(
    tipo='Patente',
    prefixo='P',
    leiaute=LEIAUTE_PATENTE,
    baixar_sempre=True,
    ler_pelo_nome_do_zip=False,
    reler_em_latin1=True,
    despacho_por_codigo=False,
)


class Command(BaseCommandPlus):
    def handle(self, *args: Any, **options: Any) -> None:
        # Importa todos os registros de patentes da instituição e seus despachos das RPI 2139 a 2756 do INPI
        # (http://revistas.inpi.gov.br/rpi/), com a segunda passada de despachos retroativos (ver ``_rpi.importar_historico``).
        importar_historico(PATENTES_HISTORICO, inicio=2139, fim=2756, criar_pasta_na_releitura=True)
