from djtools.management.commands import BaseCommandPlus
from edu.models import Componente, ComponenteCurricular, AtividadeCurricularExtensao, AtividadeCurricularExtensaoExtra
from django.db.models import F


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        Componente.objects.update(ch_hora_relogio=F('ch_hora_relogio') / 100)
        Componente.objects.update(ch_hora_aula=F('ch_hora_aula') / 100)
        ComponenteCurricular.objects.update(ch_presencial=F('ch_presencial') / 100)
        ComponenteCurricular.objects.update(ch_pratica=F('ch_pratica') / 100)
        ComponenteCurricular.objects.update(ch_extensao=F('ch_extensao') / 100)
        ComponenteCurricular.objects.update(ch_pcc=F('ch_pcc') / 100)
        ComponenteCurricular.objects.update(ch_visita_tecnica=F('ch_visita_tecnica') / 100)
        AtividadeCurricularExtensao.objects.update(carga_horaria_vinculada=F('carga_horaria_vinculada') / 100)
        AtividadeCurricularExtensao.objects.update(carga_horaria=F('carga_horaria') / 100)
        AtividadeCurricularExtensaoExtra.objects.update(carga_horaria=F('carga_horaria') / 100)
