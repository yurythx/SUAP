from djtools.management.commands import BaseCommandPlus
from rsc.models import ProcessoRSC, TipoRsc


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for processo in ProcessoRSC.objects.all():
            pontuacao = {}
            for tipo_rsc in TipoRsc.objects.all():
                pontuacao_rsc = 0
                for diretriz in tipo_rsc.diretriz_set.all():
                    pontuacao_diretriz = 0
                    for criterio in diretriz.criterio_set.all():
                        arquivos = processo.arquivo_set.filter(criterio=criterio)
                        for arquivo in arquivos:
                            qtd_itens = arquivo.qtd_itens or 0
                            arquivo.nota_pretendida = qtd_itens * criterio.fator * diretriz.peso
                            arquivo.save()
                            pontuacao_diretriz += arquivo.nota_pretendida
                    if pontuacao_diretriz > diretriz.teto:
                        pontuacao_diretriz = diretriz.teto
                    pontuacao_rsc += pontuacao_diretriz
                pontuacao[tipo_rsc.nome] = pontuacao_rsc
            processo.pontuacao_pretendida_rsc1 = pontuacao['RSC-I']
            processo.pontuacao_pretendida_rsc2 = pontuacao['RSC-II']
            processo.pontuacao_pretendida_rsc3 = pontuacao['RSC-III']
            processo.pontuacao_pretendida = (
                processo.pontuacao_pretendida_rsc1 + processo.pontuacao_pretendida_rsc2 + processo.pontuacao_pretendida_rsc3
            )
            processo.save()
