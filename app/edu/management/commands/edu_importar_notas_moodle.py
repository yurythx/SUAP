from datetime import date, timedelta

from tqdm import tqdm
from json import JSONDecodeError
from comum.models import APIExterna
from djtools.management.commands import BaseCommandPlus
from edu.models import TurmaMinicurso


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = date.today()
        limite = hoje - timedelta(days=7)
        qs = TurmaMinicurso.objects.filter(minicurso__autoinstrucional=True, data_inicio__lte=hoje, data_fim__gte=limite)
        moodle = APIExterna.MOODLE.get_service()
        if not moodle.estah_acessivel():
            self.stderr.write('Serviço Moodle inacessível no momento.')
            return
        for obj in tqdm(qs):
            try:
                moodle.importar_notas_turma_minicurso(obj, '')
            except JSONDecodeError:
                pass
