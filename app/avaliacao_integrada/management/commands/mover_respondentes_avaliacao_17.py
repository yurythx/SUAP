from django.db import transaction
from django.db.models import Count

from avaliacao_integrada.models import Avaliacao, Respondente, Resposta
from djtools.management.commands import BaseCommandPlus, bcolors


class Command(BaseCommandPlus):
    def handle(self, **options):
        print('INICIANDO PROCESSAMENTO DE TRANSFERÊNCIA DE RESPONDENTES ...')
        qs_resposta = Resposta.objects.filter(
            respondente__avaliacao_id=17,
            valor__in=('☹️ Discordo', '😶 Desconheço', '😃 Concordo', '🙂 Concordo parcialmente', '😐 Discordo parcialmente'),
        )
        qs_resposta.values('respondente_id').annotate(quant=Count('id')).values('respondente_id', 'quant')
        ids_respondentes = list(qs_resposta.values('respondente_id').annotate(quant=Count('id')).values_list('respondente_id', flat=True))

        if len(ids_respondentes) == 0:
            print(f'{bcolors.WARNING}AVISO: Não há respondente cuja resposta possui emoji. {bcolors.ENDC}')
            print('PROCESSAMENTO FINALIZADO, NÃO FAZ NADA!')
            return

        print(f'>>> Obitdo {len(ids_respondentes)} respondentes da avaliação com emoji.')

        nova_avaliacao = None
        with transaction.atomic():
            avaliacao_anterior_id = 17
            avaliacao = Avaliacao.objects.get(id=avaliacao_anterior_id)
            avaliacao.nome = '[DESCONSIDERAR] - Autoavaliação Institucional 2023.1'
            avaliacao.save()

            print(f'>>> Avaliação de id {avaliacao_anterior_id}, nome = "[DESCONSIDERAR] - Autoavaliação Institucional 2023.1" ')

            qs_nova_avaliacao = Avaliacao.objects.filter(nome__icontains='[FASE VALIDAÇÃO]')
            if not qs_nova_avaliacao.exists():
                nova_avaliacao = avaliacao
                nova_avaliacao.id = None
                nova_avaliacao.nome = '[FASE VALIDAÇÃO] - Autoavaliação Institucional 2023.1'
                nova_avaliacao.save()
            else:
                nova_avaliacao = qs_nova_avaliacao.first()

            print(f'>>> Criado nova avaliação, id {nova_avaliacao.id}, nome = "[FASE VALIDAÇÃO] - Autoavaliação Institucional 2023.1"')

            Respondente.objects.filter(id__in=ids_respondentes).update(avaliacao_id=nova_avaliacao.id)
            print(
                f'>>> Movido {len(ids_respondentes)} respondentes e seus respectivos questionários da avaliação {avaliacao_anterior_id} para a nova cuso id = {nova_avaliacao.id}'
            )
            print('FIM')
