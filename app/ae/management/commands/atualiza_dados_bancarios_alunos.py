# Executar este comando após a migração 0081

from ae.models import DadosBancarios
from djtools.management.commands import BaseCommandPlus
from rh.models import Banco


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for registro in DadosBancarios.objects.all():
            if registro.banco == DadosBancarios.BANCO_BB:
                codigo = '001'
            elif registro.banco == DadosBancarios.BANCO_CEF:
                codigo = '104'
            elif registro.banco == DadosBancarios.BRADESCO:
                codigo = '237'
            elif registro.banco == DadosBancarios.ITAU:
                codigo = '341'
            elif registro.banco == DadosBancarios.SANTANDER:
                codigo = '033'
            elif registro.banco == DadosBancarios.NORDESTE:
                codigo = '004'

            if Banco.objects.filter(codigo=codigo).exists():
                instituicao = Banco.objects.get(codigo=codigo)
                registro.instituicao = instituicao
                registro.save()
