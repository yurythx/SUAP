import collections
import datetime
import hashlib
import os
from copy import copy

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import HttpResponse
from sentry_sdk import capture_exception

from comum.models import Ano, RegistroEmissaoDocumento
from djtools.db import models
from djtools.storages import cache_file
from djtools.utils import data_extenso, gerar_documento_impressao, httprr, libreoffice_new_line
from processo_eletronico.models import Processo
from rh.models import UnidadeOrganizacional


class Avaliacao(models.ModelPlus):
    SEARCH_FIELDS = ['ano__ano', 'tipo']

    # Dados gerais
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', related_name='encceja_ano_set', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus(
        verbose_name='Tipo',
        choices=[
            ['Enem', 'Enem'],
            ['Encceja Nacional', 'Encceja Nacional'],
            ['Encceja Exterior', 'Encceja Exterior'],
            ['Encceja PPL', 'Encceja PPL'],
        ],
    )
    descricao_edital = models.TextField(verbose_name='Descrição do Edital')

    # Pontuações Mínimas
    pontuacao_min_area_conhecimento = models.DecimalFieldPlus(verbose_name='Área de Conhecimento')
    pontuacao_min_redacao = models.DecimalFieldPlus(verbose_name='Redação')

    class Meta:
        verbose_name_plural = 'Avaliação'
        verbose_name = 'Avaliações'

    def __str__(self):
        return f'{self.tipo} ({self.ano})'


class AreaConhecimento(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome')
    descricao = models.TextField(verbose_name='Descrição', help_text='Texto que será impresso no certificado.')

    class Meta:
        verbose_name_plural = 'Área de Conhecimento'
        verbose_name = 'Áreas de Conhecimento'

    def __str__(self):
        return self.nome


class Configuracao(models.ModelPlus):
    SEARCH_FIELDS = ['ano__ano', 'descricao']
    ano = models.OneToOneField('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE, null=True, related_name='encceja_set')
    descricao = models.CharFieldPlus('Descrição', help_text='Será usado nos certificados pela marcação #DESCRICAO#')
    edital = models.CharFieldPlus('Edital', blank=True, help_text='Será usado nos certificados pela marcação #EDITAL#')
    data_primeira_prova = models.DateFieldPlus('Data de realização da 1ª Prova', null=True)
    modelo_certificacao_parcial = models.FileFieldPlus(
        upload_to='encceja/modelos_documento/',
        filetypes=['docx'],
        null=True,
        blank=True,
        verbose_name='Modelo de Certificação Parcial',
        check_mimetype=False,
        help_text="""O arquivo de modelo deve ser uma arquivo .docx. Marcações disponíveis #NOME#, #CPF#, #ANO#, #AREAS#, #AVALIACOES#, #PONTUACAO#,
                                                       #EDITAIS#, #LEGENDA_EDITAIS#, #CODIGOVERIFICADOR#, #LOCAL#, #DATA#, #AVA_REDACAO#, #EDIT_REDACAO#, #PONT_REDACAO#""",
    )
    modelo_certificacao_parcial_com_timbre = models.FileFieldPlus(
        upload_to='encceja/modelos_documento/',
        filetypes=['docx'],
        null=True,
        blank=True,
        verbose_name='Modelo de Certificação Parcial Com Timbre',
        check_mimetype=False,
        help_text="""O arquivo de modelo deve ser uma arquivo .docx. Marcações disponíveis #NOME#, #CPF#, #ANO#, #AREAS#, #AVALIACOES#, #PONTUACAO#,
                                                       #EDITAIS#, #LEGENDA_EDITAIS#, #CODIGOVERIFICADOR#, #LOCAL#, #DATA#, #AVA_REDACAO#, #EDIT_REDACAO#, #PONT_REDACAO#""",
    )
    modelo_certificacao_completa = models.FileFieldPlus(
        upload_to='encceja/modelos_documento/',
        filetypes=['docx'],
        null=True,
        blank=True,
        verbose_name='Modelo de Certificação Completa',
        check_mimetype=False,
        help_text="""O arquivo de modelo deve ser uma arquivo .docx. Marcações disponíveis #NOME#, #CPF#, #ANO#, #AREAS#, #AVALIACOES#, #PONTUACAO#,
                                                       #EDITAIS#, #LEGENDA_EDITAIS#, #CODIGOVERIFICADOR#, #LOCAL#, #DATA#, #AVA_REDACAO#, #EDIT_REDACAO#, #PONT_REDACAO#""",
    )
    modelo_certificacao_completa_com_timbre = models.FileFieldPlus(
        upload_to='encceja/modelos_documento/',
        filetypes=['docx'],
        null=True,
        blank=True,
        verbose_name='Modelo de Certificação Completa com Timbre',
        check_mimetype=False,
        help_text="""O arquivo de modelo deve ser uma arquivo .docx. Marcações disponíveis #NOME#, #CPF#, #ANO#, #AREAS#, #AVALIACOES#, #PONTUACAO#,
                                                       #EDITAIS#, #LEGENDA_EDITAIS#, #CODIGOVERIFICADOR#, #LOCAL#, #DATA#, #AVA_REDACAO#, #EDIT_REDACAO#, #PONT_REDACAO#""",
    )
    ativa = models.BooleanField(verbose_name='Ativa', blank=True)
    nota_redacao_obrigatoria = models.BooleanField(
        verbose_name='Nota da redação obrigatória',
        help_text='Indica se a nota da Redação será levada em consideração na emissão dos certificados.',
        default=True,
        blank=True,
    )

    class Meta:
        verbose_name_plural = 'Configuração ENCCEJA'
        verbose_name = 'Configurações ENCCEJA'

    def __str__(self):
        return self.descricao


class Solicitacao(models.ModelPlus):
    COMPLETO = 1
    PARCIAL = 2
    TIPO_CERTIFICADO_CHOICES = [[COMPLETO, 'Completo'], [PARCIAL, 'Parcial']]
    processo = models.ForeignKeyPlus(Processo, verbose_name='Processo', null=True, blank=True)
    cadastrador = models.CurrentUserField(verbose_name='Cadastrador', null=True, blank=True, related_name='solicitacao_cadastrada_set')
    # Configuração
    configuracao = models.ForeignKeyPlus(Configuracao, verbose_name='Configuração', on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=True, on_delete=models.CASCADE)
    # Dados do Solicitante
    inscricao = models.CharFieldPlus(verbose_name='Inscrição', null=True, blank=True)
    nome = models.CharFieldPlus(verbose_name='Nome')
    tipo_certificado = models.IntegerField(choices=TIPO_CERTIFICADO_CHOICES, null=True, verbose_name='Tipo de Certificado')
    cpf = models.BrCpfField(verbose_name='CPF')
    ppl = models.BooleanField(verbose_name='Participante Privado de Liberdade', default=False, blank=True)
    data_nascimento = models.DateField(verbose_name='Data de Nascimento')
    # Pontuação da Redação
    avaliacao_redacao = models.ForeignKeyPlus(Avaliacao, verbose_name='Avaliação da Redação', on_delete=models.CASCADE)
    pontuacao_redacao = models.DecimalFieldPlus(verbose_name='Pontuação da Redação', null=True)
    # Pontuação por Área de Conhecimento está na tabela Pontuação
    codigo_verificador = models.CharFieldPlus(verbose_name='Código Verificador', null=True)
    data_emissao = models.DateField(verbose_name='Data da Emissão', null=True)
    emissor = models.ForeignKeyPlus('comum.User', verbose_name='Avaliador', null=True, blank=True, related_name='emss_set', on_delete=models.CASCADE)
    atendida = models.BooleanField(verbose_name='Atendida', default=False, blank=True)

    aproveitamento_de_notas_outras_edicoes = models.BooleanField(verbose_name='Aproveitamento de notas de outras edições?', default=False, blank=True)

    cancelada = models.BooleanField(verbose_name='Cancelada', default=False)
    data_cancelamento = models.DateFieldPlus(verbose_name='Data do Cancelamento', null=True)
    responsavel_cancelamento = models.CurrentUserField(
        verbose_name='Responsável pelo Cancelamento', null=True, related_name='solicitacaocancelada_set'
    )
    motivo_cancelamento = models.TextField(verbose_name='Motivo do Cancelamento/Descancelamento', null=True)

    class Meta:
        verbose_name = 'Solicitação'
        verbose_name_plural = 'Solicitações'

    def __str__(self):
        return f'Solicitação de {self.nome} do {self.configuracao}'

    def get_tipo_certificacao(self, formatar=False):
        if self.pode_certificar():
            if self.pode_certificar_integralmente():
                return formatar and '<span class="status status-success">Completa</span>' or 'Completa'
            else:
                return formatar and '<span class="status status-alert">Parcial</span>' or 'Parcial'
        else:
            return formatar and '<span class="status status-error">Nenhuma</span>' or 'Nenhuma'

    def pode_certificar_integralmente(self):
        if self.pontuacao_redacao is None or self.pontuacao_redacao < self.avaliacao_redacao.pontuacao_min_redacao:
            return False
        if not self.pk or self.pontuacao_set.all().count() < 4:
            return False
        return all(pontuacao.valor >= pontuacao.avaliacao.pontuacao_min_area_conhecimento for pontuacao in self.pontuacao_set.all())

    def atingiu_pontuacao_minima_redacao(self):
        return self.pontuacao_redacao and self.pontuacao_redacao >= self.avaliacao_redacao.pontuacao_min_redacao

    def atingiu_pontuacao_minima_linguagem(self):
        passou_linguagem = False
        qs_linguagens = self.pontuacao_set.filter(area_conhecimento__descricao__unaccent__icontains='linguagens') | self.pontuacao_set.filter(
            area_conhecimento__nome__unaccent__icontains='linguagens'
        )
        if qs_linguagens.exists():
            pontuacao_linguagem = qs_linguagens[0]
            passou_linguagem = pontuacao_linguagem.valor >= pontuacao_linguagem.avaliacao.pontuacao_min_area_conhecimento
        return passou_linguagem

    def get_motivo_certificacao_negada(self):
        data_nascimento = self.data_nascimento.date() if hasattr(self.data_nascimento, 'date') else self.data_nascimento
        if not data_nascimento <= self.configuracao.data_primeira_prova - relativedelta(years=18):
            return 'Não é possível emitir este certificado, pois o solicitante realizou prova com idade inferior a 18 anos.'
        if not self.pk:
            return 'Não é possível emitir este certificado, pois o solicitante não possui nenhuma pontuação cadastrada.'
        for pontuacao in self.pontuacao_set.all():
            if pontuacao.is_certificado():
                return None
        return 'Não é possível emitir este certificado, pois o solicitante não atingiu pontuação mínima para aprovação.'

    def pode_certificar(self):
        return self.get_motivo_certificacao_negada() is None

    def imprimir_certificacao(self, emissor=None, com_timbre=False):
        if self.pode_certificar():
            dicionario = {}
            listas = [[], [], [], []]
            obs = ['(1)', '(2)', '(3)', '(4)', '(5)']
            lengenda_editais = collections.OrderedDict()
            for pontuacao in self.pontuacao_set.all():
                if pontuacao.is_certificado():
                    legenda_edital = pontuacao.avaliacao.descricao_edital.split(',')[0]
                    descricao_edital = pontuacao.avaliacao.descricao_edital
                    lengenda_editais[legenda_edital] = descricao_edital
                    listas[0].append(pontuacao.area_conhecimento.nome)
                    listas[1].append(str(pontuacao.valor))
                    listas[2].append(str(pontuacao.avaliacao))
                    listas[3].append(f'{legenda_edital} {obs[list(lengenda_editais.keys()).index(legenda_edital)]}')
            if self.atingiu_pontuacao_minima_redacao() and self.atingiu_pontuacao_minima_linguagem():
                legenda_edital = self.avaliacao_redacao.descricao_edital.split(',')[0]
                descricao_edital = self.avaliacao_redacao.descricao_edital
                lengenda_editais[legenda_edital] = descricao_edital
                listas[0].append('Redação')
                listas[1].append(str(self.pontuacao_redacao))
                listas[2].append(str(self.avaliacao_redacao))
                listas[3].append(f'{legenda_edital} {obs[list(lengenda_editais.keys()).index(legenda_edital)]}')

            primeira_impressao = False
            if not self.data_emissao:
                primeira_impressao = True
                self.emissor = emissor
                self.data_emissao = datetime.date.today()
                self.atendida = True
                self.codigo_verificador = hashlib.sha1(f'{self.pk}{self.data_emissao}{settings.SECRET_KEY}'.encode()).hexdigest()
                self.save()

            codigo_verificador = (
                'Documento emitido pelo SUAP. Para comprovar sua autenticidade, '
                'acesse {}/comum/autenticar_documento/ - '
                'Código de autenticação: {} - Tipo de Documento: ENCCEJA - '
                'Data da emissão: {} '.format(settings.SITE_URL, self.codigo_verificador[0:7], self.data_emissao.strftime('%d/%m/%Y'))
            )

            dicionario['#CPF#'] = self.cpf
            dicionario['#NOME#'] = self.nome
            dicionario['#DESCRICAO#'] = self.configuracao.descricao
            dicionario['#EDITAL#'] = self.configuracao.edital
            dicionario['#AREAS#'] = libreoffice_new_line(listas[0])
            dicionario['#PONTUACAO#'] = libreoffice_new_line(listas[1])
            dicionario['#AVALIACOES#'] = libreoffice_new_line(listas[2])
            dicionario['#EDITAIS#'] = libreoffice_new_line(listas[3])
            dicionario['#DATA#'] = data_extenso(datetime.date.today())
            dicionario['#PONT_REDACAO#'] = libreoffice_new_line([str(self.pontuacao_redacao)])
            dicionario['#AVA_REDACAO#'] = libreoffice_new_line([str(self.avaliacao_redacao)])
            dicionario['#EDIT_REDACAO#'] = libreoffice_new_line([f'{legenda_edital} {obs[list(lengenda_editais.keys()).index(legenda_edital)]}'])
            dicionario['#CODIGOVERIFICADOR#'] = codigo_verificador
            dicionario['#LOCAL#'] = self.uo and self.uo.municipio and str(self.uo.municipio) or ''
            dicionario['#ANO#'] = self.configuracao.ano.ano

            lista_lengenda_editais = []
            for legenda_edital, descricao_edital in list(lengenda_editais.items()):
                lista_lengenda_editais.append(f'{obs[list(lengenda_editais.keys()).index(legenda_edital)]} {descricao_edital}')
            dicionario['#LEGENDA_EDITAIS#'] = libreoffice_new_line(lista_lengenda_editais)
            parcial = not self.pode_certificar_integralmente()
            if com_timbre:
                modelo_documento = (
                    parcial and self.configuracao.modelo_certificacao_parcial_com_timbre or self.configuracao.modelo_certificacao_completa_com_timbre
                )
            else:
                modelo_documento = parcial and self.configuracao.modelo_certificacao_parcial or self.configuracao.modelo_certificacao_completa

            try:
                local_filename = cache_file(modelo_documento.name)
                caminho_arquivo = gerar_documento_impressao(dicionario, local_filename)
                os.unlink(local_filename)
                if not caminho_arquivo:
                    raise Exception('Documento não encontrado.')
                content_type = caminho_arquivo.endswith('.pdf') and 'application/pdf' or 'application/vnd.ms-word'
                arquivo = open(caminho_arquivo, 'rb')
                conteudo_arquivo = arquivo.read()
                response = HttpResponse(conteudo_arquivo, content_type=content_type)
                nome_arquivo = caminho_arquivo.split('/')[-1]
                extensao = nome_arquivo.split('.')[-1]
                response['Content-Disposition'] = f'attachment; filename=Certificado.{extensao}'
                arquivo.close()
                os.unlink(caminho_arquivo)

                if primeira_impressao:
                    registro_emissao_documento = RegistroEmissaoDocumento()
                    registro_emissao_documento.tipo = 'ENCCEJA'
                    registro_emissao_documento.codigo_verificador = self.codigo_verificador
                    registro_emissao_documento.data_emissao = self.data_emissao
                    registro_emissao_documento.documento.save(f'{self.codigo_verificador}.pdf', ContentFile(conteudo_arquivo))
                    registro_emissao_documento.data_validade = None
                    registro_emissao_documento.modelo_pk = self.pk
                    registro_emissao_documento.objeto = self
                    registro_emissao_documento.save()

                return response
            except FileNotFoundError:
                return httprr(self.get_absolute_url(), 'Erro ao processar esta solicitação. Por favor tente novamente.', 'error')
            except Exception as e:
                capture_exception(e)
                return httprr(
                    self.get_absolute_url(),
                    'Erro ao processar esta solicitação. A equipe de desenvolvimento foi notificada. Por favor, tente novamente mais tarde ou reporte um erro no SUAP.',
                    'error',
                )
        return httprr(self.get_absolute_url(), 'Não é possível certificar esta solicitação.', 'error')

    @classmethod
    def criar_solicitacao_com_aproveitamento_de_notas(cls, cpf):
        solicitacoes_encceja = (
            Solicitacao.objects.filter(cpf=cpf, configuracao__ativa=True)
            .exclude(aproveitamento_de_notas_outras_edicoes=True)
            .order_by('-configuracao__ano__ano')
        )
        if solicitacoes_encceja.count() > 1:
            ultima_solicitacao = solicitacoes_encceja.first()
            # Copia a ultima solicitação do ENCCEJA

            melhores_pontuacoes_area_conhecimento = {}
            melhores_pontuacoes_redacao = {}
            for solicitacao in solicitacoes_encceja:
                for pontuacao in solicitacao.pontuacao_set.all():
                    pontuacao_area = melhores_pontuacoes_area_conhecimento.get(pontuacao.area_conhecimento.nome)
                    if pontuacao_area:
                        if int(pontuacao_area.valor) <= int(pontuacao.valor):
                            melhores_pontuacoes_area_conhecimento[pontuacao.area_conhecimento.nome] = pontuacao
                    else:
                        melhores_pontuacoes_area_conhecimento[pontuacao.area_conhecimento.nome] = pontuacao

                if melhores_pontuacoes_redacao.get('pontuacao'):
                    if solicitacao.pontuacao_redacao and melhores_pontuacoes_redacao.get('pontuacao') < solicitacao.pontuacao_redacao:
                        melhores_pontuacoes_redacao['pontuacao'] = solicitacao.pontuacao_redacao
                        melhores_pontuacoes_redacao['avaliacao'] = solicitacao.avaliacao_redacao
                else:
                    melhores_pontuacoes_redacao['pontuacao'] = solicitacao.pontuacao_redacao or 0
                    melhores_pontuacoes_redacao['avaliacao'] = solicitacao.avaliacao_redacao

            nova_solicitacao = Solicitacao.objects.filter(inscricao=ultima_solicitacao.inscricao, aproveitamento_de_notas_outras_edicoes=True).first()
            if not nova_solicitacao:
                nova_solicitacao = copy(ultima_solicitacao)
                nova_solicitacao.pk = None
                nova_solicitacao.cadastrador = None
                nova_solicitacao.tipo_certificado = None
                nova_solicitacao.codigo_verificador = None
                nova_solicitacao.data_emissao = None
                nova_solicitacao.emissor = None
                nova_solicitacao.atendida = False
                nova_solicitacao.cancelada = False
                nova_solicitacao.data_cancelamento = None
                nova_solicitacao.responsavel_cancelamento = None
                nova_solicitacao.motivo_cancelamento = None

                nova_solicitacao.aproveitamento_de_notas_outras_edicoes = True
                nova_solicitacao.save()
                nova_solicitacao = Solicitacao.objects.get(inscricao=nova_solicitacao.inscricao, aproveitamento_de_notas_outras_edicoes=True)

            nova_solicitacao.avaliacao_redacao = melhores_pontuacoes_redacao['avaliacao']
            nova_solicitacao.pontuacao_redacao = melhores_pontuacoes_redacao['pontuacao']
            nova_solicitacao.pontuacao_set.all().delete()
            for pontuacao in melhores_pontuacoes_area_conhecimento.values():
                nova_pontuacao = copy(pontuacao)
                nova_pontuacao.pk = None
                nova_pontuacao.solicitacao = nova_solicitacao
                nova_pontuacao.save()

            nova_solicitacao.save()
            if nova_solicitacao.pode_certificar_integralmente():
                return nova_solicitacao
            # Somente poderá juntar resultados parciais para gerar um certificado completo e
            # nunca outro parcial. Verificar se essa solicitação ja foi emitida para evitar excluir.
            elif not nova_solicitacao.codigo_verificador:
                nova_solicitacao.delete()
                return ultima_solicitacao
        return None

    def get_absolute_url(self):
        return f'/encceja/solicitacao/{self.pk}/'

    def save(self, *args, **kwargs):
        self.tipo_certificado = (
            self.pode_certificar_integralmente() and Solicitacao.COMPLETO or (self.pode_certificar() and Solicitacao.PARCIAL or None)
        )
        super().save(*args, **kwargs)


class Pontuacao(models.ModelPlus):
    solicitacao = models.ForeignKeyPlus(Solicitacao, verbose_name='Solicitação', on_delete=models.CASCADE)
    avaliacao = models.ForeignKeyPlus(Avaliacao, verbose_name='Avaliação', on_delete=models.CASCADE)
    area_conhecimento = models.ForeignKeyPlus(AreaConhecimento, verbose_name='Área do Conhecimento', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus(verbose_name='Pontuação')

    class Meta:
        verbose_name_plural = 'Pontuação'
        verbose_name = 'Pontuações'

    def __str__(self):
        return f'{self.pk}'

    def is_certificado(self):
        if 'linguagens' in self.area_conhecimento.descricao.lower():
            if not self.solicitacao.atingiu_pontuacao_minima_redacao():
                return False
        return self.is_aprovado()

    def is_aprovado(self):
        return self.valor >= self.avaliacao.pontuacao_min_area_conhecimento
