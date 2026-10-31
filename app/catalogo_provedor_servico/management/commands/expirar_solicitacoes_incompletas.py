import datetime
import json

import tqdm
from django.utils import termcolors

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa
from djtools.management.commands import BaseCommandPlus
from processo_seletivo.models import CandidatoVaga


class Command(BaseCommandPlus):
    help = 'Expira solicitações antigas e incompletas do Balcão Digital'

    def processar_solicitacoes(self, verbose):
        qs = SolicitacaoEtapa.objects.filter(numero_etapa=1, solicitacao__servico__id_servico_portal_govbr__in=[6176, 6424, 6410, 10054])
        qs = qs.exclude(solicitacao__status__in=Solicitacao.STATUS_DEFINITIVOS)

        if verbose:
            qs = tqdm.tqdm(qs)

        for solicitacao_etapa in qs:
            campos = json.loads(solicitacao_etapa.dados)
            cv_pk = campos.get('formulario')[0].get('value')
            cv = CandidatoVaga.objects.filter(pk=cv_pk).first()
            if not cv:
                continue
            solicitacao = solicitacao_etapa.solicitacao
            mensagem = None
            status = None
            if cv.situacao == CandidatoVaga.AUSENTE:
                mensagem = 'Solicitação automaticamente expirada pois o candidato já se encontra ausente no Edital.'
                status = Solicitacao.STATUS_EXPIRADO
            if cv.situacao == CandidatoVaga.MATRICULADO:
                mensagem = 'Solicitação automaticamente atendida pois o candidato já se encontra matriculado no Edital.'
                status = Solicitacao.STATUS_ATENDIDO
            if cv.situacao == CandidatoVaga.INAPTO:
                mensagem = 'Solicitação automaticamente não atendida pois o candidato já se encontra inapto no Edital.'
                status = Solicitacao.STATUS_NAO_ATENDIDO

            if mensagem and status:
                solicitacao.status = status
                solicitacao.status_detalhamento = mensagem
                solicitacao.save()

        mes_passado = datetime.datetime.now() - datetime.timedelta(days=30)

        qs = Solicitacao.objects.filter(data_criacao__lt=mes_passado, status=Solicitacao.STATUS_INCOMPLETO)
        if verbose:
            qs = tqdm.tqdm(qs)
        for solicitacao in qs:
            solicitacao.status = Solicitacao.STATUS_EXPIRADO
            solicitacao.status_detalhamento = 'Solicitação expirada pois ficou incompleta pelo prazo de 30 dias.'
            solicitacao.save()

    def handle(self, *args, **options):
        try:
            self.processar_solicitacoes(verbose=options.get('verbosity'))
        except Exception as e:
            self.stderr.write(termcolors.make_style(fg='red', opts=('bold',))(str(e)))
            raise
