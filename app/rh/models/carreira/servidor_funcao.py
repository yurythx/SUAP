from django.apps.registry import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models.functions import Concat
from django.db.transaction import atomic

from djtools.db import models
from djtools.db.models import QuerySet
from djtools.utils import get_datetime_now
from rh.managers import ServidorFuncaoHistoricoManager

from .funcao import Funcao
from .papel import Papel


class ServidorFuncaoHistorico(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, on_delete=models.CASCADE)
    data_inicio_funcao = models.DateFieldPlus(null=False, blank=False, db_index=True, verbose_name='Data de Início da Função')
    data_fim_funcao = models.DateFieldPlus(null=True, blank=True, verbose_name='Data de Fim da Função')
    atividade = models.ForeignKeyPlus('rh.Atividade', null=True, blank=True, on_delete=models.CASCADE)
    funcao = models.ForeignKeyPlus('rh.Funcao', null=False, on_delete=models.CASCADE, verbose_name='Função')
    nivel = models.CharField(max_length=4, null=True, blank=True, verbose_name='Nível')
    setor = models.ForeignKeyPlus('rh.Setor', null=False, blank=False, on_delete=models.CASCADE)
    setor_suap = models.ForeignKeyPlus(
        'rh.Setor', null=True, blank=True, related_name='setor_suap', on_delete=models.CASCADE, verbose_name='Setor SUAP'
    )
    nome_amigavel = models.CharFieldPlus(verbose_name='Nome Amigável', blank=True, default='')
    atualiza_pelo_extrator = models.BooleanField(verbose_name='Atualizar pelo extrator', default=True)

    objects = ServidorFuncaoHistoricoManager()

    class Meta:
        verbose_name = 'Histórico de Função do Servidor'
        verbose_name_plural = 'Histórico de Funções do Servidor'

    def get_absolute_url(self):
        return f'/admin/rh/servidorfuncaohistorico/{self.pk}/view/'

    @classmethod
    def codigos_e_niveis_liberados_frequencia(cls) -> list[str]:
        """dados na configuração "rh.funcoes_codigos_e_niveis_liberados_frequencia"
        retorna uma lista de strings: ["CD-1", "CD-2", "CD-3", "CD-0001", "AB-4"]"""
        Configuracao = apps.get_model('comum', 'configuracao')
        codigos_e_niveis = Configuracao.get_valor_por_chave(app='rh', chave='funcoes_codigos_e_niveis_liberados_frequencia')
        try:
            return f'{codigos_e_niveis}'.split(',')
        except Exception:
            return []

    @classmethod
    def get_liberados_frequencia(cls, from_queryset: QuerySet[ServidorFuncaoHistorico]) -> QuerySet[ServidorFuncaoHistorico]:
        return from_queryset.annotate(
            codigo_e_nivel=Concat(
                'funcao__codigo',
                models.Value('-'),
                'nivel',  # "codigo-nivel"
                output_field=models.CharField(),
            )
        ).filter(setor_suap__isnull=False, codigo_e_nivel__in=ServidorFuncaoHistorico.codigos_e_niveis_liberados_frequencia())

    @property
    def eh_liberado_frequencia(self) -> bool:
        return f'{self.funcao.codigo}-{self.nivel}' in ServidorFuncaoHistorico.codigos_e_niveis_liberados_frequencia()

    def __str__(self):
        data_fim = self.data_fim_funcao.strftime('%d/%m/%Y') if self.data_fim_funcao else 'Atual'
        return '{} : {} - Setor SIAPE: {} - de {} à {}'.format(
            self.funcao_display, self.servidor, self.setor, self.data_inicio_funcao.strftime('%d/%m/%Y'), data_fim
        )

    @property
    def funcao_display(self):
        return '{}{} - {}'.format(self.funcao and self.funcao.codigo or '', self.nivel or '', self.setor_suap or '')

    @property
    def get_nome_amigavel(self):
        return f'{self.nome_amigavel or (self.atividade and self.atividade.nome) or ""} {self.funcao_display}'

    @property
    def estah_ativa(self):
        hoje = get_datetime_now().date()
        if self.data_inicio_funcao > hoje:
            return False
        return not self.data_fim_funcao or self.data_fim_funcao >= hoje

    @property
    def eh_funcao_reitor(self):
        return self.funcao.codigo == Funcao.CODIGO_CD and self.nivel in ('1', '0001')

    @classmethod
    def permite_multiplas_funcoes(cls):
        Configuracao = apps.get_model('comum', 'configuracao')
        return Configuracao.get_valor_por_chave(app='rh', chave='permite_multiplas_funcoes')

    def clean(self):
        permite_multiplas_funcoes = ServidorFuncaoHistorico.permite_multiplas_funcoes()
        if not permite_multiplas_funcoes and hasattr(self, 'servidor'):
            query = ServidorFuncaoHistorico.objects.filter(servidor=self.servidor, data_inicio_funcao=self.data_inicio_funcao)
            if not self.id and query.exists():
                raise ValidationError('Histórico de Função do Servidor com este Servidor e Data de Início da Função já existe.')

    @atomic()
    def save(self, *args, **kwargs):
        from ..carreira import Servidor

        self.full_clean()

        configuracao_setor = settings.TIPO_ARVORE_SETORES
        if configuracao_setor == 'SIAPE':
            self.setor_suap = self.setor

        super().save(*args, **kwargs)

        if Papel.objects.filter(papel_content_id__isnull=True).exists():
            raise Exception(
                'Existem registros de Papel sem CargoEmprego ou Funcao definidos. '
                'Execute o command "importar_funcao_servidor_atualizar_genericfk" para '
                'resolver o problema.'
            )

        if self.nome_amigavel:
            detalhamento = f'{self.nome_amigavel} - {self.funcao_display}'
        elif self.atividade:
            detalhamento = f'{self.atividade.nome} - {self.funcao_display}'
        else:
            detalhamento = self.funcao_display
        kwargs = {
            'detalhamento': detalhamento,
            'portaria': '',
            'descricao': f'{self.funcao.nome} - {self.funcao.codigo}',
            'setor_suap': self.setor_suap,
            'data_fim': self.data_fim_funcao,
            'tipo_papel': Papel.TIPO_PAPEL_FUNCAO,
        }
        servidor = Servidor.objects.get(pk=self.servidor.pk)
        _papel, _criou = Papel.objects.update_or_create(
            vinculo=servidor.get_vinculo(),
            data_inicio=self.data_inicio_funcao,
            papel_content_type=ContentType.objects.get_for_model(self.funcao),
            papel_content_id=self.funcao.id,
            defaults=kwargs,
        )
