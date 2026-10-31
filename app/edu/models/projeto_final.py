import datetime
import uuid

from django.conf import settings

from comum.models import Configuracao, Sala
from comum.utils import tl
from djtools.db import models
from djtools.utils import mask_nota, send_mail
from edu.models.logs import LogModel


class ProjetoFinal(LogModel):
    TIPO_ATA_FISICA = 'fisica'
    TIPO_ATA_ELETRONICA = 'eletronica'

    TIPO_ATA_CHOICES = [[TIPO_ATA_FISICA, 'Física'], [TIPO_ATA_ELETRONICA, 'Eletrônica']]

    TIPO_PROJETO_CHOICES = [
        ['Monografia', 'Monografia'],
        ['Dissertação', 'Dissertação'],
        ['Tese', 'Tese'],
        ['Artigo Científico', 'Artigo Científico'],
        ['Capítulo de Livro', 'Capítulo de Livro'],
        ['Portfólio', 'Portfólio'],
        ['Trabalho de Conclusão de Curso', 'Trabalho de Conclusão de Curso'],
        ['Relatório de Projeto', 'Relatório de Projeto'],
    ]

    SITUACAO_APROVADO = 1
    SITUACAO_REPROVADO = 2
    SITUACAO_CHOICES = [[SITUACAO_APROVADO, 'Aprovado'], [SITUACAO_REPROVADO, 'Reprovado']]

    # Dados gerais
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    titulo = models.CharFieldPlus('Título do Trabalho', null=False, blank=False)
    resumo = models.TextField('Resumo do Trabalho', null=False, blank=False)
    tipo = models.CharFieldPlus(choices=TIPO_PROJETO_CHOICES, verbose_name='Tipo de Trabalho', null=False, blank=False)
    informacao_complementar = models.TextField('Informações Complementares', null=True, blank=True)
    documento = models.FileFieldPlus('Arquivo Digitalizado do Projeto', upload_to='edu/projeto_final/', null=True, blank=True)
    documento_final = models.FileFieldPlus('Arquivo Final Digitalizado do Projeto', upload_to='edu/projeto_final/', null=True, blank=True)

    # Dados da Orientação
    orientador = models.ForeignKeyPlus('edu.Professor', related_name='orientador_set', verbose_name='Orientador', null=True, blank=True)
    coorientadores_vinculos = models.ManyToManyFieldPlus(
        'comum.Vinculo', related_name='coorientadores_vinculos_set', verbose_name='Coorientadores', blank=True
    )

    # Dados da Defesa
    data_defesa = models.DateTimeFieldPlus('Data Prevista', null=True, blank=True)
    data_deposito = models.DateTimeFieldPlus('Data de Depósito ', null=True, blank=True)
    local_defesa = models.ForeignKeyPlus(Sala, verbose_name='Local', null=True, blank=True)
    defesa_online = models.BooleanField(
        verbose_name='Defesa Online',
        default=False,
        blank=True,
        help_text='Marque essa opção caso os membros da banca tenham acompanhado ou acompanharão a defesa virtualmente.',
    )

    # Dados da Banca
    presidente = models.ForeignKeyPlus('edu.Professor', related_name='presidente_set', verbose_name='Presidente', null=True, blank=True)
    examinador_interno = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='examinador_interno_set', verbose_name='Examinador Interno', null=True, blank=True
    )
    examinador_externo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='examinador_externo_set', verbose_name='Segundo Examinador', null=True, blank=True
    )
    is_examinador_externo = models.BooleanField('Externo', default=True, help_text='Marque essa opção caso o segundo examinador seja externo.')

    terceiro_examinador = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='terceiro_examinador_set', verbose_name='Terceiro Examinador', null=True, blank=True
    )
    is_terceiro_examinador_externo = models.BooleanField(
        'Externo', default=True, help_text='Marque essa opção caso o terceiro examinador seja externo.'
    )

    suplente_interno = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='suplente_interno_set', verbose_name='Suplente Interno', null=True, blank=True
    )
    suplente_externo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='suplente_externo_set', verbose_name='Segundo Suplente', null=True, blank=True
    )
    is_suplente_externo = models.BooleanField('Externo', default=True, help_text='Marque essa opção caso o segundo suplente seja externo.')

    terceiro_suplente = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='terceiro_suplente_set', verbose_name='Terceiro Suplente', null=True, blank=True
    )
    is_terceiro_suplente_externo = models.BooleanField('Externo', default=True, help_text='Marque essa opção caso o terceiro suplente seja externo.')
    # Dados Resultado
    resultado_data = models.DateTimeFieldPlus('Data da Defesa', null=True, blank=True)
    nota = models.NotaField(null=True, blank=True)
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_CHOICES, null=True, blank=True)

    ata = models.FileFieldPlus('Ata da Defesa', upload_to='edu/projeto_final_ata/', null=True, blank=True)
    documento_url = models.CharFieldPlus('Link para Arquivo Digitalizado do Projeto', null=True, blank=True)
    documento_final_url = models.CharFieldPlus('Link Final para Arquivo Digitalizado do Projeto', null=True, blank=True)
    documento_cadastrado_por = models.CurrentUserField(verbose_name='Arquivo Digitalizado Cadastrado Por', null=True, blank=True)
    documento_cadastrado_em = models.DateTimeFieldPlus(verbose_name='Arquivo Digitalizado Cadastrado Em', null=True, blank=True)

    class Meta:
        verbose_name = 'Trabalho de Conclusão de Curso'
        verbose_name_plural = 'Trabalhos de Conclusão de Curso'

    def get_absolute_url(self):
        return f'/edu/visualizar_projeto_final/{self.pk}/'

    def get_tipo_examinador(self, vinculo):
        if self.examinador_interno and self.examinador_interno.pk == vinculo.pk:
            return 'examinador_interno'
        elif self.examinador_externo and self.examinador_externo.pk == vinculo.pk:
            return 'examinador_externo'
        elif self.terceiro_examinador and self.terceiro_examinador.pk == vinculo.pk:
            return 'terceiro_examinador'

    def get_aluno(self):
        return self.matricula_periodo.aluno

    def get_nota(self):
        estrutura = self.matricula_periodo.aluno.matriz.estrutura
        if estrutura.is_lancamento_conceito():
            nota = estrutura.get_conceito(self.nota)
        else:
            nota = mask_nota(self.nota)
        return nota

    def get_nome_documento(self):
        return self.documento.name.split('/')[-1]

    def get_nome_ata(self):
        return self.ata and self.ata.name.split('/')[-1] or ''

    def get_ano_periodo_letivo(self):
        return f'{self.matricula_periodo.ano_letivo}.{self.matricula_periodo.periodo_letivo}'

    def get_titulo_participante(self, participante='orientador'):
        vinculo = getattr(self, participante, None)
        if participante == 'orientador' or participante == 'presidente':
            vinculo = vinculo.vinculo
        sexo = vinculo and vinculo.pessoa.pessoafisica.sexo or 'M'

        if participante == 'examinador_interno':
            participacao = 'Examinador Interno'
            if sexo == 'F':
                participacao = 'Examinadora Interna'

        elif participante == 'examinador_externo':
            if self.is_examinador_externo:
                participacao = 'Examinador Externo'
                if sexo == 'F':
                    participacao = 'Examinadora Externa'
            else:
                participacao = 'Examinador Interno'
                if sexo == 'F':
                    participacao = 'Examinadora Interna'

        elif participante == 'terceiro_examinador':
            if self.is_terceiro_examinador_externo:
                participacao = 'Examinador Externo'
                if sexo == 'F':
                    participacao = 'Examinadora Externa'
            else:
                participacao = 'Examinador Interno'
                if sexo == 'F':
                    participacao = 'Examinadora Interna'

        elif participante == 'suplente_interno':
            participacao = 'Examinador Suplente Interno'
            if sexo == 'F':
                participacao = 'Examinadora Suplente Interna'

        elif participante == 'suplente_externo':
            if self.is_suplente_externo:
                participacao = 'Examinador Suplente Externo'
                if sexo == 'F':
                    participacao = 'Examinadora Suplente Interna'
            else:
                participacao = 'Examinador Suplente Interno'
                if sexo == 'F':
                    participacao = 'Examinadora Suplente Interna'

        elif participante == 'terceiro_suplente':
            if self.is_terceiro_suplente_externo:
                participacao = 'Examinador Suplente Externo'
                if sexo == 'F':
                    participacao = 'Examinadora Suplente Interna'
            else:
                participacao = 'Examinador Suplente Interno'
                if sexo == 'F':
                    participacao = 'Examinadora Suplente Interna'

        elif participante == 'presidente':
            participacao = 'Presidente'

        else:
            participacao = 'Orientador'
            if sexo == 'F':
                participacao = 'Orientadora'
        if vinculo and self.coorientadores_vinculos.filter(pk=vinculo.pk).exists():
            participacao = 'Coorientador{} e {}'.format('a' if sexo == 'F' else '', participacao)
        return sexo, participacao, vinculo

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        tipo_ata = Configuracao.get_valor_por_chave('edu', 'tipo_ata_projeto_final')
        pode_atualizar_aluno = tipo_ata == ProjetoFinal.TIPO_ATA_ELETRONICA and self.get_ata_eletronica() or tipo_ata == ProjetoFinal.TIPO_ATA_FISICA
        if self.resultado_data and pode_atualizar_aluno:
            self.matricula_periodo.aluno.atualizar_situacao('Lançamento de Projeto Final')

    def delete(self, *args, **kwargs):
        if not self.matricula_periodo.aluno.is_concluido() or tl.get_user().is_superuser:
            super().delete(*args, **kwargs)
            if self.resultado_data:
                self.matricula_periodo.aluno.atualizar_situacao('Exclusão de Projeto Final')
        else:
            raise Exception('Impossível excluir projeto final de aluno concluído.')

    def get_url_ata(self):
        ata_eletronica = self.ataeletronica_set.first()
        if ata_eletronica:
            return f'/edu/visualizar_ata_eletronica/{ata_eletronica.pk}/'
        else:
            return f'/edu/ata_projeto_final_pdf/{self.pk}/'

    def get_assinaturas_eletronicas_pendentes(self):
        return AssinaturaAtaEletronica.objects.filter(ata__projeto_final=self, data__isnull=True)

    def get_assinaturas_eletronicas_concluidas(self):
        return AssinaturaAtaEletronica.objects.filter(ata__projeto_final=self, data__isnull=False)

    def get_ata_eletronica(self):
        return self.ataeletronica_set.first()

    def pode_ser_editado(self):
        ata_eletronica = self.get_ata_eletronica()
        return ata_eletronica is None or not ata_eletronica.assinaturaataeletronica_set.filter(data__isnull=False).exists()


class MembroBanca(LogModel):
    nome = models.CharFieldPlus('Nome')
    email = models.EmailField('Email')
    sexo = models.CharField(max_length=1, null=True, choices=[['M', 'Masculino'], ['F', 'Feminino']])
    instituicao = models.CharFieldPlus('Instituição')
    formacao = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Formação', null=False, blank=False, on_delete=models.CASCADE)

    fieldsets = (('Dados gerais', {'fields': ('nome', 'email', 'sexo', 'instituicao', 'formacao')}),)

    class Meta:
        verbose_name = 'Membro da Banca'
        verbose_name_plural = 'Membros da Banca'

    def get_absolute_url(self):
        return f'/edu/visualizar/edu/membrobanca/{self.pk:d}/'


class AtaEletronica(models.ModelPlus):
    projeto_final = models.ForeignKeyPlus(ProjetoFinal, verbose_name='Projeto Final')
    consideracoes = models.TextField(verbose_name='Considerações')

    class Meta:
        verbose_name = 'Ata Eletrônica'
        verbose_name_plural = 'Atas Eletrônicas'

    def __str__(self):
        return f'Ata - {self.projeto_final}'

    def get_assinaturas(self):
        return self.assinaturaataeletronica_set.all()

    def criar_assinaturas(self):
        qs = ProjetoFinal.objects.filter(pk=self.projeto_final.pk).values(
            'presidente__vinculo',
            'examinador_interno',
            'examinador_externo',
            'terceiro_examinador',
            'suplente_interno',
            'suplente_externo',
            'terceiro_suplente',
        )
        pks = set()
        for item in qs:
            for pk in item.values():
                if pk:
                    pks.add(pk)
        for pk in pks:
            if not AssinaturaAtaEletronica.objects.filter(ata=self, vinculo_id=pk).exists():
                AssinaturaAtaEletronica.objects.get_or_create(ata=self, vinculo_id=pk)
        AssinaturaAtaEletronica.objects.filter(ata=self, data__isnull=True).exclude(vinculo_id__in=pks).delete()

    def is_assinaturas_concluidas(self):
        return not self.get_assinaturas().filter(data__isnull=True).exists()


class AssinaturaAtaEletronica(models.ModelPlus):
    ata = models.ForeignKeyPlus(AtaEletronica, verbose_name='Ata Eletrônica')
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Pessoa', null=True, blank=True)
    data = models.DateTimeFieldPlus(verbose_name='Data da Assinatura', null=True)
    chave = models.CharFieldPlus(verbose_name='Chave', null=True)

    class Meta:
        verbose_name = 'Assinatura de Ata Eletrônica'
        verbose_name_plural = 'Assinaturas de Atas Eletrônicas'

    def __str__(self):
        return f'Assinatura de {self.vinculo} da ata {self.ata.projeto_final}'

    def assinar(self):
        self.data = datetime.datetime.now()
        self.chave = uuid.uuid1().hex
        self.save()
        if self.ata.is_assinaturas_concluidas():
            aluno = self.ata.projeto_final.matricula_periodo.aluno
            if aluno.matriz.exige_tcc:
                aluno.atualizar_situacao('Assinatura de Ata de Projeto Final')

    def enviar_email(self):
        titulo = '[SUAP] Solicitação de Assinatura de Ata'
        url = f'<a href="{settings.SITE_URL}/admin/edu/ataeletronica/?tab=tab_pendentes">{settings.SITE_URL}/admin/edu/ataeletronica/</a>'
        texto = f'Uma solicitação de asssinatura de ata eletrônica foi endereçada a você. Para assiná-la, acesse {url}.'
        email_destino = [self.vinculo.email_pessoal, self.vinculo.email_notificacao]
        return send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, email_destino)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.enviar_email()
        super().save(*args, **kwargs)
