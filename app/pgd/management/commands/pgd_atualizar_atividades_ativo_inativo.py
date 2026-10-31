from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # Model Atividade
        # - O campo ativo servirá apenas para gerenciar a solicitação de cadastro de uma nova atividade
        #   - ativo
        # Para saber se atividade está ativa ou não deve-se observar a data de efeitos de inativação
        #   - data_inativacao_efeitos_a_partir_de
        import datetime

        from pgd.utils import get_datetime_now

        Atividade = apps.get_model('pgd', 'Atividade')
        PlanoTrabalhoSetorialAtividades = apps.get_model('pgd', 'PlanoTrabalhoSetorialAtividades')

        hoje = get_datetime_now()
        data_inativacao_efeitos_a_partir_de = datetime.date(hoje.year, hoje.month, 1)

        # Inativando atividades no QTA
        Atividade.objects.filter(ativo=False).update(data_inativacao_efeitos_a_partir_de=data_inativacao_efeitos_a_partir_de)

        # Inativando atividades do PTSs
        PlanoTrabalhoSetorialAtividades.objects.filter(atividade__in=Atividade.objects.filter(ativo=False).values_list('id', flat=True)).update(
            ativo=False
        )
