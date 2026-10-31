import hashlib

from djtools.db import models
from djtools.utils import fake_request
from edu.diploma_digital import status
from edu.models.cadastros_gerais import SituacaoMatricula


class HistoricoEscolarParcial(models.ModelPlus):
    SITUACAO_CHOICES = status.STATUS_PADRAO + status.STATUS_ESPECIAIS + status.STATUS_ERRO_DOCUMENTO + status.STATUS_ERRO

    aluno = models.ForeignKeyPlus(
        'edu.aluno',
        verbose_name='Aluno',
        limit_choices_to={
            'curso_campus__assinatura_digital': True,
            'situacao_id__in': (SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL, SituacaoMatricula.TRANCADO),
        },
    )
    emissor = models.CurrentUserField(verbose_name='Emissor')
    data_emissao = models.DateFieldPlus(verbose_name='Data da Emissão', auto_now_add=True)
    id_rap = models.IntegerField(verbose_name='Identificador RAP', default=0)
    status_rap = models.IntegerField(verbose_name='Situação RAP', null=True, choices=SITUACAO_CHOICES)
    erro_rap = models.TextField(verbose_name='Erro RAP', null=True, blank=True)
    revogado = models.BooleanField(verbose_name='Revogado', default=False)

    registro_emissao_documento = models.ForeignKeyPlus('comum.registroemissaodocumento', verbose_name='Registro do Documento', null=True)

    class Meta:
        verbose_name = 'Histórico Escolar Digital Parcial'
        verbose_name_plural = 'Históricos Escolares Digitais Parciais'

    def get_token_download(self):
        return hashlib.sha256(f'{self.pk}-{self.id_rap}-{self.data_emissao.isoformat()}'.encode()).hexdigest()

    def validar_token_download(self, user, token):
        return token == self.get_token_download()

    def get_url_xml(self):
        return f'/edu/baixar_xml_historico_escolar_parcial/{self.pk}/{self.get_token_download()}/' if self.id_rap else None

    def get_url_pdf(self):
        return self.registro_emissao_documento.documento.url if self.registro_emissao_documento else None

    def baixar_xml(self):
        from edu.diploma_digital.rap import AssinadorDigital

        assinador_digital = AssinadorDigital()
        return assinador_digital.baixar_xml(self.id_rap)

    def gerar_registro_emissao_documento(self):
        from edu.diploma_digital.rap import AssinadorDigital
        from edu.views import emitir_historico_parcial_digital_pdf

        assinador_digital = AssinadorDigital()
        qr = assinador_digital.gerar_qr_code_historico(self.id, self.id_rap, 'historico_parcial_digital')
        self.registro_emissao_documento = emitir_historico_parcial_digital_pdf(fake_request(self.emissor), pk=self.pk, qr=qr)
        HistoricoEscolarParcial.objects.filter(pk=self.pk).update(registro_emissao_documento=self.registro_emissao_documento)
