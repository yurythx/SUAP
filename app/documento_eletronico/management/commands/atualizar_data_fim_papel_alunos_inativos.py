import datetime

from django.apps import apps
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Comando para atualizar a data de fim do papel de alunos inativos no sistema.

    Este comando verifica todos os alunos que possuem papel ativo do tipo discente
    e que não estão mais ativos no sistema (sem matrícula ativa). Para estes alunos,
    atualiza a data_fim do papel para a data atual.

    O comando possui duas opções de execução:
    - SIMULAR: Apenas simula a execução sem realizar alterações no banco de dados
    - EXECUTAR: Realiza as alterações efetivamente no banco de dados

    Ao final da execução, apresenta:
    - Total de alunos processados
    - Total de alunos que tiveram o papel inativado
    - Lista de erros encontrados durante o processamento
    - Percentual de execução
    - Status final do processamento
    """

    def handle(self, *args, **options):
        Papel = apps.get_model('rh', 'Papel')
        Aluno = apps.get_model('edu', 'Aluno')

        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR/ABORTAR) ').strip().upper()

        executar_simulacao = executar_command == 'SIMULAR'
        executar_pra_valer = executar_command == 'EXECUTAR'
        if not executar_simulacao and not executar_pra_valer:
            print()
            print('Processamento abortado.')
            return

        title = 'Doc. Eletrônico - Command para inativar o papel para alunos sem matricula ativa que possuem papel'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        hoje = datetime.date.today()
        alunos_com_papel_ativo = Aluno.objects.filter(
            vinculos__papel__data_inicio__lte=hoje, vinculos__papel__tipo_papel=Papel.TIPO_PAPEL_DISCENTE
        ).exclude(Q(vinculos__papel__data_fim__isnull=False) | Q(vinculos__papel__data_fim__lte=hoje))
        total_alunos = alunos_com_papel_ativo.count()
        counter = 0
        count_erros = 0
        qtd_inativados = 0
        exceptions = {}
        if alunos_com_papel_ativo:
            print()
            print(f'Foram encontrados {alunos_com_papel_ativo.count()} alunos inativos com Papel do Tipo Discente ativo.')
            for aluno in alunos_com_papel_ativo:
                try:
                    print(f'Analisando se o Aluno {aluno.pessoa_fisica.nome} - matricula: {aluno.matricula} esta com situação ativa no SUAP')
                    if not aluno.situacao.ativo:
                        if executar_pra_valer:
                            Papel.objects.filter(vinculo=aluno.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_DISCENTE).update(
                                data_fim=datetime.datetime.now()
                            )
                            qtd_inativados += 1
                            print(f'Inativou papeis do aluno {aluno.pessoa_fisica.nome}')
                    else:
                        print(f'Aluno {aluno.pessoa_fisica.nome} esta ativo')

                    print()
                    counter += 1
                    percentual = counter / float(total_alunos) * 100
                    print(f'{percentual}% executado - {counter} de {total_alunos} alunos')
                except Exception as e:
                    count_erros += 1
                    exceptions[e] = aluno.matricula
                    continue

        else:
            print()
            print('Nenhum aluno inativo com papel de Discente ativo foi encontrado .')
        if exceptions:
            print('HOUVE ERRO NA EXECUÇÃO DOS SEGUINTES ITENS')
            for exception in exceptions:
                print(exception)
        print('Fim do processamento.')
        if not executar_pra_valer:
            print(
                'OBS: Este processamento foi apenas uma SIMULAÇÃO. Nada foi gravado no banco de dados. Para executar '
                'algo em definitivo, realize novamente o processamento e escolha a opção "EXECUTAR".'
            )
