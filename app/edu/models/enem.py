import datetime
import hashlib

import magic
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from comum import utils
from djtools.db import models
from djtools.utils import normalizar_nome_proprio, send_mail
from edu.managers import FiltroUnidadeOrganizacionalManager
from edu.models.cadastros_gerais import ConfiguracaoLivro
from edu.models.logs import LogModel
from rh.models import UnidadeOrganizacional


class ConfiguracaoCertificadoENEM(LogModel):
    SEARCH_FIELDS = ['numero_portaria', 'ano']

    ano = models.OneToOneField('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE)
    data_primeira_prova = models.DateFieldPlus('Data de realização da 1ª Prova')
    pontuacao_necessaria_areas_conhecimento = models.PositiveIntegerField('Pontuação mínima necessária em cada uma das áreas de conhecimento')
    pontuacao_necessaria_redacao = models.PositiveIntegerField('Pontuação mínima necessária na redação')
    responsaveis_vinculos = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Responsáveis pela Certificação')
    numero_portaria = models.TextField('Portaria', help_text='Exemplo: Portaria Normativa nº 16, de 27 de Julho de 2011')
    manual = models.BooleanField('Manual', default=False, help_text='Marque apenas se o certificado só puder ser solicitado através do secretário.')

    def get_absolute_url(self):
        return f'/edu/configuracao_certificacao_enem/{self.pk:d}/'

    def __str__(self):
        return f'{self.ano.ano}'

    class Meta:
        verbose_name = 'Configuração para Certificação ENEM'
        verbose_name_plural = 'Configurações para Certificação ENEM'


class RegistroAlunoINEP(LogModel):
    SEARCH_FIELDS = ['nome', 'cpf']

    configuracao_certificado_enem = models.ForeignKeyPlus('edu.ConfiguracaoCertificadoENEM', on_delete=models.CASCADE)
    numero_inscricao = models.CharFieldPlus('Número da Inscrição')
    nome = models.CharFieldPlus('Nome')
    nome_mae = models.CharFieldPlus('Nome da Mãe')
    rg = models.CharFieldPlus('RG')
    cpf = models.CharField(max_length=20, null=False, verbose_name='CPF')
    data_nascimento = models.DateFieldPlus('Data de Nascimento')
    nota_cn = models.DecimalFieldPlus('Nota - Ciências da Natureza e suas Tecnologias', decimal_places=2)
    nota_ch = models.DecimalFieldPlus('Nota - Ciências Humanas e suas Tecnologias', decimal_places=2)
    nota_lc = models.DecimalFieldPlus('Nota - Linguagens, Códigos e suas Tecnologias', decimal_places=2)
    nota_mt = models.DecimalFieldPlus('Nota - Matemática e suas Tecnologias', decimal_places=2)
    nota_redacao = models.DecimalFieldPlus('Nota - Redação', decimal_places=2)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', null=True, on_delete=models.CASCADE)

    def __str__(self):
        return f'{normalizar_nome_proprio(self.nome)} ({self.cpf})'

    class Meta:
        verbose_name = 'Registro do aluno no INEP'
        verbose_name_plural = 'Registros dos alunos no INEP'

    def get_nota_minima_necessaria_areas_conhecimento(self):
        return self.configuracao_certificado_enem.pontuacao_necessaria_areas_conhecimento

    def get_nota_minima_necessaria_redacao(self):
        return self.configuracao_certificado_enem.pontuacao_necessaria_redacao

    def possui_registro_emissao_certificado_enem(self):
        return self.get_registro_emissao_certificado_enem() is not None

    def get_registro_emissao_certificado_enem(self):
        return RegistroEmissaoCertificadoENEM.objects.filter(
            solicitacao__cpf=self.cpf, solicitacao__configuracao_certificado_enem=self.configuracao_certificado_enem, cancelado=False
        ).first()

    def apto_certificado_completo(self):
        nota_minima_necessaria_areas_conhecimento = self.get_nota_minima_necessaria_areas_conhecimento()
        nota_minima_necessaria_redacao = self.get_nota_minima_necessaria_redacao()

        return (
            self.nota_ch >= nota_minima_necessaria_areas_conhecimento
            and self.nota_cn >= nota_minima_necessaria_areas_conhecimento
            and self.nota_lc >= nota_minima_necessaria_areas_conhecimento
            and self.nota_mt >= nota_minima_necessaria_areas_conhecimento
            and self.nota_redacao >= nota_minima_necessaria_redacao
        )

    def apto_certificado_parcial(self):
        nota_minima_necessaria_areas_conhecimento = self.get_nota_minima_necessaria_areas_conhecimento()
        nota_minima_necessaria_redacao = self.get_nota_minima_necessaria_redacao()

        return (
            self.nota_ch >= nota_minima_necessaria_areas_conhecimento
            or self.nota_cn >= nota_minima_necessaria_areas_conhecimento
            or (self.nota_lc >= nota_minima_necessaria_areas_conhecimento and self.nota_redacao >= nota_minima_necessaria_redacao)
            or self.nota_mt >= nota_minima_necessaria_areas_conhecimento
        )


class SolicitacaoCertificadoENEM(models.ModelPlus):
    COMPLETO = 1
    PARCIAL = 2
    TIPO_CERTIFICADO_CHOICES = [[COMPLETO, 'Completo'], [PARCIAL, 'Parcial']]

    nome = models.CharFieldPlus('Nome')
    cpf = models.CharField('CPF', max_length=20)
    email = models.CharFieldPlus('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    tipo_certificado = models.IntegerField(choices=TIPO_CERTIFICADO_CHOICES, verbose_name='Tipo de Certificado')
    documento_identidade_frente = models.FileFieldPlus(
        upload_to='edu/solicitacao_certificado_enem/', verbose_name='Cópia do documento de identidade - Frente', null=True
    )
    documento_identidade_verso = models.FileFieldPlus(
        upload_to='edu/solicitacao_certificado_enem/', verbose_name='Cópia do documento de identidade - Verso', null=True
    )
    data_solicitacao = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Data da Solicitação')

    avaliada = models.BooleanField(verbose_name='Avaliada', default=False)
    avaliador = models.ForeignKeyPlus('comum.User', verbose_name='Avaliador', null=True, related_name='solicitacao_certificado_enem_avaliador_set')
    data_avaliacao = models.DateTimeFieldPlus(null=True)
    razao_indeferimento = models.TextField(null=True, verbose_name='Razão do Indeferimento')
    razao_ressalva = models.TextField(null=True, verbose_name='Razão da Ressalva')
    configuracao_certificado_enem = models.ForeignKey('edu.ConfiguracaoCertificadoENEM', verbose_name='Edição do ENEM', on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    codigo_geracao_solicitacao = models.CharFieldPlus(max_length=16, null=True)

    # Caso seja uma solicitação manual via processo. Edição do ENEM < 2014
    processo = models.ForeignKeyPlus('protocolo.Processo', null=True, blank=True)
    solicitacao_manual = models.BooleanField(default=False)

    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('uo')

    def __init__(self, *args, **kwargs):
        self._meta.get_field('uo').default = UnidadeOrganizacional.objects.suap().get(sigla=utils.get_sigla_reitoria()).pk
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f'({self.cpf}) {self.nome} - {self.tipo_certificado}'

    class Meta:
        verbose_name = 'Solicitação de Certificado ENEM'
        verbose_name_plural = 'Solicitações de Certificado ENEM'

    def get_absolute_url(self):
        return f'/edu/solicitacao_certificado_enem/{self.pk:d}/'

    def get_registro_aluno_inep(self):
        qs = self.configuracao_certificado_enem.registroalunoinep_set.filter(cpf=self.cpf)

        if qs.exists():
            return qs[0]
        else:
            return None

    def get_registro_emissao_certificado_enem(self):
        return self.registroemissaocertificadoenem_set.latest('id')

    def get_tipo_certificado_enem_label(self):
        if self.tipo_certificado == 1:
            return 'Completo'
        else:
            return 'Parcial'

    def get_mime_type_arquivo_documento_identidade(self, lado):
        arquivo = self.documento_identidade_frente if lado == 1 else self.documento_identidade_verso
        return magic.from_buffer(arquivo.read(1024), mime=True)

    def get_mime_type_arquivo_documento_identidade_frente(self):
        return self.get_mime_type_arquivo_documento_identidade(1)

    def get_mime_type_arquivo_documento_identidade_verso(self):
        return self.get_mime_type_arquivo_documento_identidade(2)

    def frente_documento_identidade_pode_ser_visualizado(self):
        return self.get_mime_type_arquivo_documento_identidade(1) in (
            'application/pdf',
            'application/octet-stream',
            'image/jpeg',
            'image/pjpeg',
            'image/png',
        )

    def verso_documento_identidade_pode_ser_visualizado(self):
        return self.get_mime_type_arquivo_documento_identidade(2) in (
            'application/pdf',
            'application/octet-stream',
            'image/jpeg',
            'image/pjpeg',
            'image/png',
        )

    def get_tipo_certificacao(self, formatar=False):
        if self.tipo_certificado == 1:
            return formatar and '<span class="status status-success">Completa</span>' or 'Completa'
        else:
            return formatar and '<span class="status status-alert">Parcial</span>' or 'Parcial'

    @transaction.atomic
    def replicar(self, user):
        if not self.avaliador:
            raise ValidationError('Não é possível replicar uma solicitação não avaliada.')
        else:
            registro = RegistroEmissaoCertificadoENEM.objects.get(id=self.get_registro_emissao_certificado_enem().pk)
            registro.cancelar(user, 'Solicitação de Certidicado ENEM Replicada')
            self.id = None
            self.avaliada = False
            self.avaliador = None
            self.data_avaliacao = None
            self.razao_ressalva = None
            self.save()

    @transaction.atomic
    def atender(self, avaliador, razao_ressalva=None):
        try:
            sigla_re = utils.get_sigla_reitoria()
            conf = ConfiguracaoLivro.objects.get(uo__sigla=sigla_re, descricao=ConfiguracaoLivro.NOME_LIVRO_ENEM)

            # Salvando os dados da Avaliação
            self.data_avaliacao = datetime.datetime.now()
            self.avaliador = avaliador
            self.avaliada = True
            self.razao_ressalva = razao_ressalva
            self.save()

            # Salvando os dados do Registro de Emissão
            registro = RegistroEmissaoCertificadoENEM()
            registro.solicitacao = self
            registro.livro = conf.numero_livro
            registro.folha = conf.numero_folha
            registro.numero_registro = conf.numero_registro
            registro.data_expedicao = datetime.datetime.now()
            registro.via = RegistroEmissaoCertificadoENEM.objects.filter(solicitacao__pk=self.pk).filter(cancelado=False).count() + 1
            registro.codigo_geracao_certificado = hashlib.sha1(f'{registro.pk}{registro.data_expedicao}{settings.SECRET_KEY}'.encode()).hexdigest()[
                0:16
            ]
            registro.save()
            conf.gerar_proximo_numero()
        except Exception:
            raise ValidationError(
                f'Ocorreu um erro no processamento da solicitação. Verifique a configuração do {ConfiguracaoLivro.NOME_LIVRO_ENEM} da {sigla_re}.'
            )

        if avaliador and not self.solicitacao_manual:
            self.enviar_email(avaliador)

    def rejeitar(self, avaliador, razao_indeferimento):
        self.data_avaliacao = datetime.datetime.now()
        self.avaliador = avaliador
        self.avaliada = False
        self.razao_indeferimento = razao_indeferimento
        self.save()

        if not self.solicitacao_manual:
            self.enviar_email(avaliador)

    def enviar_email(self, avaliador):
        titulo = '[SUAP] Situação da Solicitação de Certificado ENEM'
        texto = 'Caro(a) aluno(a),<br /><br />'
        if avaliador:
            artigo = self.avaliador.get_profile().sexo == 'F' and 'a' or 'o'
            if self.avaliada and not self.razao_indeferimento:
                texto += '<p>A sua solicitação de Certificado ENEM foi atendida pel{} servidor{} {}.</p>'.format(
                    artigo, artigo == 'a' and 'a' or '', avaliador
                )
                texto += f'<p>Para emitir o seu Certificado, acesse o endereço: {settings.SITE_URL}/edu/gerar_certificado_enem/{self.get_registro_emissao_certificado_enem().codigo_geracao_certificado}/</p>'
            else:
                texto += f'<p>A sua solicitação de Certificado ENEM foi rejeitada pelo servidor {avaliador} devido ao seguinte motivo: "{self.razao_indeferimento}"</p>'

            uo = self.avaliador.get_vinculo().setor.uo
            texto += (
                '<br /><br /><br />'
                '<p>INSTITUTO FEDERAL DO RIO GRANDE DO NORTE</p>'
                f'<p>{normalizar_nome_proprio(uo.nome)} {self.avaliador.get_vinculo().pessoa.telefones_institucionais or uo.telefone}<p>'
                f'<p>{normalizar_nome_proprio(uo.endereco)}, CEP {uo.cep}, {normalizar_nome_proprio(uo.municipio.nome)} ({uo.municipio.uf})</p>'
                f'<p>CNPJ: {uo.cnpj}</p>'
            )
        else:
            texto += '<p>A sua solicitação de Certificado ENEM foi aprovada</p>'
            texto += f'<p>Para emitir o seu Certificado, acesse o endereço: {self.get_url()}/</p>'
        email_destino = [self.email]
        return send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, email_destino)

    def get_url(self):
        return f'{settings.SITE_URL}/edu/gerar_certificado_enem/{self.get_registro_emissao_certificado_enem().codigo_geracao_certificado}/'


class RegistroEmissaoCertificadoENEM(LogModel):
    livro = models.PositiveIntegerField()
    folha = models.PositiveIntegerField()
    numero_registro = models.PositiveIntegerField(verbose_name='Número do Registro')
    solicitacao = models.ForeignKeyPlus('edu.SolicitacaoCertificadoENEM')
    data_expedicao = models.DateFieldPlus(verbose_name='Data de Expedição')
    emissor = models.CurrentUserField()
    via = models.IntegerField()

    cancelado = models.BooleanField(default=False)
    razao_cancelamento = models.TextField(null=True, verbose_name='Razão do Cancelamento')
    responsavel_cancelamento = models.ForeignKeyPlus(
        'comum.User', verbose_name='Responsável pelo Cancelamento', null=True, related_name='reg_emissao_certificado_enem_resp_cancelamento_set'
    )
    data_cancelamento = models.DateTimeFieldPlus(null=True, verbose_name='Data do Cancelamento')
    codigo_geracao_certificado = models.CharFieldPlus(max_length=16)

    class Meta:
        verbose_name = 'Registro de Emissão de Certificado ENEM'
        verbose_name_plural = 'Registro de Emissão de Certificados ENEM'

    def get_absolute_url(self):
        return f'/edu/registroemissaocertificadoenem/{self.pk:d}/'

    def __str__(self):
        return f'{self.via}ª Via'

    def get_avaliador(self):
        return self.solicitacao.avaliador.get_relacionamento()

    def eh_ultima_via(self):
        return self.via == RegistroEmissaoCertificadoENEM.objects.filter(solicitacao__pk=self.solicitacao.pk).filter(cancelado=False).count()

    def cancelar(self, responsavel_cancelamento, razao_cancelamento):
        if self.eh_ultima_via():
            self.cancelado = True
            self.razao_cancelamento = razao_cancelamento
            self.responsavel_cancelamento = responsavel_cancelamento
            self.data_cancelamento = datetime.datetime.now()
            self.save()
            self.enviar_email()
        else:
            raise ValidationError('Apenas a última via pode ser cancelada.')

    def enviar_email(self):
        artigo = self.responsavel_cancelamento.get_profile().sexo == 'F' and 'a' or 'o'
        titulo = '[SUAP] Situação do Registro de Emissão de Certificado ENEM'
        certificado_status = 'cancelado pel{} servidor{} {}.\nDevido ao seguinte motivo "{}"'.format(
            artigo, artigo == 'a' and 'a' or '', self.responsavel_cancelamento, self.razao_cancelamento
        )
        texto = (
            '<h1>Ensino</h1>'
            f'<h2>Situação do Registro de Emissão de Certificado ENEM de Número {self.pk}</h2>'
            f'<p>O Registro de Emissão de Certifido ENEM foi: <strong>{certificado_status}</strong>.</p>'
        )
        uo = self.responsavel_cancelamento.get_vinculo().setor.uo
        texto += (
            '<br /><br /><br />'
            '<p>INSTITUTO FEDERAL DO RIO GRANDE DO NORTE</p>'
            f'<p>{normalizar_nome_proprio(uo.nome)} {self.responsavel_cancelamento.get_vinculo().pessoa.telefones_institucionais or uo.telefone}<p>'
            f'<p>{normalizar_nome_proprio(uo.endereco)}, CEP {uo.cep}, {normalizar_nome_proprio(uo.municipio.nome)} ({uo.municipio.uf})</p>'
            f'<p>CNPJ: {uo.cnpj}</p>'
        )
        email_destino = [self.solicitacao.email]
        return send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, email_destino)
