from avaliacao_integrada.models import Segmento
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Aplica migração de dados para Segmento.'

    def handle(self, *args, **options):
        Segmento.objects.get_or_create(descricao='Profissional Prestador de Serviço', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
        Segmento.objects.get_or_create(descricao='Supervisor de Estágio', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)

        Segmento.objects.filter(id=Segmento.DESLIGADO, descricao='Desligado').update(descricao='Evadidos/Jubilados')
        Segmento.objects.filter(id=Segmento.PAIS, descricao='Pais').update(descricao='Pais e/ou Responsável')
        Segmento.objects.filter(id=Segmento.ALUNO_EGRESSO, descricao='Egresso').update(descricao='Aluno Egresso')
        Segmento.objects.filter(id=Segmento.EMPRESA_PRESTADORA_SERVICO, descricao='Empresas').update(descricao='Empresa Prestadora de Serviço')
        Segmento.objects.filter(id=Segmento.OUTRO_SOCIEDADE_CIVIL, descricao='Sociedade Civil').update(
            descricao='Demais segmentos da sociedade civil'
        )

        Segmento.objects.filter(id__in=Segmento.SOCIEDADE_CIVIL).update(tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
