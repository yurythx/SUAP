from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from sentry_sdk import capture_exception

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa
from catalogo_provedor_servico.providers.base import Etapa, GovBr_User_Info, Mask
from catalogo_provedor_servico.utils import Notificar
from comum.models import Configuracao
from encceja.models import Solicitacao as SolicitacaoEncceja

from .base import AbstractServiceProvider


class SolicitarCertificadoEnccejaServiceProvider(AbstractServiceProvider):
    def get_id_servico_portal_govbr(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_certificado_encceja') or 0)

    def is_em_periodo_avaliacao(self, solicitacao, campus=None):
        return True

    def _on_persist_solicitacao(self, solicitacao, is_create, is_update):
        pass

    def _on_persist_solicitacao_etapa(self, etapa, solicitacao_etapa, is_create, is_update):
        if etapa.numero == 1:
            solicitacao_etapa.solicitacao.nome = etapa.formulario.get_value('nome')
            solicitacao_etapa.solicitacao.save()

    def _do_avaliacao_disponibilidade_especifica(self, cpf, servico, avaliacao):
        """
        :param cpf:
        :return:
        """
        # Condições para tornar disponível a avaliação
        # 1 - Existir alguma solicitação de certificado do tipo encceja solicitado no módulo ENCCEJA de qualquer ano
        #
        em_disponibilidade = SolicitacaoEncceja.objects.filter(
            cpf=cpf, data_nascimento__lte=F('configuracao__data_primeira_prova') - timedelta(days=365.25 * 18)
        ).exists()

        mensagem = ''
        if em_disponibilidade:
            mensagem = 'Há solicitações do cidadão para certificado encceja cadastrados no SUAP.'

        avaliacao.add_criterio(em_disponibilidade, mensagem, 'Não há solicitações de certificado encceja cadastrado no SUAP para o ano solicitado.')

    def get_dados_email(self, solicitacao):
        dados_email = []
        try:
            solicitacao_etapa1 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1).first()
            if solicitacao_etapa1:
                etapa1 = Etapa.load_from_json(solicitacao_etapa1.get_dados_as_json())
                nome = etapa1.formulario.get_field('nome')
                dados_email.append(nome)
                cpf = etapa1.formulario.get_field('cpf')
                dados_email.append(cpf)
                telefone = etapa1.formulario.get_field('telefone')
                dados_email.append(telefone)
                email = etapa1.formulario.get_field('email')
                dados_email.append(email)
                # Obtém fields com erro da etapa 1 caso exista
                if etapa1.formulario.get_campos_by_status(status='ERROR'):
                    dados_email += etapa1.formulario.get_campos_by_status(status='ERROR')
            return dados_email
        except Exception as e:
            if settings.DEBUG:
                raise Exception(f'Detalhes: {e}')
            capture_exception(e)
            return None

    def _get_etapa_1(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        if etapa_1:
            return etapa_1

        etapa_1 = Etapa(numero=1, total_etapas=self.get_numero_total_etapas(), nome='Etapa 1')

        etapa_1.formulario.add_string(
            label='Nome', name='nome', value=None, balcaodigital_user_info=GovBr_User_Info.NOME, required=True, read_only=True, max_length=200
        ).add_string(
            label='CPF', name='cpf', value=None, balcaodigital_user_info=GovBr_User_Info.CPF, mask=Mask.CPF, required=True, read_only=True
        ).add_string(
            label='E-mail',
            name='email',
            help_text='O certificado do ENCCEJA será enviado para esse email.',
            value=None,
            balcaodigital_user_info=GovBr_User_Info.EMAIL if not settings.DEBUG else None,
            required=True,
            read_only=not settings.DEBUG,
            max_length=200,
        ).add_string(
            label='Telefone',
            name='telefone',
            value=None,
            balcaodigital_user_info=GovBr_User_Info.FONE if not settings.DEBUG else None,
            required=True,
            read_only=not settings.DEBUG,
            help_text='Formato: (XX) XXXXX-XXXX',
            mask=Mask.TELEFONE,
            max_length=200,
        )

        etapa_1.fieldsets.add(
            name='Dados Pessoais',
            fields=(
                'nome',
                'cpf',
                'email',
                'telefone',
            ),
        )

        return etapa_1

    def _on_after_finish_recebimento_solicitacao(self, request, solicitacao):
        self.executar_solicitacao(request, solicitacao)

    def executar_solicitacao(self, request, solicitacao):
        """

        :param request: Dados do request
        :param solicitacao: Solicitacao de serviço digital que será executada, neste caso cria um proceso eletrônico
        :return: HttpResponse com informação sobre execução (Sucesso, Erro)
        """
        solicitacao_etapa = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1)
        dados = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())
        email = dados.formulario.get_value('email')
        cpf = dados.formulario.get_value('cpf')
        solicitacoes_encceja = SolicitacaoEncceja.objects.filter(cpf=cpf, configuracao__ativa=True).order_by('-configuracao__ano__ano')
        solicitacao_encceja = solicitacoes_encceja.first()
        if solicitacao_encceja and not solicitacao_encceja.pode_certificar_integralmente() and solicitacoes_encceja.count() > 1:
            solicitacao_encceja = SolicitacaoEncceja.criar_solicitacao_com_aproveitamento_de_notas(solicitacao_encceja.cpf)
        with transaction.atomic():
            self.registrar_acompanhamento(solicitacao)
            # Enviando o e-mail com a notificação de serviço atendido com sucesso.
            self.obter_formulario_avaliacao(solicitacao)
            url_avaliacao = None
            if solicitacao.get_registroavaliacao_govbr():
                url_avaliacao = solicitacao.get_registroavaliacao_govbr().url_avaliacao

            # Registra solicitação com ATENDIDA
            solicitacao.status = Solicitacao.STATUS_ATENDIDO
            identificador, provedor = email.split('@')
            email_anonimizado = identificador[0:2] + int(len(identificador) - 4) * '*' + identificador[-2:] + '@' + provedor
            mensagem = f'Certificado ENCCEJA emitido e foi enviado para o email {email_anonimizado} cadastrado na solicitação.'
            solicitacao.status_detalhamento = mensagem
            solicitacao.save()
            # Registra acomapanhamento e indica conclusão do serviço junto ao GOVBR
            self.registrar_conclusao(solicitacao)

            # envia email com os certificados. Deve ser o último passo pois aqui não é possível efetuar rollback
            Notificar.envia_certificados_encceja(solicitacao, cpf, email, url_avaliacao)
