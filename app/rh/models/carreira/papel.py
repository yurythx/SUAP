from djtools.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Papel(models.ModelPlus):
    TIPO_PAPEL_CARGO = 'cargo'
    TIPO_PAPEL_FUNCAO = 'funcao'
    TIPO_PAPEL_COMISSAOCONSELHO = 'comissaoconselho'
    TIPO_PAPEL_OCUPACAO = 'ocupacao'  # usado pelos prestadores de serviço
    TIPO_PAPEL_DISCENTE = 'discente'  # usado pelos alunos ativos = matriculados
    TIPO_PAPEL_USUARIOEXTERNO = 'usuarioexterno'  # usado pelos usuários externos (proxy from PrestadorServico)

    TIPOS_PAPEIS = [
        (TIPO_PAPEL_CARGO, TIPO_PAPEL_CARGO),
        (TIPO_PAPEL_FUNCAO, TIPO_PAPEL_FUNCAO),
        (TIPO_PAPEL_COMISSAOCONSELHO, TIPO_PAPEL_COMISSAOCONSELHO),
        (TIPO_PAPEL_OCUPACAO, TIPO_PAPEL_OCUPACAO),
        (TIPO_PAPEL_DISCENTE, TIPO_PAPEL_DISCENTE),
        (TIPO_PAPEL_USUARIOEXTERNO, TIPO_PAPEL_USUARIOEXTERNO),
    ]
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo', on_delete=models.CASCADE)
    tipo_papel = models.CharField('Tipo de papel', default=TIPO_PAPEL_CARGO, choices=TIPOS_PAPEIS, null=False, blank=False, max_length=255)

    # TODO: Com o uso da GenericKey, o campo descricao agora armazena uma informação redundate (nome do CargoEmprego /
    # codigo - nome da Funcao). Ver com Lucas se é interessante manter essa informação redundante, a título de "histórico",
    # ou se esse campo pode ser descartado. Obs: O mesmo ocorre com o campo detalhamento.
    descricao = models.TextField('Descrição', null=False, blank=False)
    detalhamento = models.TextField('Detalhamento', blank=False)
    portaria = models.CharField('portaria', null=False, blank=False, max_length=50)
    data_inicio = models.DateFieldPlus('Data de início', null=True, blank=False)
    data_fim = models.DateFieldPlus('Data fim', null=True)

    setor_suap = models.ForeignKeyPlus('rh.Setor', null=True, blank=False, related_name='papel_servidor_setor_suap', on_delete=models.CASCADE)

    # Dados do tipo de papel exercido pelo servidor. Por enquanto só dois tipos de papéis estão sendo
    # carregados: CargoEmprego e Funcao. Para abstrair isso está sendo usado o GenericKey.
    papel_limit_choices = (
        models.Q(app_label='rh', model='CargoEmprego') | models.Q(app_label='rh', model='Funcao') | models.Q(app_label='comum', model='Ocupacao')
    )
    papel_content_type = models.ForeignKeyPlus(
        ContentType, verbose_name='Papel (Type)', limit_choices_to=papel_limit_choices, null=False, blank=False, on_delete=models.CASCADE
    )
    papel_content_id = models.PositiveIntegerField(verbose_name='Papel (Id)', null=False)
    papel_content_object = GenericForeignKey('papel_content_type', 'papel_content_id')

    def __str__(self):
        return self.detalhamento

    class Meta:
        verbose_name = 'Papel'
        verbose_name_plural = 'Papéis'
        unique_together = ('vinculo', 'papel_content_type', 'papel_content_id', 'data_inicio')
