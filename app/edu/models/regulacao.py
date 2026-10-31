from django.conf import settings
from django.core.exceptions import ValidationError

from djtools.db import models
from edu.models.cadastros_gerais import Modalidade
from edu.models.cursos import CursoCampus
from edu.models.logs import LogModel


class Credenciamento(LogModel):
    SEARCH_FIELDS = ['nome']
    CREDECIAMENTO = 1
    RECREDECIAMENTO = 2
    RENOVACAO_RECREDECIAMENTO = 3

    TIPO_CHOICES = [
        [CREDECIAMENTO, 'Credenciamento'],
        [RECREDECIAMENTO, 'Recredenciamento'],
        [RENOVACAO_RECREDECIAMENTO, 'Renovação de Recredenciamento'],
    ]

    tipo = models.PositiveIntegerFieldPlus(verbose_name='Tipo', choices=TIPO_CHOICES)
    tipo_ato = models.CharFieldPlus(
        verbose_name='Tipo',
        choices=[
            ['Parecer', 'Parecer'],
            ['Resolução', 'Resolução'],
            ['Decreto', 'Decreto'],
            ['Portaria', 'Portaria'],
            ['Lei Federal', 'Lei Federal'],
            ['Lei Estadual', 'Lei Estadual'],
            ['Lei Municipal', 'Lei Municipal'],
            ['Ato Próprio', 'Ato Próprio'],
        ],
    )
    numero_ato = models.CharFieldPlus(verbose_name='Número')
    data_ato = models.DateFieldPlus(verbose_name='Data')

    numero_publicacao = models.CharFieldPlus(verbose_name='Número da Publicação')
    data_publicacao = models.DateFieldPlus(verbose_name='Data da Publicação')
    veiculo_publicacao = models.CharFieldPlus(verbose_name='Veículo da Publicação', choices=[['DOU', 'DOU']])
    secao_publicacao = models.CharFieldPlus(verbose_name='Seção da Publicação')
    pagina_publicacao = models.CharFieldPlus(verbose_name='Página da Publicação')

    natureza_participacao = models.ManyToManyFieldPlus('edu.NaturezaParticipacao', verbose_name='Natureza de participação', blank=False)
    orgao = models.CharFieldPlus(verbose_name='Órgão', null=True, blank=True)
    sem_numero = models.BooleanField(verbose_name='Sem número', default=False)

    class Meta:
        verbose_name = 'Credenciamento'
        verbose_name_plural = 'Credenciamentos'

    def __str__(self):
        publicacao = ''
        if self.veiculo_publicacao:
            data_publicacao = ''
            if self.data_publicacao:
                data_publicacao = f' em {self.data_publicacao.strftime("%d/%m/%Y")}'
            publicacao = f'. Publicado no {self.veiculo_publicacao} N° {self.numero_publicacao}, seção {self.secao_publicacao}, página {self.pagina_publicacao}{data_publicacao}'
        numero = f' N° {self.numero_ato}/' if not self.sem_numero else ''
        orgao = f' {self.orgao}' or ''
        return f'{self.tipo_ato}{orgao}{numero}{self.data_ato.year}{publicacao}.'


class AtoRegulatorioCurso(LogModel):
    TIPO_AUTORIZACAO = '1'
    TIPO_ADEQUACAO_PAFC = '2'
    TIPO_RECONHECIMENTO = '3'
    TIPO_RENOVACAO = '4'
    TIPO_ALTERACAO_VAGAS = '5'
    TIPO_SUSPENSAO = '6'
    TIPO_REATIVACAO = '7'
    TIPO_EM_EXTINCAO = '8'
    TIPO_EXTINTO = '9'
    TIPO_CRIACAO_CURSO = '10'
    TIPO_ALTERACAO_ENDERECO = '11'
    TIPO_ALTERACAO_NOME = '12'

    TIPO_CHOICES = [
        [TIPO_AUTORIZACAO, 'Autorização de funcionamento'],
        [TIPO_ADEQUACAO_PAFC, 'Adequação do PAFC'],
        [TIPO_RECONHECIMENTO, 'Reconhecimento'],
        [TIPO_RENOVACAO, 'Renovação de reconhecimento'],
        [TIPO_CRIACAO_CURSO, 'Criação de curso'],
        [TIPO_ALTERACAO_VAGAS, 'Alteração de quantitativo de vagas'],
        [TIPO_ALTERACAO_ENDERECO, 'Alteração de endereço'],
        [TIPO_ALTERACAO_NOME, 'Alteração de denominação'],
        [TIPO_SUSPENSAO, 'Suspensão da oferta'],
        [TIPO_REATIVACAO, 'Reativação da oferta'],
        [TIPO_EM_EXTINCAO, 'Iniciação de extinção de curso'],
        [TIPO_EXTINTO, 'Extinção de curso'],
    ]

    TIPO_DOCUMENTO_CHOICES = [
        ['Resolução', 'Resolução'],
        ['Portaria', 'Portaria'],
        ['Lei Federal', 'Lei Federal'],
        ['Deliberação', 'Deliberação'],
    ]

    MODALIDADE_EXIGE_RECONHECIMENTO = [
        Modalidade.BACHARELADO,
        Modalidade.ENGENHARIA,
        Modalidade.LICENCIATURA,
        Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
        Modalidade.TECNOLOGIA,
    ]

    # dados gerais
    tipo = models.CharFieldPlus(verbose_name='Tipo', null=False, blank=False, choices=TIPO_CHOICES)
    curso = models.ForeignKeyPlus('edu.CursoCampus', verbose_name='Curso')
    quantidade_vagas = models.PositiveIntegerField('Quantidade de vagas anuais autorizadas', null=True, blank=True)
    id_pafc = models.PositiveIntegerFieldPlus(
        verbose_name='Identificador PAFC', null=True, blank=True, help_text='Código de identificação do PAFC que gerou o ato regulatório.'
    )

    # dados do documento
    tipo_documento = models.CharFieldPlus(verbose_name='Tipo de documento', choices=TIPO_DOCUMENTO_CHOICES, null=False, blank=True)
    data = models.DateFieldPlus(verbose_name='Data', null=False, blank=True)
    numero = models.CharFieldPlus(verbose_name='Número', null=False, blank=True)
    orgao = models.CharFieldPlus(verbose_name='Órgão', null=False, blank=True)
    validade = models.DateFieldPlus(verbose_name='Validade', null=True, blank=True)
    id_documento = models.PositiveIntegerFieldPlus(
        verbose_name='Identificador', null=True, blank=True, help_text='Código de identificação do documento.'
    )
    arquivo_documento = models.FileFieldPlus(
        'Documento',
        upload_to='edu/atos_regulatorios/',
        null=True,
        blank=True,
        filetypes=[
            'pdf',
        ],
    )
    url_documento = models.URLField(verbose_name='Link do D.O.U.', null=True, blank=True)
    ad_referendum = models.BooleanField(verbose_name='Ad Referendum', default=False)
    ato_homologador = models.ForeignKeyPlus(
        'edu.AtoRegulatorioCurso', verbose_name='Ato de homologação', null=True, blank=True, on_delete=models.SET_NULL
    )

    # dados da publicação
    veiculo_publicacao = models.CharFieldPlus(verbose_name='Veículo da publicação', choices=[['DOU', 'DOU']], null=True, blank=True)
    numero_publicacao = models.CharFieldPlus(verbose_name='Número da publicação', blank=True, null=True)
    data_publicacao = models.DateFieldPlus(verbose_name='Data da publicação', blank=True, null=True)
    pagina_publicacao = models.CharFieldPlus(verbose_name='Página da publicação', blank=True, null=True)
    secao_publicacao = models.CharFieldPlus(verbose_name='Seção da publicação', blank=True, null=True)

    class Meta:
        verbose_name = 'Ato regulatório de curso'
        verbose_name_plural = 'Atos regulatórios de cursos'

        permissions = (('recebe_notificao_curso_suspenso', 'Pode receber notificação de curso suspenso'),)

    def __str__(self):
        publicacao = ''
        if self.veiculo_publicacao:
            data_publicacao = ''
            if self.data_publicacao:
                data_publicacao = f' em {self.data_publicacao.strftime("%d/%m/%Y")}'
            publicacao = f'. Publicado no {self.veiculo_publicacao} N° {self.numero_publicacao}, seção {self.secao_publicacao}, página {self.pagina_publicacao}{data_publicacao}'
        return f'{self.tipo_documento} {self.orgao} N° {self.numero}/{self.data.year}{publicacao}.'

    def clean(self):
        if self.veiculo_publicacao:
            campos_vazios = []
            if not self.numero_publicacao:
                campos_vazios.append('Número da publicação')
            if not self.data_publicacao:
                campos_vazios.append('Data da publicação')
            if not self.pagina_publicacao:
                campos_vazios.append('Página da publicação')
            if not self.secao_publicacao:
                campos_vazios.append('Seção da publicação')

            if campos_vazios:
                raise ValidationError(f"Os campos {', '.join(campos_vazios)} são obrigatórios quando o campo 'Veículo da publicação' é preenchido.")

        if self.ad_referendum:
            if self.ato_homologador and self.data > self.ato_homologador.data:
                data_ad = self.data.strftime('%d/%m/%Y')
                data_ho = self.ato_homologador.data.strftime('%d/%m/%Y')
                raise ValidationError(f'A data deste ato Ad Referendum ({data_ad}) não pode ser maior que a data do ato de homologação ({data_ho}).')
        else:
            if self.ato_homologador:
                raise ValidationError('Este ato possui ato de homologação e não pode ter a opção "Ad Referendum" desmarcada.')

            ato_ad_referendum = self.id and self.atoregulatoriocurso_set.first()
            if ato_ad_referendum and ato_ad_referendum.data > self.data:
                data_ad = ato_ad_referendum.data.strftime('%d/%m/%Y')
                data_ho = self.data.strftime('%d/%m/%Y')
                raise ValidationError(f'A data do ato Ad Referendum ({data_ad}) não pode ser maior que a data deste ato de homologação ({data_ho}).')

        curso = CursoCampus.objects.get(id=self.curso_id)
        if self.tipo == AtoRegulatorioCurso.TIPO_AUTORIZACAO:
            if self.ad_referendum is True:
                if curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO, ad_referendum=True).exclude(id=self.pk).exists():
                    raise ValidationError('Este curso já possui um ato de regulatório Ad Referendum de autorização de funcionamento.')
                if self.id is None and curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO).exists():
                    raise ValidationError('Este curso já possui um ato de regulatório de autorização de funcionamento.')
            if (
                self.ad_referendum is False
                and curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO, ad_referendum=False).exclude(id=self.pk).exists()
            ):
                raise ValidationError('Este curso já possui um ato de regulatório de autorização de funcionamento.')

        elif self.tipo == AtoRegulatorioCurso.TIPO_RECONHECIMENTO:
            if self.ad_referendum is True:
                if (
                    curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO, ad_referendum=True)
                    .exclude(id=self.pk)
                    .exists()
                ):
                    raise ValidationError('Este curso já possui um ato de regulatório Ad Referendum de reconhecimento.')
                if self.id is None and curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO).exists():
                    raise ValidationError('Este curso já possui um ato de regulatório de reconhecimento.')
            if (
                self.ad_referendum is False
                and curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO, ad_referendum=False)
                .exclude(id=self.pk)
                .exists()
            ):
                raise ValidationError('Este curso já possui um ato de regulatório de reconhecimento.')

        elif self.tipo == AtoRegulatorioCurso.TIPO_EXTINTO and curso.possui_aluno_cursando():
            raise ValidationError('Este curso não pode ser extinto pois possui alunos com situação de matrícula não finalizada.')

        elif self.tipo == AtoRegulatorioCurso.TIPO_CRIACAO_CURSO:
            if self.curso.modalidade_id not in [Modalidade.MESTRADO, Modalidade.DOUTORADO]:
                raise ValidationError('O ato de criação de curso pode ser usado apenas para cursos das modalidades mestrado ou doutorado.')
            if (
                self.ad_referendum is True
                and curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_CRIACAO_CURSO, ad_referendum=True).exclude(id=self.pk).exists()
            ):
                raise ValidationError('Este curso já possui um ato de regulatório Ad Referendum de criação de curso.')
            if (
                self.ad_referendum is False
                and curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_CRIACAO_CURSO, ad_referendum=False)
                .exclude(id=self.pk)
                .exists()
            ):
                raise ValidationError('Este curso já possui um ato de regulatório de criação de curso.')

        super().clean()

    def delete(self, *args, **kwargs):
        if self.atoregulatoriocurso_set.first() is None:  # se não é homologação de ad referendum
            if self.tipo == AtoRegulatorioCurso.TIPO_SUSPENSAO:
                curso = CursoCampus.objects.get(id=self.curso_id)
                curso.suspenso = False
                curso.save()

            elif self.tipo == AtoRegulatorioCurso.TIPO_REATIVACAO:
                curso = CursoCampus.objects.get(id=self.curso_id)
                curso.suspenso = True
                curso.save()

            elif self.tipo == AtoRegulatorioCurso.TIPO_EM_EXTINCAO:
                curso = CursoCampus.objects.get(id=self.curso_id)
                curso.em_extincao = False
                curso.save()

            elif self.tipo == AtoRegulatorioCurso.TIPO_EXTINTO:
                curso = CursoCampus.objects.get(id=self.curso_id)
                curso.extinto = False
                curso.ativo = True
                curso.data_fim = None
                curso.save()

        super().delete(*args, **kwargs)

    def can_delete(self, user):
        result = user.has_perm('edu.delete_atoregulatoriocurso')
        if result and self.ad_referendum:
            result = self.ato_homologador is None
        return result

    def gerar_ato(self, id_documento, arquivo_documento, url_documento, ato_ad_referendum=None):
        if id_documento:
            documento = AtoRegulatorioCurso.get_documento(id_documento)
            if documento:
                self.tipo_documento = documento.modelo.tipo_documento_texto.nome
                self.data = documento.data_emissao or documento.data_criacao
                self.numero = documento.identificador_numero
                self.orgao = documento.identificador_setor_sigla or f'{documento.setor_dono.sigla}/{documento.setor_dono.uo.sigla}'
                self.save()
            else:
                raise ValidationError('Documento não encontrado')

        elif arquivo_documento or url_documento or (self.id and self.id_pafc):
            self.save()
        else:
            raise ValidationError('Cadastro incompleto')

        if ato_ad_referendum:
            ato_ad_referendum.ato_homologador = self
            ato_ad_referendum.save()
        else:
            qs = AtoRegulatorioCurso.objects.filter(tipo=self.tipo, curso_id=self.curso_id, data__gt=self.data)
            if not qs.exclude(id=self.ato_homologador_id).exists():
                if self.tipo == AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS:
                    curso = CursoCampus.objects.get(id=self.curso_id)
                    curso.quantidade_vagas = self.quantidade_vagas
                    curso.save()

                elif self.tipo == AtoRegulatorioCurso.TIPO_SUSPENSAO:
                    curso = CursoCampus.objects.get(id=self.curso_id)
                    curso.suspenso = True
                    curso.save()

                elif self.tipo == AtoRegulatorioCurso.TIPO_REATIVACAO:
                    curso = CursoCampus.objects.get(id=self.curso_id)
                    curso.suspenso = False
                    curso.save()

                elif self.tipo == AtoRegulatorioCurso.TIPO_EM_EXTINCAO:
                    curso = CursoCampus.objects.get(id=self.curso_id)
                    curso.em_extincao = True
                    curso.save()

                elif self.tipo == AtoRegulatorioCurso.TIPO_EXTINTO:
                    curso = CursoCampus.objects.get(id=self.curso_id)
                    curso.extinto = True
                    curso.ativo = False
                    curso.data_fim = (
                        AtoRegulatorioCurso.objects.filter(tipo=AtoRegulatorioCurso.TIPO_EXTINTO, curso_id=self.curso_id)
                        .order_by('data')
                        .first()
                        .data
                    )
                    curso.save()

    @staticmethod
    def gerar_ato_pafc(curso_id, adequacao, qtd_vagas, id_documento, id_pafc):
        documento = AtoRegulatorioCurso.get_documento(id_documento)
        if documento:
            ato = AtoRegulatorioCurso()
            ato.id_pafc = id_pafc
            ato.curso_id = curso_id
            ato.id_documento = id_documento
            if adequacao:
                ato.tipo = AtoRegulatorioCurso.TIPO_ADEQUACAO_PAFC
            else:
                ato.tipo = AtoRegulatorioCurso.TIPO_AUTORIZACAO
            ato.tipo_documento = documento.modelo.tipo_documento_texto.nome
            ato.data = documento.data_criacao
            ato.numero = documento.identificador_numero
            ato.orgao = documento.identificador_setor_sigla or f'{documento.setor_dono.sigla}/{documento.setor_dono.uo.sigla}'
            ato.save()

            return ato
        else:
            raise ValidationError('Documento não encontrado.')

    @staticmethod
    def gerar_ato_alteracao_vagas_pafc(curso_id, qtd_vagas, id_documento, id_pafc):
        documento = AtoRegulatorioCurso.get_documento(id_documento)
        if documento:
            ato = AtoRegulatorioCurso()
            ato.curso_id = curso_id
            ato.tipo = AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS
            ato.quantidade_vagas = qtd_vagas
            ato.id_pafc = id_pafc
            ato.id_documento = id_documento
            ato.tipo_documento = documento.modelo.tipo_documento_texto.nome
            ato.data = documento.data_criacao
            ato.numero = documento.identificador_numero
            ato.orgao = documento.identificador_setor_sigla or f'{documento.setor_dono.sigla}/{documento.setor_dono.uo.sigla}'
            ato.save()

            return ato
        else:
            raise ValidationError('Documento não encontrado.')

    @staticmethod
    def get_documento(id_documento):
        result = None
        if id_documento and 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            result = DocumentoTexto.objects.filter(id=id_documento).first()
        return result

    def get_numero_com_orgao(self):
        result = f'{self.numero}/{self.data.year}'
        if self.orgao:
            result = f'{result}-{self.orgao}'
        return result


class TramitacaoProcessoEMEC(LogModel):
    TIPO_PROCESSO_CHOICES = [
        ['1', 'Reconhecimento de curso'],
        ['2', 'Reconhecimento de curso EAD'],
        ['3', 'Renovação de reconhecimento de curso'],
        ['4', 'Renovação de reconhecimento de curso EAD'],
    ]

    curso = models.ForeignKeyPlus('edu.CursoCampus', verbose_name='Curso')
    numero_processo = models.CharFieldPlus(verbose_name='Número do processo', blank=False, null=False)
    tipo_processo = models.CharFieldPlus(verbose_name='Tipo do processo', null=False, blank=False, choices=TIPO_PROCESSO_CHOICES)
    data_cadastro = models.DateFieldPlus(verbose_name='Data de cadastro', blank=False, null=False)
    data_protocolo = models.DateFieldPlus(verbose_name='Data do protocolo', blank=False, null=False)

    class Meta:
        verbose_name = 'Tramitação de processo e-MEC'
        verbose_name_plural = 'Tramitações de processos e-MEC'
