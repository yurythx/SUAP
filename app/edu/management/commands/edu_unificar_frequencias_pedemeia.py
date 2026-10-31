from djtools.management.commands import BaseCommandPlus
from tqdm import tqdm
from edu.models import MatriculaPeriodo, FrequenciaPeDeMeia


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = MatriculaPeriodo.objects.filter(codigo_sgp__isnull=False, ano_letivo__ano=2024)
        for matricula_periodo in tqdm(qs):
            for requisicao in matricula_periodo.aluno.get_frequencias_pedemeia_ultima_atualizacao():
                frequencia = (
                    FrequenciaPeDeMeia.objects.filter(matricula_periodo=matricula_periodo, ano=requisicao.ano, mes=requisicao.mes).first()
                    or FrequenciaPeDeMeia()
                )
                frequencia.matricula_periodo = matricula_periodo
                frequencia.ano = requisicao.ano
                frequencia.mes = requisicao.mes
                frequencia.qtd_horas_ofertadas = requisicao.registro_serializado.get('hlOfertadaPeriodo', 0)
                frequencia.qtd_horas_presentes = requisicao.registro_serializado.get('hlPresentePeriodo', 0)
                frequencia.qtd_horas_ausentes = frequencia.qtd_horas_ofertadas - frequencia.qtd_horas_presentes
                frequencia.save()
                frequencia.aulas.set(requisicao.aulas.values_list('id', flat=True))
                frequencia.faltas.set(requisicao.faltas.values_list('id', flat=True))
                frequencia.praticas_profissionais.set(requisicao.praticas_profissionais.values_list('id', flat=True))
