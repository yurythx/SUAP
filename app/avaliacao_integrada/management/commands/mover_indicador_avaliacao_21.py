from django.db import transaction
from django.db.models import Count

from avaliacao_integrada.models import Avaliacao, Respondente, Resposta
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, **options):
        # Respondente.objects.filter(avaliacao_id=22).update(avaliacao_id=21)
        # qs = Resposta.objects.filter(respondente__avaliacao_id=21)
        #  Resposta.objects.filter(respondente__avaliacao_id=id_avaliacao).values('indicador__macroprocesso__dimensao__eixo__descricao').annotate(quant=Count('id')).values('indicador__macroprocesso__dimensao__eixo__descricao', 'quant')
        #  print(qs_resposta.values('respondente_id').distinct().query)
        #  qs_resposta.values('respondente_id').distinct().count()

        id_avaliacao = 21
        avaliacao = Avaliacao.objects.get(id=id_avaliacao)
        print(f'INICIANDO PROCESSAMENTO DE TRANSFERÊNCIA DE RESPONDENTES REFERENTE A AVALAÇÃO {avaliacao.nome} ...')

        qs_resposta = Resposta.objects.filter(
            respondente__avaliacao_id=id_avaliacao,
            indicador__macroprocesso__dimensao__eixo__descricao__in=('Políticas de Gestão', 'Políticas de desenvolvimento institucional'),
        )
        #                                       , valor__in=('☹️ Discordo',
        #                                                  '😶 Desconheço',
        #                                                  '😃 Concordo',
        #                                                  '🙂 Concordo parcialmente',
        #                                                  '😐 Discordo parcialmente')
        #                                       )
        ids_respondentes = list(qs_resposta.values('respondente_id').annotate(quant=Count('id')).values_list('respondente_id', flat=True))

        # if len(ids_respondentes) == 0:
        #     print(f"{bcolors.WARNING}AVISO: Não há respondente cuja resposta possui emoji. {bcolors.ENDC}")
        #     print('PROCESSAMENTO FINALIZADO, NÃO FAZ NADA!')
        #     return

        print(f'>>> Obtido {len(ids_respondentes)} respondentes da avaliação referente a {qs_resposta.count()} respostas')

        with transaction.atomic():
            nova_avaliacao = None
            nova_avaliacao_nome = '[DESCONSIDERAR] - Autoavaliação Institucional 2023.2'

            if not Avaliacao.objects.filter(nome=nova_avaliacao_nome).exists():
                nova_avaliacao.id = None
                nova_avaliacao.nome = nova_avaliacao_nome
                nova_avaliacao.save()
            else:
                nova_avaliacao = Avaliacao.objects.get(nome=nova_avaliacao_nome)

            print(f'>>> Nova avaliação,  id = {nova_avaliacao.id}, nome = {nova_avaliacao_nome}')
            print(f'>>> Movendo respostas e respondentes da avaliação {avaliacao.nome} para {nova_avaliacao.nome} ...')

            rows_update = 0
            for id_respondente in ids_respondentes:
                novo_respondente = Respondente.objects.get(id=id_respondente)
                novo_respondente.id = None
                novo_respondente.avaliacao_id = nova_avaliacao.id
                novo_respondente.save()

                rows = Resposta.objects.filter(
                    respondente_id=id_respondente,
                    indicador__macroprocesso__dimensao__eixo__descricao__in=('Políticas de Gestão', 'Políticas de desenvolvimento institucional'),
                ).update(respondente_id=novo_respondente.id)
                rows_update = rows_update + rows

            print(f'>>> Movido {len(ids_respondentes)} respondentes, totalizando {rows_update} repostas')

            print('Eixos da avaliação anterior: ')
            print(
                '>>>',
                Resposta.objects.filter(respondente__avaliacao_id=avaliacao.id)
                .values('indicador__macroprocesso__dimensao__eixo__descricao')
                .annotate(quant=Count('id'))
                .values('indicador__macroprocesso__dimensao__eixo__descricao', 'quant'),
            )

            print('Eixos da nova avaliação: ')
            print(
                '>>>',
                Resposta.objects.filter(respondente__avaliacao_id=nova_avaliacao.id)
                .values('indicador__macroprocesso__dimensao__eixo__descricao')
                .annotate(quant=Count('id'))
                .values('indicador__macroprocesso__dimensao__eixo__descricao', 'quant'),
            )
