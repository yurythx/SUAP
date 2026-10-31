from djtools.management.commands import BaseCommandPlus
from ppc.models import Conteudo, ConteudoPPC, PlanoDisciplina, SecaoPlanoDisciplina


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Conteudo')
        for conteudo in Conteudo.objects.all():
            conteudo.texto = PlanoDisciplina.remover_formatacao(conteudo.texto)
            conteudo.save()

        print('ConteudoPPC')
        for conteudo in ConteudoPPC.objects.all():
            conteudo.texto = PlanoDisciplina.remover_formatacao(conteudo.texto)
            conteudo.save()

        print('SecaoPlanoDisciplina')
        for conteudo in SecaoPlanoDisciplina.objects.all():
            conteudo.texto = PlanoDisciplina.remover_formatacao(conteudo.texto)
            conteudo.save()

        print('PlanoDisciplina')
        for conteudo in PlanoDisciplina.objects.all():
            conteudo.ementa = PlanoDisciplina.remover_formatacao(conteudo.ementa)
            conteudo.save()
