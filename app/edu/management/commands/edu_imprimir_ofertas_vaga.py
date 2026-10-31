from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno
from processo_seletivo.models import OfertaVaga


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        ofertas_vaga = (
            OfertaVaga.objects.exclude(curso_campus__estrutura__proitec=True)
            .filter(edital__ano__ano__gte=2017)
            .order_by('edital', 'curso_campus', 'lista')
        )
        print('ANO\tPERÍODO\tEDITAL\tCURSO\tTURNO\tLISTA\tFORMA DE INGRESSO\tQTD OFERTADA\tQTD MATRICULADOS\tDIFERENÇA')
        for oferta_vaga in ofertas_vaga:
            qs = Aluno.objects.filter(
                ano_letivo=oferta_vaga.edital.ano, periodo_letivo=oferta_vaga.edital.semestre, curso_campus=oferta_vaga.curso_campus
            )
            if oferta_vaga.turno:
                qs = qs.filter(turno=oferta_vaga.turno)
            qs = qs.filter(forma_ingresso=oferta_vaga.lista.forma_ingresso)
            qtd = qs.count()
            lista = [
                oferta_vaga.edital.ano.ano,
                oferta_vaga.edital.semestre,
                oferta_vaga.edital,
                oferta_vaga.curso_campus.descricao_historico,
                oferta_vaga.turno or '',
                oferta_vaga.lista,
                oferta_vaga.lista.forma_ingresso,
                oferta_vaga.qtd,
                qtd,
                qtd - oferta_vaga.qtd,
            ]
            print('\t'.join(str(x) for x in lista))
