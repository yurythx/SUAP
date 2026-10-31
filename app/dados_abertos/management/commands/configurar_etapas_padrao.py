"""Reconfigura as etapas e ações do PDA para o padrão automático.

Alinha o checklist às condições automáticas: cada marco com evento detectável vira uma ação
obrigatória automática; registros documentais ficam como opcionais manuais. SUBSTITUI a estrutura
existente de Etapa/Acao (as PDAAcao antigas são removidas por cascade e recriadas pelo checklist).

Aplicação é **manual e deliberada**, não por migração: o command apaga a estrutura vigente e, com
ela, o progresso manual das PDAAcao. Rodar é decisão de quem opera o PDA, não efeito colateral de
deploy. As dispensas de etapa (PDAEtapa) são preservadas.

Uso: ``python manage.py configurar_etapas_padrao``. Requer as migrações do app aplicadas.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from dados_abertos.enums import CondicaoAcaoAutomatica as C
from dados_abertos.models import Acao, Etapa, PDAEtapa, PlanoDadosAbertos
from dados_abertos.services.acoes_automaticas_service import sincronizar_acoes_automaticas

ESTRUTURA = [
    {
        'ordem': 1,
        'titulo': 'Grupo de Trabalho',
        'descricao': 'Definição do grupo responsável pela condução do Plano de Dados Abertos.',
        'dispara_analise_lai': False,
        'acoes': [
            {'ordem': 1, 'titulo': 'Definir grupo de trabalho e responsáveis', 'obrigatoria': True, 'condicao': C.GRUPO_TRABALHO_DEFINIDO},
            {'ordem': 2, 'titulo': 'Registrar portaria de designação', 'obrigatoria': False, 'condicao': ''},
        ],
    },
    {
        'ordem': 2,
        'titulo': 'Conjuntos de Dados',
        'descricao': 'Levantamento e catalogação dos conjuntos de dados da instituição no PDA.',
        'dispara_analise_lai': False,
        'acoes': [
            {'ordem': 1, 'titulo': 'Vincular os conjuntos de dados ao PDA', 'obrigatoria': True, 'condicao': C.BASES_VINCULADAS},
            {'ordem': 2, 'titulo': 'Classificar por tema e descrever os conjuntos', 'obrigatoria': False, 'condicao': ''},
        ],
    },
    {
        'ordem': 3,
        'titulo': 'Consulta Pública',
        'descricao': 'Coleta de sugestões e demandas da sociedade sobre os dados a abrir.',
        'dispara_analise_lai': False,
        'pulavel': True,
        'acoes': [
            {'ordem': 1, 'titulo': 'Realizar a consulta pública', 'obrigatoria': True, 'condicao': C.CONSULTA_PUBLICA_REALIZADA},
            {'ordem': 2, 'titulo': 'Elaborar relatório da consulta pública', 'obrigatoria': False, 'condicao': ''},
        ],
    },
    {
        'ordem': 4,
        'titulo': 'Priorização',
        'descricao': 'Definição das bases prioritárias a partir dos critérios e da consulta pública.',
        'dispara_analise_lai': False,
        'acoes': [
            {'ordem': 1, 'titulo': 'Finalizar a matriz de priorização', 'obrigatoria': True, 'condicao': C.MATRIZ_FINALIZADA},
            {'ordem': 2, 'titulo': 'Aprovar a relação final com o grupo de trabalho', 'obrigatoria': False, 'condicao': ''},
        ],
    },
    {
        'ordem': 5,
        'titulo': 'Abertura e Publicação',
        'descricao': 'Abertura efetiva das bases: recurso, deliberação do LAI e sincronização com o CKAN.',
        'dispara_analise_lai': True,
        'acoes': [
            {'ordem': 1, 'titulo': 'Cadastrar recurso em ao menos uma base priorizada', 'obrigatoria': True, 'condicao': C.BASES_COM_RECURSO},
            {'ordem': 2, 'titulo': 'Liberação de ao menos uma base pelo Responsável LAI', 'obrigatoria': True, 'condicao': C.BASES_LIBERADAS_LAI},
            {'ordem': 3, 'titulo': 'Sincronização de ao menos uma base com o CKAN', 'obrigatoria': True, 'condicao': C.BASES_SINCRONIZADAS_CKAN},
        ],
    },
]


def _capturar_dispensas() -> list[dict]:
    """Fotografa as dispensas de etapa antes de as etapas serem recriadas.

    ``PDAEtapa.etapa`` é ``CASCADE``, então apagar as etapas apagaria junto a auditoria da dispensa
    (justificativa, autor, IP) e faria o PDA regredir para a etapa que havia sido dispensada. A
    chave usada é a **ordem** da etapa, não o id, porque os ids mudam na recriação.
    """
    return [
        {
            'pda_id': dispensa.pda_id,
            'ordem': dispensa.etapa.ordem,
            'justificativa': dispensa.justificativa,
            'pulada_por_id': dispensa.pulada_por_id,
            'data_pulada': dispensa.data_pulada,
            'ip': dispensa.ip,
            'user_agent': dispensa.user_agent,
        }
        for dispensa in PDAEtapa.objects.select_related('etapa')
    ]


def _restaurar_dispensas(dispensas: list[dict]) -> int:
    """Recria as dispensas nas etapas equivalentes da nova estrutura.

    Dispensas cuja etapa não existe mais, ou cuja etapa correspondente deixou de ser pulável, são
    descartadas — manter a dispensa de uma etapa obrigatória deixaria o fluxo inconsistente.

    Returns:
        int: Quantidade de dispensas restauradas.
    """
    etapas_por_ordem = {etapa.ordem: etapa for etapa in Etapa.objects.all()}
    restauradas = 0
    for dispensa in dispensas:
        etapa = etapas_por_ordem.get(dispensa['ordem'])
        if not etapa or not etapa.pulavel:
            continue
        nova = PDAEtapa.objects.create(
            pda_id=dispensa['pda_id'],
            etapa=etapa,
            justificativa=dispensa['justificativa'],
            pulada_por_id=dispensa['pulada_por_id'],
            ip=dispensa['ip'],
            user_agent=dispensa['user_agent'],
        )
        # data_pulada é auto_now_add: preserva a data original da dispensa por fora do create.
        PDAEtapa.objects.filter(pk=nova.pk).update(data_pulada=dispensa['data_pulada'])
        restauradas += 1
    return restauradas


class Command(BaseCommand):
    help = 'Reconfigura as etapas/ações do PDA para o padrão automático (substitui a estrutura existente).'

    @transaction.atomic
    def handle(self, *args, **options):
        dispensas = _capturar_dispensas()
        Etapa.objects.all().delete()  # cascade: Acao -> PDAAcao; etapa_atual dos PDAs vira NULL (SET_NULL)

        total_acoes = 0
        for etapa_def in ESTRUTURA:
            etapa = Etapa.objects.create(
                ordem=etapa_def['ordem'],
                titulo=etapa_def['titulo'],
                descricao=etapa_def['descricao'],
                dispara_analise_lai=etapa_def['dispara_analise_lai'],
                pulavel=etapa_def.get('pulavel', False),
            )
            for acao_def in etapa_def['acoes']:
                Acao.objects.create(
                    etapa=etapa,
                    ordem=acao_def['ordem'],
                    titulo=acao_def['titulo'],
                    obrigatoria=acao_def['obrigatoria'],
                    condicao_automatica=acao_def['condicao'],
                )
                total_acoes += 1

        restauradas = _restaurar_dispensas(dispensas)

        # Repovoa o checklist e sincroniza o estado automático de cada PDA existente.
        for pda in PlanoDadosAbertos.objects.all():
            pda.inicializar_checklist()
            sincronizar_acoes_automaticas(pda)
            pda.atualizar_etapa_atual()

        self.stdout.write(self.style.SUCCESS(f'{len(ESTRUTURA)} etapas e {total_acoes} ações configuradas (padrão automático).'))
        if restauradas:
            self.stdout.write(self.style.SUCCESS(f'{restauradas} dispensa(s) de etapa preservada(s).'))
