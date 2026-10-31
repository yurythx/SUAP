import datetime
import logging
import os
import tempfile
from pathlib import Path

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.safestring import mark_safe

from comum.utils import tl
from djtools.db import models
from djtools.utils import convert_docx_to_pdf, convert_pdf_to_pdfa
from edu.models.alunos import Aluno
from edu.models.logs import LogModel
from rh.models import AbstractVinculoArquivoUnico, ArquivoUnico

logger = logging.getLogger(__name__)

MENSAGEM_CONVERSOR_PDFA_INDISPONIVEL = 'Serviço de conversão para PDF/A indisponível no momento. Tente novamente mais tarde.'


class TipoAlunoArquivo(models.ModelPlus):
    SEARCH_FIELDS = ['nome']

    IDENTIDADE = 'Documento de Identidade'
    CERTIDAO_NASCIMENTO = 'Certidão de Nascimento'
    CERTIDAO_CASAMENTO = 'Certidão de Casamento'
    TITULO_ELEITOR = 'Título de Eleitor'
    ATO_NATURALIZACAO = 'Ato de Naturalização'
    CNH = 'CNH'
    RESERVISTA = 'Reservista'
    HISTORICO = 'Histórico Escolar'
    CERTIFICADO_CONCLUSAO = 'Certificado de Conclusão'
    RELATORIO_CONCLUSAO = 'Relatório de Conclusão'
    QUITACAO_ELEITORAL = 'Certidão de Quitação Eleitoral'
    CARTAO_VACINA = 'Cartão de Vacina'
    COMPROVANTE_RENDA = 'Comprovante de Renda'
    LAUDO_MEDICO = 'Laudo Médico'
    DECLARACAO_PEDIDO_CANCELAMENTO_MATRICULA = 'Declaração de Pedido de Cancelamento de Matrícula'
    PASSAPORTE = 'Passaporte'
    CPF = 'CPF'
    FOTO = 'Foto'
    DOSSIE = 'Dossiê'
    OUTROS = 'Outros'
    COMPROVANTE_APROVACAO_PROCESSO_SELETIVO = 'Comprovante de Aprovação (Vestibular/SISU)'

    TIPO_CHOICES = [
        [1, IDENTIDADE],
        [2, CERTIDAO_NASCIMENTO],
        [3, CERTIDAO_CASAMENTO],
        [4, TITULO_ELEITOR],
        [5, ATO_NATURALIZACAO],
        [6, CNH],
        [7, RESERVISTA],
        [8, HISTORICO],
        [9, CERTIFICADO_CONCLUSAO],
        [10, RELATORIO_CONCLUSAO],
        [11, QUITACAO_ELEITORAL],
        [12, CARTAO_VACINA],
        [13, COMPROVANTE_RENDA],
        [14, LAUDO_MEDICO],
        [15, DECLARACAO_PEDIDO_CANCELAMENTO_MATRICULA],
        [16, PASSAPORTE],
        [17, CPF],
        [18, FOTO],
        [19, DOSSIE],
        [99, OUTROS],
        [100, COMPROVANTE_APROVACAO_PROCESSO_SELETIVO],
    ]

    nome = models.CharFieldPlus('Nome', max_length=120, unique=True, null=False, blank=False)
    # campos_servicos = models.ManyToManyFieldPlus('catalogo_provedor_servico.CampoServico', verbose_name='Campos Correlacionados dos serviços de matrícula', blank=True)
    ativo = models.BooleanField('Ativo?', default=True, null=False, blank=False)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Tipo de Documento da Pasta Documental'
        verbose_name_plural = 'Tipos de Documentos da Pasta Documental'

    def __str__(self):
        return self.nome


class GrupoArquivoObrigatorio(LogModel):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    modalidades = models.ManyToManyFieldPlus('edu.Modalidade', verbose_name='Modalidades')
    tipos = models.ManyToManyFieldPlus(TipoAlunoArquivo, verbose_name='Tipos de Documentos')

    class Meta:
        verbose_name = 'Grupo de Arquivos Obrigatórios'
        verbose_name_plural = 'Grupo de Arquivos Obrigatórios'
        ordering = ('descricao',)

    def __str__(self):
        return self.descricao


class AlunoArquivo(AbstractVinculoArquivoUnico, LogModel):
    tipo = models.ForeignKeyPlus(TipoAlunoArquivo)
    aluno = models.ForeignKeyPlus(Aluno, on_delete=models.CASCADE)

    validado = models.BooleanField('Validado', default=True, null=True)
    data_validacao = models.DateTimeFieldPlus('Data da Validação', null=True)
    responsavel_validacao = models.ForeignKeyPlus('comum.User', verbose_name='Responsável pela Validação', null=True)
    prazo_validade = models.IntegerField(
        verbose_name='Validade', blank=False, null=False, default=6, help_text='Prazo de validade do documento em anos.'
    )
    data_expiracao = models.DateFieldPlus('Data de Expiração', blank=True, null=True)

    observacao = models.TextField(verbose_name='Observação', max_length=255, blank=True, null=True)

    em_diploma = models.BooleanField(verbose_name='Contido no diploma vigente', default=False, null=False, blank=False)

    TIPO_ORIGEM_CADASTRO_MANUAL = 'MANUAL'
    TIPO_ORIGEM_CADASTRO_MATRICULA_ONLINE = 'MATRICULA_ONLINE'
    TIPO_ORIGEM_CADASTRO_CHOICES = (
        (TIPO_ORIGEM_CADASTRO_MANUAL, 'Manual'),
        (TIPO_ORIGEM_CADASTRO_MATRICULA_ONLINE, 'Matrícula Online'),
    )
    tipo_origem_cadastro = models.CharField('Tipo de Origem do Cadastro', max_length=25, choices=TIPO_ORIGEM_CADASTRO_CHOICES, editable=False)

    class Meta:
        verbose_name = 'Arquivo do Aluno'
        verbose_name_plural = 'Arquivos do Aluno'
        ordering = ('-data_hora_upload',)
        permissions = (('adm_delete_alunoarquivo', 'Pode excluir documento validado da pasta do aluno'),)

    def __str__(self):
        return f'{self.nome_exibicao} - {self.data_hora_upload} - {self.aluno}'

    def validar(self, user):
        self.responsavel_validacao = user
        self.data_validacao = datetime.datetime.now()
        self.prazo_validade = self.prazo_validade or 6
        self.data_expiracao = self.data_validacao.date() + relativedelta(years=self.prazo_validade)
        self.save()

    def renovar(self, user):
        if self.pode_renovar(user):
            self.data_expiracao = self.data_expiracao + relativedelta(years=self.prazo_validade)
            self.save()

    def get_status_html(self):
        hoje = datetime.datetime.now().date()
        situacao = 'Inválido'
        status = 'error'
        if self.validado is None:
            situacao = 'Aguardando Validação'
            status = 'alert'
        elif self.validado and self.data_expiracao and hoje > self.data_expiracao:
            situacao = 'Expirado'
            status = 'error'
        elif self.validado:
            situacao = 'Validado'
            status = 'success'
        return mark_safe(f'<span class="status status-{status}">{situacao}</span>')

    def pode_renovar(self, user):
        hoje = datetime.datetime.now().date()
        return self.validado and user.has_perm('edu.change_alunoarquivo') and self.data_expiracao and hoje > self.data_expiracao

    def can_validate(self, user):
        return self.validado is None and user.has_perm('edu.change_alunoarquivo')

    def can_delete(self, user=None):
        if user is None:
            user = tl.get_user()

        eh_administrador = user.has_perm('edu.adm_delete_alunoarquivo')
        eh_aluno = user == self.aluno.get_user()
        eh_usuario_com_permissao = user.has_perm('edu.delete_alunoarquivo')

        if self.em_diploma or self.aluno.is_concluido():
            return eh_administrador
        else:
            if self.validado:
                return eh_administrador or (user == self.responsavel_validacao and eh_usuario_com_permissao)
            else:
                return eh_administrador or eh_aluno or eh_usuario_com_permissao

    def get_tipo_diploma_exibicao(self):
        tipo = TipoAlunoArquivo.OUTROS
        if self.tipo.nome == TipoAlunoArquivo.IDENTIDADE:
            tipo = 'DocumentoIdentidadeDoAluno'
        elif self.tipo.nome == TipoAlunoArquivo.HISTORICO:
            tipo = 'HistoricoEscolar'
        elif self.tipo.nome == TipoAlunoArquivo.CERTIDAO_NASCIMENTO:
            tipo = 'CertidaoNascimento'
        elif self.tipo.nome == TipoAlunoArquivo.CERTIDAO_CASAMENTO:
            tipo = 'CertidaoCasamento'
        elif self.tipo.nome == TipoAlunoArquivo.TITULO_ELEITOR:
            tipo = 'TituloEleitor'
        return tipo

    @classmethod
    def get_tipo_para_matricula_online(cls, descricao_arquivo):
        tipo = None
        if 'RG' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.IDENTIDADE).first()
        elif 'Foto' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.FOTO).first()
        elif 'Laudo' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.LAUDO_MEDICO).first()
        elif 'Histórico Escolar' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.HISTORICO).first()
        elif 'Certificado' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.CERTIFICADO_CONCLUSAO).first()
        elif 'Eleitor' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.TITULO_ELEITOR).first()
        elif 'Quitação Eleitoral' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.QUITACAO_ELEITORAL).first()
        elif 'Reservista' in descricao_arquivo:
            tipo = TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.RESERVISTA).first()

        if tipo:
            return tipo
        return TipoAlunoArquivo.objects.filter(nome=TipoAlunoArquivo.OUTROS).first()

    # TODO: Testar e rever. Creio que dá pra abstrair e jogar pra classe pai!
    @classmethod
    def update_or_create_from_file_bytes(
        cls,
        bytes,
        tipo_conteudo,
        data_hora_upload,
        nome_original,
        nome_exibicao,
        descricao,
        aluno,
        observacao,
        tipo,
        tamanho_em_bytes_para_validar=None,
        hash_sha512_para_validar=None,
        aluno_arquivo_id=None,
    ):
        if aluno_arquivo_id:
            aluno_arquivo = AlunoArquivo.objects.filter(pk=aluno_arquivo_id).first()
            if not aluno_arquivo:
                raise ValidationError('A arquivo do aluno não existe, portanto não pode ser atualizado.')
            aluno_arquivo_created = False
        else:
            aluno_arquivo = AlunoArquivo()
            aluno_arquivo_created = True

        arquivo_unico_created = False
        arquivo_unico = None

        try:
            with transaction.atomic():
                arquivo_unico, arquivo_unico_created = ArquivoUnico.get_or_create_from_file_bytes(
                    bytes=bytes,
                    tipo_conteudo=tipo_conteudo,
                    nome_original_primeiro_upload=nome_original,
                    data_hora_primeiro_upload=data_hora_upload,
                    tamanho_em_bytes_para_validar=tamanho_em_bytes_para_validar,
                    hash_sha512_para_validar=hash_sha512_para_validar,
                )

                # Setando os atributos do AlunoArquivo.
                aluno_arquivo.arquivo_unico = arquivo_unico
                aluno_arquivo.nome_original = nome_original
                aluno_arquivo.nome_exibicao = nome_exibicao
                aluno_arquivo.add_extensao_ao_nome_exibicao_com_base_no_nome_original()
                aluno_arquivo.descricao = descricao
                aluno_arquivo.data_hora_upload = data_hora_upload
                aluno_arquivo.aluno = aluno
                aluno_arquivo.observacao = observacao
                aluno_arquivo.tipo = tipo
                aluno_arquivo.save()

                return aluno_arquivo, aluno_arquivo_created, arquivo_unico, arquivo_unico_created
        except Exception as e:
            if arquivo_unico_created:
                arquivo_unico.conteudo.delete(save=False)
            raise e

    def to_pdfa(self) -> str:
        """Converte o arquivo para PDF/A e devolve o caminho do arquivo gerado.

        Raises:
            RuntimeError: se o serviço externo de conversão estiver indisponível (a causa técnica vai só para o log).
        """
        tmp_file_path = tempfile.NamedTemporaryFile('wb', delete=False)
        temporarios = {tmp_file_path.name}
        try:
            with self.arquivo_unico.conteudo.open('rb') as f:
                tmp_file_path.write(f.read())
            tmp_file_path.close()
            _filename, file_extension = os.path.splitext(self.arquivo_unico.conteudo.name)
            original_pdf_path = tempfile.NamedTemporaryFile('wb', delete=False, suffix='.pdf').name
            temporarios.add(original_pdf_path)
            if file_extension.lower() == '.docx':
                original_pdf_path = convert_docx_to_pdf(settings.TEMP_DIR, tmp_file_path.name)
                temporarios.add(original_pdf_path)
            elif file_extension.lower() in ['.jpeg', '.png', '.jpg']:
                command = f'convert {tmp_file_path.name} {original_pdf_path}'
                os.system(command)
            elif file_extension.lower() == '.pdf':
                command = f'cp {tmp_file_path.name} {original_pdf_path}'
                os.system(command)
            else:
                raise Exception(f'Não é possível realizar a conversão de arquivos no formato {file_extension.lower()}.')
            try:
                return convert_pdf_to_pdfa(original_pdf_path)
            except requests.exceptions.RequestException as e:
                logger.warning('Falha ao converter o AlunoArquivo %s para PDF/A: %r', self.pk, e)
                raise RuntimeError(MENSAGEM_CONVERSOR_PDFA_INDISPONIVEL) from e
        finally:
            tmp_file_path.close()
            for caminho in temporarios:
                Path(caminho).unlink(missing_ok=True)
