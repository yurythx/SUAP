from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa
from catalogo_provedor_servico.providers.base import Etapa
from catalogo_provedor_servico.providers.impl.ifrn.codes import ID_GOVBR_6176_MATRICULA_EAD
from edu.models import Aluno
from processo_seletivo.models import CandidatoVaga


class Command(BaseCommand):
    def handle(self, *args, **options):
        PROCESSAR_S0MENTE_SOLICITACAOES_SEM_DADOS_REGISTRO_EXECUCAO = True

        title = 'Catálogo Provedor de Serviços - Command "matricula_ead_preencher_dados_registros_execucao"'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print()
        print(
            'O objetivo deste command eh varrer todas as solicitacoes de servico do tipo Matrícula EAD (6176) e preencher\n'
            'o atributo "dados_registros_execucao".'
        )
        print('Parametros:')
        print(
            '- PROCESSAR_S0MENTE_SOLICITACAOES_SEM_DADOS_REGISTRO_EXECUCAO: {}'.format(
                'Sim' if PROCESSAR_S0MENTE_SOLICITACAOES_SEM_DADOS_REGISTRO_EXECUCAO else 'Nao'
            )
        )
        print()

        executar_command = input('Deseja continuar (S/N)?').strip().upper() == 'S'
        if not executar_command:
            print('Processamento abortado!')
            return

        solicitacoes = Solicitacao.objects.filter(servico__id_servico_portal_govbr=ID_GOVBR_6176_MATRICULA_EAD, status=Solicitacao.STATUS_ATENDIDO)
        if PROCESSAR_S0MENTE_SOLICITACAOES_SEM_DADOS_REGISTRO_EXECUCAO:
            solicitacoes = solicitacoes.filter(dados_registros_execucao__isnull=PROCESSAR_S0MENTE_SOLICITACAOES_SEM_DADOS_REGISTRO_EXECUCAO)

        if solicitacoes.exists():
            for solicitacao in solicitacoes:
                solicitacao_etapa_1 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1)
                if solicitacao_etapa_1:
                    solicitacao_etapa_1 = solicitacao_etapa_1.first()
                    etapa_1 = Etapa.load_from_json(solicitacao_etapa_1.get_dados_as_json())
                    candidato_vaga_id = etapa_1.formulario.get_value('candidato_vaga')

                    try:
                        candidato_vaga = CandidatoVaga.objects.get(id=candidato_vaga_id)

                        aluno = Aluno.objects.get(candidato_vaga=candidato_vaga)
                        solicitacao.add_dado_registro_execucao(model_object=aluno, operation='CREATE', registered_on=aluno.data_matricula)
                        solicitacao.add_dado_registro_execucao(model_object=candidato_vaga, operation='UPDATE', registered_on=aluno.data_matricula)

                        for aluno_arquivo in aluno.alunoarquivo_set.all().order_by('id'):
                            solicitacao.add_dado_registro_execucao(model_object=aluno_arquivo, operation='CREATE', registered_on=aluno.data_matricula)

                        solicitacao.processar_add_dados_registros_execucao_cache()
                        # A atualização ocorrerá direta no banco porque o save() não permite mexer nos registros depois
                        # que um status definitivo é alcançado.
                        Solicitacao.objects.filter(id=solicitacao.id).update(dados_registros_execucao=solicitacao.dados_registros_execucao)
                    except CandidatoVaga.DoesNotExist:
                        print(f'Erro: Nenhum candidato vaga encontrado para o id "{candidato_vaga_id}"')
                    except Aluno.DoesNotExist:
                        print(f'Erro: Nenhum aluno encontrado para o candidato vaga de id "{candidato_vaga_id}"')
                    except Aluno.MultipleObjectsReturned:
                        print(f'Erro: Vários alunos encontrados para o candidato vaga de id "{candidato_vaga_id}"')

        print('FIM')
