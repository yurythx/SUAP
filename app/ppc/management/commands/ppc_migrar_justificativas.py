from datetime import datetime

import sentry_sdk
import tqdm
from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def migrar_dados_justificativa_planodisciplina(self):
        """
        Cria uma nova revisão para planos de ensino que estejam na situação
        Em Elaboração e migra a informação do attr justificativa para a nova revisão
        """
        PlanoDisciplina = apps.get_model('ppc', 'PlanoDisciplina')
        RevisaoPlanoDisciplina = apps.get_model('ppc', 'RevisaoPlanoDisciplina')

        sucessos, falhas = 0, 0
        planos = PlanoDisciplina.objects.filter(justificativa__isnull=False)
        print(f'Migrando justificativa de {planos.count()} planos de disciplina')
        for plano in tqdm.tqdm(planos):
            try:
                ultima_movimentacao_elaboracao = (
                    plano.movimentacaoplanodisciplina_set.filter(
                        plano_disciplina__situacao=PlanoDisciplina.ELABORACAO, usuario=plano.avaliador.get_vinculo()
                    )
                    .order_by('-data')
                    .first()
                )
                data_da_revisao = ultima_movimentacao_elaboracao and ultima_movimentacao_elaboracao.data or datetime.now()
                vinculo_criador = ultima_movimentacao_elaboracao and ultima_movimentacao_elaboracao.usuario or plano.avaliador.get_vinculo()

                # Criar nova revisão
                numero_revisao = plano.revisaoplanodisciplina_set.count() + 1
                revisao = RevisaoPlanoDisciplina.objects.create(
                    numero_revisao=numero_revisao,
                    plano_disciplina=plano,
                    texto=plano.justificativa,
                    vinculo=vinculo_criador,
                    data_criacao=data_da_revisao,
                    resolvido=False,
                )
                if revisao:
                    sucessos += 1
                else:
                    falhas += 1
                    sentry_sdk.capture_message(f'Erro ao migrar justificativa do Plano de Disciplina id: {plano.id}')
            except Exception as e:
                falhas += 1
                e.message = f'Erro ao migrar justificativa do Plano de Disciplina id: {plano.id}'
                sentry_sdk.capture_exception(e)
        print(f'FIM: {sucessos} Revisões criadas e {falhas} erros na criação da revisão')

    def handle(self, *args, **options):
        self.migrar_dados_justificativa_planodisciplina()
