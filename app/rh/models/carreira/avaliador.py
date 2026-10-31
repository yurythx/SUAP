import datetime
from djtools.db import models
from djtools.utils import anonimizar_cpf
from django.apps.registry import apps
from django.conf import settings
from django.contrib.auth.models import Group
from rh.managers import AvaliadorExternosManager, AvaliadorInternosManager


class Avaliador(models.ModelPlus):
    SEARCH_FIELDS = ['vinculo__pessoa__nome', 'vinculo__pessoa__pessoafisica__cpf', 'matricula_siape', 'numero_documento_identificacao', 'pis_pasep']

    TIPOCONTA_CONTACORRENTE = 'Conta Corrente'
    TIPOCONTA_POUPANCA = 'Conta Poupança'
    TIPOCONTA_CHOICES = ((TIPOCONTA_CONTACORRENTE, 'Conta Corrente'), (TIPOCONTA_POUPANCA, 'Conta Poupança'))
    TELEFONE_CELULAR = 'Telefone Celular'
    TELEFONE_RESIDENCIAL = 'Telefone Residencial'
    TELEFONE_COMERCIAL = 'Telefone Comercial'

    NOVOS_NIVEIS = {
        'A1': 'A1',
        'B1': 'B1',
        'B2': 'B2',
        'B3': 'B3',
        'B4': 'B4',
        'C1': 'C1',
        'C2': 'C2',
        'C3': 'C3',
        'C4': 'C4',
        'T1': 'T1',  # nível titular
    }

    vinculo = models.OneToOneField('comum.Vinculo', on_delete=models.CASCADE)
    ativo = models.BooleanField('Ativo', default=True, help_text='Somente avaliadores com situação ativa podem avaliar')
    email_contato = models.EmailField('Email para Contato', blank=True)
    titulacao = models.ForeignKeyPlus('rh.Titulacao', null=True, blank=True, on_delete=models.CASCADE)
    padrao_vencimento = models.ForeignKeyPlus('rh.PadraoVencimento', null=True, blank=True, on_delete=models.CASCADE)

    # nivel atual
    nivel_atual = models.CharFieldPlus('Nível atual', max_length=50, null=True, blank=True)
    area_conhecimento = models.ForeignKeyPlus(
        'rh.AreaConhecimento', verbose_name='Área de conhecimento', null=True, blank=True, on_delete=models.SET_NULL
    )

    matricula_siape = models.CharField('Matrícula SIAPE', max_length=50)
    instituicao_origem = models.ForeignKeyPlus('rh.Instituicao', blank=True, null=True, verbose_name='Instituição', on_delete=models.CASCADE)

    numero_documento_identificacao = models.CharField('Número do Documento de Identificação', max_length=50, help_text='Somente números')
    emissor_documento_identificacao = models.CharField('Emissor do Documento de Identificação', max_length=50)
    pis_pasep = models.CharField('PIS/PASEP', max_length=50)

    endereco_municipio = models.CharFieldPlus('Município', blank=True)
    endereco_logradouro = models.CharFieldPlus(blank=True)
    endereco_numero = models.CharField('Nº', max_length=50, blank=True)
    endereco_complemento = models.CharFieldPlus(blank=True)
    endereco_bairro = models.CharFieldPlus(blank=True)
    endereco_cep = models.CharField('CEP', max_length=9, blank=True)

    banco = models.ForeignKeyPlus('rh.Banco', blank=True, null=True, verbose_name='Bancos', on_delete=models.CASCADE)
    numero_agencia = models.CharField('Número da Agência', max_length=50, help_text='Ex: 3293-X')
    tipo_conta = models.CharField('Tipo da Conta', max_length=50, choices=TIPOCONTA_CHOICES)
    numero_conta = models.CharField('Número da Conta', max_length=50, help_text='Ex: 23384-6')
    operacao = models.CharField('Operação', max_length=50, blank=True)

    objects = models.Manager()
    externos = AvaliadorExternosManager()
    internos = AvaliadorInternosManager()

    class Meta:
        verbose_name = 'Avaliador Externo'
        verbose_name_plural = 'Avaliadores'

    def __str__(self):
        pessoa_fisica = self.vinculo.user.get_profile()
        if self.eh_interno():
            return f'{pessoa_fisica.nome} ({self.vinculo.relacionamento.matricula})'
        else:
            return f'{pessoa_fisica.nome} - {anonimizar_cpf(pessoa_fisica.cpf)}'

    def get_absolute_url(self):
        return f'/rh/avaliador/{self.pk:d}/'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.eh_interno():
            grupo = Group.objects.get(name='Avaliador Interno')
        elif self.eh_externo():
            grupo = Group.objects.get(name='Avaliador Externo')

        if self.ativo and grupo:
            self.vinculo.user.groups.add(grupo)
        else:
            self.vinculo.user.groups.remove(grupo)

    def get_matricula(self):
        if self.eh_interno():
            return self.eh_interno().matricula
        if self.eh_externo():
            return self.matricula_siape

    def qtd_avaliacoes_realizadas(self, avaliacao):
        if 'rsc' in settings.INSTALLED_APPS:
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            if isinstance(avaliacao, Avaliacao):
                return self.avaliacao_avaliador_rsc.filter(status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]).count()

        if 'professor_titular' in settings.INSTALLED_APPS:
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            if isinstance(avaliacao, Avaliacao):
                return self.avaliacao_avaliador_titular.filter(status__in=[Avaliacao.FINALIZADA]).count()

    """
    Método que verifica a quantidade de avaliações realizadas no ano pelo avaliador
    - se o parametro avaliacao for passado, será verificada a instância e mostrada apenas a quantidade desta,
     caso contrario, irá mostra a soma de todas as avaliações
    """

    def avaliacoes_realizadas_no_ano(self, avaliacao=None):
        ano_corrente = datetime.date.today().year
        qtd_avaliacoes_rsc = 0
        qtd_avaliacoes_titular = 0

        if 'rsc' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('rsc', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            qtd_avaliacoes_rsc = self.processo_avaliador_rsc.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.AVALIACAO_FINALIZADA
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_rsc

        if 'professor_titular' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('professor_titular', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            qtd_avaliacoes_titular = self.processo_avaliador_titular.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.AVALIACAO_FINALIZADA
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_titular

        return qtd_avaliacoes_rsc + qtd_avaliacoes_titular

    def qtd_perda_prazo_aceite(self, avaliacao=None):
        ano_corrente = datetime.date.today().year
        qtd_avaliacoes_rsc = 0
        qtd_avaliacoes_titular = 0

        if 'rsc' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('rsc', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            qtd_avaliacoes_rsc = self.processo_avaliador_rsc.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.EXCEDEU_TEMPO_ACEITE
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_rsc

        if 'professor_titular' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('professor_titular', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            qtd_avaliacoes_titular = self.processo_avaliador_titular.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.EXCEDEU_TEMPO_ACEITE
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_titular

        return qtd_avaliacoes_rsc + qtd_avaliacoes_titular

    def qtd_perda_prazo_avaliacao(self, avaliacao=None):
        ano_corrente = datetime.date.today().year
        qtd_avaliacoes_rsc = 0
        qtd_avaliacoes_titular = 0

        if 'rsc' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('rsc', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            qtd_avaliacoes_rsc = self.processo_avaliador_rsc.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.EXCEDEU_TEMPO_AVALIACAO
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_rsc

        if 'professor_titular' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('professor_titular', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            qtd_avaliacoes_titular = self.processo_avaliador_titular.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.EXCEDEU_TEMPO_AVALIACAO
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_titular

        return qtd_avaliacoes_rsc + qtd_avaliacoes_titular

    def qtd_rejeicao_avaliacao(self, avaliacao=None):
        ano_corrente = datetime.date.today().year
        qtd_avaliacoes_rsc = 0
        qtd_avaliacoes_titular = 0

        if 'rsc' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('rsc', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            qtd_avaliacoes_rsc = self.processo_avaliador_rsc.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.REJEITADO_PELO_AVALIADOR
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_rsc

        if 'professor_titular' in settings.INSTALLED_APPS:
            ProcessoAvaliador = apps.get_model('professor_titular', 'ProcessoAvaliador')
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            qtd_avaliacoes_titular = self.processo_avaliador_titular.filter(
                data_cadastro__year=ano_corrente, status=ProcessoAvaliador.REJEITADO_PELO_AVALIADOR
            ).count()
            if isinstance(avaliacao, Avaliacao):
                return qtd_avaliacoes_titular

        return qtd_avaliacoes_rsc + qtd_avaliacoes_titular

    def qtd_avaliacoes_pagas(self, avaliacao):
        if 'rsc' in settings.INSTALLED_APPS:
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            if isinstance(avaliacao, Avaliacao):
                return self.avaliacao_avaliador_rsc.filter(avaliacao_paga=True, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]).count()

        if 'professor_titular' in settings.INSTALLED_APPS:
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            if isinstance(avaliacao, Avaliacao):
                return self.avaliacao_avaliador_titular.filter(avaliacao_paga=True, status__in=[Avaliacao.FINALIZADA]).count()

    def qtd_avaliacoes_nao_pagas(self, avaliacao):
        if 'rsc' in settings.INSTALLED_APPS:
            Avaliacao = apps.get_model('rsc', 'Avaliacao')
            if isinstance(avaliacao, Avaliacao):
                return self.avaliacao_avaliador_rsc.filter(avaliacao_paga=False, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]).count()

        if 'professor_titular' in settings.INSTALLED_APPS:
            Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
            if isinstance(avaliacao, Avaliacao):
                return self.avaliacao_avaliador_titular.filter(avaliacao_paga=False, status__in=[Avaliacao.FINALIZADA]).count()

    def eh_interno(self):
        if self.vinculo.eh_servidor():
            return self.vinculo.relacionamento
        return None

    def eh_externo(self):
        if self.vinculo.eh_prestador():
            return self.vinculo.relacionamento
        return None

    def get_nome_completo(self):
        try:
            if self.eh_interno() and self.vinculo and self.vinculo.pessoa:
                return str(self.vinculo.pessoa.nome)
            elif self.eh_externo() and self.pessoa_fisica:
                return str(self.pessoa_fisica.nome)
            return 'Nome Desconhecido'
        except Exception:
            return 'Nome Desconhecido'
