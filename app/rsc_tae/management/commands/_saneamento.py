"""Peças comuns aos management commands de saneamento do RSC-TAE.

O nome começa com ``_`` de propósito: o Django só descobre commands em módulos que não
começam com underscore, então este arquivo é biblioteca, não comando.

Reúne o que ``alterar_situacao_processo`` e ``remover_avaliador_processo`` repetiriam:
a resolução do processo e do responsável, os argumentos comuns e a sentinela de rollback
que implementa o modo simulação (padrão dos commands já existentes no módulo).
"""

from __future__ import annotations

from django.core.management.base import CommandError

from comum.models import Vinculo
from rsc_tae.models import ProcessoRSCTae


class Rollback(Exception):
    """Sentinela para forçar rollback da transação em modo simulação."""


def adicionar_argumentos_comuns(parser) -> None:
    """Argumentos que os dois commands de saneamento compartilham."""
    parser.add_argument(
        '--motivo',
        dest='motivo',
        help='Justificativa do ato. Obrigatório para aplicar; fica registrado para auditoria.',
    )
    parser.add_argument(
        '--responsavel-vinculo',
        type=int,
        dest='responsavel_vinculo',
        help='ID do Vinculo de quem responde pelo ato (fica registrado). Alternativa a --responsavel-matricula.',
    )
    parser.add_argument(
        '--responsavel-matricula',
        dest='responsavel_matricula',
        help='Matrícula de quem responde pelo ato. Alternativa a --responsavel-vinculo.',
    )
    parser.add_argument(
        '--commit',
        action='store_true',
        help='Aplica as alterações. Sem esta flag, o comando apenas simula (rollback ao final).',
    )


def get_processo(processo_id: int) -> ProcessoRSCTae:
    """Processo pelo id, com os relacionamentos que as mensagens usam. ``CommandError`` se não existir."""
    processo = ProcessoRSCTae.objects.filter(pk=processo_id).select_related('vinculo__pessoa', 'nivel_requisitado').first()
    if processo is None:
        raise CommandError(f'ProcessoRSCTae #{processo_id} não encontrado.')
    return processo


def get_vinculo_por_matricula(matricula: str) -> Vinculo:
    """Vínculo DAQUELA matrícula. ``CommandError`` quando não existe.

    A busca parte do relacionamento do próprio vínculo, e não da pessoa: quem tem duas
    matrículas (o técnico-administrativo que também é docente, por exemplo) tem dois vínculos
    ligados à mesma pessoa, e um filtro por ``pessoa__pessoafisica__servidor_set__matricula``
    alcança os DOIS a partir de QUALQUER uma das matrículas — o vínculo escolhido sairia ao
    acaso. Num comando cujo produto é um registro auditável, isso gravaria a pessoa certa com
    o vínculo errado.
    """
    from rh.models import Servidor

    vinculo = Vinculo.objects.filter(
        tipo_relacionamento__app_label='rh',
        tipo_relacionamento__model='servidor',
        id_relacionamento__in=Servidor.objects.filter(matricula=matricula).values('id'),
    ).first()
    if vinculo is None:
        raise CommandError(f'Nenhum servidor com a matrícula {matricula} foi encontrado.')
    return vinculo


def get_responsavel(vinculo_id: int | None, matricula: str | None) -> Vinculo | None:
    """Vínculo de quem responde pelo ato, por id ou matrícula. ``None`` quando não informado."""
    if vinculo_id:
        responsavel = Vinculo.objects.filter(pk=vinculo_id).first()
        if responsavel is None:
            raise CommandError(f'Vinculo responsável #{vinculo_id} não encontrado.')
        return responsavel
    if matricula:
        return get_vinculo_por_matricula(matricula)
    return None


def exigir_motivo(motivo: str | None) -> str:
    """Motivo obrigatório e não vazio. ``CommandError`` explicando a flag quando falta."""
    motivo = (motivo or '').strip()
    if not motivo:
        raise CommandError('Informe a justificativa do ato em --motivo (ela fica registrada para auditoria).')
    return motivo
