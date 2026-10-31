from django.core.management.base import BaseCommand

from edu.models.diarios import ConfiguracaoAvaliacao, Diario, ItemConfiguracaoAvaliacao, NotaAvaliacao


"""
Exemplo de execução

python manage.py edu_gerar_recuperacao 2 2024

sendo
2 - periodo letivo
2024 - ano letivo
"""


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('periodo_letivo', type=int, help='Período letivo')
        parser.add_argument('ano_letivo', type=int, help='Ano letivo')

    def handle(self, *args, **options):
        periodo_letivo = options.get('periodo_letivo')
        ano_letivo = options.get('ano_letivo')

        diarios = Diario.objects.filter(
            turma__periodo_letivo=periodo_letivo, turma__ano_letivo__ano=ano_letivo, turma__matriz__estrutura__permite_recuperacao_etapa=True
        ).distinct()

        for diario in diarios:
            configuracoes_avaliacao = ConfiguracaoAvaliacao.objects.filter(diario=diario).exclude(etapa=5)

            for configuracao_avaliacao in configuracoes_avaliacao:
                if not configuracao_avaliacao.itemconfiguracaoavaliacao_set.filter(tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO).exists():
                    item_configuracao_avaliacao_recuperacao = ItemConfiguracaoAvaliacao()
                    item_configuracao_avaliacao_recuperacao.sigla = 'REC'
                    item_configuracao_avaliacao_recuperacao.descricao = 'Recuperação'
                    item_configuracao_avaliacao_recuperacao.configuracao_avaliacao = configuracao_avaliacao
                    item_configuracao_avaliacao_recuperacao.tipo = ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO
                    item_configuracao_avaliacao_recuperacao.save()

                    for matricula_diario in diario.matriculadiario_set.all():
                        nota_avaliacao = NotaAvaliacao(
                            matricula_diario=matricula_diario, item_configuracao_avaliacao=item_configuracao_avaliacao_recuperacao
                        )
                        nota_avaliacao.save()
