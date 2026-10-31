from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa
from catalogo_provedor_servico.providers.base import Etapa
from catalogo_provedor_servico.providers.impl.ifrn.codes import (
    ID_GOVBR_6176_MATRICULA_EAD,
    ID_GOVBR_6410_MATRICULA_CURSO_NIVEL_TECNICO_IFRN,
    ID_GOVBR_6424_MATRICULA_CURSO_NIVEL_SUPERIOR_IFRN,
)
from edu.models import Aluno
from processo_seletivo.models import CandidatoVaga


class Command(BaseCommand):
    def handle(self, *args, **options):
        title = 'Catálogo Provedor de Serviços - Command "Preencher o campo email_responsavel no aluno"'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print()
        print(
            'O objetivo deste command eh varrer todas as solicitacoes de servico de matrícula e verificar\n'
            'se existe valor no  atributo email_responsavel e caso positivo atualizar no aluno se não possuir este campo".'
        )

        executar_command = input('Deseja continuar (S/N)?').strip().upper() == 'S'
        if not executar_command:
            print('Processamento abortado!')
            return

        solicitacoes = Solicitacao.objects.filter(
            servico__id_servico_portal_govbr__in=[
                ID_GOVBR_6176_MATRICULA_EAD,
                ID_GOVBR_6410_MATRICULA_CURSO_NIVEL_TECNICO_IFRN,
                ID_GOVBR_6424_MATRICULA_CURSO_NIVEL_SUPERIOR_IFRN,
            ],
            status=Solicitacao.STATUS_ATENDIDO,
        )
        print(f'Verificando {solicitacoes.count()} solicitações atendidas.')
        if solicitacoes.exists():
            atualizados = 0
            for solicitacao in solicitacoes:
                candidato_vaga_id, email_responsavel_solicitacao = None, None
                solicitacao_etapa_1 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1)
                if solicitacao_etapa_1:
                    solicitacao_etapa_1 = solicitacao_etapa_1.first()
                    etapa_1 = Etapa.load_from_json(solicitacao_etapa_1.get_dados_as_json())
                    candidato_vaga_id = etapa_1.formulario.get_value('candidato_vaga')

                if solicitacao_etapa_2 := SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=2):
                    solicitacao_etapa_2 = solicitacao_etapa_2.first()
                    etapa_2 = Etapa.load_from_json(solicitacao_etapa_2.get_dados_as_json())
                    email_responsavel_solicitacao = etapa_2.formulario.get_value('email_responsavel')

                if candidato_vaga_id and email_responsavel_solicitacao:
                    try:
                        candidato_vaga = CandidatoVaga.objects.get(id=candidato_vaga_id)

                        aluno = Aluno.objects.get(candidato_vaga=candidato_vaga)

                        if not aluno.email_responsavel and email_responsavel_solicitacao:
                            Aluno.objects.filter(candidato_vaga=candidato_vaga).update(email_responsavel=email_responsavel_solicitacao)
                            atualizados += 1

                    except CandidatoVaga.DoesNotExist:
                        print(f'Erro: Nenhum candidato vaga encontrado para o id "{candidato_vaga_id}"')
                    except Aluno.DoesNotExist:
                        print(f'Erro: Nenhum aluno encontrado para o candidato vaga de id "{candidato_vaga_id}"')
                    except Aluno.MultipleObjectsReturned:
                        print(f'Erro: Vários alunos encontrados para o candidato vaga de id "{candidato_vaga_id}"')

        print(f'Foram atualizados o email_resposavel para {atualizados} Alunos')
        print('FIM')
