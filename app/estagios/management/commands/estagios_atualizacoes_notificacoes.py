import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from sentry_sdk import capture_exception

from djtools.management.commands import BaseCommandPlus
from estagios.models import Aprendizagem, AtividadeProfissionalEfetiva, PraticaProfissional


def _tratar_excecao(excecao):
    if settings.DEBUG:
        raise excecao
    capture_exception(excecao)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = datetime.datetime.today()

        estagios = PraticaProfissional.objects.filter(data_fim__isnull=True)
        for estagio in estagios:
            try:
                estagio.atualizar_situacoes(salvar=True)
                estagio.verificar_pendencias()
                estagio.verificar_matricula_irregular()
                estagio.notificar_orientador_pendencia_visita()
                # executar apenas na segunda-feira
                if hoje.weekday() == 0:
                    estagio.notificar_orientador_divergencia_relatorios_estagio()
                    estagio.notificar_signatarios_tre_eletronico()
            except Exception as e:
                _tratar_excecao(e)

        aprendizagens = Aprendizagem.objects.filter(data_encerramento__isnull=True)
        for aprendizagem in aprendizagens:
            try:
                aprendizagem.verificar_pendencias()
                aprendizagem.verificar_matricula_irregular()
                aprendizagem.notificar_orientador_pendencia_visita()
                # executar apenas na segunda-feira
                if hoje.weekday() == 0:
                    aprendizagem.notificar_orientador_divergencia_relatorios_modulo_aprendizagem()
                    aprendizagem.notificar_orientador_necessidade_revisao()
            except Exception as e:
                _tratar_excecao(e)

        aprendizagens = aprendizagens | Aprendizagem.objects.filter(
            data_encerramento__isnull=False,
            data_encerramento__gte=datetime.date.today() - relativedelta(months=1),
            data_encerramento__lte=datetime.date.today(),
        )
        for aprendizagem in aprendizagens:
            try:
                aprendizagem.verificar_envio_relatorio_frequencia()
            except Exception as e:
                _tratar_excecao(e)

        atividades_profissionais_efetivas = AtividadeProfissionalEfetiva.objects.filter(situacao=AtividadeProfissionalEfetiva.EM_ANDAMENTO)
        for ape in atividades_profissionais_efetivas:
            try:
                ape.verificar_matricula_irregular()
            except Exception as e:
                _tratar_excecao(e)
