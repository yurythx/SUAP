import base64
import hashlib
import mimetypes

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from djtools.db import models
from djtools.utils import convert_bytes_to_strb64, files, get_datetime_now


class ArquivoUnico(models.ModelPlus):
    # Conteudo é o arquivo em si.
    conteudo = models.FileFieldPlus(
        verbose_name='Arquivo',
        upload_to='private-media/rh/arquivo_unico/',
        # validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv', 'docx', 'doc', 'pdf', 'jpg', 'jpeg', 'png', 'zip', 'txt'])],
        # max_file_size=settings.FILE_UPLOAD_MAX_MEMORY_SIZE,
    )
    # Tipo do conteúdo (content_type). Ex: Application/pdf
    tipo_conteudo = models.CharFieldPlus(verbose_name='Tipo de Conteúdo', max_length=100)
    # Tamanho em bytes do arquivo (size).
    tamanho_em_bytes = models.PositiveIntegerFieldPlus(verbose_name='Tamanho em bytes')
    # Charset
    charset = models.CharFieldPlus(verbose_name='Charset', max_length=50, blank=True, null=True)
    # Hash 512 dos bytes do arquivo. A ideia desse hash é servir para verificação. Não expor ele publicamente.
    hash_sha512 = models.CharFieldPlus(verbose_name='Hash 512', max_length=128, unique=True)
    # Nome original no primeiro upload
    nome_original_primeiro_upload = models.CharFieldPlus(verbose_name='Nome Original do Primeiro Upload', max_length=100)
    # Data do primeiro upload do arquivo.
    data_hora_primeiro_upload = models.DateTimeFieldPlus('Data e Hora do Primeiro Upload')
    # Data de criação do registro.
    # Atenção: Não coloquei o "auto_now_add=True" pra poder forçar o desenvolvedor a fornecer e data e horas atuais
    # e assim poder gerar o hash_sha512_link_id.
    data_hora_criacao_registro = models.DateTimeFieldPlus('Data e Hora da Criação do Registro')
    hash_sha512_link_id = models.CharFieldPlus(verbose_name='Hash 512 Link Id', max_length=128, unique=True)

    class Meta:
        verbose_name = 'Arquivo Único'
        verbose_name_plural = 'Arquivos Únicos'

    @classmethod
    def get_or_create_from_file_bytes(
        cls,
        bytes,
        tipo_conteudo,
        nome_original_primeiro_upload,
        data_hora_primeiro_upload,
        tamanho_em_bytes_para_validar=None,
        hash_sha512_para_validar=None,
    ):
        tamanho_em_bytes = len(bytes)
        if tamanho_em_bytes_para_validar and tamanho_em_bytes != tamanho_em_bytes_para_validar:
            raise ValidationError('O tamanho em bytes informado diverge do tamanho real do arquivo.')

        hash_sha512 = hashlib.sha512(bytes).hexdigest()
        if hash_sha512_para_validar and hash_sha512 != hash_sha512_para_validar:
            raise ValidationError('O hash_sha512 informado diverge do calculado para o arquivo.')

        try:
            created = False
            arquivo = cls.objects.get(hash_sha512=hash_sha512)
            if arquivo:
                return arquivo, created
        except cls.DoesNotExist:
            content_file = ContentFile(bytes)
            # if tamanho_em_bytes_para_validar and content_file.size != tamanho_em_bytes_para_validar:
            #     raise ValidationError('O tamanho em bytes informado diverge do tamanho real do arquivo.')

            created = True
            arquivo = ArquivoUnico()
            arquivo.tipo_conteudo = tipo_conteudo
            arquivo.tamanho_em_bytes = tamanho_em_bytes

            arquivo.hash_sha512 = hash_sha512
            arquivo.data_hora_criacao_registro = get_datetime_now()
            hash_sha512_link_id_str = '[{}],[{}]'.format(arquivo.data_hora_criacao_registro.strftime('%d%m%Y__%H:%M:%S.%f'), arquivo.hash_sha512)
            hash_sha512_link_id_bytes = (hash_sha512_link_id_str).encode('utf-8')
            arquivo.hash_sha512_link_id = hashlib.sha512(hash_sha512_link_id_bytes).hexdigest()

            arquivo.nome_original_primeiro_upload = files.limitar_tamanho_nome_arquivo(nome_original_primeiro_upload, 100)
            arquivo.data_hora_primeiro_upload = data_hora_primeiro_upload

            # Tentando obter a extensão a partir do nome original do arquivo. Se houver uma e ela for válida para o
            # mimetype em questão, então ela será usada. Obs: O mimetypes parece ser bem legal, mas preferi usar
            # essa abordagem porque para um mesmo "mimetype", podem haver "n" extensões, e as vezes a extensão retornada
            # pelo "mimetypes.guess_extension()" acaba sendo uma extensão pouco conhecida ou até mesmo bugada, como é o
            # o caso de "jpe" para o mimetype 'image/jpeg'. Outra vantagem é que usamos a extensão "orginal" definida
            # no nome do arquivo.
            # Exemplos:
            # In[2]: mimetypes.guess_extension('image/jpeg')
            # Out[2]: '.jpe'

            # In[3]: mimetypes.guess_all_extensions('image/jpeg')
            # Out[3]: ['.jpe', '.jpeg', '.jpg']
            #
            # In[4]: mimetypes.guess_extension('video/mpeg')
            # Out[4]: '.m1v'
            #
            # In[5]: mimetypes.guess_all_extensions('video/mpeg')
            # Out[5]: ['.m1v', '.mpa', '.mpe', '.mpeg', '.mpg', '.m2v']
            extensao = '.{}'.format(nome_original_primeiro_upload.split('.')[-1])
            if extensao not in mimetypes.guess_all_extensions(tipo_conteudo):
                extensao = mimetypes.guess_extension(tipo_conteudo)
            nome_arquivo = '{}{}'.format('AU', extensao)
            # Nesse momento, o arquivo é criado em disco. O "save=False" indica que não é para salvar ainda a instancia
            # de ArquivoUnico no banco.
            arquivo.conteudo.save(nome_arquivo, content_file, save=False)

            try:
                # Tentando persistir uma instância de ArquivoUnico.
                arquivo.save()
                # arquivo.delete()
                # raise Exception('Proocando rollback...')
                return arquivo, created
            except Exception as e:
                # Em caso de erro, o arquivo que foi persitido em disco é removido, para não gerar lixo.
                arquivo.conteudo.delete(save=False)
                raise e

    @classmethod
    def get_or_create_from_file_strb64(
        cls,
        strb64,
        tipo_conteudo,
        nome_original_primeiro_upload,
        data_hora_primeiro_upload,
        tamanho_em_bytes_para_validar=None,
        hash_sha512_para_validar=None,
    ):
        bytes_b64 = strb64.encode('utf-8')
        bytes = base64.b64decode(bytes_b64)
        return cls.get_or_create_from_file_bytes(
            bytes,
            tipo_conteudo,
            nome_original_primeiro_upload,
            data_hora_primeiro_upload,
            tamanho_em_bytes_para_validar,
            hash_sha512_para_validar,
        )

    def get_conteudo_as_bytes(self):
        bytes = self.conteudo.file.read()
        return bytes

    def get_conteudo_as_strb64(self):
        return convert_bytes_to_strb64(self.get_conteudo_as_bytes())


class AbstractVinculoArquivoUnico(models.ModelPlus):
    arquivo_unico = models.ForeignKeyPlus('rh.ArquivoUnico', on_delete=models.PROTECT)
    nome_original = models.CharFieldPlus(verbose_name='Nome Original', max_length=100)
    nome_exibicao = models.CharFieldPlus(verbose_name='Nome para Exibição', max_length=255, blank=True, null=True)
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=255)
    data_hora_upload = models.DateTimeFieldPlus('Data e Hora do Upload')
    data_hora_criacao_registro = models.DateTimeFieldPlus('Data e Hora da Criação do Registro', auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ('-data_hora_upload',)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        self.clean()
        super().save(force_insert, force_update, using, update_fields)

    def clean(self):
        if self.nome_original:
            self.nome_original = files.limitar_tamanho_nome_arquivo(self.nome_original, 100)

    def add_extensao_ao_nome_exibicao_com_base_no_nome_original(self):
        extensao = '.{}'.format(self.nome_original.split('.')[-1])
        self.nome_exibicao = f'{self.nome_exibicao}{extensao}'
