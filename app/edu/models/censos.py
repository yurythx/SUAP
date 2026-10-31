import datetime
import io
import os
import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction

from comum.models import CertificadoDigital, Configuracao, User, UsuarioGrupo
from djtools.db import models
from djtools.templatetags.filters.utils import format_data_extenso
from djtools.utils import gerar_documento_impressao, libreoffice_new_line, mask_cpf, send_notification, somar_dias
from edu.managers import FiltroUnidadeOrganizacionalManager
from edu.models import Aluno, LogModel
from rh.models import Setor, UnidadeOrganizacional


class RegistroEducacenso(LogModel):
    SEARCH_FIELDS = [
        'ano_censo__ano',
        'numero_registro',
    ]

    ano_censo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano do Censo', null=False, blank=False)
    numero_registro = models.CharFieldPlus(verbose_name='Número do Registro', null=False, blank=False)
    privado = models.BooleanField(
        verbose_name='Privado', default=True, help_text='O questionário ficará inacessível para repostas dos campi enquanto estiver privado.'
    )
    data_limite = models.DateFieldPlus(
        verbose_name='Data Limite para Respostas', null=True, blank=False, help_text='Data limite para que os campi possam responder o questionário.'
    )

    class Meta:
        verbose_name = 'Registro Educacenso'
        verbose_name_plural = 'Registros Educacenso'

    def __str__(self):
        return f'Educacenso {self.ano_censo} - Registro {self.numero_registro}'

    def get_absolute_url(self):
        return f'/edu/registroeducacenso/{self.pk}/'

    def get_respostas_por_campus(self, sigla_campus=None):
        resultados = []
        qs_campi = UnidadeOrganizacional.objects.campi()
        if sigla_campus:
            campus = qs_campi.get(sigla=sigla_campus)
            resultados.extend(RespostaEducacenso.objects.filter(questao__registro_id=self.pk, campus_id=campus.id))
        else:
            campi = qs_campi.all()
            for uo in campi:
                qs = RespostaEducacenso.objects.filter(questao__registro_id=self.pk, campus_id=uo.id)
                resultados.append({uo.sigla: qs})
        return resultados

    def get_questoes_para_resposta(self, campus_id):
        return RespostaEducacenso.objects.filter(questao__registro_id=self.pk, campus_id=campus_id)

    def get_situacao_resposta_questionario(self, campus_sigla):
        qs = RespostaEducacenso.objects.filter(questao__registro_id=self.pk, campus__sigla=campus_sigla)
        if qs.filter(situacao=RespostaEducacenso.SITUACAO_EDICAO).exists():
            return 'Em edição'
        if not qs.exclude(situacao=RespostaEducacenso.SITUACAO_CONCLUIDO).exists():
            return 'Concluído'
        return 'Aguardando respostas'

    def get_campi_questionario_pendente(self):
        qs = (
            RespostaEducacenso.objects.filter(
                questao__registro_id=self.pk,
                situacao__in=[RespostaEducacenso.SITUACAO_AGUARDANDO, RespostaEducacenso.SITUACAO_EDICAO],
            )
            .values_list('campus__sigla', flat=True)
            .distinct()
        )
        return qs

    def publicar(self):
        self.privado = False
        self.save()

    def fechar(self):
        self.privado = True
        self.save()

    def clonar(self, ano_censo, copiar_respostas=False):
        from edu import tasks

        return tasks.clonar_registro_educacenso(self, ano_censo, copiar_respostas)

    @staticmethod
    @transaction.atomic
    def atualizar_numero_campo(questao_atualizada):
        registro_id = questao_atualizada.registro.id
        questoes = QuestaoEducacenso.objects.filter(registro_id=registro_id).order_by('numero_campo')

        ordem_ultima_questao = questao_atualizada.numero_campo

        # numero_campo precisa estar entre 1 e a quantidade total de questões
        if ordem_ultima_questao < 1:
            ordem_ultima_questao = 1
        else:
            total_questoes = questoes.count()
            if ordem_ultima_questao > total_questoes:
                ordem_ultima_questao = total_questoes

        nova_ordem = list(questoes.exclude(id=questao_atualizada.id))

        nova_ordem.insert(ordem_ultima_questao - 1, questao_atualizada)

        for ordem, questao in enumerate(nova_ordem, start=1):
            if questao.numero_campo != ordem:
                questao.numero_campo = ordem
                questao.save()


class QuestaoEducacenso(LogModel):
    TIPO_REPOSTA_SIM_NAO = '1'
    TIPO_RESPOSTA_NUMERICA = '2'
    TIPO_RESPOSTA_NUMERICA_COM_ZERO = '3'
    TIPO_RESPOSTA = [[TIPO_REPOSTA_SIM_NAO, 'Sim/Não'], [TIPO_RESPOSTA_NUMERICA, 'Numérica >= 1'], [TIPO_RESPOSTA_NUMERICA_COM_ZERO, 'Numérica >= 0']]

    TIPO_OBRIGATORIEDADE_OBRIGATORIO = '1'
    TIPO_OBRIGATORIEDADE_CONDICIONAL = '2'
    TIPO_OBRIGATORIEDADE_NAO_OBRIGATORIO = '3'
    TIPO_OBRIGATORIEDADE = [
        [TIPO_OBRIGATORIEDADE_OBRIGATORIO, 'Obrigatório'],
        [TIPO_OBRIGATORIEDADE_CONDICIONAL, 'Condicional'],
        [TIPO_OBRIGATORIEDADE_NAO_OBRIGATORIO, 'Não Obrigatório'],
    ]

    registro = models.ForeignKeyPlus('edu.RegistroEducacenso', verbose_name='Registro Educacenso', null=False, blank=False)
    numero_campo = models.PositiveIntegerField(verbose_name='Número do Campo', null=False, blank=False)
    nome_campo = models.CharFieldPlus(verbose_name='Nome do Campo', null=False, blank=False)
    resposta_privada = models.BooleanField(
        verbose_name='Resposta Privada',
        default=False,
        help_text='Marque esta opção caso este campo deva ser respondido somente pelo Administrador Acadêmico.',
    )
    regra_resposta = models.TextField(verbose_name='Regra de Preenchimento', null=True, blank=True)
    tipo_resposta = models.CharFieldPlus(max_length=1, verbose_name='Tipo de Resposta', null=False, blank=False, choices=TIPO_RESPOSTA)
    tipo_obrigatoriedade = models.CharFieldPlus(
        max_length=1, verbose_name='Tipo de Obrigatoriedade', null=False, blank=False, choices=TIPO_OBRIGATORIEDADE
    )

    class Meta:
        verbose_name = 'Questão Educacenso'
        verbose_name_plural = 'Questões Educacenso'
        ordering = ('numero_campo',)

    def __str__(self):
        return f'{self.numero_campo} - {self.nome_campo}'


class RespostaEducacenso(LogModel):
    SITUACAO_AGUARDANDO = '1'
    SITUACAO_EDICAO = '2'
    SITUACAO_CONCLUIDO = '3'
    SITUACAO_CHOICES = [
        [SITUACAO_AGUARDANDO, 'Aguardando respostas'],
        [SITUACAO_EDICAO, 'Em edição'],
        [SITUACAO_CONCLUIDO, 'Concluído'],
    ]
    questao = models.ForeignKeyPlus('edu.QuestaoEducacenso', verbose_name='Questão', null=False, blank=False)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', null=False, blank=False)
    resposta = models.CharFieldPlus(verbose_name='Resposta', null=True, blank=True)
    situacao = models.CharFieldPlus(
        max_length=1, default=SITUACAO_AGUARDANDO, verbose_name='Situação', null=True, blank=False, choices=SITUACAO_CHOICES
    )

    class Meta:
        ordering = ('campus__sigla', 'questao__numero_campo')

    def __str__(self):
        return f'Resposta do Campus {self.campus.sigla} para a questão #{self.questao.numero_campo}: {self.get_resposta_display()}'

    def get_resposta_display(self):
        if self.questao.tipo_resposta == QuestaoEducacenso.TIPO_REPOSTA_SIM_NAO:
            if self.resposta in ['True', '1']:
                return 'Sim'
            if self.resposta in ['False', '0']:
                return 'Não'
        return self.resposta


class AuditoriaEnsino(LogModel):
    TIPO_SISTEC = '1'
    TIPO_SITUACAO_MATRICULA = '2'
    TIPO_RECEITA_FEDERAL = '3'
    TIPO_MATRICULA_MODALIDADE = '4'
    TIPO_NOME_ALUNO = '5'
    TIPO_NOME_PAIS = '6'
    TIPO_NOME_SERVIDOR = '7'
    TIPO_CIDADE = '8'
    TIPO_ALUNO_SEM_SISTEC = '9'
    TIPO_ALUNOS_RETIDOS = '10'

    TIPO_AUDITORIA_CHOICES = [
        [TIPO_SISTEC, 'SISTEC'],
        [TIPO_SITUACAO_MATRICULA, 'Mudança de Situação de Matrícula'],
        [TIPO_RECEITA_FEDERAL, 'Inconsistência com Dados da Receita Federal'],
        [TIPO_MATRICULA_MODALIDADE, 'Inconsistência de Matrículas em Modalidade'],
        [TIPO_NOME_ALUNO, 'Inconsistência em Nome de Aluno'],
        [TIPO_NOME_PAIS, 'Inconsistência em Nome de Pais de Aluno'],
        [TIPO_NOME_SERVIDOR, 'Inconsistência em Nome de Servidor'],
        [TIPO_CIDADE, 'Inconsistência em Cidades'],
        [TIPO_ALUNO_SEM_SISTEC, 'Aluno sem código SISTEC'],
        [TIPO_ALUNOS_RETIDOS, 'Alunos retidos'],
    ]

    TIPO_AUDITORIA_SOLICITAVEL_CHOICES = [
        [TIPO_SISTEC, 'SISTEC'],
    ]

    AUDITORIAS_MENSAIS = [TIPO_SITUACAO_MATRICULA]
    AUDITORIAS_TRIMESTRAIS = [TIPO_ALUNO_SEM_SISTEC, TIPO_MATRICULA_MODALIDADE, TIPO_CIDADE]
    AUDITORIAS_SEMESTRAIS = [TIPO_NOME_ALUNO, TIPO_NOME_PAIS, TIPO_NOME_SERVIDOR, TIPO_ALUNOS_RETIDOS]

    tipo_auditoria = models.CharFieldPlus(verbose_name='Tipo de Auditoria', null=False, blank=False, choices=TIPO_AUDITORIA_CHOICES)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', null=False, blank=False)
    nivel_ensino = models.ForeignKeyPlus('edu.NivelEnsino', verbose_name='Nível de ensino', null=True, blank=True)
    geracao_finalizada = models.BooleanField(verbose_name='Geração Finalizada', default=False)
    data_auditoria = models.DateTimeFieldPlus(verbose_name='Data de Criação da Auditoria', auto_now_add=True)
    auditor = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Auditor', related_name='auditoriaensino_auditor_set', on_delete=models.CASCADE, null=True, blank=False
    )
    atendente = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Atendente', related_name='auditoriaensino_atendente_set', on_delete=models.CASCADE, null=True, blank=True
    )
    data_ciencia_atendente = models.DateTimeFieldPlus(verbose_name='Data de Ciência do Atendente', null=True, blank=False)
    data_resolucao_auditoria = models.DateTimeFieldPlus(verbose_name='Data de Resolução da Auditoria', null=True, blank=False)
    resolvido_parcialmente = models.BooleanField(verbose_name='Há registros pendentes', null=True)
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    # uso excluivo para sistec
    fonte_dados = models.FileFieldPlus(
        upload_to='edu/censos/auditoria/',
        verbose_name='Fonte de Dados',
        filetypes=[
            'csv',
        ],
        null=True,
        blank=True,
        max_file_size=20 * settings.BYTES_SIZE_1MB,
    )
    solicitante = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Solicitante', related_name='auditoriaensino_solicitante_set', on_delete=models.CASCADE, null=True, blank=False
    )
    data_inicio_auditoria = models.DateFieldPlus(verbose_name='Data de Início da Auditoria', null=True, blank=False)
    data_fim_auditoria = models.DateFieldPlus(verbose_name='Data Final da Auditoria', null=True, blank=True)

    class Meta:
        verbose_name = 'Auditoria do Ensino'
        verbose_name_plural = 'Auditorias do Ensino'

    def get_absolute_url(self):
        return f'/edu/auditoria_ensino/{self.pk}/'

    def pode_solicitar(self, user):
        return user.has_perm('edu.add_auditoriaensino') and self.is_auditoria_sistec()

    def pode_gerar(self, user):
        return (
            user.has_perm('comum.is_administrador_academico') and self.is_auditoria_sistec() and self.fonte_dados and not self.is_auditoria_gerada()
        )

    def pode_editar_atendente(self, user):
        result = user.has_perm('edu.change_auditoriaensino') and self.data_ciencia_atendente and self.data_resolucao_auditoria is None
        if result and not user.has_perm('comum.is_administrador_academico'):
            result = user.get_vinculo().setor.uo == self.campus and not self.is_auditoria_administrador()
        return result

    def pode_desfazer(self, user):
        return (
            user.has_perm('comum.is_administrador_academico')
            and self.is_auditoria_sistec()
            and self.data_ciencia_atendente is None
            and self.is_auditoria_gerada()
        )

    def pode_informar_dados(self, user):
        return user.has_perm('comum.is_administrador_academico') and self.is_auditoria_sistec() and not self.is_auditoria_gerada()

    def pode_atender(self, user):
        result = self.is_auditoria_gerada() and user.has_perm('edu.change_auditoriaensino') and not self.data_ciencia_atendente
        if not user.has_perm('comum.is_administrador_academico'):
            result = result and user.get_vinculo().setor.uo == self.campus and not self.is_auditoria_administrador()
        return result

    def pode_resolver(self, user):
        return user.get_vinculo() == self.atendente and self.data_resolucao_auditoria is None

    def pode_ver_registros(self, user):
        return self.is_auditoria_gerada() and user.has_perm('edu.view_auditoriaensino')

    def pode_exportar(self, user):
        return self.is_auditoria_gerada() and (
            user.has_perm('comum.is_administrador_academico') or user.has_perm('edu.view_auditoriaensino') and self.data_ciencia_atendente
        )

    def pode_notificar_campus(self, user):
        return (
            user.has_perm('comum.is_administrador_academico')
            and self.is_auditoria_sistec()
            and self.is_auditoria_gerada()
            and self.data_resolucao_auditoria is None
        )

    def notificar_campus(self, user):
        from edu.auditoria_ensino import AuditoriaEnsinoService

        if self.pode_notificar_campus(user):
            AuditoriaEnsinoService.notificar_campus(self)

    def possui_form_correcao(self):
        return self.tipo_auditoria in [
            AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC,
            AuditoriaEnsino.TIPO_RECEITA_FEDERAL,
            AuditoriaEnsino.TIPO_NOME_PAIS,
            AuditoriaEnsino.TIPO_NOME_ALUNO,
        ]

    def solicitar(self, user):
        if self.pode_solicitar(user):
            self.solicitante = user.get_vinculo()
            self.save()
            if self.pode_gerar(user):
                return self.gerar(user)

    def gerar(self, user):
        from edu import tasks

        if self.pode_gerar(user):
            self.auditor = user.get_vinculo()
            self.save()
            return tasks.gerar_auditoria_ensino(self)

    def desfazer_auditoria_gerada(self, user):
        from edu import tasks

        if self.pode_desfazer(user):
            self.auditor = None
            self.geracao_finalizada = False
            self.save()
            return tasks.remover_registros_auditoria_ensino(self)

    def atender(self, user):
        if self.pode_atender(user):
            self.atendente = user.get_vinculo()
            self.data_ciencia_atendente = datetime.datetime.now()
            self.save()

    def editar_atendente(self, user):
        if self.pode_editar_atendente(user):
            if self.atendente is None:
                self.data_ciencia_atendente = None
            self.save()

    def resolver(self, user):
        if self.pode_resolver(user):
            self.data_resolucao_auditoria = datetime.datetime.now()
            self.save()

    def exportar(self, user):
        from edu import tasks

        if self.pode_exportar(user):
            return tasks.exportar_auditoria_ensino(self)

    def atualizar_situacao_registros(self, user):
        pendentes = list(self.get_registros_auditoria().filter(situacao__isnull=True))
        if not pendentes:
            return 0

        matriculas_map = {r.get_matricula(): r for r in pendentes if r.get_matricula()}
        alunos_com_sistec = set(
            Aluno.objects.filter(matricula__in=matriculas_map.keys(), codigo_sistec__isnull=False)
            .exclude(codigo_sistec='')
            .values_list('matricula', flat=True)
        )

        atualizados = 0
        for matricula in alunos_com_sistec:
            registro = matriculas_map.get(matricula)
            if registro:
                registro.situacao = RegistroAuditoriaEnsino.SITUACAO_RESOLVIDO
                registro.registrar_situacao(user)
                atualizados += 1
        return atualizados

    def is_auditoria_sistec(self):
        return self.tipo_auditoria == self.TIPO_SISTEC

    def is_auditoria_aluno_sem_sistec(self):
        return self.tipo_auditoria == self.TIPO_ALUNO_SEM_SISTEC

    def is_auditoria_administrador(self):
        return self.tipo_auditoria in [self.TIPO_ALUNO_SEM_SISTEC, self.TIPO_CIDADE]

    def is_auditoria_gerada(self):
        return self.geracao_finalizada is True

    def get_registros_auditoria(self, divergente=True):
        return self.registroauditoriaensino_set.filter(divergente=divergente)

    def get_ignorados_auditorias_anteriores(self):
        return RegistroAuditoriaEnsino.objects.filter(
            situacao=RegistroAuditoriaEnsino.SITUACAO_IGNORADO,
            auditoria_ensino__tipo_auditoria=self.tipo_auditoria,
            auditoria_ensino__campus_id=self.campus.id,
            auditoria_ensino__data_auditoria__lt=self.data_auditoria,
        )

    _HEADERS_POR_TIPO = {
        TIPO_SITUACAO_MATRICULA: ['NOME', 'SITUAÇÃO ANTERIOR', 'SITUAÇÃO ATUAL', 'DATA MUDANÇA', 'CURSO'],
        TIPO_RECEITA_FEDERAL: ['NOME SUAP', 'NOME RF', 'NASCIMENTO SUAP', 'NASCIMENTO RF', 'MÃE SUAP', 'MÃE RF', 'CURSO'],
        TIPO_MATRICULA_MODALIDADE: ['NOME', 'MODALIDADE', 'SITUAÇÃO', 'CURSO'],
        TIPO_NOME_ALUNO: ['NOME', 'CAMPUS', 'DIRETORIA', 'CURSO'],
        TIPO_NOME_PAIS: ['PARENTESCO', 'NOME', 'CAMPUS', 'DIRETORIA', 'CURSO'],
        TIPO_NOME_SERVIDOR: ['NOME', 'CAMPUS'],
        TIPO_CIDADE: ['CAMPUS', 'VÍNCULO', 'CIDADE', 'CURSO'],
        TIPO_ALUNO_SEM_SISTEC: ['NOME', 'SITUAÇÃO', 'CURSO'],
        TIPO_ALUNOS_RETIDOS: ['NOME', 'SITUAÇÃO', 'CURSO', 'DATA PREVISTA TÉRMINO'],
    }

    def get_header(self, to_xls=False):
        default = [
            'MATRÍCULA',
            'CPF',
        ]
        if to_xls:
            default = ['SITUAÇÃO ATENDIMENTO', *default]
        if self.is_auditoria_sistec():
            return [*default, 'NOME', 'SITUAÇÃO SISTEC', 'SITUAÇÃO SUAP', 'SITUAÇÃO AUDITORIA', 'CURSO', 'CICLO']
        colunas = self._HEADERS_POR_TIPO.get(self.tipo_auditoria)
        return [*default, *colunas] if colunas is not None else ''

    def get_auditor(self):
        if self.is_auditoria_sistec():
            return self.auditor or '-'
        return 'Sistema'

    def get_pendencia(self):
        if self.is_auditoria_sistec():
            if self.fonte_dados.name == '':
                return 'Aguardando fonte de dados.'
            if self.auditor and not self.is_auditoria_gerada():
                return 'Geração da auditoria em andamento.'
            if not self.is_auditoria_gerada():
                return 'Aguardando geração da auditoria.'
        if self.is_auditoria_gerada():
            if self.data_ciencia_atendente is None:
                return 'Aguardando início do atendimento.'
            if self.data_resolucao_auditoria is None:
                return 'Aguardando resolução da auditoria'
        return None

    def get_situacao(self):
        if self.data_resolucao_auditoria:
            return 'Resolvida'
        if self.data_ciencia_atendente:
            return 'Em Atendimento'
        if self.is_auditoria_sistec() and not self.is_auditoria_gerada():
            return 'Solicitada'
        return 'Gerada'


class RegistroAuditoriaEnsino(models.ModelPlus):
    class History:
        disabled = True

    SITUACAO_RESOLVIDO = '1'
    SITUACAO_IGNORADO = '2'

    SITUACAO_CHOICES = [
        [SITUACAO_RESOLVIDO, 'Resolvido'],
        [SITUACAO_IGNORADO, 'Ignorado'],
    ]

    auditoria_ensino = models.ForeignKeyPlus('edu.AuditoriaEnsino', verbose_name='Auditoria do Ensino', null=False, blank=False)
    registro = models.TextField(verbose_name='Registro', null=False, blank=False)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=True, blank=True, choices=SITUACAO_CHOICES)
    atendente = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Atendente', on_delete=models.CASCADE, null=True, blank=True)
    divergente = models.BooleanField(default=True)

    def get_itens(self, to_xls=False):
        if to_xls:
            situacao = '-' if self.situacao is None else self.get_situacao_display()
            return [situacao, *self.registro.split(';')]
        return self.registro.split(';')

    def get_resumo(self):
        itens = self.get_itens()
        return f'Registro: Matrícula: {itens[0]} | CPF: {itens[1]}'

    def get_matricula(self):
        return self.get_itens()[0]

    def registrar_situacao(self, user):
        self.atendente = user.get_vinculo()
        self.save()


class AberturaExtemporanea(LogModel):
    SOLICITADA = '1'
    DEFERIDA = '2'
    INICIADA = '3'
    FINALIZADA = '4'
    INDEFERIDA = '5'

    SITUACAO_CHOICES = [
        [SOLICITADA, 'Solicitada'],
        [DEFERIDA, 'Deferida'],
        [INICIADA, 'Iniciada'],
        [FINALIZADA, 'Finalizada'],
        [INDEFERIDA, 'Indeferida'],
    ]

    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=SITUACAO_CHOICES, default=SOLICITADA)

    # solicitação
    qtd_alunos = models.PositiveIntegerField(
        verbose_name='Quantidade de alunos', null=False, blank=False, help_text='Quantidade de alunos envolvidos na abertura extemporânea.'
    )
    data_inicio_ciclo = models.DateFieldPlus(
        verbose_name='Data de início', null=True, blank=False, help_text='Data de início dos ciclos a serem corrigidos.'
    )
    data_fim_ciclo = models.DateFieldPlus(verbose_name='Data final', null=True, blank=False, help_text='Data final dos ciclos a serem corrigidos.')
    justificativa = models.TextField(verbose_name='Justificativa da solicitação', null=False, blank=False)
    diretoria = models.ForeignKeyPlus('edu.Diretoria', verbose_name='Diretoria', null=True, blank=False)
    solicitante = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Solicitante',
        related_name='aberturaextemporanea_solicitante_set',
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    # deferimento
    vinculo_reitor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo de Reitor', null=True)
    data_deferimento = models.DateTimeFieldPlus(verbose_name='Data do Deferimento', null=True)
    configuracao = models.ForeignKeyPlus('edu.ConfiguracaoAberturaExtemporanea', verbose_name='Configuração de Abertura Extemporânea', null=True)
    requerimento = models.FileFieldPlus(verbose_name='Requerimento', upload_to='edu/censos/abertura_extemporanea/requerimentos/', null=True)

    # abertura
    periodo_abertura = models.PositiveIntegerField(
        verbose_name='Período de Abertura', null=True, blank=False, help_text='Quantidade de dias da abertura extemporânea.'
    )
    data_inicio = models.DateFieldPlus(verbose_name='Data de início', null=True, blank=False)
    data_fim = models.DateFieldPlus(verbose_name='Data final', null=True, blank=True)

    vinculo_administrador = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Vínculo de Administrador', null=True, related_name='aberturaextemporanea_vinculo_administrador_set'
    )
    cursos = models.ManyToManyFieldPlus('edu.CursoCampus', verbose_name='Cursos', blank=True)
    campi = models.TextField(
        verbose_name='Campi',
        null=True,
        blank=False,
        help_text='Informe a sigla do campus seguida da quantidade de alunos, separadas por dois-pontos. Exemplo: CNAT:123. Insira um registro por linha.',
    )

    class Meta:
        verbose_name = 'Abertura Extemporânea'
        verbose_name_plural = 'Aberturas Extemporâneas'

    def get_absolute_url(self):
        return f'/edu/abertura_extemporanea/{self.pk}/'

    def get_configuracao(self):
        if self.diretoria:
            return ConfiguracaoAberturaExtemporanea.objects.filter(ativo=True, tipo_modelo=ConfiguracaoAberturaExtemporanea.TIPO_INDIVIDUAL).first()
        else:
            return ConfiguracaoAberturaExtemporanea.objects.filter(
                ativo=True, tipo_modelo=ConfiguracaoAberturaExtemporanea.TIPO_MULTIPLUS_CAMPI
            ).first()

    def pode_deferir(self, user):
        return user.eh_servidor and user.has_perm('comum.is_reitor') and self.situacao == AberturaExtemporanea.SOLICITADA

    def pode_iniciar(self, user):
        return user.has_perm('comum.is_administrador_academico') and self.situacao == AberturaExtemporanea.DEFERIDA

    @transaction.atomic()
    def deferir(self, user: User, id_certificado: int | str, senha_certificado: str) -> None:
        from edu.models.diretorias import Diretoria
        from edu.models.regulacao import AtoRegulatorioCurso

        configuracao = self.get_configuracao()
        if configuracao is None:
            raise Exception('Nenhuma configuração de abertura extemporânea encontrada.')

        if not self.diretoria and not self.campi:
            raise Exception('Diretoria ou campus não informado.')

        # Monta o #EMAIL_CAMPUS# do requerimento assinado: vazia, sairia "gabin.<campus>@.edu.br".
        sigla_instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao_sigla').lower()
        if not sigla_instituicao:
            raise Exception('Configuração comum.instituicao_sigla não definida: necessária para o e-mail do campus no requerimento.')

        if self.pode_deferir(user):
            vinculo = user.get_vinculo()

            titulo = 'Reitor' if vinculo.relacionamento.sexo == 'M' else 'Reitora'
            if not vinculo.relacionamento.eh_reitor():
                titulo = f'{titulo} em Exercício'

            lista_campi = []
            lista_cursos = []
            lista_modalidades = []
            lista_atos = []
            if self.diretoria is None:
                diretoria = Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA).first()
                lista_campi = self.get_campi()
            else:
                diretoria = self.diretoria
                for curso in self.cursos.all():
                    lista_cursos.append(curso.descricao_historico)
                    lista_modalidades.append(curso.modalidade.descricao)
                    lista_atos.append(curso.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO).first())

            gabinete_campus = (
                Setor.objects.suap_ativos()
                .filter(sigla=f'GABIN/{diretoria.setor.uo.sigla.upper()}')
                .select_related('uo')
                .only('uo__telefone')
                .first()
            )
            hoje = datetime.datetime.now()
            data_formatada = format_data_extenso(hoje.date())

            dicionario = {
                '#GESTOR_REITOR#': vinculo.relacionamento.nome,
                '#CPF_GESTOR_REITOR#': f'{vinculo.relacionamento.cpf[0:3]}.***.***-**',
                '#GESTOR_CAMPUS#': diretoria.diretor_geral and diretoria.diretor_geral.relacionamento.nome or vinculo.relacionamento.nome,
                '#SISTEC_CAMPUS#': diretoria.setor.uo.codigo_sistec,
                '#CAMPUS#': str(diretoria.setor.uo.nome),
                '#ENDERECO_CAMPUS#': diretoria.setor.uo.endereco,
                '#EMAIL_GESTOR#': diretoria.diretor_geral
                and diretoria.diretor_geral.relacionamento.email_institucional
                or vinculo.relacionamento.email_institucional,
                '#EMAIL_CAMPUS#': f'gabin.{diretoria.setor.uo.sigla.lower()}@{sigla_instituicao}.edu.br',
                '#TELEFONE_CAMPUS#': gabinete_campus and gabinete_campus.uo.telefone,
                '#TELEFONE_GESTOR#': diretoria.setor.uo.telefone or vinculo.setor.uo.telefone,
                '#PERIODO#': f'{self.data_inicio_ciclo.strftime("%d/%m/%Y")} a {self.data_fim_ciclo.strftime("%d/%m/%Y")}',
                '#DIAS_ABERTURA#': self.periodo_abertura,
                '#QUANTIDADE_ALUNOS#': self.qtd_alunos,
                '#JUSTIFICATIVA#': self.justificativa,
                '#DATA#': data_formatada,
                '#NOME_CURSO#': libreoffice_new_line(lista_cursos or '-'),
                '#MODALIDADE#': libreoffice_new_line(lista_modalidades or '-'),
                '#ATO_REGULATORIO#': libreoffice_new_line(lista_atos or '-'),
                '#CAMPI#': libreoffice_new_line(lista_campi),
            }

            chave_assinatura = uuid.uuid1().hex
            caminho_arquivo = gerar_documento_impressao(dicionario, io.BytesIO(configuracao.modelo_requerimento.read()))
            if not caminho_arquivo:
                raise Exception('Documento não encontrado.')
            with open(caminho_arquivo, 'rb') as local_filename:
                content = local_filename.read()
            caminho_relativo = os.path.join('edu/censos/abertura_extemporanea/requerimentos/', f'{chave_assinatura}-{caminho_arquivo.split("/")[-1]}')
            default_storage.save(caminho_relativo, io.BytesIO(content))
            os.unlink(caminho_arquivo)
            self.requerimento = caminho_relativo

            certificado_digital = CertificadoDigital.objects.get(pk=id_certificado)
            certificado_digital.assinar_arquivo_pdf(
                self.requerimento.name,
                senha_certificado,
                adicionar_texto=False,
                adicionar_imagem=True,
                x=270,
                y=770,
                bgcolor='#EEEEEE',
                page=1,
                titulo=titulo,
            )

            self.data_deferimento = datetime.datetime.now()
            self.vinculo_reitor = vinculo
            self.situacao = AberturaExtemporanea.DEFERIDA
            self.configuracao = configuracao
            self.save()

            qs_usuario_grupo = UsuarioGrupo.objects.filter(group__name='Administrador Acadêmico').select_related('user').distinct()
            administradores = [ug.user.get_vinculo() for ug in qs_usuario_grupo]
            titulo = '[SUAP] Deferimento de Abertura Extemporânea'
            texto_diretoria = self.diretoria and f'solicitada pela {self.diretoria}' or 'administração acadêmica'
            texto = (
                '<h2>Deferimento de Abertura Extemporânea</h2>'
                f'<p>A abertura extemporânea {texto_diretoria} foi deferida.</p>'
                f'<p>Acesse {settings.SITE_URL}/admin/edu/aberturaextemporanea/?tab=tab_deferida para listar todas as solicitações deferidas.</p>'
            )

            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, administradores, fail_silently=True)

    def get_campi(self) -> list[str]:
        lista_campi = []
        for c in self.campi.split('\n'):
            if c:
                sigla, qtd = c.split(':')
                sigla = sigla.strip()
                qtd = int(qtd.strip())
                if not isinstance(qtd, int) or qtd <= 0:
                    raise ValidationError(f'Quantidade de alunos inválida: {qtd}')
                uo = UnidadeOrganizacional.objects.filter(sigla=sigla, codigo_sistec__isnull=False).exclude(codigo_sistec='').first()
                if uo is None:
                    raise ValidationError(f'Sigla do campus inválida: {sigla}')

                instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
                lista_campi.append(f'{uo.codigo_sistec} - {instituicao} - {uo.nome.upper()}: {qtd} alunos')
        return lista_campi

    def indeferir(self, user):
        if self.pode_deferir(user):
            self.data_deferimento = datetime.datetime.now()
            self.vinculo_reitor = user.get_vinculo()
            self.situacao = AberturaExtemporanea.INDEFERIDA
            self.save()

    def iniciar(self, user):
        if self.pode_iniciar(user):
            self.vinculo_administrador = user.get_vinculo()
            self.data_fim = somar_dias(self.data_inicio, self.periodo_abertura - 1)
            self.situacao = AberturaExtemporanea.INICIADA
            self.save()

            qs_usuario_grupo = UsuarioGrupo.objects.filter(group__name='Secretário Acadêmico').select_related('user').distinct()
            if self.diretoria:
                qs_usuario_grupo = qs_usuario_grupo.filter(setores__id=self.diretoria.setor.pk)

            secretarios = [ug.user.get_vinculo() for ug in qs_usuario_grupo]
            titulo = '[SUAP] Período de Abertura Extemporânea Iniciada'
            texto = (
                '<h2>Período de Abertura Extemporânea Iniciada</h2>'
                f'<p>O período de abertura extemporânea ficará aberto entre os dias {self.data_inicio.strftime("%d/%m/%Y")} e {self.data_fim.strftime("%d/%m/%Y")}.</p>'
                f'<p>Acesse {settings.SITE_URL}/admin/edu/aberturaextemporanea/?tab=tab_iniciada para listar todas as solicitações iniciadas.</p>'
            )

            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, secretarios, fail_silently=True)

    def solicitar(self, user, cursos=None):
        self.solicitante = user.get_vinculo()
        if self.diretoria is None:
            self.qtd_alunos = 0
        self.save()
        if cursos:
            for curso in cursos:
                self.cursos.add(curso)

    def is_iniciada(self):
        return self.situacao == AberturaExtemporanea.INICIADA


class ConfiguracaoAberturaExtemporanea(LogModel):
    TIPO_INDIVIDUAL = '1'
    TIPO_MULTIPLUS_CAMPI = '2'

    TIPO_CHOICES = [
        [TIPO_INDIVIDUAL, 'Individual'],
        [TIPO_MULTIPLUS_CAMPI, 'Múltiplos campi'],
    ]

    modelo_requerimento = models.FileFieldPlus(
        upload_to='edu/censos/abertura_extemporanea/',
        filetypes=['docx'],
        null=False,
        blank=False,
        verbose_name='Modelo de Requerimento',
        check_mimetype=False,
        help_text="""O modelo de requerimento deve ser uma arquivo .docx contendo as marcações #GESTOR_CAMPUS#, #GESTOR_REITOR#, #CPF_GESTOR_REITOR#, #SISTEC_CAMPUS#, #CAMPUS#, #ENDERECO_CAMPUS#, #EMAIL_GESTOR#, #EMAIL_CAMPUS#, #TELEFONE_GESTOR#, #TELEFONE_CAMPUS#, #PERIODO#, #DIAS_ABERTURA#, #QUANTIDADE_ALUNOS#, #JUSTIFICATIVA#, #DATA#, #NOME_CURSO#, #MODALIDADE#, #ATO_REGULATORIO#, #CAMPI#""",
    )
    ativo = models.BooleanField(default=False)
    tipo_modelo = models.CharFieldPlus('Tipo', choices=TIPO_CHOICES, null=False, blank=False, default=TIPO_INDIVIDUAL)

    class Meta:
        verbose_name = 'Configuração de Abertura Extemporânea'
        verbose_name_plural = 'Configurações de Abertura Extemporânea'

    # TODO: permitir apenas um registro ativo


class JustificativaCensup(LogModel):
    SEARCH_FIELDS = [
        'ano_letivo__ano',
    ]

    arquivo = models.FileFieldPlus(
        upload_to='edu/censos/justificativa_censup/',
        filetypes=[
            'txt',
        ],
        null=False,
        blank=False,
        verbose_name='Arquivo de Justificativas',
        check_mimetype=False,
    )
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo')

    class Meta:
        verbose_name = 'Justificativa CENSUP'
        verbose_name_plural = 'Justificativas CENSUP'

    def __str__(self):
        return f'Justificativa CENSUP {self.ano_letivo}'

    def get_absolute_url(self):
        return f'/edu/justificativacensup/{self.pk}/'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not RespostaJustificativaCensup.objects.filter(justificativa_censup_id=self.id).exists():
            for line in self.arquivo.file.readlines():
                tokens = line.decode().split('|')
                if tokens[0] != 'LINHA':
                    identificacao = tokens[1].split('-')
                    cpf = mask_cpf(identificacao[0].split(':')[1].strip())
                    cod_censup = identificacao[1].split(':')[1].strip()

                    mensagem = re.split(r'\d{2} - ', tokens[4], maxsplit=1)[0].strip()
                    padrao_opcoes = re.compile(r'(\d{2}) - ([^;]+)')
                    lista_opcoes = padrao_opcoes.findall(tokens[4])
                    if lista_opcoes:
                        opcoes = '; '.join([f'{codigo} - {descricao}' for codigo, descricao in lista_opcoes])
                    else:
                        continue

                    aluno = (
                        Aluno.objects.filter(pessoa_fisica__cpf=cpf, curso_campus__codigo_censup=cod_censup, ano_letivo__ano__lte=self.ano_letivo.ano)
                        .order_by('-data_matricula')
                        .first()
                    )
                    if aluno:
                        resposta = RespostaJustificativaCensup()
                        resposta.justificativa_censup = self
                        resposta.aluno = aluno
                        resposta.mensagem = mensagem
                        resposta.opcoes = opcoes
                        resposta.save()


class RespostaJustificativaCensup(LogModel):
    RESPOSTA_CHOICES = [
        ['1', 'O aluno reingressou no mesmo curso'],
        ['2', 'O aluno reingressou no mesmo curso e o semestre de ingresso foi informado incorretamente no Censo anterior'],
        ['3', 'Situação do vínculo do aluno informada errada no Censo anterior'],
        ['4', 'Situação do vínculo e semestre de ingresso informados incorretamente no Censo anterior'],
        ['5', 'Curso ou local de oferta não carregado para o Censo anterior'],
        ['6', 'Curso em que o aluno estava vinculado não existe no Censo atual'],
        ['7', 'A IES não vinculou o aluno no Censo anterior'],
        ['8', 'Semestre de ingresso informado errado no Censo anterior'],
        ['9', 'Situação de vínculo informada errada, aluno formado no curso BI/LI correspondente no Censo Anterior'],
        ['10', 'Aluno não informado no curso BI/LI correspondente no Censo Anterior'],
        ['11', 'Aluno concluiu o curso BI/LI correspondente até o ano de <ano censo atual -2>'],
        ['12', 'O aluno reingressou no mesmo curso. Situação de vínculo e semestre de ingresso informados errados no Censo anterior'],
    ]

    justificativa_censup = models.ForeignKeyPlus('edu.JustificativaCensup', null=False, blank=False)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', null=False, blank=False)
    mensagem = models.CharFieldPlus('Mensagem', null=False, blank=False)
    opcoes = models.CharFieldPlus('Opções', null=False, blank=False)
    resposta = models.CharFieldPlus('Resposta', choices=RESPOSTA_CHOICES, null=True, blank=False)

    respondente = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Respondente', null=True)
    data_resposta = models.DateTimeFieldPlus(verbose_name='Data da Resposta', null=True)

    class Meta:
        verbose_name = 'Resposta de Justificativa CENSUP'
        verbose_name_plural = 'Respostas de Justificativa CENSUP'

    def get_absolute_url(self):
        return f'/edu/respostajustificativacensup/{self.pk}/'

    def get_opcoes_choices(self):
        choices = []
        for item in self.opcoes.split(';'):
            value, label = item.split('-')
            choices.append([int(value.strip()), label.strip()])
        return choices

    def pode_solicitar_alteracao_resposta(self, user):
        return self.resposta and not user.has_perm('edu.delete_respostajustificativacensup')

    def pode_avaliar_solicitacao(self, user):
        return user.has_perm('edu.delete_respostajustificativacensup')

    def responder(self, user):
        self.respondente = user.get_vinculo()
        self.data_resposta = datetime.datetime.now()
        self.save()
        self.notificar()

    def notificar(self):
        diretoria = self.aluno.curso_campus.diretoria
        if not RespostaJustificativaCensup.objects.filter(
            resposta__isnull=True, justificativa_censup_id=self.justificativa_censup.id, aluno__curso_campus__diretoria_id=diretoria.id
        ).exists():
            # todas as justificativas da diretoria foram respondidas
            qs_usuario_grupo = UsuarioGrupo.objects.filter(group__name='Administrador Acadêmico').select_related('user').distinct()
            administradores = [ug.user.get_vinculo() for ug in qs_usuario_grupo]
            titulo = '[SUAP] Justificativas CENSUP Respondidas'
            texto = (
                '<h2>Justificativas CENSUP Respondidas</h2>'
                f'<p>Todas as justificativas do CENSUP {self.justificativa_censup.ano_letivo} da diretoria {diretoria} foram respondidas.</p>'
            )

            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, administradores, fail_silently=True)


class AlteracaoRespostaJustificativaCensup(LogModel):
    resposta_justificativa_censup = models.ForeignKeyPlus('edu.RespostaJustificativaCensup', null=False, blank=False)
    deferido = models.BooleanField('Deferido', null=True)
    resposta = models.CharFieldPlus('Resposta', choices=RespostaJustificativaCensup.RESPOSTA_CHOICES, null=False, blank=False)
    solicitante = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Solicitante', null=False)
    data_solicitacao = models.DateTimeFieldPlus(verbose_name='Data da Resposta', null=False)

    class Meta:
        verbose_name = 'Solicitação de Alteração de Resposta de Justificativa CENSUP'
        verbose_name_plural = 'Solicitações de Alterações de Respostas de Justificativa CENSUP'

    def get_absolute_url(self):
        return f'/edu/respostajustificativacensup/{self.resposta_justificativa_censup.pk}/'

    def solicitar(self, user):
        self.solicitante = user.get_vinculo()
        self.data_solicitacao = datetime.datetime.now()
        self.save()

    def avaliar(self):
        self.save()
        if self.deferido:
            self.resposta_justificativa_censup.resposta = self.resposta
            self.resposta_justificativa_censup.respondente = self.solicitante
            self.resposta_justificativa_censup.data_resposta = self.data_solicitacao
            self.resposta_justificativa_censup.save()

    def get_opcoes_choices(self):
        choices = []
        for item in self.resposta_justificativa_censup.opcoes.split(';'):
            value, label = item.split('-')
            if int(self.resposta_justificativa_censup.resposta) != int(value.strip()):
                choices.append([int(value.strip()), label.strip()])
        return choices


class Laboratorio(LogModel):
    AREA_CONHECIMENTO_EXATAS = '1'
    AREA_CONHECIMENTO_BIOLOGICAS = '2'
    AREA_CONHECIMENTO_ENGENHARIAS = '3'
    AREA_CONHECIMENTO_SAUDE = '4'
    AREA_CONHECIMENTO_AGRARIAS = '5'
    AREA_CONHECIMENTO_SOCIAIS = '6'
    AREA_CONHECIMENTO_HUMANAS = '7'
    AREA_CONHECIMENTO_LINGUISTICA = '8'

    AREA_CONHECIMENTO_CHOICES = [
        [AREA_CONHECIMENTO_EXATAS, 'Ciências Exatas e da Terra'],
        [AREA_CONHECIMENTO_BIOLOGICAS, 'Ciências Biológicas'],
        [AREA_CONHECIMENTO_ENGENHARIAS, 'Engenharias'],
        [AREA_CONHECIMENTO_SAUDE, 'Ciência da Saúde'],
        [AREA_CONHECIMENTO_AGRARIAS, 'Ciências Agrárias'],
        [AREA_CONHECIMENTO_SOCIAIS, 'Ciências Sociais Aplicadas'],
        [AREA_CONHECIMENTO_HUMANAS, 'Ciências Humanas'],
        [AREA_CONHECIMENTO_LINGUISTICA, 'Linguística, Letras e Artes'],
    ]

    nome = models.CharFieldPlus(verbose_name='Nome', null=False, blank=False)
    descricao = models.TextField(verbose_name='Descrição das atividades', null=True, blank=True)
    palavras_chave = models.CharFieldPlus(
        verbose_name='Pàlavras-Chave', null=True, blank=True, help_text='Informe até 3 palavras separadas por espaço.'
    )
    sala = models.ForeignKeyPlus('comum.Sala', null=False, blank=False)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    laboratorio_informatica = models.BooleanField(verbose_name='Laboratório de informática', default=False)
    area_conhecimento_1 = models.CharFieldPlus(verbose_name='Área de conhecimento 1', choices=AREA_CONHECIMENTO_CHOICES, null=True, blank=True)
    area_conhecimento_2 = models.CharFieldPlus(verbose_name='Área de conhecimento 2', choices=AREA_CONHECIMENTO_CHOICES, null=True, blank=True)

    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('sala__predio__uo')

    class Meta:
        verbose_name = 'Laboratório'
        verbose_name_plural = 'Laboratórios'

    def clean(self):
        if Laboratorio.objects.filter(nome=self.nome).exclude(id=self.id).exists():
            raise ValidationError('Já existe um laboratório com esse nome.')
        return super().clean()

    def get_absolute_url(self):
        return f'/edu/laboratorio/{self.id}/'

    def get_areas_conhecimento(self):
        result = []
        if self.area_conhecimento_1:
            result.append(self.get_area_conhecimento_1_display())
        if self.area_conhecimento_2:
            result.append(self.get_area_conhecimento_2_display())
        return result


class ExecucaoPlanoLaboratorio(LogModel):
    ano = models.ForeignKeyPlus('comum.Ano', null=False, blank=False)
    laboratorio = models.ForeignKeyPlus('edu.Laboratorio', null=False, blank=False)

    plano_politica_acesso = models.BooleanField(verbose_name='Executou plano de política de acesso e agendamento', default=False)
    plano_manutencao = models.BooleanField(verbose_name='Executou plano de manutenção', default=False)
    plano_riscos = models.BooleanField(verbose_name='Executou plano de gerenciamento de riscos', default=False)
    plano_residuos = models.BooleanField(verbose_name='Executou plano de gerenciamento de resíduos', default=False)

    id_documento = models.PositiveIntegerFieldPlus(
        verbose_name='Identificador', null=True, blank=True, help_text='Código de identificação do documento.'
    )
    arquivo_documento = models.FileFieldPlus(
        'Documento',
        upload_to='edu/plano_laboratorio/',
        null=True,
        blank=True,
        filetypes=[
            'pdf',
        ],
    )
    url_documento = models.URLField(verbose_name='Link do plano', null=True, blank=True)

    class Meta:
        verbose_name = 'Execução de plano em laboratório'
        verbose_name_plural = 'Execuções de planos em laboratório'

    def clean(self):
        if ExecucaoPlanoLaboratorio.objects.filter(id=self.laboratorio_id, ano=self.ano).exclude(id=self.id).exists():
            raise ValidationError(f'Já existe uma execução de planos em laboratório cadastrada para o ano {self.ano.ano}.')
        return super().clean()

    def get_absolute_url(self):
        return f'/edu/execucaoplanolaboratorio/{self.id}/'

    @staticmethod
    def get_documento(id_documento):
        result = None
        if id_documento and 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            result = DocumentoTexto.objects.filter(id=id_documento).first()
        return result

    def get_link_documento(self):
        if self.url_documento:
            return self.url_documento
        elif self.id_documento:
            documento = ExecucaoPlanoLaboratorio.get_documento(self.id_documento)
            if documento:
                return documento.get_absolute_url()
        elif self.arquivo_documento:
            return self.arquivo_documento.url
        return None

    def get_planos(self):
        planos = []
        if self.plano_politica_acesso:
            planos.append('Política de acesso e agendamento')
        if self.plano_manutencao:
            planos.append('Manutenção')
        if self.plano_riscos:
            planos.append('Gerenciamento de riscos')
        if self.plano_residuos:
            planos.append('Gerenciamento de resíduos')
        return planos
