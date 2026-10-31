import os
import tempfile
import traceback
from calendar import monthrange
from datetime import date, timedelta

from django import forms
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify
from sentry_sdk import capture_exception

from boletim_servico import utils
from comum.models import User
from djtools import relatorios
from djtools.db import models
from djtools.storages import cache_file
from djtools.utils import merge_pdf_files_qpdf
from documento_eletronico.models import Documento, DocumentoTexto
from documento_eletronico.status import DocumentoStatus

BOLETIM_IMAGENS = os.path.join(settings.BASE_DIR, 'boletim_servico', 'static', 'boletim_servico', 'img')


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {'form_class': forms.MultipleChoiceField, 'choices': self.base_field.choices}
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)

    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, list):
            return [self.base_field.to_python(val) for val in value]
        return value


class BoletimProgramado(models.Model):
    titulo = models.CharFieldPlus(verbose_name='Título', max_length=512)
    tipo_documento = models.ManyToManyFieldPlus('documento_eletronico.TipoDocumento', verbose_name='Tipos de Documentos')
    nivel_acesso = ChoiceArrayField(
        verbose_name='Nível de Acesso de Documentos', base_field=models.PositiveSmallIntegerField(choices=Documento.NIVEL_ACESSO_CHOICES)
    )
    programado = models.BooleanField(verbose_name='Gerar boletim diário?', default=False)
    programado_semanal = models.BooleanField(verbose_name='Gerar boletim semanal?', default=False)
    programado_mensal = models.BooleanField(verbose_name='Gerar boletim mensal?', default=False)
    criado_por = models.ForeignKeyPlus(User, verbose_name='Criado por', on_delete=models.PROTECT)
    criado_em = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Criado em')
    atualizado_em = models.DateTimeFieldPlus(auto_now=True, verbose_name='Atualizado em')
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = 'Boletim de Serviço Programado'
        verbose_name_plural = 'Boletins de Serviço Programados'

    def __str__(self):
        return self.titulo

    def clean(self):
        checks = [self.programado, self.programado_semanal, self.programado_mensal]
        if len(list(filter(lambda x: x is True, checks))) > 1:
            raise ValidationError('Só é permitido selecionar uma opção para gerar boletim (boletim diário, boletim semanal ou boletim mensal)')

    def gerar_boletim_diario(self, data=None, somente_documentos=False):
        from boletim_servico import tasks

        if not data:
            data = date.today() - timedelta(days=1)
        boletim = BoletimDiario(boletim_programado=self, data=data)
        documentos = boletim.get_documentos()
        if documentos:
            boletim.save()
            return tasks.gerar_boletim(boletim, somente_documentos=somente_documentos)
        else:
            raise ValidationError('Não existem documentos para geração do boletim referente ao dia anterior.')

    def gerar_boletim_semanal(self, data=None, somente_documentos=False):
        from boletim_servico import tasks

        if not data:
            data = date.today()
        dia_equivale_semana_anterior = data - timedelta(days=7)
        data_inicial_da_semana = dia_equivale_semana_anterior - timedelta(days=dia_equivale_semana_anterior.isoweekday())
        data_final_da_semana = data_inicial_da_semana + timedelta(days=6)
        boletim = BoletimPeriodo(boletim_programado=self, data_inicio=data_inicial_da_semana, data_fim=data_final_da_semana)
        documentos = boletim.get_documentos()
        if documentos:
            boletim.save()
            return tasks.gerar_boletim(boletim, somente_documentos=somente_documentos)
        else:
            raise ValidationError('Não existem documentos para geração do boletim referente a semana anterior.')

    def gerar_boletim_mensal(self, data=None, somente_documentos=False):
        from boletim_servico import tasks

        if not data:
            data = date.today()
        ultimo_dia_mes_anterior = data.replace(day=1) - timedelta(days=1)
        ano = ultimo_dia_mes_anterior.year
        mes = ultimo_dia_mes_anterior.month
        data_inicio_mes = date(ano, mes, 1)
        data_fim_mes = date(ano, mes, monthrange(ano, mes)[1])
        boletim = BoletimPeriodo(boletim_programado=self, data_inicio=data_inicio_mes, data_fim=data_fim_mes)
        documentos = boletim.get_documentos()
        if documentos:
            boletim.save()
            return tasks.gerar_boletim(boletim, somente_documentos=somente_documentos)
        else:
            raise ValidationError('Não existem documentos para geração do boletim referente ao mês informado.')


class ConfiguracaoSetorBoletim(models.Model):
    boletim_programado = models.ForeignKeyPlus(BoletimProgramado, verbose_name='Boletim Programado', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(max_length=512, verbose_name='Nome do Setor no Boletim')
    ordenacao = models.PositiveSmallIntegerField(verbose_name='Ordem do Setor no Boletim', default=1)
    setor_documento = models.ForeignKeyPlus(
        'rh.Setor', verbose_name='Setor do Documento', limit_choices_to={'codigo': None}, on_delete=models.CASCADE
    )
    material_anexo = models.FileFieldPlus(
        verbose_name='Material a anexar no final da seção do setor', null=True, blank=True, upload_to='boletim_servico/anexos/'
    )

    class Meta:
        verbose_name = 'Configuração de Setor no Boletim'
        verbose_name_plural = 'Configurações de Setor no Boletim'

    def __str__(self):
        return f'{self.boletim_programado} - {self.descricao}'


class BoletimDiario(models.Model):
    class Situacao:
        INICIAL = 1
        SOLICITADO = 2
        GERANDO = 3
        FINALIZADO = 4
        ERRO = 6

    SITUACAO_CHOICES = [
        (Situacao.INICIAL, '--'),
        (Situacao.SOLICITADO, 'Solicitado'),
        (Situacao.GERANDO, 'Gerando'),
        (Situacao.FINALIZADO, 'Finalizado'),
        (Situacao.ERRO, 'Erro'),
    ]

    boletim_programado = models.ForeignKeyPlus(BoletimProgramado, verbose_name='Boletim programado', on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(
        verbose_name='Arquivo do boletim', null=True, blank=True, upload_to='boletim_servico/boletim_diario/', max_length=255
    )
    situacao = models.PositiveSmallIntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES, default=1)
    data = models.DateFieldPlus(verbose_name='Data do boletim')
    data_criacao = models.DateTimeFieldPlus(verbose_name='Data de criação do boletim', auto_now_add=True)
    edicao_extra = models.PositiveSmallIntegerField(verbose_name='Número da edição extra', default=0)
    documentos = models.ManyToManyFieldPlus('documento_eletronico.DocumentoTexto', verbose_name='Documentos')

    class Meta:
        verbose_name_plural = 'Boletins de Serviços Diários'
        verbose_name = 'Boletim de Serviço Diário'
        unique_together = ('boletim_programado', 'data', 'edicao_extra')

    def __str__(self):
        string = '{} - {}'.format(self.boletim_programado.titulo, self.data.strftime('%d/%m/%Y'))
        if self.edicao_extra:
            string += f' - Edição Extra nº {self.edicao_extra}'
        return string

    def save(self, *args, **kwargs):
        if not self.pk and self.boletim_programado_id:
            qs_extra = BoletimDiario.objects.filter(boletim_programado=self.boletim_programado, data=self.data)
            if qs_extra.exists():
                ultima_edicao_extra = qs_extra.aggregate(ultima_edicao=Max('edicao_extra'))['ultima_edicao']
                self.edicao_extra = ultima_edicao_extra + 1
        super().save(*args, **kwargs)

    def get_documentos(self, reprocessamento=False):
        query = {
            'status__in': [DocumentoStatus.STATUS_ASSINADO, DocumentoStatus.STATUS_FINALIZADO],
            'assinaturadocumentotexto__assinatura__data_assinatura__date': self.data,
            'nivel_acesso__in': self.boletim_programado.nivel_acesso,
            'setor_dono__in': self.boletim_programado.configuracaosetorboletim_set.values('setor_documento'),
            'boletimdiario__isnull': not reprocessamento,
            'modelo__tipo_documento_texto__in': self.boletim_programado.tipo_documento.values_list('id', flat=True),
        }

        ordenacao = {c.setor_documento: c.ordenacao for c in self.boletim_programado.configuracaosetorboletim_set.all()}

        return sorted(
            DocumentoTexto.objects.filter(**query).reverse().distinct().order_by('-data_emissao'), key=lambda doc: ordenacao.get(doc.setor_dono, 1000)
        )

    def gerar_pdf(self, somente_documentos=False, reprocessamento=False):
        self.arquivo.delete()
        self.situacao = self.Situacao.GERANDO
        self.save()
        pdfs = []
        if not somente_documentos:
            pdfs.append(self.gerar_capa())
        setor = None

        documentos = self.get_documentos(reprocessamento=reprocessamento)
        self.documentos.add(*documentos)
        configuracoes = self.boletim_programado.configuracaosetorboletim_set.all()

        labels = {c.setor_documento: c.descricao for c in configuracoes}
        anexos = {c.setor_documento: c.material_anexo for c in configuracoes}
        obrigatorios = {c.setor_documento for c in configuracoes if c.material_anexo}
        setores_visitados = set()
        temps = []
        try:
            for documento in documentos:
                if documento.setor_dono != setor:
                    if setor:
                        anexo = anexos.get(setor)
                        if anexo:
                            tmp_name = cache_file(anexo.name)
                            temps.append(tmp_name)
                            pdfs.append(tmp_name)

                    setor = documento.setor_dono
                    setores_visitados.add(setor)
                    if not somente_documentos:
                        capa_setor = self.gerar_capa_secao(
                            'Nesta publicação, serão relacionados os atos administrativos, as concessões de diárias e passagens e os afastamentos deliberados'
                            f' no âmbito da {labels.get(setor, setor.nome)} do IFRN.'
                        )
                        pdfs.append(capa_setor)
                        capa_atos_administrativos = os.path.join(BOLETIM_IMAGENS, 'capa_secao_atos_administrativos.pdf')
                        pdfs.append(capa_atos_administrativos)
                pdf = utils.documento_to_pdf(documento)
                pdfs.append(pdf)

            # anexo do último setor
            anexo = anexos.get(setor)
            if anexo:
                tmp_name = cache_file(anexo.name)
                temps.append(tmp_name)
                pdfs.append(tmp_name)

            nao_visitados = obrigatorios - setores_visitados

            for setor in nao_visitados:
                if not somente_documentos:
                    capa_setor = self.gerar_capa_secao(
                        'Nesta publicação, serão relacionados os atos administrativos, as concessões de diárias e passagens e os afastamentos deliberados'
                        'do IFRN expedidos'
                        f' no âmbito da {labels.get(setor, setor.nome)} do IFRN.'
                    )
                    pdfs.append(capa_setor)
                    capa_atos_administrativos = os.path.join(BOLETIM_IMAGENS, 'capa_secao_atos_administrativos.pdf')
                    pdfs.append(capa_atos_administrativos)
                anexo = anexos.get(setor)
                if anexo:
                    tmp_name = cache_file(anexo.name)
                    temps.append(tmp_name)
                    pdfs.append(tmp_name)

            if not somente_documentos:
                pdfs.append(self.gerar_pagina_final())

            arquivo_pdf = merge_pdf_files_qpdf(pdfs)
            nome_arquivo = os.path.join(
                'boletim_servico',
                slugify(self.boletim_programado.titulo),
                str(self.data.year),
                str(self.data.month),
                f'boletim-{self.data.day}-{self.data.month}-{self.data.year}-{self.edicao_extra}.pdf',
            )
            self.arquivo.save(nome_arquivo, ContentFile(open(arquivo_pdf, 'rb').read()))
            self.situacao = self.Situacao.FINALIZADO
            self.save()
            for tmp in temps:
                os.unlink(tmp)
        except Exception:
            traceback.print_exc()
            self.situacao = self.Situacao.ERRO
            self.save()
            raise

    def gerar_pdfreport(self, conteudo=None):
        if conteudo:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as arquivo_temp:
                arquivo_temp.write(relatorios.PdfReport(body=conteudo, pages_count=0).generate())
                return arquivo_temp.name
        return None

    def gerar_capa(self):
        capa_img_path = os.path.join(BOLETIM_IMAGENS, 'capa_boletim_servico.png')
        contracapa_img_path = os.path.join(BOLETIM_IMAGENS, 'capa_logo_boletim_servico.png')

        expediente = self.boletim_programado.titulo
        if self.edicao_extra > 0:
            expediente = f'{expediente} Extra Nº {self.edicao_extra}'
        edicao = self.data.strftime('%d/%m/%Y')
        documento = [
            relatorios.ImageFullBackground(capa_img_path),
            relatorios.space(120),
            relatorios.para(expediente, style='Title'),
            relatorios.space(35),
            relatorios.para(edicao, style='Title'),
            relatorios.PageBreak(),
            relatorios.ImageFullBackground(contracapa_img_path),
        ]
        return self.gerar_pdfreport(documento)

    def gerar_capa_secao(self, msg):
        image_path = os.path.join(BOLETIM_IMAGENS, 'capa_secao_boletim_servico.png')
        message_table = relatorios.table([[relatorios.para(msg, style='Title')]], w=[140], a=['l'], grid=0)
        documento_capa = [relatorios.ImageFullBackground(image_path), relatorios.space(130), message_table]
        return self.gerar_pdfreport(documento_capa)

    def gerar_pagina_final(self):
        image_path = os.path.join(BOLETIM_IMAGENS, 'capa_final_boletim_servico.png')
        return self.gerar_pdfreport([relatorios.ImageFullBackground(image_path)])

    @property
    def is_finalizado(self):
        return self.situacao == self.Situacao.FINALIZADO

    @property
    def possui_link(self):
        return self.is_finalizado and self.arquivo


class BoletimPeriodo(models.Model):
    class Situacao:
        INICIAL = 1
        SOLICITADO = 2
        GERANDO = 3
        FINALIZADO = 4
        ERRO = 6

    SITUACAO_CHOICES = [
        (Situacao.INICIAL, '--'),
        (Situacao.SOLICITADO, 'Solicitado'),
        (Situacao.GERANDO, 'Gerando'),
        (Situacao.FINALIZADO, 'Finalizado'),
        (Situacao.ERRO, 'Erro'),
    ]

    boletim_programado = models.ForeignKeyPlus(BoletimProgramado, verbose_name='Boletim Programado', on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(
        verbose_name='Arquivo do Boletim', null=True, blank=True, upload_to='boletim_servico/boletim_periodo/', max_length=255
    )
    situacao = models.PositiveSmallIntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES, default=1)
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial do boletim')
    data_fim = models.DateFieldPlus(verbose_name='Data Final do boletim')
    data_criacao = models.DateTimeFieldPlus(verbose_name='Data de Criação do Boletim', auto_now_add=True)
    edicao_extra = models.PositiveSmallIntegerField(verbose_name='Número da edição extra', default=0)
    documentos = models.ManyToManyFieldPlus('documento_eletronico.DocumentoTexto', verbose_name='Documentos')

    class Meta:
        verbose_name_plural = 'Boletins de Serviço do Período'
        verbose_name = 'Boletim de Serviço do Período'
        unique_together = ('boletim_programado', 'data_inicio', 'data_fim', 'edicao_extra')

    def __str__(self):
        string = '{} - {} até {}'.format(self.boletim_programado.titulo, self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'))
        if self.edicao_extra:
            string += f' - Edição Extra nº {self.edicao_extra}'
        return string

    def save(self, *args, **kwargs):
        if not self.pk and self.boletim_programado_id:
            qs_extra = BoletimPeriodo.objects.filter(boletim_programado=self.boletim_programado, data_inicio=self.data_inicio, data_fim=self.data_fim)
            if qs_extra.exists():
                ultima_edicao_extra = qs_extra.aggregate(ultima_edicao=Max('edicao_extra'))['ultima_edicao']
                self.edicao_extra = ultima_edicao_extra + 1
        super().save(*args, **kwargs)

    def get_documentos(self, reprocessamento=False):
        query = {
            'status__in': [DocumentoStatus.STATUS_ASSINADO, DocumentoStatus.STATUS_FINALIZADO],
            'assinaturadocumentotexto__assinatura__data_assinatura__date__range': (self.data_inicio, self.data_fim),
            'nivel_acesso__in': self.boletim_programado.nivel_acesso,
            'setor_dono__in': self.boletim_programado.configuracaosetorboletim_set.values('setor_documento'),
            'boletimperiodo__isnull': not reprocessamento,
            'modelo__tipo_documento_texto__in': self.boletim_programado.tipo_documento.values_list('id', flat=True),
        }

        ordenacao = {c.setor_documento: c.ordenacao for c in self.boletim_programado.configuracaosetorboletim_set.all()}

        return sorted(
            DocumentoTexto.objects.filter(**query).reverse().distinct().order_by('-data_emissao'), key=lambda doc: ordenacao.get(doc.setor_dono, 1000)
        )

    @transaction.atomic()
    def gerar_pdf(self, somente_documentos=False, reprocessamento=False):
        try:
            self.arquivo.delete()
            self.situacao = self.Situacao.GERANDO
            self.save()
            pdfs = []
            temps = []
            if not somente_documentos:
                capa = self.gerar_capa()
                temps.append(capa)
                pdfs.append(capa)
            setor = None

            documentos = self.get_documentos(reprocessamento=reprocessamento)
            self.documentos.add(*documentos)
            configuracoes = self.boletim_programado.configuracaosetorboletim_set.all()

            labels = {c.setor_documento: c.descricao for c in configuracoes}
            anexos = {c.setor_documento: c.material_anexo for c in configuracoes}
            obrigatorios = {c.setor_documento for c in configuracoes if c.material_anexo}
            setores_visitados = set()

            for documento in documentos:
                if documento.setor_dono != setor:
                    if setor:
                        anexo = anexos.get(setor)
                        if anexo:
                            tmp_name = cache_file(anexo.name)
                            temps.append(tmp_name)
                            pdfs.append(tmp_name)

                    setor = documento.setor_dono
                    setores_visitados.add(setor)
                    if not somente_documentos:
                        capa_setor = self.gerar_capa_secao(
                            'Nesta publicação, serão relacionados os atos administrativos, as concessões de diárias e passagens e os afastamentos deliberados'
                            f' no âmbito da {labels.get(setor, setor.nome)} do IFRN.'
                        )
                        temps.append(capa_setor)
                        pdfs.append(capa_setor)
                        capa_atos_administrativos = os.path.join(BOLETIM_IMAGENS, 'capa_secao_atos_administrativos.pdf')
                        pdfs.append(capa_atos_administrativos)
                pdf = utils.documento_to_pdf(documento)
                temps.append(pdf)
                pdfs.append(pdf)

            # anexo do último setor
            anexo = anexos.get(setor)
            if anexo:
                tmp_name = cache_file(anexo.name)
                temps.append(tmp_name)
                pdfs.append(tmp_name)

            nao_visitados = obrigatorios - setores_visitados

            for setor in nao_visitados:
                if not somente_documentos:
                    capa_setor = self.gerar_capa_secao(
                        'Nesta publicação, serão relacionados os atos administrativos, as concessões de diárias e passagens e os afastamentos deliberados'
                        f' no âmbito da {labels.get(setor, setor.nome)} do IFRN·'
                    )
                    temps.append(capa_setor)
                    pdfs.append(capa_setor)
                    capa_atos_administrativos = os.path.join(BOLETIM_IMAGENS, 'capa_secao_atos_administrativos.pdf')
                    pdfs.append(capa_atos_administrativos)
                anexo = anexos.get(setor)
                if anexo:
                    tmp_name = cache_file(anexo.name)
                    temps.append(tmp_name)
                    pdfs.append(tmp_name)

            if not somente_documentos:
                pagina_final = self.gerar_pagina_final()
                temps.append(pagina_final)
                pdfs.append(pagina_final)

            arquivo_pdf = merge_pdf_files_qpdf(pdfs)
            nome_arquivo = os.path.join(
                'boletim_servico',
                slugify(self.boletim_programado.titulo),
                str(self.data_inicio.year),
                str(self.data_inicio.month),
                f'boletim-{self.data_inicio.day}-{self.data_fim.day}-{self.data_inicio.month}-{self.data_inicio.year}-{self.edicao_extra}.pdf',
            )
            self.arquivo.save(nome_arquivo, ContentFile(open(arquivo_pdf, 'rb').read()))
            self.situacao = self.Situacao.FINALIZADO
            for tmp in temps:
                os.unlink(tmp)
            self.save()
        except Exception as e:
            if settings.DEBUG:
                traceback.print_exc()
            capture_exception(e)
            self.situacao = self.Situacao.ERRO
            self.save()
            raise e

    def gerar_pdfreport(self, conteudo=None):
        if conteudo:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as arquivo_temp:
                arquivo_temp.write(relatorios.PdfReport(body=conteudo, pages_count=0).generate())
                return arquivo_temp.name
        return None

    def gerar_capa(self):
        capa_img_path = os.path.join(BOLETIM_IMAGENS, 'capa_boletim_servico.png')
        contracapa_img_path = os.path.join(BOLETIM_IMAGENS, 'capa_logo_boletim_servico.png')

        expediente = self.boletim_programado.titulo
        if self.edicao_extra > 0:
            expediente = f'{expediente} Extra Nº {self.edicao_extra}'
        edicao = '{} até {}'.format(self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'))
        documento = [
            relatorios.ImageFullBackground(capa_img_path),
            relatorios.space(120),
            relatorios.para(expediente, style='Title'),
            relatorios.space(35),
            relatorios.para(edicao, style='Title'),
            relatorios.PageBreak(),
            relatorios.ImageFullBackground(contracapa_img_path),
        ]
        return self.gerar_pdfreport(documento)

    def gerar_capa_secao(self, msg):
        image_path = os.path.join(BOLETIM_IMAGENS, 'capa_secao_boletim_servico.png')
        message_table = relatorios.table([[relatorios.para(msg, style='Title')]], w=[140], a=['l'], grid=0)
        documento_capa = [relatorios.ImageFullBackground(image_path), relatorios.space(130), message_table]
        return self.gerar_pdfreport(documento_capa)

    def gerar_pagina_final(self):
        image_path = os.path.join(BOLETIM_IMAGENS, 'capa_final_boletim_servico.png')
        return self.gerar_pdfreport([relatorios.ImageFullBackground(image_path)])

    @property
    def is_finalizado(self):
        return self.situacao == self.Situacao.FINALIZADO

    @property
    def possui_link(self):
        return self.is_finalizado and self.arquivo
