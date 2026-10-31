from djtools.management.commands import BaseCommandPlus
from edu import pedemeia
from comum.models import Ano


class Command(BaseCommandPlus):
    def check(self, *args, **kwargs):
        pass

    def check_migrations(self, *args, **kwargs):
        pass

    def handle(self, *args, **options):
        periodos = [(2025, 4)]
        pedemeia.consultar_unidades_sgp()
        pedemeia.consultar_alunos_sgp()
        pedemeia.consultar_alunos_sgp(False)
        pedemeia.consultar_alunos_suap()
        for ano, mes in periodos:
            ano_letivo = Ano.objects.get(ano=ano)
            pedemeia.consultar_frequencia_suap(ano_letivo=ano_letivo, mes=mes)
        for ano, mes in periodos:
            ano_letivo = Ano.objects.get(ano=ano)
            pedemeia.consultar_frequencia_sgp(ano_letivo=ano_letivo, mes=mes)
        for ano, mes in periodos:
            ano_letivo = Ano.objects.get(ano=ano)
            pedemeia.calcular_frequencia_suap(ano_letivo=ano_letivo, mes=mes)
        pedemeia.gerar_relatorio_frequencias(periodos)
