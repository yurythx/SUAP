import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache

from comum.models import Ano, User
from djtools.db import models
from edu.models import CalendarioAcademico, Professor
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES
from edu.models.logs import LogModel
from rh.models import Servidor


class AtividadeEnsino(models.ModelPlus):
    SUBGRUPOS = [
        (1, 'Aulas'),
        (2, 'Atividade de Preparação, Manutenção e Apoio ao Ensino'),
        (3, 'Programas ou Projetos de Ensino'),
        (4, 'Atendimento, Acompanhamento, Avaliação e Orientação de Alunos'),
        (5, 'Reuniões Pedagógicas, de Grupo e Afins'),
    ]

    descricao = models.CharFieldPlus(verbose_name='Descrição')
    subgrupo = models.IntegerField(verbose_name='Subgrupo', choices=SUBGRUPOS)

    class Meta:
        verbose_name = 'Atividade de Ensino'
        verbose_name_plural = 'Atividades de Ensino'

    def __str__(self):
        return self.descricao


class AtividadePesquisa(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Atividade de Pesquisa e Inovação'
        verbose_name_plural = 'Atividades de Pesquisa e Inovação'

    def __str__(self):
        return self.descricao


class AtividadeExtensao(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Atividade de Extensão'
        verbose_name_plural = 'Atividades de Extensão'

    def __str__(self):
        return self.descricao


class AtividadeGestao(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Atividade de Gestão'
        verbose_name_plural = 'Atividades de Gestão'

    def __str__(self):
        return self.descricao


class PlanoIndividualTrabalhoV2(LogModel):
    ANO_INICIO_APP = 2019

    # DADOS GERAIS
    ano_letivo = models.ForeignKeyPlus(Ano, verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.IntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)

    professor = models.ForeignKeyPlus(Professor, verbose_name='Professor', on_delete=models.CASCADE)

    # ENSINO
    # Aulas
    obs_aulas = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_aulas = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # Preparação e Manutenção ao Ensino
    ch_preparacao_manutencao_ensino = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    obs_preparacao_manutencao_ensino = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_preparacao_manutencao_ensino = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)
    # Apoio ao Ensino
    ch_apoio_ensino = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    atividades_apoio_ensino = models.ManyToManyFieldPlus(AtividadeEnsino, verbose_name='Atividades', related_name='a1')
    outras_atividades_apoio_ensino = models.TextField(verbose_name='Outras Atividades', null=True, blank=True)
    obs_apoio_ensino = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_apoio_ensino = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # Programas ou Projetos de Ensino
    ch_programas_projetos_ensino = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    obs_programas_projetos_ensino = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_programas_projetos_ensino = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # Atendimento, Acompanhamento, Avaliação e Orientação de Alunos
    ch_orientacao_alunos = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    atividades_orientacao_alunos = models.ManyToManyFieldPlus(AtividadeEnsino, verbose_name='Atividades', related_name='a2')
    outras_atividades_orientacao_alunos = models.TextField(verbose_name='Outras Atividades', null=True, blank=True)
    obs_orientacao_alunos = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_orientacao_alunos = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # Reuniões Pedagógicas, de Grupo e Afins
    ch_reunioes = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    atividades_reunioes = models.ManyToManyFieldPlus(AtividadeEnsino, verbose_name='Atividades', related_name='a3')
    outras_atividades_reunioes = models.TextField(verbose_name='Outras Atividades', null=True, blank=True)
    obs_reunioes = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_reunioes = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # PESQUISA E INOVAÇÃO
    ch_pesquisa = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    atividades_pesquisa = models.ManyToManyFieldPlus(AtividadePesquisa, verbose_name='Atividades')
    outras_atividades_pesquisa = models.TextField(verbose_name='Outras Atividades', null=True, blank=True)
    obs_pesquisa = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_pesquisa = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # EXTENSÃO
    ch_extensao = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    atividades_extensao = models.ManyToManyFieldPlus(AtividadeExtensao, verbose_name='Atividades')
    outras_atividades_extensao = models.TextField(verbose_name='Outras Atividades', null=True, blank=True)
    obs_extensao = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_extensao = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # GESTÃO E REPRESENTAÇÃO INSTITUCIONAL
    ch_gestao = models.PositiveIntegerField(verbose_name='Carga-Horária', default=0)
    atividades_gestao = models.ManyToManyFieldPlus(AtividadeGestao, verbose_name='Atividades')
    outras_atividades_gestao = models.TextField(verbose_name='Outras Atividades', null=True, blank=True)
    obs_gestao = models.TextField(verbose_name='Observações', null=True, blank=False)
    arquivo_gestao = models.FileFieldPlus(verbose_name='Arquivo', null=True, blank=True, upload_to='pit_rit_v2', can_view=True)

    # DADOS DA AVALIAÇÃO DO PLANO
    data_envio = models.DateTimeFieldPlus(verbose_name='Data do Envio do Plano', null=True)
    avaliador = models.ForeignKeyPlus(Servidor, verbose_name='Avaliador do Plano', null=True, on_delete=models.CASCADE)
    aprovado = models.BooleanField(verbose_name='Plano Aprovado', null=True)
    data_aprovacao = models.DateTimeFieldPlus(verbose_name='Data da Aprovação do Plano', null=True)

    # DADOS DA AVALIAÇÃO DO RELATORIO
    data_envio_relatorio = models.DateTimeFieldPlus(verbose_name='Data do Envio do Relatório', null=True)
    avaliador_relatorio = models.ForeignKeyPlus(
        Servidor, verbose_name='Avaliador do Relatório', null=True, on_delete=models.CASCADE, related_name='avaliador_relatorio_set'
    )
    relatorio_aprovado = models.BooleanField(verbose_name='Relatório Aprovado', null=True)
    data_aprovacao_relatorio = models.DateTimeFieldPlus(verbose_name='Data da Aprovação do Relatório', null=True)

    # DADOS DA PUBLICAÇÃO
    publicado = models.BooleanField(verbose_name='Publicado', null=True)
    responsavel_publicacao = models.ForeignKeyPlus(
        Servidor, verbose_name='Responsável pela Publicação', null=True, related_name='responsavel_publiacao_set', on_delete=models.CASCADE
    )
    data_publicacao = models.DateTimeFieldPlus(verbose_name='Data da Publicação', null=True)

    class Meta:
        verbose_name = 'Plano Individual de Trabalho'
        verbose_name_plural = 'Planos Individuais de Trabalho'

    def save(self, *args, **kwargs):
        super().save()
        if self.avaliador:
            user = User.objects.get(username=self.avaliador.matricula)
            group = Group.objects.get(name='Avaliador de Plano Individual de Trabalho')
            user.groups.add(group)
        if self.avaliador_relatorio:
            user = User.objects.get(username=self.avaliador_relatorio.matricula)
            group = Group.objects.get(name='Avaliador de Plano Individual de Trabalho')
            user.groups.add(group)
        if self.responsavel_publicacao:
            user = User.objects.get(username=self.responsavel_publicacao.matricula)
            group = Group.objects.get(name='Publicador de Plano Individual de Trabalho')
            user.groups.add(group)
        cache.delete(f'check_pit_rit_{self.professor.vinculo.user.pk}')

    def can_change(self, user=None):
        return user == self.professor.vinculo.user

    def get_absolute_url(self):
        return f'/edu/professor/{self.professor.pk}/?tab=planoatividades&ano-periodo={self.ano_letivo}.{self.periodo_letivo}'

    def __str__(self):
        return f'Plano Individual de Trabalho - {self.professor} - {self.ano_letivo}/{self.periodo_letivo}'

    def is_relatorio_preenchido(self):
        for attr in (
            'obs_aulas',
            'obs_preparacao_manutencao_ensino',
            'obs_apoio_ensino',
            'obs_programas_projetos_ensino',
            'obs_orientacao_alunos',
            'obs_reunioes',
            'obs_pesquisa',
            'obs_extensao',
            'obs_gestao',
        ):
            if getattr(self, attr) is None:
                return False
        return True

    def get_atividades(self, tipo):
        lista = []
        for atividade in getattr(self, tipo).all():
            lista.append(atividade.descricao)
        for atividade in (getattr(self, f'outras_{tipo}') or '').split('\n'):
            if atividade.strip():
                lista.append(atividade)
        return lista

    def get_atividades_apoio_ensino(self):
        return self.get_atividades('atividades_apoio_ensino')

    def get_atividades_orientacao_alunos(self):
        return self.get_atividades('atividades_orientacao_alunos')

    def get_atividades_reunioes(self):
        return self.get_atividades('atividades_reunioes')

    def get_atividades_pesquisa(self):
        return self.get_atividades('atividades_pesquisa')

    def get_atividades_extensao(self):
        return self.get_atividades('atividades_extensao')

    def get_atividades_gestao(self):
        return self.get_atividades('atividades_gestao')

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

    # Diários Especiais
    def get_vinculos_diarios_especiais(self, is_cap=None):
        return self.professor.get_vinculos_diarios_especiais(self.ano_letivo.ano, self.periodo_letivo, is_cap)

    def get_ch_semanal_diarios_especiais(self):
        ch_semanal_diarios_especiais = 0
        ch_semanal_diarios_especiais_hr = 0
        for diario_especial in self.get_vinculos_diarios_especiais(True):
            ch_ha = diario_especial.get_carga_horaria_semanal_ha()
            ch_semanal_diarios_especiais += ch_ha
            ch_semanal_diarios_especiais_hr += (
                Decimal(ch_ha * (diario_especial.componente.ch_hora_relogio / diario_especial.componente.ch_hora_aula))
                if ch_ha and diario_especial.componente.ch_hora_aula > 0
                else 0
            )
        if ch_semanal_diarios_especiais > 6:
            ch_semanal_diarios_especiais = 6
        for diario_especial in self.get_vinculos_diarios_especiais(False):
            ch_ha = diario_especial.get_carga_horaria_semanal_ha()
            ch_semanal_diarios_especiais += ch_ha
            ch_semanal_diarios_especiais_hr += (
                Decimal(ch_ha * (diario_especial.componente.ch_hora_relogio / diario_especial.componente.ch_hora_aula))
                if ch_ha and diario_especial.componente.ch_hora_aula > 0
                else 0
            )
        return ch_semanal_diarios_especiais, ch_semanal_diarios_especiais_hr

    # Cargas-Horárias
    def get_cargas_horarias(self):
        ch_semanal_diarios, ch_semanal_efetiva = self.get_ch_diarios()
        ch_semanal_diarios_fic, ch_semanal_efetiva_fic = self.get_ch_diarios(True)
        ch_semanal_minicursos, ch_semanal_minicursos_hr = self.get_ch_minicursos()
        ch_semanal_diarios_especiais, ch_semanal_diarios_especiais_hr = self.get_ch_semanal_diarios_especiais()
        ch_preparacao_manutencao_ensino = self.ch_preparacao_manutencao_ensino
        ch_apoio_ensino = self.ch_apoio_ensino
        ch_programas_projetos_ensino = self.ch_programas_projetos_ensino
        ch_orientacao_alunos = self.ch_orientacao_alunos
        ch_reunioes = self.ch_reunioes

        ch_pesquisa = self.ch_pesquisa
        ch_extensao = self.ch_extensao
        ch_gestao = self.ch_gestao

        ch_semanal_aulas = ch_semanal_diarios + ch_semanal_diarios_fic + ch_semanal_minicursos + ch_semanal_diarios_especiais

        percentual = Decimal(settings.PERCENTUAL_CH_PREPARACAO_AULAS_PIT / 100)
        ch_aulas_hr = round(percentual * (ch_semanal_efetiva + ch_semanal_efetiva_fic + ch_semanal_minicursos_hr + ch_semanal_diarios_especiais_hr))

        ch_total = (
            ch_aulas_hr
            + ch_preparacao_manutencao_ensino
            + ch_apoio_ensino
            + ch_programas_projetos_ensino
            + ch_orientacao_alunos
            + ch_reunioes
            + ch_pesquisa
            + ch_extensao
            + ch_gestao
        )
        return (
            ch_semanal_aulas,
            ch_aulas_hr,
            ch_semanal_diarios,
            ch_semanal_diarios_fic,
            ch_semanal_minicursos,
            ch_semanal_diarios_especiais,
            ch_preparacao_manutencao_ensino,
            ch_apoio_ensino,
            ch_programas_projetos_ensino,
            ch_orientacao_alunos,
            ch_reunioes,
            ch_pesquisa,
            ch_extensao,
            ch_gestao,
            ch_total,
        )

    def get_ch_total_semanal(self):
        return self.get_cargas_horarias()[-1]

    def get_ch_total_aulas(self):
        return self.get_cargas_horarias()[0]

    def pode_enviar_plano(self, user):
        return self.aprovado is None and self.data_envio is None and self.professor.vinculo.user == user

    def pode_alterar_avaliador_plano(self, user):
        return self.aprovado is None and self.data_envio and self.professor.vinculo.user == user

    def pode_avaliar_plano(self, user):
        return self.aprovado is None and self.data_envio and self.avaliador.get_vinculo().user == user

    def pode_desfazer_aprovacao_plano(self, user):
        return self.aprovado and self.avaliador.get_vinculo().user == user and not self.publicado and self.data_envio_relatorio is None

    def pode_preencher_relatorio(self, user):
        return self.aprovado and self.data_envio_relatorio is None and self.professor.vinculo.user == user

    def pode_enviar_relatorio(self, user):
        return (
            self.aprovado
            and self.is_relatorio_preenchido()
            and self.relatorio_aprovado is None
            and self.data_envio_relatorio is None
            and self.professor.vinculo.user == user
        )

    def pode_alterar_avaliador_relatorio(self, user):
        return (
            self.aprovado
            and self.is_relatorio_preenchido()
            and self.relatorio_aprovado is None
            and self.data_envio_relatorio
            and self.professor.vinculo.user == user
        )

    def pode_avaliar_relatorio(self, user):
        return self.aprovado and self.data_envio_relatorio and self.relatorio_aprovado is None and self.avaliador_relatorio.get_vinculo().user == user

    def pode_desfazer_aprovacao_relatorio(self, user):
        return self.relatorio_aprovado and self.avaliador_relatorio.get_vinculo().user == user and not self.publicado

    def pode_desfazer_publicacao_relatorio(self, user):
        return self.publicado and user.has_group_cached('Administrador Acadêmico')

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

    def aprovar_relatorio(self, user, parecer, responsavel_publicacao):
        if self.pode_avaliar_relatorio(user):
            self.relatorio_aprovado = True
            self.data_aprovacao_relatorio = datetime.datetime.now()
            self.responsavel_publicacao = responsavel_publicacao
            self.save()

            parecer.pit = self
            parecer.data = self.data_aprovacao_relatorio
            parecer.tipo = 'RIT'
            parecer.servidor = self.avaliador_relatorio
            parecer.save()

    def devolver_relatorio(self, user, parecer):
        if self.pode_avaliar_relatorio(user) or self.pode_desfazer_aprovacao_relatorio(user):
            parecer.pit = self
            parecer.data = datetime.datetime.now()
            parecer.tipo = 'RIT'
            parecer.servidor = self.avaliador_relatorio
            parecer.save()

            self.relatorio_aprovado = None
            self.data_aprovacao_relatorio = None
            self.data_envio_relatorio = None
            self.avaliador_relatorio = None
            self.responsavel_publicacao = None
            self.save()

    @classmethod
    def check_pit_rit(cls, user):
        CACHE_24H = 86400  # 24 horas em segundos
        key = f'check_pit_rit_{user.pk}'
        value = cache.get(key)
        if value is not None:
            return value
        mensagens = []
        hoje = datetime.date.today()
        vinculo = user.get_vinculo()
        if not vinculo.setor:
            return [(False, 'Usuário sem setor.')]

        calendario_referencia = (
            CalendarioAcademico.objects.filter(eh_calendario_referencia=True, uo=vinculo.setor.uo, data_fim__gte=hoje).order_by('data_fim').first()
        )
        if calendario_referencia:
            if calendario_referencia.data_inicio_etapa_3 is None or (
                calendario_referencia.data_inicio_etapa_3 and hoje < calendario_referencia.data_inicio_etapa_3
            ):
                periodo_letivo = 1
            else:
                periodo_letivo = 2
            # Não gerar nenhum alerta caso o módulo tenha sido desativado em favor da V3
            if 'pit_rit_v3' in settings.INSTALLED_APPS:
                from pit_rit_v3.models import PlanoIndividualTrabalhoV3

                if PlanoIndividualTrabalhoV3.modulo_ativo(calendario_referencia.ano_letivo.ano, periodo_letivo):
                    return []
            pit = cls.objects.filter(professor__vinculo=vinculo, ano_letivo=calendario_referencia.ano_letivo, periodo_letivo=periodo_letivo).first()
            if pit:
                # PIT
                data_inicio_prazo = calendario_referencia.data_inicio_etapa_1 if periodo_letivo == 1 else calendario_referencia.data_inicio_etapa_3
                data_termino_prazo = data_inicio_prazo + datetime.timedelta(days=30)
                prazo = (data_termino_prazo - hoje).days
                # print("Calendário de Referência:", calendario_referencia)
                # print("Período Letivo (PIT):", f"{calendario_referencia.ano_letivo}.{periodo_letivo}")
                # print("Início do Prazo (PIT):", data_inicio_prazo)
                # print("Término do Prazo (PIT):", data_termino_prazo)
                # print("Data do Envio (PIT):", pit.data_envio)
                # print("Prazo (PIT):", None if pit.data_envio else prazo)
                if data_inicio_prazo <= hoje and pit.data_envio is None:
                    if prazo == 0:
                        mensagem = (False, f'O PIT referente ao período letivo {pit.ano_letivo}.{pit.periodo_letivo} deve ser entregue hoje.')
                    elif prazo > 0:
                        mensagem = (
                            False,
                            f'Você tem {prazo} dias para entregar o PIT referente ao período letivo {pit.ano_letivo}.{pit.periodo_letivo}.',
                        )
                    else:
                        mensagem = (
                            True,
                            f'O PIT referente ao período letivo {pit.ano_letivo}.{periodo_letivo} está pendente de entrega há {-prazo} dias.',
                        )
                    mensagens.append(mensagem)
                # RIT
                rit = None
                if periodo_letivo == 2:
                    rit = pit
                    rit_ano_letivo = pit.ano_letivo
                    rit_periodo_letivo = 1
                    rit = cls.objects.filter(professor__vinculo=vinculo, ano_letivo=rit_ano_letivo, periodo_letivo=rit_periodo_letivo).first()
                    data_inicio_prazo_rit = calendario_referencia.data_inicio_etapa_3
                    data_termino_prazo_rit = data_inicio_prazo_rit + datetime.timedelta(days=30)
                    prazo_rit = (data_termino_prazo_rit - hoje).days
                else:
                    rit_ano_letivo = Ano.objects.get_or_create(ano=calendario_referencia.ano_letivo.ano - 1)[0]
                    rit_periodo_letivo = 2
                    rit = cls.objects.filter(professor__vinculo=vinculo, ano_letivo=rit_ano_letivo, periodo_letivo=rit_periodo_letivo).first()
                    data_inicio_prazo_rit = calendario_referencia.data_inicio_etapa_1
                    data_termino_prazo_rit = data_inicio_prazo_rit + datetime.timedelta(days=30)
                    prazo_rit = (data_termino_prazo_rit - hoje).days

                if rit:
                    if rit.aprovado and data_inicio_prazo_rit <= hoje and rit.data_envio_relatorio is None:
                        if prazo_rit == 0:
                            mensagem_rit = (False, f'O RIT referente ao período letivo {rit.ano_letivo}.{rit.periodo_letivo} deve ser entregue hoje.')
                        elif prazo_rit > 0:
                            mensagem_rit = (
                                False,
                                f'Você tem {prazo_rit} dias para entregar o RIT referente ao período letivo {rit.ano_letivo}.{rit.periodo_letivo}.',
                            )
                        else:
                            mensagem_rit = (
                                True,
                                f'O RIT referente ao período letivo {rit.ano_letivo}.{rit.periodo_letivo} está pendente de entrega há {-prazo} dias.',
                            )
                        mensagens.append(mensagem_rit)
                elif pit.professor.requer_pit_no_periodo(rit_ano_letivo.ano, rit_periodo_letivo):
                    mensagens.append((True, f'O RIT referente ao período letivo {rit_ano_letivo}.{rit_periodo_letivo} ainda não foi cadastrado.'))
            else:
                mensagens.append(
                    (True, f'O PIT referente ao período letivo {calendario_referencia.ano_letivo}.{periodo_letivo} ainda não foi cadastrado.')
                )
        cache.set(key, mensagens, timeout=CACHE_24H)
        return mensagens


class Parecer(models.ModelPlus):
    pit = models.ForeignKeyPlus(PlanoIndividualTrabalhoV2, verbose_name='Plano Individual de Trabalho')
    tipo = models.CharFieldPlus(verbose_name='Tipo', null=True, choices=[['PIT', 'PIT'], ['RIT', 'RIT']], default='PIT')
    data = models.DateTimeFieldPlus(verbose_name='Data')
    obs = models.TextField(verbose_name='Observação')
    servidor = models.ForeignKeyPlus(
        Servidor, verbose_name='Servidor', null=True, on_delete=models.CASCADE, help_text='Servidor que emitiu o parecer'
    )

    class Meta:
        verbose_name = 'Parecer'
        verbose_name_plural = 'Pareceres'
        ordering = ('-data',)

    def __str__(self):
        return self.obs


class HistoricoReaberturaRelatorio(models.ModelPlus):
    pit = models.ForeignKeyPlus(PlanoIndividualTrabalhoV2, verbose_name='Plano Individual de Trabalho')
    data = models.DateTimeFieldPlus(verbose_name='Data', auto_created=True)
    relatorio = models.FileField(verbose_name='Relatório Anterior', upload_to='rits', null=True)
    responsavel = models.CurrentUserField(verbose_name='Responsável')
    justificativa = models.TextField(verbose_name='Justificativa')

    class Meta:
        verbose_name = 'Histórico de Reabertura de Relatório'
        verbose_name_plural = 'Histórico de Reabertura de Relatório'
