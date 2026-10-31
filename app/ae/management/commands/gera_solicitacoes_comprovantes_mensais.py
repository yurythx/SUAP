import datetime

import tqdm
from django.db.models import Q

from ae.models import ComprovanteParticipacao, Participacao, Programa
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        JANEIRO = 1
        FEVEREIRO = 2
        MARCO = 3
        ABRIL = 4
        MAIO = 5
        JUNHO = 6
        JULHO = 7
        AGOSTO = 8
        SETEMBRO = 9
        OUTUBRO = 10
        NOVEMBRO = 11
        DEZEMBRO = 12
        Meses_CHOICES = [
            [JANEIRO, 'Janeiro'],
            [FEVEREIRO, 'Fevereiro'],
            [MARCO, 'Março'],
            [ABRIL, 'Abril'],
            [MAIO, 'Maio'],
            [JUNHO, 'Junho'],
            [JULHO, 'Julho'],
            [AGOSTO, 'Agosto'],
            [SETEMBRO, 'Setembro'],
            [OUTUBRO, 'Outubro'],
            [NOVEMBRO, 'Novembro'],
            [DEZEMBRO, 'Dezembro'],
        ]
        mes_atual = datetime.datetime.now().month
        ano_atual = datetime.datetime.now().year
        if mes_atual == 1:
            mes = 12
            ano = ano_atual - 1
        else:
            mes = mes_atual - 1
            ano = ano_atual
        mes_pendencia = dict(Meses_CHOICES)[mes]
        if not ComprovanteParticipacao.objects.filter(ano=ano, mes=mes_pendencia).exists():
            data_inicio_participacoes_validas = datetime.date(ano_atual, mes_atual, 1)
            for programa in Programa.objects.filter(Q(exige_comprovante_pagamento=True) | Q(exige_folha_frequencia=True)):
                for participacao in tqdm.tqdm(
                    Participacao.objects.filter(programa=programa).filter(
                        Q(data_inicio__lt=data_inicio_participacoes_validas),
                        Q(data_termino__gte=data_inicio_participacoes_validas) | Q(data_termino__isnull=True),
                    )
                ):
                    if programa.exige_comprovante_pagamento:
                        ComprovanteParticipacao.objects.update_or_create(
                            aluno=participacao.aluno,
                            campus=programa.instituicao,
                            programa=programa,
                            participacao=participacao,
                            tipo=ComprovanteParticipacao.TIPO_PAGAMENTO,
                            mes=mes_pendencia,
                            ano=ano,
                        )
                    if programa.exige_folha_frequencia:
                        ComprovanteParticipacao.objects.update_or_create(
                            aluno=participacao.aluno,
                            programa=programa,
                            campus=programa.instituicao,
                            participacao=participacao,
                            tipo=ComprovanteParticipacao.TIPO_FOLHA_FREQUENCIA,
                            mes=mes_pendencia,
                            ano=ano,
                        )

        dicionario = dict(Meses_CHOICES)
        indices = dict(zip(dicionario.values(), dicionario.keys(), strict=False))
        for pendencia in ComprovanteParticipacao.objects.filter(pendente=True, participacao__data_termino__isnull=False):
            mes_apontado = indices[pendencia.mes]
            if pendencia.participacao.data_termino < datetime.date(pendencia.ano, mes_apontado, 1):
                pendencia.delete()
