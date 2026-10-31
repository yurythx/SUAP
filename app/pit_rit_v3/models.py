from __future__ import annotations

import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User

from comum.models import Ano
from djtools.db import models
from djtools.utils import tl
from edu.models import Professor
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES
from edu.models.logs import LogModel
from rh.models import Servidor


class Configuracao(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome')
    ativa = models.BooleanField(verbose_name='Ativa', default=True)

    class Meta:
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if pk is None:
            Configuracao.objects.exclude(pk=self.pk).update(ativa=False)
            configuracao = Configuracao.objects.exclude(pk=self.pk).order_by('id').last()
            if configuracao:
                for atividade in configuracao.atividade_set.all():
                    atividade.id = None
                    atividade.pk = None
                    atividade.configuracao = self
                    atividade.save()

    def delete(self, *args, **kwargs):
        if not Configuracao.objects.exclude(pk=self.pk).filter(ativa=True).exists():
            configuracao = Configuracao.objects.exclude(pk=self.pk).order_by('id').last()
            if configuracao:
                configuracao.ativa = True
                configuracao.save()
        super().delete(*args, **kwargs)


class Grupo(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome')

    class Meta:
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'

    def __str__(self):
        return self.nome


class Subgrupo(models.ModelPlus):
    grupo = models.ForeignKey(Grupo, verbose_name='Grupo', on_delete=models.CASCADE)
    nome = models.CharFieldPlus(verbose_name='Nome')

    class Meta:
        verbose_name = 'Subgrupo'
        verbose_name_plural = 'Subgrupos'

    def __str__(self):
        return self.nome


class Atividade(models.ModelPlus):
    FONTE_DADOS_DIARIOS_REGULARES = 'Diários Regulares'
    FONTE_DADOS_CHOICES = [[FONTE_DADOS_DIARIOS_REGULARES, FONTE_DADOS_DIARIOS_REGULARES]]
    configuracao = models.ForeignKey(Configuracao, verbose_name='Configuração', on_delete=models.CASCADE, null=True)
    subgrupo = models.ForeignKey(Subgrupo, verbose_name='Subgrupo', on_delete=models.CASCADE)
    nome = models.CharFieldPlus(verbose_name='Nome')
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)
    carga_horaria_unitaria = models.DecimalFieldPlus(verbose_name='Carga-Horária Unitária', null=True, blank=True)
    carga_horaria_maxima = models.DecimalFieldPlus(verbose_name='Carga-Horária Máxima', null=True, blank=True)

    fonte_dados = models.CharField(verbose_name='Fonte de Dados', choices=FONTE_DADOS_CHOICES, null=True, blank=True)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

    def __str__(self):
        return self.nome


class PlanoIndividualTrabalhoV3(LogModel):
    # DADOS GERAIS
    ano_letivo = models.ForeignKeyPlus(Ano, verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.IntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    professor = models.ForeignKeyPlus(Professor, verbose_name='Professor', on_delete=models.CASCADE)

    # DADOS DA AVALIAÇÃO DO PLANO
    data_envio = models.DateTimeFieldPlus(verbose_name='Data do Envio do Plano', null=True)
    avaliador = models.ForeignKeyPlus(Servidor, verbose_name='Avaliador do Plano', null=True, on_delete=models.CASCADE)
    aprovado = models.BooleanField(verbose_name='Plano Aprovado', null=True)
    data_aprovacao = models.DateTimeFieldPlus(verbose_name='Data da Aprovação do Plano', null=True)

    # DADOS DA AVALIAÇÃO DO RELATORIO
    data_envio_relatorio = models.DateTimeFieldPlus(verbose_name='Data do Envio do Relatório', null=True)
    avaliador_relatorio = models.ForeignKeyPlus(
        Servidor, verbose_name='Avaliador do Relatório', null=True, on_delete=models.CASCADE, related_name='avaliador_relatoriov3_set'
    )
    relatorio_aprovado = models.BooleanField(verbose_name='Relatório Aprovado', null=True)
    data_aprovacao_relatorio = models.DateTimeFieldPlus(verbose_name='Data da Aprovação do Relatório', null=True)

    # DADOS DA PUBLICAÇÃO
    publicado = models.BooleanField(verbose_name='Publicado', null=True)
    responsavel_publicacao = models.ForeignKeyPlus(
        Servidor, verbose_name='Responsável pela Publicação', null=True, related_name='responsavel_publiacaov3_set', on_delete=models.CASCADE
    )
    data_publicacao = models.DateTimeFieldPlus(verbose_name='Data da Publicação', null=True)

    def __str__(self):
        return f'Plano Individual de Trabalho - {self.professor} - {self.ano_letivo}/{self.periodo_letivo}'

    def get_absolute_url(self):
        return f'/edu/professor/{self.professor.pk}/?tab=planoatividades&ano-periodo={self.ano_letivo}.{self.periodo_letivo}'

    @classmethod
    def get_ano_inicio(cls) -> int | None:
        from comum.models import Configuracao as ConfiguracaoGeral

        valor = ConfiguracaoGeral.get_valor_por_chave('pit_rit_v3', 'ano_inicio_app')
        try:
            return int(valor) if valor else None
        except ValueError, TypeError:
            return None

    @classmethod
    def get_periodo_inicio(cls) -> int | None:
        from comum.models import Configuracao as ConfiguracaoGeral

        valor = ConfiguracaoGeral.get_valor_por_chave('pit_rit_v3', 'periodo_inicio_app')
        try:
            return int(valor) if valor else None
        except ValueError, TypeError:
            return None

    @classmethod
    def modulo_ativo(cls, ano: int | None = None, periodo: int | None = None) -> bool:
        ano_inicio = cls.get_ano_inicio()
        periodo_inicio = cls.get_periodo_inicio()
        if not ano_inicio or not periodo_inicio:
            return False
        if ano is None or periodo is None:
            return True
        return ano > ano_inicio or (ano == ano_inicio and periodo >= periodo_inicio)

    def get_ch_prevista(self):
        servidor = self.professor.vinculo.relacionamento
        carga_horaria_servidor = servidor.jornada_trabalho and servidor.jornada_trabalho.nome or None
        return 20 if carga_horaria_servidor == '20 HORAS SEMANAIS' else 40

    # Diários
    def get_vinculo_diarios(self, fic=None):
        return self.professor.get_vinculo_diarios(self.ano_letivo.ano, self.periodo_letivo, fic, None, False)

    def get_ch_diarios(self, fic=False):
        ch_semanal_credito = 0
        ch_semanal_efetiva = 0
        for professor_diario in self.get_vinculo_diarios(fic):
            ch_diario = professor_diario.get_qtd_creditos_efetiva(self.periodo_letivo)
            ch_semanal_credito += ch_diario

            componente = professor_diario.diario.componente_curricular.componente
            ch_semanal_efetiva += Decimal(ch_diario * componente.ch_hora_relogio / componente.ch_hora_aula) if componente.ch_hora_aula else 0
        return ch_semanal_credito, ch_semanal_efetiva

    # Minicursos
    def get_vinculos_minicurso(self):
        return self.professor.get_vinculos_minicurso(self.ano_letivo.ano, self.periodo_letivo)

    def get_ch_minicursos(self):
        ha = 0
        hr = 0
        for vinculo in self.get_vinculos_minicurso():
            ha += vinculo.get_carga_horaria_semanal_ha()
            hr += vinculo.carga_horaria_semanal or 0
        return ha, hr

    # Cargas-Horárias
    def get_ch_aulas(self):
        if hasattr(self, 'ch_aulas'):
            return self.ch_aulas
        ch_semanal_diarios, ch_semanal_efetiva = self.get_ch_diarios()
        ch_semanal_diarios_fic, ch_semanal_efetiva_fic = self.get_ch_diarios(True)
        ch_semanal_minicursos, ch_semanal_minicursos_hr = self.get_ch_minicursos()
        ch_semanal_aulas = ch_semanal_diarios + ch_semanal_diarios_fic + ch_semanal_minicursos
        percentual = Decimal(settings.PERCENTUAL_CH_PREPARACAO_AULAS_PIT / 100)
        ch_aulas = round(percentual * (ch_semanal_efetiva + ch_semanal_efetiva_fic + ch_semanal_minicursos_hr))
        self.ch_aulas = ch_semanal_aulas, ch_aulas
        return self.ch_aulas

    def get_atividades_planejadas(self):
        total = 0
        grupos = {}
        totais_atividades = {}
        for grupo in Grupo.objects.all():
            grupo.total = 0
            grupos[grupo] = []
            for atividade in Atividade.objects.filter(fonte_dados__isnull=False, subgrupo__grupo=grupo).order_by('id'):
                atividade_planejada = AtividadePlanejada(pit=self, atividade=atividade, bolsa_especifica=False)
                grupos[grupo].append(atividade_planejada)
                ch_considerada = atividade_planejada.get_carga_horaria_considerada(totais_atividades)
                grupo.total += ch_considerada
                total += ch_considerada
                atividade_planejada.carga_horaria = Decimal(ch_considerada)
                totais_atividades[atividade.id] = totais_atividades.get(atividade.id, 0) + ch_considerada
            for atividade_planejada in self.atividadeplanejada_set.filter(
                atividade__subgrupo__grupo=grupo, atividade__fonte_dados__isnull=True
            ).order_by('atividade_id'):
                grupos[grupo].append(atividade_planejada)
                ch_considerada = atividade_planejada.get_carga_horaria_considerada(totais_atividades)
                grupo.total += ch_considerada
                total += ch_considerada
                totais_atividades[atividade_planejada.atividade.id] = totais_atividades.get(atividade_planejada.atividade.id, 0) + ch_considerada
        return total, grupos

    def pode_enviar_plano(self, user: User) -> bool:
        return self.aprovado is None and self.data_envio is None and self.professor.vinculo.user == user

    def pode_desfazer_envio_plano(self, user: User | None = None) -> bool:
        if user is None:
            user = tl.get_user()
        return self.aprovado is None and self.data_envio is not None and user is not None and self.professor.vinculo.user == user

    def desfazer_envio_plano(self, user: User | None = None) -> None:
        if self.pode_desfazer_envio_plano(user):
            self.data_envio = None
            self.avaliador = None
            self.save()

    def pode_alterar_avaliador_plano(self, user: User) -> bool:
        return self.aprovado is None and self.data_envio and self.professor.vinculo.user == user

    def pode_avaliar_plano(self, user: User) -> bool:
        return self.aprovado is None and self.data_envio and self.avaliador.get_vinculo().user == user

    def pode_desfazer_aprovacao_plano(self, user: User) -> bool:
        return self.aprovado and self.avaliador.get_vinculo().user == user and not self.publicado and self.data_envio_relatorio is None

    def pode_desfazer_envio_relatorio(self, user: User | None = None) -> bool:
        if user is None:
            user = tl.get_user()
        return self.relatorio_aprovado is None and self.data_envio_relatorio is not None and user is not None and self.professor.vinculo.user == user

    def desfazer_envio_relatorio(self, user: User | None = None) -> None:
        if self.pode_desfazer_envio_relatorio(user):
            self.data_envio_relatorio = None
            self.avaliador_relatorio = None
            self.save()

    def devolver_plano(self, user, parecer):
        if self.pode_avaliar_plano(user) or self.pode_desfazer_aprovacao_plano(user):
            parecer.pit = self
            parecer.data = datetime.datetime.now()
            parecer.tipo = 'PIT'
            parecer.servidor = self.avaliador
            parecer.save()

            self.aprovado = None
            self.data_aprovacao = None
            self.data_envio = None
            self.avaliador = None
            self.save()

    def aprovar_plano(self, user, parecer):
        if self.pode_avaliar_plano(user):
            self.aprovado = True
            self.data_aprovacao = datetime.datetime.now()
            self.save()

            parecer.pit = self
            parecer.data = self.data_aprovacao
            parecer.tipo = 'PIT'
            parecer.servidor = self.avaliador
            parecer.save()

    def get_carga_horaria(self, fonte_dados):
        if fonte_dados == Atividade.FONTE_DADOS_DIARIOS_REGULARES:
            return self.get_ch_aulas()[1]
        return 0


class AtividadePlanejada(models.ModelPlus):
    pit = models.ForeignKey(PlanoIndividualTrabalhoV3, verbose_name='PIT', on_delete=models.CASCADE)
    atividade = models.ForeignKeyPlus(Atividade, verbose_name='Atividade', on_delete=models.CASCADE)
    objeto_institucional = models.CharFieldPlus(verbose_name='Objeto Institucional')
    carga_horaria = models.DecimalFieldPlus(verbose_name='Carga-Horária')
    bolsa_especifica = models.BooleanField(verbose_name='Bolsa ou Retribuição Específica')
    comprovante = models.FileFieldPlus(verbose_name='Comprovante', upload_to='comprovante_pit_rit_v3', null=True, blank=True, filetypes=['pdf'])
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Atividade Planejada'
        verbose_name_plural = 'Atividades Planejadas'

    def __str__(self):
        return self.atividade.nome

    def get_carga_horaria_considerada(self, totais_atividades):
        if self.bolsa_especifica:
            return Decimal(0)
        carga_horaria = self.carga_horaria
        if self.atividade.fonte_dados:
            carga_horaria = self.pit.get_carga_horaria(self.atividade.fonte_dados)
        ch_considerada = Decimal(carga_horaria)
        novo_total_considerado = (totais_atividades.get(self.atividade_id, 0) if totais_atividades else 0) + ch_considerada
        if self.atividade.carga_horaria_maxima and novo_total_considerado > self.atividade.carga_horaria_maxima:
            ch_considerada = max(ch_considerada - novo_total_considerado + self.atividade.carga_horaria_maxima, 0)
        if self.atividade.carga_horaria_unitaria and ch_considerada > self.atividade.carga_horaria_unitaria:
            ch_considerada = self.atividade.carga_horaria_unitaria
        self.carga_horaria_considerada = ch_considerada
        return self.carga_horaria_considerada


class Parecer(models.ModelPlus):
    pit = models.ForeignKeyPlus(PlanoIndividualTrabalhoV3, verbose_name='Plano Individual de Trabalho')
    tipo = models.CharFieldPlus(verbose_name='Tipo', null=True, choices=[['PIT', 'PIT'], ['RIT', 'RIT']], default='PIT')
    data = models.DateTimeFieldPlus(verbose_name='Data')
    obs = models.TextField(verbose_name='Observação')
    servidor = models.ForeignKeyPlus(
        Servidor, verbose_name='Servidor', null=True, on_delete=models.CASCADE, help_text='Servidor que emitiu o parecer', related_name='pareceres'
    )

    class Meta:
        verbose_name = 'Parecer'
        verbose_name_plural = 'Pareceres'
        ordering = ('-data',)

    def __str__(self):
        return self.obs
