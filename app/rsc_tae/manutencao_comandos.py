"""Allowlist dos management commands executáveis pela tela de manutenção (/rsc_tae/manutencao/).

Só os commands listados aqui podem ser executados pela tela. Cada entrada tem:

    chave     - referência opaca usada na interface (é o que vai para o HTML/select). NÃO expõe
                o nome real do management command.
    nome      - nome real do management command (usado apenas no servidor, nunca renderizado).
    label     - rótulo amigável exibido ao usuário.
    descricao - descrição/exemplo de uso.

Para liberar um novo command, adicione uma entrada manualmente. A tela nunca executa (nem expõe)
um nome que não esteja aqui.
"""

COMANDOS_MANUTENCAO = [
    {
        'chave': 'reverter-deliberacao',
        'nome': 'reverter_deliberacao_final',
        'label': 'Reverter deliberação final',
        'descricao': (
            'Reverte um processo finalizado para AGUARDANDO_CRSC. '
            'Ex.: "1 --membro-matricula 1234" (sem --commit = simulação; adicione --commit para aplicar).'
        ),
    },
    {
        'chave': 'reabrir-deliberacao-item',
        'nome': 'reverter_deliberacao_item',
        'label': 'Reabrir deliberação de item (divergência)',
        'descricao': (
            'Remove o voto de item de um membro em processo que está em deliberação da CRSC, reabrindo o item para nova votação. '
            'Ex.: "1 --anexo 11473 --membro-matricula 1234" (sem --commit = simulação; adicione --commit para aplicar). '
            'Para desfazer só o voto de desempate do presidente, sem que os membros revotem, acrescente --somente-desempate.'
        ),
    },
    {
        'chave': 'alterar-situacao',
        'nome': 'alterar_situacao_processo',
        'label': 'Alterar situação do processo',
        'descricao': (
            'Move o processo para outra situação válida gravando o histórico — é o registro que devolve o processo à '
            'posição correta da fila da etapa. Ex.: "601 --listar" mostra os destinos válidos; '
            '"601 --para aguardando-crsc --motivo \'...\'" simula e, com --commit, aplica. '
            'Deferir/indeferir não sai daqui: isso é a deliberação da CRSC.'
        ),
    },
    {
        'chave': 'remover-avaliador',
        'nome': 'remover_avaliador_processo',
        'label': 'Remover avaliador do processo',
        'descricao': (
            'Remove avaliador designado indevidamente, marcando a avaliação como substituída, apagando as avaliações de '
            'anexo dele e registrando a auditoria. Ex.: "601 --listar"; '
            '"601 --avaliador-matricula 1234 --motivo \'...\' --commit". '
            'Exige que restem três avaliadores — para trocar um por outro, use "Remanejar avaliador".'
        ),
    },
]


def comando_por_chave(chave: str) -> dict | None:
    """Retorna a entrada da allowlist cuja ``chave`` bate, ou ``None``."""
    return next((comando for comando in COMANDOS_MANUTENCAO if comando['chave'] == chave), None)


def label_por_nome(nome: str) -> str:
    """Rótulo amigável para um ``nome`` de command já executado (histórico). Fallback: '(comando removido)'."""
    entrada = next((comando for comando in COMANDOS_MANUTENCAO if comando['nome'] == nome), None)
    return entrada['label'] if entrada else '(comando removido)'
