from chaves.models import Movimentacao
from comum.models import Vinculo
from djtools.assincrono import task
from ponto.models import MaquinaLog
from rh.models import PessoaFisica


def _vinculo_id(id_terminal: str) -> int | None:
    """Vínculo da pessoa que o terminal de chaves registrou (id da sua tabela ``pessoa``)."""
    if not id_terminal:
        return None
    return (Vinculo.objects.do_terminal(id_terminal) or PessoaFisica.objects.get(pk=id_terminal).get_vinculo()).id


@task('Inserir Movimentação')
def inserir_movimentacoes(maquina, dados, task=None):
    novas = 0
    alteradas = 0
    erros = []
    for registro in task.iterate(dados.split('\n')):
        try:
            if registro:
                registros = registro.replace('\tnull', '\t').split('\t')
                terminal_antigo = len(registros) == 9
                if terminal_antigo:
                    (
                        chave_id,
                        operador_emprestimo_id,
                        pessoa_emprestimo_id,
                        data_emprestimo,
                        observacao_emprestimo,
                        operador_devolucao_id,
                        pessoa_devolucao_id,
                        data_devolucao,
                        observacao_devolucao,
                    ) = registros
                else:
                    (
                        _movimentacao_id,
                        chave_id,
                        operador_emprestimo_id,
                        pessoa_emprestimo_id,
                        data_emprestimo,
                        observacao_emprestimo,
                        operador_devolucao_id,
                        pessoa_devolucao_id,
                        data_devolucao,
                        observacao_devolucao,
                    ) = registros
                data_emprestimo = data_emprestimo or None
                operador_emprestimo_id = _vinculo_id(operador_emprestimo_id)
                vinculo_emprestimo_id = _vinculo_id(pessoa_emprestimo_id)

                data_devolucao = data_devolucao or None
                operador_devolucao_id = _vinculo_id(operador_devolucao_id)
                vinculo_devolucao_id = _vinculo_id(pessoa_devolucao_id)

                if data_devolucao:
                    Movimentacao.objects.filter(chave_id=chave_id, data_devolucao=data_devolucao).update(data_devolucao=None)

                # empréstimo e devolução
                _movimentacao, novo = Movimentacao.objects.update_or_create(
                    chave_id=chave_id,
                    data_emprestimo=data_emprestimo,
                    defaults={
                        'data_devolucao': data_devolucao,
                        'operador_emprestimo_id': operador_emprestimo_id,
                        'vinculo_emprestimo_id': vinculo_emprestimo_id,
                        'observacao_emprestimo': observacao_emprestimo,
                        'operador_devolucao_id': operador_devolucao_id,
                        'vinculo_devolucao_id': vinculo_devolucao_id,
                        'observacao_devolucao': observacao_devolucao,
                    },
                )

                if novo:
                    novas += 1
                else:
                    alteradas += 1
        except Exception as e:
            erros.append(f'O registro "{registro}" provocou o seguinte erro: {e!s}')
    if erros:
        msg = 'Erro ao executar tarefa. Detalhes: {}'.format('\n'.join(erros))
        MaquinaLog.objects.create(maquina=maquina, operacao='importar_emprestimos', status=MaquinaLog.ERRO, mensagem=msg)
        task.finalize(msg, error=True)
    else:
        msg = f'Tarefa executada com sucesso. Detalhes: {novas} movimentações criadas e {alteradas} movimentações alteradas.'
        MaquinaLog.objects.create(maquina=maquina, operacao='importar_emprestimos', mensagem=msg)
        task.finalize(msg)
