from ae.models import PeriodoInscricao, Inscricao
from djtools.management.commands import BaseCommandPlus


# 129 inscrições para serem migradas
# 25 inscrições foram feitas no período correto pelos próprios alunos
class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        periodo_errado = PeriodoInscricao.objects.get(id=468)
        periodo_certo = PeriodoInscricao.objects.get(id=560)
        inscricoes_erradas = Inscricao.objects.filter(periodo_inscricao=periodo_errado, data_cadastro__year=2025)
        for errada in inscricoes_erradas:
            if not Inscricao.objects.filter(periodo_inscricao=periodo_certo, aluno=errada.aluno, programa=errada.programa):
                errada.periodo_inscricao = periodo_certo
                errada.ativa = True
                errada.save()
