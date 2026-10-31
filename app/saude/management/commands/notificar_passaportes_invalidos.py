import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from saude.models import PassaporteVacinalCovid


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        data_inicio_checagem_ponto = Configuracao.get_valor_por_chave('saude', 'data_checagem_ponto')
        if (
            data_inicio_checagem_ponto
            and ((datetime.datetime.strptime(data_inicio_checagem_ponto, '%Y-%m-%d')) + relativedelta(days=15)).date() == datetime.date.today()
        ):
            titulo = '[SUAP] Regularize o seu registro de vacinação contra a COVID-19'
            mensagem = """
            <h1>Saúde</h1><h2>Passaporte vacinal pendente de regularização</h2>
            <p>
            Solicitamos a gentileza de regularizar o seu registro de vacinação contra a COVID-19.
            </p><p>
            Os usuários com vacinas administradas em outros estados e países podem procurar algum posto de vacinação no RN e solicitar o cadastramento das doses já administradas na plataforma do RN+Vacina. Posteriormente, no SUAP, através do menu Saúde > COVID-19 > Meu Passaporte Vacinal, devem solicitar uma nova importação dos seus dados do RN+Vacina. Alternativamente é possível anexar os comprovantes vacinais no SUAP e sua validação dependerá de análise e deferimento de um profissional de saúde do IFRN.
            </p><p>
            O prazo limite para regularização da sua situação se encerra em 07/03/2022 e deve ser assumido seguindo as determinações da Resolução n° 07/2022 CONSUP e na Instrução Normativa n° 03/2022 DIGPE/RE/IFRN.
            </p><p>
            No caso de descumprimento dessa recomendação na data limite acima mencionada, seu Passaporte Vacinal permanecerá inválido e o seu acesso a instituição para realização de suas atividades será impossibilitado.
            </p><p>
            Em caso de dúvidas, procure sua chefia imediata (para os servidores) ou o coordenador do seu curso (para os estudantes).
            """
            for passaporte in PassaporteVacinalCovid.objects.filter(situacao_passaporte=PassaporteVacinalCovid.INVALIDO):
                send_notification(
                    titulo,
                    mensagem,
                    settings.DEFAULT_FROM_EMAIL,
                    [passaporte.vinculo],
                    categoria='Saúde: Passaporte vacinal pendente de regularização',
                )
