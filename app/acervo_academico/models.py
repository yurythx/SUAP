import logging
import re
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from acervo_academico.utils import validar_aluno, validar_nome_do_arquivo
from djtools.db import models
from djtools.db.models import Count
from djtools.utils import get_datetime_now
from edu.models import AlunoArquivo, TipoAlunoArquivo
from microsoft.services import SharepointService
from rh.models import UnidadeOrganizacional

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


class RotinaImportacao(models.ModelPlus):
    CRIADA = 1
    EM_PROCESSAMENTO = 2
    FINALIZADA = 3
    FALHOU = 4

    STATUS_CHOICES = [
        (CRIADA, 'Criada'),
        (EM_PROCESSAMENTO, 'Em Processamento'),
        (FINALIZADA, 'Finalizada'),
        (FALHOU, 'Falhou'),
    ]

    url_diretorio_raiz = models.URLField('URL do diretório no Sharepoint', max_length=500)
    nome_do_projeto = models.CharField('Nome do projeto', null=True, blank=True)

    data_criacao = models.DateTimeField('Data de criação', auto_now_add=True)
    ultima_execucao = models.DateTimeFieldPlus('Última execução', null=True, blank=True)
    status = models.PositiveIntegerFieldPlus('Status', choices=STATUS_CHOICES, default=CRIADA)

    # Metadados obtidos da URL
    dominio_site = models.CharField('Domínio', null=True, blank=True)
    caminho_projeto = models.CharField('Caminho do projeto')
    diretorio_raiz = models.CharField('Diretório raiz', max_length=400)

    class Meta:
        verbose_name = 'Rotina de Importação'
        verbose_name_plural = 'Rotinas de Importação'
        unique_together = (
            'dominio_site',
            'caminho_projeto',
            'diretorio_raiz',
        )
        ordering = ('-data_criacao',)

    def __str__(self):
        return f'Rotina #{self.id} - {self.nome_do_projeto}' if self.nome_do_projeto else f'Rotina #{self.id}'

    def save(self, *args, **kwargs):
        self.dominio_site, self.caminho_projeto, self.diretorio_raiz = self.decodificar_url_raiz()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('acervo_visualizar_rotina', args=[self.id])

    def get_status(self):
        if self.status == RotinaImportacao.FINALIZADA and self.houve_falhas:
            return 'Finalizada com falhas'
        return self.get_status_display()

    def get_campi(self):
        return UnidadeOrganizacional.objects.filter(pk__in=self.itens.values_list('campus_id', flat=True)).distinct()

    def get_quantitativo_de_itens_por_campus(self, campus: int | UnidadeOrganizacional = None, status: int | list[int] | None = None):
        return self.itens.values('campus_id', 'campus__sigla', 'status').annotate(quantidade=Count('id')).order_by('campus__sigla', 'status')

    def decodificar_url_raiz(self):
        """
        Extrai da URL os componentes "hostname", "caminho do projeto (sites/...)" e "caminho para o diretório raiz"
        e os retorna como uma tupla (nessa mesma ordem).

        Espera-se uma URL no formato:
        https://<domínio_do_sharepoint>/sites/<nome_do_projeto>/[...]?id=/sites/<nome_do_projeto>/Shared Documents/<diretorio raiz>[&<outras queries>]
        """
        parsed_url = urlparse(self.url_diretorio_raiz)
        hostname = parsed_url.netloc
        query_id = parse_qs(parsed_url.query).get('id')

        if not query_id:
            raise ValidationError('A URL do diretório raiz não contém o argumento "id". Verifique se você informou a URL correta.')

        caminho_absoluto_diretorio = query_id[0].strip('/')

        caminho_projeto = re.match(r'sites/[^/]+', caminho_absoluto_diretorio).group(0)
        diretorio_raiz = caminho_absoluto_diretorio.removeprefix(caminho_projeto).removeprefix('/Shared Documents/')

        return hostname, caminho_projeto, diretorio_raiz

    def em_processamento(self):
        return self.status == RotinaImportacao.EM_PROCESSAMENTO

    def finalizada(self):
        return self.status == RotinaImportacao.FINALIZADA

    def pode_processar(self, user):
        return user is not None and user.has_perm('acervo_academico.change_rotinaimportacao') and user.has_perm('edu.add_alunoarquivo')

    @property
    def houve_falhas(self):
        return self.itens.filter(status=ItemRotina.FALHOU).exists()

    def consultar_nome_do_projeto(self):
        sp_service = SharepointService.get_instance(self.dominio_site, self.caminho_projeto, self.diretorio_raiz)
        return sp_service.get_dados_do_site(select='displayName')['displayName']


class ItemRotina(models.ModelPlus):
    AGUARDANDO_PROCESSAMENTO = 1
    NA_FILA = 2
    EM_PROCESSAMENTO = 3
    PROCESSADO = 4
    FALHOU = 5
    SIMULADO = 99

    STATUS_CHOICES = [
        (AGUARDANDO_PROCESSAMENTO, 'Aguardando processamento'),
        (NA_FILA, 'Na fila'),
        (EM_PROCESSAMENTO, 'Em processamento'),
        (PROCESSADO, 'Processado'),
        (FALHOU, 'Falhou'),
        (SIMULADO, 'Simulado'),
    ]

    rotina = models.ForeignKeyPlus(RotinaImportacao, verbose_name='Rotina', related_name='itens')
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', null=True)
    aluno = models.ForeignKeyPlus('edu.Aluno', null=True)

    # Dados do arquivo no Sharepoint
    id_arquivo = models.CharFieldPlus('ID do arquivo')
    nome_arquivo = models.CharFieldPlus('Nome do arquivo')
    url_arquivo = models.CharFieldPlus('URL do arquivo', max_length=500)
    content_type_arquivo = models.CharFieldPlus('Tipo do arquivo')
    tamanho_arquivo = models.PositiveIntegerFieldPlus('Tamanho do arquivo em bytes')

    # Dados do processamento
    inicio_execucao = models.DateTimeFieldPlus('Início da execução', null=True)
    status = models.PositiveIntegerFieldPlus('Status', choices=STATUS_CHOICES, default=AGUARDANDO_PROCESSAMENTO)
    detalhes_execucao = models.TextField('Detalhes da execução', default='')

    # Arquivo salvo no Suap
    aluno_arquivo = models.ForeignKeyPlus('edu.AlunoArquivo', verbose_name='Arquivo criado no SUAP', null=True)

    class Meta:
        verbose_name = 'Item da rotina de importação'
        verbose_name_plural = 'Itens da rotina de importação'
        unique_together = ('rotina', 'id_arquivo')
        ordering = ('campus__sigla', 'nome_arquivo')

    def get_absolute_url(self):
        return reverse('acervo_visualizar_item_rotina', args=[self.id])

    @property
    def processado(self):
        return self.status in [ItemRotina.PROCESSADO, ItemRotina.SIMULADO]

    def processar(self, apenas_simular=False):
        logger.debug(f'Processando o arquivo {self.nome_arquivo} (ID {self.id_arquivo}) da {self.rotina}.')

        self.inicio_execucao = get_datetime_now()
        self.status = ItemRotina.EM_PROCESSAMENTO
        self.save()

        if self.aluno is None:
            try:
                validar_nome_do_arquivo(self.nome_arquivo)
                _matricula, aluno = validar_aluno(self.nome_arquivo, self.campus)
                self.aluno = aluno
            except ValidationError as e:
                self.status = ItemRotina.FALHOU
                self.detalhes_execucao = str(' / '.join(e.messages))
                self.save()
                return

        sp_service = SharepointService.get_instance(self.rotina.dominio_site, self.rotina.caminho_projeto, self.rotina.diretorio_raiz)
        try:
            if apenas_simular:
                conteudo_arquivo = b'Arquivo de teste.'
                tipo_conteudo = 'text/plain'
                tamanho_para_validar = len(conteudo_arquivo)
            else:
                conteudo_arquivo = sp_service.baixar_arquivo(self.id_arquivo)
                tipo_conteudo = self.content_type_arquivo
                tamanho_para_validar = self.tamanho_arquivo
            arquivo, _criado, _, _ = AlunoArquivo.update_or_create_from_file_bytes(
                bytes=conteudo_arquivo,
                tipo_conteudo=tipo_conteudo,
                data_hora_upload=get_datetime_now(),
                nome_original=self.nome_arquivo,
                nome_exibicao='Dossiê do aluno',
                descricao=f'Documentação de {self.aluno}.',
                aluno=self.aluno,
                observacao='Importado automaticamente pelo módulo de Acervo Acadêmico',
                tipo=TipoAlunoArquivo.objects.get(nome=TipoAlunoArquivo.DOSSIE),
                tamanho_em_bytes_para_validar=tamanho_para_validar,
                aluno_arquivo_id=self.aluno_arquivo.pk if self.aluno_arquivo else None,
            )

            self.aluno_arquivo = arquivo
            self.status = ItemRotina.PROCESSADO if not apenas_simular else ItemRotina.SIMULADO
            self.detalhes_execucao = f'{"Simulação realizada" if apenas_simular else "Arquivo importado"} com sucesso em {get_datetime_now()}.'
            self.save()

        except Exception as e:
            self.status = ItemRotina.FALHOU
            self.detalhes_execucao = str(e)
            self.save()


class LogRotina(models.ModelPlus):
    INFO = 1
    ERRO = 2
    TIPO_CHOICES = [
        (INFO, 'Info'),
        (ERRO, 'Erro'),
    ]

    rotina = models.ForeignKeyPlus(RotinaImportacao, verbose_name='Rotina', related_name='logs')
    tipo = models.PositiveIntegerFieldPlus('Tipo', choices=TIPO_CHOICES)
    data_hora = models.DateTimeFieldPlus('Data e hora', auto_now_add=True)
    mensagem = models.TextField('Mensagem')

    class Meta:
        verbose_name = 'Log da rotina de importação'
        verbose_name_plural = 'Logs da rotina de importação'
        ordering = ('data_hora',)

    def __str__(self):
        return f'Log #{self.id} da {self.rotina}'

    @classmethod
    def registrar_log(cls, tipo, rotina, mensagem):
        LogRotina.objects.create(rotina=rotina, mensagem=mensagem, tipo=tipo)

    @classmethod
    def registrar_info(cls, rotina, mensagem):
        cls.registrar_log(cls.INFO, rotina, mensagem)

    @classmethod
    def registrar_erro(cls, rotina, mensagem):
        cls.registrar_log(cls.ERRO, rotina, mensagem)
