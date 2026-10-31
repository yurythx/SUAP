import tqdm

from djtools.management.commands import BaseCommandPlus
from saude.models import Atendimento, TipoAtendimento, SituacaoAtendimento
import datetime


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for pessoa in tqdm.tqdm(
            Atendimento.objects.filter(tipo=TipoAtendimento.AVALIACAO_BIOMEDICA, situacao=SituacaoAtendimento.ABERTO, aluno__situacao__ativo=False)
        ):
            pessoa.data_fechado = datetime.datetime.today()
            pessoa.situacao = SituacaoAtendimento.FECHADO
            pessoa.obs_fechado = 'Fechado automaticamente. Motivo: aluno com situação concluída/cancelada.'
            pessoa.save()
