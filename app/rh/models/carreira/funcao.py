from django.apps.registry import apps
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from djtools.db import models
from rh.managers import FuncaoManager

CACHED_FUNCOES_CHEFIA = 'funcoes_chefia'
CACHED_FUNCAO_CHEFIA_TIME = 24 * 3600


class Funcao(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']

    # Constantes em destaque:
    # 1 - O SUAP deve consumir essas constantes nos vários pontos do código (o consumidor usa a constante, e isso é o correto);
    #     Uso correto..: .filter(funcao__codigo=Funcao.CODIGO_CD);
    # 2 - Evitar o uso dos valores dessas constantes diretamente (o consumidor não usa a constante, e isso é incorreto);
    #     Uso incorreto: .filter(funcao__codigo='CD');
    # 3 - As funções com os códigos CODIGO_CD e CODIGO_FG serão SEMPRE funções de chefia (funcao.eh_funcao_chefia=True).
    #     Além desses códigos, existem outros códigos fixos (ver get_codigos_funcao_chefia_fixos). O 'save' vai garantir
    #     que o atributo 'eh_funcao_chefia' seja sempre 'True' para esses códigos fixos.
    CODIGO_CD = 'CD'
    CODIGO_FG = 'FG'
    CODIGO_ESTAGIARIO = 'ETG'

    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    excluido = models.BooleanField(default=False)
    funcao_suap = models.BooleanField('Função SUAP', default=False, help_text='Essa função pode ser gerenciada dentro do SUAP?')
    funcao_siape = models.BooleanField('Função SIAPE', default=True, help_text='Essa função tem origem no SIAPE?')
    eh_funcao_chefia = models.BooleanField(
        'É Função de Chefia', default=False, help_text='Permitirá gerenciar dados e informações dos servidores como chefe do setor.'
    )
    ch_semanal = models.IntegerField(
        'Carga Horária Semanal', null=True, blank=True, help_text='Em horas. Se não informada, será usada a carga horária do servidor.'
    )

    objects = FuncaoManager()

    class Meta:
        db_table = 'funcao'
        verbose_name = 'Função'
        verbose_name_plural = 'Funções'

    def save(self, *args, **kwargs):
        # há códigos de funções fixos que forçam a função a ser de chefia (manter compatibilidade)
        if self.codigo in Funcao.get_codigos_funcao_chefia_fixos():
            self.eh_funcao_chefia = True
        super().save(*args, **kwargs)
        cache.delete(CACHED_FUNCOES_CHEFIA)

    def __str__(self):
        return self.nome

    @classmethod
    def get_codigos_funcao_chefia(cls):
        funcoes_chefia = cache.get(CACHED_FUNCOES_CHEFIA, local_ttl=3600)
        if funcoes_chefia:
            return funcoes_chefia
        codigos = []
        funcoes_de_chefia = Funcao.objects.filter(eh_funcao_chefia=True).distinct('codigo')
        codigos += funcoes_de_chefia.values_list('codigo', flat=True)
        codigos += Funcao.get_codigos_funcao_chefia_fixos()
        codigos = list(set(codigos))
        cache.set(CACHED_FUNCOES_CHEFIA, codigos, CACHED_FUNCAO_CHEFIA_TIME)
        return codigos

    @classmethod
    def get_codigos_funcao_chefia_fixos(cls):
        codigos = []

        # códigos baseados em constantes específicas/destacadas (manter compatibilidade)
        codigos += [cls.CODIGO_CD, cls.CODIGO_FG]

        # código de função de substituição de chefia (via configuração; manter compatibilidade)
        sigla_substituicao_chefia = cls.get_sigla_substituicao_chefia()
        if sigla_substituicao_chefia:
            codigos.append(sigla_substituicao_chefia)

        # código de função de apoio à gestão (via configuração se apoio à gestão for considerado função de chefia; manter compatibilidade)
        sigla_funcao_apoio_a_gestao_se_considerado_chefia = cls.get_sigla_funcao_apoio_a_gestao_se_considerado_chefia()
        if sigla_funcao_apoio_a_gestao_se_considerado_chefia:
            codigos.append(sigla_funcao_apoio_a_gestao_se_considerado_chefia)

        return list(set(codigos))

    @classmethod
    def get_sigla_substituicao_chefia(cls):
        Configuracao = apps.get_model('comum', 'configuracao')
        return Configuracao.get_valor_por_chave(app='rh', chave='sigla_funcao_substituicao_chefia')

    @classmethod
    def get_sigla_funcao_apoio_a_gestao(cls):
        Configuracao = apps.get_model('comum', 'configuracao')
        return Configuracao.get_valor_por_chave(app='rh', chave='sigla_funcao_apoio_gestao')

    @classmethod
    def get_sigla_funcao_apoio_a_gestao_se_considerado_chefia(cls):
        Configuracao = apps.get_model('comum', 'configuracao')
        if Configuracao.get_valor_por_chave(app='rh', chave='fag_considerado_chefia'):
            return Configuracao.get_valor_por_chave(app='rh', chave='sigla_funcao_apoio_gestao')
        return None

    @property
    def eh_substituicao_chefia(self):
        return self.codigo == Funcao.get_sigla_substituicao_chefia()


@receiver((post_delete, post_save), sender=Funcao)
def invalidar_funcoes_chefia_cache(sender, instance, **kwargs):
    """
    Invalida a cache das funções de chefia
    """
    cache.delete(CACHED_FUNCOES_CHEFIA)
