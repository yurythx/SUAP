import tqdm

from projetos.models import HistoricoEquipe
from djtools.management.commands import BaseCommandPlus
from ae.models import ParticipacaoBolsa


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        participacoes = ParticipacaoBolsa.abertas.filter(aluno_participante_projeto__vinculo='Voluntário')
        for participacao in tqdm.tqdm(participacoes):
            historicos = HistoricoEquipe.objects.filter(
                vinculo='Voluntário',
                participante=participacao.aluno_participante_projeto,
                tipo_de_evento__in=[HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, HistoricoEquipe.EVENTO_EDICAO_ALUNO],
            ).order_by('-id')
            if historicos.exists():
                participacao.data_termino = historicos[0].data_movimentacao
                participacao.save()
