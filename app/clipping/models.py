from djtools.db import models
from djtools.utils import to_ascii
from rh.models import UnidadeOrganizacional


class Fonte(models.ModelPlus):
    nome = models.CharField(max_length=50, verbose_name='Descrição')
    editorial = models.CharField(max_length=50, verbose_name='Editorial')
    link = models.CharField(max_length=150, verbose_name='Link')
    ativo = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Fonte'
        verbose_name_plural = 'Fontes'

    def __str__(self):
        return self.nome


class Classificacao(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)
    visivel = models.BooleanField('Visível', default=True)

    class Meta:
        verbose_name = 'Classificação'
        verbose_name_plural = 'Classificações'

    def __str__(self):
        return self.descricao


class Veiculo(models.ModelPlus):
    nome = models.CharField(max_length=50, verbose_name='Nome', unique=True)

    class Meta:
        verbose_name = 'Veículo'
        verbose_name_plural = 'Veículos'

    def __str__(self):
        return self.nome


class Editorial(models.ModelPlus):
    nome = models.CharField(max_length=50, verbose_name='Nome', unique=True)

    class Meta:
        verbose_name = 'Editorial'
        verbose_name_plural = 'Editoriais'

    def __str__(self):
        return self.nome


class PalavraChave(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', unique=True)

    class Meta:
        verbose_name = 'Palavra-Chave'
        verbose_name_plural = 'Palavras-Chave'

    def __str__(self):
        return self.descricao


class Publicacao(models.ModelPlus):
    data = models.DateFieldPlus()
    veiculo = models.ForeignKeyPlus(Veiculo, verbose_name='Veículo', on_delete=models.CASCADE)
    editorial = models.ForeignKeyPlus(
        Editorial,
        verbose_name='Editorial',
        null=True,
        blank=True,
        help_text='Categoria da notícia. Ex: Política, Saúde, Educação',
        on_delete=models.CASCADE,
    )
    titulo = models.CharField(max_length=255, verbose_name='Título', blank=True, db_index=True)
    palavras_chaves = models.ManyToManyField(PalavraChave, verbose_name='Palavras-Chaves')
    classificacao = models.ForeignKeyPlus(Classificacao, verbose_name='Classificação', null=True, on_delete=models.CASCADE)
    uos = models.ManyToManyFieldPlus(UnidadeOrganizacional, verbose_name='Campus', blank=True)

    def get_link(self):
        """
        Retorna o link caso self seja PublicacaoDigital ou PublicacaoEletornica
        """
        try:
            return self.publicacaodigital.link
        except Exception:
            try:
                return self.publicacaoeletronica.link or self.publicacaoeletronica.arquivo.url
            except Exception:
                try:
                    return self.publicacaoimpressa.arquivo.url
                except Exception:
                    return ''

    def __str__(self):
        return self.titulo


class PublicacaoDigital(Publicacao):
    subtitulo = models.CharField('Subtítulo', max_length=255, blank=True)
    imagem = models.ImageFieldPlus(upload_to='upload/clipping/digital/', null=True, blank=True)
    texto = models.TextField()
    link = models.CharField('Link', max_length=255)

    def get_palavras_chaves(self):
        ids = []
        for palavra_chave in PalavraChave.objects.all():
            if (
                to_ascii(palavra_chave.descricao).lower() in to_ascii(self.titulo).lower()
                or to_ascii(palavra_chave.descricao).lower() in to_ascii(self.texto).lower()
            ):
                ids.append(palavra_chave.id)
        return PalavraChave.objects.filter(id__in=ids)

    class Meta:
        verbose_name = 'Publicação Digital'
        verbose_name_plural = 'Publicações Digitais'

    def get_categoria(self):
        return 'Digital'


class PublicacaoImpressa(Publicacao):
    subtitulo = models.CharField(max_length=50, verbose_name='Subtítulo', blank=True)
    arquivo = models.FileFieldPlus(upload_to='upload/clipping/impresso/', create_date_subdirectories=True, null=True, blank=True)
    pagina = models.CharField('Página', max_length=255)
    colunista = models.CharField('Colunista', max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Publicação Impressa'
        verbose_name_plural = 'Publicações Impressas'

    def get_categoria(self):
        return 'Impressa'


class PublicacaoEletronica(Publicacao):
    programa = models.CharField(max_length=50, verbose_name='Programa', blank=True)
    arquivo = models.FileFieldPlus(upload_to='upload/clipping/eletronico/', create_date_subdirectories=True, null=True, blank=True)
    link = models.CharField(max_length=150, verbose_name='Link', blank=True)

    class Meta:
        verbose_name = 'Publicação Eletrônica'
        verbose_name_plural = 'Publicações Eletrônicas'

    def get_categoria(self):
        return 'Eletrônica'
