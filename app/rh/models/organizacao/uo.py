import datetime
from typing import Any

from django.conf import settings
from comum.utils import get_sigla_reitoria
from djtools.db import models
from rh.managers import UnidadeOrganizacionalManager
from suap import nomenclatura
from django.core.exceptions import ValidationError

if 'edu' in settings.INSTALLED_APPS:
    from edu.managers import FiltroUnidadeOrganizacionalManager

from ..pessoa import PessoaJuridica
from ..carreira import ServidorFuncaoHistorico, Funcao, Atividade
from django.apps import apps


class UnidadeOrganizacional(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'sigla']
    AUTOCOMPLETE_MIN_CHARS = 2

    TIPO_CAMPUS_NAO_PRODUTIVO = 1
    TIPO_CAMPUS_PRODUTIVO = 2
    TIPO_CAMPUS_EAD = 3
    TIPO_REITORIA = 4
    TIPO_CONSELHO = 5

    nome = models.CharField(max_length=255, verbose_name='Nome')
    sigla = models.CharField(max_length=25, verbose_name='Sigla')
    setor = models.OneToOneField('rh.Setor', on_delete=models.CASCADE)
    municipio = models.ForeignKeyPlus('comum.Municipio', null=True, blank=True, verbose_name='Município')
    codigo_protocolo = models.CharField(
        max_length=5, blank=True, verbose_name='Prefixo para geração do número de protocolo', help_text='Este valor deve ter 5 dígitos.'
    )
    codigo_ug = models.CharField(max_length=6, blank=True, verbose_name='Código UG')
    codigo_ugr = models.CharField(max_length=6, blank=True, verbose_name='Código UGR')
    cnpj = models.BrCnpjField(null=True, blank=True)
    equivalente = models.ForeignKeyPlus(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        limit_choices_to={'setor__codigo__isnull': True},
        help_text=f'{nomenclatura.campus} SUAP equivalente. Preencha caso esteja editando um campus SIAPE.',
    )
    endereco = models.CharField(max_length=255, verbose_name='Endereço', null=True, blank=True)
    numero = models.CharField(max_length=255, verbose_name='Número', null=True, blank=True)
    zona_rual = models.BooleanField(verbose_name='Zona Rural?', default=False)
    bairro = models.CharField(max_length=255, verbose_name='Bairro', null=True, blank=True)
    cep = models.CharField(max_length=255, verbose_name='Cep', null=True, blank=True)
    telefone = models.CharField(max_length=255, verbose_name='Telefone', null=True, blank=True)
    fax = models.CharField(max_length=255, verbose_name='Fax', null=True, blank=True)

    # dados acadêmicos
    codigo_inep = models.CharField('Código INEP', max_length=25, blank=True)
    codigo_censup = models.CharField('Código CENSUP', max_length=25, blank=True, null=True)
    codigo_emec = models.CharField('Código e-MEC', max_length=25, blank=True, null=True)
    codigo_sgp = models.CharField('Código SGP', max_length=25, blank=True, null=True)
    portaria_criacao = models.TextField('Portaria de Criação', blank=True)

    # outras informações
    tipo = models.ForeignKeyPlus('rh.TipoUnidadeOrganizacional', null=True, blank=False, on_delete=models.CASCADE)
    codigo_interno = models.CharFieldPlus('Código Interno', default='', blank=True)

    # SISTEC
    codigo_sistec = models.CharFieldPlus('Código SISTEC', default='', blank=True)

    # ConectaGOV - Barramento PEN
    setor_recebimento_pen = models.ForeignKey(
        'rh.Setor',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='setor_barramento',
        verbose_name='Setor de Recebimento de Processos Externos))',
        help_text='Setor que irá receber processos enviados por outras instituições via Tramita Gov.BR',
    )
    id_repositorio_pen = models.CharFieldPlus(
        'ID Repositório Estruturas',
        default='001',
        blank=True,
        null=True,
        help_text='Identificador do repositório de estruturas - Órgãos do Poder Executivo = 001',
    )
    id_estrutura_pen = models.CharFieldPlus(
        'ID Estrutura PEN', blank=True, null=True, help_text='Identificador da estrutura referente a esta unidade no Tramita Gov.BR'
    )

    objects = UnidadeOrganizacionalManager()
    locals = FiltroUnidadeOrganizacionalManager() if 'edu' in settings.INSTALLED_APPS else UnidadeOrganizacionalManager()

    class Meta:
        db_table = 'unidadeorganizacional'
        ordering = ['setor__sigla']
        verbose_name = nomenclatura.campus
        verbose_name_plural = nomenclatura.campi

    def __str__(self):
        return self.sigla

    def save(self, *args: Any, **kwargs: Any) -> None:
        Setor = apps.get_model('rh', 'Setor')
        """
        O método foi sobrescrito para preencher automaticamente o campo ``uo`` dos
        setores.
        """
        if self.pk:
            setor_antigo = UnidadeOrganizacional.objects.get(pk=self.pk).setor
            novo_setor = self.setor
            ignorar_processamento_setores = setor_antigo == novo_setor
        else:
            ignorar_processamento_setores = False

        super().save(*args, **kwargs)
        self._vincular_unidade_gestora_sem_uo()
        if not ignorar_processamento_setores:
            for setor in Setor.objects.all():
                setor.save()

    def _vincular_unidade_gestora_sem_uo(self) -> None:
        if not self.codigo_ug or not apps.is_installed('tesouro_gerencial'):
            return

        UnidadeGestora = apps.get_model('tesouro_gerencial', 'UnidadeGestora')
        UnidadeGestora.objects.filter(codigo=self.codigo_ug, uo__isnull=True).update(uo=self)

    def clean(self):
        super().clean()
        if self.codigo_protocolo and len(self.codigo_protocolo) != 5:
            raise ValidationError('O "prefixo para geração do número de protocolo" deve ter 5 dígitos.')
        if self.setor.excluido:
            raise ValidationError('O "setor" deve ser um setor ativo.')

    def get_ext_combo_template(self):
        configuracao_setor_eh_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        out = str(self)
        if configuracao_setor_eh_suap and self.setor.codigo:
            out += ' (SIAPE)'
        return f'<div>{out}</div>'

    def get_endereco_completo(self):
        return f'{self.endereco}, {self.numero}, {self.bairro}, {self.municipio}, CEP {self.cep} - Telefone: {self.telefone}'

    def get_servidores(self):
        from ..carreira import Servidor

        return Servidor.objects.ativos().filter(setor__uo=self)

    def get_pessoa_juridica(self):
        eh_setor_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        if eh_setor_suap:
            qs = UnidadeOrganizacional.objects.suap()
        else:
            qs = UnidadeOrganizacional.objects.siape()
        pessoa = PessoaJuridica.objects.filter(cnpj=self.cnpj).first()
        if not pessoa:
            campus = qs.filter(sigla=self.sigla).first()
            pessoa = PessoaJuridica.objects.filter(cnpj=campus.cnpj).first()
        if not pessoa:
            from comum.models import Configuracao

            pessoa = PessoaJuridica.objects.filter(pk=Configuracao.get_valor_por_chave('comum', 'instituicao_pessoa_juridica') or 0).first()
        if not pessoa:
            reitoria = qs.filter(sigla=get_sigla_reitoria()).first()
            pessoa = PessoaJuridica.objects.filter(cnpj=reitoria.cnpj).first()
        return pessoa

    @property
    def eh_reitoria(self):
        return self.sigla == get_sigla_reitoria()

    def get_diretor_geral(self, excluir_substituto=False):
        from ..carreira import Servidor

        servidor_funcao_qs = ServidorFuncaoHistorico.objects.filter(
            atividade__codigo__in=[Atividade.DIRETOR_GERAL, Atividade.REITOR],
            setor_suap=self.setor,
            data_inicio_funcao__lte=datetime.datetime.today(),
        )
        servidor_funcao_qs = servidor_funcao_qs.filter(data_fim_funcao__gte=datetime.datetime.today()) | servidor_funcao_qs.filter(
            data_fim_funcao__isnull=True
        )
        if excluir_substituto:
            servidor_funcao_qs = servidor_funcao_qs.exclude(funcao__codigo=Funcao.get_sigla_substituicao_chefia())
        if not servidor_funcao_qs.exists() and self.setor.superior:
            return self.setor.superior.uo.get_diretor_geral()
        return Servidor.objects.filter(pk__in=servidor_funcao_qs.values_list('servidor', flat=True))

    def can_change(self, user):
        return user.has_perm('rh.eh_rh_sistemico') or (user.has_perm('rh.eh_rh_campus') and user.get_relacionamento().setor.uo == self)
