from django.conf import settings
from django.db import transaction
from sentry_sdk import capture_exception
from dateutil.relativedelta import relativedelta
from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa
from catalogo_provedor_servico.providers.base import Etapa, GovBr_User_Info, Mask
from comum.models import Configuracao
from edu.models import RegistroAlunoINEP, SolicitacaoCertificadoENEM

from .base import AbstractServiceProvider


class SolicitarCertificadoEnemServiceProvider(AbstractServiceProvider):
    def get_id_servico_portal_govbr(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_certificacao_enem') or 0)

    def is_em_periodo_avaliacao(self, solicitacao, campus=None):
        return True

    def _on_persist_solicitacao(self, solicitacao, is_create, is_update):
        pass

    def _on_persist_solicitacao_etapa(self, etapa, solicitacao_etapa, is_create, is_update):
        if etapa.numero == 1:
            solicitacao_etapa.solicitacao.nome = etapa.formulario.get_value('nome')
            solicitacao_etapa.solicitacao.save()

    def _do_avaliacao_disponibilidade_especifica(self, cpf, servico, avaliacao):
        em_disponibilidade = RegistroAlunoINEP.objects.filter(cpf=cpf, configuracao_certificado_enem__ano__ano__gte=2025).exists()
        mensagem = 'Há registro na base de alunos que realizaram o ENEM' if em_disponibilidade else ''
        avaliacao.add_criterio(em_disponibilidade, mensagem, 'Não há registro na base de alunos que realizaram o ENEM')

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

    @staticmethod
    def choices_ano():
        return {'2025': '2025'}

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
            help_text='O certificado será enviado para esse email.',
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
        ).add_choices(label='Ano', name='ano', value=None, required=True, read_only=False, choices=self.choices_ano)
        etapa_1.fieldsets.add(
            name='Dados Pessoais',
            fields=(
                'nome',
                'cpf',
                'email',
                'telefone',
            ),
        ).add(
            name='Dados da Certificação',
            fields=('ano',),
        )

        return etapa_1

    def _validate_dados_etapa(self, request, etapa, solicitacao):
        has_errors = super()._validate_dados_etapa(request, etapa, solicitacao)
        cpf = etapa.formulario.get_field('cpf')
        ano = etapa.formulario.get_field('ano')
        registro = RegistroAlunoINEP.objects.filter(cpf=cpf['value'], configuracao_certificado_enem__ano__ano=ano['value']).first()
        if registro is None:
            has_errors.append('Registro não encontrado para o ano informado.')
        elif not registro.data_nascimento <= registro.configuracao_certificado_enem.data_primeira_prova - relativedelta(years=18):
            has_errors.append('O aluno deve ser maior de idade no dia da primeira prova.')
        elif not registro.apto_certificado_completo() and not registro.apto_certificado_parcial():
            has_errors.append('As notas do aluno não atendem aos critérios para emissão do certificado nem parcial e nem completo.')
        return has_errors

    def _on_after_finish_recebimento_solicitacao(self, request, solicitacao):
        self.executar_solicitacao(request, solicitacao)

    def executar_solicitacao(self, request, solicitacao):
        solicitacao_etapa = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1)
        dados = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())
        nome = dados.formulario.get_value('nome')
        email = dados.formulario.get_value('email')
        cpf = dados.formulario.get_value('cpf')
        ano = dados.formulario.get_value('ano')

        registro = RegistroAlunoINEP.objects.filter(cpf=cpf, configuracao_certificado_enem__ano__ano=ano).first()
        with transaction.atomic():
            if registro.apto_certificado_completo():
                tipo_certificado = '1'
            elif registro.apto_certificado_parcial():
                tipo_certificado = '2'
            solicitacao_certificado_enem, created = SolicitacaoCertificadoENEM.objects.get_or_create(
                configuracao_certificado_enem=registro.configuracao_certificado_enem,
                cpf=cpf,
                tipo_certificado=tipo_certificado,
                defaults={
                    'nome': nome,
                    'email': email,
                    'solicitacao_manual': False,
                },
            )
            if created:
                solicitacao_certificado_enem.atender(None)
            self.registrar_acompanhamento(solicitacao)

            # Registra solicitação com ATENDIDA
            solicitacao.status = Solicitacao.STATUS_ATENDIDO
            identificador, provedor = email.split('@')
            email_anonimizado = identificador[0:2] + int(len(identificador) - 4) * '*' + identificador[-2:] + '@' + provedor
            url = solicitacao_certificado_enem.get_url()
            if tipo_certificado == '1':
                mensagem = f'Sua solicitação de certificação de conclusão do ensino médio, com base no ENEM, foi aprovada e o certificado emitido. O documento foi encaminhado automaticamente para {email_anonimizado}. Caso deseje visualizá-lo, acesse o endereço: {url}'
            else:
                mensagem = f'Sua solicitação de declaração parcial de proficiência, com base no ENEM, foi aprovada e a declaração emitida. O documento foi encaminhado automaticamente {email_anonimizado}. Caso deseje visualizá-lo, acesse o endereço: {url}'
            solicitacao.status_detalhamento = mensagem
            solicitacao.save()

            # Registra acomapanhamento e indica conclusão do serviço junto ao GOVBR
            self.registrar_conclusao(solicitacao)

            # envia email com os certificados. Deve ser o último passo pois aqui não é possível efetuar rollback
            solicitacao_certificado_enem.enviar_email(None)
