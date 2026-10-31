import tqdm

from catalogo_provedor_servico.models import RegistroAcompanhamentoGovBR, RegistroAvaliacaoGovBR
from catalogo_provedor_servico.providers.factory import get_service_provider_factory
from catalogo_provedor_servico.utils import Notificar
from comum.models import APIExterna
from djtools.management.commands import BaseCommandPlus

# Exemplo de chamada:
# python manage.py enviar_email_avaliacao_de_servicos


class Command(BaseCommandPlus):
    def acompanhar_servicos(self):
        verbose = self.verbose
        api = APIExterna.ACOMPANHAMENTO_GOVBR
        if not api.ativo:
            self.stdout.write(self.style.ERROR('API de Acompanhamentos do gov.br não está ativa. Verifique as configurações.'))
            return

        # Envia registros de acompanhamentos pendentes, pois o link da url de avaliação só pode é retornado se existir
        # o acompanhamento registrado anteriormente
        registros_acompanhamentos_nao_enviados = RegistroAcompanhamentoGovBR.objects.filter(
            status__in=[RegistroAcompanhamentoGovBR.PENDENTE, RegistroAcompanhamentoGovBR.ERRO], tentativas_envio__lte=3
        ).order_by('data_criacao')

        self.stdout.write('Tentando obter as avaliação de solicitações com o govbr.')
        if verbose:
            registros_acompanhamentos_nao_enviados = tqdm.tqdm(registros_acompanhamentos_nao_enviados)

        for registro_acompanhamento in registros_acompanhamentos_nao_enviados:
            service = get_service_provider_factory().get_service_provider(
                id_servico_portal_govbr=registro_acompanhamento.solicitacao.servico.id_servico_portal_govbr
            )
            if registro_acompanhamento.tipo == RegistroAcompanhamentoGovBR.TIPO_ACOMPANHAMENTO:
                resposta = service.registrar_acompanhamento(registro=registro_acompanhamento)
            elif registro_acompanhamento.tipo == RegistroAcompanhamentoGovBR.TIPO_CONCLUSAO:
                resposta = service.registrar_conclusao(registro=registro_acompanhamento)
            elif registro_acompanhamento.tipo == RegistroAcompanhamentoGovBR.TIPO_REABERTURA:
                resposta = service.registrar_reabertura(registro=registro_acompanhamento)
            if verbose:
                self.stdout.write(
                    f'Resposta ao registrar {registro_acompanhamento.tipo} para solicitação {registro_acompanhamento.solicitacao.id}: {resposta}'
                )

    def avaliar_servicos(self):
        verbose = self.verbose
        api = APIExterna.AVALIACAO_GOVBR
        if not api.ativo:
            self.stdout.write(self.style.ERROR('API de Avaliações do gov.br não está ativa. Verifique as configurações.'))
            return

        # Verifica se existem registros não notificados para obter link da url
        registros_avaliacao_pendente_url = RegistroAvaliacaoGovBR.objects.filter(notificado_por_email=False, avaliado=False, tentativas_envio__lte=4)

        if not registros_avaliacao_pendente_url.exists():
            self.stdout.write('Nenhuma solicitação com e-mail de avaliação pendente.')
            return
        else:
            self.stdout.write('Tentando enviar as avaliação de solicitações para os solicitantes.')

        if verbose:
            registros_avaliacao_pendente_url = tqdm.tqdm(registros_avaliacao_pendente_url)

        for registro in registros_avaliacao_pendente_url:
            service_provider = get_service_provider_factory().get_service_provider(
                id_servico_portal_govbr=registro.solicitacao.servico.id_servico_portal_govbr
            )
            url_avaliacao = registro.url_avaliacao
            if not url_avaliacao:
                if verbose:
                    self.stdout.write(f'Obtendo url de avaliação para solicitação {registro.solicitacao.id}')
                resposta = service_provider.obter_formulario_avaliacao(solicitacao=registro.solicitacao)
                if verbose:
                    self.stdout.write(f'Resposta ao obter url de avaliação para solicitação {registro.solicitacao.id}: {resposta}')
            dados_email = service_provider.get_dados_email(solicitacao=registro.solicitacao)
            if url_avaliacao:
                Notificar.notifica_conclusao_servico_atendido(solicitacao=registro.solicitacao, dados_email=dados_email, url_avaliacao=url_avaliacao)
                if registro.notificado_por_email:
                    self.stdout.write(self.style.SUCCESS(f'E-MAIL ENVIADO para solicitação {registro.solicitacao.id}'))
                else:
                    registro.tentativas_envio = registro.tentativas_envio + 1
                    registro.save()
                    self.stdout.write(
                        self.style.ERROR(f'Url de avaliação salva porém houve ERRO AO ENVIAR E-MAIL para solicitação {registro.solicitacao.id}')
                    )

    def handle(self, *args, **options):
        self.verbose = str(options.get('verbosity', '0')) != '0'
        self.acompanhar_servicos()
        self.avaliar_servicos()
