import os
from uuid import uuid4

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from djtools.db import models

PRIVATE_ROOT_DIR = 'private-media/arquivo'


class TipoArquivo(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']

    descricao = models.CharFieldPlus('Descrição', unique=True)

    def __str__(self):
        tipo_descricao = self.descricao
        #
        tipo_classificacao = ''
        processo = self.processo
        funcao = self.funcao
        if processo:
            tipo_classificacao = processo
        if funcao:
            tipo_classificacao = f'{tipo_classificacao} - {funcao}'
        #
        if tipo_classificacao:
            return f'{tipo_descricao} ({tipo_classificacao})'
        else:
            return tipo_descricao

    @property
    def processo(self):
        if self.processo_set.all().exists():
            return self.processo_set.all()[0]
        return None

    @property
    def funcao(self):
        processo = self.processo
        if processo:
            return processo.funcao
        return None

    class Meta:
        verbose_name = 'Tipo de Arquivo'
        verbose_name_plural = 'Tipos de Arquivo'
        ordering = ('descricao',)

    def get_caminho(self):
        """
        Retorna a lista de setores que fazem a hierarquia do setor desde o setor
        raiz.
        """
        caminho = [self.processo]
        processo_atual = self.processo.superior
        while processo_atual is not None:
            caminho.append(processo_atual)
            processo_atual = processo_atual.superior
        caminho.reverse()
        return caminho

    def get_caminho_processo_as_html(self):
        from django.utils.safestring import mark_safe

        caminho = self.get_caminho()
        caminho_html = []
        for processo in caminho:
            caminho_html.append(f'<span title="{processo.descricao}">{processo.descricao}</span>')
        return mark_safe(' &rarr; '.join(caminho_html))

    def get_ext_combo_template(self):
        template = f"""
                <h3>{self.descricao}</h3>
                <p class="disabled">Função: {self.funcao}</p>
                <p class="disabled">Processos: {self.get_caminho_processo_as_html()}</p>
                    """
        return template


class Funcao(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', unique=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Função'
        verbose_name_plural = 'Funções'


class Processo(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']

    descricao = models.CharFieldPlus('Descrição', unique=True)
    tipos_arquivos = models.ManyToManyFieldPlus(TipoArquivo, verbose_name='Tipos Arquivos')
    superior = models.ForeignKeyPlus('self', null=True, blank=True, verbose_name='Processo Superior', on_delete=models.CASCADE)
    funcao = models.ForeignKeyPlus(Funcao, null=True, blank=True, verbose_name='Função', on_delete=models.CASCADE)

    def __str__(self):
        return self.descricao

    @property
    def descricao_completa(self):
        descricao_superior = ''
        if self.superior:
            descricao_superior = f'{self.superior.descricao_completa}'
        if descricao_superior:
            descricao = f'{descricao_superior} - {self.descricao}'
        else:
            descricao = f'{self.descricao}'
        return descricao

    def filhos(self):
        return Processo.objects.filter(superior=self)

    class Meta:
        verbose_name = 'Processo/Rotina Rh para o Servidor'
        verbose_name_plural = 'Processos/Rotinas Rh para o Servidor'


def file_upload_to(instance, filename):
    content_type = str(instance.content_type).lower()
    object_id = instance.object_id
    path = f'{PRIVATE_ROOT_DIR}/{content_type}/{object_id}'
    ext = filename.split('.')[-1]
    # get filename
    if instance.pk:
        filename = f'{instance.pk}.{ext}'
    else:
        # set filename as random string
        filename = f'{uuid4().hex}.{ext}'
        # return the whole path to the file
        return os.path.join(path, filename)


class ArquivoManager(models.EncryptedPKModelManager):
    pass


class Arquivo(models.EncryptedPKModel):
    STATUS_PENDENTE = 0
    STATUS_IDENTIFICADO = 1
    STATUS_VALIDADO = 2
    STATUS_IMAGEM_REJEITADA = 3
    STATUS_CHOICES = [
        [STATUS_PENDENTE, 'Pendente'],
        [STATUS_IDENTIFICADO, 'Identificado'],
        [STATUS_VALIDADO, 'Validado'],
        [STATUS_IMAGEM_REJEITADA, 'Imagem Rejeitada'],
    ]

    upload_em = models.DateTimeField(auto_now_add=True)
    upload_por = models.ForeignKeyPlus(
        'comum.User', on_delete=models.CASCADE, related_name='arquivo_upload_por', null=True, blank=True, editable=False
    )
    identificado_em = models.DateTimeField(null=True)
    validado_em = models.DateTimeField(null=True)
    validado_por = models.ForeignKeyPlus(
        'comum.User', on_delete=models.CASCADE, related_name='arquivo_validado_por', null=True, blank=True, editable=False
    )
    identificado_por = models.ForeignKeyPlus(
        'comum.User', on_delete=models.CASCADE, related_name='arquivo_identificado_por', null=True, blank=True, editable=False
    )
    justificativa_rejeicao = models.CharFieldPlus('Justificativa Rejeição Imagem', blank=True)
    nome = models.CharFieldPlus('Nome do Arquivo')
    content_type = models.ForeignKeyPlus(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    objeto = GenericForeignKey('content_type', 'object_id')
    tipo_arquivo = models.ForeignKeyPlus(TipoArquivo, on_delete=models.CASCADE, null=True)
    status = models.PositiveIntegerField('Status', default=0, choices=STATUS_CHOICES)
    file = models.FileFieldPlus(upload_to=file_upload_to)

    processo_protocolo = models.ForeignKeyPlus('protocolo.Processo', on_delete=models.CASCADE, null=True, blank=True)

    objects = ArquivoManager()

    def __str__(self):
        return '{} - {}'.format(self.nome, self.tipo_arquivo or ' ')

    def dono(self):
        return self.content_type.get_object_for_this_type(pk=self.object_id)

    class Meta:
        verbose_name = 'Arquivo'
        verbose_name_plural = 'Arquivos'

        permissions = (
            ('pode_fazer_upload_arquivo', 'Pode realizar o upload de arquivos'),
            ('pode_validar_arquivo', 'Pode atestar a validade do arquivo'),
            ('pode_identificar_arquivo', 'Pode identificar do arquivo'),
        )

    """
    Esse metodo retorna todos os arquivos vinculados a instancia passada.
    """

    @classmethod
    def get_arquivos_por_instancia(self, instancia):
        return Arquivo.objects.filter(content_type=ContentType.objects.get_for_model(instancia.__class__), object_id=instancia.pk)
